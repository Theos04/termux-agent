"""
Chrome DevTools Protocol HAR capture - Enhanced version with full header capture and token extraction
"""

import json
import websocket
import time
import threading
from typing import Dict, List, Optional, Any, Set, Union
from datetime import datetime
from collections import defaultdict
import logging
import re
import base64
from urllib.parse import urlparse, parse_qs

# Configure logging with more detail
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


class TokenExtractor:
    """Extract and analyze authentication tokens from requests"""

    @staticmethod
    def decode_jwt(token: str) -> Optional[Dict]:
        """Decode JWT without verification for analysis"""
        try:
            parts = token.split('.')
            if len(parts) != 3:
                return None

            # Decode header and payload
            header = json.loads(base64.urlsafe_b64decode(parts[0] + '==').decode('utf-8'))
            payload = json.loads(base64.urlsafe_b64decode(parts[1] + '==').decode('utf-8'))

            return {
                'header': header,
                'payload': payload,
                'algorithm': header.get('alg', 'unknown'),
                'type': header.get('typ', 'JWT'),
                'issued_at': datetime.fromtimestamp(payload.get('iat', 0)).isoformat() if payload.get('iat') else None,
                'expires_at': datetime.fromtimestamp(payload.get('exp', 0)).isoformat() if payload.get('exp') else None,
                'issuer': payload.get('iss'),
                'subject': payload.get('sub'),
                'audience': payload.get('aud'),
                'claims': payload
            }
        except Exception as e:
            return None

    @staticmethod
    def extract_tokens(headers: Dict) -> List[Dict]:
        """Extract all tokens from headers"""
        tokens = []

        if not isinstance(headers, dict):
            return tokens

        for header_name, header_value in headers.items():
            header_lower = header_name.lower()

            if header_lower == 'authorization':
                if isinstance(header_value, str) and header_value.startswith('Bearer '):
                    token = header_value[7:]
                    decoded = TokenExtractor.decode_jwt(token)
                    tokens.append({
                        'type': 'Bearer',
                        'header': header_name,
                        'value': token[:50] + '...' if len(token) > 50 else token,
                        'full_value': token,
                        'decoded': decoded
                    })
                elif isinstance(header_value, str) and header_value.startswith('Basic '):
                    tokens.append({
                        'type': 'Basic',
                        'header': header_name,
                        'value': header_value[:50] + '...' if len(header_value) > 50 else header_value,
                        'full_value': header_value,
                        'decoded': None
                    })

            elif header_lower in ['x-auth-token', 'x-api-token', 'x-api-key']:
                if isinstance(header_value, str):
                    decoded = TokenExtractor.decode_jwt(header_value)
                    tokens.append({
                        'type': 'Custom',
                        'header': header_name,
                        'value': header_value[:50] + '...' if len(header_value) > 50 else header_value,
                        'full_value': header_value,
                        'decoded': decoded
                    })

            elif header_lower == 'cookie' and isinstance(header_value, str):
                # Parse cookie header
                cookies = re.findall(r'([^=;,]+)=([^;,]+)', header_value)
                for cookie_name, cookie_value in cookies:
                    cookie_name = cookie_name.strip()
                    cookie_value = cookie_value.strip()
                    if any(key in cookie_name.lower() for key in ['token', 'jwt', 'auth', 'session']):
                        decoded = TokenExtractor.decode_jwt(cookie_value)
                        tokens.append({
                            'type': 'Cookie',
                            'header': header_name,
                            'cookie_name': cookie_name,
                            'value': cookie_value[:50] + '...' if len(cookie_value) > 50 else cookie_value,
                            'full_value': cookie_value,
                            'decoded': decoded
                        })

        return tokens


