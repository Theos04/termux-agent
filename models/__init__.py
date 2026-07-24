# models/__init__.py
from .job_model_listing import JobListing, JobPage, JobScrapeResult
from .job_model_details import JobDetail, JobDetailScrapeResult

__all__ = [
    'JobListing',
    'JobPage', 
    'JobScrapeResult',
    'JobDetail',
    'JobDetailScrapeResult'
]
