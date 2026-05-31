from sqlalchemy.orm import Session
from sqlalchemy import func, select, and_, text
from src.models.schema import Event, VisitorSession, POSTransaction, ZoneMetric
from src.schemas.events import TelemetryEvent
from src.schemas.analytics import StoreMetrics, FunnelStage, FunnelResponse, HeatmapItem, HeatmapResponse
from src.utils.logger import logger
from src.services.websocket import websocket_manager
from src.config import settings
import asyncio
import uuid
from datetime import datetime, timedelta
from typing import List, Tuple, Dict, Any

def process_incoming_events(db: Session, telemetry_events: List[TelemetryEvent]) -> Tuple[bool, int]:
    """
    Processes a batch of CCTV telemetry events.
    1. Implements strict idempotency using event_id checks to prevent duplicate ingestion.
    2. Inserts events into the database.
    3. Reconstructs visitor stays (sessionizer) in real-time.
    4. Triggers POS transaction matching to link visual tracks to transaction sales.
    """
    ingested_count = 0
    loop = asyncio.get_event_loop()
    is_sqlite = settings.get_db_url().startswith("sqlite")

    for event in telemetry_events:
        try:
            # 1. Idempotency Check
            event_id_val = str(event.event_id) if is_sqlite else event.event_id
            exists = db.scalar(select(Event).where(Event.event_id == event_id_val))
            if exists:
                logger.info(f"Duplicate event ignored for idempotency: {event.event_id}")
                continue

            # 2. Persist Raw Event
            db_event = Event(
                event_id=event_id_val,
                store_id=event.store_id,
                camera_id=event.camera_id,
                visitor_id=event.visitor_id,
                event_type=event.event_type,
                timestamp=event.timestamp,
                zone_id=event.zone_id,
                dwell_ms=event.dwell_ms,
                is_staff=event.is_staff,
                confidence=event.confidence,
                meta_data={
                    "track_age": event.meta_data.track_age,
                    "trajectory_confidence": event.meta_data.trajectory_confidence,
                    "occlusion_score": event.meta_data.occlusion_score,
                    "camera_transition": event.meta_data.camera_transition,
                    "session_sequence": event.meta_data.session_sequence
                }
            )
            db.add(db_event)
            db.flush()
            
            # 3. Reconstruct Visitor Session State (Sessionizer)
            session = db.scalar(
                select(VisitorSession).where(
                    and_(
                        VisitorSession.store_id == event.store_id,
                        VisitorSession.visitor_id == event.visitor_id
                    )
                )
            )

            if not session:
                # Construct new session state
                session = VisitorSession(
                    session_id=str(uuid.uuid4()) if is_sqlite else uuid.uuid4(),
                    store_id=event.store_id,
                    visitor_id=event.visitor_id,
                    start_time=event.timestamp,
                    end_time=event.timestamp,
                    is_staff=event.is_staff,
                    has_purchased=(event.event_type == "PURCHASE"),
                    reentry_count=1 if event.event_type == "REENTRY" else 0,
                    total_dwell_ms=event.dwell_ms or 0,
                    zones_visited=[event.zone_id] if event.zone_id else [],
                    meta_data={
                        "latest_camera": event.camera_id,
                        "latest_confidence": event.confidence,
                        "track_age": event.meta_data.track_age
                    }
                )
                db.add(session)
            else:
                # Update existing active session state
                session.end_time = max(session.end_time, event.timestamp)
                if event.event_type == "PURCHASE":
                    session.has_purchased = True
                elif event.event_type == "REENTRY":
                    session.reentry_count += 1
                
                if event.dwell_ms:
                    session.total_dwell_ms += event.dwell_ms

                if event.zone_id and event.zone_id not in session.zones_visited:
                    session.zones_visited = session.zones_visited + [event.zone_id]

                # Update metadata
                session.meta_data = {
                    **session.meta_data,
                    "latest_camera": event.camera_id,
                    "latest_confidence": event.confidence,
                    "track_age": max(session.meta_data.get("track_age", 0), event.meta_data.track_age)
                }
                session.updated_at = datetime.utcnow()

            # 4. POS Transaction Matching (Dynamic Purchase Correlator)
            if event.event_type in ("ZONE_EXIT", "ZONE_DWELL") and event.zone_id == "Cash_Counter" and not session.has_purchased:
                # Look for a POS transaction in the store matching checkout time +/- 90 seconds
                start_window = (event.timestamp - timedelta(seconds=90)).time()
                end_window = (event.timestamp + timedelta(seconds=90)).time()
                
                pos_match = db.execute(
                    text(
                        """
                        SELECT transaction_id FROM pos_transactions 
                        WHERE store_id = :store_id 
                        AND order_date = :order_date 
                        AND order_time BETWEEN :start_time AND :end_time
                        LIMIT 1
                        """
                    ),
                    {
                        "store_id": event.store_id,
                        "order_date": event.timestamp.date(),
                        "start_time": start_window,
                        "end_time": end_window
                    }
                ).fetchone()

                if pos_match:
                    session.has_purchased = True
                    session.meta_data = {**session.meta_data, "pos_matched_transaction_id": pos_match[0]}
                    logger.info(f"Successful dynamic POS correlation: Visited {event.visitor_id} matched POS Transaction ID {pos_match[0]}")

            db.flush()
            ingested_count += 1
            
            # Broadcast the live event to WebSockets
            event_payload = {
                "type": "NEW_EVENT",
                "event_id": str(event.event_id),
                "store_id": event.store_id,
                "camera_id": event.camera_id,
                "visitor_id": event.visitor_id,
                "event_type": event.event_type,
                "timestamp": event.timestamp.isoformat(),
                "zone_id": event.zone_id,
                "is_staff": event.is_staff,
                "confidence": event.confidence
            }
            loop.create_task(websocket_manager.broadcast(event_payload))

        except Exception as e:
            logger.error(f"Failed to process telemetry event: {e}")
            db.rollback()
            return False, ingested_count

    db.commit()
    return True, ingested_count

