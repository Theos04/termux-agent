from dataclasses import dataclass, asdict, field
from typing import Dict, List, Optional, Any
from datetime import datetime
import json

@dataclass
class ScraperConfig:
    """Configuration for a scraper instance"""
    name: str
    url: str
    schedule: str  # cron expression or 'daily', 'hourly', 'weekly'
    selectors: Dict[str, str]  # field_name: selector
    extract_after_navigation: bool = True
    take_screenshot: bool = True
    save_html: bool = True
    session_name: Optional[str] = None
    active: bool = True
    last_run: Optional[str] = None
    next_run: Optional[str] = None
    run_count: int = 0
    success_count: int = 0
    error_count: int = 0
    partition: str = "default"  # Partition support
    headers: Optional[Dict[str, str]] = None  # Custom HTTP headers
    timeout: int = 60  # Timeout in seconds
    retry_count: int = 3
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'ScraperConfig':
        """Create from dictionary"""
        return cls(**data)
    
    def to_json(self) -> str:
        """Convert to JSON string"""
        return json.dumps(self.to_dict(), default=str)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'ScraperConfig':
        """Create from JSON string"""
        return cls.from_dict(json.loads(json_str))


@dataclass
class ScrapeResult:
    """Result of a scrape operation"""
    scraper_name: str
    timestamp: str
    success: bool
    data: Dict[str, Any]
    screenshot_path: Optional[str] = None
    html_path: Optional[str] = None
    error: Optional[str] = None
    duration: float = 0.0
    partition: str = "default"
    url: Optional[str] = None
    task_id: Optional[str] = None
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'ScrapeResult':
        """Create from dictionary"""
        return cls(**data)
    
    def to_json(self) -> str:
        """Convert to JSON string"""
        return json.dumps(self.to_dict(), default=str)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'ScrapeResult':
        """Create from JSON string"""
        return cls.from_dict(json.loads(json_str))
    
    def get_summary(self) -> str:
        """Get a summary of the result"""
        status = "✅ SUCCESS" if self.success else "❌ FAILED"
        return f"{status} - {self.scraper_name} ({self.duration:.2f}s) - {len(self.data)} fields extracted"


@dataclass
class ScraperStats:
    """Statistics for a scraper"""
    name: str
    partition: str
    total_runs: int = 0
    total_success: int = 0
    total_errors: int = 0
    last_run: Optional[str] = None
    avg_duration: float = 0.0
    total_data_points: int = 0
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate"""
        if self.total_runs == 0:
            return 0.0
        return (self.total_success / self.total_runs) * 100
    
    def to_dict(self) -> Dict:
        return asdict(self)
