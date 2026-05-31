from sqlalchemy.orm import Session
from sqlalchemy import select, and_, func
from src.models.schema import Event, Anomaly, VisitorSession
from src.utils.logger import logger
from src.services.websocket import websocket_manager
import asyncio
from datetime import datetime, timedelta
from typing import List

async def run_anomaly_check_rules(db: Session, store_id: str):
    """
    Evaluates real-time anomaly detection rules against the event logs and visitor sessions.
    Automatically persists detected anomalies and broadcasts alerts to the live dashboard.
    """
    loop = asyncio.get_event_loop()
    
    # Use virtual simulation time if historical data is ingested
    latest_db_time = db.scalar(
        select(func.max(Event.timestamp))
        .where(Event.store_id == store_id)
    )
    now = latest_db_time.replace(tzinfo=None) if (latest_db_time and latest_db_time.tzinfo) else (latest_db_time or datetime.utcnow())

    # Rule 1: STALE_FEED
    cameras = ["CAM_1", "CAM_2", "CAM_3", "CAM_4", "CAM_5"]
    for cam in cameras:
        latest_event_time = db.scalar(
            select(func.max(Event.timestamp))
            .where(and_(Event.store_id == store_id, Event.camera_id == cam))
        )
        latest_naive = latest_event_time.replace(tzinfo=None) if latest_event_time and latest_event_time.tzinfo else latest_event_time
        if latest_naive and (now - latest_naive) > timedelta(seconds=60):
            active = db.scalar(
                select(Anomaly).where(
                    and_(
                        Anomaly.store_id == store_id,
                        Anomaly.anomaly_type == "STALE_FEED",
                        Anomaly.meta_data["camera_id"].as_string() == cam,
                        Anomaly.resolved == False
                    )
                )
            )
            if not active:
                new_anomaly = Anomaly(
                    store_id=store_id,
                    timestamp=now,
                    anomaly_type="STALE_FEED",
                    title="Camera Feed Ingest Offline",
                    description=f"Camera {cam} has stopped ingesting telemetry events. Last event received at {latest_event_time.isoformat()}.",
                    severity="CRITICAL",
                    suggested_action=f"Verify store edge node physical network cables and power cycle Camera {cam}.",
                    meta_data={"camera_id": cam, "last_active": latest_event_time.isoformat()}
                )
                db.add(new_anomaly)
                db.flush()
                loop.create_task(
                    websocket_manager.broadcast({
                        "type": "NEW_ANOMALY",
                        "anomaly_id": str(new_anomaly.anomaly_id),
                        "store_id": store_id,
                        "anomaly_type": "STALE_FEED",
                        "title": new_anomaly.title,
                        "severity": "CRITICAL",
                        "description": new_anomaly.description
                    })
                )

    # Rule 2: QUEUE_SPIKE
    cutoff = now - timedelta(seconds=30)
    queue_depth = db.scalar(
        select(func.count(func.distinct(Event.visitor_id)))
        .where(and_(
            Event.store_id == store_id,
            Event.zone_id == "Cash_Counter",
            Event.timestamp >= cutoff,
            Event.is_staff == False
        ))
    ) or 0

    if queue_depth > 5:
        active_spike = db.scalar(
            select(Anomaly).where(
                and_(
                    Anomaly.store_id == store_id,
                    Anomaly.anomaly_type == "QUEUE_SPIKE",
                    Anomaly.resolved == False
                )
            )
        )
        if not active_spike:
            severity = "CRITICAL" if queue_depth > 8 else "WARN"
            new_anomaly = Anomaly(
                store_id=store_id,
                timestamp=now,
                anomaly_type="QUEUE_SPIKE",
                title="Checkout Counter Queue Spike",
                description=f"A spatial cluster of {queue_depth} shoppers has formed at the cash register, exceeding baseline thresholds.",
                severity=severity,
                suggested_action="Deploy supplementary cashier and activate Cash Counter Register 2 immediately.",
                meta_data={"queue_depth": queue_depth}
            )
            db.add(new_anomaly)
            db.flush()
            loop.create_task(
                websocket_manager.broadcast({
                    "type": "NEW_ANOMALY",
                    "anomaly_id": str(new_anomaly.anomaly_id),
                    "store_id": store_id,
                    "anomaly_type": "QUEUE_SPIKE",
                    "title": new_anomaly.title,
                    "severity": severity,
                    "description": new_anomaly.description
                })
            )

    # Rule 3: CONVERSION_DROP
    hour_cutoff = now - timedelta(hours=1)
    unique_count = db.scalar(
        select(func.count(func.distinct(VisitorSession.visitor_id)))
        .where(and_(
            VisitorSession.store_id == store_id,
            VisitorSession.start_time >= hour_cutoff,
            VisitorSession.is_staff == False
        ))
    ) or 0

    if unique_count >= 10:
        purchasers = db.scalar(
            select(func.count(func.distinct(VisitorSession.visitor_id)))
            .where(and_(
                VisitorSession.store_id == store_id,
                VisitorSession.start_time >= hour_cutoff,
                VisitorSession.is_staff == False,
                VisitorSession.has_purchased == True
            ))
        ) or 0
        
        conversion_rate = purchasers / unique_count
        if conversion_rate < 0.10:  # Drop below 10%
            active_drop = db.scalar(
                select(Anomaly).where(
                    and_(
                        Anomaly.store_id == store_id,
                        Anomaly.anomaly_type == "CONVERSION_DROP",
                        Anomaly.resolved == False
                    )
                )
            )
            if not active_drop:
                new_anomaly = Anomaly(
                    store_id=store_id,
                    timestamp=now,
                    anomaly_type="CONVERSION_DROP",
                    title="Store Conversion Rate Dip",
                    description=f"Rolling hourly conversion rate has dropped to {conversion_rate*100:.1f}%. High browser-to-buyer dropout.",
                    severity="WARN",
                    suggested_action="Inspect product replenishment schedules, shelf availability, and run interactive promotional checkouts.",
                    meta_data={"conversion_rate": conversion_rate, "unique_visitors": unique_count}
                )
                db.add(new_anomaly)
                db.flush()
                loop.create_task(
                    websocket_manager.broadcast({
                        "type": "NEW_ANOMALY",
                        "anomaly_id": str(new_anomaly.anomaly_id),
                        "store_id": store_id,
                        "anomaly_type": "CONVERSION_DROP",
                        "title": new_anomaly.title,
                        "severity": "WARN",
                        "description": new_anomaly.description
                    })
                )

    # Rule 4: DEAD_ZONE
    zones = ["Top_Aisle_Bays", "Bottom_Aisle_Bays", "Fragrance_Nail", "Makeup_Unit"]
    zone_cutoff = now - timedelta(minutes=15)
    for zone in zones:
        visits = db.scalar(
            select(func.count(Event.event_id))
            .where(and_(
                Event.store_id == store_id,
                Event.zone_id == zone,
                Event.timestamp >= zone_cutoff,
                Event.is_staff == False
            ))
        ) or 0

        if visits == 0:
            active_dead = db.scalar(
                select(Anomaly).where(
                    and_(
                        Anomaly.store_id == store_id,
                        Anomaly.anomaly_type == "DEAD_ZONE",
                        Anomaly.meta_data["zone_id"].as_string() == zone,
                        Anomaly.resolved == False
                    )
                )
            )
            if not active_dead:
                new_anomaly = Anomaly(
                    store_id=store_id,
                    timestamp=now,
                    anomaly_type="DEAD_ZONE",
                    title="Cold Retail Zone Detected",
                    description=f"Zone '{zone}' has registered zero visitor traffic in the last 15 minutes.",
                    severity="INFO",
                    suggested_action=f"Improve visual merchandising layouts or run direct display discounts inside '{zone}'.",
                    meta_data={"zone_id": zone}
                )
                db.add(new_anomaly)
                db.flush()
                loop.create_task(
                    websocket_manager.broadcast({
                        "type": "NEW_ANOMALY",
                        "anomaly_id": str(new_anomaly.anomaly_id),
                        "store_id": store_id,
                        "anomaly_type": "DEAD_ZONE",
                        "title": new_anomaly.title,
                        "severity": "INFO",
                        "description": new_anomaly.description
                    })
                )

    db.commit()
