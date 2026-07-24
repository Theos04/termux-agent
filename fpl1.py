#!/usr/bin/env python3
"""
Chrome Session Manager - Production v19
Advanced Scheduler & Automation Engine
Features: Job applications, Hackathon submissions, Chatbot automation, Data scraping
"""

import os
import time
import subprocess
import shutil
import signal
import sys
import json
import re
import logging
import logging.handlers
import threading
import queue
import socket
import hashlib
import tempfile
from typing import Optional, Dict, List, Any, Tuple, Set, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
import atexit
import sqlite3
import random
import yaml
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import psutil
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "psutil"])
    import psutil

try:
    import websocket
    import websocket._core
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "websocket-client"])
    import websocket

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.prompt import Prompt, Confirm
    from rich import box
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
    from rich.layout import Layout
    from rich.live import Live
    from rich.text import Text
    from rich.columns import Columns
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "rich"])
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.prompt import Prompt, Confirm
    from rich import box
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
    from rich.layout import Layout
    from rich.live import Live
    from rich.text import Text
    from rich.columns import Columns

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger
    from apscheduler.triggers.date import DateTrigger
    from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR, EVENT_JOB_MISSED
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "apscheduler"])
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger
    from apscheduler.triggers.date import DateTrigger
    from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR, EVENT_JOB_MISSED

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.common.action_chains import ActionChains
    from selenium.common.exceptions import TimeoutException, NoSuchElementException
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "selenium"])
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.common.action_chains import ActionChains
    from selenium.common.exceptions import TimeoutException, NoSuchElementException

try:
    import pandas as pd
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pandas"])
    import pandas as pd

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "playwright"])
    subprocess.check_call([sys.executable, "-m", "playwright", "install"])
    from playwright.sync_api import sync_playwright

from session_db import SessionDB

console = Console()

# ============================================================================
# Enhanced Configuration
# ============================================================================

@dataclass
class SchedulerConfig:
    enabled: bool = True
    timezone: str = "UTC"
    max_workers: int = 4
    job_timeout: int = 3600
    retry_count: int = 3
    retry_delay: int = 60

@dataclass
class JobConfig:
    id: str = ""
    name: str = ""
    enabled: bool = True
    trigger_type: str = "interval"  # interval, cron, date
    trigger_config: Dict = field(default_factory=dict)
    session_port: int = 0
    action_type: str = "browser"  # browser, api, js, python, shell
    action_config: Dict = field(default_factory=dict)
    timeout: int = 300
    retry_count: int = 3
    retry_delay: int = 30
    concurrent: bool = False
    priority: int = 5
    tags: List[str] = field(default_factory=list)
    created_at: str = ""
    last_run: Optional[str] = None
    next_run: Optional[str] = None
    run_count: int = 0
    success_count: int = 0
    error_count: int = 0

@dataclass
class JobTemplate:
    id: str
    name: str
    description: str
    category: str  # job_application, hackathon, chatbot, scraping, custom
    config: Dict
    tags: List[str] = field(default_factory=list)

class JobStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"
    CANCELLED = "cancelled"
    SCHEDULED = "scheduled"

# ============================================================================
# Job Templates Database
# ============================================================================

JOB_TEMPLATES = [
    JobTemplate(
        id="job_apply_linkedin",
        name="LinkedIn Job Application",
        description="Apply to jobs on LinkedIn with auto-fill",
        category="job_application",
        tags=["linkedin", "jobs", "automation"],
        config={
            "url": "https://www.linkedin.com/jobs/",
            "actions": [
                {"type": "navigate", "url": "https://www.linkedin.com/jobs/"},
                {"type": "wait", "seconds": 3},
                {"type": "login", "credentials": "{{linkedin_credentials}}"},
                {"type": "search_jobs", "keywords": "{{job_keywords}}", "location": "{{job_location}}"},
                {"type": "apply_filters", "filters": {"date_posted": "past_week", "experience_level": "entry"}},
                {"type": "click", "selector": "button.apply-button"},
                {"type": "fill_form", "fields": {
                    "full_name": "{{full_name}}",
                    "email": "{{email}}",
                    "phone": "{{phone}}",
                    "resume": "{{resume_path}}"
                }},
                {"type": "submit_application"},
                {"type": "screenshot", "save_to": "job_applications/{{timestamp}}" }
            ]
        }
    ),
    JobTemplate(
        id="job_apply_indeed",
        name="Indeed Job Application",
        description="Apply to jobs on Indeed",
        category="job_application",
        tags=["indeed", "jobs", "automation"],
        config={
            "url": "https://www.indeed.com/",
            "actions": [
                {"type": "navigate", "url": "https://www.indeed.com/"},
                {"type": "search_jobs", "keywords": "{{job_keywords}}", "location": "{{job_location}}"},
                {"type": "click", "selector": "a.jobtitle"},
                {"type": "apply", "method": "easy_apply"},
                {"type": "fill_form", "fields": {
                    "full_name": "{{full_name}}",
                    "email": "{{email}}",
                    "phone": "{{phone}}",
                    "resume": "{{resume_path}}"
                }},
                {"type": "submit_application"},
                {"type": "screenshot", "save_to": "job_applications/{{timestamp}}" }
            ]
        }
    ),
    JobTemplate(
        id="hackathon_submit_devpost",
        name="Devpost Hackathon Submission",
        description="Submit project to Devpost hackathon",
        category="hackathon",
        tags=["devpost", "hackathon", "submission"],
        config={
            "url": "https://devpost.com/",
            "actions": [
                {"type": "navigate", "url": "https://devpost.com/"},
                {"type": "login", "credentials": "{{devpost_credentials}}"},
                {"type": "click", "selector": "a.submit-button"},
                {"type": "fill_form", "fields": {
                    "project_name": "{{project_name}}",
                    "description": "{{project_description}}",
                    "tags": "{{project_tags}}",
                    "video_url": "{{demo_video}}",
                    "github_url": "{{github_url}}",
                    "live_url": "{{live_url}}"
                }},
                {"type": "submit_application"},
                {"type": "screenshot", "save_to": "hackathons/{{timestamp}}" }
            ]
        }
    ),
    JobTemplate(
        id="chatbot_send_message",
        name="Chatbot Message Sender",
        description="Send messages to chatbot with predefined prompts",
        category="chatbot",
        tags=["chatbot", "message", "automation"],
        config={
            "url": "{{chatbot_url}}",
            "actions": [
                {"type": "navigate", "url": "{{chatbot_url}}"},
                {"type": "wait", "seconds": 2},
                {"type": "send_message", "message": "{{chat_message}}"},
                {"type": "wait", "seconds": 5},
                {"type": "get_response", "save_to": "chat_responses/{{timestamp}}"},
                {"type": "screenshot", "save_to": "chat_screenshots/{{timestamp}}" }
            ]
        }
    ),
    JobTemplate(
        id="scrape_website",
        name="Website Scraper",
        description="Extract data from websites",
        category="scraping",
        tags=["scraping", "data", "extraction"],
        config={
            "actions": [
                {"type": "navigate", "url": "{{target_url}}"},
                {"type": "wait", "seconds": 3},
                {"type": "scrape", "selector": "{{content_selector}}", "save_to": "scraped_data/{{timestamp}}.json"},
                {"type": "export_csv", "save_to": "scraped_data/{{timestamp}}.csv"}
            ]
        }
    )
]

# ============================================================================
# Advanced Job Scheduler
# ============================================================================

