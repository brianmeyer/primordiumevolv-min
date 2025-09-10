"""
Logging utility factory for the meta-evolution system.

Provides standardized logging configuration across all modules.
"""

import logging
import os


def get_logger(name):
    """
    Get a configured logger instance.
    
    Args:
        name: Logger name (typically __name__)
        
    Returns:
        logging.Logger: Configured logger instance
    """
    lvl = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=lvl,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    return logging.getLogger(name)