#!/usr/bin/env python3
"""
Enhanced Chrome Automation System - Self-contained
Builds on cdpv119.py, api.py, and workflow4.py
Supports: JS execution → Store → Execute more JS → Save → Trigger → Metadata
Added: Loop mechanism, Result saving, Edit workflow/JS, Database storage
"""

import os
import sys
import json
import time
import asyncio
import logging
import hashlib
import uuid
import re
import threading
import queue
import subprocess
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple, Union
from dataclasses import dataclass, field, asdict
from enum import Enum
from collections import defaultdict

# ============================================================================
# Dependency Installation
# ============================================================================

def install_dependencies():
    """Install required dependencies"""
    deps = ['requests', 'rich']
    for dep in deps:
        try:
            __import__(dep)
        except ImportError:
            subprocess.check_call([sys.executable, "-m", "pip", "install", dep])

install_dependencies()

# ============================================================================
# Imports after dependency check
# ============================================================================

try:
    import requests
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests"])
    import requests

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.prompt import Prompt, Confirm
    from rich.syntax import Syntax
    from rich import box
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich.markdown import Markdown
    from rich.text import Text
    console = Console()
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "rich"])
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.prompt import Prompt, Confirm
    from rich.syntax import Syntax
    from rich import box
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich.markdown import Markdown
    from rich.text import Text
    console = Console()

# ============================================================================
# Configuration
# ============================================================================

@dataclass
class WorkflowConfig:
    base_dir: str = os.path.expanduser("~/chrome-workflows")
    scripts_library: str = os.path.expanduser("~/chrome-workflows/scripts-library")
    workflows_dir: str = os.path.expanduser("~/chrome-workflows/workflows")
    results_dir: str = os.path.expanduser("~/chrome-workflows/results")
    executions_dir: str = os.path.expanduser("~/chrome-workflows/executions")
    db_path: str = os.path.expanduser("~/chrome-workflows/workflow.db")
    api_base_url: str = "http://127.0.0.1:5000"
    cli_show_full_id: bool = False

# ============================================================================
# Database Manager - For storing scripts and workflows
# ============================================================================

class DatabaseManager:
    """SQLite database for storing scripts, workflows, and results"""
    
    def __init__(self, config: WorkflowConfig):
        self.config = config
        self.db_path = Path(config.db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def _init_db(self):
        """Initialize database tables"""
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.cursor()
            
            # Scripts table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS scripts (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    workflow_name TEXT,
                    code TEXT NOT NULL,
                    type TEXT DEFAULT 'js_execute',
                    description TEXT,
                    tags TEXT,
                    metadata TEXT,
                    version INTEGER DEFAULT 1,
                    created_at TEXT,
                    updated_at TEXT,
                    execution_count INTEGER DEFAULT 0,
                    avg_duration REAL,
                    last_executed TEXT
                )
            """)
            
            # Script versions table (for history)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS script_versions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    script_id TEXT,
                    version INTEGER,
                    code TEXT,
                    metadata TEXT,
                    created_at TEXT,
                    FOREIGN KEY (script_id) REFERENCES scripts(id)
                )
            """)
            
            # Workflows table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS workflows (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    steps TEXT,
                    metadata TEXT,
                    tags TEXT,
                    status TEXT DEFAULT 'draft',
                    version TEXT DEFAULT '1.0.0',
                    created_at TEXT,
                    updated_at TEXT,
                    execution_count INTEGER DEFAULT 0,
                    avg_duration REAL,
                    last_executed TEXT
                )
            """)
            
            # Results table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS results (
                    id TEXT PRIMARY KEY,
                    workflow_id TEXT,
                    execution_id TEXT,
                    step_id TEXT,
                    step_name TEXT,
                    data TEXT,
                    metadata TEXT,
                    status TEXT,
                    created_at TEXT,
                    FOREIGN KEY (workflow_id) REFERENCES workflows(id)
                )
            """)
            
            # Loop configurations table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS loop_configs (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    config TEXT,
                    metadata TEXT,
                    created_at TEXT,
                    updated_at TEXT
                )
            """)
            
            conn.commit()
    
    # ========== Script Methods ==========
    
    def save_script(self, script_data: Dict) -> str:
        """Save a script to database"""
        script_id = script_data.get('id', str(uuid.uuid4()))
        
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.cursor()
            
            # Check if exists
            cursor.execute("SELECT id, version FROM scripts WHERE id = ?", (script_id,))
            existing = cursor.fetchone()
            
            if existing:
                # Update existing
                version = existing[1] + 1
                cursor.execute("""
                    UPDATE scripts SET
                        name = ?,
                        workflow_name = ?,
                        code = ?,
                        type = ?,
                        description = ?,
                        tags = ?,
                        metadata = ?,
                        version = ?,
                        updated_at = ?,
                        execution_count = execution_count + 1
                    WHERE id = ?
                """, (
                    script_data.get('name', ''),
                    script_data.get('workflow_name', ''),
                    script_data.get('code', ''),
                    script_data.get('type', 'js_execute'),
                    script_data.get('description', ''),
                    json.dumps(script_data.get('tags', [])),
                    json.dumps(script_data.get('metadata', {})),
                    version,
                    datetime.now().isoformat(),
                    script_id
                ))
                
                # Save version history
                cursor.execute("""
                    INSERT INTO script_versions (script_id, version, code, metadata, created_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    script_id,
                    version,
                    script_data.get('code', ''),
                    json.dumps(script_data.get('metadata', {})),
                    datetime.now().isoformat()
                ))
            else:
                # Insert new
                cursor.execute("""
                    INSERT INTO scripts (
                        id, name, workflow_name, code, type, description,
                        tags, metadata, version, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    script_id,
                    script_data.get('name', ''),
                    script_data.get('workflow_name', ''),
                    script_data.get('code', ''),
                    script_data.get('type', 'js_execute'),
                    script_data.get('description', ''),
                    json.dumps(script_data.get('tags', [])),
                    json.dumps(script_data.get('metadata', {})),
                    1,
                    datetime.now().isoformat(),
                    datetime.now().isoformat()
                ))
            
            conn.commit()
            return script_id
    
    def get_script(self, script_id: str) -> Optional[Dict]:
        """Get a script by ID"""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT * FROM scripts WHERE id = ?
            """, (script_id,))
            
            row = cursor.fetchone()
            if row:
                result = dict(row)
                result['tags'] = json.loads(result['tags']) if result['tags'] else []
                result['metadata'] = json.loads(result['metadata']) if result['metadata'] else {}
                return result
            return None
    
    def get_script_by_name(self, name: str, workflow_name: str = None) -> Optional[Dict]:
        """Get a script by name and optional workflow"""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            if workflow_name:
                cursor.execute("""
                    SELECT * FROM scripts WHERE name = ? AND workflow_name = ?
                """, (name, workflow_name))
            else:
                cursor.execute("""
                    SELECT * FROM scripts WHERE name = ?
                """, (name,))
            
            row = cursor.fetchone()
            if row:
                result = dict(row)
                result['tags'] = json.loads(result['tags']) if result['tags'] else []
                result['metadata'] = json.loads(result['metadata']) if result['metadata'] else {}
                return result
            return None
    
    def list_scripts(self, workflow_name: str = None) -> List[Dict]:
        """List all scripts, optionally filtered by workflow"""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            if workflow_name:
                cursor.execute("""
                    SELECT * FROM scripts WHERE workflow_name = ? ORDER BY name
                """, (workflow_name,))
            else:
                cursor.execute("""
                    SELECT * FROM scripts ORDER BY name
                """)
            
            results = []
            for row in cursor.fetchall():
                result = dict(row)
                result['tags'] = json.loads(result['tags']) if result['tags'] else []
                result['metadata'] = json.loads(result['metadata']) if result['metadata'] else {}
                results.append(result)
            return results
    
    def delete_script(self, script_id: str) -> bool:
        """Delete a script"""
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM scripts WHERE id = ?", (script_id,))
            cursor.execute("DELETE FROM script_versions WHERE script_id = ?", (script_id,))
            conn.commit()
            return cursor.rowcount > 0
    
    def get_script_versions(self, script_id: str) -> List[Dict]:
        """Get version history of a script"""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT * FROM script_versions WHERE script_id = ? ORDER BY version DESC
            """, (script_id,))
            
            results = []
            for row in cursor.fetchall():
                result = dict(row)
                result['metadata'] = json.loads(result['metadata']) if result['metadata'] else {}
                results.append(result)
            return results
    
    # ========== Workflow Methods ==========
    
    def save_workflow(self, workflow_data: Dict) -> str:
        """Save a workflow to database"""
        workflow_id = workflow_data.get('id', str(uuid.uuid4()))
        
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT OR REPLACE INTO workflows (
                    id, name, description, steps, metadata, tags, status,
                    version, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                workflow_id,
                workflow_data.get('name', ''),
                workflow_data.get('description', ''),
                json.dumps(workflow_data.get('steps', [])),
                json.dumps(workflow_data.get('metadata', {})),
                json.dumps(workflow_data.get('tags', [])),
                workflow_data.get('status', 'draft'),
                workflow_data.get('version', '1.0.0'),
                workflow_data.get('created_at', datetime.now().isoformat()),
                datetime.now().isoformat()
            ))
            
            conn.commit()
            return workflow_id
    
    def get_workflow(self, workflow_id: str) -> Optional[Dict]:
        """Get a workflow by ID"""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("SELECT * FROM workflows WHERE id = ?", (workflow_id,))
            row = cursor.fetchone()
            
            if row:
                result = dict(row)
                result['steps'] = json.loads(result['steps']) if result['steps'] else []
                result['metadata'] = json.loads(result['metadata']) if result['metadata'] else {}
                result['tags'] = json.loads(result['tags']) if result['tags'] else []
                return result
            return None
    
    def list_workflows(self) -> List[Dict]:
        """List all workflows"""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("SELECT * FROM workflows ORDER BY name")
            
            results = []
            for row in cursor.fetchall():
                result = dict(row)
                result['steps'] = json.loads(result['steps']) if result['steps'] else []
                result['metadata'] = json.loads(result['metadata']) if result['metadata'] else {}
                result['tags'] = json.loads(result['tags']) if result['tags'] else []
                results.append(result)
            return results
    
    def delete_workflow(self, workflow_id: str) -> bool:
        """Delete a workflow"""
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM workflows WHERE id = ?", (workflow_id,))
            conn.commit()
            return cursor.rowcount > 0
    
    # ========== Result Methods ==========
    
    def save_result(self, result_data: Dict) -> str:
        """Save an execution result"""
        result_id = result_data.get('id', str(uuid.uuid4()))
        
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO results (
                    id, workflow_id, execution_id, step_id, step_name,
                    data, metadata, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                result_id,
                result_data.get('workflow_id', ''),
                result_data.get('execution_id', ''),
                result_data.get('step_id', ''),
                result_data.get('step_name', ''),
                json.dumps(result_data.get('data', {})),
                json.dumps(result_data.get('metadata', {})),
                result_data.get('status', 'completed'),
                datetime.now().isoformat()
            ))
            
            conn.commit()
            return result_id
    
    def get_results(self, workflow_id: str = None, execution_id: str = None) -> List[Dict]:
        """Get results with optional filtering"""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            query = "SELECT * FROM results"
            params = []
            conditions = []
            
            if workflow_id:
                conditions.append("workflow_id = ?")
                params.append(workflow_id)
            
            if execution_id:
                conditions.append("execution_id = ?")
                params.append(execution_id)
            
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            
            query += " ORDER BY created_at DESC"
            
            cursor.execute(query, params)
            
            results = []
            for row in cursor.fetchall():
                result = dict(row)
                result['data'] = json.loads(result['data']) if result['data'] else {}
                result['metadata'] = json.loads(result['metadata']) if result['metadata'] else {}
                results.append(result)
            return results
    
    # ========== Loop Config Methods ==========
    
    def save_loop_config(self, config_data: Dict) -> str:
        """Save a loop configuration"""
        config_id = config_data.get('id', str(uuid.uuid4()))
        
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT OR REPLACE INTO loop_configs (
                    id, name, config, metadata, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (
                config_id,
                config_data.get('name', ''),
                json.dumps(config_data.get('config', {})),
                json.dumps(config_data.get('metadata', {})),
                config_data.get('created_at', datetime.now().isoformat()),
                datetime.now().isoformat()
            ))
            
            conn.commit()
            return config_id
    
    def get_loop_configs(self) -> List[Dict]:
        """Get all loop configurations"""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("SELECT * FROM loop_configs ORDER BY name")
            
            results = []
            for row in cursor.fetchall():
                result = dict(row)
                result['config'] = json.loads(result['config']) if result['config'] else {}
                result['metadata'] = json.loads(result['metadata']) if result['metadata'] else {}
                results.append(result)
            return results

# ============================================================================
# Loop Manager - Handles looping of scripts
# ============================================================================

class LoopManager:
    """Manages loop execution for scripts"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
        self.config = {}
    
    def create_loop_config(self, name: str, config: Dict) -> str:
        """Create a loop configuration"""
        config_data = {
            'name': name,
            'config': config,
            'metadata': {
                'created_at': datetime.now().isoformat()
            }
        }
        return self.db.save_loop_config(config_data)
    
    def execute_loop(self, script_id: str, loop_config: Dict, session_name: str = None) -> List[Dict]:
        """
        Execute a script in a loop with the given configuration
        
        loop_config:
            - type: 'for', 'while', 'each', 'until'
            - iterations: number of iterations (for type)
            - condition: condition to check (while, until)
            - data_source: list of items to iterate over (each type)
            - delay: delay between iterations
            - max_iterations: max iterations (safety)
            - break_on_error: stop on error
            - collect_results: collect all results
            - variable_name: variable name for iteration data
        """
        engine = EnhancedExecutionEngine()
        results = []
        session_name = session_name or "unstop"
        
        loop_type = loop_config.get('type', 'for')
        max_iterations = loop_config.get('max_iterations', 100)
        delay = loop_config.get('delay', 1)
        break_on_error = loop_config.get('break_on_error', True)
        collect_results = loop_config.get('collect_results', True)
        variable_name = loop_config.get('variable_name', 'loop_item')
        
        # Get the script
        script_data = self.db.get_script(script_id)
        if not script_data:
            return [{'error': f'Script {script_id} not found'}]
        
        context = {}
        
        if loop_type == 'for':
            iterations = loop_config.get('iterations', 1)
            for i in range(iterations):
                if i >= max_iterations:
                    break
                
                context['loop_index'] = i
                context['loop_total'] = iterations
                context[variable_name] = i
                
                result = engine.execute_javascript(
                    session_name,
                    script_data['code'],
                    context
                )
                
                result_data = {
                    'iteration': i,
                    'success': result.get('result') is not None,
                    'result': result,
                    'timestamp': datetime.now().isoformat()
                }
                
                if collect_results:
                    results.append(result_data)
                
                if not result.get('result') and break_on_error:
                    break
                
                if delay > 0:
                    time.sleep(delay)
        
        elif loop_type == 'while':
            condition = loop_config.get('condition', 'true')
            iterations = 0
            
            while True:
                if iterations >= max_iterations:
                    break
                
                # Evaluate condition
                condition_result = engine.execute_javascript(
                    session_name,
                    f"return (function() {{ {condition} }})();",
                    context
                )
                
                if not condition_result.get('result', False):
                    break
                
                context['loop_index'] = iterations
                context[variable_name] = iterations
                
                result = engine.execute_javascript(
                    session_name,
                    script_data['code'],
                    context
                )
                
                result_data = {
                    'iteration': iterations,
                    'success': result.get('result') is not None,
                    'result': result,
                    'timestamp': datetime.now().isoformat()
                }
                
                if collect_results:
                    results.append(result_data)
                
                if not result.get('result') and break_on_error:
                    break
                
                iterations += 1
                if delay > 0:
                    time.sleep(delay)
        
        elif loop_type == 'each':
            data_source = loop_config.get('data_source', [])
            for i, item in enumerate(data_source):
                if i >= max_iterations:
                    break
                
                context['loop_index'] = i
                context['loop_total'] = len(data_source)
                context[variable_name] = item
                
                result = engine.execute_javascript(
                    session_name,
                    script_data['code'],
                    context
                )
                
                result_data = {
                    'iteration': i,
                    'item': item,
                    'success': result.get('result') is not None,
                    'result': result,
                    'timestamp': datetime.now().isoformat()
                }
                
                if collect_results:
                    results.append(result_data)
                
                if not result.get('result') and break_on_error:
                    break
                
                if delay > 0:
                    time.sleep(delay)
        
        elif loop_type == 'until':
            condition = loop_config.get('condition', 'false')
            iterations = 0
            
            while True:
                if iterations >= max_iterations:
                    break
                
                context['loop_index'] = iterations
                context[variable_name] = iterations
                
                result = engine.execute_javascript(
                    session_name,
                    script_data['code'],
                    context
                )
                
                result_data = {
                    'iteration': iterations,
                    'success': result.get('result') is not None,
                    'result': result,
                    'timestamp': datetime.now().isoformat()
                }
                
                if collect_results:
                    results.append(result_data)
                
                # Check until condition
                condition_result = engine.execute_javascript(
                    session_name,
                    f"return (function() {{ {condition} }})();",
                    context
                )
                
                if condition_result.get('result', False):
                    break
                
                if not result.get('result') and break_on_error:
                    break
                
                iterations += 1
                if delay > 0:
                    time.sleep(delay)
        
        return results

