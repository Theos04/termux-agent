"""
Endpoint classification and grouping
"""

import re
from typing import List, Dict, Set
from collections import defaultdict
from urllib.parse import urlparse

from ..core.models import RequestModel, EndpointModel, HttpMethod, EndpointType

class EndpointClassifier:
    """Classify and group API endpoints"""
    
    def __init__(self, similarity_threshold: float = 0.85):
        self.similarity_threshold = similarity_threshold
        self.static_patterns = [
            r'\.(js|css|png|jpg|jpeg|gif|svg|ico|woff|woff2|ttf|eot)$',
            r'/(static|assets|images|fonts|styles|scripts)/',
            r'/(favicon|manifest|robots)\.'
        ]
        self.api_patterns = [
            r'/api/',
            r'/v[0-9]+/',
            r'/gateway/',
            r'/services/',
            r'/rest/',
            r'/graphql'
        ]
        
    def classify_endpoints(self, requests: List[RequestModel]) -> List[EndpointModel]:
        """Classify requests into endpoints"""
        # Group by method and path pattern
        groups = self._group_requests(requests)
        
        endpoints = []
        for (method, pattern), request_group in groups.items():
            endpoint = self._create_endpoint(method, pattern, request_group)
            if endpoint:
                endpoints.append(endpoint)
                
        return sorted(endpoints, key=lambda e: e.frequency, reverse=True)
    
    def _group_requests(self, requests: List[RequestModel]) -> Dict[tuple, List[RequestModel]]:
        """Group requests by method and path pattern"""
        groups = defaultdict(list)
        
        for req in requests:
            # Normalize path by replacing IDs with placeholders
            normalized_path = self._normalize_path(req.path)
            key = (req.method, normalized_path)
            groups[key].append(req)
            
        return groups
    
    def _normalize_path(self, path: str) -> str:
        """Normalize path by replacing dynamic segments"""
        # Replace UUIDs
        path = re.sub(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', '{id}', path)
        # Replace numeric IDs
        path = re.sub(r'/\d+', '/{id}', path)
        # Replace hashes
        path = re.sub(r'/[a-f0-9]{32,}', '/{hash}', path)
        return path
    
    def _create_endpoint(self, method: str, pattern: str, requests: List[RequestModel]) -> Optional[EndpointModel]:
        """Create an endpoint model from a group of requests"""
        if not requests:
            return None
            
        # Determine endpoint type
        endpoint_type = self._determine_endpoint_type(requests[0].url)
        
        # Extract query params
        query_params = set()
        request_headers = set()
        response_headers = set()
        status_codes = defaultdict(int)
        
        total_response_time = 0
        
        for req in requests:
            query_params.update(req.query_params.keys())
            for header in req.headers:
                request_headers.add(header.name)
            # Note: Response headers would come from response model
            # This is simplified
            
        return EndpointModel(
            method=HttpMethod(method),
            path=pattern,
            base_url=self._extract_base_url(requests[0].url),
            query_params=query_params,
            request_headers=request_headers,
            response_headers=set(),
            examples=requests[:3],  # Keep first 3 as examples
            frequency=len(requests),
            status_codes=dict(status_codes),
            endpoint_type=endpoint_type
        )
    
    def _determine_endpoint_type(self, url: str) -> EndpointType:
        """Determine the type of endpoint"""
        if '/graphql' in url:
            return EndpointType.GRAPHQL
        if '/api/' in url or '/rest/' in url:
            return EndpointType.REST
        if self._is_static_url(url):
            return EndpointType.STATIC
        return EndpointType.API
    
    def _is_static_url(self, url: str) -> bool:
        """Check if URL is a static asset"""
        return any(re.search(p, url, re.IGNORECASE) for p in self.static_patterns)
    
    def _extract_base_url(self, url: str) -> str:
        """Extract base URL from full URL"""
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}"
