#!/usr/bin/env python3
"""
Extract token by intercepting network requests via Chrome DevTools Protocol
"""

import asyncio
import json
import time
from pathlib import Path
import websockets
import requests

class TokenExtractor:
    def __init__(self, port=9260):
        self.port = port
        self.token = None
        
    async def extract_token(self):
        """Extract token by monitoring network requests"""
        try:
            # Get list of pages
            response = requests.get(f"http://localhost:{self.port}/json")
            if response.status_code != 200:
                print(f"❌ Chrome debugging port {self.port} not accessible")
                return None
                
            pages = response.json()
            
            # Find Naukri pages
            naukri_pages = []
            for page in pages:
                url = page.get('url', '')
                if 'naukri.com' in url or 'naukimg.com' in url:
                    naukri_pages.append(page)
                    
            if not naukri_pages:
                print("❌ No Naukri pages found. Please open Naukri.com first.")
                return None
                
            page = naukri_pages[0]
            ws_url = page.get('webSocketDebuggerUrl')
            
            print(f"📄 Found Naukri page: {page.get('title', 'Unknown')}")
            print(f"🔗 URL: {page.get('url', '')[:80]}...")
            
            # Connect to Chrome
            async with websockets.connect(ws_url, ping_interval=20, ping_timeout=20) as websocket:
                # Enable network monitoring
                await websocket.send(json.dumps({
                    "id": 1,
                    "method": "Network.enable"
                }))
                
                # Enable runtime for page reload
                await websocket.send(json.dumps({
                    "id": 2,
                    "method": "Runtime.enable"
                }))
                
                # Wait for enable responses
                for _ in range(2):
                    try:
                        await asyncio.wait_for(websocket.recv(), timeout=2)
                    except:
                        pass
                
                print("✅ Connected to Chrome")
                print("🔄 Monitoring network requests...")
                print("💡 Please interact with the page or refresh it")
                print("   (Press Ctrl+C to stop monitoring)\n")
                
                # Monitor requests
                found_tokens = []
                
                while True:
                    try:
                        message = await asyncio.wait_for(websocket.recv(), timeout=30)
                        data = json.loads(message)
                        
                        # Check for request headers
                        if data.get('method') == 'Network.requestWillBeSent':
                            request = data.get('params', {}).get('request', {})
                            headers = request.get('headers', {})
                            url = request.get('url', '')
                            
                            # Check for Authorization header
                            auth = headers.get('authorization') or headers.get('Authorization')
                            if auth and 'Bearer' in auth:
                                token = auth.replace('Bearer', '').strip()
                                if token and len(token) > 20:
                                    print(f"\n✅ Found token in request to: {url[:60]}...")
                                    found_tokens.append(token)
                                    self.token = token
                                    
                                    # Return immediately if found
                                    return token
                                    
                            # Also check for token in URL parameters
                            if 'token=' in url or 'auth=' in url or 'access_token=' in url:
                                print(f"\n🔍 Found potential token in URL: {url[:80]}...")
                                
                        # Check for response headers
                        elif data.get('method') == 'Network.responseReceived':
                            response = data.get('params', {}).get('response', {})
                            headers = response.get('headers', {})
                            url = response.get('url', '')
                            
                            auth = headers.get('authorization') or headers.get('Authorization')
                            if auth and 'Bearer' in auth:
                                token = auth.replace('Bearer', '').strip()
                                if token and len(token) > 20:
                                    print(f"\n✅ Found token in response from: {url[:60]}...")
                                    found_tokens.append(token)
                                    self.token = token
                                    return token
                                    
                        # Check for WebSocket messages
                        elif data.get('method') == 'Runtime.consoleAPICalled':
                            args = data.get('params', {}).get('args', [])
                            for arg in args:
                                value = arg.get('value', '')
                                if isinstance(value, str) and 'token' in value.lower():
                                    if len(value) > 20:
                                        print(f"\n✅ Found potential token in console: {value[:50]}...")
                                        
                    except asyncio.TimeoutError:
                        print("⏰ No activity detected. Try refreshing the page or clicking something.")
                    except websockets.exceptions.ConnectionClosed:
                        print("⚠️ Connection closed. Please refresh the page.")
                        break
                    except KeyboardInterrupt:
                        print("\n\n⏹️ Monitoring stopped")
                        break
                        
                # If token not found via monitoring, try alternative extraction
                if not self.token:
                    print("\n❌ No token found in network traffic")
                    print("\n💡 Tips:")
                    print("  1. Refresh the page (F5)")
                    print("  2. Navigate to another page on Naukri")
                    print("  3. Click on something that triggers an API call")
                    print("  4. Make sure you're logged in")
                    
                    # Try to extract from cookies as fallback
                    print("\n🔍 Trying alternative extraction methods...")
                    token = await self.extract_from_cookies(websocket)
                    if token:
                        self.token = token
                        return token
                        
                return self.token
                
        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()
            return None
            
    async def extract_from_cookies(self, websocket):
        """Extract token from cookies"""
        try:
            # Get cookies
            await websocket.send(json.dumps({
                "id": 10,
                "method": "Network.getCookies"
            }))
            
            response = await asyncio.wait_for(websocket.recv(), timeout=3)
            data = json.loads(response)
            cookies = data.get('result', {}).get('cookies', [])
            
            for cookie in cookies:
                name = cookie.get('name', '')
                value = cookie.get('value', '')
                domain = cookie.get('domain', '')
                
                if 'naukri' in domain:
                    # Look for session or auth cookies
                    if any(key in name.lower() for key in ['session', 'auth', 'token', 'sso']):
                        print(f"🍪 Found cookie: {name}")
                        if len(value) > 30:
                            return value
                            
            # Try localStorage
            script = """
            (function() {
                const tokens = [];
                for (let i = 0; i < localStorage.length; i++) {
                    const key = localStorage.key(i);
                    const value = localStorage.getItem(key);
                    if (value && value.length > 30) {
                        if (key.includes('token') || key.includes('auth') || 
                            key.includes('session') || key.includes('sso')) {
                            tokens.push({key: key, value: value});
                        }
                    }
                }
                return tokens;
            })()
            """
            
            await websocket.send(json.dumps({
                "id": 11,
                "method": "Runtime.evaluate",
                "params": {
                    "expression": script,
                    "returnByValue": True
                }
            }))
            
            response = await asyncio.wait_for(websocket.recv(), timeout=3)
            data = json.loads(response)
            result = data.get('result', {}).get('result', {}).get('value', [])
            
            if result and len(result) > 0:
                print(f"💾 Found in localStorage: {len(result)} items")
                return result[0].get('value')
                
            return None
            
        except Exception as e:
            print(f"⚠️ Fallback extraction error: {e}")
            return None