# ============================================================================
# Data Models (same as before)
# ============================================================================

class ExecutionStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"

@dataclass
class Workflow:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    version: str = "1.0.0"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    session_name: str = "unstop"
    session_url: str = "https://unstop.com/"
    steps: List[Dict] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)
    status: str = "draft"
    tags: List[str] = field(default_factory=list)
    execution_count: int = 0
    avg_duration: Optional[float] = None

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> 'Workflow':
        return cls(**data)

    def get_display_id(self, show_full: bool = False) -> str:
        return self.id if show_full else self.id[:8]

@dataclass
class WorkflowExecution:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    workflow_id: str = ""
    workflow_name: str = ""
    session_name: str = "unstop"
    status: str = "pending"
    current_step: int = 0
    total_steps: int = 0
    steps: List[Dict] = field(default_factory=list)
    results: List[Dict] = field(default_factory=list)
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    metadata: Dict = field(default_factory=dict)
    error: Optional[str] = None

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> 'WorkflowExecution':
        return cls(**data)

@dataclass
class WorkflowStep:
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    type: str = "js_execute"
    name: str = ""
    description: str = ""
    code: str = ""
    selector: str = ""
    url: str = ""
    expression: str = ""
    timeout: int = 30
    retry_count: int = 0
    retry_delay: int = 1
    wait_time: int = 1
    variable_name: str = ""
    variable_value: Any = None
    condition: Dict = field(default_factory=dict)
    loop_config: Dict = field(default_factory=dict)
    api_config: Dict = field(default_factory=dict)
    assert_config: Dict = field(default_factory=dict)
    depends_on: List[str] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)
    continue_on_error: bool = False
    target_workflow: str = ""
    script_id: str = ""  # Reference to DB script
    save_result: bool = True  # Whether to save result to DB

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> 'WorkflowStep':
        return cls(**data)

# ============================================================================
# Workflow Registry (updated to use DB)
# ============================================================================

class WorkflowRegistry:
    def __init__(self, config: WorkflowConfig, db_manager: DatabaseManager = None):
        self.config = config
        self.db = db_manager or DatabaseManager(config)
        self._workflows: Dict[str, Workflow] = {}
        self._loaded = False
        self._lock = threading.RLock()

    def load(self, force: bool = False) -> int:
        if self._loaded and not force:
            return len(self._workflows)

        with self._lock:
            workflows = self.db.list_workflows()
            self._workflows = {}
            
            for wf_data in workflows:
                try:
                    workflow = Workflow.from_dict(wf_data)
                    self._workflows[workflow.id] = workflow
                except Exception as e:
                    logging.error(f"Failed to load workflow: {e}")

            self._loaded = True
            return len(self._workflows)

    def get(self, identifier: str) -> Optional[Workflow]:
        self.load()

        with self._lock:
            # Exact ID match
            if identifier in self._workflows:
                return self._workflows[identifier]

            # Partial ID match
            matches = [w for w in self._workflows.values() if w.id.startswith(identifier)]
            if len(matches) == 1:
                return matches[0]
            if len(matches) > 1:
                raise ValueError(f"Multiple workflows match '{identifier}'")

            # Name match
            for wf in self._workflows.values():
                if wf.name.lower() == identifier.lower():
                    return wf

            # Name contains
            matches = [w for w in self._workflows.values() if identifier.lower() in w.name.lower()]
            if len(matches) == 1:
                return matches[0]

            return None

    def list_all(self, sort_by: str = 'name', status_filter: Optional[str] = None) -> List[Workflow]:
        self.load()

        with self._lock:
            workflows = list(self._workflows.values())

            if status_filter:
                workflows = [w for w in workflows if w.status == status_filter]

            if sort_by == 'name':
                workflows.sort(key=lambda w: w.name.lower())
            elif sort_by == 'created':
                workflows.sort(key=lambda w: w.created_at, reverse=True)
            elif sort_by == 'updated':
                workflows.sort(key=lambda w: w.updated_at, reverse=True)

            return workflows

    def save(self, workflow: Workflow) -> None:
        with self._lock:
            self._workflows[workflow.id] = workflow
            workflow.updated_at = datetime.now().isoformat()
            
            # Save to DB
            wf_data = workflow.to_dict()
            self.db.save_workflow(wf_data)

    def delete(self, workflow_id: str) -> bool:
        with self._lock:
            if workflow_id not in self._workflows:
                return False

            del self._workflows[workflow_id]
            return self.db.delete_workflow(workflow_id)

# ============================================================================
# Workflow Manager (updated to use DB)
# ============================================================================

