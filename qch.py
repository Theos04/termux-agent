#!/usr/bin/env python3
"""
Complete HAR Capture & Analysis Tool
Dynamic port selection with real-time capture and comprehensive analysis
"""

import websocket
import json
import time
import sys
import requests
from datetime import datetime
from typing import Dict, List, Optional, Any, Set, Tuple
import threading
from collections import defaultdict, Counter
import os
import signal
import logging
import traceback
from dataclasses import dataclass, field
from enum import Enum
import hashlib
import re
import base64
import urllib.parse
import subprocess
import psutil
import tempfile

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('har_capture.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# ============================================================================
# CHROME DISCOVERY & PORT MANAGEMENT
# ============================================================================

class ChromeDiscovery:
    """Discover Chrome instances and their debugging ports"""
    
    COMMON_PORTS = [9222, 9223, 9224, 9225, 9226, 9227, 9228, 9229, 9258, 9259, 9260, 9261, 9262]
    
    @staticmethod
    def find_chrome_processes() -> List[Dict]:
        """Find running Chrome processes with debugging enabled"""
        chrome_processes = []
        
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                name = proc.info['name'] or ''
                cmdline = proc.info['cmdline'] or []
                cmdline_str = ' '.join(cmdline) if cmdline else ''
                
                if any(browser in name.lower() for browser in ['chrome', 'chromium', 'brave', 'edge']):
                    if '--remote-debugging-port' in cmdline_str:
                        port_match = re.search(r'--remote-debugging-port=(\d+)', cmdline_str)
                        if port_match:
                            port = int(port_match.group(1))
                            chrome_processes.append({
                                'pid': proc.info['pid'],
                                'name': name,
                                'port': port,
                                'cmdline': cmdline_str,
                                'is_debugging': True
                            })
                    else:
                        chrome_processes.append({
                            'pid': proc.info['pid'],
                            'name': name,
                            'port': None,
                            'cmdline': cmdline_str,
                            'is_debugging': False
                        })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        return chrome_processes
    
    @staticmethod
    def check_port(port: int, timeout: float = 2.0) -> bool:
        """Check if a port is running a Chrome debugging server"""
        try:
            response = requests.get(f"http://127.0.0.1:{port}/json", timeout=timeout)
            return response.status_code == 200
        except:
            return False
    
    @staticmethod
    def scan_ports(ports: List[int] = None) -> List[int]:
        """Scan for Chrome debugging ports"""
        if ports is None:
            ports = ChromeDiscovery.COMMON_PORTS
        
        available_ports = []
        for port in ports:
            if ChromeDiscovery.check_port(port):
                available_ports.append(port)
                logger.info(f"✅ Found Chrome debugging on port {port}")
        
        return available_ports
    
    @staticmethod
    def get_tabs(port: int) -> List[Dict]:
        """Get tabs from a Chrome debugging port"""
        try:
            response = requests.get(f"http://127.0.0.1:{port}/json", timeout=5)
            return response.json()
        except Exception as e:
            logger.error(f"Error getting tabs from port {port}: {e}")
            return []
    
    @staticmethod
    def get_active_tab(port: int) -> Optional[Dict]:
        """Get the active tab from a Chrome debugging port"""
        tabs = ChromeDiscovery.get_tabs(port)
        for tab in tabs:
            if tab.get('type') == 'page' and tab.get('webSocketDebuggerUrl'):
                return tab
        return None
    
    @staticmethod
    def start_chrome_with_debugging(port: int = 9222, 
                                   user_data_dir: str = None) -> subprocess.Popen:
        """Start Chrome with debugging enabled"""
        chrome_paths = [
            '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
            '/usr/bin/google-chrome',
            '/usr/bin/chromium-browser',
            'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
            'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
        ]
        
        chrome_path = None
        for path in chrome_paths:
            if os.path.exists(path):
                chrome_path = path
                break
        
        if not chrome_path:
            for cmd in ['google-chrome', 'chromium', 'chrome', 'chromium-browser']:
                if subprocess.run(['which', cmd], capture_output=True).returncode == 0:
                    chrome_path = cmd
                    break
        
        if not chrome_path:
            raise Exception("Chrome not found. Please install Chrome or specify the path.")
        
        cmd = [chrome_path, f'--remote-debugging-port={port}']
        
        if user_data_dir:
            cmd.append(f'--user-data-dir={user_data_dir}')
        else:
            temp_dir = tempfile.mkdtemp(prefix='chrome_debug_')
            cmd.append(f'--user-data-dir={temp_dir}')
        
        logger.info(f"🚀 Starting Chrome with debugging on port {port}")
        
        if sys.platform == 'win32':
            CREATE_NEW_PROCESS_GROUP = 0x00000200
            process = subprocess.Popen(
                cmd,
                creationflags=CREATE_NEW_PROCESS_GROUP,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        else:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                preexec_fn=os.setsid if hasattr(os, 'setsid') else None
            )
        
        time.sleep(2)
        
        if ChromeDiscovery.check_port(port):
            logger.info(f"✅ Chrome started successfully on port {port}")
            return process
        else:
            logger.error(f"❌ Chrome failed to start on port {port}")
            return None


# ============================================================================
# TOKEN EXTRACTOR
# ============================================================================

@dataclass
class ExtractedToken:
    """Represents an extracted authentication token"""
    token_type: str
    token_value: str
    source: str
    location: str
    url: str
    timestamp: str
    method: str
    status_code: int
    confidence: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    hashed_value: str = field(default_factory=str)

    def __post_init__(self):
        if not self.hashed_value and self.token_value:
            self.hashed_value = hashlib.sha256(
                self.token_value.encode('utf-8')
            ).hexdigest()[:16]

    def mask(self) -> str:
        if len(self.token_value) > 10:
            return f"{self.token_value[:8]}...{self.token_value[-4:]}"
        return "***MASKED***"


class TokenExtractor:
    """Extracts authentication tokens from HAR entries"""
    
    JWT_PATTERN = re.compile(r'^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$')
    BEARER_PATTERN = re.compile(r'^Bearer\s+(.+)$', re.IGNORECASE)
    BASIC_PATTERN = re.compile(r'^Basic\s+(.+)$', re.IGNORECASE)
    API_KEY_PATTERNS = [
        re.compile(r'^[A-Za-z0-9]{32,64}$'),
        re.compile(r'^sk-[A-Za-z0-9]{32,64}$'),
        re.compile(r'^pk_[A-Za-z0-9]{32,64}$'),
        re.compile(r'^[A-Fa-f0-9]{64}$'),
        re.compile(r'^[A-Za-z0-9+/=]{32,128}$'),
    ]
    UUID_PATTERN = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.IGNORECASE)

    AUTH_HEADERS = [
        'authorization', 'x-auth-token', 'x-api-key', 'api-key',
        'x-access-token', 'x-csrf-token', 'csrf-token', 'x-xsrf-token',
        'x-session-token', 'session-token', 'access-token', 'refresh-token',
        'x-user-token', 'user-token', 'x-jwt-token', 'jwt-token',
        'x-oauth-token', 'oauth-token', 'x-identity-token', 'identity-token',
        'x-app-token', 'app-token', 'x-device-token', 'device-token',
        'x-authentication', 'authentication', 'x-auth', 'auth'
    ]

    TOKEN_COOKIE_NAMES = [
        'token', 'access_token', 'refresh_token', 'jwt', 'auth',
        'session', 'sid', 'csrf', 'xsrf', 'x-csrf-token',
        'oauth_token', 'oauth2_token', 'id_token', 'user_token',
        'app_token', 'device_token', 'api_token', 'apikey'
    ]

    TOKEN_RESPONSE_FIELDS = [
        'token', 'access_token', 'refresh_token', 'jwt',
        'auth_token', 'api_token', 'bearer_token', 'id_token',
        'oauth_token', 'session_token', 'user_token',
        'accessToken', 'refreshToken', 'idToken', 'authToken'
    ]

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.max_token_length = self.config.get('max_token_length', 4096)
        self.min_token_length = self.config.get('min_token_length', 8)
        self.extract_from_body = self.config.get('extract_from_body', True)
        self.extract_from_response = self.config.get('extract_from_response', True)
        self.max_body_size = self.config.get('max_body_size', 1024 * 1024)
        
        self.tokens_found: List[ExtractedToken] = []
        self.total_entries_scanned = 0
        self.token_types: Dict[str, int] = defaultdict(int)

    def process_entry(self, entry: Dict) -> List[ExtractedToken]:
        """Process a single HAR entry and extract all tokens"""
        self.total_entries_scanned += 1
        extracted_tokens = []

        request = entry.get('request', {})
        response = entry.get('response', {})

        # Extract from request headers
        headers = request.get('headers', {})
        if headers:
            tokens = self._extract_from_headers(headers, entry)
            extracted_tokens.extend(tokens)

        # Extract from request cookies
        cookie_header = headers.get('cookie', '')
        if cookie_header:
            cookies = self._parse_cookie_header(cookie_header)
            tokens = self._extract_from_cookies(cookies, entry)
            extracted_tokens.extend(tokens)

        # Extract from request URL
        url = request.get('url', '')
        if url:
            tokens = self._extract_from_url(url, entry)
            extracted_tokens.extend(tokens)

        # Extract from request body
        if self.extract_from_body:
            post_data = request.get('postData', {})
            if post_data:
                body = post_data.get('text', '') or post_data.get('params', {})
                tokens = self._extract_from_body(body, entry, is_request=True)
                extracted_tokens.extend(tokens)

        # Extract from response body
        if self.extract_from_response:
            response_body = response.get('content', {}).get('text', '')
            if response_body and len(response_body) < self.max_body_size:
                tokens = self._extract_from_body(response_body, entry, is_request=False)
                extracted_tokens.extend(tokens)

        for token in extracted_tokens:
            self.tokens_found.append(token)
            self.token_types[token.token_type] += 1

        return extracted_tokens

    def _extract_from_headers(self, headers: Dict[str, str], entry: Dict) -> List[ExtractedToken]:
        """Extract tokens from HTTP headers"""
        tokens = []
        headers_lower = {k.lower(): v for k, v in headers.items()}

        for header_name in self.AUTH_HEADERS:
            if header_name in headers_lower:
                value = headers_lower[header_name]
                extracted = self._extract_token_from_value(value, 'header', header_name, entry)
                if extracted:
                    tokens.extend(extracted)

        for name, value in headers_lower.items():
            if name not in self.AUTH_HEADERS and len(value) > self.min_token_length:
                if self._is_likely_token(value):
                    extracted = self._extract_token_from_value(value, 'header', name, entry)
                    if extracted:
                        tokens.extend(extracted)

        return tokens

    def _extract_from_cookies(self, cookies: Dict[str, str], entry: Dict) -> List[ExtractedToken]:
        """Extract tokens from cookies"""
        tokens = []

        for name, value in cookies.items():
            name_lower = name.lower()
            is_token_cookie = any(token_name in name_lower for token_name in self.TOKEN_COOKIE_NAMES)

            if is_token_cookie or self._is_likely_token(value):
                token_type = self._identify_token_type(value)
                if token_type:
                    tokens.append(ExtractedToken(
                        token_type=token_type,
                        token_value=value,
                        source='cookie',
                        location=name,
                        url=entry.get('request', {}).get('url', ''),
                        timestamp=entry.get('startedDateTime', datetime.now().isoformat()),
                        method=entry.get('request', {}).get('method', ''),
                        status_code=entry.get('response', {}).get('status', 0),
                        confidence=self._calculate_confidence(value, token_type),
                        metadata={'cookie': name}
                    ))

        return tokens

    def _extract_from_body(self, body: Any, entry: Dict, is_request: bool = True) -> List[ExtractedToken]:
        """Extract tokens from request/response body"""
        tokens = []
        source = 'request_body' if is_request else 'response_body'

        if not body:
            return tokens

        body_dict = None
        if isinstance(body, dict):
            body_dict = body
        elif isinstance(body, str):
            try:
                body_dict = json.loads(body)
            except:
                try:
                    parsed = urllib.parse.parse_qs(body)
                    if parsed:
                        body_dict = {k: v[0] if len(v) == 1 else v for k, v in parsed.items()}
                except:
                    pass

        if body_dict and isinstance(body_dict, dict):
            tokens.extend(self._search_dict_for_tokens(body_dict, entry, source, is_request))

        if isinstance(body, str) and self._contains_token_pattern(body):
            extracted = self._extract_tokens_from_text(body, entry, source, is_request)
            tokens.extend(extracted)

        return tokens

    def _extract_from_url(self, url: str, entry: Dict) -> List[ExtractedToken]:
        """Extract tokens from URL parameters"""
        tokens = []
        
        try:
            parsed = urllib.parse.urlparse(url)
            query_params = urllib.parse.parse_qs(parsed.query)
            
            token_param_names = [
                'token', 'access_token', 'auth', 'api_key', 'apikey',
                'jwt', 'bearer', 'oauth_token', 'session_token'
            ]
            
            for param_name, values in query_params.items():
                param_lower = param_name.lower()
                if param_lower in token_param_names or self._is_likely_token(values[0]):
                    value = values[0] if values else ''
                    if self._is_likely_token(value):
                        token_type = self._identify_token_type(value)
                        if token_type:
                            tokens.append(ExtractedToken(
                                token_type=token_type,
                                token_value=value,
                                source='url',
                                location=param_name,
                                url=url,
                                timestamp=entry.get('startedDateTime', datetime.now().isoformat()),
                                method=entry.get('request', {}).get('method', ''),
                                status_code=entry.get('response', {}).get('status', 0),
                                confidence=0.7,
                                metadata={'url_param': param_name}
                            ))
        except:
            pass

        return tokens

    def _extract_token_from_value(self, value: str, source: str, location: str, entry: Dict) -> List[ExtractedToken]:
        """Extract token from a header value"""
        tokens = []
        
        bearer_match = self.BEARER_PATTERN.match(value)
        if bearer_match:
            token_value = bearer_match.group(1).strip()
            if self._is_likely_token(token_value):
                token_type = self._identify_token_type(token_value)
                tokens.append(ExtractedToken(
                    token_type=token_type or 'Bearer',
                    token_value=token_value,
                    source=source,
                    location=location,
                    url=entry.get('request', {}).get('url', ''),
                    timestamp=entry.get('startedDateTime', datetime.now().isoformat()),
                    method=entry.get('request', {}).get('method', ''),
                    status_code=entry.get('response', {}).get('status', 0),
                    confidence=0.95 if token_type else 0.8
                ))
                return tokens

        basic_match = self.BASIC_PATTERN.match(value)
        if basic_match:
            try:
                decoded = base64.b64decode(basic_match.group(1)).decode('utf-8')
                if ':' in decoded:
                    username, password = decoded.split(':', 1)
                    tokens.append(ExtractedToken(
                        token_type='Basic',
                        token_value=password,
                        source=source,
                        location=location,
                        url=entry.get('request', {}).get('url', ''),
                        timestamp=entry.get('startedDateTime', datetime.now().isoformat()),
                        method=entry.get('request', {}).get('method', ''),
                        status_code=entry.get('response', {}).get('status', 0),
                        confidence=1.0,
                        metadata={'username': username}
                    ))
                    return tokens
            except:
                pass

        if self._is_likely_token(value):
            token_type = self._identify_token_type(value)
            tokens.append(ExtractedToken(
                token_type=token_type or 'Unknown',
                token_value=value,
                source=source,
                location=location,
                url=entry.get('request', {}).get('url', ''),
                timestamp=entry.get('startedDateTime', datetime.now().isoformat()),
                method=entry.get('request', {}).get('method', ''),
                status_code=entry.get('response', {}).get('status', 0),
                confidence=self._calculate_confidence(value, token_type)
            ))

        return tokens

    def _search_dict_for_tokens(self, data: Any, entry: Dict, source: str, is_request: bool) -> List[ExtractedToken]:
        """Recursively search dict for token values"""
        tokens = []
        
        if isinstance(data, dict):
            for key, value in data.items():
                key_lower = key.lower()
                is_token_field = any(token_field in key_lower for token_field in self.TOKEN_RESPONSE_FIELDS)

                if is_token_field and isinstance(value, str) and self._is_likely_token(value):
                    token_type = self._identify_token_type(value)
                    tokens.append(ExtractedToken(
                        token_type=token_type or 'Unknown',
                        token_value=value,
                        source=source,
                        location=key,
                        url=entry.get('request', {}).get('url', ''),
                        timestamp=entry.get('startedDateTime', datetime.now().isoformat()),
                        method=entry.get('request', {}).get('method', ''),
                        status_code=entry.get('response', {}).get('status', 0),
                        confidence=self._calculate_confidence(value, token_type),
                        metadata={'field': key}
                    ))
                elif isinstance(value, (dict, list)):
                    tokens.extend(self._search_dict_for_tokens(value, entry, source, is_request))
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, (dict, list)):
                    tokens.extend(self._search_dict_for_tokens(item, entry, source, is_request))
                elif isinstance(item, str) and self._is_likely_token(item):
                    token_type = self._identify_token_type(item)
                    tokens.append(ExtractedToken(
                        token_type=token_type or 'Unknown',
                        token_value=item,
                        source=source,
                        location='array_item',
                        url=entry.get('request', {}).get('url', ''),
                        timestamp=entry.get('startedDateTime', datetime.now().isoformat()),
                        method=entry.get('request', {}).get('method', ''),
                        status_code=entry.get('response', {}).get('status', 0),
                        confidence=self._calculate_confidence(item, token_type)
                    ))

        return tokens

    def _extract_tokens_from_text(self, text: str, entry: Dict, source: str, is_request: bool) -> List[ExtractedToken]:
        """Extract tokens from raw text using regex patterns"""
        tokens = []
        
        jwt_matches = self.JWT_PATTERN.findall(text)
        for match in jwt_matches:
            if len(match) > self.min_token_length:
                tokens.append(ExtractedToken(
                    token_type='JWT',
                    token_value=match,
                    source=source,
                    location='text_match',
                    url=entry.get('request', {}).get('url', ''),
                    timestamp=entry.get('startedDateTime', datetime.now().isoformat()),
                    method=entry.get('request', {}).get('method', ''),
                    status_code=entry.get('response', {}).get('status', 0),
                    confidence=0.9,
                    metadata={'pattern': 'jwt'}
                ))

        return tokens

    def _is_likely_token(self, value: str) -> bool:
        """Determine if a value is likely to be a token"""
        if not value or not isinstance(value, str):
            return False
        
        if len(value) < self.min_token_length or len(value) > self.max_token_length:
            return False
        
        if self.JWT_PATTERN.match(value):
            return True
        
        for pattern in self.API_KEY_PATTERNS:
            if pattern.match(value):
                return True
        
        if self.UUID_PATTERN.match(value):
            return True
        
        if re.match(r'^[A-Fa-f0-9]{32,128}$', value):
            return True
        
        if re.match(r'^[A-Za-z0-9+/=]{32,128}$', value) and len(value) % 4 == 0:
            return True
        
        if re.match(r'^[A-Za-z0-9_-]{16,}$', value):
            entropy = self._calculate_entropy(value)
            if entropy > 3.5:
                return True
        
        return False

    def _identify_token_type(self, value: str) -> Optional[str]:
        """Identify the type of token"""
        if self.JWT_PATTERN.match(value):
            return 'JWT'
        
        if re.match(r'^sk-[A-Za-z0-9]{32,64}$', value):
            return 'Secret_Key'
        
        if re.match(r'^pk_[A-Za-z0-9]{32,64}$', value):
            return 'Public_Key'
        
        if self.UUID_PATTERN.match(value):
            return 'UUID'
        
        if re.match(r'^[A-Fa-f0-9]{32}$', value):
            return 'Hex32'
        
        if re.match(r'^[A-Fa-f0-9]{64}$', value):
            return 'Hex64'
        
        if re.match(r'^[A-Za-z0-9+/=]{32,128}$', value) and len(value) % 4 == 0:
            return 'Base64'
        
        if re.match(r'^[A-Za-z0-9_-]{20,128}$', value):
            return 'Session_Token'
        
        return None

    def _calculate_confidence(self, value: str, token_type: Optional[str]) -> float:
        """Calculate confidence score for token detection"""
        confidence = 0.5
        
        if token_type == 'JWT':
            confidence = 0.95
        elif token_type in ['Secret_Key', 'API_Key']:
            confidence = 0.9
        elif token_type in ['Hex32', 'Hex64']:
            confidence = 0.85
        elif token_type == 'UUID':
            confidence = 0.8
        elif token_type == 'Base64':
            confidence = 0.7
        elif token_type == 'Session_Token':
            confidence = 0.75
        
        if len(value) > 40:
            confidence = min(1.0, confidence + 0.1)
        
        return confidence

    def _calculate_entropy(self, s: str) -> float:
        """Calculate Shannon entropy of a string"""
        if not s:
            return 0
        
        frequency = {}
        for char in s:
            frequency[char] = frequency.get(char, 0) + 1
        
        entropy = 0
        length = len(s)
        for count in frequency.values():
            probability = count / length
            entropy -= probability * (probability.bit_length() if probability > 0 else 0)
        
        return entropy

    def _contains_token_pattern(self, text: str) -> bool:
        """Check if text contains token patterns"""
        if not text:
            return False
        
        if self.JWT_PATTERN.search(text):
            return True
        
        if re.search(r'[A-Fa-f0-9]{32,128}', text):
            return True
        
        if re.search(r'[A-Za-z0-9+/=]{32,128}', text):
            return True
        
        return False

    def _parse_cookie_header(self, cookie_header: str) -> Dict[str, str]:
        """Parse Cookie header into dict"""
        cookies = {}
        for cookie in cookie_header.split(';'):
            cookie = cookie.strip()
            if '=' in cookie:
                name, value = cookie.split('=', 1)
                cookies[name.strip()] = value.strip()
        return cookies

    def get_statistics(self) -> Dict:
        """Get token extraction statistics"""
        return {
            'total_entries_scanned': self.total_entries_scanned,
            'total_tokens_found': len(self.tokens_found),
            'token_types': dict(self.token_types),
            'unique_tokens': len(set(t.hashed_value for t in self.tokens_found)),
            'by_source': dict(Counter(t.source for t in self.tokens_found)),
            'by_type': dict(self.token_types)
        }

    def get_unique_tokens(self) -> List[ExtractedToken]:
        """Get unique tokens (by hash)"""
        seen = set()
        unique = []
        for token in self.tokens_found:
            if token.hashed_value not in seen:
                seen.add(token.hashed_value)
                unique.append(token)
        return unique


