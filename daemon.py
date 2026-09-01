# daemon.py - Fixed version with proper integration with cdpv119.py
import asyncio
import json
import logging
import signal
import time
import os
import sys
from pathlib import Path
from typing import Optional, Dict, Any

import websockets
import requests

# Import ChromeSessionManager from cdpv119
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cdpv119 import ChromeSessionManager, Config, logger

class ChromeDaemon:
    def __init__(self):
        self.manager = ChromeSessionManager()
        self.active_connections = {}
        self.logger = logging.getLogger(__name__)
        self._msg_counter = 0
        self.session_file = Path(Config().session_info_file)

    def load_session_info(self) -> dict:
        """Load the session info from your existing JSON file"""
        try:
            with open(self.session_file, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            self.logger.error(f"Session file not found: {self.session_file}")
            return {"sessions": {}}
        except json.JSONDecodeError:
            self.logger.error(f"Invalid JSON in session file: {self.session_file}")
            return {"sessions": {}}

    def get_session(self, name: str) -> Optional[dict]:
        """Get session details by name"""
        data = self.load_session_info()
        for session_id, session in data.get('sessions', {}).items():
            if session.get('name') == name:
                return {
                    'id': int(session_id),
                    **session
                }
        return None

    def get_session_by_id(self, session_id: int) -> Optional[dict]:
        """Get session details by ID"""
        data = self.load_session_info()
        session = data.get('sessions', {}).get(str(session_id))
        if session:
            return {
                'id': session_id,
                **session
            }
        return None

    async def get_websocket_connection(self, session_name: str):
        """Get or create a WebSocket connection to Chrome"""
        # Check if we have an active connection
        if session_name in self.active_connections:
            ws = self.active_connections[session_name]
            try:
                await ws.ping()
                return ws
            except Exception:
                self.logger.warning(f"WebSocket connection for {session_name} is dead, reconnecting...")
                del self.active_connections[session_name]

        # Get session info
        session = self.get_session(session_name)
        if not session:
            self.logger.error(f"Session {session_name} not found")
            return None

        # Check if session is running
        if session.get('status') != 'running':
            self.logger.error(f"Session {session_name} is not running (status: {session.get('status')})")
            return None

        # Build WebSocket URL
        port = session.get('port')
        ws_id = session.get('current_ws_id')

        if not port or not ws_id:
            self.logger.error(f"Session {session_name} missing port or WebSocket ID")
            self.logger.info(f"Port: {port}, WS ID: {ws_id}")
            
            # Try to get WebSocket ID from Chrome directly
            try:
                response = requests.get(f"http://127.0.0.1:{port}/json", timeout=3)
                if response.status_code == 200:
                    tabs = response.json()
                    for tab in tabs:
                        if tab.get('type') == 'page':
                            ws_id = tab.get('id')
                            if ws_id:
                                self.logger.info(f"✅ Found WebSocket ID from Chrome: {ws_id}")
                                # Update session info
                                data = self.load_session_info()
                                for sid, s in data.get('sessions', {}).items():
                                    if s.get('name') == session_name:
                                        s['current_ws_id'] = ws_id
                                        s['status'] = 'running'
                                        break
                                with open(self.session_file, 'w') as f:
                                    json.dump(data, f, indent=2)
                                break
            except Exception as e:
                self.logger.error(f"Failed to get WebSocket ID from Chrome: {e}")
            
            # Try again after update
            session = self.get_session(session_name)
            ws_id = session.get('current_ws_id') if session else None
            if not ws_id:
                return None

        ws_url = f"ws://127.0.0.1:{port}/devtools/page/{ws_id}"
        self.logger.info(f"Connecting to WebSocket: {ws_url}")

        try:
            ws = await websockets.connect(
                ws_url,
                ping_interval=20,
                ping_timeout=10,
                close_timeout=10
            )
            self.active_connections[session_name] = ws
            self.logger.info(f"✅ Connected to WebSocket for session {session_name}")
            return ws
        except Exception as e:
            self.logger.error(f"❌ Failed to connect to WebSocket: {e}")
            return None

    async def execute_cdp_command(self, session_name: str, method: str, params: dict = None) -> dict:
        """Execute a CDP command and return the response"""
        ws = await self.get_websocket_connection(session_name)
        if not ws:
            return {'error': 'No WebSocket connection'}

        self._msg_counter += 1
        msg_id = self._msg_counter

        command = {
            'id': msg_id,
            'method': method,
            'params': params or {}
        }

        self.logger.debug(f"Sending command: {method} (id: {msg_id})")

        try:
            await ws.send(json.dumps(command))
            response = await asyncio.wait_for(ws.recv(), timeout=30.0)
            result = json.loads(response)

            if 'error' in result:
                self.logger.error(f"CDP error: {result['error']}")
                return {'error': result['error']}

            return result
        except asyncio.TimeoutError:
            self.logger.error(f"Command timeout for {method}")
            return {'error': 'Command timeout'}
        except websockets.exceptions.ConnectionClosed:
            self.logger.error(f"WebSocket connection closed")
            if session_name in self.active_connections:
                del self.active_connections[session_name]
            return {'error': 'WebSocket connection closed'}
        except Exception as e:
            self.logger.error(f"Command error: {e}")
            return {'error': str(e)}

    async def start_session(self, name: str, url: str = "https://unstop.com/") -> Dict[str, Any]:
        """Start a Chrome session using the ChromeSessionManager"""
        self.logger.info(f"Starting session {name}")
        
        # Check if session exists
        session = self.get_session(name)
        
        if session:
            session_id = session['id']
            
            # Check if already running
            if session.get('status') == 'running':
                # Verify it's actually running
                if session.get('pid'):
                    try:
                        os.kill(session['pid'], 0)
                        # Session is running, try to connect
                        ws = await self.get_websocket_connection(name)
                        return {
                            'success': True,
                            'session': session,
                            'pid': session.get('pid'),
                            'ws_connected': ws is not None
                        }
                    except OSError:
                        # Process is dead, update status
                        self.logger.warning(f"Session {name} PID {session['pid']} is dead")
                        self.manager.db.stop_session(session_id)
                        session['status'] = 'stopped'
            
            # Start the session using the manager
            try:
                # Start in a separate thread to avoid blocking the event loop
                import threading
                def start_in_background():
                    self.manager.start_session(session_id)
                
                thread = threading.Thread(target=start_in_background)
                thread.daemon = True
                thread.start()
                
                # Wait for session to start
                for i in range(15):
                    await asyncio.sleep(1)
                    updated = self.get_session(name)
                    if updated and updated.get('status') == 'running':
                        ws = await self.get_websocket_connection(name)
                        return {
                            'success': True,
                            'session': updated,
                            'pid': updated.get('pid'),
                            'ws_connected': ws is not None
                        }
                
                return {
                    'success': False,
                    'error': 'Session failed to start within timeout',
                    'session': session
                }
                
            except Exception as e:
                self.logger.error(f"Failed to start session: {e}")
                return {'success': False, 'error': str(e)}
        else:
            # Create new session
            return await self._create_new_session(name, url)
    
    async def _create_new_session(self, name: str, url: str) -> Dict[str, Any]:
        """Create a new session"""
        self.logger.info(f"Creating new session {name}")
        
        try:
            # Get a free port
            config = Config()
            used_ports = self.manager.db.get_all_ports()
            port = config.debug_port_start
            for p in range(config.debug_port_start, config.debug_port_end + 1):
                if p not in used_ports:
                    port = p
                    break
            
            profile_dir = os.path.join(config.base_profile_dir, name)
            os.makedirs(profile_dir, exist_ok=True)
            
            # Create session in DB
            session_id = self.manager.db.create_session(name, url, port, profile_dir)
            
            # Start the session
            import threading
            def start_in_background():
                self.manager.start_session(session_id)
            
            thread = threading.Thread(target=start_in_background)
            thread.daemon = True
            thread.start()
            
            # Wait for it to start
            for i in range(15):
                await asyncio.sleep(1)
                session = self.get_session(name)
                if session and session.get('status') == 'running':
                    ws = await self.get_websocket_connection(name)
                    return {
                        'success': True,
                        'session': session,
                        'pid': session.get('pid'),
                        'ws_connected': ws is not None
                    }
            
            return {
                'success': False,
                'error': 'Session creation failed',
                'session': None
            }
            
        except Exception as e:
            self.logger.error(f"Failed to create session: {e}")
            return {'success': False, 'error': str(e)}

    async def stop_session(self, name: str) -> dict:
        """Stop a Chrome session"""
        session = self.get_session(name)
        if not session:
            return {'error': 'Session not found'}

        try:
            # Use the manager to stop
            self.manager.stop_session(session['id'])
            
            # Clean up WebSocket connection
            if name in self.active_connections:
                try:
                    await self.active_connections[name].close()
                except:
                    pass
                del self.active_connections[name]

            return {'success': True, 'session': name}
        except Exception as e:
            return {'error': str(e)}

    async def navigate(self, session_name: str, url: str) -> dict:
        """Navigate to URL"""
        self.logger.info(f"Navigating {session_name} to {url}")
        return await self.execute_cdp_command(
            session_name,
            'Page.navigate',
            {'url': url}
        )

    async def evaluate(self, session_name: str, expression: str) -> dict:
        """Execute JavaScript"""
        return await self.execute_cdp_command(
            session_name,
            'Runtime.evaluate',
            {'expression': expression, 'returnByValue': True}
        )

    async def click(self, session_name: str, selector: str) -> dict:
        """Click an element by CSS selector"""
        js = f"""
        (function() {{
            const el = document.querySelector('{selector}');
            if (!el) return {{error: 'Element not found'}};
            el.click();
            return {{success: true}};
        }})()
        """
        return await self.evaluate(session_name, js)

    async def get_html(self, session_name: str) -> dict:
        """Get full page HTML"""
        result = await self.evaluate(session_name, 'document.documentElement.outerHTML')
        if 'result' in result and 'result' in result['result']:
            return {'html': result['result']['result']['value']}
        return {'error': 'Failed to get HTML'}

    async def get_url(self, session_name: str) -> dict:
        """Get current page URL"""
        result = await self.evaluate(session_name, 'window.location.href')
        if 'result' in result and 'result' in result['result']:
            return {'url': result['result']['result']['value']}
        return {'error': 'Failed to get URL'}

    async def screenshot(self, session_name: str) -> dict:
        """Take screenshot"""
        result = await self.execute_cdp_command(
            session_name,
            'Page.captureScreenshot',
            {'format': 'png', 'fromSurface': True}
        )
        if 'result' in result and 'data' in result['result']:
            return {'screenshot': result['result']['data']}
        return {'error': 'Failed to capture screenshot'}
