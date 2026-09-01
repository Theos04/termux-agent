# chrome_wrapper_enhanced.py - improved version

import os
import sys
import json
import time
import base64
import requests
from pathlib import Path
from typing import Optional, Dict, List, Any
from datetime import datetime
from dataclasses import dataclass

# ============================================================================
# Enhanced ChromeAPI Client with session management
# ============================================================================

class ChromeAPI:
    """Enhanced client with session detection"""
    
    def __init__(self, base_url="http://127.0.0.1:5000"):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.timeout = 30
        self._session_cache = None
        
    def _request(self, method, endpoint, data=None):
        url = f"{self.base_url}{endpoint}"
        try:
            if method == 'GET':
                resp = self.session.get(url)
            else:
                resp = self.session.post(url, json=data)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            return {'error': str(e)}
    
    def list_sessions(self):
        """List all sessions"""
        return self._request('GET', '/sessions')
    
    def get_session(self, name):
        """Get session by name"""
        return self._request('GET', f'/session/{name}/status')
    
    def start_session(self, name, url="https://unstop.com/"):
        """Start a session"""
        return self._request('POST', f'/session/{name}/start', {'url': url})
    
    def stop_session(self, name):
        """Stop a session"""
        return self._request('POST', f'/session/{name}/stop')
    
    def evaluate(self, name, expression):
        """Execute JavaScript"""
        return self._request('POST', f'/session/{name}/evaluate', {'expression': expression})
    
    def get_url(self, name):
        """Get current URL"""
        return self._request('GET', f'/session/{name}/url')
    
    def screenshot(self, name):
        """Take screenshot"""
        return self._request('GET', f'/session/{name}/screenshot')
    
    def get_running_sessions(self):
        """Get all running sessions"""
        result = self.list_sessions()
        if 'error' in result:
            return []
        return [s for s in result.get('sessions', []) if s.get('status') == 'running']
    
    def get_first_running_session(self):
        """Get the first running session name"""
        sessions = self.get_running_sessions()
        return sessions[0]['name'] if sessions else None
    
    def ensure_session(self, name=None, url="https://unstop.com/"):
        """Ensure a session exists and is running"""
        # Try with provided name first
        if name:
            status = self.get_session(name)
            if status.get('exists') and status.get('session', {}).get('status') == 'running':
                return {'success': True, 'name': name, 'action': 'already_running'}
            
            # Try to start it
            result = self.start_session(name, url)
            if result.get('success'):
                return {'success': True, 'name': name, 'action': 'started'}
        
        # Check for any running session
        running = self.get_first_running_session()
        if running:
            return {'success': True, 'name': running, 'action': 'found'}
        
        # No sessions found - create default
        default = 'unstop'
        result = self.start_session(default, url)
        if result.get('success'):
            return {'success': True, 'name': default, 'action': 'created'}
        
        return {'success': False, 'error': 'No session available'}

# ============================================================================
# Interactive wrapper with smart session handling
# ============================================================================

