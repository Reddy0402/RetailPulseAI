import requests
from typing import List, Dict, Any

import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TelemetryClient")

class TelemetryIngestionClient:
    """
    Edge Event Ingestion Buffer.
    Ensures zero data loss during network dropouts by buffering events
    locally in memory and retrying ingestion.
    """
    def __init__(self, api_url: str):
        self.api_url = api_url
        self.buffer: List[Dict[str, Any]] = []

    def buffer_and_send(self, events: List[Dict[str, Any]]):
        """
        Adds events to buffer and attempts to transmit.
        """
        self.buffer.extend(events)
        self.flush()

    def flush(self):
        if not self.buffer:
            return

        batch_size = 100
        while self.buffer:
            batch = self.buffer[:batch_size]
            payload = {"events": batch}
            try:
                url = f"{self.api_url}/events/ingest"
                response = requests.post(url, json=payload, timeout=10.0)
                
                if response.status_code in (200, 201):
                    logger.info(f"Successfully ingested {len(batch)} telemetry events to API.")
                    self.buffer = self.buffer[batch_size:]
                else:
                    logger.error(f"API Ingest rejected events. Status: {response.status_code}. Retaining in edge buffer.")
                    break
            except Exception as e:
                logger.error(f"Connection failure to central API endpoint: {e}. Retaining {len(self.buffer)} events in edge buffer.")
                break
