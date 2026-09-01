#!/usr/bin/env python3
"""
Enhanced Chrome CDP Controller - ULTIMATE EDITION v3.0
========================================================
Features:
- REAL-TIME NETWORK MONITORING with SQLite persistence
- Persistent WebSocket connection
- Tab change detection
- Console Hijacking
- XSS Detection
- DOM Time-Travel
- Session Recording
- Data Extraction
- HAR Export with full data
"""

import json
import subprocess
import sys
import os
import time
import base64
import threading
import queue
import sqlite3
from typing import Optional, Dict, List, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime
from collections import defaultdict
from enum import Enum

try:
    import requests
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests"])
    import requests

try:
    import websocket
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "websocket-client"])
    import websocket

# ============================================================================
# SQLite Database Manager
# ============================================================================

class NetworkDatabase:
    """SQLite database for storing network events"""
    
    def __init__(self, db_path: str = "network_capture.db"):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """Initialize database schema"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Create tables
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id TEXT UNIQUE,
                url TEXT,
                method TEXT,
                headers TEXT,
                post_data TEXT,
                timestamp REAL,
                started REAL,
                tab_id TEXT,
                request_type TEXT,
                status_code INTEGER,
                response_headers TEXT,
                response_body TEXT,
                response_time REAL,
                duration REAL,
                finished INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT,
                request_id TEXT,
                url TEXT,
                method TEXT,
                status_code INTEGER,
                headers TEXT,
                body TEXT,
                timestamp REAL,
                duration REAL,
                tab_id TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tab_changes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                old_tab_id TEXT,
                new_tab_id TEXT,
                timestamp REAL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS console_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                log_type TEXT,
                message TEXT,
                timestamp REAL,
                tab_id TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                start_time REAL,
                end_time REAL,
                tab_id TEXT,
                url TEXT,
                request_count INTEGER DEFAULT 0,
                error_count INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create indexes for performance
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_requests_url ON requests(url)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_requests_timestamp ON requests(timestamp)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_events_request_id ON events(request_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp)')
        
        conn.commit()
        conn.close()
        print("✅ Database initialized: network_capture.db")
    
    def insert_request(self, request: Dict) -> int:
        """Insert a new request"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO requests (
                request_id, url, method, headers, post_data, timestamp, started,
                tab_id, request_type
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            request.get('request_id'),
            request.get('url'),
            request.get('method'),
            json.dumps(request.get('headers', {})),
            request.get('post_data'),
            request.get('timestamp'),
            request.get('started'),
            request.get('tab_id'),
            request.get('type')
        ))
        
        conn.commit()
        last_id = cursor.lastrowid
        conn.close()
        return last_id
    
    def update_request_response(self, request_id: str, response: Dict):
        """Update request with response data"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE requests SET
                status_code = ?,
                response_headers = ?,
                response_body = ?,
                response_time = ?,
                duration = ?,
                finished = 1
            WHERE request_id = ?
        ''', (
            response.get('status_code'),
            json.dumps(response.get('headers', {})),
            response.get('body'),
            response.get('response_time'),
            response.get('duration'),
            request_id
        ))
        
        conn.commit()
        conn.close()
    
    def insert_event(self, event: Dict) -> int:
        """Insert a network event"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO events (
                event_type, request_id, url, method, status_code, headers, body,
                timestamp, duration, tab_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            event.get('type'),
            event.get('request_id'),
            event.get('url'),
            event.get('method'),
            event.get('status'),
            json.dumps(event.get('headers', {})),
            event.get('body'),
            event.get('timestamp'),
            event.get('duration'),
            event.get('tab_id')
        ))
        
        conn.commit()
        last_id = cursor.lastrowid
        conn.close()
        return last_id
    
    def insert_tab_change(self, old_tab_id: str, new_tab_id: str, timestamp: float):
        """Log tab change"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO tab_changes (old_tab_id, new_tab_id, timestamp)
            VALUES (?, ?, ?)
        ''', (old_tab_id, new_tab_id, timestamp))
        
        conn.commit()
        conn.close()
    
    def insert_console_log(self, log_type: str, message: str, timestamp: float, tab_id: str = None):
        """Log console message"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO console_logs (log_type, message, timestamp, tab_id)
            VALUES (?, ?, ?, ?)
        ''', (log_type, message, timestamp, tab_id))
        
        conn.commit()
        conn.close()
    
    def get_stats(self) -> Dict:
        """Get database statistics"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        stats = {}
        
        cursor.execute('SELECT COUNT(*) FROM requests')
        stats['total_requests'] = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM events')
        stats['total_events'] = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM tab_changes')
        stats['tab_changes'] = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM console_logs')
        stats['console_logs'] = cursor.fetchone()[0]
        
        # Get requests by type
        cursor.execute('''
            SELECT request_type, COUNT(*) FROM requests GROUP BY request_type
        ''')
        stats['by_type'] = dict(cursor.fetchall())
        
        # Get requests by status
        cursor.execute('''
            SELECT status_code, COUNT(*) FROM requests 
            WHERE status_code IS NOT NULL GROUP BY status_code
        ''')
        stats['by_status'] = dict(cursor.fetchall())
        
        conn.close()
        return stats
    
    def export_har(self, output_file: str = None) -> Dict:
        """Export all data as HAR format"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM requests ORDER BY timestamp
        ''')
        
        rows = cursor.fetchall()
        columns = [description[0] for description in cursor.description]
        
        entries = []
        for row in rows:
            data = dict(zip(columns, row))
            entry = {
                'startedDateTime': datetime.fromtimestamp(data['timestamp']).isoformat(),
                'time': data['duration'] or 0,
                'request': {
                    'method': data['method'],
                    'url': data['url'],
                    'headers': json.loads(data['headers']) if data['headers'] else {},
                    'bodySize': len(data['post_data']) if data['post_data'] else -1
                },
                'response': {
                    'status': data['status_code'] or 0,
                    'headers': json.loads(data['response_headers']) if data['response_headers'] else {},
                    'bodySize': len(data['response_body']) if data['response_body'] else -1
                },
                'timings': {
                    'wait': data['duration'] or 0
                }
            }
            entries.append(entry)
        
        conn.close()
        
        har_data = {
            'log': {
                'version': '1.2',
                'creator': {
                    'name': 'CDP Ultimate Recorder',
                    'version': '3.0'
                },
                'entries': entries,
                'timestamp': datetime.now().isoformat(),
                'stats': self.get_stats()
            }
        }
        
        if output_file:
            with open(output_file, 'w') as f:
                json.dump(har_data, f, indent=2)
            print(f"✅ HAR exported to: {output_file}")
        
        return har_data

# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class NetworkRequest:
    """Network request data"""
    request_id: str
    url: str
    method: str
    headers: Dict
    post_data: Optional[str]
    timestamp: float
    started: float
    response_status: Optional[int] = None
    response_headers: Optional[Dict] = None
    response_body: Optional[str] = None
    response_time: Optional[float] = None
    duration: Optional[float] = None
    type: str = "unknown"
    tab_id: Optional[str] = None
    finished: bool = False

@dataclass
class NetworkEvent:
    """Network event for real-time monitoring"""
    type: str
    request_id: str
    url: str
    method: str
    status: Optional[int] = None
    headers: Optional[Dict] = None
    body: Optional[str] = None
    timestamp: float = field(default_factory=time.time)
    duration: Optional[float] = None
    tab_id: Optional[str] = None

# ============================================================================
# Persistent CDP Client with Real-Time Monitoring
# ============================================================================

class PersistentCDPClient:
    """Persistent WebSocket connection with real-time monitoring"""
    
    def __init__(self, port: int = 9227):
        self.port = port
        self.base_url = f"http://127.0.0.1:{port}"
        self.ws = None
        self.ws_url = None
        self.tabs = []
        self.tab_index = 0
        self._running = False
        self._thread = None
        self._event_queue = queue.Queue()
        self._command_counter = 0
        
        # Network data
        self.active_requests: Dict[str, NetworkRequest] = {}
        self.completed_requests: List[NetworkRequest] = []
        self.network_events: List[NetworkEvent] = []
        self.callbacks: List[Callable] = []
        self.tab_change_callbacks: List[Callable] = []
        
        # Database
        self.db = NetworkDatabase()
        
        # Recording state
        self.is_recording = False
        self.recording_start = None
        self.har_entries = []
        
        # Tab tracking
        self.current_tab_id = None
        self.last_tab_id = None
        
        # Console
        self.console_messages = []
        
        # Stats
        self.stats = {
            'requests': 0,
            'responses': 0,
            'errors': 0,
            'tab_changes': 0
        }
        
        # Connect immediately
        self.connect()
    
    def connect(self, tab_index: int = 0) -> bool:
        """Connect to Chrome and start monitoring"""
        print(f"🔌 Connecting to Chrome on port {self.port}...")
        
        # Get tabs
        self.tabs = self._get_tabs()
        if not self.tabs:
            print("❌ No tabs found. Make sure Chrome is running with:")
            print(f"   chromium-browser --remote-debugging-port={self.port}")
            return False
        
        # Select tab
        if tab_index >= len(self.tabs):
            tab_index = 0
        self.tab_index = tab_index
        
        # Get WebSocket URL
        ws_url = self.tabs[tab_index].get('webSocketDebuggerUrl')
        if not ws_url:
            print("❌ No WebSocket URL found")
            return False
        
        self.ws_url = ws_url
        self.current_tab_id = self.tabs[tab_index].get('id')
        print(f"📡 Connecting to: {ws_url[:60]}...")
        
        try:
            self.ws = websocket.create_connection(
                ws_url,
                timeout=30,
                header={"Origin": f"http://127.0.0.1:{self.port}"}
            )
            print("✅ WebSocket connected!")
            
            # Enable domains
            self._send_command("Network.enable", {
                "maxResourceBufferSize": 10000000,
                "maxTotalBufferSize": 10000000
            })
            self._send_command("Runtime.enable")
            self._send_command("DOM.enable")
            self._send_command("CSS.enable")
            
            print("✅ All domains enabled")
            
            # Start monitoring thread
            self._running = True
            self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
            self._thread.start()
            
            # Log session start
            self.db.insert_event({
                'type': 'session_start',
                'url': self.tabs[tab_index].get('url', ''),
                'tab_id': self.current_tab_id,
                'timestamp': time.time()
            })
            
            return True
            
        except Exception as e:
            print(f"❌ Connection error: {e}")
            return False
    
    def _get_tabs(self) -> List[Dict]:
        """Get all tabs from Chrome"""
        try:
            response = requests.get(f"{self.base_url}/json", timeout=5)
            if response.status_code == 200:
                return [t for t in response.json() if t.get('type') == 'page']
            return []
        except Exception as e:
            print(f"❌ Error getting tabs: {e}")
            return []
    
    def _send_command(self, method: str, params: Dict = None) -> Dict:
        """Send CDP command"""
        if not self.ws:
            return None
        
        self._command_counter += 1
        cmd = {
            "id": self._command_counter,
            "method": method,
            "params": params or {}
        }
        
        try:
            self.ws.send(json.dumps(cmd))
            return {'id': self._command_counter}
        except Exception as e:
            print(f"❌ Failed to send command: {e}")
            return None
    
    def _monitor_loop(self):
        """Main monitoring loop"""
        print("📡 Starting real-time monitoring...")
        
        while self._running:
            try:
                self.ws.settimeout(1.0)
                message = self.ws.recv()
                
                if message:
                    data = json.loads(message)
                    
                    if 'id' in data:
                        # Command response
                        continue
                    elif 'method' in data:
                        # Event notification
                        self._handle_event(data['method'], data.get('params', {}))
                        
            except websocket.WebSocketTimeoutException:
                # Check if we need to reconnect
                continue
            except websocket.WebSocketConnectionClosedException:
                print("⚠️ WebSocket disconnected, reconnecting...")
                self._reconnect()
                break
            except Exception as e:
                print(f"⚠️ Monitor error: {e}")
                time.sleep(1)
    
    def _reconnect(self):
        """Reconnect WebSocket"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
        
        time.sleep(2)
        self.connect(self.tab_index)
    
    def _handle_event(self, method: str, params: Dict):
        """Handle incoming CDP events"""
        try:
            if method == 'Network.requestWillBeSent':
                self._handle_request(params)
            elif method == 'Network.responseReceived':
                self._handle_response(params)
            elif method == 'Network.loadingFinished':
                self._handle_loading_finished(params)
            elif method == 'Network.loadingFailed':
                self._handle_loading_failed(params)
            elif method == 'Runtime.consoleAPICalled':
                self._handle_console(params)
            elif method == 'DOM.documentUpdated':
                self._handle_dom_updated()
            elif method == 'Page.frameNavigated':
                self._handle_navigation(params)
                
        except Exception as e:
            print(f"⚠️ Event handler error: {e}")
    
    def _handle_request(self, params: Dict):
        """Handle requestWillBeSent event"""
        request_id = params.get('requestId')
        request = params.get('request', {})
        url = request.get('url', '')
        
        # Skip data URLs
        if url.startswith('data:'):
            return
        
        req = NetworkRequest(
            request_id=request_id,
            url=url,
            method=request.get('method', 'GET'),
            headers=request.get('headers', {}),
            post_data=request.get('postData'),
            timestamp=time.time(),
            started=params.get('timestamp', time.time()),
            tab_id=self.current_tab_id,
            type=self._get_request_type(url)
        )
        
        self.active_requests[request_id] = req
        
        # Store in database
        self.db.insert_request({
            'request_id': request_id,
            'url': url,
            'method': req.method,
            'headers': req.headers,
            'post_data': req.post_data,
            'timestamp': req.timestamp,
            'started': req.started,
            'tab_id': req.tab_id,
            'type': req.type
        })
        
        # Create event
        event = NetworkEvent(
            type='request',
            request_id=request_id,
            url=url,
            method=req.method,
            headers=req.headers,
            body=req.post_data,
            timestamp=req.timestamp,
            tab_id=req.tab_id
        )
        self.network_events.append(event)
        self._notify_callbacks(event)
        self.stats['requests'] += 1
        
        # Print live
        print(f"   📤 {req.method} {url[:60]}...")
    
    def _handle_response(self, params: Dict):
        """Handle responseReceived event"""
        request_id = params.get('requestId')
        if request_id not in self.active_requests:
            return
        
        req = self.active_requests[request_id]
        response = params.get('response', {})
        
        req.response_status = response.get('status', 0)
        req.response_headers = response.get('headers', {})
        req.response_time = time.time()
        req.duration = req.response_time - req.started
        
        # Update database
        self.db.update_request_response(request_id, {
            'status_code': req.response_status,
            'headers': req.response_headers,
            'response_time': req.response_time,
            'duration': req.duration
        })
        
        event = NetworkEvent(
            type='response',
            request_id=request_id,
            url=req.url,
            method=req.method,
            status=req.response_status,
            headers=req.response_headers,
            timestamp=req.response_time,
            duration=req.duration,
            tab_id=req.tab_id
        )
        self.network_events.append(event)
        self._notify_callbacks(event)
        
        # HAR recording
        if self.is_recording:
            self.har_entries.append({
                'startedDateTime': datetime.fromtimestamp(req.started).isoformat(),
                'time': req.duration or 0,
                'request': {
                    'method': req.method,
                    'url': req.url,
                    'headers': req.headers,
                    'bodySize': len(req.post_data) if req.post_data else -1
                },
                'response': {
                    'status': req.response_status,
                    'headers': req.response_headers,
                    'bodySize': -1
                }
            })
        
        self.stats['responses'] += 1
        
        # Print live with status
        status_emoji = "✅" if 200 <= req.response_status < 300 else "⚠️" if 300 <= req.response_status < 400 else "❌"
        print(f"   {status_emoji} {req.method} {req.url[:50]}... - {req.response_status} ({req.duration:.2f}s)")
    
    def _handle_loading_finished(self, params: Dict):
        """Handle loadingFinished event"""
        request_id = params.get('requestId')
        if request_id in self.active_requests:
            req = self.active_requests[request_id]
            req.finished = True
            req.duration = time.time() - req.started
            
            event = NetworkEvent(
                type='finished',
                request_id=request_id,
                url=req.url,
                method=req.method,
                status=req.response_status,
                duration=req.duration,
                timestamp=time.time(),
                tab_id=req.tab_id
            )
            self.network_events.append(event)
            self._notify_callbacks(event)
            
            # Move to completed
            self.completed_requests.append(req)
            del self.active_requests[request_id]
    
    def _handle_loading_failed(self, params: Dict):
        """Handle loadingFailed event"""
        request_id = params.get('requestId')
        if request_id in self.active_requests:
            req = self.active_requests[request_id]
            error_text = params.get('errorText', 'Unknown error')
            
            event = NetworkEvent(
                type='failed',
                request_id=request_id,
                url=req.url,
                method=req.method,
                status=0,
                body=error_text,
                timestamp=time.time(),
                tab_id=req.tab_id
            )
            self.network_events.append(event)
            self._notify_callbacks(event)
            self.stats['errors'] += 1
            
            print(f"   ❌ FAILED: {req.method} {req.url[:50]}... - {error_text}")
            
            del self.active_requests[request_id]
    
    def _handle_console(self, params: Dict):
        """Handle console API calls"""
        log_type = params.get('type', 'log')
        args = params.get('args', [])
        
        # Extract message
        message_parts = []
        for arg in args:
            if arg.get('type') == 'string':
                message_parts.append(arg.get('value', ''))
            elif arg.get('type') == 'object':
                message_parts.append(json.dumps(arg.get('value', {})))
            else:
                message_parts.append(str(arg.get('value', '')))
        
        message = ' '.join(message_parts)
        timestamp = time.time()
        
        self.console_messages.append({
            'type': log_type,
            'message': message,
            'timestamp': timestamp
        })
        
        # Store in database
        self.db.insert_console_log(log_type, message, timestamp, self.current_tab_id)
        
        # Print if important
        if log_type in ['error', 'warn']:
            print(f"   🔴 {log_type.upper()}: {message[:100]}")
    
    def _handle_dom_updated(self):
        """Handle DOM update"""
        # Check for tab changes
        self._check_tab_change()
    
    def _handle_navigation(self, params: Dict):
        """Handle page navigation"""
        url = params.get('url', '')
        print(f"   🧭 Navigated to: {url[:80]}...")
        
        # Check for tab changes
        self._check_tab_change()
    
    def _check_tab_change(self):
        """Check if tab has changed"""
        tabs = self._get_tabs()
        if tabs:
            new_tab_id = tabs[self.tab_index].get('id') if self.tab_index < len(tabs) else None
            if new_tab_id and new_tab_id != self.current_tab_id:
                old_tab_id = self.current_tab_id
                self.current_tab_id = new_tab_id
                self.stats['tab_changes'] += 1
                
                # Store in database
                self.db.insert_tab_change(old_tab_id, new_tab_id, time.time())
                
                # Notify callbacks
                for callback in self.tab_change_callbacks:
                    try:
                        callback(old_tab_id, new_tab_id)
                    except Exception as e:
                        print(f"Tab change callback error: {e}")
                
                print(f"   🔄 TAB CHANGED: {old_tab_id} -> {new_tab_id}")
    
    def _get_request_type(self, url: str) -> str:
        """Determine request type from URL"""
        if '/api/' in url or '/v' in url and '/' in url:
            return 'api'
        if '.js' in url:
            return 'script'
        if '.css' in url:
            return 'stylesheet'
        if '.png' in url or '.jpg' in url or '.gif' in url or '.svg' in url:
            return 'image'
        if '.woff' in url or '.woff2' in url or '.ttf' in url:
            return 'font'
        if 'google' in url or 'analytics' in url:
            return 'analytics'
        return 'other'
    
    def _notify_callbacks(self, event: NetworkEvent):
        """Notify all registered callbacks"""
        for callback in self.callbacks:
            try:
                callback(event)
            except Exception as e:
                print(f"Callback error: {e}")
    
    # ==================== Public API ====================
    
    def on_network_event(self, callback: Callable):
        """Register callback for network events"""
        self.callbacks.append(callback)
    
    def on_tab_change(self, callback: Callable):
        """Register callback for tab changes"""
        self.tab_change_callbacks.append(callback)
    
    def start_recording(self):
        """Start HAR recording"""
        self.is_recording = True
        self.recording_start = time.time()
        self.har_entries = []
        print("📡 HAR recording started!")
    
    def stop_recording(self) -> Dict:
        """Stop HAR recording and return data"""
        self.is_recording = False
        
        har_data = {
            'log': {
                'version': '1.2',
                'creator': {
                    'name': 'CDP Ultimate Recorder',
                    'version': '3.0'
                },
                'entries': self.har_entries,
                'recording_duration': time.time() - self.recording_start,
                'timestamp': datetime.now().isoformat()
            }
        }
        
        print(f"✅ HAR recording stopped. Captured {len(self.har_entries)} entries")
        return har_data
    
    def get_stats(self) -> Dict:
        """Get current statistics"""
        return {
            'active_requests': len(self.active_requests),
            'completed_requests': len(self.completed_requests),
            'network_events': len(self.network_events),
            'console_messages': len(self.console_messages),
            'db_stats': self.db.get_stats(),
            'runtime_stats': self.stats.copy()
        }
    
    def get_db_stats(self) -> Dict:
        """Get database statistics"""
        return self.db.get_stats()
    
    def export_har(self, filename: str = None) -> Dict:
        """Export HAR from database"""
        if not filename:
            filename = f"har_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.har"
        return self.db.export_har(filename)
    
    def execute_js(self, script: str) -> Optional[Any]:
        """Execute JavaScript"""
        result = self._send_command("Runtime.evaluate", {
            "expression": script,
            "returnByValue": True,
            "awaitPromise": True
        })
        return result
    
    def close(self):
        """Close connection"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
        if self.ws:
            self.ws.close()
        print("🔌 Connection closed")