def main():
    """Main function"""
    print("""
╔═══════════════════════════════════════════════════════════╗
║    🔑 Network Token Extractor                           ║
║    Extract token by monitoring network requests         ║
╚═══════════════════════════════════════════════════════════╝
    """)
    
    # Check for active Chrome debug ports
    print("🔍 Checking Chrome debugging ports...")
    
    # Use port 9260 (from your quick_capture_har.py)
    port = 9260
    try:
        response = requests.get(f"http://localhost:{port}/json", timeout=2)
        if response.status_code == 200:
            print(f"✅ Chrome debug port {port} is active")
        else:
            # Try other ports
            for p in [9222, 9223, 9224, 9225, 9226, 9227, 9228, 9229]:
                try:
                    response = requests.get(f"http://localhost:{p}/json", timeout=2)
                    if response.status_code == 200:
                        port = p
                        print(f"✅ Chrome debug port {port} is active")
                        break
                except:
                    pass
    except:
        print("❌ No active Chrome debugging ports found!")
        print("\nPlease start Chrome with debugging enabled:")
        print("  google-chrome --remote-debugging-port=9260")
        print("\nOr use your existing Chrome launcher script")
        return
        
    extractor = TokenExtractor(port)
    
    print("\n📡 Starting token extraction...")
    print("   (This will monitor network traffic)\n")
    
    try:
        token = asyncio.run(extractor.extract_token())
        
        if token:
            print(f"\n✅ Token extracted successfully!")
            print(f"🔑 Token: {token[:30]}...{token[-10:]}")
            
            # Save token
            with open('naukri_token.txt', 'w') as f:
                f.write(token)
            print("\n💾 Token saved to: naukri_token.txt")
            
            # Show token info
            print(f"\n📊 Token Info:")
            print(f"  • Length: {len(token)} characters")
            print(f"  • Format: Bearer token")
            print(f"\n🚀 You can now run: ./start_smart.sh")
            print("   Or: python naukri_job_bot_fixed.py")
        else:
            print("\n❌ Could not extract token")
            print("\n📋 Manual alternatives:")
            print("  1. Extract from HAR: python extract_token_from_har.py")
            print("  2. Manual entry: python get_token_manual.py")
            
    except KeyboardInterrupt:
        print("\n\n⏹️ Cancelled by user")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()
