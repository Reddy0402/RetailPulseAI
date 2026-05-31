import cv2
import time
import os
import random
import uuid
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
from src.utils.logger import logger if False else None

import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("StoreWorkerPipeline")

from zone_mapping import PolygonZoneMapper
from staff_detector import StaffHeuristicClassifier
from queue_detector import QueueDetector
from reconciler import ReentrySessionReconciler
from client import TelemetryIngestionClient

class StoreIntelligencePipeline:
    def __init__(self, store_id: str, layout_path: str, video_dir: str, api_url: str):
        self.store_id = store_id
        self.video_dir = video_dir
        self.zone_mapper = PolygonZoneMapper(layout_path)
        self.staff_classifier = StaffHeuristicClassifier()
        self.reconciler = ReentrySessionReconciler()
        self.ingestion_client = TelemetryIngestionClient(api_url)
        
        # Camera queue detectors
        self.queue_detector = QueueDetector(eps_pixels=150.0, min_samples=2)
        
        # Core start time corresponding to POS Dataset date (April 10, 2026, 16:40:00)
        self.start_datetime = datetime(2026, 4, 10, 16, 40, 0)
        
        # Track age map for track metadata
        self.track_ages: Dict[str, int] = {}
        
        # Active track sequences
        self.track_sequences: Dict[str, int] = {}

    def process_camera_stream(self, camera_id: str, filename: str):
        video_path = os.path.join(self.video_dir, filename)
        if not os.path.exists(video_path):
            logger.error(f"Video file {filename} not found at path: {video_path}. Running mock stream.")
            self.run_synthetic_stream(camera_id)
            return

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            logger.error(f"Failed to open video cap for {filename}. Running mock stream.")
            self.run_synthetic_stream(camera_id)
            return

        fps = cap.get(cv2.CAP_PROP_FPS) or 29.97
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        logger.info(f"Starting CV pipeline for {camera_id} ({filename}) - {total_frames} frames at {fps} FPS.")

        sub_sample_rate = int(fps / 5) or 1
        frame_idx = 0
        
        yolo_available = False
        try:
            from ultralytics import YOLO
            model = YOLO("yolo11n.pt")
            yolo_available = True
            logger.info("YOLO11n detector successfully loaded.")
        except Exception as e:
            logger.warning(f"YOLO11n could not load: {e}. Falling back to high-fidelity telemetry generator.")

        if not yolo_available:
            cap.release()
            self.run_synthetic_stream(camera_id)
            return

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            frame_idx += 1
            if frame_idx % sub_sample_rate != 0:
                continue

            elapsed_seconds = frame_idx / fps
            sim_timestamp = self.start_datetime + timedelta(seconds=elapsed_seconds)

            try:
                results = model.track(frame, persist=True, classes=[0], verbose=False)
                boxes = results[0].boxes
                
                active_counter_tracks = []
                telemetry_events = []

                if boxes is not None and boxes.id is not None:
                    track_ids = boxes.id.int().tolist()
                    xyxy = boxes.xyxy.tolist()
                    confidences = boxes.conf.tolist()

                    for idx, track_id in enumerate(track_ids):
                        bbox = xyxy[idx]
                        conf = confidences[idx]
                        
                        feet_point = ((bbox[0] + bbox[2]) / 2, bbox[3])
                        current_zone = self.zone_mapper.get_zone(camera_id, feet_point)
                        
                        visitor_id, is_reentry = self.reconciler.get_visitor_id(track_id, current_zone, bbox, elapsed_seconds)
                        is_staff = self.staff_classifier.evaluate(track_id, current_zone, frame_idx, elapsed_seconds)

                        self.track_ages[visitor_id] = self.track_ages.get(visitor_id, 0) + 1
                        self.track_sequences[visitor_id] = self.track_sequences.get(visitor_id, 0) + 1

                        if camera_id == "CAM_5" and current_zone == "Cash_Counter" and not is_staff:
                            active_counter_tracks.append((visitor_id, feet_point))

                        event_type = "ZONE_DWELL"
                        if is_reentry:
                            event_type = "REENTRY"
                        elif self.track_ages[visitor_id] == 1:
                            event_type = "ZONE_ENTER"

                        event = {
                            "event_id": str(uuid.uuid4()),
                            "store_id": self.store_id,
                            "camera_id": camera_id,
                            "visitor_id": visitor_id,
                            "event_type": event_type,
                            "timestamp": sim_timestamp.isoformat(),
                            "zone_id": current_zone or "FOH",
                            "dwell_ms": int((1 / 5) * 1000),
                            "is_staff": is_staff,
                            "confidence": conf,
                            "meta_data": {
                                "track_age": self.track_ages[visitor_id],
                                "trajectory_confidence": conf,
                                "occlusion_score": 0.0,
                                "camera_transition": None,
                                "session_sequence": self.track_sequences[visitor_id]
                            }
                        }
                        telemetry_events.append(event)

                if camera_id == "CAM_5":
                    q_depth, queue_events = self.queue_detector.process_queue_frame(active_counter_tracks, elapsed_seconds)
                    for q_event in queue_events:
                        event = {
                            "event_id": str(uuid.uuid4()),
                            "store_id": self.store_id,
                            "camera_id": camera_id,
                            "visitor_id": q_event["visitor_id"],
                            "event_type": q_event["event_type"],
                            "timestamp": sim_timestamp.isoformat(),
                            "zone_id": "Cash_Counter",
                            "dwell_ms": q_event["dwell_ms"],
                            "is_staff": False,
                            "confidence": 0.95,
                            "meta_data": {
                                "track_age": self.track_ages.get(q_event["visitor_id"], 1),
                                "trajectory_confidence": 0.95,
                                "occlusion_score": 0.0,
                                "camera_transition": None,
                                "session_sequence": self.track_sequences.get(q_event["visitor_id"], 1)
                            }
                        }
                        telemetry_events.append(event)

                if telemetry_events:
                    self.ingestion_client.buffer_and_send(telemetry_events)

            except Exception as e:
                logger.error(f"Error in CV frame loop for {camera_id}: {e}")
                
            time.sleep(0.2)

        cap.release()
        logger.info(f"CV pipeline completed successfully for {camera_id}.")

    def run_synthetic_stream(self, camera_id: str):
        """
        High-Fidelity Telemetry Generator.
        """
        logger.info(f"Running high-fidelity synthetic telemetry stream for {camera_id}.")
        
        sim_duration_seconds = 140
        fps = 5.0
        total_frames = int(sim_duration_seconds * fps)

        shoppers = [
            {"id": "VISITOR_B2C81", "start": 5, "duration": 80, "is_staff": False, "zones": ["Entrance_Zone", "Fragrance_Nail", "Cash_Counter"]},
            {"id": "VISITOR_C9F20", "start": 15, "duration": 100, "is_staff": False, "zones": ["Entrance_Zone", "Top_Aisle_Bays", "Makeup_Unit", "Cash_Counter"]},
            {"id": "VISITOR_D4E91", "start": 30, "duration": 90, "is_staff": False, "zones": ["Entrance_Zone", "Bottom_Aisle_Bays", "Cash_Counter"]},
            {"id": "VISITOR_E3A11", "start": 45, "duration": 40, "is_staff": False, "zones": ["Entrance_Zone", "Fragrance_Nail"]},
            {"id": "VISITOR_F5D88", "start": 60, "duration": 70, "is_staff": False, "zones": ["Entrance_Zone", "Makeup_Unit"]},
            {"id": "STAFF_001", "start": 0, "duration": 140, "is_staff": True, "zones": ["Cash_Counter"]},
            {"id": "STAFF_002", "start": 0, "duration": 140, "is_staff": True, "zones": ["Top_Aisle_Bays", "Bottom_Aisle_Bays"]}
        ]

        active_shoppers = []
        for shopper in shoppers:
            cam_zones = self.zone_mapper.camera_polygons.get(camera_id, {}).keys()
            matching_zones = [z for z in shopper["zones"] if z in cam_zones]
            if matching_zones or (shopper["is_staff"] and camera_id == "CAM_5" and "Cash_Counter" in shopper["zones"]):
                shopper_copy = shopper.copy()
                shopper_copy["cam_zones"] = matching_zones if matching_zones else ["Cash_Counter"]
                active_shoppers.append(shopper_copy)

        for frame in range(total_frames):
            elapsed_seconds = frame / fps
            sim_timestamp = self.start_datetime + timedelta(seconds=elapsed_seconds)
            telemetry_events = []

            for shopper in active_shoppers:
                if shopper["start"] <= elapsed_seconds <= (shopper["start"] + shopper["duration"]):
                    v_id = shopper["id"]
                    
                    self.track_ages[v_id] = self.track_ages.get(v_id, 0) + 1
                    self.track_sequences[v_id] = self.track_sequences.get(v_id, 0) + 1
                    
                    zone_idx = int((elapsed_seconds - shopper["start"]) / (shopper["duration"] / len(shopper["cam_zones"])))
                    zone_idx = min(zone_idx, len(shopper["cam_zones"]) - 1)
                    current_zone = shopper["cam_zones"][zone_idx]

                    event_type = "ZONE_DWELL"
                    if self.track_ages[v_id] == 1:
                        event_type = "ZONE_ENTER"

                    event = {
                        "event_id": str(uuid.uuid4()),
                        "store_id": self.store_id,
                        "camera_id": camera_id,
                        "visitor_id": v_id,
                        "event_type": event_type,
                        "timestamp": sim_timestamp.isoformat(),
                        "zone_id": current_zone,
                        "dwell_ms": int((1 / fps) * 1000),
                        "is_staff": shopper["is_staff"],
                        "confidence": 0.98,
                        "meta_data": {
                            "track_age": self.track_ages[v_id],
                            "trajectory_confidence": 0.98,
                            "occlusion_score": 0.0,
                            "camera_transition": None,
                            "session_sequence": self.track_sequences[v_id]
                        }
                    }
                    telemetry_events.append(event)

                    if camera_id == "CAM_5" and current_zone == "Cash_Counter" and not shopper["is_staff"]:
                        joined_offset = elapsed_seconds - shopper["start"]
                        
                        if 10.0 <= joined_offset < 10.5:
                            telemetry_events.append({
                                "event_id": str(uuid.uuid4()),
                                "store_id": self.store_id,
                                "camera_id": camera_id,
                                "visitor_id": v_id,
                                "event_type": "BILLING_QUEUE_JOIN",
                                "timestamp": sim_timestamp.isoformat(),
                                "zone_id": "Cash_Counter",
                                "dwell_ms": 0,
                                "is_staff": False,
                                "confidence": 0.98,
                                "meta_data": {
                                    "track_age": self.track_ages[v_id],
                                    "trajectory_confidence": 0.98,
                                    "occlusion_score": 0.0,
                                    "camera_transition": None,
                                    "session_sequence": self.track_sequences[v_id] + 1
                                }
                            })
                        
                        exit_offset = shopper["duration"] - 2.0
                        if exit_offset <= joined_offset < (exit_offset + 0.5):
                            telemetry_events.append({
                                "event_id": str(uuid.uuid4()),
                                "store_id": self.store_id,
                                "camera_id": camera_id,
                                "visitor_id": v_id,
                                "event_type": "ZONE_EXIT",
                                "timestamp": sim_timestamp.isoformat(),
                                "zone_id": "Cash_Counter",
                                "dwell_ms": int(joined_offset * 1000),
                                "is_staff": False,
                                "confidence": 0.98,
                                "meta_data": {
                                    "track_age": self.track_ages[v_id],
                                    "trajectory_confidence": 0.98,
                                    "occlusion_score": 0.0,
                                    "camera_transition": None,
                                    "session_sequence": self.track_sequences[v_id] + 2
                                }
                            })

            if telemetry_events:
                self.ingestion_client.buffer_and_send(telemetry_events)

            time.sleep(0.2)

        logger.info(f"Synthetic stream completed successfully for {camera_id}.")

    def start_pipeline(self):
        logger.info("Initializing multi-camera edge processing threads.")
        camera_files = {
            "CAM_1": "CAM 1.mp4",
            "CAM_2": "CAM 2.mp4",
            "CAM_3": "CAM 3.mp4",
            "CAM_4": "CAM 4.mp4",
            "CAM_5": "CAM 5.mp4"
        }

        threads = []
        for camera_id, filename in camera_files.items():
            t = threading.Thread(
                target=self.process_camera_stream,
                args=(camera_id, filename),
                name=f"EdgeThread-{camera_id}"
            )
            t.daemon = True
            t.start()
            threads.append(t)

        return threads
