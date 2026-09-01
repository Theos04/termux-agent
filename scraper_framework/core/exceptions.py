"""Custom exceptions for the scraper framework"""

class ScraperError(Exception):
    """Base exception for scraper errors"""
    pass

class ScraperNotFoundError(ScraperError):
    """Raised when a scraper is not found"""
    def __init__(self, name: str, partition: str = "default"):
        self.name = name
        self.partition = partition
        super().__init__(f"Scraper '{name}' not found in partition '{partition}'")

class ScraperExecutionError(ScraperError):
    """Raised when a scraper fails to execute"""
    pass

class ScraperValidationError(ScraperError):
    """Raised when scraper configuration is invalid"""
    pass

class ScraperTimeoutError(ScraperError):
    """Raised when a scraper times out"""
    pass

class PartitionNotFoundError(ScraperError):
    """Raised when a partition is not found"""
    def __init__(self, partition: str):
        self.partition = partition
        super().__init__(f"Partition '{partition}' not found")
