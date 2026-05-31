import pytest
from worker.src.staff_detector import StaffHeuristicClassifier
from worker.src.queue_detector import QueueDetector
from worker.src.reconciler import ReentrySessionReconciler

def test_staff_heuristic_classifier():
    classifier = StaffHeuristicClassifier()
    
    # 1. Simulate Cashier - stationary at checkout for 50 frames
    track_id_cashier = 1
    for frame in range(1, 60):
        is_staff = classifier.evaluate(
            track_id=track_id_cashier,
            current_zone="Cash_Counter",
            frame_idx=frame,
            timestamp=float(frame)
        )
    # Cash cashier spends 100% of time at Cash_Counter and duration is >40 seconds (59s)
    assert is_staff is True

    # 2. Simulate standard Shopper - enters and moves around quickly
    track_id_shopper = 2
    for frame in range(1, 10):
        is_staff = classifier.evaluate(
            track_id=track_id_shopper,
            current_zone="Top_Aisle_Bays",
            frame_idx=frame,
            timestamp=float(frame)
        )
    assert is_staff is False

def test_queue_depth_dbscan_clustering():
    detector = QueueDetector(eps_pixels=150.0, min_samples=2)
    
    # 1. Frame 1: Shoppers walking far apart (No cluster)
    tracks_no_cluster = [
        ("VISITOR_A", (100.0, 200.0)),
        ("VISITOR_B", (800.0, 500.0))
    ]
    depth, events = detector.process_queue_frame(tracks_no_cluster, 0.0)
    assert depth == 0
    assert len(events) == 0

    # 2. Frame 2: Shoppers standing close together in queue (Cluster formed!)
    tracks_in_queue = [
        ("VISITOR_A", (500.0, 600.0)),
        ("VISITOR_B", (520.0, 610.0))  # Distance is ~22 pixels (<150 eps)
    ]
    depth, events = detector.process_queue_frame(tracks_in_queue, 1.0)
    assert depth == 2
    # Both join queue
    assert len(events) == 2
    assert events[0]["event_type"] == "BILLING_QUEUE_JOIN"

def test_reentry_session_reconciliation():
    reconciler = ReentrySessionReconciler(temporal_threshold_seconds=60.0)
    
    track_id_1 = 101
    bbox_exit = (200.0, 100.0, 300.0, 300.0)  # aspect ratio: 100 / 200 = 0.5
    
    # Shopper exits
    visitor_id1, is_re = reconciler.get_visitor_id(track_id_1, "Cash_Counter", bbox_exit, 10.0)
    assert is_re is False
    
    reconciler.close_track_session(track_id_1, "Cash_Counter", bbox_exit, 15.0)

    # Case A: Quick reentry (after 20 seconds) with identical aspect ratio -> Reconciled!
    track_id_2 = 102
    bbox_reentry = (210.0, 105.0, 310.0, 305.0) # aspect ratio: 100 / 200 = 0.5
    visitor_id2, is_reentry = reconciler.get_visitor_id(track_id_2, "Entrance_Zone", bbox_reentry, 35.0)
    
    assert is_reentry is True
    assert visitor_id2 == visitor_id1

    # Case B: Reentry after expiration window (>60 seconds) -> New Visitor!
    reconciler.close_track_session(track_id_2, "Cash_Counter", bbox_reentry, 40.0)
    track_id_3 = 103
    visitor_id3, is_reentry3 = reconciler.get_visitor_id(track_id_3, "Entrance_Zone", bbox_reentry, 110.0) # 70 seconds later
    
    assert is_reentry3 is False
    assert visitor_id3 != visitor_id1
