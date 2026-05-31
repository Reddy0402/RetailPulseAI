import uuid
from sqlalchemy import Column, String, Integer, BigInteger, Float, Boolean, DateTime, Date, Time, JSON, text
from src.database import Base
from src.config import settings

# Elite SQLite Test-Suite & Production Postgres Dual-Compatibility Type Mapping
# Allows SQLite in-memory compilation during Pytest without sacrificing Postgres performance in prod
if settings.get_db_url().startswith("sqlite"):
    from sqlalchemy import JSON as JSONB
    ARRAY_TYPE = JSON
    ARRAY_DEFAULT = None
    JSONB_DEFAULT = None
else:
    from sqlalchemy.dialects.postgresql import JSONB, ARRAY as PG_ARRAY
    ARRAY_TYPE = PG_ARRAY
    ARRAY_DEFAULT = text("ARRAY[]::VARCHAR[]")
    JSONB_DEFAULT = text("'{}'::jsonb")

class IngestionLog(Base):
    __tablename__ = "ingestion_logs"

    log_id = Column(UUID if False else String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    store_id = Column(String(50), nullable=False)
    camera_id = Column(String(50), nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    frame_count = Column(Integer, nullable=False)
    processing_time_ms = Column(Float, nullable=False)
    fps = Column(Float, nullable=False)
    status = Column(String(20), nullable=False)
    error_message = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"))

class Event(Base):
    __tablename__ = "events"

    event_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    store_id = Column(String(50), nullable=False)
    camera_id = Column(String(50), nullable=False)
    visitor_id = Column(String(100), nullable=False)
    event_type = Column(String(50), nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    zone_id = Column(String(50), nullable=True)
    dwell_ms = Column(BigInteger, nullable=True)
    is_staff = Column(Boolean, default=False)
    confidence = Column(Float, nullable=False)
    meta_data = Column(JSONB, nullable=False, server_default=JSONB_DEFAULT)
    created_at = Column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"))

class VisitorSession(Base):
    __tablename__ = "visitor_sessions"

    session_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    store_id = Column(String(50), nullable=False)
    visitor_id = Column(String(100), nullable=False)
    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True), nullable=True)
    is_staff = Column(Boolean, default=False)
    has_purchased = Column(Boolean, default=False)
    reentry_count = Column(Integer, default=0)
    total_dwell_ms = Column(BigInteger, default=0)
    zones_visited = Column(ARRAY_TYPE(String(50)), server_default=ARRAY_DEFAULT)
    meta_data = Column(JSONB, nullable=False, server_default=JSONB_DEFAULT)
    created_at = Column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"))
    updated_at = Column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"))

class ZoneMetric(Base):
    __tablename__ = "zone_metrics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    store_id = Column(String(50), nullable=False)
    zone_id = Column(String(50), nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    visitor_count = Column(Integer, default=0)
    avg_dwell_ms = Column(BigInteger, default=0)
    meta_data = Column(JSONB, nullable=False, server_default=JSONB_DEFAULT)
    created_at = Column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"))

class Anomaly(Base):
    __tablename__ = "anomalies"

    anomaly_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    store_id = Column(String(50), nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    anomaly_type = Column(String(50), nullable=False)
    title = Column(String(100), nullable=False)
    description = Column(String, nullable=False)
    severity = Column(String(20), nullable=False)
    suggested_action = Column(String, nullable=False)
    resolved = Column(Boolean, default=False)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    meta_data = Column(JSONB, nullable=False, server_default=JSONB_DEFAULT)
    created_at = Column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"))

class POSTransaction(Base):
    __tablename__ = "pos_transactions"

    transaction_id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(String(50), nullable=False)
    invoice_number = Column(String(50), nullable=False)
    order_date = Column(Date, nullable=False)
    order_time = Column(Time, nullable=False)
    store_id = Column(String(50), nullable=False)
    customer_name = Column(String(100), nullable=True)
    customer_number = Column(String(50), nullable=True)
    brand_name = Column(String(100), nullable=True)
    product_name = Column(String, nullable=True)
    qty = Column(Integer, nullable=False)
    total_amount = Column(Float, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"))
