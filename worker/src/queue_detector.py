import numpy as np
from sklearn.cluster import DBSCAN
from typing import Dict, List, Set, Tuple

class QueueDetector:
    """
    Density-Based Checkout Queue Estimator.
    Applies DBSCAN clustering on customer foot coordinates inside the Cash Counter zone
    to distinguish active queue lines from walking bypass shoppers.
    """
    def __init__(self, eps_pixels: float = 150.0, min_samples: int = 2):
        self.eps = eps_pixels
        self.min_samples = min_samples
        
        # Track active queue states: visitor_id -> {joined_time, in_queue}
        self.active_queue_tracks: Dict[str, dict] = {}
        
        # Track history of emitted joins to prevent duplicate joins in same session
        self.emitted_joins: Set[str] = set()

    def process_queue_frame(self, active_counter_tracks: List[Tuple[str, Tuple[float, float]]], timestamp: float) -> Tuple[int, List[dict]]:
        """
        Processes active tracks currently inside the Cash Counter zone.
        Returns:
            queue_depth: Number of visitors clustered in the queue line.
            emitted_events: List of BILLING_QUEUE_JOIN or BILLING_QUEUE_ABANDON events to ingest.
        """
        emitted_events = []
        if not active_counter_tracks:
            # Cleanup active queue tracks if empty
            self.active_queue_tracks.clear()
            return 0, []

        # 1. Extract foot coordinates
        track_ids = [t[0] for t in active_counter_tracks]
        coords = np.array([t[1] for t in active_counter_tracks])

        # 2. Apply DBSCAN spatial clustering
        # Clusters standing shoppers close to register computer coords
        queue_depth = 0
        in_queue_set = set()

        if len(coords) >= self.min_samples:
            db = DBSCAN(eps=self.eps, min_samples=self.min_samples).fit(coords)
            labels = db.labels_

            for idx, label in enumerate(labels):
                if label != -1:  # Not noise
                    queue_depth += 1
                    in_queue_set.add(track_ids[idx])

        # 3. State Management & Event Generation
        for track_id in track_ids:
            is_in_queue = track_id in in_queue_set

            if is_in_queue:
                if track_id not in self.active_queue_tracks:
                    # Joined queue
                    self.active_queue_tracks[track_id] = {
                        "joined_time": timestamp,
                        "last_seen": timestamp,
                        "in_queue": True
                    }
                    # Only emit JOIN once per session to prevent spamming
                    if track_id not in self.emitted_joins:
                        self.emitted_joins.add(track_id)
                        emitted_events.append({
                            "event_type": "BILLING_QUEUE_JOIN",
                            "visitor_id": track_id,
                            "timestamp": timestamp,
                            "zone_id": "Cash_Counter",
                            "dwell_ms": 0
                        })
                else:
                    self.active_queue_tracks[track_id]["last_seen"] = timestamp
                    self.active_queue_tracks[track_id]["in_queue"] = True
            else:
                if track_id in self.active_queue_tracks:
                    self.active_queue_tracks[track_id]["in_queue"] = False

        # 4. Check for Queue Abandonments
        # Shopper was in queue for >40 seconds, exits without crossing checkout line
        abandoned_tracks = []
        for track_id, state in list(self.active_queue_tracks.items()):
            # If they haven't been seen in queue for >5 seconds
            if not state["in_queue"] or (timestamp - state["last_seen"]) > 5.0:
                dwell_in_queue = timestamp - state["joined_time"]
                
                # Exits queue back to store aisles (shoppers who checked out exit rightward)
                # If they were standing in queue for >40s but didn't checkout, they abandoned
                if dwell_in_queue > 40.0:
                    emitted_events.append({
                        "event_type": "BILLING_QUEUE_ABANDON",
                        "visitor_id": track_id,
                        "timestamp": timestamp,
                        "zone_id": "Cash_Counter",
                        "dwell_ms": int(dwell_in_queue * 1000)
                    })
                abandoned_tracks.append(track_id)

        for t in abandoned_tracks:
            self.active_queue_tracks.pop(t, None)

        return queue_depth, emitted_events
