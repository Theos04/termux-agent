"""
Data models for HAR analysis and API generation
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Set
from datetime import datetime
from enum import Enum

class HttpMethod(Enum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
    PATCH = "PATCH"
    HEAD = "HEAD"
    OPTIONS = "OPTIONS"

class AuthType(Enum):
    BEARER = "bearer"
    BASIC = "basic"
    API_KEY = "api_key"
    COOKIE = "cookie"
    OAUTH2 = "oauth2"
    NONE = "none"

class EndpointType(Enum):
    API = "api"
    STATIC = "static"
    GRAPHQL = "graphql"
    REST = "rest"
    WEBSOCKET = "websocket"

@dataclass
class RequestHeader:
    """HTTP request header"""
    name: str
    value: str
    is_sensitive: bool = False
    
    def is_auth_header(self) -> bool:
        """Check if this is an authentication header"""
        auth_names = {'authorization', 'x-api-key', 'x-auth-token', 'cookie', 'x-csrf-token'}
        return self.name.lower() in auth_names

@dataclass
class RequestModel:
    """HTTP request model"""
    method: str
    url: str
    path: str
    query_params: Dict[str, List[str]] = field(default_factory=dict)
    headers: List[RequestHeader] = field(default_factory=list)
    body: Optional[str] = None
    body_type: str = "json"  # json, form, text, binary
    timestamp: Optional[datetime] = None
    request_id: Optional[str] = None

@dataclass
class ResponseModel:
    """HTTP response model"""
    status: int
    status_text: str = ""
    headers: List[RequestHeader] = field(default_factory=list)
    body: Optional[str] = None
    body_size: int = 0
    mime_type: str = ""
    timestamp: Optional[datetime] = None
    response_time: Optional[float] = None

@dataclass
class EndpointModel:
    """API endpoint model"""
    method: HttpMethod
    path: str
    base_url: str
    query_params: Set[str] = field(default_factory=set)
    request_headers: Set[str] = field(default_factory=set)
    response_headers: Set[str] = field(default_factory=set)
    request_body_schema: Optional[Dict] = None
    response_body_schema: Optional[Dict] = None
    examples: List[RequestModel] = field(default_factory=list)
    frequency: int = 0
    avg_response_time: float = 0.0
    status_codes: Dict[int, int] = field(default_factory=dict)
    endpoint_type: EndpointType = EndpointType.API
    dependencies: List[str] = field(default_factory=list)
    dependents: List[str] = field(default_factory=list)

@dataclass
class AuthConfig:
    """Authentication configuration"""
    auth_type: AuthType = AuthType.NONE
    header_name: str = ""
    header_value_pattern: str = ""
    token_locations: List[str] = field(default_factory=list)
    login_endpoint: Optional[str] = None
    refresh_endpoint: Optional[str] = None
    session_cookie: Optional[str] = None
    confidence: float = 0.0

@dataclass
class APISpec:
    """Complete API specification"""
    base_url: str
    title: str = "API from HAR Analysis"
    version: str = "1.0.0"
    endpoints: List[EndpointModel] = field(default_factory=list)
    authentication: AuthConfig = field(default_factory=AuthConfig)
    common_headers: Dict[str, str] = field(default_factory=dict)
    dependencies: List[Dict[str, str]] = field(default_factory=list)
    generated_at: datetime = field(default_factory=datetime.now)
    source_files: List[str] = field(default_factory=list)
