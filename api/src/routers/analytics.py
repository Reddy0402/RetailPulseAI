from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from src.database import get_db
from src.schemas.analytics import StoreMetrics, FunnelResponse, HeatmapResponse
from src.services.metrics import get_store_metrics_data, get_funnel_data, get_heatmap_data
from src.utils.logger import logger

router = APIRouter(prefix="/stores", tags=["Analytics"])

@router.get("/{id}/metrics", response_model=StoreMetrics)
def get_store_metrics(id: str, db: Session = Depends(get_db)):
    """
    Retrieves high-fidelity offline store conversion analytics, active check-out queue depths,
    and average brand zone dwells.
    """
    try:
        metrics = get_store_metrics_data(db, id)
        return metrics
    except Exception as e:
        logger.error(f"Failed to query store metrics: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Database aggregation error on store metrics query: {str(e)}"
        )

@router.get("/{id}/funnel", response_model=FunnelResponse)
def get_store_funnel(id: str, db: Session = Depends(get_db)):
    """
    Retrieves dynamic, session-based customer conversion funnels (ENTRY -> ZONE_VISIT -> BILLING_QUEUE -> PURCHASE).
    Deduplicates re-entry tracks.
    """
    try:
        funnel = get_funnel_data(db, id)
        return funnel
    except Exception as e:
        logger.error(f"Failed to query store funnel: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Database aggregation error on store funnel query: {str(e)}"
        )

@router.get("/{id}/heatmap", response_model=HeatmapResponse)
def get_store_heatmap(id: str, db: Session = Depends(get_db)):
    """
    Retrieves relative spatial zone heatmaps containing normalized visits and tracking trajectory confidence scores.
    """
    try:
        heatmap = get_heatmap_data(db, id)
        return heatmap
    except Exception as e:
        logger.error(f"Failed to query store heatmap: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Database aggregation error on store heatmap query: {str(e)}"
        )
