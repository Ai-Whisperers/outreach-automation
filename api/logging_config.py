"""
Logging configuration for Campaign Generator API.

Provides structured logging with different configurations for
development and production environments.
"""

import logging
import sys
import uuid
from contextvars import ContextVar
from datetime import datetime
from pathlib import Path
from typing import Any

# Try to import json_log_formatter for production, fall back gracefully
try:
    import json
    HAS_JSON_LOGGING = True
except ImportError:
    HAS_JSON_LOGGING = False

# Context variable for request ID
request_id_var: ContextVar[str] = ContextVar("request_id", default="")


def get_request_id() -> str:
    """Get the current request ID from context."""
    return request_id_var.get()


def set_request_id(request_id: str) -> None:
    """Set the request ID in context."""
    request_id_var.set(request_id)


def generate_request_id() -> str:
    """Generate a new unique request ID."""
    return uuid.uuid4().hex[:12]


# =============================================================================
# Custom Formatters
# =============================================================================

class ConsoleFormatter(logging.Formatter):
    """
    Custom formatter for console output with colors and request ID.
    """

    COLORS = {
        "DEBUG": "\033[36m",     # Cyan
        "INFO": "\033[32m",      # Green
        "WARNING": "\033[33m",   # Yellow
        "ERROR": "\033[31m",     # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        # Add request ID to record
        request_id = get_request_id()
        record.request_id = request_id if request_id else "-"

        # Add color to level name
        levelname = record.levelname
        if levelname in self.COLORS:
            colored_level = f"{self.COLORS[levelname]}{levelname}{self.RESET}"
            record.levelname = colored_level

        # Format the message
        formatted = super().format(record)

        # Reset level name for other handlers
        record.levelname = levelname

        return formatted


class JSONFormatter(logging.Formatter):
    """
    JSON formatter for structured logging in production.
    """

    def format(self, record: logging.LogRecord) -> str:
        # Get request ID from context
        request_id = get_request_id()

        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add request ID if available
        if request_id:
            log_data["request_id"] = request_id

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add extra fields
        for key, value in record.__dict__.items():
            if key not in [
                "name", "msg", "args", "created", "filename", "funcName",
                "levelname", "levelno", "lineno", "module", "msecs",
                "pathname", "process", "processName", "relativeCreated",
                "stack_info", "thread", "threadName", "exc_info", "exc_text",
                "message", "request_id"
            ]:
                log_data[key] = value

        return json.dumps(log_data)


# =============================================================================
# Logger Configuration
# =============================================================================

def setup_logging(
    level: str = "INFO",
    environment: str = "development",
    log_file: str | None = None
) -> logging.Logger:
    """
    Configure logging for the application.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        environment: Environment name (development, production, test)
        log_file: Optional path to log file

    Returns:
        Configured root logger
    """
    # Get root logger
    logger = logging.getLogger("campaign_generator")
    logger.setLevel(getattr(logging, level.upper()))

    # Remove existing handlers
    logger.handlers = []

    # Choose formatter based on environment
    if environment == "production":
        formatter = JSONFormatter()
    else:
        formatter = ConsoleFormatter(
            fmt="%(asctime)s | %(levelname)-8s | %(request_id)s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler (if specified)
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.FileHandler(log_path)
        file_handler.setFormatter(JSONFormatter())  # Always JSON for files
        logger.addHandler(file_handler)

    # Prevent propagation to root logger
    logger.propagate = False

    return logger


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance with the given name.

    Args:
        name: Logger name (usually __name__ of the module)

    Returns:
        Logger instance
    """
    return logging.getLogger(f"campaign_generator.{name}")


# =============================================================================
# Context Logging
# =============================================================================

class LogContext:
    """
    Context manager for adding contextual information to logs.

    Usage:
        with LogContext(project_id="123", phase="research"):
            logger.info("Processing started")
    """

    def __init__(self, **kwargs: Any):
        self.context = kwargs
        self.logger = get_logger("context")
        self.old_factory = None

    def __enter__(self):
        self.old_factory = logging.getLogRecordFactory()
        context = self.context

        def factory(*args, **kwargs):
            record = self.old_factory(*args, **kwargs)
            for key, value in context.items():
                setattr(record, key, value)
            return record

        logging.setLogRecordFactory(factory)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        logging.setLogRecordFactory(self.old_factory)


# =============================================================================
# Logging Decorators
# =============================================================================

def log_function_call(logger: logging.Logger | None = None):
    """
    Decorator to log function entry and exit.

    Usage:
        @log_function_call()
        def my_function(arg1, arg2):
            ...
    """
    def decorator(func):
        nonlocal logger
        if logger is None:
            logger = get_logger(func.__module__)

        def wrapper(*args, **kwargs):
            func_name = func.__name__
            logger.debug(f"Entering {func_name}")
            try:
                result = func(*args, **kwargs)
                logger.debug(f"Exiting {func_name}")
                return result
            except Exception as e:
                logger.error(f"Exception in {func_name}: {e}")
                raise

        return wrapper
    return decorator


def log_async_function_call(logger: logging.Logger | None = None):
    """
    Decorator to log async function entry and exit.

    Usage:
        @log_async_function_call()
        async def my_async_function(arg1, arg2):
            ...
    """
    def decorator(func):
        nonlocal logger
        if logger is None:
            logger = get_logger(func.__module__)

        async def wrapper(*args, **kwargs):
            func_name = func.__name__
            logger.debug(f"Entering {func_name}")
            try:
                result = await func(*args, **kwargs)
                logger.debug(f"Exiting {func_name}")
                return result
            except Exception as e:
                logger.error(f"Exception in {func_name}: {e}")
                raise

        return wrapper
    return decorator


# =============================================================================
# Pre-configured Loggers for Common Modules
# =============================================================================

# These can be imported directly in modules
api_logger = get_logger("api")
research_logger = get_logger("research")
ideas_logger = get_logger("ideas")
export_logger = get_logger("export")
ai_logger = get_logger("ai")


# =============================================================================
# Initialize Default Logging
# =============================================================================

def init_default_logging():
    """Initialize logging with default settings based on environment."""
    import os

    environment = os.getenv("ENVIRONMENT", "development")
    level = os.getenv("LOG_LEVEL", "INFO" if environment == "production" else "DEBUG")
    log_file = os.getenv("LOG_FILE")

    setup_logging(
        level=level,
        environment=environment,
        log_file=log_file
    )