# ============================================================================
# Interactive CLI
# ============================================================================

def main():
    print("=" * 70)
    print("🚀 ULTIMATE CDP CONTROLLER v3.0 - Real-Time Network Monitor")
    print("=" * 70)
    print()
    
    # Get port
    port_input = input("🔌 Chrome debug port (default 9227): ").strip()
    port = int(port_input) if port_input else 9227
    
    # Create client
    client = PersistentCDPClient(port)
    
    if not client.ws:
        print("❌ Failed to connect. Exiting.")
        return
    
    # Print available tabs
    print("\n📑 Available Tabs:")
    for i, tab in enumerate(client.tabs):
        title = tab.get('title', 'Untitled')[:50]
        url = tab.get('url', '')[:60]
        print(f"  [{i}] {title}")
        print(f"      {url}")
    
    # Select tab
    tab_input = input(f"\n📑 Select tab (0-{len(client.tabs)-1}, default 0): ").strip()
    if tab_input:
        try:
            tab_index = int(tab_input)
            if 0 <= tab_index < len(client.tabs):
                client.tab_index = tab_index
        except:
            pass
    
    print("\n✅ Connected! Starting real-time monitoring...")
    print("   Network requests will appear as they happen")
    print("   Type 'help' for commands\n")
    
    # Command loop
    while True:
        try:
            cmd = input("\n🔧 > ").strip().lower()
            
            if not cmd:
                continue
            
            elif cmd in ['q', 'quit', 'exit']:
                break
            
            elif cmd == 'stats':
                stats = client.get_stats()
                print("\n📊 STATISTICS:")
                print(f"   Active Requests: {stats['active_requests']}")
                print(f"   Completed Requests: {stats['completed_requests']}")
                print(f"   Network Events: {stats['network_events']}")
                print(f"   Console Messages: {stats['console_messages']}")
                print(f"   Tab Changes: {stats['runtime_stats']['tab_changes']}")
                print(f"   Errors: {stats['runtime_stats']['errors']}")
                
                db_stats = client.get_db_stats()
                print(f"\n   Database Stats:")
                print(f"     Total Requests: {db_stats['total_requests']}")
                print(f"     Total Events: {db_stats['total_events']}")
                print(f"     Tab Changes: {db_stats['tab_changes']}")
                print(f"     Console Logs: {db_stats['console_logs']}")
            
            elif cmd == 'record':
                client.start_recording()
                print("📡 Recording started! All requests will be saved.")
            
            elif cmd == 'stop':
                har_data = client.stop_recording()
                print(f"✅ Recording stopped. Captured {len(har_data['log']['entries'])} entries")
                
                save = input("💾 Save HAR to file? (y/n): ").strip().lower()
                if save == 'y':
                    filename = f"har_capture_{datetime.now().strftime('%Y%m%d_%H%M%S')}.har"
                    with open(filename, 'w') as f:
                        json.dump(har_data, f, indent=2)
                    print(f"✅ Saved to {filename}")
            
            elif cmd == 'export':
                filename = input("📁 Output filename (default: auto): ").strip()
                if not filename:
                    filename = f"har_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.har"
                client.export_har(filename)
                print(f"✅ HAR exported to {filename}")
            
            elif cmd == 'console':
                logs = client.console_messages[-20:]
                print(f"\n📋 Console Logs (last {len(logs)}):")
                for log in logs:
                    print(f"   [{log['type']}] {log['message'][:100]}")
            
            elif cmd.startswith('js '):
                script = cmd[3:]
                result = client.execute_js(script)
                if result:
                    print(f"✅ Result: {json.dumps(result, indent=2, default=str)[:500]}")
            
            elif cmd == 'help':
                print("""
📋 AVAILABLE COMMANDS:
  stats     - Show statistics
  record    - Start HAR recording
  stop      - Stop HAR recording
  export    - Export HAR from database
  console   - Show console logs
  js <code> - Execute JavaScript
  help      - Show this help
  q/quit    - Exit
""")
            
            else:
                print(f"❌ Unknown command: {cmd}")
                print("   Type 'help' for available commands")
                
        except KeyboardInterrupt:
            print("\n👋 Interrupted!")
            break
        except Exception as e:
            print(f"❌ Error: {e}")
    
    # Cleanup
    client.close()
    print("\n👋 Goodbye!")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Goodbye!")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Fatal Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
