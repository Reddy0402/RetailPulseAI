from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from uuid import UUID, uuid4

class EventMetadata(BaseModel):
    track_age: int = Field(..., description="Duration of track in frames")
    trajectory_confidence: float = Field(..., ge=0.0, le=1.0)
    occlusion_score: float = Field(..., ge=0.0, le=1.0)
    camera_transition: Optional[str] = None
    session_sequence: int = Field(..., description="Incremental event order within visitor session")

class TelemetryEvent(BaseModel):
    event_id: UUID = Field(default_factory=uuid4)
    store_id: str = Field(..., min_length=2)
    camera_id: str
    visitor_id: str
    event_type: str = Field(..., pattern="^(ZONE_ENTER|ZONE_EXIT|ZONE_DWELL|BILLING_QUEUE_JOIN|BILLING_QUEUE_ABANDON|REENTRY|PURCHASE)$")
    timestamp: datetime
    zone_id: Optional[str] = None
    dwell_ms: Optional[int] = None
    is_staff: bool = False
    confidence: float = Field(..., ge=0.0, le=1.0)
    meta_data: EventMetadata

class IngestRequest(BaseModel):
    events: List[TelemetryEvent]

class IngestResponse(BaseModel):
    success: bool
    ingested_count: int
    trace_id: UUID
