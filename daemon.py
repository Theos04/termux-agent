# daemon.py - Fixed version with proper integer IDs
import asyncio
import json
import logging
import subprocess
import signal
import time
import os
from pathlib import Path
from typing import Optional
import websockets

class ChromeDaemon:
    def __init__(self, session_file="/data/data/com.termux/files/home/chrome-sessions/session_info.json"):
        self.session_file = Path(session_file)
        self.active_connections = {}
        self.logger = logging.getLogger(__name__)
        self._msg_counter = 0  # Simple counter for message IDs

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
                    'id': session_id,
                    **session
                }
        return None

    def get_session_by_id(self, session_id: str) -> Optional[dict]:
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
                # Check if connection is alive with ping
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

        # Build WebSocket URL
        port = session.get('port')
        ws_id = session.get('current_ws_id')
        
        if not port or not ws_id:
            self.logger.error(f"Session {session_name} missing port or WebSocket ID")
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

        # Use a simple incrementing counter for message IDs (ensure integer)
        self._msg_counter += 1
        msg_id = self._msg_counter
        
        command = {
            'id': msg_id,  # This must be a pure integer
            'method': method,
            'params': params or {}
        }

        self.logger.debug(f"Sending command: {method} (id: {msg_id})")

        try:
            # Send command
            await ws.send(json.dumps(command))
            
            # Wait for response
            response = await asyncio.wait_for(ws.recv(), timeout=30.0)
            result = json.loads(response)
            
            # Check for error response
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

    async def navigate(self, session_name: str, url: str) -> dict:
        """Navigate to URL"""
        self.logger.info(f"Navigating {session_name} to {url}")
        result = await self.execute_cdp_command(
            session_name,
            'Page.navigate',
            {'url': url}
        )
        return result

    async def evaluate(self, session_name: str, expression: str) -> dict:
        """Execute JavaScript"""
        result = await self.execute_cdp_command(
            session_name,
            'Runtime.evaluate',
            {'expression': expression, 'returnByValue': True}
        )
        return result

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

    async def start_session(self, name: str, url: str = "https://unstop.com/") -> dict:
        """Start a new Chrome session using your existing manager"""
        # Check if session exists in the info file
        session = self.get_session(name)
        if session:
            # Session exists, try to just connect
            self.logger.info(f"Session {name} already exists, attempting to connect...")
            ws = await self.get_websocket_connection(name)
            if ws:
                return {
                    'success': True,
                    'session': session,
                    'message': 'Session already running'
                }
            else:
                # Session exists but not running, might need to start it
                pass
        
        # Use your existing cdpv119.py to start the session
        manager_path = Path("/data/data/com.termux/files/home/automation/chrome-launcher/cdpv119.py")
        if not manager_path.exists():
            return {'success': False, 'error': f'Manager not found at {manager_path}'}
        
        # Start the session
        cmd = [
            "python",
            str(manager_path),
            "--start",
            "--session", name
        ]

        try:
            self.logger.info(f"Starting session {name} via cdpv119.py")
            proc = subprocess.Popen(cmd)
            await asyncio.sleep(5)  # Wait for session to start
            
            # Check if session exists now
            session = self.get_session(name)
            if session:
                # Try to connect WebSocket
                ws = await self.get_websocket_connection(name)
                return {
                    'success': True,
                    'session': session,
                    'pid': proc.pid if proc.pid else None,
                    'ws_connected': ws is not None
                }
            else:
                return {'success': False, 'error': 'Session not created'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    async def stop_session(self, name: str) -> dict:
        """Stop a Chrome session"""
        session = self.get_session(name)
        if not session:
            return {'error': 'Session not found'}

        # Use your existing manager to stop
        manager_path = Path("/data/data/com.termux/files/home/automation/chrome-launcher/cdpv119.py")
        
        try:
            # Use the stop command
            cmd = [
                "python",
                str(manager_path),
                "--stop",
                "--session", name
            ]
            
            self.logger.info(f"Stopping session {name} via cdpv119.py")
            proc = subprocess.Popen(cmd)
            await asyncio.sleep(2)
            
            # Also try to kill the PID directly if it exists
            pid = session.get('pid')
            if pid:
                try:
                    os.kill(pid, signal.SIGTERM)
                except Exception:
                    pass
            
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
