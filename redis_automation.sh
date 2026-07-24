#!/usr/bin/env python3
"""
Lightweight Redis Scheduler for Chrome Session Manager
Designed for Termux with native Redis installation
"""

import os
import sys
import json
import time
import redis
import uuid
import signal
import threading
import logging
import subprocess
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

# Setup logging
LOG_DIR = Path.home() / "chrome-logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / "redis_scheduler.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ============================================================================
# Redis Connection
# ============================================================================

class RedisClient:
    """Singleton Redis client"""
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance
    
    def _initialize(self):
        self.redis = redis.Redis(
            host='localhost',
            port=6379,
            db=0,
            decode_responses=True,
            socket_keepalive=True,
            socket_connect_timeout=5,
            socket_timeout=5
        )
        # Test connection
        try:
            self.redis.ping()
            logger.info("✅ Connected to Redis")
        except Exception as e:
            logger.error(f"❌ Redis connection failed: {e}")
            raise
    
    def get(self):
        return self.redis

# ============================================================================
# Job Definitions
# ============================================================================

class JobStatus(Enum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"
    CANCELLED = "cancelled"
    SCHEDULED = "scheduled"
    PAUSED = "paused"

@dataclass
class Job:
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = ""
    job_type: str = "shell"  # shell, python, browser, api, chrome
    status: str = "pending"
    priority: int = 2  # 0=highest, 4=lowest
    
    # Schedule
    schedule_type: str = "once"  # once, interval, cron, recurring
    schedule_config: Dict = field(default_factory=dict)
    next_run: Optional[str] = None
    last_run: Optional[str] = None
    
    # Command
    command: str = ""
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    work_dir: str = "."
    timeout: int = 300
    
    # Retry
    max_retries: int = 3
    retry_count: int = 0
    retry_delay: int = 60
    
    # Chrome session
    session_port: Optional[int] = None
    session_name: Optional[str] = None
    
    # Results
    result: Optional[Dict] = None
    error: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    # Tags
    tags: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        return {
            'id': self.id,
            'name': self.name,
            'job_type': self.job_type,
            'status': self.status,
            'priority': self.priority,
            'schedule_type': self.schedule_type,
            'schedule_config': json.dumps(self.schedule_config),
            'next_run': self.next_run,
            'last_run': self.last_run,
            'command': self.command,
            'args': json.dumps(self.args),
            'env': json.dumps(self.env),
            'work_dir': self.work_dir,
            'timeout': self.timeout,
            'max_retries': self.max_retries,
            'retry_count': self.retry_count,
            'retry_delay': self.retry_delay,
            'session_port': self.session_port or 0,
            'session_name': self.session_name or '',
            'result': json.dumps(self.result) if self.result else None,
            'error': self.error,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'tags': json.dumps(self.tags)
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Job':
        return cls(
            id=data.get('id', str(uuid.uuid4())[:8]),
            name=data.get('name', ''),
            job_type=data.get('job_type', 'shell'),
            status=data.get('status', 'pending'),
            priority=int(data.get('priority', 2)),
            schedule_type=data.get('schedule_type', 'once'),
            schedule_config=json.loads(data.get('schedule_config', '{}')),
            next_run=data.get('next_run'),
            last_run=data.get('last_run'),
            command=data.get('command', ''),
            args=json.loads(data.get('args', '[]')),
            env=json.loads(data.get('env', '{}')),
            work_dir=data.get('work_dir', '.'),
            timeout=int(data.get('timeout', 300)),
            max_retries=int(data.get('max_retries', 3)),
            retry_count=int(data.get('retry_count', 0)),
            retry_delay=int(data.get('retry_delay', 60)),
            session_port=int(data.get('session_port')) if data.get('session_port') else None,
            session_name=data.get('session_name'),
            result=json.loads(data.get('result', 'null')) if data.get('result') else None,
            error=data.get('error'),
            created_at=data.get('created_at', datetime.now().isoformat()),
            updated_at=data.get('updated_at', datetime.now().isoformat()),
            tags=json.loads(data.get('tags', '[]'))
        )

# ============================================================================
# Redis Scheduler
# ============================================================================

class RedisScheduler:
    KEY_PREFIX = "chrome:scheduler:"
    
    def __init__(self):
        self.redis = RedisClient().get()
        self._running = False
        self._workers = []
        self._max_workers = 4
        self._lock = threading.RLock()
        
        # Register handlers
        self._handlers = {
            'shell': self._execute_shell,
            'python': self._execute_python,
            'browser': self._execute_browser,
            'api': self._execute_api,
            'chrome': self._execute_chrome_command,
        }
        
        # Setup signal handlers
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
        
        logger.info("✅ Redis Scheduler initialized")
    
    def _signal_handler(self, signum, frame):
        logger.info(f"Received signal {signum}, shutting down...")
        self.shutdown()
        sys.exit(0)
    
    # ========================================================================
    # Job CRUD Operations
    # ========================================================================
    
    def create_job(self, job: Job) -> str:
        """Create a new job"""
        job.updated_at = datetime.now().isoformat()
        
        # Save job
        key = f"{self.KEY_PREFIX}job:{job.id}"
        self.redis.hset(key, mapping=job.to_dict())
        
        # Add to index
        self.redis.sadd(f"{self.KEY_PREFIX}jobs", job.id)
        
        # Schedule if recurring
        if job.schedule_type != 'once' and job.status != JobStatus.PAUSED:
            self._schedule_job(job)
        
        # Queue if immediate
        if job.schedule_type == 'once' and job.status == JobStatus.PENDING:
            self.enqueue_job(job.id)
        
        logger.info(f"✅ Created job: {job.name} ({job.id})")
        return job.id
    
    def get_job(self, job_id: str) -> Optional[Job]:
        """Get job by ID"""
        key = f"{self.KEY_PREFIX}job:{job_id}"
        data = self.redis.hgetall(key)
        if not data:
            return None
        return Job.from_dict(data)
    
    def update_job(self, job_id: str, updates: Dict) -> bool:
        """Update a job"""
        job = self.get_job(job_id)
        if not job:
            return False
        
        for key, value in updates.items():
            if hasattr(job, key):
                setattr(job, key, value)
        
        job.updated_at = datetime.now().isoformat()
        
        key = f"{self.KEY_PREFIX}job:{job_id}"
        self.redis.hset(key, mapping=job.to_dict())
        
        # Reschedule if needed
        self._reschedule_job(job)
        
        logger.info(f"✅ Updated job: {job.name}")
        return True
    
    def delete_job(self, job_id: str) -> bool:
        """Delete a job"""
        job = self.get_job(job_id)
        if not job:
            return False
        
        # Remove from queues
        self.redis.srem(f"{self.KEY_PREFIX}queue:waiting", job_id)
        self.redis.srem(f"{self.KEY_PREFIX}queue:processing", job_id)
        self.redis.zrem(f"{self.KEY_PREFIX}schedule:timeline", job_id)
        
        # Remove job data
        key = f"{self.KEY_PREFIX}job:{job_id}"
        self.redis.delete(key)
        
        # Remove from index
        self.redis.srem(f"{self.KEY_PREFIX}jobs", job_id)
        
        logger.info(f"🗑️ Deleted job: {job.name}")
        return True
    
    def list_jobs(self, status: Optional[str] = None) -> List[Job]:
        """List all jobs"""
        job_ids = self.redis.smembers(f"{self.KEY_PREFIX}jobs")
        jobs = []
        
        for job_id in job_ids:
            job = self.get_job(job_id)
            if job:
                if status and job.status != status:
                    continue
                jobs.append(job)
        
        return sorted(jobs, key=lambda j: j.created_at, reverse=True)
    
    # ========================================================================
    # Queue Operations
    # ========================================================================
    
    def enqueue_job(self, job_id: str, priority: Optional[int] = None) -> bool:
        """Add job to queue"""
        job = self.get_job(job_id)
        if not job:
            logger.error(f"Job {job_id} not found")
            return False
        
        if job.status == JobStatus.RUNNING:
            logger.warning(f"Job {job_id} is already running")
            return False
        
        # Update status
        job.status = JobStatus.QUEUED
        job.updated_at = datetime.now().isoformat()
        self._save_job(job)
        
        # Add to priority queue
        priority = priority if priority is not None else job.priority
        queue_key = f"{self.KEY_PREFIX}queue:priority:{priority}"
        self.redis.sadd(queue_key, job_id)
        self.redis.sadd(f"{self.KEY_PREFIX}queue:waiting", job_id)
        
        logger.info(f"📋 Job queued: {job.name} (Priority: {priority})")
        return True
    
    def dequeue_job(self) -> Optional[Job]:
        """Get next job from queue (priority-based)"""
        for priority in range(5):  # 0-4
            queue_key = f"{self.KEY_PREFIX}queue:priority:{priority}"
            job_ids = self.redis.smembers(queue_key)
            
            if job_ids:
                job_id = list(job_ids)[0]
                job = self.get_job(job_id)
                
                if job and job.status == JobStatus.QUEUED:
                    # Remove from queue
                    self.redis.srem(queue_key, job_id)
                    self.redis.srem(f"{self.KEY_PREFIX}queue:waiting", job_id)
                    self.redis.sadd(f"{self.KEY_PREFIX}queue:processing", job_id)
                    
                    job.status = JobStatus.RUNNING
                    job.updated_at = datetime.now().isoformat()
                    self._save_job(job)
                    
                    logger.info(f"▶️ Dequeued job: {job.name}")
                    return job
        
        return None
    
    # ========================================================================
    # Scheduling
    # ========================================================================
    
    def _schedule_job(self, job: Job):
        """Schedule a job for future execution"""
        if job.status == JobStatus.PAUSED:
            return
        
        next_run = self._calculate_next_run(job)
        if next_run:
            job.next_run = next_run.isoformat()
            self._save_job(job)
            
            # Add to sorted set
            self.redis.zadd(
                f"{self.KEY_PREFIX}schedule:timeline",
                {job.id: next_run.timestamp()}
            )
            logger.info(f"📅 Scheduled job: {job.name} at {next_run}")
    
    def _reschedule_job(self, job: Job):
        """Reschedule a job"""
        self.redis.zrem(f"{self.KEY_PREFIX}schedule:timeline", job.id)
        if job.status != JobStatus.PAUSED:
            self._schedule_job(job)
    
    def _calculate_next_run(self, job: Job) -> Optional[datetime]:
        """Calculate next run time"""
        now = datetime.now()
        config = job.schedule_config
        
        if job.schedule_type == 'once':
            return None
        
        elif job.schedule_type == 'interval':
            seconds = config.get('seconds', 0)
            minutes = config.get('minutes', 0)
            hours = config.get('hours', 0)
            days = config.get('days', 0)
            
            delta = timedelta(
                seconds=seconds,
                minutes=minutes,
                hours=hours,
                days=days
            )
            
            if job.last_run:
                return datetime.fromisoformat(job.last_run) + delta
            return now + delta
        
        elif job.schedule_type == 'cron':
            # Simple cron parsing for common patterns
            expr = config.get('expression', '*/5 * * * *')
            parts = expr.split()
            
            # Very basic cron parsing
            if len(parts) >= 5:
                minute, hour, day, month, dow = parts
                
                # Build next run time
                next_run = now.replace(second=0, microsecond=0)
                
                if hour != '*':
                    next_run = next_run.replace(hour=int(hour))
                
                if minute != '*':
                    next_run = next_run.replace(minute=int(minute))
                
                if next_run <= now:
                    next_run += timedelta(minutes=5)
                
                return next_run
            
            return now + timedelta(minutes=5)
        
        elif job.schedule_type == 'recurring':
            times = config.get('times', ['09:00', '14:00', '19:00'])
            for time_str in times:
                try:
                    hour, minute = map(int, time_str.split(':'))
                    scheduled = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                    if scheduled > now:
                        return scheduled
                except:
                    pass
            return now + timedelta(days=1)
        
        return None
    
    # ========================================================================
    # Job Execution
    # ========================================================================
    
    def _worker_loop(self, worker_id: int):
        """Worker thread"""
        logger.info(f"👷 Worker {worker_id} started")
        
        while self._running:
            try:
                job = self.dequeue_job()
                if job:
                    self._execute_job(job)
                else:
                    time.sleep(1)
            except Exception as e:
                logger.error(f"Worker {worker_id} error: {e}")
                time.sleep(5)
        
        logger.info(f"👷 Worker {worker_id} stopped")
    
    def _execute_job(self, job: Job):
        """Execute a job"""
        try:
            logger.info(f"🚀 Executing job: {job.name}")
            
            # Get handler
            handler = self._handlers.get(job.job_type)
            if not handler:
                raise ValueError(f"Unknown job type: {job.job_type}")
            
            # Execute with timeout
            result = handler(job)
            
            # Update job
            job.status = JobStatus.COMPLETED
            job.last_run = datetime.now().isoformat()
            job.result = result
            job.updated_at = datetime.now().isoformat()
            self._save_job(job)
            
            # Save result
            self._save_result(job.id, result)
            
            logger.info(f"✅ Job completed: {job.name}")
            
            # Reschedule if recurring
            if job.schedule_type != 'once' and job.status != JobStatus.PAUSED:
                self._schedule_job(job)
            
            # Remove from processing queue
            self.redis.srem(f"{self.KEY_PREFIX}queue:processing", job.id)
            
        except Exception as e:
            logger.error(f"❌ Job failed: {job.name} - {e}")
            
            # Handle retry
            if job.retry_count < job.max_retries:
                job.retry_count += 1
                job.status = JobStatus.RETRYING
                job.error = str(e)
                job.updated_at = datetime.now().isoformat()
                self._save_job(job)
                
                time.sleep(job.retry_delay)
                self.enqueue_job(job.id)
            else:
                job.status = JobStatus.FAILED
                job.error = str(e)
                job.last_run = datetime.now().isoformat()
                job.updated_at = datetime.now().isoformat()
                self._save_job(job)
                
                self.redis.srem(f"{self.KEY_PREFIX}queue:processing", job.id)
    
    # ========================================================================
    # Job Handlers
    # ========================================================================
    
    def _execute_shell(self, job: Job) -> Dict:
        """Execute shell command"""
        try:
            result = subprocess.run(
                job.command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=job.timeout,
                cwd=job.work_dir,
                env={**os.environ, **job.env}
            )
            
            return {
                'success': result.returncode == 0,
                'returncode': result.returncode,
                'stdout': result.stdout,
                'stderr': result.stderr
            }
        except subprocess.TimeoutExpired:
            return {'success': False, 'error': f"Timeout after {job.timeout}s"}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _execute_python(self, job: Job) -> Dict:
        """Execute Python script"""
        try:
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                f.write(job.command)
                temp_file = f.name
            
            result = subprocess.run(
                ['python3', temp_file],
                capture_output=True,
                text=True,
                timeout=job.timeout,
                cwd=job.work_dir,
                env={**os.environ, **job.env}
            )
            
            os.unlink(temp_file)
            
            return {
                'success': result.returncode == 0,
                'returncode': result.returncode,
                'stdout': result.stdout,
                'stderr': result.stderr
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _execute_browser(self, job: Job) -> Dict:
        """Execute browser automation using Playwright"""
        try:
            from playwright.sync_api import sync_playwright
            
            with sync_playwright() as p:
                browser = p.chromium.connect_over_cdp(
                    f"http://127.0.0.1:{job.session_port}"
                )
                
                context = browser.contexts[0] if browser.contexts else browser.new_context()
                page = context.pages[0] if context.pages else context.new_page()
                
                actions = json.loads(job.command)
                results = []
                
                for action in actions:
                    result = self._execute_browser_action(page, action)
                    results.append(result)
                
                browser.close()
                
                return {'success': True, 'results': results}
                
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _execute_browser_action(self, page, action: Dict) -> Dict:
        """Execute single browser action"""
        action_type = action.get('type')
        
        try:
            if action_type == 'navigate':
                page.goto(action['url'], timeout=action.get('timeout', 30000))
                return {'action': 'navigate', 'url': action['url']}
            
            elif action_type == 'click':
                page.click(action['selector'], timeout=action.get('timeout', 30000))
                return {'action': 'click', 'selector': action['selector']}
            
            elif action_type == 'fill':
                page.fill(action['selector'], action['value'], timeout=action.get('timeout', 30000))
                return {'action': 'fill', 'selector': action['selector']}
            
            elif action_type == 'type':
                page.type(action['selector'], action['text'], delay=action.get('delay', 100))
                return {'action': 'type', 'selector': action['selector']}
            
            elif action_type == 'wait':
                page.wait_for_timeout(action['seconds'] * 1000)
                return {'action': 'wait', 'seconds': action['seconds']}
            
            elif action_type == 'screenshot':
                path = action.get('save_to', f"screenshots/{time.time()}.png")
                page.screenshot(path=path)
                return {'action': 'screenshot', 'path': path}
            
            elif action_type == 'evaluate':
                result = page.evaluate(action['script'])
                return {'action': 'evaluate', 'result': result}
            
            elif action_type == 'get_text':
                text = page.text_content(action['selector'])
                return {'action': 'get_text', 'text': text}
            
        except Exception as e:
            return {'action': action_type, 'error': str(e)}
        
        return {}
    
    def _execute_api(self, job: Job) -> Dict:
        """Execute API request"""
        try:
            import requests
            
            config = json.loads(job.command)
            method = config.get('method', 'GET')
            url = config.get('url')
            headers = config.get('headers', {})
            params = config.get('params', {})
            data = config.get('data', {})
            
            response = requests.request(
                method=method,
                url=url,
                headers=headers,
                params=params,
                json=data if config.get('json', False) else None,
                data=data if not config.get('json', False) else None,
                timeout=job.timeout
            )
            
            return {
                'success': response.status_code < 400,
                'status_code': response.status_code,
                'body': response.text[:10000]
            }
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _execute_chrome_command(self, job: Job) -> Dict:
        """Execute Chrome session command"""
        # This integrates with your cdpv117.py
        cmd = f"python3 {os.path.expanduser('~/cdpv117.py')} {job.command}"
        return self._execute_shell(job)
    
    # ========================================================================
    # Result Management
    # ========================================================================
    
    def _save_result(self, job_id: str, result: Dict):
        """Save job result"""
        key = f"{self.KEY_PREFIX}result:{job_id}"
        self.redis.hset(key, mapping={
            'job_id': job_id,
            'timestamp': datetime.now().isoformat(),
            'result': json.dumps(result)
        })
        
        # Add to history
        self.redis.lpush(
            f"{self.KEY_PREFIX}history:{job_id}",
            json.dumps({'timestamp': datetime.now().isoformat(), 'result': result})
        )
        self.redis.ltrim(f"{self.KEY_PREFIX}history:{job_id}", 0, 99)
    
    def get_result(self, job_id: str) -> Optional[Dict]:
        """Get latest result"""
        key = f"{self.KEY_PREFIX}result:{job_id}"
        data = self.redis.hgetall(key)
        if data:
            return {
                'timestamp': data.get('timestamp'),
                'result': json.loads(data.get('result', '{}'))
            }
        return None
    
    def _save_job(self, job: Job):
        """Save job to Redis"""
        key = f"{self.KEY_PREFIX}job:{job.id}"
        self.redis.hset(key, mapping=job.to_dict())
    
    # ========================================================================
    # Lifecycle Management
    # ========================================================================
    
    def start(self, workers: int = 4):
        """Start the scheduler"""
        if self._running:
            logger.warning("Scheduler already running")
            return
        
        self._running = True
        self._max_workers = workers
        
        # Start scheduler thread
        self._scheduler_thread = threading.Thread(target=self._schedule_loop, daemon=True)
        self._scheduler_thread.start()
        
        # Start worker threads
        for i in range(workers):
            thread = threading.Thread(target=self._worker_loop, args=(i,), daemon=True)
            thread.start()
            self._workers.append(thread)
        
        logger.info(f"🚀 Scheduler started with {workers} workers")
    
    def _schedule_loop(self):
        """Background scheduler loop"""
        while self._running:
            try:
                now = time.time()
                ready_jobs = self.redis.zrangebyscore(
                    f"{self.KEY_PREFIX}schedule:timeline",
                    0, now
                )
                
                for job_id in ready_jobs:
                    self.redis.zrem(f"{self.KEY_PREFIX}schedule:timeline", job_id)
                    job = self.get_job(job_id)
                    if job and job.status != JobStatus.PAUSED:
                        self.enqueue_job(job_id)
                
                time.sleep(1)
                
            except Exception as e:
                logger.error(f"Schedule loop error: {e}")
                time.sleep(5)
    
    def shutdown(self):
        """Shutdown the scheduler"""
        if not self._running:
            return
        
        self._running = False
        
        if self._scheduler_thread:
            self._scheduler_thread.join(timeout=5)
        
        for thread in self._workers:
            thread.join(timeout=5)
        
        self._workers.clear()
        logger.info("🛑 Scheduler stopped")
    
    def get_stats(self) -> Dict:
        """Get scheduler statistics"""
        return {
            'jobs': {
                'total': self.redis.scard(f"{self.KEY_PREFIX}jobs"),
                'queued': self.redis.scard(f"{self.KEY_PREFIX}queue:waiting"),
                'processing': self.redis.scard(f"{self.KEY_PREFIX}queue:processing"),
                'scheduled': self.redis.zcard(f"{self.KEY_PREFIX}schedule:timeline"),
            },
            'workers': len([t for t in self._workers if t.is_alive()]),
            'status': 'running' if self._running else 'stopped'
        }

# ============================================================================
# CLI
# ============================================================================

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Redis Scheduler')
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # Start
    start_parser = subparsers.add_parser('start')
    start_parser.add_argument('--workers', type=int, default=2, help='Worker count')
    
    # Stop
    subparsers.add_parser('stop')
    
    # Stats
    subparsers.add_parser('stats')
    
    # Create job
    create_parser = subparsers.add_parser('create')
    create_parser.add_argument('--name', required=True, help='Job name')
    create_parser.add_argument('--type', choices=['shell', 'python', 'browser', 'api', 'chrome'], default='shell')
    create_parser.add_argument('--schedule', choices=['once', 'interval', 'cron', 'recurring'], default='once')
    create_parser.add_argument('--command', required=True, help='Command')
    create_parser.add_argument('--port', type=int, help='Chrome port (for browser jobs)')
    create_parser.add_argument('--priority', type=int, choices=range(5), default=2)
    create_parser.add_argument('--tags', help='Comma-separated tags')
    
    # List
    subparsers.add_parser('list')
    
    # Run
    run_parser = subparsers.add_parser('run')
    run_parser.add_argument('job_id', help='Job ID')
    
    # Delete
    delete_parser = subparsers.add_parser('delete')
    delete_parser.add_argument('job_id', help='Job ID')
    
    # Templates
    subparsers.add_parser('template-linkedin')
    subparsers.add_parser('template-chatbot')
    subparsers.add_parser('template-scrape')
    
    args = parser.parse_args()
    
    scheduler = RedisScheduler()
    
    if args.command == 'start':
        try:
            scheduler.start(workers=args.workers)
            print(f"✅ Scheduler started with {args.workers} workers")
            print("Press Ctrl+C to stop")
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            scheduler.shutdown()
    
    elif args.command == 'stop':
        scheduler.shutdown()
        print("✅ Scheduler stopped")
    
    elif args.command == 'stats':
        stats = scheduler.get_stats()
        print(json.dumps(stats, indent=2))
    
    elif args.command == 'create':
        job = Job(
            name=args.name,
            job_type=args.type,
            schedule_type=args.schedule,
            command=args.command,
            session_port=args.port,
            priority=args.priority,
            tags=args.tags.split(',') if args.tags else []
        )
        
        if args.schedule == 'interval':
            job.schedule_config = {'minutes': 5}
        elif args.schedule == 'cron':
            job.schedule_config = {'expression': '*/5 * * * *'}
        elif args.schedule == 'recurring':
            job.schedule_config = {'times': ['09:00', '14:00', '19:00']}
        
        job_id = scheduler.create_job(job)
        print(f"✅ Job created: {job_id}")
        print(json.dumps(job.to_dict(), indent=2))
    
    elif args.command == 'list':
        jobs = scheduler.list_jobs()
        print(f"Total jobs: {len(jobs)}")
        for job in jobs:
            print(f"  {job.id} - {job.name} ({job.status}) - {job.job_type}")
    
    elif args.command == 'run':
        if scheduler.enqueue_job(args.job_id):
            print(f"✅ Job queued: {args.job_id}")
        else:
            print(f"❌ Failed to queue job: {args.job_id}")
    
    elif args.command == 'delete':
        if scheduler.delete_job(args.job_id):
            print(f"✅ Job deleted: {args.job_id}")
        else:
            print(f"❌ Job not found: {args.job_id}")
    
    elif args.command == 'template-linkedin':
        job = Job(
            name='linkedin_applications',
            job_type='browser',
            schedule_type='interval',
            command=json.dumps([
                {'type': 'navigate', 'url': 'https://www.linkedin.com/jobs/'},
                {'type': 'wait', 'seconds': 3},
                {'type': 'click', 'selector': 'button.apply-button'},
                {'type': 'wait', 'seconds': 2},
                {'type': 'screenshot', 'save_to': 'linkedin_$(date +%Y%m%d).png'}
            ]),
            session_port=9222,
            schedule_config={'minutes': 30}
        )
        job_id = scheduler.create_job(job)
        print(f"✅ LinkedIn job created: {job_id}")
    
    elif args.command == 'template-chatbot':
        job = Job(
            name='chatbot_messages',
            job_type='browser',
            schedule_type='interval',
            command=json.dumps([
                {'type': 'navigate', 'url': 'https://web.whatsapp.com'},
                {'type': 'wait', 'seconds': 2},
                {'type': 'fill', 'selector': 'textarea', 'value': 'Hello from automation!'},
                {'type': 'click', 'selector': 'button.send'},
                {'type': 'screenshot', 'save_to': 'chat_$(date +%Y%m%d_%H%M%S).png'}
            ]),
            session_port=9222,
            schedule_config={'minutes': 15}
        )
        job_id = scheduler.create_job(job)
        print(f"✅ Chatbot job created: {job_id}")
    
    elif args.command == 'template-scrape':
        job = Job(
            name='daily_scrape',
            job_type='browser',
            schedule_type='cron',
            command=json.dumps([
                {'type': 'navigate', 'url': 'https://example.com'},
                {'type': 'wait', 'seconds': 3},
                {'type': 'evaluate', 'script': "document.querySelectorAll('body').map(el => el.textContent)"},
                {'type': 'screenshot', 'save_to': 'scrape_$(date +%Y%m%d).png'}
            ]),
            session_port=9222,
            schedule_config={'expression': '0 0 * * *'}
        )
        job_id = scheduler.create_job(job)
        print(f"✅ Scrape job created: {job_id}")

if __name__ == "__main__":
    main()
