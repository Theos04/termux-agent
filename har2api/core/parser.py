"""
HAR file parser with validation and normalization - Self-contained
Enhanced with token extraction and session analysis
"""

import json
import re
from typing import List, Optional, Dict, Any, Union
from urllib.parse import urlparse, parse_qs, unquote
from datetime import datetime
import os
import logging
from collections import defaultdict, Counter
from dataclasses import dataclass, field
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Simple dataclasses for models
@dataclass
class RequestHeader:
    name: str
    value: str
    is_sensitive: bool = False

@dataclass
class ResponseModel:
    status: int
    status_text: str = ""
    headers: List[RequestHeader] = field(default_factory=list)
    body: str = ""
    body_size: int = 0
    mime_type: str = ""
    redirect_url: str = ""

@dataclass
class RequestModel:
    method: str
    url: str
    path: str
    query_params: Dict[str, List[str]]
    headers: List[RequestHeader]
    body: Optional[str]
    body_type: str
    timestamp: Optional[datetime] = None
    request_id: Optional[str] = None
    response: Optional[ResponseModel] = None
    size: int = 0
    timings: Dict[str, float] = field(default_factory=dict)

@dataclass
class EndpointModel:
    path: str
    method: str
    description: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)
    responses: Dict[str, Any] = field(default_factory=dict)
    request_body: Optional[Dict[str, Any]] = None
    examples: List[Dict[str, Any]] = field(default_factory=list)
    count: int = 0

@dataclass
class AuthConfig:
    type: str = "none"
    header_name: str = ""
    header_value: str = ""
    token_location: str = ""
    requires_auth: bool = False
    token_type: str = ""
    cookie_name: str = ""

@dataclass
class APISpec:
    base_url: str
    endpoints: List[EndpointModel]
    authentication: AuthConfig
    common_headers: Dict[str, str]
    source_files: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

class HARParseError(Exception):
    pass

class EndpointClassifier:
    """Simple endpoint classifier"""

    def classify_endpoints(self, requests: List[RequestModel]) -> List[EndpointModel]:
        """Group requests into endpoints"""
        endpoint_map = {}

        for req in requests:
            # Create a key from path and method
            key = f"{req.method}:{req.path}"

            if key not in endpoint_map:
                endpoint_map[key] = EndpointModel(
                    path=req.path,
                    method=req.method,
                    count=0,
                    parameters={},
                    responses={},
                    examples=[]
                )

            endpoint = endpoint_map[key]
            endpoint.count += 1

            # Add example
            example = {
                'url': req.url,
                'method': req.method,
                'timestamp': req.timestamp.isoformat() if req.timestamp else None,
                'headers': {h.name: h.value for h in req.headers if not h.is_sensitive},
                'query_params': req.query_params
            }
            if req.body:
                example['body'] = req.body[:500]  # Truncate long bodies

            endpoint.examples.append(example)

            # Extract parameters from path
            path_parts = req.path.split('/')
            for part in path_parts:
                if part.startswith('{') and part.endswith('}'):
                    param_name = part[1:-1]
                    endpoint.parameters[param_name] = {'in': 'path', 'required': True}

            # Extract query parameters
            for param_name, values in req.query_params.items():
                if param_name not in endpoint.parameters:
                    endpoint.parameters[param_name] = {'in': 'query', 'required': False}

            # Capture response info
            if req.response:
                status_key = str(req.response.status)
                if status_key not in endpoint.responses:
                    endpoint.responses[status_key] = {
                        'description': req.response.status_text or f"Status {req.response.status}",
                        'examples': []
                    }
                endpoint.responses[status_key]['examples'].append({
                    'body': req.response.body[:500] if req.response.body else None,
                    'headers': {h.name: h.value for h in req.response.headers}
                })

        return list(endpoint_map.values())