# ============================================================================
# PAYLOAD EXTRACTOR
# ============================================================================

@dataclass
class ExtractedPayload:
    """Represents an extracted payload"""
    payload_type: str
    content: Any
    raw_content: str
    url: str
    method: str
    status_code: int
    timestamp: str
    direction: str
    content_type: str
    size_bytes: int
    fields: Dict[str, Any] = field(default_factory=dict)
    sensitive_fields: List[str] = field(default_factory=list)
    structures: List[str] = field(default_factory=list)


class PayloadExtractor:
    """Extracts and analyzes payloads from HAR entries"""
    
    SENSITIVE_FIELD_PATTERNS = [
        r'password', r'passwd', r'pwd', r'secret', r'token', r'auth',
        r'authorization', r'api[_-]?key', r'apikey', r'credential',
        r'credit[_-]?card', r'cc[_-]?number', r'ssn', r'social[_-]?security',
        r'phone', r'email', r'address', r'birth', r'age', r'gender'
    ]

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.max_payload_size = self.config.get('max_payload_size', 5 * 1024 * 1024)
        self.truncate_size = self.config.get('truncate_size', 1024 * 1024)
        
        self.sensitive_patterns = [re.compile(p, re.IGNORECASE) for p in self.SENSITIVE_FIELD_PATTERNS]
        self.payloads: List[ExtractedPayload] = []
        self.total_size = 0

    def process_entry(self, entry: Dict) -> List[ExtractedPayload]:
        """Process a single HAR entry and extract payloads"""
        payloads = []
        request = entry.get('request', {})
        response = entry.get('response', {})

        # Process request payload
        post_data = request.get('postData', {})
        if post_data:
            payload = self._extract_post_data(post_data, entry, 'request')
            if payload:
                payloads.append(payload)

        # Process response payload
        content = response.get('content', {})
        if content and content.get('size', 0) > 0:
            payload = self._extract_response_content(content, entry, 'response')
            if payload:
                payloads.append(payload)

        self.payloads.extend(payloads)
        for p in payloads:
            self.total_size += p.size_bytes

        return payloads

    def _extract_post_data(self, post_data: Dict, entry: Dict, direction: str) -> Optional[ExtractedPayload]:
        """Extract payload from post data"""
        mime_type = post_data.get('mimeType', 'application/octet-stream')
        text = post_data.get('text', '')
        params = post_data.get('params', [])

        if not text and not params:
            return None

        if 'application/json' in mime_type or self._looks_like_json(text):
            return self._extract_json(text, entry, direction, mime_type)
        
        if 'application/x-www-form-urlencoded' in mime_type:
            return self._extract_form_data(text or params, entry, direction, mime_type)
        
        if text and len(text) < self.max_payload_size:
            return self._extract_text(text, entry, direction, mime_type)

        return None

    def _extract_response_content(self, content: Dict, entry: Dict, direction: str) -> Optional[ExtractedPayload]:
        """Extract payload from response content"""
        mime_type = content.get('mimeType', 'application/octet-stream')
        text = content.get('text', '')
        size = content.get('size', 0)

        if not text and size == 0:
            return None

        if 'application/json' in mime_type or self._looks_like_json(text):
            return self._extract_json(text, entry, direction, mime_type)
        
        if 'text/html' in mime_type:
            return self._extract_html(text, entry, direction, mime_type)
        
        if text and len(text) < self.max_payload_size:
            return self._extract_text(text, entry, direction, mime_type)

        return None

    def _extract_json(self, text: str, entry: Dict, direction: str, content_type: str) -> Optional[ExtractedPayload]:
        """Extract JSON payload"""
        try:
            data = json.loads(text) if text else {}
        except:
            return None

        fields = self._flatten_json(data)
        sensitive = self._find_sensitive_fields(fields)
        structures = self._identify_structures(data)

        return ExtractedPayload(
            payload_type='JSON',
            content=data,
            raw_content=text[:self.truncate_size],
            url=entry.get('request', {}).get('url', ''),
            method=entry.get('request', {}).get('method', ''),
            status_code=entry.get('response', {}).get('status', 0),
            timestamp=entry.get('startedDateTime', datetime.now().isoformat()),
            direction=direction,
            content_type=content_type,
            size_bytes=len(text),
            fields=fields,
            sensitive_fields=sensitive,
            structures=structures
        )

    def _extract_form_data(self, data: Any, entry: Dict, direction: str, content_type: str) -> Optional[ExtractedPayload]:
        """Extract form data payload"""
        fields = {}
        
        if isinstance(data, str):
            try:
                parsed = urllib.parse.parse_qs(data)
                fields = {k: v[0] if len(v) == 1 else v for k, v in parsed.items()}
            except:
                fields = {'raw': data}
        elif isinstance(data, list):
            for param in data:
                if isinstance(param, dict):
                    name = param.get('name', '')
                    value = param.get('value', '')
                    if name:
                        fields[name] = value

        sensitive = self._find_sensitive_fields(fields)

        return ExtractedPayload(
            payload_type='Form',
            content=fields,
            raw_content=str(fields)[:self.truncate_size],
            url=entry.get('request', {}).get('url', ''),
            method=entry.get('request', {}).get('method', ''),
            status_code=entry.get('response', {}).get('status', 0),
            timestamp=entry.get('startedDateTime', datetime.now().isoformat()),
            direction=direction,
            content_type=content_type,
            size_bytes=len(str(fields)),
            fields=fields,
            sensitive_fields=sensitive,
            structures=['Form_Data']
        )

    def _extract_html(self, text: str, entry: Dict, direction: str, content_type: str) -> Optional[ExtractedPayload]:
        """Extract HTML payload"""
        return ExtractedPayload(
            payload_type='HTML',
            content={'html': text[:self.truncate_size]},
            raw_content=text[:self.truncate_size],
            url=entry.get('request', {}).get('url', ''),
            method=entry.get('request', {}).get('method', ''),
            status_code=entry.get('response', {}).get('status', 0),
            timestamp=entry.get('startedDateTime', datetime.now().isoformat()),
            direction=direction,
            content_type=content_type,
            size_bytes=len(text),
            fields={'size': len(text)},
            sensitive_fields=[],
            structures=['HTML']
        )

    def _extract_text(self, text: str, entry: Dict, direction: str, content_type: str) -> Optional[ExtractedPayload]:
        """Extract plain text payload"""
        return ExtractedPayload(
            payload_type='Text',
            content=text[:self.truncate_size],
            raw_content=text[:self.truncate_size],
            url=entry.get('request', {}).get('url', ''),
            method=entry.get('request', {}).get('method', ''),
            status_code=entry.get('response', {}).get('status', 0),
            timestamp=entry.get('startedDateTime', datetime.now().isoformat()),
            direction=direction,
            content_type=content_type,
            size_bytes=len(text),
            fields={},
            sensitive_fields=[],
            structures=['Text']
        )

    def _flatten_json(self, data: Any, prefix: str = '') -> Dict[str, Any]:
        """Flatten JSON structure into dot notation"""
        fields = {}
        
        if isinstance(data, dict):
            for key, value in data.items():
                new_prefix = f"{prefix}.{key}" if prefix else key
                if isinstance(value, (dict, list)):
                    fields.update(self._flatten_json(value, new_prefix))
                else:
                    fields[new_prefix] = value
        elif isinstance(data, list):
            for i, item in enumerate(data):
                new_prefix = f"{prefix}[{i}]"
                if isinstance(item, (dict, list)):
                    fields.update(self._flatten_json(item, new_prefix))
                else:
                    fields[new_prefix] = item
        
        return fields

    def _find_sensitive_fields(self, fields: Dict[str, Any]) -> List[str]:
        """Find sensitive fields in payload"""
        sensitive = []
        for key in fields.keys():
            key_lower = key.lower()
            for pattern in self.sensitive_patterns:
                if pattern.search(key_lower):
                    sensitive.append(key)
                    break
        return sensitive

    def _identify_structures(self, data: Any) -> List[str]:
        """Identify data structures in JSON payload"""
        structures = []
        if not data:
            return structures

        if isinstance(data, dict):
            structures.append('JSON_Object')
            if 'data' in data and 'meta' in data:
                structures.append('REST_Response')
            if 'errors' in data:
                structures.append('Error_Response')
        elif isinstance(data, list):
            structures.append('JSON_Array')
            if data and isinstance(data[0], dict):
                structures.append('Collection')
        else:
            structures.append('JSON_Primitive')

        return structures

    def _looks_like_json(self, text: str) -> bool:
        """Check if text looks like JSON"""
        if not text:
            return False
        text = text.strip()
        return (text.startswith('{') and text.endswith('}')) or \
               (text.startswith('[') and text.endswith(']'))

    def get_statistics(self) -> Dict:
        """Get payload extraction statistics"""
        types = Counter(p.payload_type for p in self.payloads)
        directions = Counter(p.direction for p in self.payloads)
        
        return {
            'total_payloads': len(self.payloads),
            'total_size_bytes': self.total_size,
            'by_type': dict(types),
            'by_direction': dict(directions),
            'payloads_with_sensitive': len([p for p in self.payloads if p.sensitive_fields])
        }


