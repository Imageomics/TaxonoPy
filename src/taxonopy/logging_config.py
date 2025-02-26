"""TaxonoPy logging configuration utilities.

This module provides functions for configuring and managing logging
throughout the TaxonoPy package.
"""

import logging
import sys
from typing import Optional


def setup_logging(log_level: str = "INFO", 
                 log_file: Optional[str] = None) -> None:
    """Set up logging configuration for TaxonoPy.
    
    Args:
        log_level: The logging level to use (e.g., "DEBUG", "INFO")
        log_file: Optional file path to write logs to (in addition to console)
    
    Raises:
        ValueError: If the log level is invalid
    """
    # Convert string log level to numeric value
    numeric_level = getattr(logging, log_level.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError(f"Invalid log level: {log_level}")
    
    # Create formatter for consistent log formatting
    formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
    
    # Root logger configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)
    
    # Clear any existing handlers to avoid duplicate logs
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Console handler (always added)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # File handler (optional)
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    
    # Initial log message to indicate successful setup
    logging.debug(f"Logging initialized at {log_level} level")
