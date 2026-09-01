# scraper_framework/__init__.py
"""
Scraper Framework - Modular, Multi-Partition Web Scraping Framework
"""

from .core import ScraperConfig, ScrapeResult, ScraperRegistry, ScraperEngine
from .tasks import run_scheduled_scraper, run_partition_scrapers, run_all_partitions

__version__ = "1.0.0"
__all__ = [
    'ScraperConfig',
    'ScrapeResult',
    'ScraperRegistry',
    'ScraperEngine',
    'run_scheduled_scraper',
    'run_partition_scrapers',
    'run_all_partitions'
]