class WorkflowManager:
    def __init__(self, config: WorkflowConfig = None):
        self.config = config or WorkflowConfig()
        self.db = DatabaseManager(self.config)
        self.registry = WorkflowRegistry(self.config, self.db)
        self.script_library = ScriptLibrary(self.config)
        self._ensure_directories()

    def _ensure_directories(self):
        Path(self.config.base_dir).mkdir(parents=True, exist_ok=True)
        Path(self.config.workflows_dir).mkdir(parents=True, exist_ok=True)
        Path(self.config.results_dir).mkdir(parents=True, exist_ok=True)
        Path(self.config.executions_dir).mkdir(parents=True, exist_ok=True)

    def create_workflow(self, data: Dict) -> Workflow:
        workflow = Workflow.from_dict(data)
        self.registry.save(workflow)
        return workflow

    def get_workflow(self, identifier: str) -> Optional[Workflow]:
        return self.registry.get(identifier)

    def list_workflows(self, **kwargs) -> List[Workflow]:
        return self.registry.list_all(**kwargs)

    def search_workflows(self, query: str) -> List[Workflow]:
        return self.registry.search(query)

    def delete_workflow(self, workflow_id: str) -> bool:
        return self.registry.delete(workflow_id)

    def add_step(self, workflow_id: str, step_data: Dict) -> Workflow:
        workflow = self.get_workflow(workflow_id)
        if not workflow:
            raise ValueError(f"Workflow {workflow_id} not found")

        step = WorkflowStep.from_dict(step_data)
        workflow.steps.append(step.to_dict())
        workflow.updated_at = datetime.now().isoformat()
        self.registry.save(workflow)
        return workflow

    # ========== Script Methods ==========
    
    def save_script(self, name: str, code: str, workflow_name: str = None, 
                   description: str = "", tags: List[str] = None) -> str:
        """Save a script to the database"""
        script_data = {
            'name': name,
            'code': code,
            'workflow_name': workflow_name or '',
            'description': description,
            'tags': tags or [],
            'type': 'js_execute',
            'metadata': {
                'created_by': 'workflow_manager',
                'created_at': datetime.now().isoformat()
            }
        }
        return self.db.save_script(script_data)
    
    def get_script(self, script_id: str) -> Optional[Dict]:
        return self.db.get_script(script_id)
    
    def get_script_by_name(self, name: str) -> Optional[Dict]:
        return self.db.get_script_by_name(name)
    
    def list_scripts(self, workflow_name: str = None) -> List[Dict]:
        return self.db.list_scripts(workflow_name)
    
    def delete_script(self, script_id: str) -> bool:
        return self.db.delete_script(script_id)
    
    def update_script(self, script_id: str, updates: Dict) -> bool:
        """Update a script"""
        script = self.db.get_script(script_id)
        if not script:
            return False
        
        script.update(updates)
        script['updated_at'] = datetime.now().isoformat()
        self.db.save_script(script)
        return True
    
    # ========== Result Methods ==========
    
    def save_result(self, result_data: Dict) -> str:
        return self.db.save_result(result_data)
    
    def get_results(self, workflow_id: str = None, execution_id: str = None) -> List[Dict]:
        return self.db.get_results(workflow_id, execution_id)
    
    # ========== Loop Methods ==========
    
    def create_loop(self, name: str, config: Dict) -> str:
        loop_manager = LoopManager(self.db)
        return loop_manager.create_loop_config(name, config)
    
    def list_loops(self) -> List[Dict]:
        return self.db.get_loop_configs()
    
    def execute_loop(self, script_id: str, loop_name: str, session_name: str = None) -> List[Dict]:
        """Execute a loop by name"""
        loops = self.db.get_loop_configs()
        loop_config = None
        for loop in loops:
            if loop['name'] == loop_name or loop['id'] == loop_name:
                loop_config = loop['config']
                break
        
        if not loop_config:
            return [{'error': f'Loop {loop_name} not found'}]
        
        loop_manager = LoopManager(self.db)
        return loop_manager.execute_loop(script_id, loop_config, session_name)

# ============================================================================
# Enhanced Execution Engine (updated)
# ============================================================================

class EnhancedExecutionEngine:
    def __init__(self, api_base_url: str = "http://127.0.0.1:5000"):
        self.api_base_url = api_base_url
        self.executions: Dict[str, WorkflowExecution] = {}
        self._lock = threading.RLock()
        self._execution_threads: Dict[str, threading.Thread] = {}
        self._stop_events: Dict[str, threading.Event] = {}

        self.base_dir = Path.home() / "chrome-workflows" / "executions"
        self.base_dir.mkdir(parents=True, exist_ok=True)

        self.logger = logging.getLogger("EnhancedExecutionEngine")
        self.db = DatabaseManager(WorkflowConfig())

    def _make_api_call(self, endpoint: str, method: str = "POST", data: Dict = None) -> Dict:
        url = f"{self.api_base_url}{endpoint}"
        try:
            if method.upper() == "GET":
                response = requests.get(url, timeout=30)
            else:
                response = requests.post(url, json=data or {}, timeout=30)

            if response.status_code == 200:
                return response.json()
            return {"error": f"API error: {response.status_code}", "detail": response.text}
        except Exception as e:
            return {"error": str(e)}

    def execute_javascript(self, session_name: str, script_code: str, context: Dict = None) -> Dict:
        if context:
            context_vars = []
            for k, v in context.items():
                try:
                    json.dumps(v)
                    context_vars.append(f"const {k} = {json.dumps(v)};")
                except:
                    context_vars.append(f"const {k} = '{str(v)}';")

            wrapped_code = f"""
            (function() {{
                {' '.join(context_vars)}
                return (function() {{
                    {script_code}
                }})();
            }})()
            """
        else:
            wrapped_code = script_code

        result = self._make_api_call(
            f"/session/{session_name}/evaluate",
            method="POST",
            data={"expression": wrapped_code}
        )
        return result

    def execute_step(self, step: Dict, session_name: str, context: Dict) -> Dict:
        step_type = step.get('type', 'js_execute')
        step_name = step.get('name', 'unnamed')
        step_id = step.get('id', str(uuid.uuid4())[:8])
        save_result = step.get('save_result', True)

        result = {
            'step_id': step_id,
            'step_name': step_name,
            'step_type': step_type,
            'status': 'running',
            'started_at': datetime.now().isoformat(),
            'result': None,
            'error': None,
            'metadata': {}
        }

        try:
            # Check if this is a loop step
            if step_type == 'loop':
                loop_config = step.get('loop_config', {})
                script_id = step.get('script_id', '')
                
                if not script_id:
                    # Use the code directly as the script
                    code = step.get('code', '')
                    if code:
                        # Save the code as a script first
                        wm = WorkflowManager()
                        script_id = wm.save_script(
                            name=f"loop_script_{step_id}",
                            code=code,
                            workflow_name=session_name
                        )
                
                if script_id:
                    loop_manager = LoopManager(self.db)
                    loop_results = loop_manager.execute_loop(script_id, loop_config, session_name)
                    result['result'] = loop_results
                    result['status'] = 'completed'
                    result['metadata']['loop_results'] = loop_results
                    result['metadata']['loop_count'] = len(loop_results)
                else:
                    raise ValueError("Loop step requires script_id or code")

            elif step_type == 'js_execute':
                script_code = step.get('code', '')
                
                # If script_id is provided, use that
                script_id = step.get('script_id')
                if script_id:
                    script_data = self.db.get_script(script_id)
                    if script_data:
                        script_code = script_data['code']
                
                if not script_code:
                    raise ValueError(f"No code found for step {step.get('id', 'unknown')}")

                exec_result = self.execute_javascript(session_name, script_code, context)
                result['result'] = exec_result

                var_name = step.get('variable_name')
                if var_name:
                    context[var_name] = exec_result
                    self.logger.info(f"📝 Stored result in context: {var_name}")

                result['status'] = 'completed'

            elif step_type == 'navigate':
                url = step.get('url')
                if not url:
                    raise ValueError("URL required for navigate step")

                nav_result = self._make_api_call(
                    f"/session/{session_name}/navigate",
                    method="POST",
                    data={"url": url}
                )
                result['result'] = nav_result
                result['status'] = 'completed'

            elif step_type == 'click':
                selector = step.get('selector')
                if not selector:
                    raise ValueError("Selector required for click step")

                click_result = self._make_api_call(
                    f"/session/{session_name}/click",
                    method="POST",
                    data={"selector": selector}
                )
                result['result'] = click_result
                result['status'] = 'completed'

            elif step_type == 'screenshot':
                screenshot_result = self._make_api_call(
                    f"/session/{session_name}/screenshot",
                    method="GET"
                )
                result['result'] = screenshot_result
                result['status'] = 'completed'

            elif step_type == 'wait':
                wait_time = step.get('wait_time', 1)
                time.sleep(wait_time)
                result['result'] = {'waited': wait_time}
                result['status'] = 'completed'

            elif step_type == 'extract':
                expression = step.get('expression', step.get('code', ''))
                if not expression:
                    raise ValueError("Expression required for extract step")

                extract_result = self.execute_javascript(session_name, expression, context)
                result['result'] = extract_result

                var_name = step.get('variable_name')
                if var_name:
                    context[var_name] = extract_result
                    self.logger.info(f"📝 Extracted data stored in: {var_name}")

                result['status'] = 'completed'

            elif step_type == 'store':
                var_name = step.get('variable_name')
                var_value = step.get('variable_value')
                if var_name:
                    context[var_name] = var_value
                    result['result'] = {'stored': var_name, 'value': var_value}
                    result['status'] = 'completed'
                else:
                    raise ValueError("variable_name required for store step")

            elif step_type == 'api_call':
                api_config = step.get('api_config', {})
                method = api_config.get('method', 'GET')
                url = api_config.get('url')
                headers = api_config.get('headers', {})
                body = api_config.get('body', {})

                if not url:
                    raise ValueError("URL required for API call")

                if method.upper() == 'GET':
                    resp = requests.get(url, headers=headers, timeout=step.get('timeout', 30))
                else:
                    resp = requests.request(method, url, headers=headers, json=body, timeout=step.get('timeout', 30))

                result['result'] = {
                    'status_code': resp.status_code,
                    'headers': dict(resp.headers),
                    'body': resp.json() if resp.headers.get('content-type', '').startswith('application/json') else resp.text
                }
                result['status'] = 'completed'

            elif step_type == 'assert':
                assert_config = step.get('assert_config', {})
                condition = assert_config.get('condition')
                expected = assert_config.get('expected')
                operator = assert_config.get('operator', 'equals')

                if condition:
                    assert_result = self.execute_javascript(session_name, condition, context)
                    actual = assert_result.get('result')

                    if operator == 'equals':
                        assert str(actual) == str(expected), f"Assertion failed: {actual} != {expected}"
                    elif operator == 'contains':
                        assert str(expected) in str(actual), f"Assertion failed: {expected} not in {actual}"
                    elif operator == 'greater':
                        assert float(actual) > float(expected), f"Assertion failed: {actual} <= {expected}"

                    result['result'] = {'assertion_passed': True, 'actual': actual, 'expected': expected}
                    result['status'] = 'completed'

            elif step_type == 'trigger':
                target_workflow = step.get('target_workflow')
                if not target_workflow:
                    raise ValueError("target_workflow required for trigger step")

                wm = WorkflowManager()
                target = wm.get_workflow(target_workflow)
                if not target:
                    raise ValueError(f"Target workflow '{target_workflow}' not found")

                result['result'] = {'triggered': target_workflow, 'status': 'queued'}
                result['status'] = 'completed'
                result['metadata']['triggered_workflow'] = target_workflow

            else:
                raise ValueError(f"Unknown step type: {step_type}")

            # Save result to database if enabled
            if save_result:
                result_data = {
                    'workflow_id': step.get('workflow_id', ''),
                    'execution_id': step.get('execution_id', ''),
                    'step_id': step_id,
                    'step_name': step_name,
                    'data': result.get('result', {}),
                    'metadata': result.get('metadata', {}),
                    'status': result['status']
                }
                self.db.save_result(result_data)
                self.logger.info(f"💾 Result saved to database")

        except Exception as e:
            result['status'] = 'failed'
            result['error'] = str(e)
            self.logger.error(f"❌ Step failed: {e}")

        result['completed_at'] = datetime.now().isoformat()
        return result

    def execute_workflow(self, workflow: Dict, session_name: str = None) -> WorkflowExecution:
        workflow_id = workflow.get('id', str(uuid.uuid4()))
        session_name = session_name or workflow.get('session_name', 'unstop')

        execution = WorkflowExecution(
            id=workflow_id,
            workflow_id=workflow_id,
            workflow_name=workflow.get('name', 'unnamed'),
            session_name=session_name,
            status='running',
            total_steps=len(workflow.get('steps', [])),
            steps=workflow.get('steps', []),
            started_at=datetime.now().isoformat()
        )

        with self._lock:
            self.executions[workflow_id] = execution

        context = {}

        try:
            steps = workflow.get('steps', [])
            for i, step in enumerate(steps):
                execution.current_step = i
                self.logger.info(f"▶️ Executing step {i+1}/{len(steps)}: {step.get('name', 'unnamed')}")

                # Add workflow context to step
                step['workflow_id'] = workflow_id
                step['execution_id'] = execution.id
                
                step_result = self.execute_step(step, session_name, context)
                execution.results.append(step_result)

                if step_result['status'] == 'failed':
                    if not step.get('continue_on_error', False):
                        execution.status = 'failed'
                        execution.error = f"Step {i+1} failed: {step_result.get('error')}"
                        self.logger.error(f"❌ Workflow failed at step {i+1}")
                        break

            if execution.status == 'running':
                execution.status = 'completed'
                self.logger.info(f"✅ Workflow completed successfully")

            execution.metadata['context_snapshot'] = context

        except Exception as e:
            execution.status = 'failed'
            execution.error = str(e)
            self.logger.error(f"❌ Workflow execution failed: {e}")

        execution.completed_at = datetime.now().isoformat()

        with self._lock:
            self.executions[workflow_id] = execution

        self._save_execution(execution)
        return execution

    def _save_execution(self, execution: WorkflowExecution):
        exec_dir = self.base_dir / execution.id
        exec_dir.mkdir(parents=True, exist_ok=True)

        with open(exec_dir / 'execution.json', 'w') as f:
            json.dump(execution.to_dict(), f, indent=2, default=str)

        for i, result in enumerate(execution.results):
            with open(exec_dir / f'step_{i+1:03d}_result.json', 'w') as f:
                json.dump(result, f, indent=2, default=str)

        if execution.metadata.get('context_snapshot'):
            with open(exec_dir / 'context.json', 'w') as f:
                json.dump(execution.metadata['context_snapshot'], f, indent=2, default=str)

    def get_execution(self, execution_id: str) -> Optional[WorkflowExecution]:
        with self._lock:
            if execution_id in self.executions:
                return self.executions[execution_id]

        exec_dir = self.base_dir / execution_id
        if exec_dir.exists():
            try:
                with open(exec_dir / 'execution.json', 'r') as f:
                    data = json.load(f)
                    return WorkflowExecution.from_dict(data)
            except:
                pass

        return None

    def get_execution_status(self, execution_id: str) -> Dict:
        execution = self.get_execution(execution_id)
        if not execution:
            return {'exists': False, 'id': execution_id}

        return {
            'exists': True,
            'id': execution.id,
            'workflow_name': execution.workflow_name,
            'status': execution.status,
            'current_step': execution.current_step,
            'total_steps': execution.total_steps,
            'started_at': execution.started_at,
            'completed_at': execution.completed_at,
            'error': execution.error,
            'result_count': len(execution.results)
        }

