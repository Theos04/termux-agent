#!/usr/bin/env python3
"""
Extract authentication token directly from Chrome using CDP
"""

import asyncio
import json
import re
from pathlib import Path
import websockets
import requests

async def get_token_from_chrome(port: int = 9222) -> str:
    """
    Extract token from Chrome using CDP
    
    Args:
        port: Chrome debugging port (default: 9222)
    """
    try:
        # Get list of available pages/tabs
        response = requests.get(f"http://localhost:{port}/json")
        if response.status_code != 200:
            print(f"❌ Chrome debugging port {port} not accessible")
            return None
            
        pages = response.json()
        
        # Find pages with naukri.com
        naukri_pages = []
        for page in pages:
            url = page.get('url', '')
            if 'naukri.com' in url or 'naukimg.com' in url:
                naukri_pages.append(page)
                
        if not naukri_pages:
            print("❌ No Naukri pages found in Chrome")
            print("Please open Naukri.com in Chrome first")
            return None
            
        # Use the first Naukri page
        page = naukri_pages[0]
        ws_url = page.get('webSocketDebuggerUrl')
        
        if not ws_url:
            print("❌ WebSocket URL not found")
            return None
            
        print(f"📄 Found Naukri page: {page.get('title', 'Unknown')}")
        print(f"🔗 URL: {page.get('url', '')[:80]}...")
        print(f"🔌 Connecting to: {ws_url[:50]}...")
        
        # Connect to Chrome
        async with websockets.connect(ws_url, ping_interval=20, ping_timeout=20) as websocket:
            # Send enable commands
            await websocket.send(json.dumps({
                "id": 1,
                "method": "Network.enable"
            }))
            
            await websocket.send(json.dumps({
                "id": 2,
                "method": "Runtime.enable"
            }))
            
            # Wait for enable responses
            for _ in range(2):
                try:
                    response = await asyncio.wait_for(websocket.recv(), timeout=2)
                except asyncio.TimeoutError:
                    break
                    
            print("✅ Connected to Chrome")
            print("🔍 Searching for authentication token...")
            
            # Method 1: Get cookies using CDP
            cookie_cmd = {
                "id": 3,
                "method": "Network.getCookies"
            }
            await websocket.send(json.dumps(cookie_cmd))
            
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=3)
                data = json.loads(response)
                cookies = data.get('result', {}).get('cookies', [])
                
                # Look for session cookies
                for cookie in cookies:
                    name = cookie.get('name', '')
                    value = cookie.get('value', '')
                    domain = cookie.get('domain', '')
                    
                    if 'naukri' in domain or 'naukimg' in domain:
                        if 'session' in name.lower() or 'auth' in name.lower() or 'token' in name.lower():
                            print(f"🍪 Found cookie: {name} = {value[:30]}...")
                            if len(value) > 30:
                                return value
                                
            except Exception as e:
                print(f"⚠️ Cookie extraction error: {e}")
                
            # Method 2: Get localStorage via Runtime
            script = """
            (function() {
                const results = {};
                for (let i = 0; i < localStorage.length; i++) {
                    const key = localStorage.key(i);
                    const value = localStorage.getItem(key);
                    if (key && value && (key.includes('token') || key.includes('auth') || key.includes('session'))) {
                        results[key] = value;
                    }
                }
                return results;
            })()
            """
            
            local_cmd = {
                "id": 4,
                "method": "Runtime.evaluate",
                "params": {
                    "expression": script,
                    "returnByValue": True
                }
            }
            await websocket.send(json.dumps(local_cmd))
            
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=3)
                data = json.loads(response)
                result = data.get('result', {}).get('result', {}).get('value', {})
                
                if result:
                    print(f"📦 Found localStorage items: {len(result)}")
                    for key, value in result.items():
                        if isinstance(value, str) and len(value) > 30:
                            print(f"💾 Found token in localStorage[{key}]")
                            return value
                            
            except Exception as e:
                print(f"⚠️ LocalStorage extraction error: {e}")
                
            # Method 3: Execute script to get Authorization header from fetch calls
            script = """
            (function() {
                const token = null;
                // Check if there's a global token variable
                if (window.token) return window.token;
                if (window.authToken) return window.authToken;
                if (window.accessToken) return window.accessToken;
                if (window.apiToken) return window.apiToken;
                return null;
            })()
            """
            
            global_cmd = {
                "id": 5,
                "method": "Runtime.evaluate",
                "params": {
                    "expression": script,
                    "returnByValue": True
                }
            }
            await websocket.send(json.dumps(global_cmd))
            
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=3)
                data = json.loads(response)
                token = data.get('result', {}).get('result', {}).get('value')
                if token and isinstance(token, str) and len(token) > 30:
                    print("🌐 Found global token variable")
                    return token
            except Exception as e:
                print(f"⚠️ Global token extraction error: {e}")
                
            print("❌ No token found in Chrome")
            print("\n💡 Tips:")
            print("  1. Make sure you're logged into Naukri.com")
            print("  2. Try refreshing the page")
            print("  3. Try navigating to different pages on Naukri")
            return None
            
    except Exception as e:
        print(f"❌ Error connecting to Chrome: {e}")
        return None

def main():
    """Main function"""
    print("""
╔═══════════════════════════════════════════════════════════╗
║    🔑 Chrome Token Extractor                            ║
║    Extract authentication token directly from Chrome    ║
╚═══════════════════════════════════════════════════════════╝
    """)
    
    # Check if Chrome is running with debugging
    print("🔍 Checking Chrome debugging ports...")
    
    ports_to_check = [9222, 9223, 9224, 9225, 9226, 9227, 9228, 9229, 9260]
    active_ports = []
    
    for port in ports_to_check:
        try:
            response = requests.get(f"http://localhost:{port}/json", timeout=2)
            if response.status_code == 200:
                active_ports.append(port)
                print(f"✅ Chrome debug port {port} is active")
        except:
            pass
            
    if not active_ports:
        print("""
❌ No active Chrome debugging ports found!

Please start Chrome with debugging enabled:

On Linux/Mac:
  google-chrome --remote-debugging-port=9222

On Windows:
  chrome.exe --remote-debugging-port=9222

Or use your existing Chrome launcher script that starts with port 9222
        """)
        
        port = input("\nEnter Chrome debugging port (or press Enter to exit): ").strip()
        if port:
            try:
                port = int(port)
                active_ports = [port]
            except:
                print("Invalid port number")
                return
        else:
            return
            
    # Use the first active port
    port = active_ports[0]
    
    print(f"\n📡 Using Chrome debug port: {port}")
    
    # Extract token
    try:
        token = asyncio.run(get_token_from_chrome(port))
        
        if token:
            print(f"\n✅ Token extracted successfully!")
            print(f"🔑 Token: {token[:30]}...{token[-10:]}")
            
            # Save token
            with open('naukri_token.txt', 'w') as f:
                f.write(token)
            print("\n💾 Token saved to: naukri_token.txt")
            print("\n🚀 You can now run: ./start_bot.sh")
        else:
            print("\n❌ Could not extract token")
            print("\nAlternative: Use the manual method")
            print("  python get_token_manual.py")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