# ============================================================================
# WEB SOCKET CAPTURE ENGINE
# ============================================================================

class WebSocketCaptureEngine:
    """Capture network traffic via Chrome DevTools WebSocket"""
    
    def __init__(self, ws_url: str, tab_info: Dict):
        self.ws_url = ws_url
        self.tab_info = tab_info
        self.entries: List[Dict] = []
        self.request_map: Dict[str, Dict] = {}
        self.is_running = False
        self.stop_event = threading.Event()
        self.websocket: Optional[websocket.WebSocket] = None
        self.entry_counter = 0
        self.lock = threading.Lock()
        self.start_time = None
        self.end_time = None
        
        # Extractors
        self.token_extractor = TokenExtractor()
        self.payload_extractor = PayloadExtractor()
        self.analyzed_tokens: List[ExtractedToken] = []
        self.analyzed_payloads: List[ExtractedPayload] = []

    def connect(self) -> bool:
        """Connect to Chrome WebSocket"""
        try:
            logger.info(f"📡 Connecting to WebSocket: {self.ws_url[:50]}...")
            self.websocket = websocket.create_connection(
                self.ws_url,
                timeout=10,
                enable_multithread=True
            )
            
            # Enable Network monitoring
            self.websocket.send(json.dumps({"id": 1, "method": "Network.enable"}))
            self.websocket.send(json.dumps({"id": 2, "method": "Page.enable"}))
            
            logger.info("✅ Connected to Chrome DevTools")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to connect: {e}")
            return False

    def capture(self, duration: int = 30) -> List[Dict]:
        """Capture network traffic for specified duration"""
        if not self.connect():
            return []
        
        self.is_running = True
        self.start_time = time.time()
        
        logger.info(f"🎯 Capturing network traffic for {duration} seconds...")
        logger.info("   Interact with the page during capture")
        logger.info("   Press Ctrl+C to stop early\n")
        
        request_count = 0
        response_count = 0
        
        try:
            while not self.stop_event.is_set() and (time.time() - self.start_time) < duration:
                try:
                    self.websocket.settimeout(0.5)
                    msg = self.websocket.recv()
                    
                    if not msg:
                        continue
                    
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
                                'content': {'mimeType': '', 'size': 0}
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
                            'request_time': time.time(),
                            'request_id': request_id,
                            'entry_number': self.entry_counter,
                            'tab_info': self.tab_info
                        }
                        
                        with self.lock:
                            self.entry_counter += 1
                            self.request_map[request_id] = entry
                            request_count += 1
                            
                    elif method == 'Network.responseReceived':
                        request_id = params.get('requestId')
                        if request_id in self.request_map:
                            response = params.get('response', {})
                            entry = self.request_map[request_id]
                            entry['response']['status'] = response.get('status', 0)
                            entry['response']['statusText'] = response.get('statusText', '')
                            entry['response']['headers'] = response.get('headers', {})
                            entry['response']['content']['mimeType'] = response.get('mimeType', '')
                            entry['response']['content']['size'] = response.get('contentSize', 0)
                            entry['response_time'] = time.time()
                            
                            if 'request_time' in entry:
                                entry['time'] = (entry['response_time'] - entry['request_time']) * 1000
                            
                            # Add to entries
                            with self.lock:
                                self.entries.append(entry)
                                response_count += 1
                                del self.request_map[request_id]
                            
                            # Analyze entry
                            self._analyze_entry(entry)
                            
                            # Show progress
                            if response_count % 5 == 0:
                                print(f"   📊 Captured {response_count} responses...", end='\r')
                                
                    elif method == 'Page.frameNavigated':
                        frame = params.get('frame', {})
                        logger.info(f"🔄 Navigated to: {frame.get('url', '')[:60]}")
                        
                except websocket.WebSocketTimeoutException:
                    continue
                except websocket.WebSocketConnectionClosedException:
                    logger.warning("⚠️ WebSocket connection closed")
                    break
                except json.JSONDecodeError:
                    continue
                except Exception as e:
                    logger.error(f"Error in capture loop: {e}")
                    continue
                    
        except KeyboardInterrupt:
            logger.info("\n⏹️ Stopped by user")
        
        self.is_running = False
        self.end_time = time.time()
        
        # Close connection
        if self.websocket:
            try:
                self.websocket.close()
            except:
                pass
        
        logger.info(f"\n✅ Capture complete!")
        logger.info(f"   Requests: {request_count}")
        logger.info(f"   Responses captured: {response_count}")
        logger.info(f"   Entries saved: {len(self.entries)}")
        
        return self.entries

    def _analyze_entry(self, entry: Dict):
        """Analyze a captured entry for tokens and payloads"""
        try:
            # Extract tokens
            tokens = self.token_extractor.process_entry(entry)
            self.analyzed_tokens.extend(tokens)
            
            # Extract payloads
            payloads = self.payload_extractor.process_entry(entry)
            self.analyzed_payloads.extend(payloads)
        except Exception as e:
            logger.debug(f"Analysis error: {e}")

    def stop(self):
        """Stop capture"""
        self.stop_event.set()

    def get_statistics(self) -> Dict:
        """Get capture statistics"""
        duration = 0
        if self.start_time and self.end_time:
            duration = self.end_time - self.start_time
        
        return {
            'duration_seconds': duration,
            'total_entries': len(self.entries),
            'status_codes': dict(Counter(e.get('response', {}).get('status', 0) for e in self.entries)),
            'unique_urls': len(set(e.get('request', {}).get('url', '') for e in self.entries)),
            'token_statistics': self.token_extractor.get_statistics(),
            'payload_statistics': self.payload_extractor.get_statistics(),
            'total_tokens': len(self.analyzed_tokens),
            'total_payloads': len(self.analyzed_payloads)
        }

    def save_har(self, output_file: str = None) -> str:
        """Save captured data as HAR file"""
        if not output_file:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = f"har_capture_{timestamp}.har"
        
        # Build HAR structure
        har_data = {
            'log': {
                'version': '1.2',
                'creator': {
                    'name': 'Enhanced HAR Capture',
                    'version': '2.0.0'
                },
                'browser': {
                    'name': 'Chrome',
                    'version': 'Auto-detected'
                },
                'entries': self.entries,
                'pages': [],
                'comment': {
                    'tab_info': self.tab_info,
                    'capture_start': datetime.fromtimestamp(self.start_time).isoformat() if self.start_time else None,
                    'capture_end': datetime.fromtimestamp(self.end_time).isoformat() if self.end_time else None,
                    'total_entries': len(self.entries),
                    'analyzed_tokens': len(self.analyzed_tokens),
                    'analyzed_payloads': len(self.analyzed_payloads)
                }
            }
        }
        
        with open(output_file, 'w') as f:
            json.dump(har_data, f, indent=2)
        
        file_size = os.path.getsize(output_file)
        logger.info(f"💾 Saved HAR to: {output_file}")
        logger.info(f"📊 File size: {file_size / 1024:.2f} KB")
        
        return output_file

    def save_analysis(self, output_file: str = None) -> str:
        """Save analysis results"""
        if not output_file:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = f"analysis_{timestamp}.json"
        
        # Prepare token data
        tokens_data = []
        for token in self.analyzed_tokens[:100]:
            tokens_data.append({
                'type': token.token_type,
                'source': token.source,
                'location': token.location,
                'url': token.url[:100],
                'masked_value': token.mask(),
                'confidence': token.confidence,
                'timestamp': token.timestamp
            })
        
        # Prepare payload data
        payloads_data = []
        for payload in self.analyzed_payloads[:100]:
            payloads_data.append({
                'type': payload.payload_type,
                'url': payload.url[:100],
                'method': payload.method,
                'size': payload.size_bytes,
                'direction': payload.direction,
                'has_sensitive': bool(payload.sensitive_fields),
                'fields_count': len(payload.fields)
            })
        
        analysis = {
            'summary': {
                'total_entries': len(self.entries),
                'total_tokens': len(self.analyzed_tokens),
                'total_payloads': len(self.analyzed_payloads),
                'unique_tokens': len(self.token_extractor.get_unique_tokens()),
                'unique_urls': len(set(e.get('request', {}).get('url', '') for e in self.entries))
            },
            'token_statistics': self.token_extractor.get_statistics(),
            'payload_statistics': self.payload_extractor.get_statistics(),
            'tokens': tokens_data,
            'payloads': payloads_data,
            'timestamp': datetime.now().isoformat()
        }
        
        with open(output_file, 'w') as f:
            json.dump(analysis, f, indent=2)
        
        logger.info(f"📊 Analysis saved to: {output_file}")
        return output_file

    def print_summary(self):
        """Print a summary of captured data"""
        stats = self.get_statistics()
        
        print("\n" + "="*60)
        print("📊 CAPTURE SUMMARY")
        print("="*60)
        print(f"   Duration: {stats['duration_seconds']:.1f} seconds")
        print(f"   Total entries: {stats['total_entries']}")
        print(f"   Unique URLs: {stats['unique_urls']}")
        print(f"   Tokens found: {stats['total_tokens']}")
        print(f"   Payloads found: {stats['total_payloads']}")
        
        if stats.get('status_codes'):
            print("\n   📈 Status Codes:")
            for code, count in sorted(stats['status_codes'].items()):
                emoji = "✅" if 200 <= code < 300 else "⚠️" if 300 <= code < 400 else "❌"
                print(f"     {emoji} {code}: {count}")
        
        token_stats = stats.get('token_statistics', {})
        if token_stats.get('token_types'):
            print("\n   🔑 Token Types:")
            for token_type, count in token_stats['token_types'].items():
                print(f"     • {token_type}: {count}")
        
        payload_stats = stats.get('payload_statistics', {})
        if payload_stats.get('by_type'):
            print("\n   📦 Payload Types:")
            for ptype, count in payload_stats['by_type'].items():
                print(f"     • {ptype}: {count}")
        
        print("="*60)


