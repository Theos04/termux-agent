#!/usr/bin/env python3
"""
Quick HAR Capture - Capture network traffic from Chrome and save as HAR
With live terminal waterfall view
"""

import websocket
import json
import time
import sys
from datetime import datetime
import os

def get_request_type(params):
    """Determine request type from CDP data"""
    # Use CDP's type if available
    if 'type' in params:
        type_map = {
            'Document': 'document',
            'Stylesheet': 'stylesheet',
            'Image': 'image',
            'Media': 'media',
            'Font': 'font',
            'Script': 'script',
            'XHR': 'xhr',
            'Fetch': 'fetch',
            'WebSocket': 'websocket'
        }
        return type_map.get(params['type'], 'other')
    
    # Fallback to URL-based detection
    url = params.get('request', {}).get('url', '').lower()
    if '/api/' in url or '/v1/' in url or '/v2/' in url:
        return 'xhr'
    if url.startswith('ws://') or url.startswith('wss://'):
        return 'websocket'
    if url.endswith('.js'):
        return 'script'
    if url.endswith('.css'):
        return 'stylesheet'
    if url.endswith(('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp')):
        return 'image'
    if url.endswith(('.woff', '.woff2', '.ttf', '.otf')):
        return 'font'
    return 'other'

def shorten_url(url, max_len=50):
    """Shorten URL for display while preserving full URL in HAR"""
    if len(url) <= max_len:
        return url
    # Try to show domain + path
    parts = url.split('/')
    if len(parts) > 3:
        # Keep protocol + domain + first part of path
        protocol = parts[0]
        domain = parts[2] if len(parts) > 2 else ''
        path = parts[3] if len(parts) > 3 else ''
        shortened = f"{protocol}//{domain}/{path}/..."
        if len(shortened) <= max_len:
            return shortened
    # If still too long, just truncate
    return url[:max_len-3] + '...'

