"""AlphaWorkbench demo package."""

import logging
import os

__all__ = ["__version__"]
__version__ = "0.1.0"

# Load .env from project root on first import
try:
    from dotenv import load_dotenv

    _env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    if os.path.exists(_env_path):
        load_dotenv(_env_path)
except ImportError:
    pass

# Configure logging: set ALPHA_LOG_LEVEL=DEBUG for verbose output
_log_level = os.environ.get("ALPHA_LOG_LEVEL", "WARNING").upper()
logging.basicConfig(
    level=getattr(logging, _log_level, logging.WARNING),
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
