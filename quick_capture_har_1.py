#!/usr/bin/env python3
"""
Robust Journey HAR Capture - Production-grade complete browsing session capture
"""

import websocket
import json
import time
import sys
import requests
from datetime import datetime
from typing import Dict, List, Optional, Any, Set
import threading
from collections import defaultdict
import os
import signal
import logging
import traceback
from dataclasses import dataclass, field
from enum import Enum
import hashlib

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('har_capture.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class CaptureStatus(Enum):
    IDLE = "idle"
    CONNECTING = "connecting"
    CAPTURING = "capturing"
    PAUSED = "paused"
    STOPPING = "stopping"
    COMPLETED = "completed"
    ERROR = "error"

@dataclass
class TabInfo:
    """Information about a browser tab"""
    id: str
    title: str = "Untitled"
    url: str = ""
    ws_url: str = ""
    entries: List[Dict] = field(default_factory=list)
    request_map: Dict[str, Dict] = field(default_factory=dict)
    capture_started: Optional[str] = None
    capture_ended: Optional[str] = None
    is_active: bool = False
    entry_count: int = 0
    first_seen: str = field(default_factory=lambda: datetime.now().isoformat())
    last_seen: str = field(default_factory=lambda: datetime.now().isoformat())
    status: CaptureStatus = CaptureStatus.IDLE
    reconnect_attempts: int = 0
    total_responses: int = 0
    total_requests: int = 0
    errors: List[str] = field(default_factory=list)
    websocket: Optional[websocket.WebSocket] = None
    lock: threading.Lock = field(default_factory=threading.Lock)

@dataclass
class CaptureConfig:
    """Configuration for the capture session"""
    port: int = 9258
    duration: int = 60
    max_reconnect_attempts: int = 5
    reconnect_delay: int = 2
    websocket_timeout: float = 1.0
    progress_interval: int = 10
    skip_patterns: List[str] = field(default_factory=lambda: [
        'google-analytics', 'doubleclick', 'facebook', 'analytics',
        'gtag', 'googletag', 'clarity', 'hotjar'
    ])
    include_console_logs: bool = True
    include_dom_events: bool = False
    max_entries_per_tab: int = 10000
    save_intermediate: bool = True
    intermediate_interval: int = 30

class ConnectionManager:
    """Manages WebSocket connections with retry logic"""
    
    def __init__(self, max_attempts: int = 5, delay: int = 2):
        self.max_attempts = max_attempts
        self.delay = delay
        self.active_connections: Dict[str, websocket.WebSocket] = {}
        self.lock = threading.Lock()
        
    def connect(self, ws_url: str, tab_id: str) -> Optional[websocket.WebSocket]:
        """Connect with retry logic"""
        for attempt in range(self.max_attempts):
            try:
                logger.info(f"Connecting to {tab_id[:20]} (attempt {attempt + 1}/{self.max_attempts})")
                ws = websocket.create_connection(
                    ws_url,
                    timeout=10,
                    enable_multithread=True
                )
                
                # Enable monitoring
                ws.send(json.dumps({"id": 1, "method": "Network.enable"}))
                ws.send(json.dumps({"id": 2, "method": "Page.enable"}))
                ws.send(json.dumps({"id": 3, "method": "Runtime.enable"}))
                
                with self.lock:
                    self.active_connections[tab_id] = ws
                
                logger.info(f"✅ Connected to {tab_id[:20]}")
                return ws
                
            except websocket.WebSocketException as e:
                logger.warning(f"WebSocket connection failed (attempt {attempt + 1}): {e}")
                time.sleep(self.delay * (attempt + 1))
            except Exception as e:
                logger.error(f"Unexpected error connecting: {e}")
                time.sleep(self.delay)
                
        logger.error(f"❌ Failed to connect to {tab_id[:20]} after {self.max_attempts} attempts")
        return None
    
    def disconnect(self, tab_id: str):
        """Disconnect a specific tab"""
        with self.lock:
            if tab_id in self.active_connections:
                try:
                    self.active_connections[tab_id].close()
                except:
                    pass
                del self.active_connections[tab_id]
    
    def disconnect_all(self):
        """Disconnect all tabs"""
        with self.lock:
            for tab_id, ws in list(self.active_connections.items()):
                try:
                    ws.close()
                except:
                    pass
            self.active_connections.clear()

class JourneyHARCapture:
    """Main capture class with robust error handling"""
    
    def __init__(self, config: CaptureConfig = None):
        self.config = config or CaptureConfig()
        self.tabs: Dict[str, TabInfo] = {}
        self.session_data = {
            'entries': [],
            'navigation_events': [],
            'tab_changes': [],
            'journey_timeline': [],
            'console_logs': [],
            'errors': [],
            'statistics': {
                'total_entries': 0,
                'total_requests': 0,
                'total_responses': 0,
                'total_tabs': 0,
                'tab_changes': 0,
                'navigation_events': 0,
                'capture_start': None,
                'capture_end': None,
                'duration_seconds': 0
            }
        }
        self.session_start_time: Optional[datetime] = None
        self.session_end_time: Optional[datetime] = None
        self.stop_event = threading.Event()
        self.capture_threads: Dict[str, threading.Thread] = {}
        self.monitor_thread: Optional[threading.Thread] = None
        self.connection_manager = ConnectionManager(
            max_attempts=self.config.max_reconnect_attempts,
            delay=self.config.reconnect_delay
        )
        self.entry_counter = 0
        self.is_running = False
        self.lock = threading.Lock()
        self.intermediate_save_timer = 0
        self.pending_requests: Dict[str, Dict] = {}
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
    def _signal_handler(self, signum, frame):
        """Handle interrupt signals gracefully"""
        logger.info(f"Received signal {signum}, stopping capture...")
        self.stop_event.set()
        
    def connect_to_chrome(self) -> List[Dict]:
        """Connect to Chrome debugging port with retry"""
        for attempt in range(3):
            try:
                response = requests.get(
                    f"http://127.0.0.1:{self.config.port}/json",
                    timeout=5
                )
                response.raise_for_status()
                return response.json()
            except requests.exceptions.ConnectionError:
                logger.warning(f"Connection attempt {attempt + 1}/3 failed")
                time.sleep(1)
            except Exception as e:
                logger.error(f"Error connecting to Chrome: {e}")
                time.sleep(1)
        return []
    
    def get_page_tabs(self) -> Dict[str, TabInfo]:
        """Get all page tabs with enhanced error handling"""
        tabs_data = self.connect_to_chrome()
        if not tabs_data:
            return {}
        
        page_tabs = [t for t in tabs_data if t.get('type') == 'page']
        
        with self.lock:
            for tab in page_tabs:
                tab_id = tab.get('id')
                if tab_id not in self.tabs:
                    self.tabs[tab_id] = TabInfo(
                        id=tab_id,
                        title=tab.get('title', 'Untitled'),
                        url=tab.get('url', ''),
                        ws_url=tab.get('webSocketDebuggerUrl')
                    )
        return self.tabs
    
    def should_skip_request(self, url: str) -> bool:
        """Check if request should be skipped"""
        if not url:
            return True
        
        url_lower = url.lower()
        
        # Skip patterns
        for pattern in self.config.skip_patterns:
            if pattern in url_lower:
                return True
        
        # Skip data URIs and blob
        if url_lower.startswith('data:') or url_lower.startswith('blob:'):
            return True
        
        # Skip chrome internal
        if url_lower.startswith('chrome://'):
            return True
        
        return False
    
    def capture_tab_continuously(self, tab_id: str):
        """Continuously capture a tab with robust error handling"""
        if tab_id not in self.tabs:
            logger.error(f"Tab {tab_id} not found")
            return
        
        tab_info = self.tabs[tab_id]
        tab_info.status = CaptureStatus.CONNECTING
        
        try:
            # Get WebSocket URL (refresh if needed)
            if not tab_info.ws_url:
                tabs = self.connect_to_chrome()
                for tab in tabs:
                    if tab.get('id') == tab_id:
                        tab_info.ws_url = tab.get('webSocketDebuggerUrl')
                        break
            
            if not tab_info.ws_url:
                logger.error(f"No WebSocket URL for tab {tab_id}")
                tab_info.status = CaptureStatus.ERROR
                return
            
            # Connect with retry
            ws = self.connection_manager.connect(tab_info.ws_url, tab_id)
            if not ws:
                tab_info.status = CaptureStatus.ERROR
                return
            
            tab_info.websocket = ws
            tab_info.capture_started = datetime.now().isoformat()
            tab_info.is_active = True
            tab_info.status = CaptureStatus.CAPTURING
            tab_info.total_responses = 0
            
            logger.info(f"✅ Capturing: {tab_info.title[:50]}")
            
            request_count = 0
            response_count = 0
            local_pending = {}
            last_activity = time.time()
            
            while not self.stop_event.is_set():
                try:
                    ws.settimeout(self.config.websocket_timeout)
                    msg = ws.recv()
                    
                    if not msg:
                        continue
                    
                    data = json.loads(msg)
                    last_activity = time.time()
                    
                    if 'method' not in data:
                        continue
                    
                    method = data['method']
                    params = data.get('params', {})
                    
                    if method == 'Network.requestWillBeSent':
                        request = params.get('request', {})
                        request_id = params.get('requestId')
                        url = request.get('url', '')
                        
                        # Skip unwanted requests
                        if self.should_skip_request(url):
                            continue
                        
                        with self.lock:
                            entry = {
                                'tab_id': tab_id,
                                'tab_title': tab_info.title,
                                'tab_url': tab_info.url,
                                'request': {
                                    'method': request.get('method', ''),
                                    'url': url,
                                    'headers': request.get('headers', {}),
                                    'postData': request.get('postData', {})
                                },
                                'response': {
                                    'status': 0,
                                    'statusText': '',
                                    'headers': {},
                                    'content': {'mimeType': '', 'size': 0}
                                },
                                'timings': {
                                    'blocked': -1,
                                    'dns': -1,
                                    'connect': -1,
                                    'send': 0,
                                    'wait': 0,
                                    'receive': 0
                                },
                                'time': 0,
                                'startedDateTime': datetime.fromtimestamp(time.time()).isoformat(),
                                'request_time': time.time(),
                                'request_id': request_id,
                                'entry_number': self.entry_counter,
                                'capture_time': datetime.now().isoformat()
                            }
                            
                            self.entry_counter += 1
                            tab_info.request_map[request_id] = entry
                            local_pending[request_id] = time.time()
                            request_count += 1
                            tab_info.total_requests += 1
                            
                    elif method == 'Network.responseReceived':
                        request_id = params.get('requestId')
                        
                        # Check both maps
                        entry = None
                        if request_id in tab_info.request_map:
                            entry = tab_info.request_map[request_id]
                        elif request_id in local_pending:
                            entry = local_pending[request_id]
                            
                        if entry:
                            response = params.get('response', {})
                            status = response.get('status', 0)
                            
                            # Skip non-successful responses if desired
                            if status == 204 or (200 <= status < 300):
                                with self.lock:
                                    entry['response']['status'] = status
                                    entry['response']['statusText'] = response.get('statusText', '')
                                    entry['response']['headers'] = response.get('headers', {})
                                    entry['response']['content']['mimeType'] = response.get('mimeType', '')
                                    entry['response']['content']['size'] = response.get('contentSize', 0)
                                    entry['response_time'] = time.time()
                                    
                                    if 'request_time' in entry:
                                        entry['time'] = (entry['response_time'] - entry['request_time']) * 1000
                                    
                                    # Add to entries
                                    tab_info.entries.append(entry)
                                    self.session_data['entries'].append(entry)
                                    response_count += 1
                                    tab_info.total_responses += 1
                                    
                                    # Clean up
                                    if request_id in tab_info.request_map:
                                        del tab_info.request_map[request_id]
                                    if request_id in local_pending:
                                        del local_pending[request_id]
                            
                            # Show progress
                            if response_count % self.config.progress_interval == 0:
                                logger.info(f"📊 [{tab_info.title[:25]}] {response_count} responses")
                    
                    elif method == 'Page.frameNavigated':
                        frame = params.get('frame', {})
                        if frame.get('id') == params.get('frameId'):
                            with self.lock:
                                nav_event = {
                                    'timestamp': datetime.now().isoformat(),
                                    'url': frame.get('url', ''),
                                    'tab_id': tab_id,
                                    'time': time.time(),
                                    'title': tab_info.title
                                }
                                self.session_data['navigation_events'].append(nav_event)
                                tab_info.url = frame.get('url', '')
                                logger.info(f"🔄 [{tab_info.title[:30]}] Navigated to: {frame.get('url', '')[:60]}")
                    
                    elif method == 'Runtime.consoleAPICalled' and self.config.include_console_logs:
                        args = params.get('args', [])
                        if args:
                            with self.lock:
                                console_msg = {
                                    'timestamp': datetime.now().isoformat(),
                                    'tab_id': tab_id,
                                    'type': params.get('type', 'log'),
                                    'message': ' '.join([
                                        str(arg.get('value', '')) 
                                        for arg in args 
                                        if arg.get('value')
                                    ])
                                }
                                if console_msg['message']:
                                    self.session_data['console_logs'].append(console_msg)
                    
                    # Check for tab overload
                    if len(tab_info.entries) > self.config.max_entries_per_tab:
                        logger.warning(f"Tab {tab_id[:20]} reached max entries ({self.config.max_entries_per_tab})")
                        break
                    
                except websocket.WebSocketTimeoutException:
                    # Check if connection is still alive
                    if time.time() - last_activity > 10:
                        logger.warning(f"Timeout for tab {tab_id[:20]}, reconnecting...")
                        # Reconnect
                        ws = self.connection_manager.connect(tab_info.ws_url, tab_id)
                        if ws:
                            tab_info.websocket = ws
                            last_activity = time.time()
                        else:
                            logger.error(f"Failed to reconnect tab {tab_id[:20]}")
                            break
                    continue
                    
                except websocket.WebSocketConnectionClosedException:
                    logger.warning(f"Connection closed for tab {tab_id[:20]}, attempting reconnect...")
                    tab_info.reconnect_attempts += 1
                    
                    if tab_info.reconnect_attempts <= self.config.max_reconnect_attempts:
                        time.sleep(self.config.reconnect_delay)
                        ws = self.connection_manager.connect(tab_info.ws_url, tab_id)
                        if ws:
                            tab_info.websocket = ws
                            last_activity = time.time()
                            logger.info(f"✅ Reconnected tab {tab_id[:20]}")
                        else:
                            logger.error(f"Failed to reconnect tab {tab_id[:20]}")
                            break
                    else:
                        logger.error(f"Max reconnect attempts reached for tab {tab_id[:20]}")
                        break
                        
                except json.JSONDecodeError as e:
                    logger.warning(f"Invalid JSON received: {e}")
                    continue
                    
                except Exception as e:
                    logger.error(f"Unexpected error in capture: {e}")
                    with self.lock:
                        tab_info.errors.append(f"{datetime.now().isoformat()}: {str(e)}")
                    
                    # Attempt to recover
                    if not self.stop_event.is_set():
                        time.sleep(1)
                        try:
                            if ws:
                                ws.close()
                        except:
                            pass
                        ws = self.connection_manager.connect(tab_info.ws_url, tab_id)
                        if ws:
                            tab_info.websocket = ws
                            last_activity = time.time()
                            logger.info(f"✅ Recovered tab {tab_id[:20]}")
                        else:
                            logger.error(f"Failed to recover tab {tab_id[:20]}")
                            break
                    continue
            
            # Clean up
            tab_info.is_active = False
            tab_info.capture_ended = datetime.now().isoformat()
            tab_info.status = CaptureStatus.COMPLETED
            
            # Clean up pending requests
            with self.lock:
                for req_id in list(tab_info.request_map.keys()):
                    del tab_info.request_map[req_id]
            
            logger.info(f"✅ Completed capture for: {tab_info.title[:50]}")
            logger.info(f"   Total responses: {response_count}")
            
        except Exception as e:
            logger.error(f"Fatal error in capture_tab_continuously: {e}")
            tab_info.status = CaptureStatus.ERROR
            tab_info.errors.append(f"{datetime.now().isoformat()}: {str(e)}")
        
        finally:
            # Ensure cleanup
            self.connection_manager.disconnect(tab_id)
    
    def monitor_and_capture_tabs(self):
        """Monitor for new tabs with robust error handling"""
        known_tabs = set(self.tabs.keys())
        logger.info("🔍 Monitoring for new tabs...")
        
        while not self.stop_event.is_set():
            try:
                time.sleep(1.5)
                
                tabs_data = self.connect_to_chrome()
                if not tabs_data:
                    continue
                
                current_tab_ids = {t.get('id') for t in tabs_data if t.get('type') == 'page'}
                
                # Detect new tabs
                new_tabs = current_tab_ids - known_tabs
                if new_tabs:
                    for tab_id in new_tabs:
                        # Skip if stop requested
                        if self.stop_event.is_set():
                            break
                            
                        # Find the new tab details
                        for tab in tabs_data:
                            if tab.get('id') == tab_id:
                                title = tab.get('title', 'Untitled')
                                url = tab.get('url', '')
                                
                                # Skip chrome internal pages
                                if url.startswith('chrome://') or url.startswith('about:'):
                                    continue
                                
                                logger.info(f"🆕 NEW TAB DETECTED: {title[:50]}")
                                logger.info(f"   URL: {url[:80]}")
                                
                                # Add to tabs
                                with self.lock:
                                    self.tabs[tab_id] = TabInfo(
                                        id=tab_id,
                                        title=title,
                                        url=url,
                                        ws_url=tab.get('webSocketDebuggerUrl'),
                                        first_seen=datetime.now().isoformat()
                                    )
                                    
                                    # Record tab change
                                    self.session_data['tab_changes'].append({
                                        'timestamp': datetime.now().isoformat(),
                                        'tab_id': tab_id,
                                        'url': url,
                                        'title': title,
                                        'action': 'created'
                                    })
                                    
                                    self.session_data['journey_timeline'].append({
                                        'timestamp': datetime.now().isoformat(),
                                        'event': 'tab_created',
                                        'tab_id': tab_id,
                                        'title': title,
                                        'url': url
                                    })
                                
                                # Start capturing the new tab
                                if self.tabs[tab_id].ws_url:
                                    logger.info(f"🔄 Starting capture for new tab...")
                                    thread = threading.Thread(
                                        target=self.capture_tab_continuously,
                                        args=(tab_id,),
                                        daemon=True
                                    )
                                    thread.start()
                                    with self.lock:
                                        self.capture_threads[tab_id] = thread
                                break
                    known_tabs = current_tab_ids
                
                # Check for closed tabs
                closed_tabs = known_tabs - current_tab_ids
                if closed_tabs:
                    for tab_id in closed_tabs:
                        if tab_id in self.tabs:
                            logger.info(f"❌ Tab closed: {self.tabs[tab_id].title[:50]}")
                            with self.lock:
                                self.session_data['tab_changes'].append({
                                    'timestamp': datetime.now().isoformat(),
                                    'tab_id': tab_id,
                                    'action': 'closed'
                                })
                                self.session_data['journey_timeline'].append({
                                    'timestamp': datetime.now().isoformat(),
                                    'event': 'tab_closed',
                                    'tab_id': tab_id,
                                    'title': self.tabs[tab_id].title
                                })
                                
                                # Clean up
                                if tab_id in self.capture_threads:
                                    del self.capture_threads[tab_id]
                                
                                if tab_id in self.tabs:
                                    self.tabs[tab_id].status = CaptureStatus.STOPPING
                    known_tabs = current_tab_ids
                
                # Save intermediate results
                if self.config.save_intermediate:
                    self.intermediate_save_timer += 1
                    if self.intermediate_save_timer >= self.config.intermediate_interval:
                        self.save_intermediate_results()
                        self.intermediate_save_timer = 0
                    
            except Exception as e:
                if not self.stop_event.is_set():
                    logger.error(f"Monitor error: {e}")
                    logger.debug(traceback.format_exc())
                time.sleep(2)
    
    def save_intermediate_results(self):
        """Save intermediate results for safety"""
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"intermediate_har_{timestamp}.har"
            
            with self.lock:
                if self.session_data['entries']:
                    har_data = self.build_har_data()
                    with open(filename, 'w') as f:
                        json.dump(har_data, f, indent=2)
                    logger.info(f"💾 Intermediate save: {filename}")
        except Exception as e:
            logger.warning(f"Failed to save intermediate results: {e}")
    
    def build_har_data(self) -> Dict:
        """Build HAR data structure with all captured information"""
        with self.lock:
            har_data = {
                'log': {
                    'version': '1.2',
                    'creator': {
                        'name': 'Journey HAR Capture',
                        'version': '3.0.0',
                        'comment': 'Complete browsing session capture'
                    },
                    'browser': {
                        'name': 'Chrome',
                        'version': 'Auto-detected'
                    },
                    'entries': self.session_data['entries'],
                    'pages': [],
                    'comment': {
                        'session_start': self.session_start_time.isoformat() if self.session_start_time else None,
                        'session_end': self.session_end_time.isoformat() if self.session_end_time else datetime.now().isoformat(),
                        'total_tabs': len(self.tabs),
                        'tab_changes': len(self.session_data['tab_changes']),
                        'navigation_events': len(self.session_data['navigation_events']),
                        'total_entries': len(self.session_data['entries']),
                        'console_logs': len(self.session_data['console_logs']),
                        'errors': len(self.session_data['errors']),
                        'tab_details': {},
                        'journey_timeline': self.session_data['journey_timeline'],
                        'statistics': self.session_data['statistics']
                    }
                }
            }
            
            # Add tab details
            for tab_id, tab_info in self.tabs.items():
                tab_data = {
                    'title': tab_info.title,
                    'url': tab_info.url,
                    'entries_count': len(tab_info.entries),
                    'capture_started': tab_info.capture_started,
                    'capture_ended': tab_info.capture_ended,
                    'first_seen': tab_info.first_seen,
                    'entry_count': tab_info.entry_count,
                    'total_responses': tab_info.total_responses,
                    'total_requests': tab_info.total_requests,
                    'reconnect_attempts': tab_info.reconnect_attempts,
                    'errors': len(tab_info.errors),
                    'status': tab_info.status.value if tab_info.status else 'unknown'
                }
                har_data['log']['comment']['tab_details'][tab_id] = tab_data
            
            # Add pages
            for nav_event in self.session_data['navigation_events']:
                har_data['log']['pages'].append({
                    'startedDateTime': nav_event.get('timestamp'),
                    'title': nav_event.get('title', ''),
                    'pageTimings': {
                        'onContentLoad': 0,
                        'onLoad': 0
                    }
                })
            
            return har_data
    
    def capture_journey(self, initial_tab_ids: List[str]) -> bool:
        """Capture complete journey with robust error handling"""
        self.stop_event.clear()
        self.session_start_time = datetime.now()
        self.is_running = True
        
        logger.info("="*60)
        logger.info("🎯 STARTING JOURNEY CAPTURE")
        logger.info("="*60)
        logger.info(f"   Initial tabs: {len(initial_tab_ids)}")
        logger.info(f"   Duration: {self.config.duration} seconds")
        logger.info(f"   Auto-detect new tabs: YES")
        logger.info(f"   Auto-capture all tabs: YES")
        logger.info(f"   Max reconnect attempts: {self.config.max_reconnect_attempts}")
        logger.info("="*60)
        
        # Get initial tabs
        self.get_page_tabs()
        
        # Start monitoring thread
        self.monitor_thread = threading.Thread(target=self.monitor_and_capture_tabs, daemon=True)
        self.monitor_thread.start()
        
        # Start capturing initial tabs
        for tab_id in initial_tab_ids:
            if tab_id in self.tabs:
                logger.info(f"🎯 Starting initial tab: {self.tabs[tab_id].title[:50]}")
                thread = threading.Thread(
                    target=self.capture_tab_continuously,
                    args=(tab_id,),
                    daemon=True
                )
                thread.start()
                with self.lock:
                    self.capture_threads[tab_id] = thread
            else:
                logger.warning(f"⚠️ Tab {tab_id} not available")
        
        logger.info("\n⏳ JOURNEY RECORDING IN PROGRESS...")
        logger.info("   🎯 Interact with the browser normally")
        logger.info("   📱 All tabs will be automatically captured")
        logger.info("   🔄 New tabs will be detected and captured")
        logger.info("   ⏹️ Press Ctrl+C to stop early")
        logger.info(f"\n   Waiting {self.config.duration} seconds...\n")
        
        # Wait for the specified duration
        start_time = time.time()
        try:
            while time.time() - start_time < self.config.duration and not self.stop_event.is_set():
                # Show progress every few seconds
                elapsed = int(time.time() - start_time)
                if elapsed % 10 == 0:
                    with self.lock:
                        active_tabs = sum(1 for t in self.tabs.values() if t.is_active)
                        total_entries = len(self.session_data['entries'])
                        total_tabs = len(self.tabs)
                    logger.info(f"   ⏱️ {elapsed}s elapsed | Active tabs: {active_tabs} | Entries: {total_entries} | Tabs: {total_tabs}")
                time.sleep(0.5)
                
        except KeyboardInterrupt:
            logger.info("\n\n⏹️ Stopped by user")
        
        # Stop everything
        logger.info("\n🛑 Stopping all captures...")
        self.stop_event.set()
        self.is_running = False
        self.session_end_time = datetime.now()
        
        # Wait for threads to finish
        for tab_id, thread in list(self.capture_threads.items()):
            try:
                thread.join(timeout=3)
            except:
                pass
        
        if self.monitor_thread:
            try:
                self.monitor_thread.join(timeout=3)
            except:
                pass
        
        # Close all connections
        self.connection_manager.disconnect_all()
        
        # Update statistics
        with self.lock:
            self.session_data['statistics'] = {
                'total_entries': len(self.session_data['entries']),
                'total_requests': sum(t.total_requests for t in self.tabs.values()),
                'total_responses': sum(t.total_responses for t in self.tabs.values()),
                'total_tabs': len(self.tabs),
                'tab_changes': len(self.session_data['tab_changes']),
                'navigation_events': len(self.session_data['navigation_events']),
                'capture_start': self.session_start_time.isoformat(),
                'capture_end': self.session_end_time.isoformat(),
                'duration_seconds': (self.session_end_time - self.session_start_time).total_seconds()
            }
        
        logger.info("✅ Capture completed")
        return True
    
    def save_har(self, output_file: Optional[str] = None) -> str:
        """Save captured data with comprehensive error handling"""
        try:
            if not output_file:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                output_file = f"journey_har_{timestamp}.har"
            
            # Build HAR data
            har_data = self.build_har_data()
            
            # Write to file
            with open(output_file, 'w') as f:
                json.dump(har_data, f, indent=2)
            
            file_size = os.path.getsize(output_file)
            logger.info(f"\n💾 Saved to: {output_file}")
            logger.info(f"📊 File size: {file_size / 1024:.2f} KB")
            
            # Generate summary
            self.generate_summary()
            
            # Also save errors if any
            if self.session_data['errors']:
                error_file = output_file.replace('.har', '_errors.json')
                with open(error_file, 'w') as f:
                    json.dump(self.session_data['errors'], f, indent=2)
                logger.info(f"⚠️ Errors saved to: {error_file}")
            
            return output_file
            
        except Exception as e:
            logger.error(f"Failed to save HAR file: {e}")
            logger.debug(traceback.format_exc())
            return ""
    
    def generate_summary(self):
        """Generate comprehensive summary with statistics"""
        with self.lock:
            entries = self.session_data['entries']
            
            if not entries:
                logger.warning("⚠️ No entries captured")
                return
            
            logger.info("\n" + "="*60)
            logger.info("📊 JOURNEY SUMMARY")
            logger.info("="*60)
            logger.info(f"   Session duration: {self.session_start_time} to {self.session_end_time}")
            logger.info(f"   Duration: {self.session_data['statistics']['duration_seconds']:.0f} seconds")
            logger.info(f"   Total tabs captured: {len(self.tabs)}")
            logger.info(f"   Total entries: {len(entries)}")
            logger.info(f"   Tab changes: {len(self.session_data['tab_changes'])}")
            logger.info(f"   Navigations: {len(self.session_data['navigation_events'])}")
            logger.info(f"   Console logs: {len(self.session_data['console_logs'])}")
            logger.info(f"   Errors: {len(self.session_data['errors'])}")
            
            # Tab statistics
            logger.info("\n   📑 Tab Statistics:")
            for tab_id, tab_info in self.tabs.items():
                entries_count = len(tab_info.entries)
                if entries_count > 0:
                    logger.info(f"     • {tab_info.title[:50]}: {entries_count} entries")
                    logger.info(f"       URL: {tab_info.url[:80]}")
                    logger.info(f"       Status: {tab_info.status.value}")
            
            # Status codes
            statuses = defaultdict(int)
            methods = defaultdict(int)
            content_types = defaultdict(int)
            
            for entry in entries:
                status = entry.get('response', {}).get('status', 0)
                statuses[status] += 1
                
                method = entry.get('request', {}).get('method', '')
                methods[method] += 1
                
                mime_type = entry.get('response', {}).get('content', {}).get('mimeType', '')
                if mime_type:
                    content_types[mime_type.split(';')[0]] += 1
            
            logger.info("\n   ✅ Status Codes:")
            for status, count in sorted(statuses.items()):
                emoji = "✅" if 200 <= status < 300 else "⚠️" if 300 <= status < 400 else "❌"
                logger.info(f"     {emoji} {status}: {count}")
            
            logger.info("\n   🔧 HTTP Methods:")
            for method, count in sorted(methods.items(), key=lambda x: x[1], reverse=True)[:5]:
                logger.info(f"     • {method}: {count}")
            
            if content_types:
                logger.info("\n   📄 Content Types:")
                for ctype, count in sorted(content_types.items(), key=lambda x: x[1], reverse=True)[:5]:
                    logger.info(f"     • {ctype}: {count}")
            
            # Timeline summary
            if self.session_data['journey_timeline']:
                logger.info("\n   🔄 Journey Timeline:")
                for event in self.session_data['journey_timeline'][:10]:
                    timestamp = event.get('timestamp', '')[:19]
                    event_type = event.get('event', '')
                    if event_type == 'tab_created':
                        title = event.get('title', '')[:40]
                        logger.info(f"     • {timestamp} - 🆕 Tab opened: {title}")
                    elif event_type == 'tab_closed':
                        title = event.get('title', '')[:40]
                        logger.info(f"     • {timestamp} - ❌ Tab closed: {title}")
            
            # Errors summary
            if self.session_data['errors']:
                logger.info(f"\n   ⚠️ Errors ({len(self.session_data['errors'])}):")
                for error in self.session_data['errors'][:5]:
                    logger.info(f"     • {error[:100]}")
            
            logger.info("\n" + "="*60)

def check_chrome_debugging(port: int) -> bool:
    """Check if Chrome is running with debugging enabled"""
    try:
        response = requests.get(f"http://127.0.0.1:{port}/json", timeout=2)
        return response.status_code == 200
    except:
        return False

def main():
    """Main entry point with user interaction"""
    try:
        print("╔" + "="*60 + "╗")
        print("║" + " "*12 + "🛡️ ROBUST JOURNEY HAR CAPTURE" + " "*13 + "║")
        print("║" + " "*8 + "Production-grade complete session capture" + " "*8 + "║")
        print("╚" + "="*60 + "╝")
        print()
        
        # Get port
        port_input = input("Chrome debugging port [9258]: ").strip()
        port = int(port_input) if port_input else 9258
        
        # Check Chrome
        if not check_chrome_debugging(port):
            logger.error(f"❌ Chrome debugging not available on port {port}")
            print("\n   To enable Chrome debugging:")
            print(f"   1. Close all Chrome windows")
            print(f"   2. Open Chrome with: chrome --remote-debugging-port={port}")
            print(f"   3. Or use: /Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome --remote-debugging-port={port}")
            print(f"   4. Then run this script again")
            return
        
        # Create config
        config = CaptureConfig(port=port)
        
        # Customize duration
        duration_input = input("\nCapture duration (seconds) [60]: ").strip()
        if duration_input:
            try:
                config.duration = int(duration_input)
            except ValueError:
                logger.warning("Invalid duration, using default 60 seconds")
        
        # Initialize capture
        capture = JourneyHARCapture(config)
        
        # Get tabs
        tabs = capture.get_page_tabs()
        if not tabs:
            logger.error("❌ No Chrome tabs found. Please open some tabs first.")
            return
        
        # Show tabs
        print(f"\n📑 Initial tabs on port {port}:")
        tab_ids = list(tabs.keys())
        for i, (tab_id, tab_info) in enumerate(tabs.items(), 1):
            title = tab_info.title[:60]
            url = tab_info.url[:80] if tab_info.url else ""
            status = "✓" if tab_info.ws_url else "✗"
            print(f"  {i}. {status} {title}")
            if url:
                print(f"     {url}")
        
        # Select tabs
        print("\n🎯 Select tabs to include in journey:")
        selected = []
        
        while True:
            choice = input("Enter tab number (or 'all' or 'done'): ").strip()
            if choice.lower() == 'done':
                break
            elif choice.lower() == 'all':
                selected = [t_id for t_id in tab_ids if tabs[t_id].ws_url]
                print(f"✅ Selected all {len(selected)} available tabs")
                break
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(tab_ids):
                    tab_id = tab_ids[idx]
                    if tab_id not in selected:
                        if tabs[tab_id].ws_url:
                            selected.append(tab_id)
                            print(f"✅ Added: {tabs[tab_id].title[:50]}")
                        else:
                            logger.warning("⚠️ Tab doesn't have WebSocket URL")
                    else:
                        print("ℹ️ Already selected")
                else:
                    logger.warning("❌ Invalid tab number")
            except ValueError:
                logger.warning("❌ Invalid input")
        
        if not selected:
            logger.error("❌ No tabs selected")
            return
        
        # Confirm
        print("\n" + "="*60)
        print(f"📋 JOURNEY CONFIGURATION:")
        print(f"   Initial tabs: {len(selected)}")
        print(f"   Duration: {config.duration} seconds")
        print(f"   Auto-detect new tabs: YES")
        print(f"   Auto-capture all tabs: YES")
        print(f"   Max reconnect attempts: {config.max_reconnect_attempts}")
        print("="*60)
        
        confirm = input("\nStart journey capture? (y/n) [y]: ").strip().lower()
        if confirm == 'n':
            print("❌ Cancelled")
            return
        
        # Start capture
        try:
            capture.capture_journey(selected)
            output_file = capture.save_har()
            
            if output_file:
                print("\n✅ Journey capture complete!")
                print(f"   📁 HAR file: {output_file}")
                print("   🔍 Open in Chrome DevTools > Network tab to analyze")
                print("   📊 Contains complete browsing session with all tabs")
                print("   📝 Check har_capture.log for detailed logs")
            else:
                print("\n⚠️ Capture completed but HAR file save failed")
                
        except KeyboardInterrupt:
            print("\n\n⏹️ Interrupted by user")
            if capture:
                capture.save_har()
        except Exception as e:
            logger.error(f"❌ Fatal error: {e}")
            logger.debug(traceback.format_exc())
            if capture:
                capture.save_har("error_recovery_har.har")
        
    except KeyboardInterrupt:
        print("\n\n⏹️ Interrupted by user")
    except Exception as e:
        logger.error(f"❌ Unhandled error: {e}")
        logger.debug(traceback.format_exc())

if __name__ == "__main__":
    main()
