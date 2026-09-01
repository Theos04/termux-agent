#!/usr/bin/env python3
"""
Auto-generated API client from HAR analysis
Generated: 2026-08-02T14:55:15.941943
Total Endpoints: 274
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
    
    BASE_URL = 'https://img.naukimg.com'
    
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
        self.default_headers['user-agent'] = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36'
        self.default_headers['sec-ch-ua'] = '"Chromium";v="149", "Not)A;Brand";v="24"'
        self.default_headers['sec-ch-ua-mobile'] = '?0'
        self.default_headers['sec-ch-ua-platform'] = '"Linux"'
        self.default_headers['referer'] = 'https://www.naukri.com/mnjuser/recommendedjobs'
        
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

    def get_mnjuser_homepage(self, 
                          **kwargs) -> Dict[str, Any]:
        """
        GET /mnjuser/homepage
        
        """
        params = {}
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/mnjuser/homepage',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_s_9_105(self, 
                          **kwargs) -> Dict[str, Any]:
        """
        GET /s/9/105/_next/static/chunks/webpack-98e018d7172db6f5.js
        
        """
        params = {}
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/s/9/105/_next/static/chunks/webpack-98e018d7172db6f5.js',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_s_9_105(self, 
                          **kwargs) -> Dict[str, Any]:
        """
        GET /s/9/105/_next/static/chunks/main-app-e7ed7af89c05b048.js
        
        """
        params = {}
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/s/9/105/_next/static/chunks/main-app-e7ed7af89c05b048.js',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_s_9_105(self, 
                          **kwargs) -> Dict[str, Any]:
        """
        GET /s/9/105/_next/static/chunks/8139-c0e2d93233a1284f.js
        
        """
        params = {}
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/s/9/105/_next/static/chunks/8139-c0e2d93233a1284f.js',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_akam_13_3ce348e8(self, 
                          **kwargs) -> Dict[str, Any]:
        """
        GET /akam/13/3ce348e8
        
        """
        params = {}
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/akam/13/3ce348e8',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_s_9_105(self, 
                          **kwargs) -> Dict[str, Any]:
        """
        GET /s/9/105/_next/static/chunks/2443530c-05f5f9c36d9c0116.js
        
        """
        params = {}
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/s/9/105/_next/static/chunks/2443530c-05f5f9c36d9c0116.js',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_s_9_105(self, 
                          **kwargs) -> Dict[str, Any]:
        """
        GET /s/9/105/_next/static/css/c336e61763b75ee6.css
        
        """
        params = {}
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/s/9/105/_next/static/css/c336e61763b75ee6.css',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_s_9_105(self, 
                          **kwargs) -> Dict[str, Any]:
        """
        GET /s/9/105/_next/static/css/2672c06d114cdca9.css
        
        """
        params = {}
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/s/9/105/_next/static/css/2672c06d114cdca9.css',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_s_9_105(self, 
                          **kwargs) -> Dict[str, Any]:
        """
        GET /s/9/105/_next/static/css/7ac4a6950080226a.css
        
        """
        params = {}
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/s/9/105/_next/static/css/7ac4a6950080226a.css',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_s_9_105(self, 
                          **kwargs) -> Dict[str, Any]:
        """
        GET /s/9/105/_next/static/css/2bc43d26759e2966.css
        
        """
        params = {}
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/s/9/105/_next/static/css/2bc43d26759e2966.css',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_s_9_105(self, 
                          **kwargs) -> Dict[str, Any]:
        """
        GET /s/9/105/_next/static/css/510d7db3becc8c35.css
        
        """
        params = {}
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/s/9/105/_next/static/css/510d7db3becc8c35.css',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_s_9_105(self, 
                          **kwargs) -> Dict[str, Any]:
        """
        GET /s/9/105/_next/static/css/58d48825c3950e2f.css
        
        """
        params = {}
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/s/9/105/_next/static/css/58d48825c3950e2f.css',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_s_9_105(self, 
                          **kwargs) -> Dict[str, Any]:
        """
        GET /s/9/105/_next/static/chunks/fac3a283-5be48d7829be91b5.js
        
        """
        params = {}
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/s/9/105/_next/static/chunks/fac3a283-5be48d7829be91b5.js',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_s_9_105(self, 
                          **kwargs) -> Dict[str, Any]:
        """
        GET /s/9/105/_next/static/chunks/2435-10acfd04b1985d7e.js
        
        """
        params = {}
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/s/9/105/_next/static/chunks/2435-10acfd04b1985d7e.js',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_s_9_105(self, 
                          **kwargs) -> Dict[str, Any]:
        """
        GET /s/9/105/_next/static/chunks/8940-3d6fc7d7063ec781.js
        
        """
        params = {}
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/s/9/105/_next/static/chunks/8940-3d6fc7d7063ec781.js',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_s_9_105(self, 
                          **kwargs) -> Dict[str, Any]:
        """
        GET /s/9/105/_next/static/chunks/5469-2fcd77d0a70a2abf.js
        
        """
        params = {}
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/s/9/105/_next/static/chunks/5469-2fcd77d0a70a2abf.js',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_s_9_105(self, 
                          **kwargs) -> Dict[str, Any]:
        """
        GET /s/9/105/_next/static/chunks/325-e40e8199495baf76.js
        
        """
        params = {}
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/s/9/105/_next/static/chunks/325-e40e8199495baf76.js',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_s_9_105(self, 
                          **kwargs) -> Dict[str, Any]:
        """
        GET /s/9/105/_next/static/chunks/6394-c68cffa6ce9625fb.js
        
        """
        params = {}
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/s/9/105/_next/static/chunks/6394-c68cffa6ce9625fb.js',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_s_9_105(self, 
                          **kwargs) -> Dict[str, Any]:
        """
        GET /s/9/105/_next/static/chunks/4224-ceb3c883028a84c4.js
        
        """
        params = {}
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/s/9/105/_next/static/chunks/4224-ceb3c883028a84c4.js',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_s_9_105(self, 
                          **kwargs) -> Dict[str, Any]:
        """
        GET /s/9/105/_next/static/chunks/app/layout-47b460cbe6b487db.js
        
        """
        params = {}
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/s/9/105/_next/static/chunks/app/layout-47b460cbe6b487db.js',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_s_9_105(self, 
                          **kwargs) -> Dict[str, Any]:
        """
        GET /s/9/105/_next/static/chunks/app/mnjuser/homepage/error-4ba54ae51df7f94f.js
        
        """
        params = {}
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/s/9/105/_next/static/chunks/app/mnjuser/homepage/error-4ba54ae51df7f94f.js',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_s_9_105(self, 
                          **kwargs) -> Dict[str, Any]:
        """
        GET /s/9/105/_next/static/chunks/app/mnjuser/homepage/page-c1cf2614aa81e776.js
        
        """
        params = {}
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/s/9/105/_next/static/chunks/app/mnjuser/homepage/page-c1cf2614aa81e776.js',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_s_0(self, 
                          **kwargs) -> Dict[str, Any]:
        """
        GET /s/0/0/i/transparentImg.png
        
        """
        params = {}
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/s/0/0/i/transparentImg.png',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_s_0(self, 
                          **kwargs) -> Dict[str, Any]:
        """
        GET /s/0/0/c/fonts/static/satoshi/KFIAZD4RUMEZIYV6FQ3T3GP5PDBDB6JY.woff2
        
        """
        params = {}
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/s/0/0/c/fonts/static/satoshi/KFIAZD4RUMEZIYV6FQ3T3GP5PDBDB6JY.woff2',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_s_0(self, 
                          **kwargs) -> Dict[str, Any]:
        """
        GET /s/0/0/c/fonts/static/satoshi/7AHDUZ4A7LFLVFUIFSARGIWCRQJHISQP.woff2
        
        """
        params = {}
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/s/0/0/c/fonts/static/satoshi/7AHDUZ4A7LFLVFUIFSARGIWCRQJHISQP.woff2',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_s_0(self, 
                          **kwargs) -> Dict[str, Any]:
        """
        GET /s/0/0/c/fonts/static/satoshi/GHM6WVH6MILNYOOCXHXB5GTSGNTMGXZR.woff2
        
        """
        params = {}
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/s/0/0/c/fonts/static/satoshi/GHM6WVH6MILNYOOCXHXB5GTSGNTMGXZR.woff2',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_s_0(self, 
                          **kwargs) -> Dict[str, Any]:
        """
        GET /s/0/0/c/fonts/static/satoshi/J64QX5IPOHK56I2KYUNBQ5M2XWZEYKYX.woff2
        
        """
        params = {}
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/s/0/0/c/fonts/static/satoshi/J64QX5IPOHK56I2KYUNBQ5M2XWZEYKYX.woff2',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def post_akam_13_pixel_3ce348e8(self, 
                          **kwargs) -> Dict[str, Any]:
        """
        POST /akam/13/pixel_3ce348e8
        
        """
        params = {}
        
        json_data = kwargs.get("json_data", {})
        # Add additional body parameters
        for key, value in kwargs.items():
            if key not in ["json_data"]:
                json_data[key] = value
        
        return self._request(
            method='POST',
            path='/akam/13/pixel_3ce348e8',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_s_0_1(self, 
                          **kwargs) -> Dict[str, Any]:
        """
        GET /s/0/1/j/ub_v1.16.min.js
        
        """
        params = {}
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/s/0/1/j/ub_v1.16.min.js',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_s_0(self, 
                          **kwargs) -> Dict[str, Any]:
        """
        GET /s/0/0/j/nLoggerJB_v3.4.min.js
        
        """
        params = {}
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/s/0/0/j/nLoggerJB_v3.4.min.js',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_favicon_ico(self, 
                          **kwargs) -> Dict[str, Any]:
        """
        GET /favicon.ico
        
        """
        params = {}
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/favicon.ico',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_s_9_105(self, 
                          **kwargs) -> Dict[str, Any]:
        """
        GET /s/9/105/_next/static/chunks/1963.7d9d77914a8664cc.js
        
        """
        params = {}
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/s/9/105/_next/static/chunks/1963.7d9d77914a8664cc.js',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_cloudgateway_mynaukri_resman_aggregator_services_v1(self, 
                          properties: Optional[str] = None,
                          **kwargs) -> Dict[str, Any]:
        """
        GET /cloudgateway-mynaukri/resman-aggregator-services/v1/users/self/dashboard
        
        Args:
            properties: Query parameter
        """
        params = {}
        if properties is not None:
            params["properties"] = properties
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/cloudgateway-mynaukri/resman-aggregator-services/v1/users/self/dashboard',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_s_9_105(self, 
                          **kwargs) -> Dict[str, Any]:
        """
        GET /s/9/105/_next/static/chunks/1778.be1aabf1dc75b363.js
        
        """
        params = {}
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/s/9/105/_next/static/chunks/1778.be1aabf1dc75b363.js',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_s_9_105(self, 
                          **kwargs) -> Dict[str, Any]:
        """
        GET /s/9/105/_next/static/chunks/647.9e6b82b3bbda979d.js
        
        """
        params = {}
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/s/9/105/_next/static/chunks/647.9e6b82b3bbda979d.js',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_s_9_105(self, 
                          **kwargs) -> Dict[str, Any]:
        """
        GET /s/9/105/_next/static/assets/info.svg
        
        """
        params = {}
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/s/9/105/_next/static/assets/info.svg',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_s_9_105(self, 
                          **kwargs) -> Dict[str, Any]:
        """
        GET /s/9/105/_next/static/assets/arrow.svg
        
        """
        params = {}
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/s/9/105/_next/static/assets/arrow.svg',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_s_9_105(self, 
                          **kwargs) -> Dict[str, Any]:
        """
        GET /s/9/105/_next/static/assets/home.svg
        
        """
        params = {}
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/s/9/105/_next/static/assets/home.svg',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_s_9_105(self, 
                          **kwargs) -> Dict[str, Any]:
        """
        GET /s/9/105/_next/static/assets/jobs.svg
        
        """
        params = {}
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/s/9/105/_next/static/assets/jobs.svg',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_s_9_105(self, 
                          **kwargs) -> Dict[str, Any]:
        """
        GET /s/9/105/_next/static/assets/company.svg
        
        """
        params = {}
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/s/9/105/_next/static/assets/company.svg',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_s_9_105(self, 
                          **kwargs) -> Dict[str, Any]:
        """
        GET /s/9/105/_next/static/assets/blog.svg
        
        """
        params = {}
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/s/9/105/_next/static/assets/blog.svg',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_s_7_0(self, 
                          **kwargs) -> Dict[str, Any]:
        """
        GET /s/7/0/j/widget-client-ni.min.js
        
        """
        params = {}
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/s/7/0/j/widget-client-ni.min.js',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_uba(self, 
                          data: Optional[str] = None,
                          rad: Optional[str] = None,
                          **kwargs) -> Dict[str, Any]:
        """
        GET //uba
        
        Args:
            data: Query parameter
            rad: Query parameter
        """
        params = {}
        if data is not None:
            params["data"] = data
        if rad is not None:
            params["rad"] = rad
        
        json_data = None
        
        return self._request(
            method='GET',
            path='//uba',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_s_9_105(self, 
                          **kwargs) -> Dict[str, Any]:
        """
        GET /s/9/105/_next/static/chunks/tracking.4c548c0510ae6df1.js
        
        """
        params = {}
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/s/9/105/_next/static/chunks/tracking.4c548c0510ae6df1.js',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_gtm_js(self, 
                          id: Optional[str] = None,
                          **kwargs) -> Dict[str, Any]:
        """
        GET /gtm.js
        
        Args:
            id: Query parameter
        """
        params = {}
        if id is not None:
            params["id"] = id
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/gtm.js',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_s_9_105(self, 
                          **kwargs) -> Dict[str, Any]:
        """
        GET /s/9/105/_next/static/chunks/9813.fe6320f6733a0e9d.js
        
        """
        params = {}
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/s/9/105/_next/static/chunks/9813.fe6320f6733a0e9d.js',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_s_9_105(self, 
                          **kwargs) -> Dict[str, Any]:
        """
        GET /s/9/105/_next/static/chunks/4506.14ae4ffaecf6088e.js
        
        """
        params = {}
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/s/9/105/_next/static/chunks/4506.14ae4ffaecf6088e.js',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_s_7_0(self, 
                          **kwargs) -> Dict[str, Any]:
        """
        GET /s/7/0/j/naukri-widget_v12.36-modern.min.js
        
        """
        params = {}
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/s/7/0/j/naukri-widget_v12.36-modern.min.js',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_cloudgateway_mynaukri_resman_aggregator_services_v0(self, 
                          **kwargs) -> Dict[str, Any]:
        """
        GET /cloudgateway-mynaukri/resman-aggregator-services/v0/users/self/profiles/18e6c5f2b2d6f71cb1abe71e0a70ccc5c0234cac14d1dd83b679862093b973de/photo
        
        """
        params = {}
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/cloudgateway-mynaukri/resman-aggregator-services/v0/users/self/profiles/18e6c5f2b2d6f71cb1abe71e0a70ccc5c0234cac14d1dd83b679862093b973de/photo',
            params=params,
            json_data=json_data,
            **kwargs.get("request_kwargs", {})
        )
    def get_cloudgateway_mynaukri_resman_aggregator_services_v2(self, 
                          expand_level: Optional[str] = None,
                          properties: Optional[str] = None,
                          **kwargs) -> Dict[str, Any]:
        """
        GET /cloudgateway-mynaukri/resman-aggregator-services/v2/users/self
        
        Args:
            expand_level: Query parameter
            properties: Query parameter
        """
        params = {}
        if expand_level is not None:
            params["expand_level"] = expand_level
        if properties is not None:
            params["properties"] = properties
        
        json_data = None
        
        return self._request(
            method='GET',
            path='/cloudgateway-mynaukri/resman-aggregator-services/v2/users/self',
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
                '/mnjuser/homepage': {
                    'get': {
                        "summary": 'get_mnjuser_homepage',
                        "parameters": [
                        ]
                    }
                },                '/s/9/105/_next/static/chunks/webpack-98e018d7172db6f5.js': {
                    'get': {
                        "summary": 'get_s_9_105',
                        "parameters": [
                        ]
                    }
                },                '/s/9/105/_next/static/chunks/main-app-e7ed7af89c05b048.js': {
                    'get': {
                        "summary": 'get_s_9_105',
                        "parameters": [
                        ]
                    }
                },                '/s/9/105/_next/static/chunks/8139-c0e2d93233a1284f.js': {
                    'get': {
                        "summary": 'get_s_9_105',
                        "parameters": [
                        ]
                    }
                },                '/akam/13/3ce348e8': {
                    'get': {
                        "summary": 'get_akam_13_3ce348e8',
                        "parameters": [
                        ]
                    }
                },                '/s/9/105/_next/static/chunks/2443530c-05f5f9c36d9c0116.js': {
                    'get': {
                        "summary": 'get_s_9_105',
                        "parameters": [
                        ]
                    }
                },                '/s/9/105/_next/static/css/c336e61763b75ee6.css': {
                    'get': {
                        "summary": 'get_s_9_105',
                        "parameters": [
                        ]
                    }
                },                '/s/9/105/_next/static/css/2672c06d114cdca9.css': {
                    'get': {
                        "summary": 'get_s_9_105',
                        "parameters": [
                        ]
                    }
                },                '/s/9/105/_next/static/css/7ac4a6950080226a.css': {
                    'get': {
                        "summary": 'get_s_9_105',
                        "parameters": [
                        ]
                    }
                },                '/s/9/105/_next/static/css/2bc43d26759e2966.css': {
                    'get': {
                        "summary": 'get_s_9_105',
                        "parameters": [
                        ]
                    }
                },                '/s/9/105/_next/static/css/510d7db3becc8c35.css': {
                    'get': {
                        "summary": 'get_s_9_105',
                        "parameters": [
                        ]
                    }
                },                '/s/9/105/_next/static/css/58d48825c3950e2f.css': {
                    'get': {
                        "summary": 'get_s_9_105',
                        "parameters": [
                        ]
                    }
                },                '/s/9/105/_next/static/chunks/fac3a283-5be48d7829be91b5.js': {
                    'get': {
                        "summary": 'get_s_9_105',
                        "parameters": [
                        ]
                    }
                },                '/s/9/105/_next/static/chunks/2435-10acfd04b1985d7e.js': {
                    'get': {
                        "summary": 'get_s_9_105',
                        "parameters": [
                        ]
                    }
                },                '/s/9/105/_next/static/chunks/8940-3d6fc7d7063ec781.js': {
                    'get': {
                        "summary": 'get_s_9_105',
                        "parameters": [
                        ]
                    }
                },                '/s/9/105/_next/static/chunks/5469-2fcd77d0a70a2abf.js': {
                    'get': {
                        "summary": 'get_s_9_105',
                        "parameters": [
                        ]
                    }
                },                '/s/9/105/_next/static/chunks/325-e40e8199495baf76.js': {
                    'get': {
                        "summary": 'get_s_9_105',
                        "parameters": [
                        ]
                    }
                },                '/s/9/105/_next/static/chunks/6394-c68cffa6ce9625fb.js': {
                    'get': {
                        "summary": 'get_s_9_105',
                        "parameters": [
                        ]
                    }
                },                '/s/9/105/_next/static/chunks/4224-ceb3c883028a84c4.js': {
                    'get': {
                        "summary": 'get_s_9_105',
                        "parameters": [
                        ]
                    }
                },                '/s/9/105/_next/static/chunks/app/layout-47b460cbe6b487db.js': {
                    'get': {
                        "summary": 'get_s_9_105',
                        "parameters": [
                        ]
                    }
                },                '/s/9/105/_next/static/chunks/app/mnjuser/homepage/error-4ba54ae51df7f94f.js': {
                    'get': {
                        "summary": 'get_s_9_105',
                        "parameters": [
                        ]
                    }
                },                '/s/9/105/_next/static/chunks/app/mnjuser/homepage/page-c1cf2614aa81e776.js': {
                    'get': {
                        "summary": 'get_s_9_105',
                        "parameters": [
                        ]
                    }
                },                '/s/0/0/i/transparentImg.png': {
                    'get': {
                        "summary": 'get_s_0',
                        "parameters": [
                        ]
                    }
                },                '/s/0/0/c/fonts/static/satoshi/KFIAZD4RUMEZIYV6FQ3T3GP5PDBDB6JY.woff2': {
                    'get': {
                        "summary": 'get_s_0',
                        "parameters": [
                        ]
                    }
                },                '/s/0/0/c/fonts/static/satoshi/7AHDUZ4A7LFLVFUIFSARGIWCRQJHISQP.woff2': {
                    'get': {
                        "summary": 'get_s_0',
                        "parameters": [
                        ]
                    }
                },                '/s/0/0/c/fonts/static/satoshi/GHM6WVH6MILNYOOCXHXB5GTSGNTMGXZR.woff2': {
                    'get': {
                        "summary": 'get_s_0',
                        "parameters": [
                        ]
                    }
                },                '/s/0/0/c/fonts/static/satoshi/J64QX5IPOHK56I2KYUNBQ5M2XWZEYKYX.woff2': {
                    'get': {
                        "summary": 'get_s_0',
                        "parameters": [
                        ]
                    }
                },                '/akam/13/pixel_3ce348e8': {
                    'post': {
                        "summary": 'post_akam_13_pixel_3ce348e8',
                        "parameters": [
                        ]
                    }
                },                '/s/0/1/j/ub_v1.16.min.js': {
                    'get': {
                        "summary": 'get_s_0_1',
                        "parameters": [
                        ]
                    }
                },                '/s/0/0/j/nLoggerJB_v3.4.min.js': {
                    'get': {
                        "summary": 'get_s_0',
                        "parameters": [
                        ]
                    }
                },                '/favicon.ico': {
                    'get': {
                        "summary": 'get_favicon_ico',
                        "parameters": [
                        ]
                    }
                },                '/s/9/105/_next/static/chunks/1963.7d9d77914a8664cc.js': {
                    'get': {
                        "summary": 'get_s_9_105',
                        "parameters": [
                        ]
                    }
                },                '/cloudgateway-mynaukri/resman-aggregator-services/v1/users/self/dashboard': {
                    'get': {
                        "summary": 'get_cloudgateway_mynaukri_resman_aggregator_services_v1',
                        "parameters": [
                            {
                                "name": 'properties',
                                "in": "query",
                                "schema": {"type": "string"}
                            }                        ]
                    }
                },                '/s/9/105/_next/static/chunks/1778.be1aabf1dc75b363.js': {
                    'get': {
                        "summary": 'get_s_9_105',
                        "parameters": [
                        ]
                    }
                },                '/s/9/105/_next/static/chunks/647.9e6b82b3bbda979d.js': {
                    'get': {
                        "summary": 'get_s_9_105',
                        "parameters": [
                        ]
                    }
                },                '/s/9/105/_next/static/assets/info.svg': {
                    'get': {
                        "summary": 'get_s_9_105',
                        "parameters": [
                        ]
                    }
                },                '/s/9/105/_next/static/assets/arrow.svg': {
                    'get': {
                        "summary": 'get_s_9_105',
                        "parameters": [
                        ]
                    }
                },                '/s/9/105/_next/static/assets/home.svg': {
                    'get': {
                        "summary": 'get_s_9_105',
                        "parameters": [
                        ]
                    }
                },                '/s/9/105/_next/static/assets/jobs.svg': {
                    'get': {
                        "summary": 'get_s_9_105',
                        "parameters": [
                        ]
                    }
                },                '/s/9/105/_next/static/assets/company.svg': {
                    'get': {
                        "summary": 'get_s_9_105',
                        "parameters": [
                        ]
                    }
                },                '/s/9/105/_next/static/assets/blog.svg': {
                    'get': {
                        "summary": 'get_s_9_105',
                        "parameters": [
                        ]
                    }
                },                '/s/7/0/j/widget-client-ni.min.js': {
                    'get': {
                        "summary": 'get_s_7_0',
                        "parameters": [
                        ]
                    }
                },                '//uba': {
                    'get': {
                        "summary": 'get_uba',
                        "parameters": [
                            {
                                "name": 'data',
                                "in": "query",
                                "schema": {"type": "string"}
                            },                            {
                                "name": 'rad',
                                "in": "query",
                                "schema": {"type": "string"}
                            }                        ]
                    }
                },                '/s/9/105/_next/static/chunks/tracking.4c548c0510ae6df1.js': {
                    'get': {
                        "summary": 'get_s_9_105',
                        "parameters": [
                        ]
                    }
                },                '/gtm.js': {
                    'get': {
                        "summary": 'get_gtm_js',
                        "parameters": [
                            {
                                "name": 'id',
                                "in": "query",
                                "schema": {"type": "string"}
                            }                        ]
                    }
                },                '/s/9/105/_next/static/chunks/9813.fe6320f6733a0e9d.js': {
                    'get': {
                        "summary": 'get_s_9_105',
                        "parameters": [
                        ]
                    }
                },                '/s/9/105/_next/static/chunks/4506.14ae4ffaecf6088e.js': {
                    'get': {
                        "summary": 'get_s_9_105',
                        "parameters": [
                        ]
                    }
                },                '/s/7/0/j/naukri-widget_v12.36-modern.min.js': {
                    'get': {
                        "summary": 'get_s_7_0',
                        "parameters": [
                        ]
                    }
                },                '/cloudgateway-mynaukri/resman-aggregator-services/v0/users/self/profiles/18e6c5f2b2d6f71cb1abe71e0a70ccc5c0234cac14d1dd83b679862093b973de/photo': {
                    'get': {
                        "summary": 'get_cloudgateway_mynaukri_resman_aggregator_services_v0',
                        "parameters": [
                        ]
                    }
                },                '/cloudgateway-mynaukri/resman-aggregator-services/v2/users/self': {
                    'get': {
                        "summary": 'get_cloudgateway_mynaukri_resman_aggregator_services_v2',
                        "parameters": [
                            {
                                "name": 'expand_level',
                                "in": "query",
                                "schema": {"type": "string"}
                            },                            {
                                "name": 'properties',
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