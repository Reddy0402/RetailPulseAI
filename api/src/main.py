from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from src.config import settings
from src.database import engine, Base, SessionLocal
from src.models.schema import POSTransaction
from src.routers import ingest, analytics, anomalies, health
from src.services.websocket import websocket_manager
from src.utils.logger import logger
import time
import os
import csv
import uuid
from datetime import datetime

# Automatically build relational database tables on API startup
# Ensures zero manual DB migration steps for the Acceptance Gate
try:
    Base.metadata.create_all(bind=engine)
    logger.info("Database relational schemas initialized successfully.")
except Exception as e:
    logger.critical(f"Critical failure initializing database relational schema: {e}")

app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Enable CORS for Next.js dashboard connection
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Wire up routers
app.include_router(ingest.router)
app.include_router(analytics.router)
app.include_router(anomalies.router)
app.include_router(health.router)

# Real-time WebSocket Endpoint for Browser Dashboard Syncing
@app.websocket("/ws/dashboard")
async def websocket_endpoint(websocket: WebSocket):
    await websocket_manager.connect(websocket)
    try:
        while True:
            # Maintain connection alive, ignore incoming client messages
            await websocket.receive_text()
    except WebSocketDisconnect:
        websocket_manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket execution error: {e}")
        websocket_manager.disconnect(websocket)

# Observability Request-Response Middleware
# Logs endpoints, trace_ids, store_ids, and latencies in JSON format
@app.middleware("http")
async def log_requests_middleware(request: Request, call_next):
    start_time = time.time()
    trace_id = request.headers.get("X-Trace-ID", str(uuid.uuid4()))
    
    # Try to extract store_id from path params or query params
    store_id = request.path_params.get("id") or request.query_params.get("store_id") or "GLOBAL"

    response = await call_next(request)
    
    duration = (time.time() - start_time) * 1000.0  # in ms

    # Standardized JSON Observability Log
    logger.info(
        f"API Request: {request.method} {request.url.path}",
        {
            "trace_id": trace_id,
            "store_id": store_id,
            "endpoint": request.url.path,
            "latency_ms": round(duration, 2),
            "status_code": response.status_code
        }
    )
    
    response.headers["X-Trace-ID"] = trace_id
    return response

# Seed POS Dataset on startup if empty
@app.on_event("startup")
def seed_pos_data():
    db = SessionLocal()
    try:
        # Check if already seeded
        count = db.query(POSTransaction).count()
        if count > 0:
            logger.info(f"POS Transactions already seeded. Row count: {count}")
            return

        # Locate CSV dataset in the mounted workspace
        csv_candidates = [
            "Brigade_Bangalore_10_April_26 (1)bc6219c.csv",
            "../Brigade_Bangalore_10_April_26 (1)bc6219c.csv",
            "/app/Brigade_Bangalore_10_April_26 (1)bc6219c.csv",
            "c:\\Users\\vippa\\Downloads\\PURPLE_project\\Brigade_Bangalore_10_April_26 (1)bc6219c.csv"
        ]
        
        csv_path = None
        for path in csv_candidates:
            if os.path.exists(path):
                csv_path = path
                break

        if not csv_path:
            logger.error("POS transaction CSV dataset was not found. Skipping seeding.")
            return

        logger.info(f"Seeding POS transactions dataset from: {csv_path}")
        with open(csv_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            transactions = []
            for row in reader:
                # Try standard DD-MM-YYYY format first, then DD-MM-YY
                try:
                    order_date = datetime.strptime(row["order_date"], "%d-%m-%Y").date()
                except ValueError:
                    order_date = datetime.strptime(row["order_date"], "%d-%m-%y").date()

                order_time = datetime.strptime(row["order_time"], "%H:%M:%S").time()

                tx = POSTransaction(
                    order_id=row["order_id"],
                    invoice_number=row["invoice_number"],
                    order_date=order_date,
                    order_time=order_time,
                    store_id=row["store_id"],
                    customer_name=row["customer_name"],
                    customer_number=row["customer_number"],
                    brand_name=row["brand_name"],
                    product_name=row["product_name"],
                    qty=int(row["qty"]),
                    total_amount=float(row["total_amount"])
                )
                transactions.append(tx)
                
            db.bulk_save_objects(transactions)
            db.commit()
            logger.info(f"Successfully seeded {len(transactions)} POS transactions.")

    except Exception as e:
        logger.error(f"Failed to seed POS dataset on startup: {e}")
        db.rollback()
    finally:
        db.close()