class CDPCapturer:
    """Capture HAR data using Chrome DevTools Protocol with enhanced header and token extraction"""

    def __init__(self, port: int = 9222, max_entries: int = 10000):
        self.port = port
        self.connections = {}
        self.har_entries = []
        self.request_map = {}
        self.is_capturing = False
        self.lock = threading.Lock()
        self.max_entries = max_entries
        self.entry_counter = 0
        self._listen_threads = {}
        self._message_counter = 0
        self._last_activity = time.time()

        # Enhanced session token tracking
        self.session_tokens = {
            'authorization': None,
            'cookies': {},
            'api_keys': [],
            'headers': {},
            'bearer_tokens': [],
            'jwt_tokens': []
        }

        # Track all extracted tokens
        self.extracted_tokens = []
        self.attack_surface = {
            'endpoints': defaultdict(lambda: {
                'methods': set(),
                'query_params': set(),
                'body_params': set(),
                'auth_methods': set(),
                'headers': set(),
                'response_statuses': set(),
                'content_types': set()
            }),
            'domains': set(),
            'authentication_endpoints': []
        }

    def safe_get_headers(self, headers_data: Any) -> Dict:
        """Safely convert headers to dictionary with comprehensive parsing"""
        if isinstance(headers_data, dict):
            return headers_data

        if not headers_data:
            return {}

        if isinstance(headers_data, str):
            # Strategy 1: Try to parse as JSON
            try:
                parsed = json.loads(headers_data)
                if isinstance(parsed, dict):
                    return parsed
            except:
                pass

            # Strategy 2: Try to parse as HTTP header lines
            try:
                result = {}
                lines = headers_data.strip().split('\n')
                for line in lines:
                    line = line.strip()
                    if ':' in line:
                        key, value = line.split(':', 1)
                        key = key.strip()
                        value = value.strip()
                        if key and value:
                            result[key] = value
                if result:
                    return result
            except:
                pass

            # Strategy 3: Try to parse as URL-encoded
            try:
                result = {}
                for pair in headers_data.split('&'):
                    if '=' in pair:
                        key, value = pair.split('=', 1)
                        key = key.strip()
                        value = value.strip()
                        if key and value:
                            result[key] = value
                if result:
                    return result
            except:
                pass

            # Strategy 4: Try to extract with regex
            try:
                result = {}
                pairs = re.findall(r'([^:=]+)[:=]\s*([^&\n]+)', headers_data)
                for key, value in pairs:
                    key = key.strip()
                    value = value.strip()
                    if key and value:
                        result[key] = value
                if result:
                    return result
            except:
                pass

            # Strategy 5: Try to parse as Cookie header
            try:
                if '=' in headers_data and ':' not in headers_data:
                    result = {}
                    cookies = re.findall(r'([^=;,]+)=([^;,]+)', headers_data)
                    for cookie_name, cookie_value in cookies:
                        cookie_name = cookie_name.strip()
                        cookie_value = cookie_value.strip()
                        if cookie_name and cookie_value:
                            result[cookie_name] = cookie_value
                    if result:
                        return result
            except:
                pass

        return {}

    def connect_to_tab(self, tab_id: str, ws_url: str) -> bool:
        """Connect to a Chrome tab via WebSocket with enhanced capabilities"""
        try:
            logger.info(f"Connecting to tab: {tab_id} at {ws_url[:50]}...")
            ws = websocket.create_connection(ws_url, timeout=10, enable_multithread=True)
            self.connections[tab_id] = ws

            # Enable network monitoring with full header capture
            logger.debug(f"Sending Network.enable for tab: {tab_id}")
            ws.send(json.dumps({"id": 1, "method": "Network.enable", "params": {"maxResourceBufferSize": 100000000}}))
            
            # Wait for response
            response = ws.recv()
            logger.debug(f"Network.enable response: {response[:100]}")
            
            logger.debug(f"Sending Page.enable for tab: {tab_id}")
            ws.send(json.dumps({"id": 2, "method": "Page.enable"}))
            response = ws.recv()
            logger.debug(f"Page.enable response: {response[:100]}")
            
            logger.debug(f"Sending Runtime.enable for tab: {tab_id}")
            ws.send(json.dumps({"id": 3, "method": "Runtime.enable"}))
            response = ws.recv()
            logger.debug(f"Runtime.enable response: {response[:100]}")
            
            # Start listening for events immediately
            self._start_listener(tab_id)

            logger.info(f"✅ Connected to tab: {tab_id}")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to connect to tab {tab_id}: {e}")
            return False

    def _start_listener(self, tab_id: str):
        """Start the listener thread for a tab"""
        def listen():
            ws = self.connections.get(tab_id)
            if not ws:
                return
                
            logger.info(f"Starting listener for tab: {tab_id}")
            while self.is_capturing or True:  # Keep listening even after capture stops
                try:
                    ws.settimeout(0.5)
                    msg = ws.recv()
                    if msg:
                        self._message_counter += 1
                        self._last_activity = time.time()
                        try:
                            data = json.loads(msg)
                            method = data.get('method', '')
                            
                            # Log only important events to avoid spam
                            if method in ['Network.requestWillBeSent', 'Network.responseReceived']:
                                logger.info(f"📨 {method} - {data.get('params', {}).get('requestId', '')[:8]}")
                            elif method.startswith('Network.') and self._message_counter % 100 == 0:
                                logger.debug(f"📨 {method} (message #{self._message_counter})")
                                
                            self._process_message(data, tab_id)
                        except json.JSONDecodeError as e:
                            logger.debug(f"Invalid JSON: {e}")
                        except Exception as e:
                            logger.error(f"Error processing message: {e}")
                except websocket.WebSocketTimeoutException:
                    # Check if we should keep running
                    if not self.is_capturing and time.time() - self._last_activity > 2:
                        break
                    continue
                except websocket.WebSocketConnectionClosedException:
                    logger.warning(f"WebSocket connection closed for tab: {tab_id}")
                    break
                except Exception as e:
                    logger.error(f"Error capturing tab {tab_id}: {e}")
                    break
            
            logger.info(f"Listener stopped for tab: {tab_id}")

        thread = threading.Thread(target=listen, daemon=True)
        thread.start()
        self._listen_threads[tab_id] = thread

    def start_capture(self, tab_id: Optional[str] = None) -> bool:
        """Start capturing network traffic with enhanced header capture"""
        if not self.connections:
            logger.error("No connections available")
            return False

        logger.info("Starting capture...")
        self.is_capturing = True
        self.har_entries = []
        self.request_map = {}
        self.entry_counter = 0
        self.extracted_tokens = []
        self._message_counter = 0
        self._last_activity = time.time()

        # Reset session tokens
        self.session_tokens = {
            'authorization': None,
            'cookies': {},
            'api_keys': [],
            'headers': {},
            'bearer_tokens': [],
            'jwt_tokens': []
        }

        # Force enable network monitoring on all connections
        for tid, ws in self.connections.items():
            try:
                logger.info(f"Re-enabling network monitoring for tab: {tid}")
                # Re-enable network monitoring
                ws.send(json.dumps({"id": 100, "method": "Network.enable"}))
                ws.send(json.dumps({"id": 101, "method": "Page.enable"}))
                
                # Also enable extra info events
                ws.send(json.dumps({"id": 102, "method": "Network.enable", "params": {"maxResourceBufferSize": 100000000}}))
                logger.info(f"✅ Re-enabled network monitoring for tab: {tid}")
            except Exception as e:
                logger.error(f"❌ Failed to enable network for tab {tid}: {e}")

        # Ensure listeners are running
        for tid in self.connections:
            if tid not in self._listen_threads or not self._listen_threads[tid].is_alive():
                logger.info(f"Starting listener for tab: {tid}")
                self._start_listener(tid)

        if tab_id and tab_id in self.connections:
            logger.info(f"Capturing specific tab: {tab_id}")
        else:
            logger.info(f"Capturing all {len(self.connections)} tabs")

        logger.info("✅ Capture started successfully")
        return True

    def _capture_tab(self, tab_id: str):
        """Capture traffic from a specific tab (deprecated - use _start_listener)"""
        self._start_listener(tab_id)

    def _parse_cookies(self, cookie_str: str) -> Dict[str, str]:
        """Parse cookie string into dictionary"""
        cookies = {}
        if not cookie_str:
            return cookies

        for cookie in cookie_str.split(';'):
            cookie = cookie.strip()
            if '=' in cookie:
                key, value = cookie.split('=', 1)
                cookies[key.strip()] = value.strip()
        return cookies

    def _extract_auth_headers(self, headers: Dict) -> Dict:
        """Extract authentication headers from request"""
        auth_info = {}

        # Extract Authorization header
        auth_header = headers.get('Authorization') or headers.get('authorization')
        if auth_header:
            auth_info['authorization'] = auth_header
            if isinstance(auth_header, str) and auth_header.lower().startswith('bearer '):
                auth_info['token_type'] = 'bearer'
                auth_info['token'] = auth_header[7:]  # Remove 'Bearer '
                # Track bearer token
                self.session_tokens['bearer_tokens'].append(auth_header[7:])
            elif isinstance(auth_header, str) and auth_header.lower().startswith('basic '):
                auth_info['token_type'] = 'basic'

        # Extract API keys
        api_key_headers = ['X-API-Key', 'x-api-key', 'API-Key', 'api-key']
        for header_name in api_key_headers:
            if header_name in headers:
                key_value = headers[header_name]
                if isinstance(key_value, str):
                    auth_info.setdefault('api_keys', []).append(key_value)
                    self.session_tokens['api_keys'].append(key_value)

        # Extract cookies
        cookie_header = headers.get('Cookie') or headers.get('cookie')
        if cookie_header and isinstance(cookie_header, str):
            cookies = self._parse_cookies(cookie_header)
            auth_info['cookies'] = cookies
            # Update session cookies
            self.session_tokens['cookies'].update(cookies)

        return auth_info

    def _process_message(self, data: Dict, tab_id: str):
        """Process CDP message with enhanced header and token extraction"""
        method = data.get('method')
        params = data.get('params', {})
        
        # Handle responses to our commands
        if 'id' in data:
            if 'result' in data:
                logger.debug(f"Response to command {data['id']}: {data.get('result', {})}")
            elif 'error' in data:
                logger.error(f"Error response to command {data['id']}: {data.get('error', {})}")
            return
        
        if method == 'Network.requestWillBeSent':
            request = params.get('request', {})
            if not isinstance(request, dict):
                return

            request_id = params.get('requestId')
            if not request_id:
                return

            # Safely extract headers
            raw_headers = request.get('headers', {})
            headers = self.safe_get_headers(raw_headers)

            logger.info(f"📤 Request: {request.get('method', '')} {request.get('url', '')[:100]}")

            # Extract authentication headers
            auth_info = self._extract_auth_headers(headers)
            if auth_info:
                logger.info(f"🔑 Auth headers found: {list(auth_info.keys())}")
                with self.lock:
                    # Update session tokens
                    for key, value in auth_info.items():
                        if key == 'cookies':
                            self.session_tokens['cookies'].update(value)
                        elif key == 'api_keys':
                            self.session_tokens['api_keys'].extend(value)
                        elif key == 'authorization':
                            self.session_tokens['authorization'] = value
                            self.session_tokens['headers']['Authorization'] = value
                        elif key == 'token':
                            pass
                        else:
                            self.session_tokens[key] = value

            # Extract JWT tokens for analysis
            tokens = TokenExtractor.extract_tokens(headers)
            for token in tokens:
                if token.get('decoded'):
                    self.session_tokens['jwt_tokens'].append(token)
                    self.extracted_tokens.append(token)
                    logger.info(f"🔐 JWT token found: {token['type']} - {token['value'][:30]}...")

            # Build entry
            entry = {
                'request': {
                    'method': request.get('method', ''),
                    'url': request.get('url', ''),
                    'headers': headers,
                    'postData': request.get('postData', {})
                },
                'response': {
                    'status': 0,
                    'statusText': '',
                    'headers': {},
                    'content': {}
                },
                'timings': {},
                'startedDateTime': datetime.now().isoformat(),
                'tab_id': tab_id,
                'request_id': request_id,
                'auth_headers': headers if auth_info else {},
                'entry_number': self.entry_counter,
                'capture_time': datetime.now().isoformat()
            }

            with self.lock:
                self.request_map[request_id] = entry
                self.entry_counter += 1
                url_short = entry['request']['url'][:80] + '...' if len(entry['request']['url']) > 80 else entry['request']['url']
                logger.info(f"📥 [{self.entry_counter}] {entry['request']['method']} {url_short}")

                # Track attack surface
                self._track_attack_surface(entry)

        elif method == 'Network.requestWillBeSentExtraInfo':
            request_id = params.get('requestId')
            if request_id and request_id in self.request_map:
                raw_extra_headers = params.get('headers', {})
                extra_headers = self.safe_get_headers(raw_extra_headers)

                if extra_headers:
                    with self.lock:
                        entry = self.request_map[request_id]
                        current_headers = entry['request']['headers']
                        if not isinstance(current_headers, dict):
                            current_headers = {}
                        current_headers.update(extra_headers)
                        entry['request']['headers'] = current_headers

                        # Extract auth from extra headers
                        extra_auth = self._extract_auth_headers(extra_headers)
                        if extra_auth:
                            entry['auth_headers'] = extra_headers
                            for key, value in extra_auth.items():
                                if key == 'cookies':
                                    self.session_tokens['cookies'].update(value)

        elif method == 'Network.responseReceived':
            request_id = params.get('requestId')
            if not request_id:
                return

            with self.lock:
                if request_id in self.request_map:
                    entry = self.request_map[request_id]
                    response = params.get('response', {})
                    if not isinstance(response, dict):
                        return

                    # Safely extract response headers
                    raw_response_headers = response.get('headers', {})
                    response_headers = self.safe_get_headers(raw_response_headers)

                    entry['response']['status'] = response.get('status', 0)
                    entry['response']['statusText'] = response.get('statusText', '')
                    entry['response']['headers'] = response_headers
                    entry['response']['content']['mimeType'] = response.get('mimeType', '')
                    entry['response']['content']['size'] = response.get('contentSize', 0)

                    # Move to completed entries
                    self.har_entries.append(entry)
                    status = entry['response']['status']
                    url_short = entry['request']['url'][:60] + '...' if len(entry['request']['url']) > 60 else entry['request']['url']
                    logger.info(f"📥 Response: {status} - {url_short}")
                    del self.request_map[request_id]

                    # Update attack surface with response info
                    self._track_response_attack_surface(entry)

        elif method == 'Network.responseReceivedExtraInfo':
            request_id = params.get('requestId')
            if request_id and request_id in self.request_map:
                raw_extra_headers = params.get('headers', {})
                extra_headers = self.safe_get_headers(raw_extra_headers)

                if extra_headers:
                    with self.lock:
                        entry = self.request_map[request_id]
                        if request_id in self.request_map:
                            entry = self.request_map[request_id]
                            current_headers = entry['response']['headers']
                            if not isinstance(current_headers, dict):
                                current_headers = {}
                            current_headers.update(extra_headers)
                            entry['response']['headers'] = current_headers

    def _track_attack_surface(self, entry: Dict):
        """Track attack surface from request data"""
        request = entry.get('request', {})
        if not isinstance(request, dict):
            return

        url = request.get('url', '')
        if not url:
            return

        parsed = urlparse(url)
        host = parsed.netloc
        path = parsed.path or '/'
        method = request.get('method', 'GET')

        # Track domain
        self.attack_surface['domains'].add(host)

        # Track endpoint
        endpoint_key = f"{host}{path}"
        endpoint = self.attack_surface['endpoints'][endpoint_key]
        endpoint['methods'].add(method)

        # Track headers
        headers = request.get('headers', {})
        if isinstance(headers, dict):
            for header_name in headers.keys():
                endpoint['headers'].add(header_name)

        # Track query parameters
        query_params = parse_qs(parsed.query)
        for param in query_params.keys():
            endpoint['query_params'].add(param)

        # Track body parameters
        post_data = request.get('postData', {})
        if post_data:
            text = post_data.get('text', '')
            if text:
                try:
                    json_data = json.loads(text)
                    if isinstance(json_data, dict):
                        for key in json_data.keys():
                            endpoint['body_params'].add(key)
                except:
                    if '=' in text:
                        params = re.findall(r'([^&=]+)=', text)
                        for param in params:
                            endpoint['body_params'].add(param)

        # Track authentication
        if isinstance(headers, dict):
            tokens = TokenExtractor.extract_tokens(headers)
            for token in tokens:
                endpoint['auth_methods'].add(token['type'])

        # Identify authentication endpoints
        if any(word in path.lower() for word in ['login', 'auth', 'signin', 'token', 'oauth']):
            self.attack_surface['authentication_endpoints'].append({
                'url': url,
                'method': method,
                'auth_methods': list(endpoint['auth_methods']),
                'timestamp': entry.get('startedDateTime', '')
            })

    def _track_response_attack_surface(self, entry: Dict):
        """Track attack surface from response data"""
        response = entry.get('response', {})
        if not isinstance(response, dict):
            return

        request = entry.get('request', {})
        if not isinstance(request, dict):
            return

        url = request.get('url', '')
        if not url:
            return

        parsed = urlparse(url)
        path = parsed.path or '/'
        status = response.get('status', 0)

        # Update endpoint with response info
        host = parsed.netloc
        endpoint_key = f"{host}{path}"
        if endpoint_key in self.attack_surface['endpoints']:
            endpoint = self.attack_surface['endpoints'][endpoint_key]
            endpoint['response_statuses'].add(status)

            content_type = response.get('content', {}).get('mimeType', '')
            if content_type:
                endpoint['content_types'].add(content_type.split(';')[0])

    def stop_capture(self) -> List[Dict]:
        """Stop capturing and return HAR entries"""
        logger.info("Stopping capture...")
        self.is_capturing = False
        
        # Wait for threads to finish
        for tab_id, thread in self._listen_threads.items():
            try:
                thread.join(timeout=2)
            except:
                pass
        
        logger.info(f"Capture stopped. Total entries: {len(self.har_entries)}")
        return self.har_entries

    def get_tabs(self) -> List[Dict]:
        """Get list of available tabs"""
        import requests
        try:
            response = requests.get(f"http://127.0.0.1:{self.port}/json", timeout=2)
            tabs = response.json()
            logger.info(f"Found {len(tabs)} tabs on port {self.port}")
            return tabs
        except Exception as e:
            logger.error(f"Failed to get tabs: {e}")
            return []

    def export_har(self, filename: str = None) -> Dict:
        """Export captured data as HAR with token information"""
        if not filename:
            filename = f"har_capture_{datetime.now().strftime('%Y%m%d_%H%M%S')}.har"

        har_data = {
            'log': {
                'version': '1.2',
                'creator': {
                    'name': 'CDP HAR Capturer - Enhanced',
                    'version': '2.0.0'
                },
                'entries': self.har_entries
            },
            'session_tokens': self.session_tokens,
            'extracted_tokens': self.extracted_tokens,
            'attack_surface': {
                'domains': list(self.attack_surface['domains']),
                'authentication_endpoints': self.attack_surface['authentication_endpoints'],
                'endpoints': {}
            },
            'capture_stats': {
                'total_entries': len(self.har_entries),
                'total_messages': self._message_counter,
                'capture_duration': time.time() - self._last_activity
            }
        }

        # Convert sets to lists for JSON serialization
        for endpoint_key, data in self.attack_surface['endpoints'].items():
            har_data['attack_surface']['endpoints'][endpoint_key] = {
                'methods': list(data['methods']),
                'query_params': list(data['query_params']),
                'body_params': list(data['body_params']),
                'auth_methods': list(data['auth_methods']),
                'headers': list(data['headers']),
                'response_statuses': list(data['response_statuses']),
                'content_types': list(data['content_types'])
            }

        # Add session tokens to each entry
        for entry in har_data['log']['entries']:
            if 'auth_headers' in entry and entry['auth_headers']:
                entry['auth_info'] = self._extract_auth_headers(entry['auth_headers'])
            # Add token analysis
            if 'request' in entry and 'headers' in entry['request']:
                tokens = TokenExtractor.extract_tokens(entry['request']['headers'])
                if tokens:
                    entry['extracted_tokens'] = tokens

        with open(filename, 'w') as f:
            json.dump(har_data, f, indent=2)

        logger.info(f"HAR exported to: {filename}")
        logger.info(f"  - Total entries: {len(self.har_entries)}")
        logger.info(f"  - Tokens extracted: {len(self.extracted_tokens)}")
        logger.info(f"  - Authentication endpoints: {len(self.attack_surface['authentication_endpoints'])}")
        logger.info(f"  - Messages processed: {self._message_counter}")
        return har_data

    def get_session_tokens(self) -> Dict:
        """Get extracted session tokens"""
        return self.session_tokens

    def get_attack_surface_report(self) -> Dict:
        """Get attack surface report"""
        return {
            'domains': list(self.attack_surface['domains']),
            'authentication_endpoints': self.attack_surface['authentication_endpoints'],
            'endpoints': {
                key: {
                    'methods': list(data['methods']),
                    'query_params': list(data['query_params']),
                    'body_params': list(data['body_params']),
                    'auth_methods': list(data['auth_methods']),
                    'headers': list(data['headers']),
                    'response_statuses': list(data['response_statuses']),
                    'content_types': list(data['content_types'])
                }
                for key, data in self.attack_surface['endpoints'].items()
            }
        }