class AuthDetector:
    """Simple auth detector with enhanced token detection"""

    def detect_auth(self, requests: List[RequestModel]) -> AuthConfig:
        """Detect authentication from requests with enhanced token extraction"""
        if not requests:
            return AuthConfig()

        auth_headers = {}
        auth_types = Counter()
        token_extracts = []

        for req in requests:
            for header in req.headers:
                name_lower = header.name.lower()
                value = header.value

                if 'authorization' in name_lower:
                    if value.lower().startswith('bearer '):
                        auth_types['bearer'] += 1
                        token = value[7:]
                        token_extracts.append({
                            'type': 'bearer',
                            'header': name_lower,
                            'token': token[:20] + '...' if len(token) > 20 else token
                        })
                    elif value.lower().startswith('basic '):
                        auth_types['basic'] += 1
                        token_extracts.append({
                            'type': 'basic',
                            'header': name_lower,
                            'token': value[:20] + '...' if len(value) > 20 else value
                        })
                    auth_headers['Authorization'] = value[:20] + '...' if len(value) > 20 else value
                    
                elif 'api-key' in name_lower or 'x-api-key' in name_lower:
                    auth_types['api_key'] += 1
                    auth_headers['X-API-Key'] = value[:20] + '...' if len(value) > 20 else value
                    token_extracts.append({
                        'type': 'api_key',
                        'header': name_lower,
                        'token': value[:20] + '...' if len(value) > 20 else value
                    })
                    
                elif 'cookie' in name_lower or 'session' in name_lower:
                    auth_types['cookie'] += 1
                    # Parse cookies to find auth tokens
                    cookies = self._parse_cookies(value)
                    for cookie_name, cookie_value in cookies.items():
                        if any(key in cookie_name.lower() for key in ['token', 'jwt', 'auth', 'session']):
                            token_extracts.append({
                                'type': 'cookie',
                                'header': name_lower,
                                'cookie_name': cookie_name,
                                'token': cookie_value[:20] + '...' if len(cookie_value) > 20 else cookie_value
                            })
                    auth_headers['Cookie'] = value[:20] + '...' if len(value) > 20 else value

        if not auth_types:
            return AuthConfig(type='none')

        # Get most common auth type
        most_common = auth_types.most_common(1)[0]
        auth_type = most_common[0]

        # Build auth config with extracted info
        config = AuthConfig(
            type=auth_type,
            header_name=list(auth_headers.keys())[0] if auth_headers else '',
            header_value=list(auth_headers.values())[0] if auth_headers else '',
            requires_auth=True
        )

        # Add token type for bearer
        if auth_type == 'bearer':
            config.token_type = 'Bearer'
            config.token_location = 'header'
        elif auth_type == 'basic':
            config.token_type = 'Basic'
            config.token_location = 'header'
        elif auth_type == 'api_key':
            config.token_type = 'API Key'
            config.token_location = 'header'
        elif auth_type == 'cookie':
            config.token_type = 'Cookie'
            config.token_location = 'cookie'
            # Extract cookie name from token extracts
            for extract in token_extracts:
                if extract.get('type') == 'cookie':
                    config.cookie_name = extract.get('cookie_name', '')
                    break

        return config

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

