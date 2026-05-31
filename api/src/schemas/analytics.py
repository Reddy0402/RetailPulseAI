from pydantic import BaseModel, Field
from typing import Dict, List, Optional
from datetime import datetime
from uuid import UUID

class StoreMetrics(BaseModel):
    store_id: str
    timestamp: datetime
    unique_visitors: int
    conversion_rate: float = Field(..., ge=0.0, le=1.0)
    avg_dwell_per_zone: Dict[str, float]
    queue_depth: int
    abandonment_rate: float = Field(..., ge=0.0, le=1.0)
    billing_visitors: int
    purchase_visitors: int
    visitor_sessions: int

class FunnelStage(BaseModel):
    stage_name: str
    count: int
    dropoff_count: int
    dropoff_percentage: float
    conversion_percentage: float

class FunnelResponse(BaseModel):
    store_id: str
    stages: List[FunnelStage]

class HeatmapItem(BaseModel):
    zone_id: str
    zone_visits: int
    avg_dwell_ms: float
    normalized_score: float = Field(..., ge=0.0, le=100.0)
    confidence_score: float = Field(..., ge=0.0, le=1.0)

class HeatmapResponse(BaseModel):
    store_id: str
    heatmap: List[HeatmapItem]

class AnomalyItem(BaseModel):
    anomaly_id: UUID
    store_id: str
    timestamp: datetime
    anomaly_type: str
    title: str
    description: str
    severity: str  # 'INFO', 'WARN', 'CRITICAL'
    suggested_action: str
    resolved: bool

class AnomalyResponse(BaseModel):
    store_id: str
    anomalies: List[AnomalyItem]

class HealthResponse(BaseModel):
    status: str
    database_connected: bool
    timestamp: datetime