class JobScheduler:
    def __init__(self, config: SchedulerConfig, db_path: str = "jobs.db"):
        self.config = config
        self.db_path = db_path
        self.scheduler = BackgroundScheduler(timezone=config.timezone)
        self.jobs: Dict[str, JobConfig] = {}
        self.running_jobs: Dict[str, Dict] = {}
        self.job_status: Dict[str, JobStatus] = {}
        self.job_results: Dict[str, Any] = {}
        self._lock = threading.RLock()
        self.executor = ThreadPoolExecutor(max_workers=config.max_workers)
        self._running = True
        
        self._init_db()
        self._load_jobs()
        self._setup_event_listeners()
        
        if config.enabled:
            self.scheduler.start()
            logger.info("✅ Job scheduler started")

    def _init_db(self):
        """Initialize SQLite database for job tracking"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                name TEXT,
                enabled INTEGER,
                trigger_type TEXT,
                trigger_config TEXT,
                session_port INTEGER,
                action_type TEXT,
                action_config TEXT,
                timeout INTEGER,
                retry_count INTEGER,
                retry_delay INTEGER,
                concurrent INTEGER,
                priority INTEGER,
                tags TEXT,
                created_at TEXT,
                last_run TEXT,
                next_run TEXT,
                run_count INTEGER DEFAULT 0,
                success_count INTEGER DEFAULT 0,
                error_count INTEGER DEFAULT 0
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS job_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT,
                status TEXT,
                start_time TEXT,
                end_time TEXT,
                duration REAL,
                result TEXT,
                error TEXT,
                data TEXT,
                FOREIGN KEY (job_id) REFERENCES jobs(id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS credentials (
                id TEXT PRIMARY KEY,
                name TEXT,
                data TEXT,
                encrypted INTEGER DEFAULT 0,
                created_at TEXT,
                updated_at TEXT
            )
        ''')
        
        conn.commit()
        conn.close()
        logger.info("✅ Job database initialized")

    def _load_jobs(self):
        """Load jobs from database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM jobs')
        rows = cursor.fetchall()
        
        for row in rows:
            job = JobConfig(
                id=row[0],
                name=row[1],
                enabled=bool(row[2]),
                trigger_type=row[3],
                trigger_config=json.loads(row[4]),
                session_port=row[5],
                action_type=row[6],
                action_config=json.loads(row[7]),
                timeout=row[8],
                retry_count=row[9],
                retry_delay=row[10],
                concurrent=bool(row[11]),
                priority=row[12],
                tags=json.loads(row[13]) if row[13] else [],
                created_at=row[14],
                last_run=row[15],
                next_run=row[16],
                run_count=row[17] or 0,
                success_count=row[18] or 0,
                error_count=row[19] or 0
            )
            self.jobs[job.id] = job
            
            if job.enabled:
                self._schedule_job(job)
        
        conn.close()
        logger.info(f"✅ Loaded {len(self.jobs)} jobs")

    def _setup_event_listeners(self):
        """Setup scheduler event listeners"""
        def job_listener(event):
            if event.code == EVENT_JOB_EXECUTED:
                logger.info(f"Job {event.job_id} executed successfully")
            elif event.code == EVENT_JOB_ERROR:
                logger.error(f"Job {event.job_id} failed: {event.exception}")
            elif event.code == EVENT_JOB_MISSED:
                logger.warning(f"Job {event.job_id} was missed")
        
        self.scheduler.add_listener(job_listener)

    def _schedule_job(self, job: JobConfig):
        """Schedule a job based on its trigger type"""
        try:
            if job.trigger_type == "interval":
                trigger = IntervalTrigger(
                    seconds=job.trigger_config.get('seconds', 3600),
                    minutes=job.trigger_config.get('minutes', 0),
                    hours=job.trigger_config.get('hours', 0)
                )
            elif job.trigger_type == "cron":
                trigger = CronTrigger(
                    year=job.trigger_config.get('year'),
                    month=job.trigger_config.get('month'),
                    day=job.trigger_config.get('day'),
                    week=job.trigger_config.get('week'),
                    day_of_week=job.trigger_config.get('day_of_week'),
                    hour=job.trigger_config.get('hour'),
                    minute=job.trigger_config.get('minute'),
                    second=job.trigger_config.get('second', 0)
                )
            elif job.trigger_type == "date":
                trigger = DateTrigger(
                    run_date=datetime.fromisoformat(job.trigger_config.get('run_date'))
                )
            else:
                logger.error(f"Unknown trigger type: {job.trigger_type}")
                return

            self.scheduler.add_job(
                self._execute_job,
                trigger,
                id=job.id,
                args=[job.id],
                misfire_grace_time=60,
                coalesce=True,
                max_instances=3
            )
            
            logger.info(f"✅ Scheduled job: {job.name} (ID: {job.id})")
            
        except Exception as e:
            logger.error(f"Failed to schedule job {job.id}: {e}")

    def _execute_job(self, job_id: str):
        """Execute a job with retry logic"""
        if not self._running:
            return
        
        with self._lock:
            if job_id in self.running_jobs:
                logger.warning(f"Job {job_id} already running")
                return
            
            job = self.jobs.get(job_id)
            if not job:
                logger.error(f"Job {job_id} not found")
                return
            
            if not job.enabled:
                logger.info(f"Job {job_id} is disabled, skipping")
                return
            
            self.job_status[job_id] = JobStatus.RUNNING
            self.running_jobs[job_id] = {
                'start_time': datetime.now(),
                'attempt': 0
            }

        try:
            self._run_job_with_retry(job)
        finally:
            with self._lock:
                self.job_status[job_id] = JobStatus.COMPLETED
                if job_id in self.running_jobs:
                    del self.running_jobs[job_id]

    def _run_job_with_retry(self, job: JobConfig):
        """Run job with retry logic"""
        attempt = 0
        last_error = None
        
        while attempt < job.retry_count:
            try:
                self.job_status[job.id] = JobStatus.RUNNING if attempt == 0 else JobStatus.RETRYING
                
                result = self._run_job_action(job)
                
                if result['success']:
                    self._update_job_stats(job.id, success=True)
                    self.job_results[job.id] = result
                    return result
                else:
                    last_error = result.get('error', 'Unknown error')
                    logger.warning(f"Job {job.id} attempt {attempt + 1} failed: {last_error}")
                    
            except Exception as e:
                last_error = str(e)
                logger.error(f"Job {job.id} attempt {attempt + 1} failed: {e}")
            
            attempt += 1
            if attempt < job.retry_count:
                time.sleep(job.retry_delay)
        
        self._update_job_stats(job.id, success=False)
        self.job_status[job.id] = JobStatus.FAILED
        self.job_results[job.id] = {'success': False, 'error': last_error}
        
        return {'success': False, 'error': last_error}

    def _run_job_action(self, job: JobConfig) -> Dict:
        """Execute the actual job action"""
        if job.action_type == "browser":
            return self._run_browser_action(job)
        elif job.action_type == "api":
            return self._run_api_action(job)
        elif job.action_type == "js":
            return self._run_js_action(job)
        elif job.action_type == "python":
            return self._run_python_action(job)
        elif job.action_type == "shell":
            return self._run_shell_action(job)
        else:
            return {'success': False, 'error': f"Unknown action type: {job.action_type}"}

    def _run_browser_action(self, job: JobConfig) -> Dict:
        """Run browser automation action using Playwright or Selenium"""
        try:
            from playwright.sync_api import sync_playwright
            
            with sync_playwright() as p:
                browser = p.chromium.connect_over_cdp(
                    f"http://127.0.0.1:{job.session_port}"
                )
                
                context = browser.contexts[0] if browser.contexts else browser.new_context()
                page = context.pages[0] if context.pages else context.new_page()
                
                actions = job.action_config.get('actions', [])
                results = {}
                
                for action in actions:
                    result = self._execute_browser_action(page, action)
                    if result:
                        results.update(result)
                
                return {'success': True, 'results': results}
                
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def _execute_browser_action(self, page, action: Dict) -> Dict:
        """Execute a single browser action"""
        action_type = action.get('type')
        
        if action_type == 'navigate':
            page.goto(action.get('url'), timeout=action.get('timeout', 30000))
            
        elif action_type == 'click':
            page.click(action.get('selector'), timeout=action.get('timeout', 30000))
            
        elif action_type == 'fill':
            page.fill(action.get('selector'), action.get('value'), timeout=action.get('timeout', 30000))
            
        elif action_type == 'type':
            page.type(action.get('selector'), action.get('text'), delay=action.get('delay', 100))
            
        elif action_type == 'wait':
            page.wait_for_timeout(action.get('seconds', 1) * 1000)
            
        elif action_type == 'wait_for_selector':
            page.wait_for_selector(action.get('selector'), timeout=action.get('timeout', 30000))
            
        elif action_type == 'screenshot':
            path = action.get('save_to', f"screenshots/{datetime.now().isoformat()}.png")
            page.screenshot(path=path)
            return {'screenshot': path}
            
        elif action_type == 'evaluate':
            return {'result': page.evaluate(action.get('script'))}
            
        elif action_type == 'get_text':
            text = page.text_content(action.get('selector'))
            return {'text': text}
            
        elif action_type == 'get_attribute':
            value = page.get_attribute(action.get('selector'), action.get('attribute'))
            return {'value': value}
            
        elif action_type == 'submit':
            with page.expect_navigation():
                page.click(action.get('selector'))
        
        return {}

    def _run_api_action(self, job: JobConfig) -> Dict:
        """Run API action (curl/requests)"""
        try:
            import requests
            
            config = job.action_config
            method = config.get('method', 'GET')
            url = config.get('url')
            headers = config.get('headers', {})
            params = config.get('params', {})
            data = config.get('data', {})
            files = config.get('files', {})
            
            response = requests.request(
                method=method,
                url=url,
                headers=headers,
                params=params,
                json=data if config.get('json') else None,
                data=data if not config.get('json') else None,
                files=files,
                timeout=job.timeout
            )
            
            return {
                'success': response.status_code < 400,
                'status_code': response.status_code,
                'headers': dict(response.headers),
                'body': response.text[:10000]  # Limit response size
            }
            
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def _run_js_action(self, job: JobConfig) -> Dict:
        """Run JavaScript action via Node.js"""
        try:
            script = job.action_config.get('script')
            temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False)
            temp_file.write(script)
            temp_file.close()
            
            result = subprocess.run(
                ['node', temp_file.name],
                capture_output=True,
                text=True,
                timeout=job.timeout
            )
            
            os.unlink(temp_file.name)
            
            return {
                'success': result.returncode == 0,
                'stdout': result.stdout,
                'stderr': result.stderr
            }
            
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def _run_python_action(self, job: JobConfig) -> Dict:
        """Run Python action with context"""
        try:
            script = job.action_config.get('script')
            context = {
                'job': job,
                'session_port': job.session_port,
                'data': job.action_config.get('data', {})
            }
            
            # Execute script in separate process for isolation
            import importlib.util
            import tempfile
            
            temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False)
            temp_file.write(f"""
import sys
import json

context = {json.dumps(context)}
result = {script}
print(json.dumps({{'success': True, 'result': result}}))
""")
            temp_file.close()
            
            result = subprocess.run(
                [sys.executable, temp_file.name],
                capture_output=True,
                text=True,
                timeout=job.timeout
            )
            
            os.unlink(temp_file.name)
            
            try:
                output = json.loads(result.stdout)
                return output
            except:
                return {
                    'success': result.returncode == 0,
                    'stdout': result.stdout,
                    'stderr': result.stderr
                }
            
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def _run_shell_action(self, job: JobConfig) -> Dict:
        """Run shell command"""
        try:
            result = subprocess.run(
                job.action_config.get('command'),
                shell=True,
                capture_output=True,
                text=True,
                timeout=job.timeout,
                cwd=job.action_config.get('cwd', os.getcwd())
            )
            
            return {
                'success': result.returncode == 0,
                'stdout': result.stdout,
                'stderr': result.stderr
            }
            
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def _update_job_stats(self, job_id: str, success: bool):
        """Update job statistics in database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        if success:
            cursor.execute(
                'UPDATE jobs SET run_count = run_count + 1, success_count = success_count + 1, last_run = ? WHERE id = ?',
                (datetime.now().isoformat(), job_id)
            )
        else:
            cursor.execute(
                'UPDATE jobs SET run_count = run_count + 1, error_count = error_count + 1, last_run = ? WHERE id = ?',
                (datetime.now().isoformat(), job_id)
            )
        
        conn.commit()
        conn.close()

    def create_job(self, job: JobConfig) -> str:
        """Create a new job"""
        job.id = hashlib.md5(f"{job.name}_{time.time()}".encode()).hexdigest()[:16]
        job.created_at = datetime.now().isoformat()
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO jobs (
                id, name, enabled, trigger_type, trigger_config,
                session_port, action_type, action_config, timeout,
                retry_count, retry_delay, concurrent, priority,
                tags, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            job.id, job.name, int(job.enabled), job.trigger_type,
            json.dumps(job.trigger_config), job.session_port,
            job.action_type, json.dumps(job.action_config),
            job.timeout, job.retry_count, job.retry_delay,
            int(job.concurrent), job.priority, json.dumps(job.tags),
            job.created_at
        ))
        
        conn.commit()
        conn.close()
        
        self.jobs[job.id] = job
        
        if job.enabled:
            self._schedule_job(job)
        
        logger.info(f"✅ Created job: {job.name} (ID: {job.id})")
        return job.id

    def update_job(self, job_id: str, updates: Dict):
        """Update an existing job"""
        if job_id not in self.jobs:
            raise ValueError(f"Job {job_id} not found")
        
        job = self.jobs[job_id]
        for key, value in updates.items():
            if hasattr(job, key):
                setattr(job, key, value)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Update database
        cursor.execute('''
            UPDATE jobs SET
                name = ?, enabled = ?, trigger_type = ?, trigger_config = ?,
                session_port = ?, action_type = ?, action_config = ?,
                timeout = ?, retry_count = ?, retry_delay = ?,
                concurrent = ?, priority = ?, tags = ?
            WHERE id = ?
        ''', (
            job.name, int(job.enabled), job.trigger_type,
            json.dumps(job.trigger_config), job.session_port,
            job.action_type, json.dumps(job.action_config),
            job.timeout, job.retry_count, job.retry_delay,
            int(job.concurrent), job.priority, json.dumps(job.tags),
            job_id
        ))
        
        conn.commit()
        conn.close()
        
        # Reschedule job if enabled
        if job.enabled:
            self.scheduler.remove_job(job_id)
            self._schedule_job(job)
        else:
            self.scheduler.remove_job(job_id)
        
        logger.info(f"✅ Updated job: {job.name}")

    def delete_job(self, job_id: str):
        """Delete a job"""
        if job_id not in self.jobs:
            raise ValueError(f"Job {job_id} not found")
        
        self.scheduler.remove_job(job_id)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM jobs WHERE id = ?', (job_id,))
        cursor.execute('DELETE FROM job_results WHERE job_id = ?', (job_id,))
        conn.commit()
        conn.close()
        
        del self.jobs[job_id]
        logger.info(f"✅ Deleted job: {job_id}")

    def get_job(self, job_id: str) -> Optional[JobConfig]:
        """Get job by ID"""
        return self.jobs.get(job_id)

    def list_jobs(self, tags: List[str] = None) -> List[JobConfig]:
        """List all jobs, optionally filtered by tags"""
        jobs = list(self.jobs.values())
        if tags:
            jobs = [j for j in jobs if any(tag in j.tags for tag in tags)]
        return jobs

    def get_job_status(self, job_id: str) -> JobStatus:
        """Get current status of a job"""
        if job_id not in self.jobs:
            return JobStatus.PENDING
        
        if job_id in self.running_jobs:
            return JobStatus.RUNNING
        
        return self.job_status.get(job_id, JobStatus.PENDING)

    def get_job_results(self, job_id: str, limit: int = 10) -> List[Dict]:
        """Get recent results for a job"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM job_results WHERE job_id = ? ORDER BY id DESC LIMIT ?
        ''', (job_id, limit))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [
            {
                'id': row[0],
                'job_id': row[1],
                'status': row[2],
                'start_time': row[3],
                'end_time': row[4],
                'duration': row[5],
                'result': row[6],
                'error': row[7],
                'data': json.loads(row[8]) if row[8] else None
            }
            for row in rows
        ]

    def pause_all_jobs(self):
        """Pause all scheduled jobs"""
        self.scheduler.pause()
        logger.info("⏸️ All jobs paused")

    def resume_all_jobs(self):
        """Resume all scheduled jobs"""
        self.scheduler.resume()
        logger.info("▶️ All jobs resumed")

    def run_job_now(self, job_id: str):
        """Run a job immediately"""
        if job_id not in self.jobs:
            raise ValueError(f"Job {job_id} not found")
        
        # Run in separate thread to not block
        threading.Thread(
            target=self._execute_job,
            args=(job_id,),
            daemon=True
        ).start()
        
        logger.info(f"▶️ Job {job_id} started manually")

    def shutdown(self):
        """Shutdown scheduler"""
        self._running = False
        self.scheduler.shutdown()
        self.executor.shutdown(wait=True)
        logger.info("🛑 Job scheduler shutdown")

# ============================================================================
# Data Storage & Export
# ============================================================================

class DataStorage:
    def __init__(self, storage_dir: str = "~/chrome_data"):
        self.storage_dir = Path(os.path.expanduser(storage_dir))
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def save_json(self, data: Dict, name: str, subdir: str = "") -> str:
        """Save data as JSON"""
        path = self._get_path(name, subdir, 'json')
        with open(path, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        return str(path)

    def save_csv(self, data: List[Dict], name: str, subdir: str = "") -> str:
        """Save data as CSV"""
        import pandas as pd
        path = self._get_path(name, subdir, 'csv')
        df = pd.DataFrame(data)
        df.to_csv(path, index=False)
        return str(path)

    def save_text(self, data: str, name: str, subdir: str = "") -> str:
        """Save data as text"""
        path = self._get_path(name, subdir, 'txt')
        with open(path, 'w') as f:
            f.write(data)
        return str(path)

    def load_json(self, name: str, subdir: str = "") -> Dict:
        """Load JSON data"""
        path = self._get_path(name, subdir, 'json')
        with open(path, 'r') as f:
            return json.load(f)

    def list_files(self, subdir: str = "") -> List[Path]:
        """List files in storage"""
        path = self.storage_dir / subdir
        if path.exists():
            return list(path.glob('*'))
        return []

    def _get_path(self, name: str, subdir: str, ext: str) -> Path:
        """Get file path"""
        if subdir:
            path = self.storage_dir / subdir
            path.mkdir(parents=True, exist_ok=True)
            return path / f"{name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{ext}"
        return self.storage_dir / f"{name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{ext}"

# ============================================================================
# Main Enhanced Session Manager
# ============================================================================

class ChromeSessionManagerEnhanced:
    def __init__(self):
        self.config = Config()
        self.db = SessionDB()
        self.storage = DataStorage()
        self.scheduler = JobScheduler(SchedulerConfig())
        self.display_manager = DisplayManager(self.config)
        self.display, self.vnc_port = self.display_manager.get_display()
        self.chrome_path = self._find_chrome()
        self.launcher = ChromeLauncher(self.config, self.chrome_path, self.display_manager)
        self.devtools: Dict[int, ChromeDevTools] = {}
        self.js_manager = JavaScriptManager()
        self._running = True
        self._cleanup_called = False
        self._session_locks = SessionLockManager()
        self._session_start_times: Dict[int, float] = {}
        
        # Job templates
        self.templates = {t.id: t for t in JOB_TEMPLATES}
        
        self._startup_cleanup()
        self._setup_signals()
        
        # Health check thread
        self._health_thread = threading.Thread(target=self._health_loop, daemon=True)
        self._health_thread.start()

    def _find_chrome(self):
        paths = [
            "chromium-browser", "chromium", "google-chrome",
            "google-chrome-stable", "/usr/bin/chromium-browser",
            "/usr/bin/chromium",
        ]
        for path in paths:
            if shutil.which(path):
                return path
        raise RuntimeError("Chrome not found")

    def _startup_cleanup(self):
        sessions = self.db.list_sessions()
        cleaned = 0
        for session in sessions:
            if session['status'] == 'running':
                if session['pid']:
                    try:
                        os.kill(session['pid'], 0)
                    except OSError:
                        self.db.stop_session(session['id'])
                        self.db.release_port(session['port'])
                        cleaned += 1
        if cleaned:
            logger.info(f"Cleaned up {cleaned} stale sessions")

    def _setup_signals(self):
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
        atexit.register(self._cleanup)

    def _signal_handler(self, signum, frame):
        logger.info(f"Received signal {signum}, shutting down...")
        self._running = False
        self._cleanup()
        sys.exit(0)

    def _cleanup(self):
        if self._cleanup_called:
            return
        self._cleanup_called = True
        
        logger.info("Cleaning up resources...")
        self.scheduler.shutdown()
        
        sessions = self.db.list_sessions()
        for session in sessions:
            if session['status'] == 'running':
                self._stop_session_internal(session['id'])
        
        with self._devtools_lock:
            self.devtools.clear()
        
        logger.info("Cleanup complete")

    def _health_loop(self):
        while self._running:
            try:
                self._check_health()
                time.sleep(self.config.health_check_interval)
            except Exception as e:
                logger.error(f"Health check error: {e}", exc_info=True)

    def _check_health(self):
        sessions = self.db.list_sessions()
        for session in sessions:
            if session['status'] == 'running':
                self._check_session_health(session['id'])

    def _check_session_health(self, session_id: int):
        if not self._session_locks.acquire(session_id, timeout=2.0):
            return
        
        try:
            session = self.db.get_session(session_id)
            if not session or session['status'] != 'running':
                return
            
            if session['pid']:
                try:
                    os.kill(session['pid'], 0)
                except OSError:
                    logger.warning(f"Session {session_id} PID {session['pid']} dead")
                    self._recover_session(session_id)
                    return
            
        except Exception as e:
            logger.error(f"Health check error for session {session_id}: {e}")
        finally:
            self._session_locks.release(session_id)

    def _recover_session(self, session_id: int):
        session = self.db.get_session(session_id)
        if not session:
            return
        
        restart_count = self.db.get_session_restart_count(session_id)
        if restart_count >= self.config.max_session_restarts:
            logger.error(f"Session {session_id} exceeded max restarts")
            self._stop_session_internal(session_id)
            return
        
        self.db.increment_session_restart_count(session_id)
        self._stop_session_internal(session_id)
        time.sleep(2)
        self._start_session_internal(session_id)

    def _get_devtools(self, port: int) -> ChromeDevTools:
        with self._devtools_lock:
            if port not in self.devtools:
                self.devtools[port] = ChromeDevTools(port=port)
            return self.devtools[port]

    def start_session(self, session_id: int):
        if not self._session_locks.acquire(session_id, timeout=self.config.session_lock_timeout):
            logger.error(f"Could not acquire lock for session {session_id}")
            return
        try:
            self._start_session_internal(session_id)
        finally:
            self._session_locks.release(session_id)

    def _start_session_internal(self, session_id: int):
        session = self.db.get_session(session_id)
        if not session:
            logger.error(f"Session {session_id} not found")
            return
        
        if self._is_port_in_use(session['port']):
            new_port = self._get_next_port()
            logger.info(f"Port {session['port']} in use, using {new_port}")
            self.db.update_session_port(session_id, new_port)
            session['port'] = new_port
        
        logger.info(f"Starting session '{session['name']}'...")
        console.print(f"[blue]🚀 Starting session '{session['name']}' on port {session['port']}...[/blue]")
        
        profile_dir = session['profile_dir']
        os.makedirs(profile_dir, exist_ok=True)
        
        success, pid, error = self.launcher.launch_with_retry(session)
        
        if success:
            self.db.start_session(session_id, pid)
            self.db.reset_session_restart_count(session_id)
            self._session_start_times[session_id] = time.time()
            logger.info(f"Session {session_id} started (PID: {pid})")
            console.print(f"[green]✅ Session '{session['name']}' started![/green]")
        else:
            logger.error(f"Failed to start session: {error}")
            console.print(f"[red]❌ Failed to start session: {error}[/red]")

    def _is_port_in_use(self, port: int) -> bool:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(1)
                return sock.connect_ex(('127.0.0.1', port)) == 0
        except:
            return False

    def _get_next_port(self) -> int:
        used_ports = set(self.db.get_all_ports())
        for port in range(self.config.debug_port_start, self.config.debug_port_end + 1):
            if port in used_ports:
                continue
            if self._is_port_in_use(port):
                continue
            return port
        raise RuntimeError("No available ports")

    def stop_session(self, session_id: int):
        if not self._session_locks.acquire(session_id, timeout=self.config.session_lock_timeout):
            logger.error(f"Could not acquire lock for session {session_id}")
            return
        try:
            self._stop_session_internal(session_id)
        finally:
            self._session_locks.release(session_id)

    def _stop_session_internal(self, session_id: int):
        session = self.db.get_session(session_id)
        if not session or session['status'] != 'running':
            return
        
        console.print(f"[yellow]⏹️ Stopping session '{session['name']}'...[/yellow]")
        
        if session['pid']:
            try:
                os.kill(session['pid'], signal.SIGTERM)
                time.sleep(2)
                try:
                    os.kill(session['pid'], 0)
                    os.kill(session['pid'], signal.SIGKILL)
                except OSError:
                    pass
            except Exception as e:
                logger.error(f"Failed to kill process: {e}")
        
        self.db.stop_session(session_id)
        self.db.release_port(session['port'])
        
        with self._devtools_lock:
            if session['port'] in self.devtools:
                del self.devtools[session['port']]
        
        if session_id in self._session_start_times:
            del self._session_start_times[session_id]
        
        logger.info(f"Session {session_id} stopped")
        console.print(f"[green]✅ Session '{session['name']}' stopped[/green]")

    # ========================================================================
    # Job Management
    # ========================================================================

    def create_job(self):
        """Interactive job creation"""
        console.print()
        console.print(Panel("🆕 Create New Job", style="bold green"))
        
        # Job name
        name = Prompt.ask("📝 Job name")
        if not name:
            console.print("[red]Name cannot be empty[/red]")
            return
        
        # Check if using template
        if Confirm.ask("Use a job template?"):
            self._create_job_from_template(name)
            return
        
        # Create job from scratch
        job = JobConfig()
        job.name = name
        
        # Trigger type
        trigger_types = ["interval", "cron", "date"]
        trigger_type = Prompt.ask(
            "⏰ Trigger type",
            choices=trigger_types,
            default="interval"
        )
        job.trigger_type = trigger_type
        
        # Trigger configuration
        if trigger_type == "interval":
            minutes = int(Prompt.ask("Minutes between runs", default="5"))
            job.trigger_config = {"minutes": minutes}
        elif trigger_type == "cron":
            job.trigger_config = {
                "minute": Prompt.ask("Minute (0-59)", default="0"),
                "hour": Prompt.ask("Hour (0-23)", default="*"),
                "day": Prompt.ask("Day (1-31)", default="*"),
                "month": Prompt.ask("Month (1-12)", default="*"),
                "day_of_week": Prompt.ask("Day of week (0-6 or mon-sun)", default="*")
            }
        elif trigger_type == "date":
            run_date = Prompt.ask("Run date (YYYY-MM-DD HH:MM:SS)")
            job.trigger_config = {"run_date": run_date}
        
        # Session port
        sessions = self.db.list_sessions()
        if sessions:
            console.print("[dim]Available sessions:[/dim]")
            for s in sessions:
                console.print(f"  {s['id']}: {s['name']} (port: {s['port']})")
            port = int(Prompt.ask("Session port", default=str(sessions[0]['port'])))
        else:
            port = self._get_next_port()
            console.print(f"[dim]Auto-assigned port: {port}[/dim]")
        job.session_port = port
        
        # Action type
        action_types = ["browser", "api", "js", "python", "shell"]
        action_type = Prompt.ask(
            "Action type",
            choices=action_types,
            default="browser"
        )
        job.action_type = action_type
        
        # Action configuration
        if action_type == "browser":
            job.action_config = self._configure_browser_action()
        elif action_type == "api":
            job.action_config = self._configure_api_action()
        elif action_type == "js":
            job.action_config = self._configure_js_action()
        elif action_type == "python":
            job.action_config = self._configure_python_action()
        elif action_type == "shell":
            job.action_config = self._configure_shell_action()
        
        # Additional settings
        job.timeout = int(Prompt.ask("Timeout (seconds)", default="300"))
        job.retry_count = int(Prompt.ask("Retry count", default="3"))
        job.retry_delay = int(Prompt.ask("Retry delay (seconds)", default="30"))
        
        # Tags
        tags_input = Prompt.ask("Tags (comma-separated)", default="")
        if tags_input:
            job.tags = [t.strip() for t in tags_input.split(',')]
        
        # Create the job
        job_id = self.scheduler.create_job(job)
        console.print(f"[green]✅ Job created! ID: {job_id}[/green]")
        
        if Confirm.ask("Run job now?"):
            self.scheduler.run_job_now(job_id)

    def _create_job_from_template(self, name: str):
        """Create job from template"""
        template_ids = list(self.templates.keys())
        
        console.print("[dim]Available templates:[/dim]")
        for tid, template in self.templates.items():
            console.print(f"  {tid}: {template.name} ({template.category})")
        
        template_id = Prompt.ask("Select template", choices=template_ids)
        template = self.templates[template_id]
        
        # Get session port
        sessions = self.db.list_sessions()
        if sessions:
            console.print("[dim]Available sessions:[/dim]")
            for s in sessions:
                console.print(f"  {s['id']}: {s['name']} (port: {s['port']})")
            port = int(Prompt.ask("Session port", default=str(sessions[0]['port'])))
        else:
            port = self._get_next_port()
            console.print(f"[dim]Auto-assigned port: {port}[/dim]")
        
        # Get credentials
        console.print("[yellow]⚠️ The template uses variables. Please provide values:[/yellow]")
        
        action_config = template.config.copy()
        # Replace variables
        config_str = json.dumps(action_config)
        
        # Find all {{variables}}
        import re
        variables = re.findall(r'\{\{([^}]+)\}\}', config_str)
        var_values = {}
        
        for var in set(variables):
            value = Prompt.ask(f"  {var}", default="")
            var_values[var] = value
            config_str = config_str.replace(f'{{{{{var}}}}}', value)
        
        job = JobConfig(
            name=name,
            trigger_type="interval",
            trigger_config={"minutes": 30},
            session_port=port,
            action_type="browser",
            action_config=json.loads(config_str),
            tags=template.tags
        )
        
        # Schedule options
        if Confirm.ask("Set a schedule?"):
            minutes = int(Prompt.ask("Minutes between runs", default="30"))
            job.trigger_config = {"minutes": minutes}
        
        job_id = self.scheduler.create_job(job)
        console.print(f"[green]✅ Job created from template! ID: {job_id}[/green]")

    def _configure_browser_action(self) -> Dict:
        """Configure browser action"""
        actions = []
        
        while True:
            console.print("[dim]Add browser actions:[/dim]")
            action_types = [
                "navigate", "click", "fill", "type", "wait",
                "wait_for_selector", "screenshot", "evaluate",
                "get_text", "get_attribute", "submit"
            ]
            action_type = Prompt.ask(
                "Action type",
                choices=action_types,
                default="navigate"
            )
            
            if action_type == "navigate":
                url = Prompt.ask("URL")
                actions.append({"type": "navigate", "url": url})
            elif action_type == "click":
                selector = Prompt.ask("CSS selector")
                actions.append({"type": "click", "selector": selector})
            elif action_type == "fill":
                selector = Prompt.ask("CSS selector")
                value = Prompt.ask("Value")
                actions.append({"type": "fill", "selector": selector, "value": value})
            elif action_type == "type":
                selector = Prompt.ask("CSS selector")
                text = Prompt.ask("Text to type")
                delay = int(Prompt.ask("Typing delay (ms)", default="100"))
                actions.append({"type": "type", "selector": selector, "text": text, "delay": delay})
            elif action_type == "wait":
                seconds = int(Prompt.ask("Seconds to wait", default="2"))
                actions.append({"type": "wait", "seconds": seconds})
            elif action_type == "wait_for_selector":
                selector = Prompt.ask("CSS selector")
                timeout = int(Prompt.ask("Timeout (ms)", default="30000"))
                actions.append({"type": "wait_for_selector", "selector": selector, "timeout": timeout})
            elif action_type == "screenshot":
                save_to = Prompt.ask("Save path", default="screenshots/{{timestamp}}.png")
                actions.append({"type": "screenshot", "save_to": save_to})
            elif action_type == "evaluate":
                script = Prompt.ask("JavaScript to evaluate")
                actions.append({"type": "evaluate", "script": script})
            elif action_type == "get_text":
                selector = Prompt.ask("CSS selector")
                actions.append({"type": "get_text", "selector": selector})
            elif action_type == "get_attribute":
                selector = Prompt.ask("CSS selector")
                attribute = Prompt.ask("Attribute name")
                actions.append({"type": "get_attribute", "selector": selector, "attribute": attribute})
            elif action_type == "submit":
                selector = Prompt.ask("CSS selector of submit button")
                actions.append({"type": "submit", "selector": selector})
            
            if not Confirm.ask("Add another action?"):
                break
        
        return {"actions": actions}

    def _configure_api_action(self) -> Dict:
        """Configure API action"""
        url = Prompt.ask("API URL")
        method = Prompt.ask("HTTP method", choices=["GET", "POST", "PUT", "DELETE"], default="GET")
        
        config = {"url": url, "method": method}
        
        if method in ["POST", "PUT"]:
            if Confirm.ask("Send JSON data?"):
                json_data = Prompt.ask("JSON data (as string)")
                config["json"] = True
                config["data"] = json.loads(json_data)
        
        if Confirm.ask("Add headers?"):
            headers = {}
            while True:
                key = Prompt.ask("Header key (empty to stop)")
                if not key:
                    break
                value = Prompt.ask("Header value")
                headers[key] = value
            config["headers"] = headers
        
        return config

    def _configure_js_action(self) -> Dict:
        """Configure JavaScript action"""
        console.print("[dim]Enter JavaScript code (end with CTRL+D on empty line):[/dim]")
        lines = []
        while True:
            try:
                line = input()
                if not line and not lines:
                    break
                lines.append(line)
            except EOFError:
                break
        
        script = '\n'.join(lines)
        return {"script": script}

    def _configure_python_action(self) -> Dict:
        """Configure Python action"""
        console.print("[dim]Enter Python code (end with CTRL+D on empty line):[/dim]")
        lines = []
        while True:
            try:
                line = input()
                if not line and not lines:
                    break
                lines.append(line)
            except EOFError:
                break
        
        script = '\n'.join(lines)
        return {"script": script, "data": {}}

    def _configure_shell_action(self) -> Dict:
        """Configure shell action"""
        command = Prompt.ask("Shell command")
        cwd = Prompt.ask("Working directory", default=os.getcwd())
        return {"command": command, "cwd": cwd}

    def list_jobs(self):
        """List all jobs"""
        jobs = self.scheduler.list_jobs()
        
        if not jobs:
            console.print("[yellow]No jobs found[/yellow]")
            return
        
        table = Table(title="📋 Scheduled Jobs", box=box.ROUNDED)
        table.add_column("ID", style="cyan", width=8)
        table.add_column("Name", style="green")
        table.add_column("Trigger", style="blue")
        table.add_column("Port", style="yellow", width=6)
        table.add_column("Status", style="magenta", width=10)
        table.add_column("Runs", style="white", width=8)
        table.add_column("Tags", style="dim")
        
        for job in jobs:
            status = self.scheduler.get_job_status(job.id)
            status_colors = {
                JobStatus.PENDING: "dim",
                JobStatus.RUNNING: "green",
                JobStatus.COMPLETED: "blue",
                JobStatus.FAILED: "red",
                JobStatus.RETRYING: "yellow",
                JobStatus.CANCELLED: "red",
                JobStatus.SCHEDULED: "cyan"
            }
            
            status_str = status.value.upper()
            if status == JobStatus.RUNNING:
                status_str += " 🔄"
            elif status == JobStatus.COMPLETED:
                status_str += " ✅"
            elif status == JobStatus.FAILED:
                status_str += " ❌"
            
            trigger_info = f"{job.trigger_type}"
            if job.trigger_type == "interval":
                trigger_info += f" {job.trigger_config.get('minutes', 0)}m"
            elif job.trigger_type == "cron":
                trigger_info += " ⏰"
            
            table.add_row(
                job.id[:8],
                job.name[:30],
                trigger_info,
                str(job.session_port),
                f"[{status_colors.get(status, 'white')}]{status_str}[/]",
                f"{job.run_count}",
                ", ".join(job.tags[:3]) if job.tags else ""
            )
        
        console.print(table)

    def show_job_details(self, job_id: str):
        """Show job details"""
        job = self.scheduler.get_job(job_id)
        if not job:
            console.print(f"[red]Job not found: {job_id}[/red]")
            return
        
        status = self.scheduler.get_job_status(job_id)
        results = self.scheduler.get_job_results(job_id, limit=5)
        
        content = f"""
[bold cyan]Job Details[/bold cyan]

[bold]ID:[/bold] {job.id}
[bold]Name:[/bold] {job.name}
[bold]Status:[/bold] {status.value.upper()}
[bold]Trigger:[/bold] {job.trigger_type}
[bold]Trigger Config:[/bold] {json.dumps(job.trigger_config, indent=2)}
[bold]Session Port:[/bold] {job.session_port}
[bold]Action Type:[/bold] {job.action_type}
[bold]Timeout:[/bold] {job.timeout}s
[bold]Retry Count:[/bold] {job.retry_count}
[bold]Retry Delay:[/bold] {job.retry_delay}s
[bold]Concurrent:[/bold] {job.concurrent}
[bold]Priority:[/bold] {job.priority}
[bold]Tags:[/bold] {', '.join(job.tags)}
[bold]Created:[/bold] {job.created_at}
[bold]Last Run:[/bold] {job.last_run or 'Never'}
[bold]Run Count:[/bold] {job.run_count}
[bold]Success Count:[/bold] {job.success_count}
[bold]Error Count:[/bold] {job.error_count}

[bold cyan]Action Config:[/bold cyan]
{json.dumps(job.action_config, indent=2)}

[bold cyan]Recent Results:[/bold cyan]
"""
        if results:
            for r in results[:3]:
                status_icon = "✅" if r['status'] == 'success' else "❌"
                content += f"\n  {status_icon} {r['start_time']} - {r['status']}"
                if r.get('duration'):
                    content += f" ({r['duration']:.2f}s)"
                if r.get('error'):
                    content += f"\n     Error: {r['error'][:200]}"
        else:
            content += "\n  No results yet"
        
        console.print(Panel(content, title="📊 Job Details", border_style="blue"))

    def delete_job(self):
        """Delete a job"""
        job_id = Prompt.ask("Job ID to delete")
        
        if not Confirm.ask(f"Delete job {job_id}?"):
            return
        
        try:
            self.scheduler.delete_job(job_id)
            console.print(f"[green]✅ Job deleted[/green]")
        except Exception as e:
            console.print(f"[red]Failed to delete job: {e}[/red]")

    def run_job_now(self):
        """Run a job immediately"""
        job_id = Prompt.ask("Job ID to run")
        
        try:
            self.scheduler.run_job_now(job_id)
            console.print(f"[green]✅ Job started[/green]")
        except Exception as e:
            console.print(f"[red]Failed to run job: {e}[/red]")

    def toggle_job(self):
        """Enable/disable a job"""
        job_id = Prompt.ask("Job ID to toggle")
        job = self.scheduler.get_job(job_id)
        
        if not job:
            console.print(f"[red]Job not found: {job_id}[/red]")
            return
        
        new_enabled = not job.enabled
        self.scheduler.update_job(job_id, {'enabled': new_enabled})
        
        console.print(f"[green]✅ Job {'enabled' if new_enabled else 'disabled'}[/green]")

    # ========================================================================
    # Template Management
    # ========================================================================

    def list_templates(self):
        """List available job templates"""
        if not self.templates:
            console.print("[yellow]No templates available[/yellow]")
            return
        
        table = Table(title="📋 Job Templates", box=box.ROUNDED)
        table.add_column("ID", style="cyan")
        table.add_column("Name", style="green")
        table.add_column("Category", style="blue")
        table.add_column("Tags", style="dim")
        table.add_column("Actions", style="white")
        
        for template in self.templates.values():
            actions = len(template.config.get('actions', []))
            table.add_row(
                template.id,
                template.name[:30],
                template.category,
                ", ".join(template.tags[:3]),
                f"{actions} actions"
            )
        
        console.print(table)

    def show_template_details(self, template_id: str):
        """Show template details"""
        template = self.templates.get(template_id)
        if not template:
            console.print(f"[red]Template not found: {template_id}[/red]")
            return
        
        console.print(Panel(
            f"""
[bold cyan]{template.name}[/bold cyan]
[bold]Description:[/bold] {template.description}
[bold]Category:[/bold] {template.category}
[bold]Tags:[/bold] {', '.join(template.tags)}
[bold]Config:[/bold]
{json.dumps(template.config, indent=2)}
""",
            title="📋 Template Details",
            border_style="blue"
        ))

    # ========================================================================
    # Interactive Menu
    # ========================================================================

    def interactive_menu(self):
        while True:
            console.clear()
            console.print()
            
            header = """
╔══════════════════════════════════════════════════════════════════╗
║     🌐 Chrome Session Manager - Production v19                 ║
║     Advanced Scheduler & Automation Engine                    ║
║     Job Applications | Hackathons | Chatbots | Scraping       ║
╚══════════════════════════════════════════════════════════════════╝
            """
            console.print(Panel(header, border_style="cyan"))
            
            # Show session summary
            sessions = self.db.list_sessions()
            running = len([s for s in sessions if s['status'] == 'running'])
            stopped = len([s for s in sessions if s['status'] == 'stopped'])
            jobs = self.scheduler.list_jobs()
            
            summary = f"""
[bold]Sessions:[/bold] {len(sessions)} total ({running} running, {stopped} stopped)
[bold]Jobs:[/bold] {len(jobs)} total
[bold]Templates:[/bold] {len(self.templates)} available
[bold]VNC:[/bold] {'vnc://127.0.0.1:' + str(self.vnc_port) if self.vnc_port else 'N/A'}
            """
            console.print(Panel(summary, title="📊 Summary", border_style="green"))
            
            console.print()
            menu = Table(show_header=False, box=box.MINIMAL_HEAVY_HEAD)
            menu.add_column("Option", style="cyan", width=8)
            menu.add_column("Action", style="white")
            menu.add_column("Description", style="dim")
            
            menu.add_row("1", "[green]Create Session[/green]", "Create a new Chrome session")
            menu.add_row("2", "[blue]Start Session[/blue]", "Start an existing session")
            menu.add_row("3", "[yellow]Stop Session[/yellow]", "Stop a running session")
            menu.add_row("4", "[magenta]List Sessions[/magenta]", "Show all sessions")
            menu.add_row("5", "[cyan]Session Details[/cyan]", "Show detailed session info")
            menu.add_row("6", "[red]Delete Session[/red]", "Delete a session")
            
            menu.add_row("", "", "")
            menu.add_row("J1", "[bold green]Create Job[/bold green]", "Create a new automated job")
            menu.add_row("J2", "[bold blue]List Jobs[/bold blue]", "List all scheduled jobs")
            menu.add_row("J3", "[bold yellow]Job Details[/bold yellow]", "Show job details")
            menu.add_row("J4", "[bold red]Delete Job[/bold red]", "Delete a job")
            menu.add_row("J5", "[bold cyan]Run Job Now[/bold cyan]", "Run a job immediately")
            menu.add_row("J6", "[bold magenta]Toggle Job[/bold magenta]", "Enable/disable a job")
            
            menu.add_row("", "", "")
            menu.add_row("T1", "[bold]List Templates[/bold]", "List available job templates")
            menu.add_row("T2", "[bold]Template Details[/bold]", "Show template details")
            
            menu.add_row("", "", "")
            menu.add_row("D", "[bold]Dashboard[/bold]", "Show comprehensive dashboard")
            menu.add_row("P", "[bold]Pause All Jobs[/bold]", "Pause all scheduled jobs")
            menu.add_row("R", "[bold]Resume All Jobs[/bold]", "Resume all scheduled jobs")
            
            menu.add_row("", "", "")
            menu.add_row("0", "[red]Exit[/red]", "Exit the manager")
            
            console.print(menu)
            console.print()
            
            choice = Prompt.ask("Select option", choices=[
                "0", "1", "2", "3", "4", "5", "6",
                "J1", "J2", "J3", "J4", "J5", "J6",
                "T1", "T2", "D", "P", "R"
            ])
            
            if choice == "0":
                console.print("[green]Goodbye! 👋[/green]")
                break
            
            elif choice == "1":
                self.create_session()
                
            elif choice == "2":
                try:
                    session_id = int(Prompt.ask("Enter session ID to start"))
                    self.start_session(session_id)
                except ValueError:
                    console.print("[red]Invalid ID[/red]")
                    
            elif choice == "3":
                try:
                    session_id = int(Prompt.ask("Enter session ID to stop"))
                    self.stop_session(session_id)
                except ValueError:
                    console.print("[red]Invalid ID[/red]")
                    
            elif choice == "4":
                self.list_sessions()
                
            elif choice == "5":
                try:
                    session_id = int(Prompt.ask("Enter session ID"))
                    self.show_session_details(session_id)
                except ValueError:
                    console.print("[red]Invalid ID[/red]")
                    
            elif choice == "6":
                try:
                    session_id = int(Prompt.ask("Enter session ID to delete"))
                    self.delete_session(session_id)
                except ValueError:
                    console.print("[red]Invalid ID[/red]")
                    
            elif choice == "J1":
                self.create_job()
                
            elif choice == "J2":
                self.list_jobs()
                
            elif choice == "J3":
                job_id = Prompt.ask("Enter job ID")
                self.show_job_details(job_id)
                
            elif choice == "J4":
                self.delete_job()
                
            elif choice == "J5":
                self.run_job_now()
                
            elif choice == "J6":
                self.toggle_job()
                
            elif choice == "T1":
                self.list_templates()
                
            elif choice == "T2":
                template_id = Prompt.ask("Enter template ID")
                self.show_template_details(template_id)
                
            elif choice == "D":
                self.show_dashboard()
                
            elif choice == "P":
                self.scheduler.pause_all_jobs()
                console.print("[yellow]⏸️ All jobs paused[/yellow]")
                
            elif choice == "R":
                self.scheduler.resume_all_jobs()
                console.print("[green]▶️ All jobs resumed[/green]")
            
            if choice != "0":
                console.print()
                Prompt.ask("Press Enter to continue...")

    def show_dashboard(self):
        """Show comprehensive dashboard"""
        sessions = self.db.list_sessions()
        jobs = self.scheduler.list_jobs()
        
        running_sessions = [s for s in sessions if s['status'] == 'running']
        stopped_sessions = [s for s in sessions if s['status'] == 'stopped']
        
        # Job status counts
        job_status_counts = {}
        for job in jobs:
            status = self.scheduler.get_job_status(job.id)
            job_status_counts[status.value] = job_status_counts.get(status.value, 0) + 1
        
        content = f"""
[bold green]📊 Chrome Session Manager Dashboard[/bold green]

[bold]Sessions:[/bold]
  Total: {len(sessions)}
  🟢 Running: {len(running_sessions)}
  ⚪ Stopped: {len(stopped_sessions)}
  🔌 Available Ports: {len(self.db.get_available_ports())}

[bold]Jobs:[/bold]
  Total: {len(jobs)}
  {''.join([f'  {k.title()}: {v}\n' for k, v in job_status_counts.items()])}

[bold]Templates:[/bold]
  Available: {len(self.templates)}
  Categories: {', '.join(set(t.category for t in self.templates.values()))}

[bold]Display:[/bold]
  🖥️ Display: {self.display or 'None (headless)'}
  📺 VNC: {'vnc://127.0.0.1:' + str(self.vnc_port) if self.vnc_port else 'N/A'}
  🔑 VNC Password: {self.config.vnc_password}

[bold]Storage:[/bold]
  📁 Base Directory: {self.config.base_profile_dir}
  📁 Data Storage: {self.storage.storage_dir}
  📁 Log Directory: {self.config.log_dir}

[bold]Scheduler:[/bold]
  Running: {self.scheduler.running}
  Workers: {self.scheduler.executor._max_workers}
  Timezone: {self.scheduler.config.timezone}
"""
        console.print(Panel(content, title="Dashboard", border_style="cyan"))

    # Reusing methods from original class
    def create_session(self):
        from your_original_file import create_session  # This should be imported from your original file
        # Actually we need to implement this or import properly
        # For now, let's implement a simple version
        console.print()
        console.print(Panel("🆕 Create New Chrome Session", style="bold green"))
        
        name = Prompt.ask("📝 Session name")
        if not name:
            console.print("[red]Name cannot be empty[/red]")
            return
        
        if self.db.get_session_by_name(name):
            console.print(f"[red]Session '{name}' already exists[/red]")
            return
        
        url = Prompt.ask("🌐 Website URL", default="https://web.whatsapp.com")
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"
        
        port = self._get_next_port()
        console.print(f"[green]Auto-assigned port: {port}[/green]")
        
        profile_dir = os.path.join(self.config.base_profile_dir, name)
        os.makedirs(profile_dir, exist_ok=True)
        
        try:
            session_id = self.db.create_session(name, url, port, profile_dir)
        except Exception as e:
            console.print(f"[red]Error creating session: {e}[/red]")
            return
        
        console.print()
        console.print(f"[green]✅ Session created! ID: {session_id}[/green]")
        console.print(f"   Name: {name}")
        console.print(f"   URL: {url}")
        console.print(f"   Port: {port}")
        
        if Confirm.ask("🚀 Start this session now?"):
            self.start_session(session_id)

    def list_sessions(self):
        sessions = self.db.list_sessions()
        if not sessions:
            console.print("[yellow]No sessions found[/yellow]")
            return
        
        table = Table(title="📋 Chrome Sessions", box=box.ROUNDED)
        table.add_column("ID", style="cyan", width=4)
        table.add_column("Name", style="green")
        table.add_column("URL", style="blue")
        table.add_column("Port", style="yellow", width=6)
        table.add_column("Status", style="magenta", width=10)
        table.add_column("PID", style="red", width=8)
        
        for session in sessions:
            status_color = "green" if session['status'] == 'running' else "dim"
            table.add_row(
                str(session['id']),
                session['name'],
                session['url'][:30] + "..." if len(session['url']) > 30 else session['url'],
                str(session['port']),
                f"[{status_color}]{session['status']}[/{status_color}]",
                str(session['pid']) if session['pid'] else "-"
            )
        
        console.print(table)

    def show_session_details(self, session_id: int):
        session = self.db.get_session(session_id)
        if not session:
            console.print(f"[red]Session not found[/red]")
            return
        
        content = f"""
[bold cyan]Session Details[/bold cyan]

[bold]ID:[/bold] {session['id']}
[bold]Name:[/bold] {session['name']}
[bold]URL:[/bold] {session['url']}
[bold]Port:[/bold] {session['port']}
[bold]Status:[/bold] {session['status']}
[bold]PID:[/bold] {session['pid'] if session['pid'] else 'N/A'}
[bold]Restart Count:[/bold] {session.get('restart_count', 0)}
[bold]Profile Directory:[/bold] {session['profile_dir']}
[bold]Created:[/bold] {session['created_at']}
[bold]Last Used:[/bold] {session['last_used'] if session['last_used'] else 'Never'}
"""
        console.print(Panel(content, title="📊 Session Details", border_style="blue"))

    def delete_session(self, session_id: int):
        session = self.db.get_session(session_id)
        if not session:
            console.print(f"[red]Session not found[/red]")
            return
        
        if session['status'] == 'running':
            console.print(f"[yellow]Session is running. Stop it first.[/yellow]")
            if Confirm.ask("Stop and delete?"):
                self.stop_session(session_id)
                time.sleep(1)
            else:
                return
        
        if Confirm.ask(f"Delete session '{session['name']}'?"):
            if os.path.exists(session['profile_dir']):
                try:
                    shutil.rmtree(session['profile_dir'], ignore_errors=True)
                except:
                    pass
            self.db.delete_session(session_id)
            console.print(f"[green]✅ Session deleted[/green]")

# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    try:
        manager = ChromeSessionManagerEnhanced()
        manager.interactive_menu()
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted[/yellow]")
        sys.exit(0)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        logger.exception("Fatal error")
        sys.exit(1)

if __name__ == "__main__":
    main()