def get_store_metrics_data(db: Session, store_id: str) -> StoreMetrics:
    """
    Computes real-time store metrics derived from the raw event stream and visitor sessions.
    """
    unique_visitors = db.scalar(
        select(func.count(func.distinct(VisitorSession.visitor_id)))
        .where(and_(VisitorSession.store_id == store_id, VisitorSession.is_staff == False))
    ) or 0

    purchase_visitors = db.scalar(
        select(func.count(func.distinct(VisitorSession.visitor_id)))
        .where(and_(
            VisitorSession.store_id == store_id,
            VisitorSession.is_staff == False,
            VisitorSession.has_purchased == True
        ))
    ) or 0

    conversion_rate = purchase_visitors / unique_visitors if unique_visitors > 0 else 0.0

    billing_visitors = db.scalar(
        select(func.count(func.distinct(Event.visitor_id)))
        .where(and_(
            Event.store_id == store_id,
            Event.zone_id == "Cash_Counter",
            Event.is_staff == False
        ))
    ) or 0

    queue_joins = db.scalar(
        select(func.count(Event.event_id))
        .where(and_(
            Event.store_id == store_id,
            Event.event_type == "BILLING_QUEUE_JOIN",
            Event.is_staff == False
        ))
    ) or 0

    queue_abandons = db.scalar(
        select(func.count(Event.event_id))
        .where(and_(
            Event.store_id == store_id,
            Event.event_type == "BILLING_QUEUE_ABANDON",
            Event.is_staff == False
        ))
    ) or 0

    abandonment_rate = queue_abandons / queue_joins if queue_joins > 0 else 0.0

    avg_dwell_results = db.execute(
        select(Event.zone_id, func.avg(Event.dwell_ms))
        .where(and_(
            Event.store_id == store_id,
            Event.event_type == "ZONE_DWELL",
            Event.is_staff == False,
            Event.zone_id.isnot(None)
        ))
        .group_by(Event.zone_id)
    ).fetchall()

    avg_dwell_per_zone = {r[0]: float(r[1]) / 1000.0 for r in avg_dwell_results}

    cutoff = datetime.utcnow() - timedelta(seconds=60)
    queue_depth = db.scalar(
        select(func.count(func.distinct(Event.visitor_id)))
        .where(and_(
            Event.store_id == store_id,
            Event.zone_id == "Cash_Counter",
            Event.timestamp >= cutoff,
            Event.is_staff == False
        ))
    ) or 0

    sessions_count = db.scalar(
        select(func.count(VisitorSession.session_id))
        .where(VisitorSession.store_id == store_id)
    ) or 0

    return StoreMetrics(
        store_id=store_id,
        timestamp=datetime.utcnow(),
        unique_visitors=unique_visitors,
        conversion_rate=conversion_rate,
        avg_dwell_per_zone=avg_dwell_per_zone,
        queue_depth=queue_depth,
        abandonment_rate=abandonment_rate,
        billing_visitors=billing_visitors,
        purchase_visitors=purchase_visitors,
        visitor_sessions=sessions_count
    )

