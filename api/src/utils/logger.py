import logging
import json
import time
from typing import Any, Dict

class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_data: Dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "message": record.getMessage(),
            "module": record.module,
            "filename": record.filename,
            "line_number": record.lineno
        }
        
        # Include extra dictionary variables
        if isinstance(record.args, dict):
            for k, v in record.args.items():
                log_data[k] = v
                
        # Include custom properties bound to record
        if hasattr(record, "extra_fields"):
            log_data.update(getattr(record, "extra_fields"))
            
        return json.dumps(log_data)

def setup_logger(name: str = "store_intelligence") -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    
    # Avoid duplicate handlers
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = JSONFormatter(datefmt="%Y-%m-%dT%H:%M:%SZ")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        
    return logger

logger = setup_logger()