# Example usage
if __name__ == "__main__":
    # Initialize capturer
    capturer = CDPCapturer(port=9222)
    
    # Get available tabs
    tabs = capturer.get_tabs()
    print(f"Found {len(tabs)} tabs")
    
    # Connect to all tabs
    for tab in tabs:
        if tab['type'] == 'page':
            capturer.connect_to_tab(tab['id'], tab['webSocketDebuggerUrl'])
    
    # Start capture
    capturer.start_capture()
    
    # Let it run for a while
    print("Capturing for 30 seconds...")
    time.sleep(30)
    
    # Stop capture
    entries = capturer.stop_capture()
    print(f"Captured {len(entries)} requests")
    
    # Export HAR
    har_data = capturer.export_har("capture_complete.har")
    
    # Get security analysis
    tokens = capturer.get_session_tokens()
    attack_surface = capturer.get_attack_surface_report()
    
    print(f"\n=== Security Analysis Report ===")
    print(f"Total Requests: {len(entries)}")
    print(f"Tokens Found: {len(capturer.extracted_tokens)}")
    print(f"Authentication Endpoints: {len(attack_surface['authentication_endpoints'])}")
    print(f"Domains Detected: {len(attack_surface['domains'])}")
    print(f"Unique Endpoints: {len(attack_surface['endpoints'])}")
