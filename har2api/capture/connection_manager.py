"""
WebSocket connection management for CDP capture
"""

import websocket
import json
import time
import threading
from typing import Dict, Optional, List
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manage WebSocket connections with retry logic"""
    
    def __init__(self, max_attempts: int = 5, delay: int = 2):
        self.max_attempts = max_attempts
        self.delay = delay
        self.active_connections: Dict[str, websocket.WebSocket] = {}
        self.lock = threading.Lock()
        self.is_running = False
        self.monitor_threads: Dict[str, threading.Thread] = {}
        
    def connect(self, ws_url: str, tab_id: str, timeout: int = 10) -> Optional[websocket.WebSocket]:
        """Connect with retry logic"""
        for attempt in range(self.max_attempts):
            try:
                logger.debug(f"Connecting to {tab_id[:20]} (attempt {attempt + 1}/{self.max_attempts})")
                
                ws = websocket.create_connection(
                    ws_url,
                    timeout=timeout,
                    enable_multithread=True
                )
                
                # Enable required domains
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
                
            if tab_id in self.monitor_threads:
                self.monitor_threads[tab_id] = None
    
    def disconnect_all(self):
        """Disconnect all tabs"""
        with self.lock:
            for tab_id, ws in list(self.active_connections.items()):
                try:
                    ws.close()
                except:
                    pass
            self.active_connections.clear()
            self.monitor_threads.clear()
    
    def monitor_connection(self, tab_id: str, callback=None):
        """Monitor a connection and reconnect if needed"""
        def monitor():
            while self.is_running:
                try:
                    ws = self.active_connections.get(tab_id)
                    if not ws:
                        time.sleep(1)
                        continue
                    
                    # Check connection health
                    try:
                        ws.settimeout(1)
                        ws.send(json.dumps({"id": 999, "method": "Runtime.evaluate", 
                                          "params": {"expression": "1+1"}}))
                        # Check for response
                        response = ws.recv()
                        # Connection is healthy
                    except websocket.WebSocketTimeoutException:
                        # No response, connection may be dead
                        logger.warning(f"Connection timeout for {tab_id[:20]}, reconnecting...")
                        self._reconnect(tab_id)
                    except Exception as e:
                        logger.warning(f"Connection issue for {tab_id[:20]}: {e}")
                        self._reconnect(tab_id)
                    
                    time.sleep(5)
                except Exception as e:
                    logger.error(f"Monitor error for {tab_id[:20]}: {e}")
                    time.sleep(2)
        
        thread = threading.Thread(target=monitor, daemon=True)
        self.monitor_threads[tab_id] = thread
        thread.start()
    
    def _reconnect(self, tab_id: str):
        """Reconnect a tab"""
        with self.lock:
            if tab_id in self.active_connections:
                try:
                    self.active_connections[tab_id].close()
                except:
                    pass
                del self.active_connections[tab_id]
        
        # Try to reconnect (implementation would need the original URL)
        # This would require storing the original URL
        pass
    
    def get_active_connections(self) -> List[str]:
        """Get list of active tab IDs"""
        with self.lock:
            return list(self.active_connections.keys())
    
    def is_connected(self, tab_id: str) -> bool:
        """Check if a tab is connected"""
        with self.lock:
            return tab_id in self.active_connections