# ============================================================================
# MAIN APPLICATION
# ============================================================================

def select_debugging_port() -> int:
    """Interactively select a Chrome debugging port"""
    print("\n🔍 Scanning for Chrome debugging ports...")
    
    # Find running Chrome processes
    chrome_processes = ChromeDiscovery.find_chrome_processes()
    debugging_processes = [p for p in chrome_processes if p.get('is_debugging')]
    
    if debugging_processes:
        print("\n📋 Found Chrome processes with debugging enabled:")
        for i, proc in enumerate(debugging_processes, 1):
            print(f"  {i}. PID: {proc['pid']} | Port: {proc['port']} | {proc['name']}")
        
        available_ports = []
        for proc in debugging_processes:
            port = proc['port']
            if ChromeDiscovery.check_port(port):
                available_ports.append(port)
                print(f"     ✅ Port {port} is accessible")
            else:
                print(f"     ❌ Port {port} is not accessible")
        
        if available_ports:
            choice = input(f"\nSelect port [{available_ports[0]}]: ").strip()
            if choice:
                try:
                    return int(choice)
                except ValueError:
                    print(f"⚠️ Invalid input, using {available_ports[0]}")
                    return available_ports[0]
            return available_ports[0]
    
    # Scan common ports
    print("\n🔍 Scanning common ports...")
    available_ports = ChromeDiscovery.scan_ports()
    
    if available_ports:
        print(f"\n✅ Found Chrome on port(s): {available_ports}")
        if len(available_ports) == 1:
            return available_ports[0]
        
        for i, port in enumerate(available_ports, 1):
            print(f"  {i}. Port {port}")
        choice = input(f"\nSelect port [1]: ").strip()
        try:
            idx = int(choice) - 1 if choice else 0
            return available_ports[idx]
        except (ValueError, IndexError):
            return available_ports[0]
    
    # No Chrome found, offer to start one
    print("\n❌ No Chrome debugging ports found.")
    response = input("Would you like to start Chrome with debugging enabled? (y/n): ").strip().lower()
    
    if response == 'y':
        port = input("Enter port [9222]: ").strip()
        port = int(port) if port else 9222
        
        process = ChromeDiscovery.start_chrome_with_debugging(port)
        if process:
            print(f"✅ Chrome started on port {port}")
            return port
        else:
            print("❌ Failed to start Chrome")
            sys.exit(1)
    else:
        print("❌ No Chrome debugging port available")
        sys.exit(1)


