from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from src.database import get_db
from src.schemas.events import IngestRequest, IngestResponse
from src.services.metrics import process_incoming_events
from src.services.anomalies import run_anomaly_check_rules
import uuid

router = APIRouter(prefix="/events", tags=["Ingestion"])

@router.post("/ingest", response_model=IngestResponse, status_code=status.HTTP_201_CREATED)
async def ingest_telemetry_events(payload: IngestRequest, db: Session = Depends(get_db)):
    """
    Ingests batched CCTV telemetry events, runs the sessionizer to reconstruct active customer stay states,
    evaluates real-time anomaly rules, and returns processing logs. 
    Guarantees full idempotency.
    """
    trace_id = uuid.uuid4()
    if not payload.events:
        return IngestResponse(success=True, ingested_count=0, trace_id=trace_id)
        
    try:
        success, count = process_incoming_events(db, payload.events)
        if not success:
            raise HTTPException(status_code=500, detail="Persistence engine failed to commit telemetry batch")
            
        # Run background anomaly rules checks against active store event state
        store_id = payload.events[0].store_id
        await run_anomaly_check_rules(db, store_id)
        
        return IngestResponse(
            success=True,
            ingested_count=count,
            trace_id=trace_id
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Telemetry ingestion pipeline error: {str(e)}"
        )
