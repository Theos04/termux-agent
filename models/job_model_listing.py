# models/job_model_listing.py
from pydantic import BaseModel, Field, validator
from typing import Optional, List, Union
from datetime import datetime

class JobListing(BaseModel):
    """Job listing model - for search results / list view"""
    title: str = Field(..., description="Job title")
    company: Optional[str] = Field(None, description="Company name")
    location: Optional[str] = Field(None, description="Job location")
    url: Optional[str] = Field(None, description="Job detail URL")
    posted_date: Optional[str] = Field(None, description="When job was posted")
    description: Optional[str] = Field(None, description="Job description preview")
    job_type: Optional[str] = Field(None, description="Full-time, Internship, etc.")
    eligibility: Optional[Union[str, List[str]]] = Field(None, description="Eligibility criteria")
    skills: List[str] = Field(default_factory=list, description="Required skills")
    source_id: Optional[str] = Field(None, description="Source ID from Unstop")
    scraped_at: datetime = Field(default_factory=datetime.now)
    
    @validator('url', pre=True)
    def validate_url(cls, v):
        if v and not v.startswith('http'):
            return f"https://unstop.com{v}"
        return v
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
        extra = 'allow'
        schema_extra = {
            "example": {
                "title": "Software Engineer",
                "company": "Google",
                "location": "Bangalore",
                "url": "https://unstop.com/job/123",
                "posted_date": "2 days ago",
                "job_type": "Full-time",
                "skills": ["Python", "JavaScript"]
            }
        }

class JobPage(BaseModel):
    """Job page results - for pagination"""
    page_number: int = Field(..., description="Current page")
    total_pages: int = Field(..., description="Total pages")
    jobs: List[JobListing] = Field(..., description="Jobs on this page")
    has_next: bool = Field(..., description="Has next page")
    scraped_at: datetime = Field(default_factory=datetime.now)
    
    class Config:
        extra = 'allow'

class JobScrapeResult(BaseModel):
    """Complete scrape result"""
    session: str = Field(default="unstop")
    target_url: str = Field(..., description="Base URL scraped")
    total_jobs: int = Field(..., description="Total jobs found")
    pages_scraped: int = Field(..., description="Number of pages scraped")
    jobs: List[JobListing] = Field(..., description="All jobs found")
    errors: List[str] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=datetime.now)
    completed_at: datetime = Field(default_factory=datetime.now)
    duration_seconds: float = Field(0.0)
    
    @property
    def summary(self) -> str:
        return f"Scraped {self.total_jobs} jobs from {self.pages_scraped} pages"
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
        extra = 'allow'
