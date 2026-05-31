import time
from typing import Dict, Set

class StaffHeuristicClassifier:
    """
    Heuristic-based Retail Staff Isolation Engine.
    Evaluates kinematic signatures, checkout lane stays, and zone traversal frequencies.
    """
    def __init__(self):
        # Maps track_id -> track state dictionary
        self.track_histories: Dict[int, dict] = {}

    def evaluate(self, track_id: int, current_zone: str, frame_idx: int, timestamp: float) -> bool:
        if track_id not in self.track_histories:
            self.track_histories[track_id] = {
                "start_time": timestamp,
                "last_time": timestamp,
                "zones_visited": {current_zone} if current_zone else set(),
                "total_frames": 1,
                "cash_counter_frames": 1 if current_zone == "Cash_Counter" else 0,
                "zone_transits": 0,
                "last_zone": current_zone
            }
            return False

        hist = self.track_histories[track_id]
        hist["total_frames"] += 1
        hist["last_time"] = timestamp

        if current_zone:
            hist["zones_visited"].add(current_zone)
            if current_zone == "Cash_Counter":
                hist["cash_counter_frames"] += 1

            if current_zone != hist["last_zone"]:
                hist["zone_transits"] += 1
                hist["last_zone"] = current_zone

        # ----------------------------------------------------
        # Staff Scoring Heuristics (Targeting Store Clips of ~140s)
        # ----------------------------------------------------
        total_duration = hist["last_time"] - hist["start_time"]
        
        # Rule 1: Cashier Stationary Counter Heuristic
        # The cashier silhouette is stationary at the Cash Counter. 
        # If a track dwells in the Cash Counter area for >75% of their total frames
        # and has been tracked for >40 seconds, they are highly likely the cashier.
        cash_ratio = hist["cash_counter_frames"] / hist["total_frames"]
        is_cashier = (cash_ratio > 0.75) and (total_duration > 40.0)

        # Rule 2: Visual Floor sweep Heuristic
        # Sales representatives traverse multiple zones repeatedly to stock items.
        # If a track is active for >90 seconds and has made >4 distinct zone transits,
        # they are classified as Floor Staff.
        is_floor_staff = (total_duration > 90.0) and (hist["zone_transits"] >= 4)

        is_staff = is_cashier or is_floor_staff
        
        return is_staff