class WaterfallDisplay:
    """Manage the terminal waterfall display"""
    
    def __init__(self):
        self.requests = []
        self.start_time = time.time()
        self.max_rows = 30  # Maximum rows to show
        self.first_draw = True
        self.terminal_width = self.get_terminal_width()
        
        # ANSI escape sequences
        self.save_cursor = '\033[s'
        self.restore_cursor = '\033[u'
        self.clear_line = '\033[K'
        self.clear_screen = '\033[2J'
        self.move_home = '\033[H'
        self.hide_cursor = '\033[?25l'
        self.show_cursor = '\033[?25h'
        
    def get_terminal_width(self):
        """Get terminal width or default to 120"""
        try:
            import shutil
            return shutil.get_terminal_size().columns
        except:
            return 120
            
    def add_request(self, request_id, method, url, start_time, params=None):
        """Add a new request to the display"""
        req_type = get_request_type(params) if params else 'other'
        request = {
            'id': request_id,
            'method': method[:6],
            'url': url,
            'short_url': shorten_url(url, 45),
            'start_time': start_time,
            'status': None,
            'status_text': '',
            'mime_type': '',
            'response_time': None,
            'end_time': None,
            'duration': 0,
            'type': req_type[:8],
            'state': 'pending',
            'size': 0
        }
        self.requests.append(request)
        self.draw()
        
    def update_response(self, request_id, status, status_text, mime_type, response_time):
        """Update request with response data"""
        for req in self.requests:
            if req['id'] == request_id:
                req['status'] = status
                req['status_text'] = status_text
                req['mime_type'] = mime_type[:8]
                req['response_time'] = response_time
                req['duration'] = (response_time - req['start_time']) * 1000  # ms
                req['state'] = 'completed'
                self.draw()
                break
                
    def update_loading_finished(self, request_id, end_time, size=None):
        """Update request when loading finishes"""
        for req in self.requests:
            if req['id'] == request_id:
                req['end_time'] = end_time
                if size is not None:
                    req['size'] = size
                # Recalculate duration with actual end time
                req['duration'] = (end_time - req['start_time']) * 1000
                self.draw()
                break
                
    def update_loading_failed(self, request_id, error_text):
        """Mark request as failed"""
        for req in self.requests:
            if req['id'] == request_id:
                req['state'] = 'failed'
                req['status_text'] = f"Failed"
                req['end_time'] = time.time()
                req['duration'] = (req['end_time'] - req['start_time']) * 1000
                self.draw()
                break
                
    def get_stats(self):
        """Get current statistics"""
        total = len(self.requests)
        completed = sum(1 for r in self.requests if r['state'] == 'completed')
        failed = sum(1 for r in self.requests if r['state'] == 'failed')
        pending = sum(1 for r in self.requests if r['state'] == 'pending')
        return total, completed, failed, pending
        
    def draw(self):
        """Draw the waterfall display"""
        # Hide cursor to prevent flickering
        if self.first_draw:
            print(self.hide_cursor, end='')
            
        # Move cursor to home position
        print(self.move_home, end='')
        
        # Clear everything below
        if self.first_draw:
            print(self.clear_screen, end='')
            self.first_draw = False
        
        # Draw header
        print("╔═══════════════════════════════════════════════════════════════════════════╗")
        print("║                         🌊 NETWORK WATERFALL                           ║")
        print("╚═══════════════════════════════════════════════════════════════════════════╝")
        print("─────────────────────────────────────────────────────────────────────────────")
        print("TIME      METHOD  STATUS  TYPE       DURATION  URL")
        print("─────────────────────────────────────────────────────────────────────────────")
        
        # Get visible requests (most recent first, limited to max_rows)
        visible = self.requests[-self.max_rows:] if len(self.requests) > self.max_rows else self.requests
        
        # Calculate max duration for bar scaling (only visible requests)
        durations = [r.get('duration', 0) for r in visible if r.get('duration', 0) > 0]
        max_duration = max(durations) if durations else 100
        max_duration = max(max_duration, 100)  # Minimum 100ms for scaling
        
        # Draw each request
        for req in reversed(visible):  # Show newest at top
            elapsed = time.time() - req['start_time']
            
            # Status emoji
            if req['state'] == 'completed':
                status_emoji = '✅' if req['status'] and 200 <= req['status'] < 300 else '⚠️' if req['status'] and 300 <= req['status'] < 400 else '❌'
            elif req['state'] == 'failed':
                status_emoji = '💥'
            else:
                status_emoji = '⏳'
                
            # Method
            method = req['method'][:6].ljust(6)
            
            # Status
            status_text = str(req['status']) if req['status'] else '...'
            status_text = f"{status_emoji}{status_text}".ljust(6)
            
            # Type
            req_type = req['type'][:8].ljust(8)
            
            # Duration
            duration = req.get('duration', (time.time() - req['start_time']) * 1000)
            duration_str = f"{duration:>6.0f}ms"
            
            # Waterfall bar (simplified for better display)
            bar_len = min(25, int((duration / max_duration) * 25))
            if req['state'] == 'pending':
                bar = '█' * bar_len + '░' * (25 - bar_len)
            elif req['state'] == 'failed':
                bar = '█' * min(bar_len, 12) + '💥'
            else:
                bar = '█' * bar_len + ' ' * (25 - bar_len)
                
            # URL
            url = req['short_url']
            
            # Print row with fixed width fields
            print(f"{elapsed:>6.2f}s  {method} {status_text}  {req_type}  {bar}  {duration_str}  {url}")
        
        # Clear remaining lines
        rows_used = len(visible) + 5
        for _ in range(rows_used, self.max_rows + 5):
            print(self.clear_line)
            
        # Stats footer
        total, completed, failed, pending = self.get_stats()
        print("─────────────────────────────────────────────────────────────────────────────")
        print(f"📊 Requests: {total} | ✅ Completed: {completed} | ❌ Failed: {failed} | ⏳ Active: {pending} | 📡 {time.time() - self.start_time:.1f}s")
        
        # Flush output
        sys.stdout.flush()

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
    request_state = {}  # Store full request state
    waterfall = WaterfallDisplay()
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
                    
                    # Store full request data for HAR
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
                    
                    # Store in state
                    request_state[request_id] = {
                        'entry': entry,
                        'start_time': time.time(),
                        'method': request.get('method', ''),
                        'url': url,
                        'status': None,
                        'response_time': None,
                        'end_time': None,
                        'state': 'pending'
                    }
                    request_count += 1
                    
                    # Add to waterfall display
                    waterfall.add_request(request_id, request.get('method', ''), url, time.time(), params)
                    
                elif method == 'Network.responseReceived':
                    request_id = params.get('requestId')
                    if request_id in request_state:
                        response = params.get('response', {})
                        state = request_state[request_id]
                        entry = state['entry']
                        
                        # Update entry with response data
                        entry['response']['status'] = response.get('status', 0)
                        entry['response']['statusText'] = response.get('statusText', '')
                        entry['response']['headers'] = response.get('headers', {})
                        entry['response']['content']['mimeType'] = response.get('mimeType', '')
                        
                        state['status'] = response.get('status', 0)
                        state['response_time'] = time.time()
                        state['state'] = 'completed'
                        
                        # Update waterfall
                        waterfall.update_response(
                            request_id,
                            response.get('status', 0),
                            response.get('statusText', ''),
                            response.get('mimeType', ''),
                            time.time()
                        )
                        
                        # Add to entries list (will be completed when loadingFinished arrives)
                        entries.append(entry)
                        response_count += 1
                        
                elif method == 'Network.loadingFinished':
                    request_id = params.get('requestId')
                    if request_id in request_state:
                        state = request_state[request_id]
                        state['end_time'] = time.time()
                        
                        # Calculate final duration
                        if state['start_time'] and state['end_time']:
                            state['entry']['time'] = (state['end_time'] - state['start_time']) * 1000
                            
                        # Update waterfall
                        waterfall.update_loading_finished(request_id, time.time())
                        
                elif method == 'Network.loadingFailed':
                    request_id = params.get('requestId')
                    if request_id in request_state:
                        state = request_state[request_id]
                        state['state'] = 'failed'
                        state['end_time'] = time.time()
                        error_text = params.get('errorText', 'Unknown error')
                        
                        # Update waterfall
                        waterfall.update_loading_failed(request_id, error_text)
                        
            except websocket.WebSocketTimeoutException:
                continue
            except KeyboardInterrupt:
                print("\n⏹️ Stopped by user")
                break
            except Exception as e:
                continue
                
    except KeyboardInterrupt:
        print("\n⏹️ Stopped by user")
    
    # Show cursor again
    print('\033[?25h', end='')
    
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
                       or '/v1/' in e.get('request', {}).get('url', '')
                       or '/v2/' in e.get('request', {}).get('url', '')
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