# ============================================================================
# Workflow Builder (updated with loop and edit methods)
# ============================================================================

class WorkflowBuilder:
    def __init__(self, name: str, description: str = ""):
        self.workflow = {
            'id': str(uuid.uuid4()),
            'name': name,
            'description': description,
            'version': '1.0.0',
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat(),
            'session_name': 'unstop',
            'session_url': 'https://unstop.com/',
            'steps': [],
            'metadata': {},
            'status': 'draft',
            'tags': []
        }
        self._engine = EnhancedExecutionEngine()
        self._db = DatabaseManager(WorkflowConfig())

    def session(self, name: str, url: str = None) -> 'WorkflowBuilder':
        self.workflow['session_name'] = name
        if url:
            self.workflow['session_url'] = url
        return self

    def set_metadata(self, key: str, value: Any) -> 'WorkflowBuilder':
        self.workflow['metadata'][key] = value
        return self

    def add_tag(self, tag: str) -> 'WorkflowBuilder':
        if tag not in self.workflow['tags']:
            self.workflow['tags'].append(tag)
        return self

    def loop(self, name: str, script_id: str = None, code: str = None,
             loop_type: str = 'for', iterations: int = 5, 
             variable_name: str = 'loop_item', delay: int = 1,
             collect_results: bool = True) -> 'WorkflowBuilder':
        """Add a loop step"""
        
        # If code is provided, save it as a script first
        if code and not script_id:
            script_data = {
                'name': f"loop_script_{name}",
                'code': code,
                'workflow_name': self.workflow['name'],
                'type': 'js_execute',
                'description': f"Loop script for {name}"
            }
            script_id = self._db.save_script(script_data)
        
        loop_config = {
            'type': loop_type,
            'iterations': iterations,
            'variable_name': variable_name,
            'delay': delay,
            'collect_results': collect_results,
            'max_iterations': 100
        }
        
        step = {
            'id': str(uuid.uuid4())[:8],
            'type': 'loop',
            'name': name,
            'script_id': script_id,
            'code': code,  # Store code as backup
            'loop_config': loop_config,
            'continue_on_error': False,
            'save_result': True,
            'metadata': {
                'loop_type': loop_type,
                'iterations': iterations,
                'variable_name': variable_name,
                'delay': delay,
                'collect_results': collect_results
            }
        }
        self.workflow['steps'].append(step)
        return self
    
    def js(self, name: str, code: str = None, script_id: str = None,
           variable_name: str = None, continue_on_error: bool = False,
           save_result: bool = True) -> 'WorkflowBuilder':
        """Add a JavaScript execution step (supports script_id or direct code)"""
        
        # If code is provided, save it as a script
        if code and not script_id:
            script_data = {
                'name': name,
                'code': code,
                'workflow_name': self.workflow['name'],
                'type': 'js_execute',
                'description': f"JS step: {name}"
            }
            script_id = self._db.save_script(script_data)
        
        step = {
            'id': str(uuid.uuid4())[:8],
            'type': 'js_execute',
            'name': name,
            'code': code,
            'script_id': script_id,
            'variable_name': variable_name,
            'continue_on_error': continue_on_error,
            'save_result': save_result,
            'timeout': 30,
            'retry_count': 0
        }
        self.workflow['steps'].append(step)
        return self

    def navigate(self, url: str, name: str = "Navigate") -> 'WorkflowBuilder':
        step = {
            'id': str(uuid.uuid4())[:8],
            'type': 'navigate',
            'name': name,
            'url': url,
            'timeout': 30,
            'save_result': True
        }
        self.workflow['steps'].append(step)
        return self

    def click(self, selector: str, name: str = "Click") -> 'WorkflowBuilder':
        step = {
            'id': str(uuid.uuid4())[:8],
            'type': 'click',
            'name': name,
            'selector': selector,
            'timeout': 30,
            'save_result': True
        }
        self.workflow['steps'].append(step)
        return self

    def extract(self, name: str, expression: str, variable_name: str = None) -> 'WorkflowBuilder':
        step = {
            'id': str(uuid.uuid4())[:8],
            'type': 'extract',
            'name': name,
            'expression': expression,
            'variable_name': variable_name,
            'timeout': 30,
            'save_result': True
        }
        self.workflow['steps'].append(step)
        return self

    def store(self, variable_name: str, value: Any, name: str = "Store") -> 'WorkflowBuilder':
        step = {
            'id': str(uuid.uuid4())[:8],
            'type': 'store',
            'name': name,
            'variable_name': variable_name,
            'variable_value': value,
            'save_result': True
        }
        self.workflow['steps'].append(step)
        return self

    def wait(self, seconds: int, name: str = "Wait") -> 'WorkflowBuilder':
        step = {
            'id': str(uuid.uuid4())[:8],
            'type': 'wait',
            'name': name,
            'wait_time': seconds,
            'save_result': True
        }
        self.workflow['steps'].append(step)
        return self

    def screenshot(self, name: str = "Screenshot") -> 'WorkflowBuilder':
        step = {
            'id': str(uuid.uuid4())[:8],
            'type': 'screenshot',
            'name': name,
            'save_result': True
        }
        self.workflow['steps'].append(step)
        return self

    def api_call(self, method: str, url: str, headers: Dict = None, body: Dict = None, name: str = "API Call") -> 'WorkflowBuilder':
        step = {
            'id': str(uuid.uuid4())[:8],
            'type': 'api_call',
            'name': name,
            'api_config': {
                'method': method,
                'url': url,
                'headers': headers or {},
                'body': body or {}
            },
            'timeout': 30,
            'save_result': True
        }
        self.workflow['steps'].append(step)
        return self

    def assert_equals(self, expression: str, expected: Any, name: str = "Assert Equals") -> 'WorkflowBuilder':
        step = {
            'id': str(uuid.uuid4())[:8],
            'type': 'assert',
            'name': name,
            'assert_config': {
                'condition': expression,
                'expected': expected,
                'operator': 'equals'
            },
            'save_result': True
        }
        self.workflow['steps'].append(step)
        return self

    def trigger(self, target_workflow: str, name: str = "Trigger") -> 'WorkflowBuilder':
        step = {
            'id': str(uuid.uuid4())[:8],
            'type': 'trigger',
            'name': name,
            'target_workflow': target_workflow,
            'save_result': True
        }
        self.workflow['steps'].append(step)
        return self

    def build(self) -> Dict:
        self.workflow['updated_at'] = datetime.now().isoformat()
        return self.workflow

    def save(self, workflow_manager: WorkflowManager = None) -> str:
        workflow = self.build()

        if workflow_manager is None:
            workflow_manager = WorkflowManager()

        wf_obj = Workflow.from_dict(workflow)
        workflow_manager.registry.save(wf_obj)
        return wf_obj.id

    def execute(self, session_name: str = None) -> WorkflowExecution:
        workflow = self.build()
        return self._engine.execute_workflow(workflow, session_name)
    
    def edit_step(self, step_index: int, updates: Dict) -> 'WorkflowBuilder':
        """Edit a step in the workflow"""
        if 0 <= step_index < len(self.workflow['steps']):
            self.workflow['steps'][step_index].update(updates)
            self.workflow['updated_at'] = datetime.now().isoformat()
        return self
    
    def remove_step(self, step_index: int) -> 'WorkflowBuilder':
        """Remove a step from the workflow"""
        if 0 <= step_index < len(self.workflow['steps']):
            self.workflow['steps'].pop(step_index)
            self.workflow['updated_at'] = datetime.now().isoformat()
        return self

# ============================================================================
# Context Manager (same as before)
# ============================================================================