class HARParser:
    """Robust HAR file parser with token extraction"""

    def __init__(self, validate_ssl: bool = True, strict_mode: bool = False):
        self.validate_ssl = validate_ssl
        self.strict_mode = strict_mode
        self.har_data = None
        self.entries = []
        self._parse_errors = []
        self._extracted_tokens = []

        self.config = {
            'max_body_size': 10 * 1024 * 1024,
            'max_entries': 10000,
            'allowed_methods': {'GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS', 'TRACE'},
            'sensitive_headers': {
                'authorization', 'cookie', 'set-cookie', 'x-api-key', 'api-key',
                'auth-token', 'x-auth-token', 'access-token', 'refresh-token',
                'session-id', 'x-session-id', 'csrf-token', 'x-csrf-token',
                'jwt', 'token', 'bearer'
            },
            'api_path_patterns': [
                r'/api/',
                r'/v\d+/',
                r'/rest/',
                r'/graphql',
                r'/oauth/',
                r'/auth/',
                r'\.json$',
                r'/service/',
                r'/rpc/',
                r'/suggest/',
                r'/flask-',
                r'/cloudgateway-',
                r'/jobapi/',
                r'/getconfig/',
                r'/sodar/',
                r'/uba$',
                r'/ads/new/',
                r'/inventory-management-',
            ],
            'exclude_path_patterns': [
                r'\.(css|js|png|gif|svg|woff2|ico|jpg|jpeg|webp|mp4|webm|woff|ttf|eot|pdf)$',
                r'/_next/static/',
                r'/fonts/',
                r'/logo_images/.*\.(gif|png|jpg|jpeg|svg|webp)$',
                r'/logo_images/',
                r'/s/\d+/\d+/(i|j|c)/',
                r'/manifest\.json$',
                r'/safeframe/',
                r'/recaptcha/',
                r'/sodar/sodar2\.js$',
                r'/sodar/sodar2/\d+/runner\.html$',
                r'/uba$',
                r'/flask-jobs',
            ],
            'auto_detect': {
                'min_api_percentage': 0.05,
                'aggressive_threshold': 0.10
            }
        }

    def parse_file(self, filename: str, encoding: str = 'utf-8') -> APISpec:
        """Parse HAR file from path"""
        file_path = Path(filename)

        if not file_path.exists():
            raise FileNotFoundError(f"HAR file not found: {filename}")

        with open(file_path, 'r', encoding=encoding) as f:
            content = f.read()

        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            content = self._sanitize_json(content)
            try:
                data = json.loads(content)
            except json.JSONDecodeError:
                raise HARParseError(f"Invalid JSON in HAR file: {str(e)}")

        return self.parse_data(data, str(file_path))

    def _sanitize_json(self, content: str) -> str:
        """Sanitize malformed JSON content"""
        content = re.sub(r',\s*([}\]])', r'\1', content)
        content = re.sub(r'//.*?$', '', content, flags=re.MULTILINE)
        content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
        return content

    def parse_data(self, har_data: Dict[str, Any], source: str = "") -> APISpec:
        """Parse HAR data structure with enhanced token extraction"""
        log = har_data.get('log', {})
        if not log:
            raise ValueError("No 'log' object found in HAR data")

        self.entries = log.get('entries', [])
        if not isinstance(self.entries, list):
            self.entries = list(self.entries) if self.entries else []

        if not self.entries:
            raise ValueError("No entries found in HAR data")

        if len(self.entries) > self.config['max_entries']:
            logger.warning(f"Too many entries ({len(self.entries)}), truncating to {self.config['max_entries']}")
            self.entries = self.entries[:self.config['max_entries']]

        # Parse all entries
        all_requests = []
        for idx, entry in enumerate(self.entries):
            try:
                request = self._parse_entry(entry)
                if request:
                    all_requests.append(request)
            except Exception as e:
                logger.warning(f"Error parsing entry {idx}: {str(e)}")
                self._parse_errors.append({'entry': idx, 'error': str(e)})

        # Extract tokens from requests
        self._extracted_tokens = self._extract_all_tokens(all_requests)

        # Classify requests into API and static
        api_requests, static_requests = self._classify_requests(all_requests)

        logger.info(f"Total: {len(all_requests)} | API: {len(api_requests)} | Static: {len(static_requests)}")
        logger.info(f"Tokens extracted: {len(self._extracted_tokens)}")

        # Extract base URL from API requests
        base_url = self._extract_base_url(api_requests)

        # Group into endpoints
        classifier = EndpointClassifier()
        endpoints = classifier.classify_endpoints(api_requests)

        # Extract authentication patterns
        detector = AuthDetector()
        auth_config = detector.detect_auth(api_requests)

        # Build API specification
        spec = APISpec(
            base_url=base_url,
            endpoints=endpoints,
            authentication=auth_config,
            common_headers=self._extract_common_headers(api_requests),
            source_files=[source] if source else [],
            metadata={
                'total_entries': len(self.entries),
                'parsed_requests': len(all_requests),
                'api_requests': len(api_requests),
                'static_requests': len(static_requests),
                'parse_errors': self._parse_errors,
                'parse_timestamp': datetime.now().isoformat(),
                'extracted_tokens': self._extracted_tokens
            }
        )

        return spec

    def _classify_requests(self, requests: List[RequestModel]) -> tuple:
        """Intelligently classify requests as API or static"""
        if not requests:
            return [], []

        api_requests = []
        static_requests = []
        ambiguous = []

        # First pass: classify based on obvious patterns
        for req in requests:
            if self._is_static_request(req):
                static_requests.append(req)
            elif self._is_api_request(req):
                api_requests.append(req)
            else:
                ambiguous.append(req)

        # Second pass: classify ambiguous requests
        for req in ambiguous:
            if self._is_likely_api(req):
                api_requests.append(req)
            else:
                static_requests.append(req)

        # Third pass: Check if any static assets were incorrectly classified as APIs
        # This happens when URLs have version numbers but are actually images
        corrected_apis = []
        for req in api_requests:
            # Check if it's actually a static asset
            if self._is_static_request(req):
                static_requests.append(req)
            else:
                corrected_apis.append(req)
        api_requests = corrected_apis

        # If we have very few APIs, be more aggressive in detection
        total = len(requests)
        if total > 0:
            api_ratio = len(api_requests) / total
            if api_ratio < self.config['auto_detect']['min_api_percentage']:
                logger.warning(f"Low API ratio ({api_ratio:.1%}), attempting aggressive detection")
                # Reclassify with more permissive rules
                api_requests = []
                static_requests = []
                for req in requests:
                    if self._is_likely_api(req, aggressive=True) and not self._is_static_request(req):
                        api_requests.append(req)
                    else:
                        static_requests.append(req)

        return api_requests, static_requests

    def _is_static_request(self, req: RequestModel) -> bool:
        """Check if request is definitely a static asset"""
        url = req.url
        if not url:
            return False

        url_lower = url.lower()

        # Check file extensions
        static_extensions = {
            'images': ['.png', '.gif', '.jpg', '.jpeg', '.svg', '.webp', '.ico', '.bmp', '.tiff'],
            'css': ['.css', '.scss', '.less'],
            'js': ['.js', '.mjs', '.jsx', '.ts', '.tsx'],
            'fonts': ['.woff', '.woff2', '.ttf', '.eot', '.otf'],
            'media': ['.mp4', '.webm', '.mp3', '.wav', '.avi', '.mov'],
            'documents': ['.pdf', '.doc', '.docx', '.xls', '.xlsx']
        }

        for ext_group in static_extensions.values():
            for ext in ext_group:
                if url_lower.endswith(ext):
                    return True

        # Check for static paths
        static_path_patterns = [
            r'/static/',
            r'/assets/',
            r'/images/',
            r'/img/',
            r'/css/',
            r'/js/',
            r'/fonts/',
            r'/media/',
            r'/_next/static/',
            r'/build/',
            r'/dist/',
            r'/public/',
            r'/favicon',
            r'/robots\.txt',
            r'/sitemap',
            r'/logo_images/',
            r'/s/\d+/\d+/(i|j|c)/',
            r'/manifest\.json$',
            r'/safeframe/',
            r'/recaptcha/',
            r'/sodar/sodar2\.js$',
            r'/sodar/sodar2/\d+/runner\.html$',
        ]

        for pattern in static_path_patterns:
            if re.search(pattern, url, re.IGNORECASE):
                return True

        # Check for image-like paths even without extension
        # e.g., /logo_images/groups/v1/12345.gif
        if re.search(r'/(logo|image|img|icon|avatar|thumb)/', url, re.IGNORECASE):
            # Check if the path ends with a number or ID (likely an image)
            if re.search(r'/v\d+/\d+\.(gif|png|jpg|jpeg|svg|webp)', url, re.IGNORECASE):
                return True

        return False

    def _is_api_request(self, req: RequestModel) -> bool:
        """Check if request matches API patterns"""
        if not req.url:
            return False

        # Check exclude patterns first
        for pattern in self.config['exclude_path_patterns']:
            if re.search(pattern, req.url, re.IGNORECASE):
                return False

        # Check API patterns
        for pattern in self.config['api_path_patterns']:
            if re.search(pattern, req.url, re.IGNORECASE):
                return True

        # Check for API-like content type in response
        if req.response and req.response.mime_type:
            api_content_types = [
                'application/json',
                'application/xml',
                'application/javascript',
                'application/x-www-form-urlencoded',
                'multipart/form-data'
            ]
            for content_type in api_content_types:
                if content_type in req.response.mime_type.lower():
                    return True

        return False

    def _is_likely_api(self, req: RequestModel, aggressive: bool = False) -> bool:
        """Check if request is likely an API based on heuristics"""
        if not req.url:
            return False

        # Check exclude patterns first
        for pattern in self.config['exclude_path_patterns']:
            if re.search(pattern, req.url, re.IGNORECASE):
                return False

        # Check for query parameters (APIs often have query params)
        if req.query_params and len(req.query_params) > 2:
            return True

        # Check for JSON request/response
        if req.body and 'json' in req.body_type.lower():
            return True

        if req.response and req.response.mime_type:
            if 'json' in req.response.mime_type.lower() or 'xml' in req.response.mime_type.lower():
                return True

        # Check for API-like path patterns
        api_like_patterns = [
            r'/v\d+/\w+',
            r'/api/',
            r'/rest/',
            r'/graphql',
            r'/query',
            r'/mutate',
            r'/rpc/',
            r'/service/',
            r'/suggest/',
            r'/search',
            r'/get',
            r'/list',
            r'/create',
            r'/update',
            r'/delete'
        ]

        for pattern in api_like_patterns:
            if re.search(pattern, req.path, re.IGNORECASE):
                return True

        # Aggressive mode: consider any request with response status 200 and JSON content as API
        if aggressive:
            if req.response and req.response.status == 200:
                if req.response.mime_type and 'json' in req.response.mime_type.lower():
                    return True
                # Also consider requests with query params
                if req.query_params and len(req.query_params) >= 1:
                    return True

        return False

    def _parse_entry(self, entry: Dict) -> Optional[RequestModel]:
        """Parse a single HAR entry"""
        if not isinstance(entry, dict):
            return None

        request_data = entry.get('request', {})
        if not request_data:
            return None

        if isinstance(request_data, str):
            try:
                request_data = json.loads(request_data)
            except:
                return None

        if not isinstance(request_data, dict):
            return None

        url = request_data.get('url', '')
        if not url:
            return None

        # Parse URL
        try:
            parsed_url = urlparse(url)
            if not parsed_url.netloc:
                return None
        except:
            return None

        # Get method
        method = request_data.get('method', 'GET').upper()
        if method not in self.config['allowed_methods']:
            method = 'GET'

        # Parse headers
        headers = self._parse_headers(request_data.get('headers', []))

        # Parse query parameters
        query_params = parse_qs(parsed_url.query, keep_blank_values=True)
        query_params = {k: [unquote(v) for v in vals] for k, vals in query_params.items()}

        # Parse body
        body, body_type = self._parse_body(request_data.get('postData', {}))

        # Parse timestamp
        timestamp = self._parse_timestamp(entry.get('startedDateTime', ''))

        # Parse response
        response_data = entry.get('response', {})
        response = self._parse_response(response_data) if response_data else None

        # Calculate size
        size = self._calculate_size(request_data, headers)

        return RequestModel(
            method=method,
            url=url,
            path=parsed_url.path or '/',
            query_params=query_params,
            headers=headers,
            body=body,
            body_type=body_type,
            timestamp=timestamp,
            request_id=entry.get('_id'),
            response=response,
            size=size,
            timings=entry.get('timings', {})
        )

    def _parse_headers(self, headers_data: Union[List, Dict, str]) -> List[RequestHeader]:
        """Parse headers from various formats"""
        headers = []

        if isinstance(headers_data, str):
            try:
                headers_data = json.loads(headers_data)
            except:
                return self._parse_http_header_string(headers_data)

        if isinstance(headers_data, list):
            for h in headers_data:
                try:
                    if isinstance(h, dict):
                        name = h.get('name', '')
                        value = h.get('value', '')
                    elif isinstance(h, (list, tuple)) and len(h) >= 2:
                        name = str(h[0])
                        value = str(h[1])
                    else:
                        continue

                    if name and value is not None:
                        is_sensitive = self._is_sensitive_header(name)
                        headers.append(RequestHeader(name=name.strip(), value=str(value).strip(), is_sensitive=is_sensitive))
                except:
                    continue

        elif isinstance(headers_data, dict):
            for name, value in headers_data.items():
                if name and value is not None:
                    is_sensitive = self._is_sensitive_header(name)
                    headers.append(RequestHeader(name=name.strip(), value=str(value).strip(), is_sensitive=is_sensitive))

        return headers

    def _parse_http_header_string(self, header_str: str) -> List[RequestHeader]:
        """Parse HTTP header string"""
        headers = []
        for line in header_str.split('\n'):
            line = line.strip()
            if ':' in line:
                parts = line.split(':', 1)
                if len(parts) == 2:
                    name = parts[0].strip()
                    value = parts[1].strip()
                    if name and value:
                        is_sensitive = self._is_sensitive_header(name)
                        headers.append(RequestHeader(name=name, value=value, is_sensitive=is_sensitive))
        return headers

    def _parse_body(self, post_data: Union[Dict, str, None]) -> tuple:
        """Parse request body"""
        if not post_data:
            return None, "json"

        body = None
        body_type = "json"

        try:
            if isinstance(post_data, dict):
                body = post_data.get('text', '')
                body_type = post_data.get('mimeType', 'application/json')
                if post_data.get('params'):
                    params = post_data.get('params', [])
                    if params:
                        body = self._format_params(params)
                        body_type = 'multipart/form-data'
            elif isinstance(post_data, str):
                body = post_data
            elif isinstance(post_data, bytes):
                body = str(post_data)
                body_type = 'binary'

            if body and len(str(body)) > self.config['max_body_size']:
                body = str(body)[:self.config['max_body_size']]

            return body, body_type
        except:
            return None, "json"

    def _format_params(self, params: List[Dict]) -> str:
        """Format parameters"""
        formatted = []
        for param in params:
            if isinstance(param, dict):
                name = param.get('name', '')
                value = param.get('value', '')
                if name:
                    formatted.append(f"{name}={value}")
        return '&'.join(formatted)

    def _parse_response(self, response_data: Dict) -> Optional[ResponseModel]:
        """Parse response data"""
        if not isinstance(response_data, dict):
            return None

        try:
            status = response_data.get('status', 0)
            status_text = response_data.get('statusText', '')
            content = response_data.get('content', {})

            body = content.get('text', '')
            mime_type = content.get('mimeType', '')
            body_size = content.get('size', 0)
            encoding = content.get('encoding', '')

            if encoding == 'base64' and body:
                try:
                    import base64
                    body = base64.b64decode(body).decode('utf-8', errors='ignore')
                except:
                    pass

            headers = self._parse_headers(response_data.get('headers', []))

            return ResponseModel(
                status=status,
                status_text=status_text,
                headers=headers,
                body=body if body else '',
                body_size=body_size,
                mime_type=mime_type,
                redirect_url=response_data.get('redirectURL', '')
            )
        except:
            return None

    def _parse_timestamp(self, timestamp_str: str) -> Optional[datetime]:
        """Parse timestamps"""
        if not timestamp_str:
            return None

        try:
            if 'Z' in timestamp_str:
                timestamp_str = timestamp_str.replace('Z', '+00:00')
            return datetime.fromisoformat(timestamp_str)
        except:
            try:
                formats = [
                    '%Y-%m-%dT%H:%M:%S.%f%z',
                    '%Y-%m-%dT%H:%M:%S%z',
                    '%Y-%m-%d %H:%M:%S',
                    '%Y-%m-%dT%H:%M:%S.%f',
                    '%Y-%m-%dT%H:%M:%S'
                ]
                for fmt in formats:
                    try:
                        return datetime.strptime(timestamp_str, fmt)
                    except:
                        continue
            except:
                pass

        return None

    def _is_sensitive_header(self, header_name: str) -> bool:
        """Check if header contains sensitive information"""
        header_name_lower = header_name.lower()
        for pattern in self.config['sensitive_headers']:
            if pattern in header_name_lower:
                return True
        return False

    def _calculate_size(self, request_data: Dict, headers: List[RequestHeader]) -> int:
        """Calculate request size"""
        size = 0
        for header in headers:
            size += len(header.name) + len(header.value) + 4

        body, _ = self._parse_body(request_data.get('postData', {}))
        if body:
            size += len(str(body))

        url = request_data.get('url', '')
        if url:
            size += len(url)
        size += len(request_data.get('method', 'GET')) + 4

        return size

    def _extract_base_url(self, requests: List[RequestModel]) -> str:
        """Extract base URL from API requests"""
        if not requests:
            return ""

        url_counts = defaultdict(int)
        for req in requests:
            if req.url:
                try:
                    parsed = urlparse(req.url)
                    base = f"{parsed.scheme}://{parsed.netloc}"
                    # Only count if it's a valid domain
                    if parsed.netloc and '.' in parsed.netloc:
                        url_counts[base] += 1
                except:
                    continue

        if url_counts:
            return max(url_counts.items(), key=lambda x: x[1])[0]

        # Fallback: try first request
        try:
            parsed = urlparse(requests[0].url)
            return f"{parsed.scheme}://{parsed.netloc}"
        except:
            return ""

    def _extract_common_headers(self, requests: List[RequestModel]) -> Dict[str, str]:
        """Extract common headers"""
        if not requests:
            return {}

        header_counts = defaultdict(int)
        header_values = defaultdict(set)

        for req in requests:
            seen_headers = set()
            for header in req.headers:
                key = header.name.lower()
                if key not in seen_headers:
                    header_counts[key] += 1
                    seen_headers.add(key)
                    if header.value:
                        header_values[key].add(header.value)

        threshold = len(requests) * 0.8
        common = {}

        for key, count in header_counts.items():
            if count >= threshold:
                values = header_values.get(key, set())
                if values:
                    common[key] = list(values)[0]

        return common

    def get_statistics(self) -> Dict[str, Any]:
        """Get parse statistics"""
        return {
            'total_entries': len(self.entries),
            'parse_errors': len(self._parse_errors),
            'errors': self._parse_errors[:10],
            'extracted_tokens': len(self._extracted_tokens)
        }

    # ==================== TOKEN EXTRACTION METHODS ====================

    def extract_session_tokens(self, har_file: str) -> Dict[str, Any]:
        """Extract session tokens and headers from HAR file"""
        spec = self.parse_file(har_file)
        
        session_info = {
            'base_url': spec.base_url,
            'authentication': {
                'type': spec.authentication.type,
                'requires_auth': spec.authentication.requires_auth,
                'header_name': spec.authentication.header_name,
                'header_value': spec.authentication.header_value,
                'token_type': getattr(spec.authentication, 'token_type', ''),
                'token_location': getattr(spec.authentication, 'token_location', ''),
                'cookie_name': getattr(spec.authentication, 'cookie_name', '')
            },
            'common_headers': spec.common_headers,
            'tokens': {
                'authorization': None,
                'bearer_token': None,
                'api_key': None,
                'cookies': {},
                'jwt_tokens': []
            },
            'all_headers': {},
            'extracted_tokens': self._extracted_tokens
        }
        
        # Extract from common headers
        for header_name, header_value in spec.common_headers.items():
            header_lower = header_name.lower()
            
            if 'authorization' in header_lower:
                session_info['tokens']['authorization'] = header_value
                # Extract bearer token if present
                if isinstance(header_value, str) and header_value.lower().startswith('bearer '):
                    session_info['tokens']['bearer_token'] = header_value[7:]
            elif 'cookie' in header_lower:
                session_info['tokens']['cookies'] = self._parse_cookie_string(header_value)
            elif 'api-key' in header_lower or 'x-api-key' in header_lower:
                session_info['tokens']['api_key'] = header_value
        
        # Also extract from first few API requests for additional headers
        if spec.endpoints:
            for endpoint in spec.endpoints[:5]:
                if endpoint.examples:
                    example = endpoint.examples[0]
                    if 'headers' in example:
                        for header, value in example['headers'].items():
                            if header not in session_info['all_headers']:
                                session_info['all_headers'][header] = value
        
        # Extract JWT tokens from extracted tokens
        for token in self._extracted_tokens:
            if token.get('type') in ['bearer', 'jwt']:
                session_info['tokens']['jwt_tokens'].append(token)
        
        return session_info

    def _parse_cookie_string(self, cookie_str: str) -> Dict[str, str]:
        """Parse cookie string into dictionary"""
        cookies = {}
        if not cookie_str:
            return cookies
        
        # Handle multiple cookie headers
        cookie_parts = cookie_str.split(';')
        for cookie in cookie_parts:
            cookie = cookie.strip()
            if '=' in cookie:
                key, value = cookie.split('=', 1)
                # Handle multiple cookies in same header
                if ';' in value:
                    # Parse nested cookies
                    for sub_cookie in value.split(';'):
                        sub_cookie = sub_cookie.strip()
                        if '=' in sub_cookie:
                            sub_key, sub_value = sub_cookie.split('=', 1)
                            cookies[sub_key.strip()] = sub_value.strip()
                else:
                    cookies[key.strip()] = value.strip()
        
        return cookies

    def _extract_all_tokens(self, requests: List[RequestModel]) -> List[Dict]:
        """Extract all tokens from requests"""
        tokens = []
        token_patterns = [
            r'Bearer\s+([a-zA-Z0-9\-_]+(?:\.[a-zA-Z0-9\-_]+){2})',  # JWT
            r'Bearer\s+([a-zA-Z0-9\-_]+)',  # Simple bearer
            r'Basic\s+([a-zA-Z0-9+/=]+)',  # Basic auth
            r'X-API-Key:\s*([a-zA-Z0-9\-_]+)',
            r'API-Key:\s*([a-zA-Z0-9\-_]+)',
            r'[Aa]uthorization:\s*Bearer\s+([a-zA-Z0-9\-_]+(?:\.[a-zA-Z0-9\-_]+){2})',
        ]
        
        for req in requests:
            for header in req.headers:
                # Check header value for tokens
                for pattern in token_patterns:
                    matches = re.findall(pattern, header.value, re.IGNORECASE)
                    for match in matches:
                        token_info = {
                            'type': self._determine_token_type(match, header.name),
                            'header': header.name,
                            'value': match[:50] + '...' if len(match) > 50 else match,
                            'full_value': match,
                            'is_sensitive': header.is_sensitive,
                            'url': req.url,
                            'method': req.method
                        }
                        tokens.append(token_info)
        
        return tokens

    def _determine_token_type(self, token: str, header_name: str) -> str:
        """Determine token type from value and header"""
        header_lower = header_name.lower()
        
        # Check if it's a JWT
        if len(token.split('.')) == 3:
            try:
                import base64
                # Try to decode JWT
                parts = token.split('.')
                decoded = base64.urlsafe_b64decode(parts[0] + '==')
                return 'jwt'
            except:
                pass
        
        if 'bearer' in header_lower or 'authorization' in header_lower:
            return 'bearer'
        elif 'api-key' in header_lower:
            return 'api_key'
        elif 'cookie' in header_lower:
            return 'cookie'
        else:
            return 'unknown'

    def _extract_auth_from_entries(self, requests: List[RequestModel]) -> Dict:
        """Extract authentication info from all requests"""
        auth_info = {
            'type': 'none',
            'headers': {},
            'tokens': {}
        }
        
        for req in requests[:10]:  # Check first few requests
            for header in req.headers:
                header_lower = header.name.lower()
                if 'authorization' in header_lower:
                    auth_info['type'] = 'bearer'
                    auth_info['headers']['Authorization'] = header.value
                    if isinstance(header.value, str) and header.value.lower().startswith('bearer '):
                        auth_info['tokens']['bearer'] = header.value[7:]
                elif 'cookie' in header_lower:
                    auth_info['type'] = 'cookie'
                    auth_info['headers']['Cookie'] = header.value
                    auth_info['tokens']['cookies'] = self._parse_cookie_string(header.value)
                elif 'api-key' in header_lower or 'x-api-key' in header_lower:
                    auth_info['type'] = 'api_key'
                    auth_info['headers'][header.name] = header.value
                    auth_info['tokens']['api_key'] = header.value
        
        return auth_info

    def get_token_summary(self) -> Dict[str, Any]:
        """Get summary of extracted tokens"""
        token_types = defaultdict(int)
        for token in self._extracted_tokens:
            token_types[token.get('type', 'unknown')] += 1
        
        return {
            'total_tokens': len(self._extracted_tokens),
            'token_types': dict(token_types),
            'tokens': self._extracted_tokens[:10]  # Show first 10 tokens
        }
