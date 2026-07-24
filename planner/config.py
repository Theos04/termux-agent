"""Configuration for the planner system"""
import os
from dataclasses import dataclass
from typing import Optional

@dataclass
class Config:
    # Core settings
    planner_name: str = "Chrome Automation Planner"
    debug: bool = False
    max_workers: int = 4
    default_timeout: int = 300
    
    # Storage
    storage_dir: str = "planner/storage"
    plans_db: str = "planner/storage/plans.db"
    memory_db: str = "planner/storage/memory.db"
    logs_db: str = "planner/storage/logs.db"
    
    # Chrome
    chrome_port: int = 9226
    default_url: str = "https://unstop.com/"
    
    # LLM (for future)
    llm_model: Optional[str] = None
    llm_api_key: Optional[str] = None
    
    # Scheduler
    scheduler_interval: int = 5  # seconds
    
    @classmethod
    def from_env(cls):
        return cls(
            debug=os.getenv("DEBUG", "false").lower() == "true",
            max_workers=int(os.getenv("MAX_WORKERS", "4")),
            chrome_port=int(os.getenv("CHROME_PORT", "9226")),
            llm_model=os.getenv("LLM_MODEL"),
            llm_api_key=os.getenv("OPENAI_API_KEY")
        )