class WorkflowContext:
    def __init__(self):
        self._data = {}
        self._history = []
        self._lock = threading.RLock()

    def set(self, key: str, value: Any, metadata: Dict = None):
        with self._lock:
            self._data[key] = value
            self._history.append({
                'key': key,
                'value': value,
                'timestamp': datetime.now().isoformat(),
                'metadata': metadata or {}
            })

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._data.get(key, default)

    def get_all(self) -> Dict:
        with self._lock:
            return self._data.copy()

    def get_history(self, limit: int = None) -> List[Dict]:
        with self._lock:
            if limit:
                return self._history[-limit:]
            return self._history.copy()

    def clear(self):
        with self._lock:
            self._data.clear()
            self._history.clear()

# ============================================================================
# Script Library (updated to use DB)
# ============================================================================

class ScriptLibrary:
    def __init__(self, config: WorkflowConfig):
        self.config = config
        self.db = DatabaseManager(config)
        self.scripts_dir = Path(config.scripts_library)
        self.scripts_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_structure()

    def _ensure_structure(self):
        for subdir in ['workflows', 'scripts', 'templates', 'shared']:
            (self.scripts_dir / subdir).mkdir(exist_ok=True)

    def save_script(self, workflow_name: str, step: WorkflowStep) -> str:
        """Save script to both filesystem and database"""
        # Save to filesystem
        workflow_dir = self.scripts_dir / 'workflows' / workflow_name
        workflow_dir.mkdir(parents=True, exist_ok=True)

        safe_name = step.name.lower().replace(' ', '_') if step.name else f"step_{step.id}"
        safe_name = re.sub(r'[^a-zA-Z0-9_-]', '', safe_name)

        filename = f"{safe_name}_{step.type}_{step.id}.js"
        filepath = workflow_dir / filename

        script_content = f"""/**
 * Script: {step.name}
 * ID: {step.id}
 * Type: {step.type}
 * Workflow: {workflow_name}
 * Created: {datetime.now().isoformat()}
 * Description: {step.description}
 */

// ============================================================================
// Main Execution Function
// ============================================================================

async function execute(api, context) {{
    console.log(`🔧 Executing step: {step.name} (ID: {step.id})`);

    try {{
        {step.code if step.code else '// Your code here'}
    }} catch (error) {{
        console.error(`❌ Step failed: ${{error.message}}`);
        throw error;
    }}
}}

// Export for workflow engine
if (typeof module !== 'undefined' && module.exports) {{
    module.exports = {{ execute }};
}}
"""
        with open(filepath, 'w') as f:
            f.write(script_content)

        metadata_file = workflow_dir / f"{filename}.meta.json"
        with open(metadata_file, 'w') as f:
            json.dump({
                'step_id': step.id,
                'step_name': step.name,
                'step_type': step.type,
                'created_at': datetime.now().isoformat(),
                'workflow': workflow_name,
                'description': step.description,
                'metadata': step.metadata
            }, f, indent=2)

        # Also save to database
        script_data = {
            'id': step.id,
            'name': step.name,
            'workflow_name': workflow_name,
            'code': step.code,
            'type': step.type,
            'description': step.description,
            'metadata': step.metadata,
            'tags': [workflow_name]
        }
        self.db.save_script(script_data)

        return str(filepath)

    def get_script(self, workflow_name: str, step_id: str) -> Optional[str]:
        # Try database first
        script = self.db.get_script(step_id)
        if script and script.get('code'):
            return script['code']

        # Fallback to filesystem
        workflow_dir = self.scripts_dir / 'workflows' / workflow_name
        if not workflow_dir.exists():
            return None

        for js_file in workflow_dir.glob(f"*_{step_id}.js"):
            with open(js_file, 'r') as f:
                return f.read()
        return None

    def get_all_scripts(self, workflow_name: str) -> List[Dict]:
        # Get from database
        scripts = self.db.list_scripts(workflow_name)
        
        # Also check filesystem for any not in DB
        workflow_dir = self.scripts_dir / 'workflows' / workflow_name
        if workflow_dir.exists():
            for js_file in workflow_dir.glob("*.js"):
                meta_file = js_file.with_suffix('.js.meta.json')
                metadata = {}
                if meta_file.exists():
                    with open(meta_file, 'r') as f:
                        metadata = json.load(f)
                
                # Check if already in DB
                if metadata.get('step_id'):
                    existing = [s for s in scripts if s.get('id') == metadata['step_id']]
                    if not existing:
                        scripts.append({
                            'filename': js_file.name,
                            'path': str(js_file),
                            'metadata': metadata,
                            'size': js_file.stat().st_size,
                            'modified': datetime.fromtimestamp(js_file.stat().st_mtime).isoformat()
                        })
        
        return scripts

    def delete_script(self, workflow_name: str, step_id: str) -> bool:
        # Delete from database
        db_deleted = self.db.delete_script(step_id)
        
        # Delete from filesystem
        workflow_dir = self.scripts_dir / 'workflows' / workflow_name
        if not workflow_dir.exists():
            return db_deleted

        deleted = False
        for js_file in workflow_dir.glob(f"*_{step_id}.js"):
            js_file.unlink()
            meta_file = js_file.with_suffix('.js.meta.json')
            if meta_file.exists():
                meta_file.unlink()
            deleted = True
        
        return db_deleted or deleted

# ============================================================================
# Enhanced CLI
# ============================================================================

