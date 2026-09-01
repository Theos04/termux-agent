"""
Authentication pattern detection
"""

import re
from typing import List, Dict, Optional
from collections import Counter

from ..core.models import RequestModel, AuthConfig, AuthType, RequestHeader

class AuthDetector:
    """Detect authentication patterns in requests"""
    
    def __init__(self):
        self.auth_patterns = {
            'bearer': {
                'headers': ['authorization'],
                'pattern': r'^Bearer\s+(.+)$',
                'auth_type': AuthType.BEARER
            },
            'basic': {
                'headers': ['authorization'],
                'pattern': r'^Basic\s+(.+)$',
                'auth_type': AuthType.BASIC
            },
            'api_key': {
                'headers': ['x-api-key', 'api-key', 'x-auth-token'],
                'pattern': r'^(.+)$',
                'auth_type': AuthType.API_KEY
            },
            'cookie': {
                'headers': ['cookie'],
                'pattern': r'^(.+)$',
                'auth_type': AuthType.COOKIE
            }
        }
        
    def detect_auth(self, requests: List[RequestModel]) -> AuthConfig:
        """Detect authentication configuration from requests"""
        auth_headers = self._extract_auth_headers(requests)
        
        if not auth_headers:
            return AuthConfig(auth_type=AuthType.NONE)
            
        # Find the most common auth pattern
        auth_type_counts = Counter()
        header_counts = Counter()
        token_locations = []
        
        for req in requests:
            for header in req.headers:
                if header.is_sensitive:
                    header_counts[header.name] += 1
                    # Try to match auth patterns
                    for pattern_name, pattern_info in self.auth_patterns.items():
                        if header.name.lower() in pattern_info['headers']:
                            if re.search(pattern_info['pattern'], header.value):
                                auth_type_counts[pattern_info['auth_type']] += 1
                                token_locations.append({
                                    'header': header.name,
                                    'value_pattern': self._anonymize_token(header.value)
                                })
                                
        # Determine most likely auth type
        if auth_type_counts:
            primary_auth = auth_type_counts.most_common(1)[0][0]
            
            # Find the header for this auth type
            header_name = ""
            for pattern_info in self.auth_patterns.values():
                if pattern_info['auth_type'] == primary_auth:
                    header_name = pattern_info['headers'][0]
                    break
                    
            return AuthConfig(
                auth_type=primary_auth,
                header_name=header_name,
                token_locations=[loc['header'] for loc in token_locations],
                confidence=auth_type_counts[primary_auth] / len(requests)
            )
            
        return AuthConfig(auth_type=AuthType.NONE)
    
    def _extract_auth_headers(self, requests: List[RequestModel]) -> List[RequestHeader]:
        """Extract authentication headers from requests"""
        auth_headers = []
        for req in requests:
            for header in req.headers:
                if header.is_sensitive:
                    auth_headers.append(header)
        return auth_headers
    
    def _anonymize_token(self, token: str) -> str:
        """Anonymize token for display"""
        if len(token) > 20:
            return token[:10] + '...' + token[-5:]
        return token
