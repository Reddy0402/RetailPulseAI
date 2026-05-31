from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from src.config import settings
from src.utils.logger import logger

# Configure production-grade SQLAlchemy Connection Pool
engine = create_engine(
    settings.get_db_url(),
    pool_size=20,          # Keeps 20 active connections open for rapid event streaming
    max_overflow=10,       # Allows overflow up to 30 under heavy checkout queue spikes
    pool_pre_ping=True,    # Verifies database connection liveness before every query
    pool_recycle=3600      # Recycles database connections hourly to prevent leaks
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    """
    Dependency injection generator providing scoped SQLAlchemy session persistence.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
