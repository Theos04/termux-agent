#!/usr/bin/env python3
"""
Quick HAR Capture - Capture network traffic from Chrome and save as HAR
"""

import websocket
import json
import time
import sys
from datetime import datetime

def capture_har(ws_url, duration=30, output_file=None):
    """
    Capture HAR data from Chrome DevTools WebSocket
    
    Args:
        ws_url: WebSocket URL (e.g., ws://127.0.0.1:9258/devtools/page/ID)
        duration: Capture duration in seconds
        output_file: Output HAR filename (auto-generated if None)
    """
    print(f"📡 Connecting to: {ws_url}")
    print(f"⏳ Capturing for {duration} seconds...")
    
    # Connect to Chrome
    ws = websocket.create_connection(ws_url)
    print("✅ Connected!")
    
    # Enable Network monitoring
    ws.send(json.dumps({"id": 1, "method": "Network.enable"}))
    print("📊 Network monitoring enabled")
    
    # Data structures
    entries = []
    request_map = {}
    start_time = time.time()
    request_count = 0
    response_count = 0
    
    print("\n🎯 Capturing network traffic... (interact with the page)")
    print("   Press Ctrl+C to stop early\n")
    
    try:
        while time.time() - start_time < duration:
            try:
                ws.settimeout(0.5)
                msg = ws.recv()
                data = json.loads(msg)
                
                if 'method' not in data:
                    continue
                
                method = data['method']
                params = data.get('params', {})
                
                if method == 'Network.requestWillBeSent':
                    request = params.get('request', {})
                    request_id = params.get('requestId')
                    url = request.get('url', '')
                    
                    entry = {
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
                            'content': {'mimeType': ''}
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
                        'request_time': time.time()
                    }
                    request_map[request_id] = entry
                    request_count += 1
                    
                elif method == 'Network.responseReceived':
                    request_id = params.get('requestId')
                    if request_id in request_map:
                        response = params.get('response', {})
                        entry = request_map[request_id]
                        entry['response']['status'] = response.get('status', 0)
                        entry['response']['statusText'] = response.get('statusText', '')
                        entry['response']['headers'] = response.get('headers', {})
                        entry['response']['content']['mimeType'] = response.get('mimeType', '')
                        entry['response_time'] = time.time()
                        
                        entries.append(entry)
                        response_count += 1
                        del request_map[request_id]
                        
                        # Show progress
                        if response_count % 10 == 0:
                            print(f"   Captured {response_count} responses...", end='\r')
                
            except websocket.WebSocketTimeoutException:
                continue
            except KeyboardInterrupt:
                print("\n⏹️ Stopped by user")
                break
            except Exception as e:
                continue
                
    except KeyboardInterrupt:
        print("\n⏹️ Stopped by user")
    
    # Close connection
    ws.close()
    print(f"\n\n✅ Capture complete!")
    print(f"   Requests sent: {request_count}")
    print(f"   Responses captured: {response_count}")
    print(f"   Entries saved: {len(entries)}")
    
    # Build HAR structure
    har_data = {
        'log': {
            'version': '1.2',
            'creator': {
                'name': 'Quick HAR Capture',
                'version': '1.0'
            },
            'entries': entries
        }
    }
    
    # Save to file
    if not output_file:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = f"har_capture_{timestamp}.har"
    
    with open(output_file, 'w') as f:
        json.dump(har_data, f, indent=2)
    
    print(f"💾 Saved to: {output_file}")
    print(f"📊 File size: {len(json.dumps(har_data)) / 1024:.2f} KB")
    
    # Show summary
    print("\n📊 Summary:")
    if entries:
        # Count by status
        statuses = {}
        methods = {}
        for entry in entries:
            status = entry.get('response', {}).get('status', 0)
            statuses[status] = statuses.get(status, 0) + 1
            
            method = entry.get('request', {}).get('method', '')
            methods[method] = methods.get(method, 0) + 1
        
        print("   Status Codes:")
        for status, count in sorted(statuses.items()):
            emoji = "✅" if 200 <= status < 300 else "⚠️" if 300 <= status < 400 else "❌"
            print(f"     {emoji} {status}: {count}")
        
        print("   Methods:")
        for method, count in methods.items():
            print(f"     • {method}: {count}")
        
        # Show API endpoints
        api_count = sum(1 for e in entries if '/api/' in e.get('request', {}).get('url', '') 
                       or '/v' in e.get('request', {}).get('url', '')
                       or 'json' in e.get('response', {}).get('content', {}).get('mimeType', ''))
        print(f"   API endpoints: {api_count}")
    
    return har_data

def get_tabs(port=9258):
    """Get list of tabs from Chrome"""
    import requests
    try:
        resp = requests.get(f"http://127.0.0.1:{port}/json", timeout=5)
        return resp.json()
    except Exception as e:
        print(f"❌ Error connecting to Chrome on port {port}: {e}")
        return []

def main():
    print("╔═══════════════════════════════════════════════╗")
    print("║    🚀 Quick HAR Capture                      ║")
    print("║    Capture network traffic from Chrome       ║")
    print("╚═══════════════════════════════════════════════╝")
    print()
    
    # Get port
    port = input("Chrome debugging port [9258]: ").strip()
    port = int(port) if port else 9258
    
    # Get tabs
    tabs = get_tabs(port)
    if not tabs:
        print("❌ No Chrome session found. Make sure Chrome is running.")
        return
    
    # Show tabs
    print(f"\n📑 Available tabs on port {port}:")
    for i, tab in enumerate(tabs):
        if tab.get('type') == 'page':
            title = tab.get('title', 'Untitled')[:50]
            url = tab.get('url', '')[:60]
            print(f"  {i+1}. {title}")
            print(f"     {url}")
    
    # Select tab
    choice = input("\nSelect tab number [1]: ").strip()
    tab_index = int(choice) - 1 if choice else 0
    
    # Filter for page tabs
    page_tabs = [t for t in tabs if t.get('type') == 'page']
    
    if tab_index >= len(page_tabs):
        print("❌ Invalid tab selection")
        return
    
    ws_url = page_tabs[tab_index].get('webSocketDebuggerUrl')
    if not ws_url:
        print("❌ No WebSocket URL found for this tab")
        return
    
    # Capture settings
    duration = input("Capture duration (seconds) [30]: ").strip()
    duration = int(duration) if duration else 30
    
    output = input("Output filename (optional): ").strip()
    output = output if output else None
    
    # Capture
    print("\n" + "="*50)
    capture_har(ws_url, duration, output)
    print("\n✅ Done!")

if __name__ == "__main__":
    main()
