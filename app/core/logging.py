import logging
import sys
import json
from datetime import datetime, timezone
from typing import Any, Dict
from contextvars import ContextVar

# Context variable to hold request_id across async execution
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="system")


class JSONFormatter(logging.Formatter):
    """Structured JSON formatter for production-ready container logging."""
    
    def format(self, record: logging.LogRecord) -> str:
        log_obj: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_ctx.get(),
            "module": record.module,
            "line": record.lineno,
        }
        
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)
            
        return json.dumps(log_obj, ensure_ascii=False)


def setup_logging(debug: bool = False) -> None:
    """Configure root logger with JSON formatting."""
    log_level = logging.DEBUG if debug else logging.INFO
    
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # Remove existing handlers to avoid duplicates
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
        
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(JSONFormatter())
    
    root_logger.addHandler(console_handler)
    
    # Quiet down some noisy loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get a named logger."""
    return logging.getLogger(f"mishil.{name}")
