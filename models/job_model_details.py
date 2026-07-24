# models/job_model_details.py
from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any, Union
from datetime import datetime
from job_model_listing import JobListing

class JobDetail(JobListing):
    """Extended job detail model - for individual job pages"""
    responsibilities: Optional[Union[str, List[str]]] = Field(None, description="Job responsibilities")
    requirements: Optional[Union[str, List[str]]] = Field(None, description="Job requirements")
    deadline: Optional[str] = Field(None, description="Application deadline")
    full_description: Optional[str] = Field(None, description="Full job description")
    sections: Optional[Dict[str, Any]] = Field(default_factory=dict, description="All sections of the job posting")
    detailed_skills: Optional[List[str]] = Field(default_factory=list, description="Detailed skills from the job posting")
    company_website: Optional[str] = Field(None, description="Company website URL")
    company_logo: Optional[str] = Field(None, description="Company logo URL")
    employment_type: Optional[str] = Field(None, description="Employment type details")
    work_mode: Optional[str] = Field(None, description="Work from home/office/hybrid")
    salary_range: Optional[str] = Field(None, description="Salary range if available")
    industry: Optional[Union[str, List[str]]] = Field(None, description="Industry sector")
    job_function: Optional[str] = Field(None, description="Job function/role category")
    detail_scraped_at: datetime = Field(default_factory=datetime.now)
    detail_url: Optional[str] = Field(None, description="URL where details were scraped from")
    
    @validator('detail_url', pre=True)
    def validate_detail_url(cls, v):
        if v and not v.startswith('http'):
            return f"https://unstop.com{v}"
        return v
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
        extra = 'allow'  # Allow extra fields from the API

class JobDetailScrapeResult(BaseModel):
    """Complete job detail scrape result"""
    session: str = Field(default="unstop")
    total_jobs: int = Field(..., description="Total jobs processed")
    successful: int = Field(..., description="Successfully scraped")
    failed: int = Field(..., description="Failed to scrape")
    job_details: List[JobDetail] = Field(default_factory=list, description="All job details")
    errors: List[Dict[str, str]] = Field(default_factory=list, description="Errors with URL and message")
    started_at: datetime = Field(default_factory=datetime.now)
    completed_at: datetime = Field(default_factory=datetime.now)
    duration_seconds: float = Field(0.0)
    
    @property
    def summary(self) -> str:
        return f"Scraped {self.successful} job details out of {self.total_jobs}"
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
        extra = 'allow'
