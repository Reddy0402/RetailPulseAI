from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select, and_
from src.database import get_db
from src.schemas.analytics import AnomalyResponse, AnomalyItem
from src.models.schema import Anomaly
from src.utils.logger import logger

router = APIRouter(prefix="/stores", tags=["Anomalies"])

@router.get("/{id}/anomalies", response_model=AnomalyResponse)
def get_store_anomalies(id: str, db: Session = Depends(get_db)):
    """
    Retrieves active, unresolved store operation anomalies (e.g. queue spikes, conversion dips).
    """
    try:
        anomalies = db.scalars(
            select(Anomaly)
            .where(and_(Anomaly.store_id == id, Anomaly.resolved == False))
            .order_by(Anomaly.timestamp.desc())
        ).all()

        anomaly_items = [
            AnomalyItem(
                anomaly_id=a.anomaly_id,
                store_id=a.store_id,
                timestamp=a.timestamp,
                anomaly_type=a.anomaly_type,
                title=a.title,
                description=a.description,
                severity=a.severity,
                suggested_action=a.suggested_action,
                resolved=a.resolved
            ) for a in anomalies
        ]
        
        return AnomalyResponse(store_id=id, anomalies=anomaly_items)
    except Exception as e:
        logger.error(f"Failed to query store anomalies: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Database query error on anomalies: {str(e)}"
        )
