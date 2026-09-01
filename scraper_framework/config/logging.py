# config/logging.py
"""Logging configuration for the scraper framework"""

import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler
from datetime import datetime


def setup_logging(level=logging.INFO, log_dir="logs", partition="default"):
    """
    Setup logging configuration
    
    Args:
        level: Logging level
        log_dir: Directory for log files
        partition: Partition name for partition-specific logs
    """
    # Create logs directory
    log_path = Path(log_dir)
    log_path.mkdir(exist_ok=True)
    
    # Create partition-specific log file
    log_file = log_path / f"scraper_{partition}_{datetime.now().strftime('%Y%m%d')}.log"
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    
    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Console handler with color support
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_format = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(console_format)
    root_logger.addHandler(console_handler)
    
    # File handler with rotation
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5
    )
    file_handler.setLevel(level)
    file_format = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_format)
    root_logger.addHandler(file_handler)
    
    # Reduce noise from some libraries
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('requests').setLevel(logging.WARNING)
    logging.getLogger('celery').setLevel(logging.INFO)
    
    # Create partition-specific logger
    logger = logging.getLogger(f"scraper.{partition}")
    logger.info(f"✅ Logging configured for partition '{partition}'")
    logger.info(f"   Log file: {log_file}")
    
    return logger


def get_logger(name, partition="default"):
    """Get a logger with partition context"""
    logger = logging.getLogger(f"{name}.{partition}")
    return logger
