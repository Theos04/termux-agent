#!/usr/bin/env python3
"""
Interactive Chrome JavaScript Executor
Execute JavaScript in any Chrome tab via WebSocket
"""

import websocket
import json
import sys
import time
import readline
import os
from typing import Optional, Dict, List

class ChromeJSExecutor:
    def __init__(self, ws_url: str = None):
        self.ws_url = ws_url
        self.tabs = []
        self.selected_tab = None
        self.ws = None
        self.connected = False
        
    def get_tabs(self, port: int = 9227) -> List[Dict]:
        """Get all tabs from Chrome"""
        import requests
        try:
            response = requests.get(f"http://127.0.0.1:{port}/json", timeout=5)
            if response.status_code == 200:
                tabs = response.json()
                return [t for t in tabs if t.get('type') == 'page']
            return []
        except:
            return []
    
    def connect(self, ws_url: str) -> bool:
        """Connect to Chrome WebSocket"""
        try:
            self.ws = websocket.create_connection(
                ws_url,
                timeout=10,
                header={"Origin": "http://127.0.0.1:9227"}
            )
            self.connected = True
            self.ws_url = ws_url
            print(f"✅ Connected to: {ws_url}")
            return True
        except Exception as e:
            print(f"❌ Failed to connect: {e}")
            return False
    
    def execute(self, script: str, await_promise: bool = True, timeout: int = 60) -> Optional[Dict]:
        """Execute JavaScript and return result"""
        if not self.connected:
            print("❌ Not connected to Chrome")
            return None
        
        try:
            # Enable Runtime
            self.ws.send(json.dumps({"id": 1, "method": "Runtime.enable"}))
            self.ws.recv()
            
            # Execute script
            cmd = {
                "id": 2,
                "method": "Runtime.evaluate",
                "params": {
                    "expression": script,
                    "returnByValue": True,
                    "awaitPromise": await_promise
                }
            }
            
            self.ws.send(json.dumps(cmd))
            
            # Collect response
            start_time = time.time()
            while time.time() - start_time < timeout:
                try:
                    response = self.ws.recv()
                    data = json.loads(response)
                    if 'id' in data and data['id'] == 2:
                        if 'result' in data and 'result' in data['result']:
                            return data['result']['result']
                        elif 'error' in data:
                            print(f"❌ Error: {data['error']}")
                            return None
                except:
                    continue
            
            print(f"⏰ Timeout after {timeout} seconds")
            return None
            
        except Exception as e:
            print(f"❌ Execution error: {e}")
            return None
    
    def execute_file(self, filename: str) -> Optional[Dict]:
        """Execute JavaScript from a file"""
        try:
            with open(filename, 'r') as f:
                script = f.read()
            return self.execute(script)
        except Exception as e:
            print(f"❌ Error reading file: {e}")
            return None
    
    def interactive_mode(self):
        """Interactive JavaScript execution mode"""
        print("\n" + "="*60)
        print("🔧 Interactive Chrome JavaScript Executor")
        print("="*60)
        
        # Get port
        port = input("Enter Chrome debug port (default 9227): ").strip()
        if not port:
            port = "9227"
        port = int(port)
        
        # Get tabs
        print(f"\n📡 Fetching tabs from port {port}...")
        tabs = self.get_tabs(port)
        
        if not tabs:
            print("❌ No tabs found. Make sure Chrome is running with --remote-debugging-port")
            return
        
        # Display tabs
        print(f"\n📑 Found {len(tabs)} tabs:")
        print("-" * 60)
        for i, tab in enumerate(tabs, 1):
            title = tab.get('title', 'Untitled')[:50]
            url = tab.get('url', '')[:50]
            print(f"  [{i}] {title}")
            print(f"      URL: {url}")
            print()
        
        # Select tab
        while True:
            try:
                choice = input(f"Select tab (1-{len(tabs)}): ").strip()
                if not choice:
                    choice = "1"
                idx = int(choice) - 1
                if 0 <= idx < len(tabs):
                    self.selected_tab = tabs[idx]
                    break
                print("❌ Invalid selection")
            except:
                print("❌ Invalid input")
        
        # Connect to WebSocket
        ws_url = self.selected_tab.get('webSocketDebuggerUrl')
        if not ws_url:
            print("❌ No WebSocket URL found for this tab")
            return
        
        if not self.connect(ws_url):
            return
        
        print(f"\n✅ Connected to tab: {self.selected_tab.get('title', 'Untitled')}")
        print("="*60)
        print("📝 Commands:")
        print("  /help     - Show this help")
        print("  /file     - Execute script from file")
        print("  /save     - Save last result to file")
        print("  /clear    - Clear screen")
        print("  /quit     - Exit")
        print("  Just type JavaScript code to execute")
        print("="*60)
        
        last_result = None
        
        while True:
            try:
                # Get input
                print("\n🔸 Enter JavaScript (or /command):")
                lines = []
                while True:
                    line = input()
                    if line.strip().startswith('/'):
                        # It's a command
                        cmd = line.strip().lower()
                        
                        if cmd == '/quit':
                            print("👋 Goodbye!")
                            self.ws.close()
                            return
                        
                        elif cmd == '/help':
                            print("\n📝 Commands:")
                            print("  /help     - Show this help")
                            print("  /file     - Execute script from file")
                            print("  /save     - Save last result to file")
                            print("  /clear    - Clear screen")
                            print("  /quit     - Exit")
                            continue
                        
                        elif cmd == '/clear':
                            os.system('clear' if os.name == 'posix' else 'cls')
                            continue
                        
                        elif cmd == '/file':
                            filename = input("📁 Enter filename: ").strip()
                            if filename:
                                result = self.execute_file(filename)
                                if result:
                                    last_result = result
                                    print(f"\n✅ Result: {json.dumps(result, indent=2, default=str)}")
                            continue
                        
                        elif cmd == '/save':
                            if last_result:
                                filename = input("📁 Save to filename: ").strip()
                                if filename:
                                    with open(filename, 'w') as f:
                                        json.dump(last_result, f, indent=2, default=str)
                                    print(f"✅ Saved to {filename}")
                            else:
                                print("❌ No result to save")
                            continue
                        
                        else:
                            print(f"❌ Unknown command: {cmd}")
                            continue
                    
                    # If line is not a command, it's JavaScript
                    lines.append(line)
                    
                    # Check if we should continue or execute
                    if line.strip().endswith(';') or line.strip() == '':
                        # Execute immediately if line ends with ;
                        if lines and lines[-1].strip().endswith(';'):
                            script = '\n'.join(lines)
                            print(f"\n⏳ Executing script...")
                            result = self.execute(script)
                            if result:
                                last_result = result
                                print(f"\n✅ Result: {json.dumps(result, indent=2, default=str)}")
                            lines = []
                            break
                        elif line.strip() == '':
                            # Empty line - execute what we have
                            if lines and len(lines) > 1:
                                script = '\n'.join(lines[:-1])
                                print(f"\n⏳ Executing script...")
                                result = self.execute(script)
                                if result:
                                    last_result = result
                                    print(f"\n✅ Result: {json.dumps(result, indent=2, default=str)}")
                            lines = []
                            break
                
            except KeyboardInterrupt:
                print("\n\n👋 Goodbye!")
                if self.ws:
                    self.ws.close()
                return
            except Exception as e:
                print(f"❌ Error: {e}")

def main():
    executor = ChromeJSExecutor()
    
    # If WebSocket URL provided as argument
    if len(sys.argv) > 1:
        ws_url = sys.argv[1]
        if executor.connect(ws_url):
            # Execute script from stdin or file
            if len(sys.argv) > 2:
                filename = sys.argv[2]
                result = executor.execute_file(filename)
                if result:
                    print(json.dumps(result, indent=2, default=str))
            else:
                # Interactive mode with connected socket
                executor.interactive_mode()
    else:
        # Interactive mode - will connect to Chrome
        executor.interactive_mode()

if __name__ == "__main__":
    main()