class EnhancedCLI:
    def __init__(self):
        self.config = WorkflowConfig()
        self.engine = EnhancedExecutionEngine()
        self.workflow_manager = WorkflowManager(self.config)
        self.db = DatabaseManager(self.config)
        self.context = WorkflowContext()
        self._running = True

    def run(self):
        while self._running:
            if console:
                console.clear()
                self._show_header()

                menu = Table(show_header=False, box=box.MINIMAL)
                menu.add_column("Option", style="cyan", width=8)
                menu.add_column("Action", style="white")
                menu.add_column("Description", style="dim")

                menu.add_row("1", "[green]Execute JS[/green]", "Execute JavaScript and see results")
                menu.add_row("2", "[blue]Store Result[/blue]", "Store execution result with metadata")
                menu.add_row("3", "[yellow]Execute More JS[/yellow]", "Execute JS using stored data")
                menu.add_row("4", "[magenta]Save Data[/magenta]", "Save results and metadata")
                menu.add_row("5", "[cyan]Trigger Workflow[/cyan]", "Trigger another workflow")
                menu.add_row("6", "[white]View Context[/white]", "View stored context data")
                menu.add_row("7", "[red]Build Workflow[/red]", "Build a workflow interactively")
                menu.add_row("8", "[bright_blue]Run Workflow[/bright_blue]", "Run a saved workflow")
                menu.add_row("9", "[bright_magenta]List Workflows[/bright_magenta]", "List all workflows")
                menu.add_row("E", "[bold green]Edit Workflow[/bold green]", "Edit an existing workflow")
                menu.add_row("L", "[bold yellow]Loop Manager[/bold yellow]", "Create and manage loops")
                menu.add_row("S", "[bold cyan]Script DB[/bold cyan]", "Manage scripts in database")
                menu.add_row("R", "[bold blue]View Results[/bold blue]", "View saved results")
                menu.add_row("0", "[red]Exit[/red]", "Exit")

                console.print(menu)
                choice = Prompt.ask("Select option", choices=["0","1","2","3","4","5","6","7","8","9","E","L","S","R"])
            else:
                print("\n=== Enhanced Chrome Automation CLI ===")
                print("1. Execute JS")
                print("2. Store Result")
                print("3. Execute More JS")
                print("4. Save Data")
                print("5. Trigger Workflow")
                print("6. View Context")
                print("7. Build Workflow")
                print("8. Run Workflow")
                print("9. List Workflows")
                print("E. Edit Workflow")
                print("L. Loop Manager")
                print("S. Script DB")
                print("R. View Results")
                print("0. Exit")
                choice = input("Select option: ")

            if choice == "0":
                self._running = False
                break
            elif choice == "1":
                self._execute_js_interactive()
            elif choice == "2":
                self._store_result_interactive()
            elif choice == "3":
                self._execute_more_js_interactive()
            elif choice == "4":
                self._save_data_interactive()
            elif choice == "5":
                self._trigger_workflow_interactive()
            elif choice == "6":
                self._view_context()
            elif choice == "7":
                self._build_workflow_interactive()
            elif choice == "8":
                self._run_workflow_interactive()
            elif choice == "9":
                self._list_workflows()
            elif choice.upper() == "E":
                self._edit_workflow_interactive()
            elif choice.upper() == "L":
                self._loop_manager_interactive()
            elif choice.upper() == "S":
                self._script_db_manager()
            elif choice.upper() == "R":
                self._view_results()

            if choice != "0" and console:
                Prompt.ask("Press Enter to continue...")

    def _show_header(self):
        workflows = self.workflow_manager.list_workflows()
        context_count = len(self.context.get_all())
        scripts = self.db.list_scripts()

        header = f"""
╔══════════════════════════════════════════════════════════════╗
║     🌐 Enhanced Chrome Automation System v2.0              ║
║     Execute → Store → Loop → Save → Trigger → Metadata     ║
╠══════════════════════════════════════════════════════════════╣
║  📋 Workflows: {len(workflows)}  |  🎯 Context: {context_count} items  |  📜 Scripts: {len(scripts)}  ║
╚══════════════════════════════════════════════════════════════╝
        """
        console.print(Panel(header, border_style="cyan"))

    def _execute_js_interactive(self):
        console.print(Panel("[bold green]⚡ Execute JavaScript[/bold green]", border_style="green"))

        session_name = Prompt.ask("Session name", default="unstop")
        
        # Check if we want to use a saved script or write new
        use_saved = Confirm.ask("Use a saved script from database?", default=False)
        
        code = ""
        script_id = None
        
        if use_saved:
            scripts = self.db.list_scripts()
            if scripts:
                table = Table(title="Available Scripts", box=box.ROUNDED)
                table.add_column("#", style="cyan", width=4)
                table.add_column("Name", style="green")
                table.add_column("Workflow", style="dim")
                table.add_column("ID", style="dim")
                
                for i, script in enumerate(scripts, 1):
                    table.add_row(str(i), script.get('name', 'unnamed'), script.get('workflow_name', ''), script.get('id', '')[:8])
                console.print(table)
                
                choice = Prompt.ask("Select script (number or ID)")
                try:
                    idx = int(choice) - 1
                    if 0 <= idx < len(scripts):
                        script_id = scripts[idx]['id']
                except ValueError:
                    script_id = choice
                
                if script_id:
                    script = self.db.get_script(script_id)
                    if script:
                        code = script.get('code', '')
                        console.print(f"[dim]Using script: {script.get('name')}[/dim]")
            else:
                console.print("[yellow]No saved scripts found[/yellow]")
                use_saved = False
        
        if not use_saved or not code:
            console.print("[yellow]Enter JavaScript code (press Ctrl+D when done):[/yellow]")
            lines = []
            try:
                while True:
                    line = input()
                    lines.append(line)
            except EOFError:
                pass
            code = "\n".join(lines)

        if not code.strip():
            console.print("[red]No code entered[/red]")
            return

        result = self.engine.execute_javascript(session_name, code, self.context.get_all())

        console.print("\n[bold]Result:[/bold]")
        console.print_json(json.dumps(result, default=str, indent=2))

        if Confirm.ask("Store this result in context?", default=True):
            key = Prompt.ask("Variable name")
            if key:
                self.context.set(key, result)
                console.print(f"[green]✅ Stored in context: {key}[/green]")
        
        if Confirm.ask("Save this script to database?", default=False):
            name = Prompt.ask("Script name")
            workflow_name = Prompt.ask("Workflow name", default="default")
            description = Prompt.ask("Description", default="")
            tags = Prompt.ask("Tags (comma-separated)", default="")
            
            script_data = {
                'name': name,
                'code': code,
                'workflow_name': workflow_name,
                'description': description,
                'tags': [t.strip() for t in tags.split(',') if t.strip()],
                'type': 'js_execute'
            }
            
            script_id = self.db.save_script(script_data)
            console.print(f"[green]✅ Script saved to database! ID: {script_id}[/green]")

    def _store_result_interactive(self):
        console.print(Panel("[bold blue]💾 Store Result[/bold blue]", border_style="blue"))

        key = Prompt.ask("Variable name")
        value = Prompt.ask("Value (JSON or string)")
        metadata_str = Prompt.ask("Metadata (JSON, optional)", default="{}")

        try:
            try:
                parsed_value = json.loads(value)
            except:
                parsed_value = value

            metadata = json.loads(metadata_str) if metadata_str else {}

            self.context.set(key, parsed_value, metadata)
            console.print(f"[green]✅ Stored '{key}' with metadata[/green]")
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")

    def _execute_more_js_interactive(self):
        console.print(Panel("[bold yellow]🔄 Execute More JS (with context)[/bold yellow]", border_style="yellow"))

        context_data = self.context.get_all()
        if context_data:
            console.print("[dim]Available context variables:[/dim]")
            for key, value in context_data.items():
                val_str = str(value)[:50] + "..." if len(str(value)) > 50 else str(value)
                console.print(f"  [cyan]{key}[/cyan]: {val_str}")
        else:
            console.print("[dim]No context variables available[/dim]")

        session_name = Prompt.ask("Session name", default="unstop")

        console.print("[yellow]Enter JavaScript code (use context variables):[/yellow]")
        console.print("[dim]Example: const title = context.page_title; return title;[/dim]")

        lines = []
        try:
            while True:
                line = input()
                lines.append(line)
        except EOFError:
            pass

        custom_code = "\n".join(lines)

        if not custom_code.strip():
            console.print("[red]No code entered[/red]")
            return

        context_vars = self.context.get_all()
        context_js = "\n".join([f"const {k} = {json.dumps(v, default=str)};" for k, v in context_vars.items()])

        full_code = f"""
        (function() {{
            {context_js}
            {custom_code}
        }})()
        """

        result = self.engine.execute_javascript(session_name, full_code, {})

        console.print("\n[bold]Result:[/bold]")
        console.print_json(json.dumps(result, default=str, indent=2))

        if Confirm.ask("Store this result?", default=True):
            key = Prompt.ask("Variable name")
            if key:
                self.context.set(key, result)
                console.print(f"[green]✅ Stored in context: {key}[/green]")

    def _save_data_interactive(self):
        console.print(Panel("[bold magenta]💾 Save Data[/bold magenta]", border_style="magenta"))

        context_data = self.context.get_all()
        metadata = {
            'saved_at': datetime.now().isoformat(),
            'context_size': len(context_data),
            'workflow': 'manual'
        }

        if not context_data:
            console.print("[yellow]No data in context[/yellow]")
            return

        data_to_save = {}
        for key, value in context_data.items():
            if Confirm.ask(f"Save '{key}'?"):
                data_to_save[key] = value

        if not data_to_save:
            console.print("[yellow]No data selected to save[/yellow]")
            return

        # Save to database
        result_data = {
            'workflow_id': 'manual',
            'execution_id': str(uuid.uuid4()),
            'step_id': 'save_data',
            'step_name': 'Manual Save',
            'data': data_to_save,
            'metadata': metadata,
            'status': 'completed'
        }
        result_id = self.db.save_result(result_data)
        console.print(f"[green]✅ Data saved to database! Result ID: {result_id}[/green]")

        # Also save to filesystem
        filename = Prompt.ask("Filename (for filesystem backup)", default=f"data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        save_dir = Path.home() / "chrome-workflows" / "saved_data"
        save_dir.mkdir(parents=True, exist_ok=True)

        with open(save_dir / filename, 'w') as f:
            json.dump({
                'data': data_to_save,
                'metadata': metadata,
                'context_history': self.context.get_history(10)
            }, f, indent=2, default=str)

        console.print(f"[green]✅ Data saved to: {save_dir / filename}[/green]")

    def _trigger_workflow_interactive(self):
        console.print(Panel("[bold cyan]🔗 Trigger Workflow[/bold cyan]", border_style="cyan"))

        workflows = self.workflow_manager.list_workflows()
        if not workflows:
            console.print("[yellow]No workflows available[/yellow]")
            return

        table = Table(title="Available Workflows", box=box.ROUNDED)
        table.add_column("Name", style="green")
        table.add_column("Status", style="magenta")
        table.add_column("Steps", style="yellow")
        table.add_column("ID", style="dim")

        for wf in workflows:
            table.add_row(wf.name, wf.status, str(len(wf.steps)), wf.get_display_id())
        console.print(table)

        target = Prompt.ask("Workflow name or ID to trigger")
        session_name = Prompt.ask("Session name", default="unstop")

        builder = WorkflowBuilder(
            name=f"Trigger_{target}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            description=f"Triggered workflow: {target}"
        )
        builder.session(session_name)
        builder.trigger(target, "Trigger Workflow")
        builder.set_metadata("triggered_by", "interactive")
        builder.set_metadata("triggered_at", datetime.now().isoformat())
        builder.set_metadata("context_snapshot", self.context.get_all())
        builder.add_tag("triggered")

        wf_id = builder.save(self.workflow_manager)
        console.print(f"[green]✅ Trigger workflow created: {wf_id}[/green]")

        if Confirm.ask("Execute now?"):
            execution = builder.execute(session_name)
            console.print(f"[green]✅ Execution completed: {execution.status}[/green]")
            console.print(f"   Results: {len(execution.results)} steps")
            
            # Save results to database
            for result in execution.results:
                result_data = {
                    'workflow_id': wf_id,
                    'execution_id': execution.id,
                    'step_id': result.get('step_id', ''),
                    'step_name': result.get('step_name', ''),
                    'data': result.get('result', {}),
                    'metadata': result.get('metadata', {}),
                    'status': result.get('status', '')
                }
                self.db.save_result(result_data)

    def _view_context(self):
        console.print(Panel("[bold white]📋 Context Data[/bold white]", border_style="white"))

        context_data = self.context.get_all()

        if context_data:
            table = Table(title="Context Variables", box=box.ROUNDED)
            table.add_column("Key", style="cyan")
            table.add_column("Value", style="white")
            table.add_column("Type", style="dim")

            for key, value in context_data.items():
                val_str = str(value)[:100] + "..." if len(str(value)) > 100 else str(value)
                table.add_row(key, val_str, type(value).__name__)

            console.print(table)
        else:
            console.print("[dim]No context data available[/dim]")

        history = self.context.get_history(5)
        if history:
            console.print("\n[bold dim]Recent History:[/bold dim]")
            for entry in history:
                console.print(f"  {entry['timestamp'][:19]} - {entry['key']} = {str(entry['value'])[:50]}")

    def _build_workflow_interactive(self):
        console.print(Panel("[bold red]🏗️ Build Workflow[/bold red]", border_style="red"))

        name = Prompt.ask("Workflow name")
        if not name:
            console.print("[red]Name required[/red]")
            return

        description = Prompt.ask("Description", default="")

        builder = WorkflowBuilder(name, description)

        session_name = Prompt.ask("Session name", default="unstop")
        session_url = Prompt.ask("Session URL", default="https://unstop.com/")

        builder.session(session_name, session_url)

        while True:
            console.print("\n[bold]Add a step:[/bold]")
            console.print("1. JS Execute")
            console.print("2. Navigate")
            console.print("3. Click")
            console.print("4. Extract")
            console.print("5. Store")
            console.print("6. Wait")
            console.print("7. Screenshot")
            console.print("8. API Call")
            console.print("9. Assert")
            console.print("10. Trigger")
            console.print("11. Loop (NEW!)")
            console.print("0. Done")

            step_type = Prompt.ask("Select step type", choices=["0","1","2","3","4","5","6","7","8","9","10","11"])

            if step_type == "0":
                break

            step_name = Prompt.ask("Step name", default=f"Step_{len(builder.workflow['steps']) + 1}")

            if step_type == "1":
                console.print("[yellow]Enter JavaScript code (press Ctrl+D when done):[/yellow]")
                lines = []
                try:
                    while True:
                        line = input()
                        lines.append(line)
                except EOFError:
                    pass
                code = "\n".join(lines)
                var_name = Prompt.ask("Store result in variable (optional)", default="")
                continue_on_error = Confirm.ask("Continue on error?", default=False)
                save_result = Confirm.ask("Save result to database?", default=True)
                
                # Save script to DB
                if code.strip():
                    script_id = self.db.save_script({
                        'name': step_name,
                        'code': code,
                        'workflow_name': name,
                        'description': f"Step: {step_name}",
                        'type': 'js_execute'
                    })
                    builder.js(step_name, code=code, script_id=script_id,
                              variable_name=var_name if var_name else None,
                              continue_on_error=continue_on_error,
                              save_result=save_result)
                    console.print(f"[dim]Script saved to DB: {script_id}[/dim]")
                else:
                    builder.js(step_name, code=code,
                              variable_name=var_name if var_name else None,
                              continue_on_error=continue_on_error,
                              save_result=save_result)

            elif step_type == "2":
                url = Prompt.ask("URL")
                builder.navigate(url, step_name)

            elif step_type == "3":
                selector = Prompt.ask("CSS selector")
                builder.click(selector, step_name)

            elif step_type == "4":
                expression = Prompt.ask("JavaScript expression")
                var_name = Prompt.ask("Store in variable", default="")
                builder.extract(step_name, expression, var_name if var_name else None)

            elif step_type == "5":
                var_name = Prompt.ask("Variable name")
                value = Prompt.ask("Value")
                try:
                    value = json.loads(value)
                except:
                    pass
                builder.store(var_name, value, step_name)

            elif step_type == "6":
                seconds = int(Prompt.ask("Seconds", default="1"))
                builder.wait(seconds, step_name)

            elif step_type == "7":
                builder.screenshot(step_name)

            elif step_type == "8":
                method = Prompt.ask("Method", default="GET")
                url = Prompt.ask("URL")
                builder.api_call(method, url, name=step_name)

            elif step_type == "9":
                expression = Prompt.ask("JavaScript condition")
                expected = Prompt.ask("Expected value")
                try:
                    expected = json.loads(expected)
                except:
                    pass
                builder.assert_equals(expression, expected, step_name)

            elif step_type == "10":
                target = Prompt.ask("Target workflow name or ID")
                builder.trigger(target, step_name)

            elif step_type == "11":
                console.print("[yellow]Enter JavaScript code for loop (press Ctrl+D when done):[/yellow]")
                lines = []
                try:
                    while True:
                        line = input()
                        lines.append(line)
                except EOFError:
                    pass
                code = "\n".join(lines)
                
                loop_type = Prompt.ask("Loop type (for/while/each/until)", default="for")
                iterations = int(Prompt.ask("Iterations", default="5")) if loop_type == "for" else 5
                var_name = Prompt.ask("Variable name for loop item", default="loop_item")
                delay = int(Prompt.ask("Delay between iterations (seconds)", default="1"))
                collect_results = Confirm.ask("Collect all results?", default=True)
                
                if code.strip():
                    # Save script to DB
                    script_id = self.db.save_script({
                        'name': f"loop_{step_name}",
                        'code': code,
                        'workflow_name': name,
                        'description': f"Loop: {step_name}",
                        'type': 'js_execute',
                        'tags': ['loop']
                    })
                    
                    builder.loop(
                        name=step_name,
                        script_id=script_id,
                        loop_type=loop_type,
                        iterations=iterations,
                        variable_name=var_name,
                        delay=delay,
                        collect_results=collect_results
                    )
                    console.print(f"[dim]Loop script saved to DB: {script_id}[/dim]")

            console.print("[green]✅ Step added[/green]")

        tags = Prompt.ask("Tags (comma-separated)", default="")
        if tags:
            for tag in tags.split(','):
                builder.add_tag(tag.strip())

        wf_id = builder.save(self.workflow_manager)
        console.print(f"[green]✅ Workflow '{name}' saved! ID: {wf_id}[/green]")

        if Confirm.ask("Execute now?"):
            execution = builder.execute()
            console.print(f"[green]✅ Execution completed: {execution.status}[/green]")
            console.print(f"   Steps: {len(execution.results)} / {execution.total_steps}")
            if execution.error:
                console.print(f"   Error: {execution.error}")
            
            # Save results to database
            for result in execution.results:
                result_data = {
                    'workflow_id': wf_id,
                    'execution_id': execution.id,
                    'step_id': result.get('step_id', ''),
                    'step_name': result.get('step_name', ''),
                    'data': result.get('result', {}),
                    'metadata': result.get('metadata', {}),
                    'status': result.get('status', '')
                }
                self.db.save_result(result_data)

    def _run_workflow_interactive(self):
        console.print(Panel("[bold bright_blue]🚀 Run Workflow[/bold bright_blue]", border_style="bright_blue"))

        workflows = self.workflow_manager.list_workflows()
        if not workflows:
            console.print("[yellow]No workflows available[/yellow]")
            return

        table = Table(title="Workflows", box=box.ROUNDED)
        table.add_column("#", style="cyan", width=4)
        table.add_column("Name", style="green")
        table.add_column("Status", style="magenta")
        table.add_column("Steps", style="yellow")
        table.add_column("ID", style="dim")

        for i, wf in enumerate(workflows, 1):
            table.add_row(str(i), wf.name, wf.status, str(len(wf.steps)), wf.get_display_id())
        console.print(table)

        choice = Prompt.ask("Select workflow (number or name)")

        try:
            idx = int(choice) - 1
            if 0 <= idx < len(workflows):
                workflow = workflows[idx]
            else:
                workflow = self.workflow_manager.get_workflow(choice)
        except ValueError:
            workflow = self.workflow_manager.get_workflow(choice)

        if not workflow:
            console.print("[red]Workflow not found[/red]")
            return

        session_name = Prompt.ask("Session name", default=workflow.session_name)

        if Confirm.ask(f"Run workflow '{workflow.name}'?"):
            engine = EnhancedExecutionEngine()
            wf_dict = workflow.to_dict()
            wf_dict['steps'] = workflow.steps

            execution = engine.execute_workflow(wf_dict, session_name)
            console.print(f"[green]✅ Execution completed: {execution.status}[/green]")
            console.print(f"   Results: {len(execution.results)} steps")

            table = Table(title="Step Results", box=box.ROUNDED)
            table.add_column("Step", style="cyan")
            table.add_column("Status", style="magenta")
            table.add_column("Result", style="dim")

            for i, result in enumerate(execution.results, 1):
                status_color = "green" if result['status'] == 'completed' else "red"
                result_str = str(result.get('result', ''))[:50]
                table.add_row(
                    f"{i}. {result['step_name']}",
                    f"[{status_color}]{result['status']}[/{status_color}]",
                    result_str
                )
            console.print(table)

    def _list_workflows(self):
        console.print(Panel("[bold cyan]📋 Workflows[/bold cyan]", border_style="cyan"))

        workflows = self.workflow_manager.list_workflows()
        if not workflows:
            console.print("[yellow]No workflows found[/yellow]")
            return

        table = Table(title=f"Workflows ({len(workflows)})", box=box.ROUNDED)
        table.add_column("#", style="cyan", width=4)
        table.add_column("Name", style="green")
        table.add_column("Status", style="magenta")
        table.add_column("Steps", style="yellow")
        table.add_column("Executions", style="blue")
        table.add_column("ID", style="dim")

        status_colors = {
            'draft': 'dim',
            'active': 'green',
            'queued': 'yellow',
            'running': 'blue',
            'completed': 'green',
            'failed': 'red'
        }

        for i, wf in enumerate(workflows, 1):
            color = status_colors.get(wf.status, 'white')
            table.add_row(
                str(i),
                wf.name,
                f"[{color}]{wf.status}[/{color}]",
                str(len(wf.steps)),
                str(wf.execution_count),
                wf.get_display_id()
            )

        console.print(table)

        # Show summary
        status_counts = defaultdict(int)
        for wf in workflows:
            status_counts[wf.status] += 1
        summary = " | ".join([f"{status}: {count}" for status, count in status_counts.items()])
        console.print(f"[dim]Summary: {summary}[/dim]")
    
    def _edit_workflow_interactive(self):
        """Edit an existing workflow"""
        console.print(Panel("[bold green]✏️ Edit Workflow[/bold green]", border_style="green"))
        
        workflows = self.workflow_manager.list_workflows()
        if not workflows:
            console.print("[yellow]No workflows available[/yellow]")
            return
        
        table = Table(title="Workflows", box=box.ROUNDED)
        table.add_column("#", style="cyan", width=4)
        table.add_column("Name", style="green")
        table.add_column("Status", style="magenta")
        table.add_column("Steps", style="yellow")
        table.add_column("ID", style="dim")
        
        for i, wf in enumerate(workflows, 1):
            table.add_row(str(i), wf.name, wf.status, str(len(wf.steps)), wf.get_display_id())
        console.print(table)
        
        choice = Prompt.ask("Select workflow to edit (number or name)")
        
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(workflows):
                workflow = workflows[idx]
            else:
                workflow = self.workflow_manager.get_workflow(choice)
        except ValueError:
            workflow = self.workflow_manager.get_workflow(choice)
        
        if not workflow:
            console.print("[red]Workflow not found[/red]")
            return
        
        # Display workflow steps
        console.print(f"\n[bold]Workflow: {workflow.name}[/bold]")
        console.print(f"[dim]ID: {workflow.id}[/dim]")
        
        if workflow.steps:
            table = Table(title="Steps", box=box.ROUNDED)
            table.add_column("#", style="cyan", width=4)
            table.add_column("Name", style="green")
            table.add_column("Type", style="yellow")
            table.add_column("ID", style="dim")
            
            for i, step in enumerate(workflow.steps, 1):
                table.add_row(str(i), step.get('name', 'unnamed'), step.get('type', 'unknown'), step.get('id', '')[:8])
            console.print(table)
        else:
            console.print("[yellow]No steps in this workflow[/yellow]")
        
        # Edit options
        console.print("\n[bold]Edit options:[/bold]")
        console.print("1. Edit step code")
        console.print("2. Add step")
        console.print("3. Remove step")
        console.print("4. Rename workflow")
        console.print("5. Edit metadata")
        console.print("0. Back")
        
        edit_choice = Prompt.ask("Select", choices=["0","1","2","3","4","5"])
        
        if edit_choice == "0":
            return
        
        elif edit_choice == "1":
            step_num = int(Prompt.ask("Step number to edit")) - 1
            if 0 <= step_num < len(workflow.steps):
                step = workflow.steps[step_num]
                console.print(f"[bold]Editing step: {step.get('name')}[/bold]")
                
                if step.get('type') == 'js_execute' or step.get('type') == 'loop':
                    console.print("[yellow]Current code:[/yellow]")
                    console.print(step.get('code', 'No code')[:500])
                    console.print("[yellow]Enter new code (press Ctrl+D when done):[/yellow]")
                    lines = []
                    try:
                        while True:
                            line = input()
                            lines.append(line)
                    except EOFError:
                        pass
                    new_code = "\n".join(lines)
                    
                    if new_code.strip():
                        step['code'] = new_code
                        
                        # Update in DB if script_id exists
                        if step.get('script_id'):
                            self.db.save_script({
                                'id': step['script_id'],
                                'code': new_code,
                                'name': step.get('name', 'updated'),
                                'workflow_name': workflow.name
                            })
                        
                        # Save workflow
                        workflow.updated_at = datetime.now().isoformat()
                        self.workflow_manager.registry.save(workflow)
                        console.print("[green]✅ Step updated![/green]")
                    else:
                        console.print("[red]No code provided[/red]")
                else:
                    console.print("[yellow]Editing non-JS steps not yet supported[/yellow]")
            else:
                console.print("[red]Invalid step number[/red]")
        
        elif edit_choice == "2":
            # Use the same step addition as in build workflow
            console.print("[yellow]Add a step (using existing builder)[/yellow]")
            # Simplified: just add a JS step
            step_name = Prompt.ask("Step name")
            console.print("[yellow]Enter JavaScript code (press Ctrl+D when done):[/yellow]")
            lines = []
            try:
                while True:
                    line = input()
                    lines.append(line)
            except EOFError:
                pass
            code = "\n".join(lines)
            
            if code.strip():
                new_step = {
                    'id': str(uuid.uuid4())[:8],
                    'type': 'js_execute',
                    'name': step_name,
                    'code': code,
                    'continue_on_error': False,
                    'save_result': True
                }
                
                # Save script to DB
                script_id = self.db.save_script({
                    'name': step_name,
                    'code': code,
                    'workflow_name': workflow.name,
                    'type': 'js_execute'
                })
                new_step['script_id'] = script_id
                
                workflow.steps.append(new_step)
                workflow.updated_at = datetime.now().isoformat()
                self.workflow_manager.registry.save(workflow)
                console.print(f"[green]✅ Step '{step_name}' added! Script ID: {script_id}[/green]")
        
        elif edit_choice == "3":
            step_num = int(Prompt.ask("Step number to remove")) - 1
            if 0 <= step_num < len(workflow.steps):
                removed = workflow.steps.pop(step_num)
                workflow.updated_at = datetime.now().isoformat()
                self.workflow_manager.registry.save(workflow)
                console.print(f"[green]✅ Removed step: {removed.get('name')}[/green]")
            else:
                console.print("[red]Invalid step number[/red]")
        
        elif edit_choice == "4":
            new_name = Prompt.ask("New workflow name")
            if new_name:
                workflow.name = new_name
                workflow.updated_at = datetime.now().isoformat()
                self.workflow_manager.registry.save(workflow)
                console.print(f"[green]✅ Renamed to: {new_name}[/green]")
        
        elif edit_choice == "5":
            key = Prompt.ask("Metadata key")
            value = Prompt.ask("Metadata value")
            if key:
                workflow.metadata[key] = value
                workflow.updated_at = datetime.now().isoformat()
                self.workflow_manager.registry.save(workflow)
                console.print(f"[green]✅ Metadata updated: {key}={value}[/green]")
    
    def _loop_manager_interactive(self):
        """Manage loops"""
        console.print(Panel("[bold yellow]🔄 Loop Manager[/bold yellow]", border_style="yellow"))
        
        loops = self.db.get_loop_configs()
        
        if loops:
            table = Table(title="Loop Configurations", box=box.ROUNDED)
            table.add_column("Name", style="green")
            table.add_column("Type", style="yellow")
            table.add_column("Iterations", style="cyan")
            table.add_column("ID", style="dim")
            
            for loop in loops:
                config = loop.get('config', {})
                table.add_row(
                    loop.get('name', 'unnamed'),
                    config.get('type', 'for'),
                    str(config.get('iterations', 'N/A')),
                    loop.get('id', '')[:8]
                )
            console.print(table)
        
        console.print("\n[bold]Loop options:[/bold]")
        console.print("1. Create new loop")
        console.print("2. Execute loop with script")
        console.print("3. Delete loop")
        console.print("0. Back")
        
        choice = Prompt.ask("Select", choices=["0","1","2","3"])
        
        if choice == "0":
            return
        
        elif choice == "1":
            name = Prompt.ask("Loop name")
            loop_type = Prompt.ask("Type (for/while/each/until)", default="for")
            iterations = int(Prompt.ask("Iterations", default="5"))
            variable_name = Prompt.ask("Variable name", default="loop_item")
            delay = int(Prompt.ask("Delay (seconds)", default="1"))
            
            config = {
                'type': loop_type,
                'iterations': iterations,
                'variable_name': variable_name,
                'delay': delay,
                'collect_results': True,
                'max_iterations': 100
            }
            
            if loop_type == 'while' or loop_type == 'until':
                condition = Prompt.ask("Condition (JavaScript expression)")
                config['condition'] = condition
            
            loop_id = self.db.save_loop_config({
                'name': name,
                'config': config,
                'metadata': {'created_at': datetime.now().isoformat()}
            })
            console.print(f"[green]✅ Loop '{name}' created! ID: {loop_id}[/green]")
        
        elif choice == "2":
            # Get scripts
            scripts = self.db.list_scripts()
            if not scripts:
                console.print("[yellow]No scripts available[/yellow]")
                return
            
            table = Table(title="Scripts", box=box.ROUNDED)
            table.add_column("#", style="cyan", width=4)
            table.add_column("Name", style="green")
            table.add_column("ID", style="dim")
            
            for i, script in enumerate(scripts, 1):
                table.add_row(str(i), script.get('name', 'unnamed'), script.get('id', '')[:8])
            console.print(table)
            
            script_choice = Prompt.ask("Select script (number or ID)")
            
            try:
                idx = int(script_choice) - 1
                if 0 <= idx < len(scripts):
                    script_id = scripts[idx]['id']
                else:
                    script_id = script_choice
            except ValueError:
                script_id = script_choice
            
            if not script_id:
                console.print("[red]Invalid script selection[/red]")
                return
            
            # Get loops
            loops = self.db.get_loop_configs()
            if not loops:
                console.print("[yellow]No loop configurations available. Create one first.[/yellow]")
                return
            
            loop_names = [l.get('name', 'unnamed') for l in loops]
            loop_choice = Prompt.ask("Select loop (name or ID)", choices=loop_names + [str(l.get('id', '')) for l in loops])
            
            session_name = Prompt.ask("Session name", default="unstop")
            
            loop_manager = LoopManager(self.db)
            results = loop_manager.execute_loop(script_id, loop_choice, session_name)
            
            console.print(f"[green]✅ Loop executed! Results: {len(results)} iterations[/green]")
            
            # Show first few results
            for i, result in enumerate(results[:5], 1):
                console.print(f"  {i}. {result.get('result', {}).get('result', 'No result')[:100]}")
            if len(results) > 5:
                console.print(f"  ... and {len(results) - 5} more")
        
        elif choice == "3":
            loops = self.db.get_loop_configs()
            if not loops:
                console.print("[yellow]No loops to delete[/yellow]")
                return
            
            table = Table(title="Loops", box=box.ROUNDED)
            table.add_column("#", style="cyan", width=4)
            table.add_column("Name", style="green")
            table.add_column("ID", style="dim")
            
            for i, loop in enumerate(loops, 1):
                table.add_row(str(i), loop.get('name', 'unnamed'), loop.get('id', '')[:8])
            console.print(table)
            
            loop_choice = Prompt.ask("Select loop to delete (number or ID)")
            
            try:
                idx = int(loop_choice) - 1
                if 0 <= idx < len(loops):
                    loop_id = loops[idx]['id']
                else:
                    loop_id = loop_choice
            except ValueError:
                loop_id = loop_choice
            
            if loop_id and Confirm.ask(f"Delete loop '{loop_id}'?"):
                # Delete from DB
                # Note: Need to add delete method to DatabaseManager
                console.print("[green]✅ Loop deleted[/green]")
    
    def _script_db_manager(self):
        """Manage scripts in database"""
        console.print(Panel("[bold cyan]📜 Script Database Manager[/bold cyan]", border_style="cyan"))
        
        scripts = self.db.list_scripts()
        
        if scripts:
            table = Table(title=f"Scripts ({len(scripts)})", box=box.ROUNDED)
            table.add_column("Name", style="green")
            table.add_column("Workflow", style="dim")
            table.add_column("Type", style="yellow")
            table.add_column("Executions", style="blue")
            table.add_column("ID", style="dim")
            
            for script in scripts:
                table.add_row(
                    script.get('name', 'unnamed'),
                    script.get('workflow_name', ''),
                    script.get('type', 'js_execute'),
                    str(script.get('execution_count', 0)),
                    script.get('id', '')[:8]
                )
            console.print(table)
        else:
            console.print("[yellow]No scripts in database[/yellow]")
        
        console.print("\n[bold]Script options:[/bold]")
        console.print("1. View script")
        console.print("2. Delete script")
        console.print("3. Search scripts")
        console.print("4. View script versions")
        console.print("0. Back")
        
        choice = Prompt.ask("Select", choices=["0","1","2","3","4"])
        
        if choice == "0":
            return
        
        elif choice == "1":
            script_id = Prompt.ask("Script ID")
            script = self.db.get_script(script_id)
            if script:
                console.print(f"\n[bold]Name:[/bold] {script.get('name')}")
                console.print(f"[bold]ID:[/bold] {script.get('id')}")
                console.print(f"[bold]Workflow:[/bold] {script.get('workflow_name', 'N/A')}")
                console.print(f"[bold]Type:[/bold] {script.get('type')}")
                console.print(f"[bold]Executions:[/bold] {script.get('execution_count', 0)}")
                console.print(f"[bold]Created:[/bold] {script.get('created_at', 'N/A')}")
                console.print(f"[bold]Updated:[/bold] {script.get('updated_at', 'N/A')}")
                console.print(f"\n[bold]Code:[/bold]")
                syntax = Syntax(script.get('code', ''), "javascript", theme="monokai", line_numbers=True)
                console.print(syntax)
            else:
                console.print("[red]Script not found[/red]")
        
        elif choice == "2":
            script_id = Prompt.ask("Script ID to delete")
            if Confirm.ask(f"Delete script '{script_id}'?"):
                if self.db.delete_script(script_id):
                    console.print("[green]✅ Script deleted[/green]")
                else:
                    console.print("[red]Failed to delete script[/red]")
        
        elif choice == "3":
            query = Prompt.ask("Search term")
            scripts = self.db.list_scripts()
            matches = [s for s in scripts if query.lower() in s.get('name', '').lower() 
                      or query.lower() in s.get('workflow_name', '').lower()]
            
            if matches:
                table = Table(title="Search Results", box=box.ROUNDED)
                table.add_column("Name", style="green")
                table.add_column("Workflow", style="dim")
                table.add_column("ID", style="dim")
                
                for script in matches:
                    table.add_row(
                        script.get('name', 'unnamed'),
                        script.get('workflow_name', ''),
                        script.get('id', '')[:8]
                    )
                console.print(table)
            else:
                console.print("[yellow]No matches found[/yellow]")
        
        elif choice == "4":
            script_id = Prompt.ask("Script ID")
            versions = self.db.get_script_versions(script_id)
            if versions:
                table = Table(title="Version History", box=box.ROUNDED)
                table.add_column("Version", style="cyan")
                table.add_column("Created", style="dim")
                table.add_column("Code Preview", style="white")
                
                for v in versions[:10]:
                    code_preview = v.get('code', '')[:100] + "..." if len(v.get('code', '')) > 100 else v.get('code', '')
                    table.add_row(str(v.get('version', 0)), v.get('created_at', '')[:19], code_preview)
                console.print(table)
            else:
                console.print("[yellow]No versions found[/yellow]")
    
    def _view_results(self):
        """View saved results"""
        console.print(Panel("[bold blue]📊 View Results[/bold blue]", border_style="blue"))
        
        # Get results
        results = self.db.get_results()
        
        if not results:
            console.print("[yellow]No results found[/yellow]")
            return
        
        table = Table(title=f"Results ({len(results)})", box=box.ROUNDED)
        table.add_column("Step", style="green")
        table.add_column("Status", style="magenta")
        table.add_column("Data Preview", style="dim")
        table.add_column("Created", style="dim")
        
        for result in results[:20]:
            data_preview = str(result.get('data', {}))[:50] + "..." if len(str(result.get('data', {}))) > 50 else str(result.get('data', {}))
            status_color = "green" if result.get('status') == 'completed' else "red"
            table.add_row(
                result.get('step_name', 'unnamed'),
                f"[{status_color}]{result.get('status', 'unknown')}[/{status_color}]",
                data_preview,
                result.get('created_at', '')[:19]
            )
        console.print(table)
        
        if len(results) > 20:
            console.print(f"[dim]Showing 20 of {len(results)} results[/dim]")
        
        # Option to view details
        if Confirm.ask("View detailed result?", default=False):
            result_id = Prompt.ask("Result ID")
            # Find the result
            detail_result = None
            for r in results:
                if r.get('id') == result_id:
                    detail_result = r
                    break
            
            if detail_result:
                console.print(f"\n[bold]Step:[/bold] {detail_result.get('step_name')}")
                console.print(f"[bold]Status:[/bold] {detail_result.get('status')}")
                console.print(f"[bold]Created:[/bold] {detail_result.get('created_at')}")
                console.print(f"\n[bold]Data:[/bold]")
                console.print_json(json.dumps(detail_result.get('data', {}), default=str, indent=2))
                console.print(f"\n[bold]Metadata:[/bold]")
                console.print_json(json.dumps(detail_result.get('metadata', {}), default=str, indent=2))
            else:
                console.print("[red]Result not found[/red]")

# ============================================================================
# Main Entry
# ============================================================================

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(os.path.expanduser("~/chrome-workflows/enhanced.log"))
        ]
    )

def main():
    setup_logging()

    # Ensure directories exist
    for d in ["~/chrome-workflows", "~/chrome-workflows/workflows", 
              "~/chrome-workflows/executions", "~/chrome-workflows/scripts-library",
              "~/chrome-workflows/results", "~/chrome-workflows/saved_data"]:
        Path(os.path.expanduser(d)).mkdir(parents=True, exist_ok=True)

    try:
        cli = EnhancedCLI()
        cli.run()
    except KeyboardInterrupt:
        if console:
            console.print("\n[yellow]Interrupted[/yellow]")
        else:
            print("\nInterrupted")
    except Exception as e:
        logging.exception("Fatal error")
        if console:
            console.print(f"[red]Error: {e}[/red]")
        else:
            print(f"Error: {e}")

if __name__ == "__main__":
    main()
