import os
import time
from pipeline import StoreIntelligencePipeline

import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("StoreWorkerMain")

if __name__ == "__main__":
    logger.info("Starting Retail Store Intelligence Edge Worker Node...")

    # Load configurations from environment variables
    # Matches Docker Compose container networking names
    api_url = os.getenv("API_URL", "http://api:8000")
    store_id = os.getenv("STORE_ID", "ST1008")
    
    # Path configuration
    layout_path = os.getenv("LAYOUT_PATH", "layouts/store_001.json")
    video_dir = os.getenv("VIDEO_DIR", "CCTV Footage-20260529T160731Z-3-00144614ea/CCTV Footage")

    # Initialize and spin up multi-camera concurrent threads
    try:
        pipeline = StoreIntelligencePipeline(
            store_id=store_id,
            layout_path=layout_path,
            video_dir=video_dir,
            api_url=api_url
        )
        threads = pipeline.start_pipeline()
        logger.info(f"Edge Node initialized successfully. Running {len(threads)} camera processing loops.")
        
        # Keep main thread alive
        while True:
            time.sleep(1.0)
            
    except KeyboardInterrupt:
        logger.info("Edge Node shutting down gracefully on user interrupt.")
    except Exception as e:
        logger.critical(f"Fatal crash inside Edge Node: {e}")