def main():
    """Main entry point"""
    print("╔" + "="*60 + "╗")
    print("║" + " "*8 + "🚀 COMPLETE HAR CAPTURE & ANALYSIS" + " "*9 + "║")
    print("║" + " "*6 + "Dynamic Port | Token Extraction | Payload Analysis" + " "*4 + "║")
    print("╚" + "="*60 + "╝")
    print()

    # If HAR file provided as argument, analyze it
    if len(sys.argv) > 1:
        har_file = sys.argv[1]
        try:
            with open(har_file, 'r') as f:
                har_data = json.load(f)
            
            entries = har_data.get('log', {}).get('entries', [])
            print(f"📊 Analyzing HAR file: {har_file}")
            print(f"   Entries found: {len(entries)}")
            
            # Create a temporary engine for analysis
            token_extractor = TokenExtractor()
            payload_extractor = PayloadExtractor()
            
            for entry in entries:
                token_extractor.process_entry(entry)
                payload_extractor.process_entry(entry)
            
            print(f"\n🔑 Tokens found: {len(token_extractor.tokens_found)}")
            print(f"📦 Payloads found: {len(payload_extractor.payloads)}")
            
            # Show token types
            if token_extractor.token_types:
                print("\n📊 Token Types:")
                for token_type, count in token_extractor.token_types.items():
                    print(f"   {token_type}: {count}")
            
            return
        except Exception as e:
            logger.error(f"Error analyzing HAR file: {e}")
            sys.exit(1)
    
    # Interactive mode - capture
    try:
        # Select port
        port = select_debugging_port()
        print(f"\n🔌 Using Chrome debugging port: {port}")
        
        # Get available tabs
        tabs = ChromeDiscovery.get_tabs(port)
        page_tabs = [t for t in tabs if t.get('type') == 'page']
        
        if not page_tabs:
            print("❌ No page tabs found. Please open a tab first.")
            return
        
        print(f"\n📑 Available tabs on port {port}:")
        for i, tab in enumerate(page_tabs, 1):
            title = tab.get('title', 'Untitled')[:50]
            url = tab.get('url', '')[:60]
            print(f"  {i}. {title}")
            print(f"     {url}")
        
        # Select tab
        choice = input(f"\nSelect tab [1]: ").strip()
        try:
            idx = int(choice) - 1 if choice else 0
            selected_tab = page_tabs[idx]
        except (ValueError, IndexError):
            selected_tab = page_tabs[0]
        
        ws_url = selected_tab.get('webSocketDebuggerUrl')
        if not ws_url:
            print("❌ No WebSocket URL found for this tab")
            return
        
        tab_info = {
            'id': selected_tab.get('id'),
            'title': selected_tab.get('title'),
            'url': selected_tab.get('url')
        }
        
        print(f"\n✅ Selected: {tab_info['title'][:50]}")
        print(f"   URL: {tab_info['url']}")
        
        # Capture settings
        duration = input("\nCapture duration (seconds) [30]: ").strip()
        duration = int(duration) if duration else 30
        
        print("\n" + "="*60)
        print("🎯 Starting capture...")
        print(f"   Tab: {tab_info['title'][:50]}")
        print(f"   Duration: {duration} seconds")
        print("="*60)
        
        # Create capture engine and run
        engine = WebSocketCaptureEngine(ws_url, tab_info)
        
        try:
            # Run capture
            entries = engine.capture(duration)
            
            if entries:
                # Save results
                har_file = engine.save_har()
                analysis_file = engine.save_analysis()
                
                # Print summary
                engine.print_summary()
                
                print(f"\n💾 Files saved:")
                print(f"   HAR: {har_file}")
                print(f"   Analysis: {analysis_file}")
            else:
                print("⚠️ No entries captured")
                
        except KeyboardInterrupt:
            print("\n⏹️ Stopped by user")
            engine.stop()
            
            if engine.entries:
                har_file = engine.save_har()
                analysis_file = engine.save_analysis()
                print(f"\n💾 Saved {len(engine.entries)} entries to {har_file}")
        
    except KeyboardInterrupt:
        print("\n\n⏹️ Interrupted by user")
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        logger.debug(traceback.format_exc())


if __name__ == "__main__":
    main()
