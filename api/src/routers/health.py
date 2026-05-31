from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from src.database import get_db
from src.schemas.analytics import HealthResponse
from src.utils.logger import logger
from datetime import datetime

router = APIRouter(tags=["System Control"])

@router.get("/health", response_model=HealthResponse)
def get_system_health(db: Session = Depends(get_db)):
    """
    Validates complete service health and monitors database connection pooling viability.
    """
    db_ok = False
    try:
        # Quick ping to Postgres
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        
    return HealthResponse(
        status="healthy" if db_ok else "unhealthy",
        database_connected=db_ok,
        timestamp=datetime.utcnow()
    )
