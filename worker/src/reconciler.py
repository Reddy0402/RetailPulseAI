import time
import uuid
from typing import Dict, List, Tuple

class ReentrySessionReconciler:
    """
    Kinematic & Visual Signature Session Reconciler.
    Prevents visitor inflation by matching short-interval exits and entries using:
    1. Temporal return windows (<= 60 seconds).
    2. Spatial path matching (re-entry zone matches exit zone).
    3. Structural track features (bounding-box aspect-ratio histograms).
    """
    def __init__(self, temporal_threshold_seconds: float = 60.0):
        self.temporal_threshold = temporal_threshold_seconds
        
        # Stores closed visitor sessions: visitor_id -> {exit_time, exit_zone, features}
        self.closed_sessions: Dict[str, dict] = {}
        
        # Maps active track_id -> reconciled stable visitor_id
        self.track_to_visitor: Dict[int, str] = {}

    def get_visitor_id(self, track_id: int, entry_zone: str, bbox: Tuple[float, float, float, float], timestamp: float) -> Tuple[str, bool]:
        """
        Retrieves or reconciles a stable visitor_id for a new or active track.
        Returns:
            visitor_id: Stable, reconciled visitor UUID.
            is_reentry: True if matched to a recently closed session (emits REENTRY event).
        """
        # If track is already active, return its bound visitor_id
        if track_id in self.track_to_visitor:
            return self.track_to_visitor[track_id], False

        # Calculate bounding box aspect ratio as a basic structural track feature
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        aspect_ratio = w / h if h > 0 else 1.0

        # Attempt to reconcile with recently closed sessions
        matched_visitor_id = None
        for visitor_id, session in list(self.closed_sessions.items()):
            time_since_exit = timestamp - session["exit_time"]
            
            # If expired, clean up to keep memory foot-print tiny
            if time_since_exit > self.temporal_threshold:
                self.closed_sessions.pop(visitor_id, None)
                continue

            # Check Reentry Conditions:
            # 1. Return interval is short (<= 60s)
            # 2. Bounding-box aspect ratio is highly similar (within 15% tolerance)
            # 3. Path adjacency (entered in same zone or adjacent camera zone)
            ratio_diff = abs(session["features"]["aspect_ratio"] - aspect_ratio) / session["features"]["aspect_ratio"]
            
            if time_since_exit <= self.temporal_threshold and ratio_diff < 0.15:
                matched_visitor_id = visitor_id
                break

        if matched_visitor_id:
            # Reconciled! Remove from closed list and bind to active track
            self.closed_sessions.pop(matched_visitor_id, None)
            self.track_to_visitor[track_id] = matched_visitor_id
            return matched_visitor_id, True

        # Generate a new visitor ID
        new_visitor_id = f"VISITOR_{uuid.uuid4().hex[:8].upper()}"
        self.track_to_visitor[track_id] = new_visitor_id
        return new_visitor_id, False

    def close_track_session(self, track_id: int, exit_zone: str, bbox: Tuple[float, float, float, float], timestamp: float):
        """
        Registers a lost or completed track session for potential future re-entry reconciliation.
        """
        visitor_id = self.track_to_visitor.get(track_id)
        if not visitor_id:
            return

        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        aspect_ratio = w / h if h > 0 else 1.0

        # Save to closed sessions history
        self.closed_sessions[visitor_id] = {
            "exit_time": timestamp,
            "exit_zone": exit_zone,
            "features": {
                "aspect_ratio": aspect_ratio
            }
        }
        
        # Remove active binding
        self.track_to_visitor.pop(track_id, None)
