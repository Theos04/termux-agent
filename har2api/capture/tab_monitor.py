"""
Tab monitoring and management for CDP capture
"""

import requests
import time
import threading
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field
from datetime import datetime
import logging

from .connection_manager import ConnectionManager

logger = logging.getLogger(__name__)


@dataclass
class TabInfo:
    """Information about a browser tab"""
    id: str
    title: str = "Untitled"
    url: str = ""
    ws_url: str = ""
    entries: List[Dict] = field(default_factory=list)
    is_active: bool = False
    first_seen: str = field(default_factory=lambda: datetime.now().isoformat())
    last_seen: str = field(default_factory=lambda: datetime.now().isoformat())
    total_requests: int = 0
    total_responses: int = 0


class TabMonitor:
    """Monitor browser tabs for new and closed tabs"""
    
    def __init__(self, port: int = 9222):
        self.port = port
        self.tabs: Dict[str, TabInfo] = {}
        self.known_tabs: Set[str] = set()
        self.is_running = False
        self.monitor_thread: Optional[threading.Thread] = None
        self.on_tab_created = None
        self.on_tab_closed = None
        self.lock = threading.Lock()
        
    def start(self):
        """Start monitoring tabs"""
        self.is_running = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        logger.info("🔍 Tab monitoring started")
    
    def stop(self):
        """Stop monitoring tabs"""
        self.is_running = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=2)
        logger.info("🔍 Tab monitoring stopped")
    
    def get_tabs(self) -> List[Dict]:
        """Get list of tabs from Chrome"""
        try:
            response = requests.get(
                f"http://127.0.0.1:{self.port}/json",
                timeout=5
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.ConnectionError:
            logger.warning(f"Failed to connect to Chrome on port {self.port}")
            return []
        except Exception as e:
            logger.error(f"Error getting tabs: {e}")
            return []
    
    def _monitor_loop(self):
        """Main monitoring loop"""
        while self.is_running:
            try:
                tabs_data = self.get_tabs()
                if not tabs_data:
                    time.sleep(2)
                    continue
                
                # Get page tabs
                page_tabs = [t for t in tabs_data if t.get('type') == 'page']
                current_tab_ids = {t.get('id') for t in page_tabs}
                
                # Detect new tabs
                new_tabs = current_tab_ids - self.known_tabs
                for tab_id in new_tabs:
                    tab_data = next((t for t in page_tabs if t.get('id') == tab_id), None)
                    if tab_data:
                        self._handle_new_tab(tab_data)
                
                # Detect closed tabs
                closed_tabs = self.known_tabs - current_tab_ids
                for tab_id in closed_tabs:
                    self._handle_closed_tab(tab_id)
                
                self.known_tabs = current_tab_ids
                time.sleep(1.5)
                
            except Exception as e:
                logger.error(f"Monitor loop error: {e}")
                time.sleep(2)
    
    def _handle_new_tab(self, tab_data: Dict):
        """Handle a newly detected tab"""
        tab_id = tab_data.get('id')
        title = tab_data.get('title', 'Untitled')
        url = tab_data.get('url', '')
        ws_url = tab_data.get('webSocketDebuggerUrl')
        
        # Skip Chrome internal pages
        if url.startswith('chrome://') or url.startswith('about:'):
            return
        
        with self.lock:
            self.tabs[tab_id] = TabInfo(
                id=tab_id,
                title=title,
                url=url,
                ws_url=ws_url
            )
        
        logger.info(f"🆕 New tab detected: {title[:50]}")
        
        if self.on_tab_created:
            self.on_tab_created(tab_id, self.tabs[tab_id])
    
    def _handle_closed_tab(self, tab_id: str):
        """Handle a closed tab"""
        with self.lock:
            if tab_id in self.tabs:
                title = self.tabs[tab_id].title
                logger.info(f"❌ Tab closed: {title[:50]}")
                del self.tabs[tab_id]
        
        if self.on_tab_closed:
            self.on_tab_closed(tab_id)
    
    def get_tab_info(self, tab_id: str) -> Optional[TabInfo]:
        """Get information about a specific tab"""
        with self.lock:
            return self.tabs.get(tab_id)
    
    def get_active_tabs(self) -> List[TabInfo]:
        """Get all active tabs"""
        with self.lock:
            return list(self.tabs.values())
