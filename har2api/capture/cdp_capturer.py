"""
Chrome DevTools Protocol HAR capture - Enhanced version with full header capture and token extraction
"""

import json
import websocket
import time
import threading
from typing import Dict, List, Optional, Any
from datetime import datetime
from collections import defaultdict
import logging
import re
import base64
from urllib.parse import urlparse, parse_qs

# Module-level logger. Do NOT call basicConfig here — let the application
# decide log levels. If nothing has configured logging, fall back to INFO.
logger = logging.getLogger(__name__)
if not logging.getLogger().handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


class TokenExtractor:
    """Extract and analyze authentication tokens from requests"""

    @staticmethod
    def decode_jwt(token: str) -> Optional[Dict]:
        """Decode JWT without verification for analysis"""
        try:
            parts = token.split('.')
            if len(parts) != 3:
                return None

            # Pad base64 as needed
            def _pad(s: str) -> str:
                return s + '=' * (-len(s) % 4)

            header = json.loads(
                base64.urlsafe_b64decode(_pad(parts[0])).decode('utf-8')
            )
            payload = json.loads(
                base64.urlsafe_b64decode(_pad(parts[1])).decode('utf-8')
            )

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
                'claims': payload,
            }
        except Exception:
            return None

    @staticmethod
    def extract_tokens(headers: Dict) -> List[Dict]:
        """Extract all tokens from headers"""
        tokens: List[Dict] = []

        if not isinstance(headers, dict):
            return tokens

        for header_name, header_value in headers.items():
            if not isinstance(header_name, str):
                continue
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
                        'decoded': decoded,
                    })
                elif isinstance(header_value, str) and header_value.startswith('Basic '):
                    tokens.append({
                        'type': 'Basic',
                        'header': header_name,
                        'value': header_value[:50] + '...' if len(header_value) > 50 else header_value,
                        'full_value': header_value,
                        'decoded': None,
                    })

            elif header_lower in ('x-auth-token', 'x-api-token', 'x-api-key'):
                if isinstance(header_value, str):
                    decoded = TokenExtractor.decode_jwt(header_value)
                    tokens.append({
                        'type': 'Custom',
                        'header': header_name,
                        'value': header_value[:50] + '...' if len(header_value) > 50 else header_value,
                        'full_value': header_value,
                        'decoded': decoded,
                    })

            elif header_lower == 'cookie' and isinstance(header_value, str):
                cookies = re.findall(r'([^=;,]+)=([^;,]+)', header_value)
                for cookie_name, cookie_value in cookies:
                    cookie_name = cookie_name.strip()
                    cookie_value = cookie_value.strip()
                    if any(k in cookie_name.lower() for k in ('token', 'jwt', 'auth', 'session')):
                        decoded = TokenExtractor.decode_jwt(cookie_value)
                        tokens.append({
                            'type': 'Cookie',
                            'header': header_name,
                            'cookie_name': cookie_name,
                            'value': cookie_value[:50] + '...' if len(cookie_value) > 50 else cookie_value,
                            'full_value': cookie_value,
                            'decoded': decoded,
                        })

        return tokens