def main():
    api = ChromeAPI()
    
    # Auto-detect sessions
    sessions = api.list_sessions()
    
    print("\n" + "="*60)
    print("🌐 Chrome Automation Wrapper (Smart Session)")
    print("="*60 + "\n")
    
    # Show available sessions
    if 'error' not in sessions and sessions.get('sessions'):
        print("📋 Available sessions:")
        for i, s in enumerate(sessions['sessions'], 1):
            status = "🟢 RUNNING" if s.get('status') == 'running' else "⚪ STOPPED"
            print(f"  {i}. {s['name']} - {s['url'][:40]}... ({status})")
            if s.get('status') == 'running' and s.get('pid'):
                print(f"     PID: {s['pid']}, Port: {s['port']}, WS: {s.get('ws_id', 'None')}")
        print()
        
        # Use first running session or prompt
        running = [s for s in sessions['sessions'] if s.get('status') == 'running']
        if running:
            session_name = running[0]['name']
            print(f"✅ Auto-selected running session: {session_name}")
        else:
            session_name = sessions['sessions'][0]['name']
            print(f"ℹ️  No running sessions. Selected: {session_name}")
    else:
        session_name = 'unstop'
        print(f"ℹ️  No sessions found. Will use default: {session_name}")
    
    print("\n" + "-"*60)
    
    # Main loop
    while True:
        print("\n📌 Commands:")
        print("  status  - Show session status")
        print("  url     - Get current URL")
        print("  eval    - Execute JavaScript")
        print("  list    - List all sessions")
        print("  start   - Start session")
        print("  stop    - Stop session")
        print("  switch  - Switch to another session")
        print("  ss      - Take screenshot")
        print("  exit    - Exit")
        
        cmd = input(f"\n[{session_name}] > ").strip().lower()
        
        if cmd == 'exit':
            print("👋 Goodbye!")
            break
            
        elif cmd == 'status':
            result = api.get_session(session_name)
            if 'error' in result:
                print(f"❌ Error: {result['error']}")
            elif result.get('exists'):
                s = result['session']
                print(f"📊 Session: {s['name']}")
                print(f"   Status: {s['status']}")
                print(f"   PID: {s.get('pid', 'N/A')}")
                print(f"   URL: {s.get('url', 'N/A')}")
                print(f"   Connected: {'✅' if result.get('connected') else '❌'}")
                print(f"   WS ID: {s.get('current_ws_id', 'None')}")
            else:
                print(f"❌ Session not found")
        
        elif cmd == 'url':
            result = api.get_url(session_name)
            if 'url' in result:
                print(f"🌐 {result['url']}")
            else:
                print(f"❌ {result.get('error', 'Failed')}")
        
        elif cmd == 'eval':
            js = input("Enter JavaScript: ")
            if js:
                result = api.evaluate(session_name, js)
                if 'result' in result:
                    print(f"✅ Result: {json.dumps(result['result'], indent=2)}")
                else:
                    print(f"❌ {result.get('error', 'Failed')}")
        
        elif cmd == 'list':
            result = api.list_sessions()
            if 'error' in result:
                print(f"❌ {result['error']}")
            else:
                for s in result.get('sessions', []):
                    print(f"  {s['name']} - {s['status']} ({s.get('pid', 'stopped')})")
        
        elif cmd == 'start':
            result = api.start_session(session_name)
            if result.get('success'):
                print(f"✅ Session started: {session_name}")
            else:
                print(f"❌ {result.get('error', 'Failed')}")
        
        elif cmd == 'stop':
            result = api.stop_session(session_name)
            if result.get('success'):
                print(f"✅ Session stopped: {session_name}")
            else:
                print(f"❌ {result.get('error', 'Failed')}")
        
        elif cmd == 'switch':
            # List sessions and let user choose
            result = api.list_sessions()
            if 'error' in result:
                print(f"❌ {result['error']}")
                continue
            sessions = result.get('sessions', [])
            if not sessions:
                print("No sessions available")
                continue
            print("Available sessions:")
            for i, s in enumerate(sessions, 1):
                print(f"  {i}. {s['name']} ({s['status']})")
            try:
                choice = int(input("Select session number: "))
                if 1 <= choice <= len(sessions):
                    session_name = sessions[choice-1]['name']
                    print(f"✅ Switched to: {session_name}")
                else:
                    print("Invalid selection")
            except ValueError:
                name = input("Enter session name: ")
                if name:
                    session_name = name
                    print(f"✅ Switched to: {session_name}")
        
        elif cmd == 'ss':
            result = api.screenshot(session_name)
            if 'screenshot' in result:
                filename = f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                with open(filename, 'wb') as f:
                    f.write(base64.b64decode(result['screenshot']))
                print(f"✅ Screenshot saved: {filename}")
            else:
                print(f"❌ {result.get('error', 'Failed')}")
        
        else:
            print(f"❓ Unknown command: {cmd}")

if __name__ == "__main__":
    main()
