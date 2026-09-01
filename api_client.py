#!/usr/bin/env python3
"""
Auto-generated API client from HAR analysis
Generated: 2026-08-10T15:35:47.000354
Total Endpoints: 6
"""

import requests
import json
from typing import Optional, Dict, Any, List
from datetime import datetime
from urllib.parse import urlencode
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging

logger = logging.getLogger(__name__)

class NaukriAPIClient:
    """Auto-generated API client from HAR analysis"""
    
    BASE_URL = 'https://www.naukri.com'
    
    def __init__(self, 
                 token: Optional[str] = None,
                 api_key: Optional[str] = None,
                 session: Optional[requests.Session] = None,
                 **kwargs):
        """
        Initialize the API client
        
        Args:
            token: Bearer token for authentication
            api_key: API key for authentication
            session: Custom requests session
            **kwargs: Additional headers as keyword arguments
        """
        self.token = token
        self.api_key = api_key
        self.session = session or requests.Session()
        
        # Default headers
        self.default_headers = {
            "User-Agent": "APIClient/1.0",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        
        # Add common headers from HAR analysis
        self.default_headers['sec-ch-ua-platform'] = '"Linux"'
        self.default_headers['referer'] = 'https://www.naukri.com/flask-jobs?k=flask&nignbevent_src=jobsearchDeskGNB'
        self.default_headers['user-agent'] = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36'
        self.default_headers['sec-ch-ua'] = '"Chromium";v="149", "Not)A;Brand";v="24"'
        self.default_headers['sec-ch-ua-mobile'] = '?0'
        self.default_headers['accept'] = '*/*'
        
        # Add authentication
        if token:
            self.default_headers["Authorization"] = f"Bearer {token}"
        elif api_key:
            self.default_headers["X-API-Key"] = api_key
            
        # Custom headers
        for key, value in kwargs.items():
            if key.startswith('header_'):
                header_name = key.replace('header_', '')
                self.default_headers[header_name] = value
                
        self.session.headers.update(self.default_headers)
        
        # Rate limiting
        self.rate_limit = 50  # requests per second
        self.last_request_time = 0
        
    def _request(self, 
                 method: str, 
                 path: str,
                 params: Optional[Dict] = None,
                 json_data: Optional[Dict] = None,
                 **kwargs) -> Dict[str, Any]:
        """Make API request with error handling"""
        url = f"{self.BASE_URL}{path}"
        
        try:
            response = self.session.request(
                method=method,
                url=url,
                params=params,
                json=json_data,
                **kwargs
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error: {e}")
            return {"error": str(e), "status_code": response.status_code}
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error: {e}")
            return {"error": str(e)}
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
            return {"error": "Invalid JSON response", "text": response.text[:200]}
            
    def _apply_rate_limit(self):
        """Apply rate limiting"""
        import time
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        if time_since_last < 1.0 / self.rate_limit:
            time.sleep(1.0 / self.rate_limit - time_since_last)
        self.last_request_time = time.time()

    def get_suggest_dscommonsuggester(self, 
                          limit: Optional[str] = None,
                          appId: Optional[str] = None,
                          tagThree: Optional[str] = None,
                          tagFour: Optional[str] = None,
                          resultField: Optional[str] = None,
                          subCategory: Optional[str] = None,
                          query: Optional[str] = None,
                          category: Optional[str] = None,
                          c_query: Optional[str] = None,
                          p_query: Optional[str] = None,
                          **kwargs) -> Dict[str, Any]:
        """
        GET /suggest/dsCommonSuggester
        
        Args:
            limit: Query parameter
            appId: Query parameter
            tagThree: Query parameter
            tagFour: Query parameter
            resultField: Query parameter
            subCategory: Query parameter
            query: Query parameter
            category: Query parameter
            c_query: Query parameter
            p_query: Query parameter
        """
        params = {}
        if limit is not None:
            params["limit"] = limit
        if appId is not None:
            params["appId"] = appId
        if tagThree is not None:
            params["tagThree"] = tagThree
        if tagFour is not None:
            params["tagFour"] = tagFour
        if resultField is not None:
            params["resultField"] = resultField
        if subCategory is not None:
            params["subCategory"] = subCategory
        if query is not None:
            params["query"] = query
        if category is not None:
            params["category"] = category
        if c_query is not None:
            params["c_query"] = c_query
        if p_query is not None:
            params["p_query"] = p_query
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/suggest/dsCommonSuggester',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_jobapi_v1_ads(self, 
                          adType: Optional[str] = None,
                          deviceType: Optional[str] = None,
                          **kwargs) -> Dict[str, Any]:
        """
        GET /jobapi/v1/ads/new/ff
        
        Args:
            adType: Query parameter
            deviceType: Query parameter
        """
        params = {}
        if adType is not None:
            params["adType"] = adType
        if deviceType is not None:
            params["deviceType"] = deviceType
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/jobapi/v1/ads/new/ff',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_jobapi_v3_search(self, 
                          noOfResults: Optional[str] = None,
                          urlType: Optional[str] = None,
                          searchType: Optional[str] = None,
                          keyword: Optional[str] = None,
                          pageNo: Optional[str] = None,
                          k: Optional[str] = None,
                          nignbevent_src: Optional[str] = None,
                          seoKey: Optional[str] = None,
                          src: Optional[str] = None,
                          latLong: Optional[str] = None,
                          **kwargs) -> Dict[str, Any]:
        """
        GET /jobapi/v3/search
        
        Args:
            noOfResults: Query parameter
            urlType: Query parameter
            searchType: Query parameter
            keyword: Query parameter
            pageNo: Query parameter
            k: Query parameter
            nignbevent_src: Query parameter
            seoKey: Query parameter
            src: Query parameter
            latLong: Query parameter
        """
        params = {}
        if noOfResults is not None:
            params["noOfResults"] = noOfResults
        if urlType is not None:
            params["urlType"] = urlType
        if searchType is not None:
            params["searchType"] = searchType
        if keyword is not None:
            params["keyword"] = keyword
        if pageNo is not None:
            params["pageNo"] = pageNo
        if k is not None:
            params["k"] = k
        if nignbevent_src is not None:
            params["nignbevent_src"] = nignbevent_src
        if seoKey is not None:
            params["seoKey"] = seoKey
        if src is not None:
            params["src"] = src
        if latLong is not None:
            params["latLong"] = latLong
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/jobapi/v3/search',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_jobapi_v1_ads(self, 
                          urlType: Optional[str] = None,
                          searchType: Optional[str] = None,
                          keyword: Optional[str] = None,
                          **kwargs) -> Dict[str, Any]:
        """
        GET /jobapi/v1/ads/new/dfp
        
        Args:
            urlType: Query parameter
            searchType: Query parameter
            keyword: Query parameter
        """
        params = {}
        if urlType is not None:
            params["urlType"] = urlType
        if searchType is not None:
            params["searchType"] = searchType
        if keyword is not None:
            params["keyword"] = keyword
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/jobapi/v1/ads/new/dfp',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def post_cloudgateway_ccs_inventory_management_services_v2(self, 
                          partial: Optional[str] = None,
                          rules: Optional[str] = None,
                          sync: Optional[str] = None,
                          **kwargs) -> Dict[str, Any]:
        """
        POST /cloudgateway-ccs/inventory-management-services/v2/page/pagename/ni-desktop-srp-dashboard-v2
        
        Args:
            partial: Query parameter
            rules: Query parameter
            sync: Query parameter
        """
        params = {}
        if partial is not None:
            params["partial"] = partial
        if rules is not None:
            params["rules"] = rules
        if sync is not None:
            params["sync"] = sync
        
        json_data = kwargs.get("json_data", {})
        # Add additional body parameters
        for key, value in kwargs.items():
            if key not in ["json_data"]:
                json_data[key] = value
        
        return self._request(
            method='POST',
            path='/cloudgateway-ccs/inventory-management-services/v2/page/pagename/ni-desktop-srp-dashboard-v2',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_getconfig_sodar(self, 
                          sv: Optional[str] = None,
                          tid: Optional[str] = None,
                          tv: Optional[str] = None,
                          st: Optional[str] = None,
                          sjk: Optional[str] = None,
                          **kwargs) -> Dict[str, Any]:
        """
        GET /getconfig/sodar
        
        Args:
            sv: Query parameter
            tid: Query parameter
            tv: Query parameter
            st: Query parameter
            sjk: Query parameter
        """
        params = {}
        if sv is not None:
            params["sv"] = sv
        if tid is not None:
            params["tid"] = tid
        if tv is not None:
            params["tv"] = tv
        if st is not None:
            params["st"] = st
        if sjk is not None:
            params["sjk"] = sjk
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/getconfig/sodar',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    
    # Utility Methods
    
    def get_all_data(self, max_workers: int = 5) -> Dict[str, Any]:
        """Fetch data from all endpoints in parallel"""
        results = {}
        endpoints = [m for m in dir(self) if callable(getattr(self, m)) and m.startswith(('get_', 'post_', 'put_', 'delete_'))]
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                endpoint: executor.submit(getattr(self, endpoint))
                for endpoint in endpoints
            }
            
            for endpoint, future in futures.items():
                try:
                    results[endpoint] = future.result(timeout=30)
                except Exception as e:
                    results[endpoint] = {"error": str(e)}
                    
        return results
    
    def export_openapi(self) -> Dict[str, Any]:
        """Generate OpenAPI specification"""
        return {
            "openapi": "3.0.0",
            "info": {
                "title": "NaukriAPIClient API",
                "version": "1.0.0",
                "description": "Auto-generated from HAR analysis"
            },
            "servers": [{"url": self.BASE_URL}],
            "paths": {
                '/suggest/dsCommonSuggester': {
                    'get': {
                        "summary": 'get_suggest_dscommonsuggester',
                        "parameters": [
                            {
                                "name": 'limit',
                                "in": "query",
                                "schema": {"type": "string"}
                            },                            {
                                "name": 'appId',
                                "in": "query",
                                "schema": {"type": "string"}
                            },                            {
                                "name": 'tagThree',
                                "in": "query",
                                "schema": {"type": "string"}
                            },                            {
                                "name": 'tagFour',
                                "in": "query",
                                "schema": {"type": "string"}
                            },                            {
                                "name": 'resultField',
                                "in": "query",
                                "schema": {"type": "string"}
                            },                            {
                                "name": 'subCategory',
                                "in": "query",
                                "schema": {"type": "string"}
                            },                            {
                                "name": 'query',
                                "in": "query",
                                "schema": {"type": "string"}
                            },                            {
                                "name": 'category',
                                "in": "query",
                                "schema": {"type": "string"}
                            },                            {
                                "name": 'c_query',
                                "in": "query",
                                "schema": {"type": "string"}
                            },                            {
                                "name": 'p_query',
                                "in": "query",
                                "schema": {"type": "string"}
                            }                        ]
                    }
                },                '/jobapi/v1/ads/new/ff': {
                    'get': {
                        "summary": 'get_jobapi_v1_ads',
                        "parameters": [
                            {
                                "name": 'adType',
                                "in": "query",
                                "schema": {"type": "string"}
                            },                            {
                                "name": 'deviceType',
                                "in": "query",
                                "schema": {"type": "string"}
                            }                        ]
                    }
                },                '/jobapi/v3/search': {
                    'get': {
                        "summary": 'get_jobapi_v3_search',
                        "parameters": [
                            {
                                "name": 'noOfResults',
                                "in": "query",
                                "schema": {"type": "string"}
                            },                            {
                                "name": 'urlType',
                                "in": "query",
                                "schema": {"type": "string"}
                            },                            {
                                "name": 'searchType',
                                "in": "query",
                                "schema": {"type": "string"}
                            },                            {
                                "name": 'keyword',
                                "in": "query",
                                "schema": {"type": "string"}
                            },                            {
                                "name": 'pageNo',
                                "in": "query",
                                "schema": {"type": "string"}
                            },                            {
                                "name": 'k',
                                "in": "query",
                                "schema": {"type": "string"}
                            },                            {
                                "name": 'nignbevent_src',
                                "in": "query",
                                "schema": {"type": "string"}
                            },                            {
                                "name": 'seoKey',
                                "in": "query",
                                "schema": {"type": "string"}
                            },                            {
                                "name": 'src',
                                "in": "query",
                                "schema": {"type": "string"}
                            },                            {
                                "name": 'latLong',
                                "in": "query",
                                "schema": {"type": "string"}
                            }                        ]
                    }
                },                '/jobapi/v1/ads/new/dfp': {
                    'get': {
                        "summary": 'get_jobapi_v1_ads',
                        "parameters": [
                            {
                                "name": 'urlType',
                                "in": "query",
                                "schema": {"type": "string"}
                            },                            {
                                "name": 'searchType',
                                "in": "query",
                                "schema": {"type": "string"}
                            },                            {
                                "name": 'keyword',
                                "in": "query",
                                "schema": {"type": "string"}
                            }                        ]
                    }
                },                '/cloudgateway-ccs/inventory-management-services/v2/page/pagename/ni-desktop-srp-dashboard-v2': {
                    'post': {
                        "summary": 'post_cloudgateway_ccs_inventory_management_services_v2',
                        "parameters": [
                            {
                                "name": 'partial',
                                "in": "query",
                                "schema": {"type": "string"}
                            },                            {
                                "name": 'rules',
                                "in": "query",
                                "schema": {"type": "string"}
                            },                            {
                                "name": 'sync',
                                "in": "query",
                                "schema": {"type": "string"}
                            }                        ]
                    }
                },                '/getconfig/sodar': {
                    'get': {
                        "summary": 'get_getconfig_sodar',
                        "parameters": [
                            {
                                "name": 'sv',
                                "in": "query",
                                "schema": {"type": "string"}
                            },                            {
                                "name": 'tid',
                                "in": "query",
                                "schema": {"type": "string"}
                            },                            {
                                "name": 'tv',
                                "in": "query",
                                "schema": {"type": "string"}
                            },                            {
                                "name": 'st',
                                "in": "query",
                                "schema": {"type": "string"}
                            },                            {
                                "name": 'sjk',
                                "in": "query",
                                "schema": {"type": "string"}
                            }                        ]
                    }
                }            }
        }

# Example usage
if __name__ == "__main__":
    # Initialize client
    client = NaukriAPIClient(token="your_token_here")
    
    # Example: Fetch data from all endpoints
    # all_data = client.get_all_data()
    # print(json.dumps(all_data, indent=2))
    
    print("API Client Generated Successfully!")
    print(f"Base URL: {client.BASE_URL}")
    print(f"Available methods: {[m for m in dir(client) if callable(getattr(client, m)) and not m.startswith('_')]}")