class CDPCapturer:
    """Capture HAR data using Chrome DevTools Protocol with enhanced header and token extraction"""

    def __init__(self, port: int = 9222, max_entries: int = 10000):
        self.port = port
        self.connections: Dict[str, websocket.WebSocket] = {}
        self.har_entries: List[Dict] = []
        self.request_map: Dict[str, Dict] = {}
        self.is_capturing = False
        self.lock = threading.Lock()
        self.max_entries = max_entries
        self.entry_counter = 0
        self._listen_threads: Dict[str, threading.Thread] = {}
        self._message_counter = 0
        self._last_activity = time.time()
        self._stop_event = threading.Event()

        # Enhanced session token tracking
        self.session_tokens = {
            'authorization': None,
            'cookies': {},
            'api_keys': [],
            'headers': {},
            'bearer_tokens': [],
            'jwt_tokens': [],
        }

        # Track all extracted tokens
        self.extracted_tokens: List[Dict] = []
        self.attack_surface = {
            'endpoints': defaultdict(lambda: {
                'methods': set(),
                'query_params': set(),
                'body_params': set(),
                'auth_methods': set(),
                'headers': set(),
                'response_statuses': set(),
                'content_types': set(),
            }),
            'domains': set(),
            'authentication_endpoints': [],
        }

    # ------------------------------------------------------------------ #
    # Header helpers
    # ------------------------------------------------------------------ #
    def safe_get_headers(self, headers_data: Any) -> Dict:
        """Safely convert headers to dictionary with comprehensive parsing"""
        if isinstance(headers_data, dict):
            return headers_data

        if not headers_data:
            return {}

        if isinstance(headers_data, str):
            # Strategy 1: JSON
            try:
                parsed = json.loads(headers_data)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                pass

            # Strategy 2: HTTP header lines
            try:
                result = {}
                for line in headers_data.strip().split('\n'):
                    line = line.strip()
                    if ':' in line:
                        key, value = line.split(':', 1)
                        key, value = key.strip(), value.strip()
                        if key and value:
                            result[key] = value
                if result:
                    return result
            except Exception:
                pass

            # Strategy 3: URL-encoded
            try:
                result = {}
                for pair in headers_data.split('&'):
                    if '=' in pair:
                        key, value = pair.split('=', 1)
                        key, value = key.strip(), value.strip()
                        if key and value:
                            result[key] = value
                if result:
                    return result
            except Exception:
                pass

            # Strategy 4: Regex
            try:
                result = {}
                for key, value in re.findall(r'([^:=]+)[:=]\s*([^&\n]+)', headers_data):
                    key, value = key.strip(), value.strip()
                    if key and value:
                        result[key] = value
                if result:
                    return result
            except Exception:
                pass

            # Strategy 5: Cookie header
            try:
                if '=' in headers_data and ':' not in headers_data:
                    result = {}
                    for cookie_name, cookie_value in re.findall(r'([^=;,]+)=([^;,]+)', headers_data):
                        cookie_name, cookie_value = cookie_name.strip(), cookie_value.strip()
                        if cookie_name and cookie_value:
                            result[cookie_name] = cookie_value
                    if result:
                        return result
            except Exception:
                pass

        return {}

    def _parse_cookies(self, cookie_str: str) -> Dict[str, str]:
        """Parse cookie string into dictionary"""
        cookies: Dict[str, str] = {}
        if not cookie_str or not isinstance(cookie_str, str):
            return cookies

        for cookie in cookie_str.split(';'):
            cookie = cookie.strip()
            if '=' in cookie:
                key, value = cookie.split('=', 1)
                cookies[key.strip()] = value.strip()
        return cookies

    def _extract_auth_headers(self, headers: Dict) -> Dict:
        """Extract authentication headers from request"""
        auth_info: Dict[str, Any] = {}

        if not isinstance(headers, dict):
            return auth_info

        # Authorization
        auth_header = headers.get('Authorization') or headers.get('authorization')
        if auth_header:
            auth_info['authorization'] = auth_header
            if isinstance(auth_header, str) and auth_header.lower().startswith('bearer '):
                auth_info['token_type'] = 'bearer'
                auth_info['token'] = auth_header[7:]
                self.session_tokens['bearer_tokens'].append(auth_header[7:])
            elif isinstance(auth_header, str) and auth_header.lower().startswith('basic '):
                auth_info['token_type'] = 'basic'

        # API keys
        for header_name in ('X-API-Key', 'x-api-key', 'API-Key', 'api-key'):
            if header_name in headers:
                key_value = headers[header_name]
                if isinstance(key_value, str):
                    auth_info.setdefault('api_keys', []).append(key_value)
                    self.session_tokens['api_keys'].append(key_value)

        # Cookies
        cookie_header = headers.get('Cookie') or headers.get('cookie')
        if isinstance(cookie_header, str):
            cookies = self._parse_cookies(cookie_header)
            auth_info['cookies'] = cookies
            self.session_tokens['cookies'].update(cookies)

        return auth_info

    # ------------------------------------------------------------------ #
    # Connection / listeners
    # ------------------------------------------------------------------ #
    def connect_to_tab(self, tab_id: str, ws_url: str) -> bool:
        """Connect to a Chrome tab via WebSocket with enhanced capabilities"""
        try:
            logger.info(f"Connecting to tab: {tab_id} at {ws_url[:50]}...")
            ws = websocket.create_connection(ws_url, timeout=10, enable_multithread=True)
            self.connections[tab_id] = ws

            # Drain the responses to our enable commands safely.
            def _send_and_drain(cmd_id: int, method: str, params: Optional[Dict] = None):
                payload = {"id": cmd_id, "method": method}
                if params is not None:
                    payload["params"] = params
                ws.send(json.dumps(payload))
                try:
                    raw = ws.recv()
                    if isinstance(raw, str):
                        logger.debug(f"{method} response: {raw[:120]}")
                except Exception as e:
                    logger.debug(f"{method} drain failed: {e}")

            _send_and_drain(1, "Network.enable", {"maxResourceBufferSize": 100_000_000})
            _send_and_drain(2, "Page.enable")
            _send_and_drain(3, "Runtime.enable")

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
            while not self._stop_event.is_set():
                try:
                    ws.settimeout(0.5)
                    msg = ws.recv()
                    if not msg:
                        continue

                    self._message_counter += 1
                    self._last_activity = time.time()

                    # --- THE FIX ---
                    # json.loads can legally return str / int / list / bool / None.
                    # Only dict-shaped messages are CDP events.
                    try:
                        data = json.loads(msg)
                    except json.JSONDecodeError as e:
                        logger.debug(f"Invalid JSON from CDP: {e}")
                        continue

                    if not isinstance(data, dict):
                        logger.debug(
                            f"Skipping non-dict CDP message: {type(data).__name__}"
                        )
                        continue
                    # ----------------

                    method = data.get('method', '')
                    params = data.get('params')
                    if not isinstance(params, dict):
                        params = {}

                    # Only log the interesting events
                    if method in ('Network.requestWillBeSent', 'Network.responseReceived'):
                        rid = str(params.get('requestId', ''))[:8]
                        logger.info(f"📨 {method} - {rid}")
                    elif method.startswith('Network.') and self._message_counter % 100 == 0:
                        logger.debug(f"📨 {method} (message #{self._message_counter})")

                    try:
                        self._process_message(data, tab_id)
                    except Exception as e:
                        logger.error(f"Error processing message: {e}", exc_info=False)

                except websocket.WebSocketTimeoutException:
                    continue
                except websocket.WebSocketConnectionClosedException:
                    logger.warning(f"WebSocket connection closed for tab: {tab_id}")
                    break
                except Exception as e:
                    logger.error(f"Error capturing tab {tab_id}: {e}")
                    break

            logger.info(f"Listener stopped for tab: {tab_id}")

        thread = threading.Thread(target=listen, daemon=True, name=f"cdp-listen-{tab_id[:8]}")
        thread.start()
        self._listen_threads[tab_id] = thread

    # ------------------------------------------------------------------ #
    # Capture lifecycle
    # ------------------------------------------------------------------ #
    def start_capture(self, tab_id: Optional[str] = None) -> bool:
        """Start capturing network traffic with enhanced header capture"""
        if not self.connections:
            logger.error("No connections available")
            return False

        logger.info("Starting capture...")
        self._stop_event.clear()
        self.is_capturing = True
        self.har_entries = []
        self.request_map = {}
        self.entry_counter = 0
        self.extracted_tokens = []
        self._message_counter = 0
        self._last_activity = time.time()

        self.session_tokens = {
            'authorization': None,
            'cookies': {},
            'api_keys': [],
            'headers': {},
            'bearer_tokens': [],
            'jwt_tokens': [],
        }

        # Force-enable network monitoring on all connections
        for tid, ws in self.connections.items():
            try:
                ws.send(json.dumps({"id": 100, "method": "Network.enable"}))
                ws.send(json.dumps({"id": 101, "method": "Page.enable"}))
                ws.send(json.dumps({
                    "id": 102,
                    "method": "Network.enable",
                    "params": {"maxResourceBufferSize": 100_000_000},
                }))
                logger.info(f"✅ Re-enabled network monitoring for tab: {tid}")
            except Exception as e:
                logger.error(f"❌ Failed to enable network for tab {tid}: {e}")

        # Ensure listeners are running
        for tid in self.connections:
            t = self._listen_threads.get(tid)
            if t is None or not t.is_alive():
                logger.info(f"Starting listener for tab: {tid}")
                self._start_listener(tid)

        if tab_id and tab_id in self.connections:
            logger.info(f"Capturing specific tab: {tab_id}")
        else:
            logger.info(f"Capturing all {len(self.connections)} tabs")

        logger.info("✅ Capture started successfully")
        return True

    def stop_capture(self) -> List[Dict]:
        """Stop capturing and return HAR entries"""
        logger.info("Stopping capture...")
        self.is_capturing = False
        self._stop_event.set()

        for tab_id, thread in list(self._listen_threads.items()):
            try:
                thread.join(timeout=2)
            except Exception:
                pass

        logger.info(f"Capture stopped. Total entries: {len(self.har_entries)}")
        return self.har_entries

    # ------------------------------------------------------------------ #
    # Message processing
    # ------------------------------------------------------------------ #
    def _process_message(self, data: Dict, tab_id: str):
        """Process CDP message with enhanced header and token extraction"""
        # Defensive: never assume dict here either
        if not isinstance(data, dict):
            return

        method = data.get('method')
        params = data.get('params')
        if not isinstance(params, dict):
            params = {}

        # Handle responses to our commands
        if 'id' in data and method is None:
            if 'result' in data:
                logger.debug(f"Response to command {data['id']}: {data.get('result', {})}")
            elif 'error' in data:
                logger.error(f"Error response to command {data['id']}: {data.get('error', {})}")
            return

        if method == 'Network.requestWillBeSent':
            request = params.get('request')
            if not isinstance(request, dict):
                return

            request_id = params.get('requestId')
            if not request_id:
                return

            raw_headers = request.get('headers', {})
            headers = self.safe_get_headers(raw_headers)

            logger.info(f"📤 Request: {request.get('method', '')} {str(request.get('url', ''))[:100]}")

            auth_info = self._extract_auth_headers(headers)
            if auth_info:
                logger.info(f"🔑 Auth headers found: {list(auth_info.keys())}")
                with self.lock:
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

            tokens = TokenExtractor.extract_tokens(headers)
            for token in tokens:
                if token.get('decoded'):
                    self.session_tokens['jwt_tokens'].append(token)
                    self.extracted_tokens.append(token)
                    logger.info(f"🔐 JWT token found: {token['type']} - {token['value'][:30]}...")

            post_data = request.get('postData', {})
            if not isinstance(post_data, dict):
                post_data = {'text': post_data} if isinstance(post_data, str) else {}

            entry = {
                'request': {
                    'method': request.get('method', ''),
                    'url': request.get('url', ''),
                    'headers': headers,
                    'postData': post_data,
                },
                'response': {
                    'status': 0,
                    'statusText': '',
                    'headers': {},
                    'content': {},
                },
                'timings': {},
                'startedDateTime': datetime.now().isoformat(),
                'tab_id': tab_id,
                'request_id': request_id,
                'auth_headers': headers if auth_info else {},
                'entry_number': self.entry_counter,
                'capture_time': datetime.now().isoformat(),
            }

            with self.lock:
                self.request_map[request_id] = entry
                self.entry_counter += 1
                url = str(entry['request'].get('url', ''))
                url_short = url[:80] + '...' if len(url) > 80 else url
                logger.info(f"📥 [{self.entry_counter}] {entry['request'].get('method', '')} {url_short}")
                self._track_attack_surface(entry)

        elif method == 'Network.requestWillBeSentExtraInfo':
            request_id = params.get('requestId')
            if request_id and request_id in self.request_map:
                extra_headers = self.safe_get_headers(params.get('headers', {}))
                if extra_headers:
                    with self.lock:
                        entry = self.request_map[request_id]
                        current = entry['request'].get('headers')
                        if not isinstance(current, dict):
                            current = {}
                        current.update(extra_headers)
                        entry['request']['headers'] = current

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
                entry = self.request_map.get(request_id)
                if entry is None:
                    return

                response = params.get('response')
                if not isinstance(response, dict):
                    return

                response_headers = self.safe_get_headers(response.get('headers', {}))

                entry['response']['status'] = response.get('status', 0)
                entry['response']['statusText'] = response.get('statusText', '')
                entry['response']['headers'] = response_headers
                entry['response']['content']['mimeType'] = response.get('mimeType', '')
                entry['response']['content']['size'] = response.get('contentSize', 0)

                self.har_entries.append(entry)
                status = entry['response']['status']
                url = str(entry['request'].get('url', ''))
                url_short = url[:60] + '...' if len(url) > 60 else url
                logger.info(f"📥 Response: {status} - {url_short}")
                del self.request_map[request_id]

                self._track_response_attack_surface(entry)

        elif method == 'Network.responseReceivedExtraInfo':
            request_id = params.get('requestId')
            if request_id and request_id in self.request_map:
                extra_headers = self.safe_get_headers(params.get('headers', {}))
                if extra_headers:
                    with self.lock:
                        entry = self.request_map.get(request_id)
                        if entry is None:
                            return
                        current = entry['response'].get('headers')
                        if not isinstance(current, dict):
                            current = {}
                        current.update(extra_headers)
                        entry['response']['headers'] = current

    # ------------------------------------------------------------------ #
    # Attack surface tracking
    # ------------------------------------------------------------------ #
    def _track_attack_surface(self, entry: Dict):
        """Track attack surface from request data"""
        request = entry.get('request', {})
        if not isinstance(request, dict):
            return

        url = request.get('url', '')
        if not isinstance(url, str) or not url:
            return

        parsed = urlparse(url)
        host = parsed.netloc
        path = parsed.path or '/'
        method = request.get('method', 'GET')

        self.attack_surface['domains'].add(host)

        endpoint_key = f"{host}{path}"
        endpoint = self.attack_surface['endpoints'][endpoint_key]
        endpoint['methods'].add(method)

        headers = request.get('headers', {})
        if isinstance(headers, dict):
            for header_name in headers.keys():
                endpoint['headers'].add(header_name)

        for param in parse_qs(parsed.query).keys():
            endpoint['query_params'].add(param)

        post_data = request.get('postData', {})
        if isinstance(post_data, dict):
            text = post_data.get('text', '')
        elif isinstance(post_data, str):
            text = post_data
        else:
            text = ''

        if isinstance(text, str) and text:
            try:
                json_data = json.loads(text)
                if isinstance(json_data, dict):
                    for key in json_data.keys():
                        endpoint['body_params'].add(key)
            except Exception:
                if '=' in text:
                    for param in re.findall(r'([^&=]+)=', text):
                        endpoint['body_params'].add(param)

        if isinstance(headers, dict):
            for token in TokenExtractor.extract_tokens(headers):
                endpoint['auth_methods'].add(token['type'])

        if any(word in path.lower() for word in ('login', 'auth', 'signin', 'token', 'oauth')):
            self.attack_surface['authentication_endpoints'].append({
                'url': url,
                'method': method,
                'auth_methods': list(endpoint['auth_methods']),
                'timestamp': entry.get('startedDateTime', ''),
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
        if not isinstance(url, str) or not url:
            return

        parsed = urlparse(url)
        path = parsed.path or '/'
        status = response.get('status', 0)

        endpoint_key = f"{parsed.netloc}{path}"
        if endpoint_key in self.attack_surface['endpoints']:
            endpoint = self.attack_surface['endpoints'][endpoint_key]
            endpoint['response_statuses'].add(status)

            content = response.get('content')
            if isinstance(content, dict):
                content_type = content.get('mimeType', '')
                if isinstance(content_type, str) and content_type:
                    endpoint['content_types'].add(content_type.split(';')[0])

    # ------------------------------------------------------------------ #
    # Tabs / export / reports
    # ------------------------------------------------------------------ #
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

    def export_har(self, filename: Optional[str] = None) -> Dict:
        """Export captured data as HAR with token information"""
        if not filename:
            filename = f"har_capture_{datetime.now().strftime('%Y%m%d_%H%M%S')}.har"

        har_data = {
            'log': {
                'version': '1.2',
                'creator': {
                    'name': 'CDP HAR Capturer - Enhanced',
                    'version': '2.0.0',
                },
                'entries': self.har_entries,
            },
            'session_tokens': self.session_tokens,
            'extracted_tokens': self.extracted_tokens,
            'attack_surface': {
                'domains': list(self.attack_surface['domains']),
                'authentication_endpoints': self.attack_surface['authentication_endpoints'],
                'endpoints': {},
            },
            'capture_stats': {
                'total_entries': len(self.har_entries),
                'total_messages': self._message_counter,
                'capture_duration': time.time() - self._last_activity,
            },
        }

        for endpoint_key, data in self.attack_surface['endpoints'].items():
            har_data['attack_surface']['endpoints'][endpoint_key] = {
                'methods': list(data['methods']),
                'query_params': list(data['query_params']),
                'body_params': list(data['body_params']),
                'auth_methods': list(data['auth_methods']),
                'headers': list(data['headers']),
                'response_statuses': list(data['response_statuses']),
                'content_types': list(data['content_types']),
            }

        for entry in har_data['log']['entries']:
            if entry.get('auth_headers'):
                entry['auth_info'] = self._extract_auth_headers(entry['auth_headers'])
            req = entry.get('request')
            if isinstance(req, dict) and isinstance(req.get('headers'), dict):
                tokens = TokenExtractor.extract_tokens(req['headers'])
                if tokens:
                    entry['extracted_tokens'] = tokens

        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(har_data, f, indent=2, default=str)

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
                    'content_types': list(data['content_types']),
                }
                for key, data in self.attack_surface['endpoints'].items()
            },
        }


# Example usage
if __name__ == "__main__":
    capturer = CDPCapturer(port=9222)

    tabs = capturer.get_tabs()
    print(f"Found {len(tabs)} tabs")

    for tab in tabs:
        if tab.get('type') == 'page':
            capturer.connect_to_tab(tab['id'], tab['webSocketDebuggerUrl'])

    capturer.start_capture()

    print("Capturing for 30 seconds...")
    time.sleep(30)

    entries = capturer.stop_capture()
    print(f"Captured {len(entries)} requests")

    capturer.export_har("capture_complete.har")

    tokens = capturer.get_session_tokens()
    attack_surface = capturer.get_attack_surface_report()

    print("\n=== Security Analysis Report ===")
    print(f"Total Requests: {len(entries)}")
    print(f"Tokens Found: {len(capturer.extracted_tokens)}")
    print(f"Authentication Endpoints: {len(attack_surface['authentication_endpoints'])}")
    print(f"Domains Detected: {len(attack_surface['domains'])}")
    print(f"Unique Endpoints: {len(attack_surface['endpoints'])}")