def get_funnel_data(db: Session, store_id: str) -> FunnelResponse:
    """
    Computes session-based funnel conversion rates.
    """
    entry_count = db.scalar(
        select(func.count(func.distinct(VisitorSession.visitor_id)))
        .where(and_(VisitorSession.store_id == store_id, VisitorSession.is_staff == False))
    ) or 0

    # Under SQLite, custom array cardinality is converted to check if zones_visited JSON is non-empty
    is_sqlite = settings.get_db_url().startswith("sqlite")
    if is_sqlite:
        # SQLite JSON-based list length mock check
        visit_count = db.scalar(
            select(func.count(func.distinct(VisitorSession.visitor_id)))
            .where(and_(
                VisitorSession.store_id == store_id,
                VisitorSession.is_staff == False,
                VisitorSession.zones_visited.isnot(None)
            ))
        ) or 0
        
        queue_count = db.scalar(
            select(func.count(func.distinct(VisitorSession.visitor_id)))
            .where(and_(
                VisitorSession.store_id == store_id,
                VisitorSession.is_staff == False,
                VisitorSession.zones_visited.contains("Cash_Counter")
            ))
        ) or 0
    else:
        visit_count = db.scalar(
            select(func.count(func.distinct(VisitorSession.visitor_id)))
            .where(and_(
                VisitorSession.store_id == store_id,
                VisitorSession.is_staff == False,
                func.cardinality(VisitorSession.zones_visited) > 0
            ))
        ) or 0

        queue_count = db.scalar(
            select(func.count(func.distinct(VisitorSession.visitor_id)))
            .where(and_(
                VisitorSession.store_id == store_id,
                VisitorSession.is_staff == False,
                VisitorSession.zones_visited.any("Cash_Counter")
            ))
        ) or 0

    purchase_count = db.scalar(
        select(func.count(func.distinct(VisitorSession.visitor_id)))
        .where(and_(
            VisitorSession.store_id == store_id,
            VisitorSession.is_staff == False,
            VisitorSession.has_purchased == True
        ))
    ) or 0

    counts = [entry_count, visit_count, queue_count, purchase_count]
    stages = ["ENTRY", "ZONE_VISIT", "BILLING_QUEUE", "PURCHASE"]
    funnel_stages = []

    for i in range(len(stages)):
        current_count = counts[i]
        dropoff_count = 0
        dropoff_pct = 0.0
        conv_pct = 0.0

        if i > 0:
            prev_count = counts[i-1]
            dropoff_count = prev_count - current_count
            dropoff_pct = (dropoff_count / prev_count) if prev_count > 0 else 0.0
            
        conv_pct = (current_count / entry_count) if entry_count > 0 else 0.0

        funnel_stages.append(
            FunnelStage(
                stage_name=stages[i],
                count=current_count,
                dropoff_count=dropoff_count,
                dropoff_percentage=dropoff_pct,
                conversion_percentage=conv_pct
            )
        )

    return FunnelResponse(store_id=store_id, stages=funnel_stages)

def get_heatmap_data(db: Session, store_id: str) -> HeatmapResponse:
    """
    Computes spatial heatmaps with normalized visits and tracking confidence scores.
    """
    results = db.execute(
        select(
            Event.zone_id,
            func.count(func.distinct(Event.visitor_id)),
            func.avg(Event.dwell_ms),
            func.avg(Event.confidence)
        )
        .where(and_(
            Event.store_id == store_id,
            Event.is_staff == False,
            Event.zone_id.isnot(None)
        ))
        .group_by(Event.zone_id)
    ).fetchall()

    heatmap_items = []
    if not results:
        return HeatmapResponse(store_id=store_id, heatmap=[])

    max_visits = max(r[1] for r in results) if results else 1

    for row in results:
        zone_id, visits, avg_dwell, confidence = row
        normalized_score = (visits / max_visits) * 100.0
        
        heatmap_items.append(
            HeatmapItem(
                zone_id=zone_id,
                zone_visits=visits,
                avg_dwell_ms=float(avg_dwell or 0),
                normalized_score=normalized_score,
                confidence_score=float(confidence or 0)
            )
        )

    return HeatmapResponse(store_id=store_id, heatmap=heatmap_items)
