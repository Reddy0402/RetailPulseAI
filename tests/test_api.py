import pytest
import uuid
from datetime import datetime, timedelta

def test_get_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["database_connected"] is True

def test_events_ingestion_and_idempotency(client):
    event_id = str(uuid.uuid4())
    payload = {
        "events": [
            {
                "event_id": event_id,
                "store_id": "ST1008",
                "camera_id": "CAM_1",
                "visitor_id": "VISITOR_TEST_001",
                "event_type": "ZONE_ENTER",
                "timestamp": datetime.utcnow().isoformat(),
                "zone_id": "Entrance_Zone",
                "dwell_ms": 0,
                "is_staff": False,
                "confidence": 0.95,
                "meta_data": {
                    "track_age": 1,
                    "trajectory_confidence": 0.95,
                    "occlusion_score": 0.0,
                    "camera_transition": None,
                    "session_sequence": 1
                }
            }
        ]
    }

    # 1. First Ingestion
    response1 = client.post("/events/ingest", json=payload)
    assert response1.status_code == 201
    data1 = response1.json()
    assert data1["success"] is True
    assert data1["ingested_count"] == 1

    # 2. Duplicate Ingestion (Idempotency!)
    response2 = client.post("/events/ingest", json=payload)
    assert response2.status_code == 201
    data2 = response2.json()
    assert data2["success"] is True
    assert data2["ingested_count"] == 0

def test_get_store_metrics_and_funnel(client):
    v_id = "VISITOR_TEST_99"
    time_now = datetime.utcnow()
    
    events = [
        {"event_id": str(uuid.uuid4()), "store_id": "ST1008", "camera_id": "CAM_1", "visitor_id": v_id, "event_type": "ZONE_ENTER", "timestamp": time_now.isoformat(), "zone_id": "Entrance_Zone", "dwell_ms": 0, "is_staff": False, "confidence": 0.98, "meta_data": {"track_age": 1, "trajectory_confidence": 0.98, "occlusion_score": 0.0, "session_sequence": 1}},
        {"event_id": str(uuid.uuid4()), "store_id": "ST1008", "camera_id": "CAM_2", "visitor_id": v_id, "event_type": "ZONE_DWELL", "timestamp": (time_now + timedelta(seconds=10)).isoformat(), "zone_id": "Top_Aisle_Bays", "dwell_ms": 15000, "is_staff": False, "confidence": 0.98, "meta_data": {"track_age": 2, "trajectory_confidence": 0.98, "occlusion_score": 0.0, "session_sequence": 2}},
        {"event_id": str(uuid.uuid4()), "store_id": "ST1008", "camera_id": "CAM_5", "visitor_id": v_id, "event_type": "BILLING_QUEUE_JOIN", "timestamp": (time_now + timedelta(seconds=30)).isoformat(), "zone_id": "Cash_Counter", "dwell_ms": 0, "is_staff": False, "confidence": 0.98, "meta_data": {"track_age": 3, "trajectory_confidence": 0.98, "occlusion_score": 0.0, "session_sequence": 3}},
        {"event_id": str(uuid.uuid4()), "store_id": "ST1008", "camera_id": "CAM_5", "visitor_id": v_id, "event_type": "PURCHASE", "timestamp": (time_now + timedelta(seconds=40)).isoformat(), "zone_id": "Cash_Counter", "dwell_ms": 10000, "is_staff": False, "confidence": 0.98, "meta_data": {"track_age": 4, "trajectory_confidence": 0.98, "occlusion_score": 0.0, "session_sequence": 4}}
    ]

    for ev in events:
        response = client.post("/events/ingest", json={"events": [ev]})
        assert response.status_code == 201

    res_metrics = client.get("/stores/ST1008/metrics")
    assert res_metrics.status_code == 200
    metrics = res_metrics.json()
    assert metrics["unique_visitors"] == 1
    assert metrics["purchase_visitors"] == 1
    assert metrics["conversion_rate"] == 1.0
    
    res_funnel = client.get("/stores/ST1008/funnel")
    assert res_funnel.status_code == 200
    funnel = res_funnel.json()
    assert funnel["stages"][0]["count"] == 1
    assert funnel["stages"][1]["count"] == 1
    assert funnel["stages"][3]["count"] == 1

    res_heatmap = client.get("/stores/ST1008/heatmap")
    assert res_heatmap.status_code == 200
    heatmap = res_heatmap.json()
    assert len(heatmap["heatmap"]) > 0
