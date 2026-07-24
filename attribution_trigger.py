#!/usr/bin/env python3
"""
Auto-generated API wrapper from HAR analysis
Generated: 2026-07-24 23:41:44
Total Endpoints: 13
"""

import requests
from typing import Optional, Dict, Any, List
from datetime import datetime
import json


class attribution_trigger:
    """API client for Unstop.com"""
    
    BASE_URL = "https://unstop.com"
    
    def __init__(self, token: Optional[str] = None, **kwargs):
        """Initialize API client"""
        self.token = token
        self.session = requests.Session()
        
        # Default headers
        self.default_headers = {
            "sec-ch-ua-platform": ""Linux"",
            "Referer": "https://unstop.com/job/backend-development-jobs?oppstatus=open&roles=backend-development",
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "sec-ch-ua": ""Chromium";v="149", "Not)A;Brand";v="24"",
            "sec-ch-ua-mobile": "?0",
            "Content-Type": "text/plain;charset=utf-8",
            "Access-Control-Request-Headers": "content-type,moe-appkey",
            "Access-Control-Request-Method": "POST",
            "Origin": "https://unstop.com",
        }
        
        if token:
            self.default_headers["Authorization"] = f"Bearer {token}"
        
        self.session.headers.update(self.default_headers)
        
        # Custom headers
        for key, value in kwargs.items():
            if key.startswith('header_'):
                header_name = key.replace('header_', '')
                self.session.headers[header_name] = value
    
    
    def get_assets_static_json_converted_faqs_data_json(self, **kwargs) -> Dict[str, Any]:
        """GET /assets/static-json/converted_faqs_data.json"""
        url = f"{self.BASE_URL}/assets/static-json/converted_faqs_data.json"
        
        response = self.session.get(url, **kwargs.get('request_kwargs', {}))
        
        return self._handle_response(response)
    
    
    def get_assets_i18n_ucore_en_json(self, **kwargs) -> Dict[str, Any]:
        """GET /assets/i18n/ucore-en.json"""
        url = f"{self.BASE_URL}/assets/i18n/ucore-en.json"
        
        response = self.session.get(url, **kwargs.get('request_kwargs', {}))
        
        return self._handle_response(response)
    
    
    def get_attribution_trigger(self, **kwargs) -> Dict[str, Any]:
        """GET /attribution_trigger"""
        url = f"{self.BASE_URL}/attribution_trigger"
        
        response = self.session.get(url, **kwargs.get('request_kwargs', {}))
        
        return self._handle_response(response)
    
    
    def get_pagead_viewthroughconversion_16653406380(self, **kwargs) -> Dict[str, Any]:
        """GET /pagead/viewthroughconversion/16653406380/"""
        url = f"{self.BASE_URL}/pagead/viewthroughconversion/16653406380/"
        
        response = self.session.get(url, **kwargs.get('request_kwargs', {}))
        
        return self._handle_response(response)
    
    
    def get_pagead_viewthroughconversion_1007890599(self, **kwargs) -> Dict[str, Any]:
        """GET /pagead/viewthroughconversion/1007890599/"""
        url = f"{self.BASE_URL}/pagead/viewthroughconversion/1007890599/"
        
        response = self.session.get(url, **kwargs.get('request_kwargs', {}))
        
        return self._handle_response(response)
    
    
    def get_public_opportunity_search_result(self, **kwargs) -> Dict[str, Any]:
        """GET /api/public/opportunity/search-result"""
        url = f"{self.BASE_URL}/api/public/opportunity/search-result"
        
        response = self.session.get(url, **kwargs.get('request_kwargs', {}))
        
        return self._handle_response(response)
    
    
    def get_sdk_report_BU64JRRIOTIBVKPCO4ONDE61(self, **kwargs) -> Dict[str, Any]:
        """POST /v2/sdk/report/BU64JRRIOTIBVKPCO4ONDE61"""
        url = f"{self.BASE_URL}/v2/sdk/report/BU64JRRIOTIBVKPCO4ONDE61"
        
        json_data = kwargs.get('json', {})
        
        response = self.session.post(url, json=json_data, **kwargs.get('request_kwargs', {}))
        
        return self._handle_response(response)
    
    
    def get_campaigns_inapp_live(self, **kwargs) -> Dict[str, Any]:
        """OPTIONS /v3/campaigns/inapp/live/6a5da0bdb90d6df8861b2722"""
        url = f"{self.BASE_URL}/v3/campaigns/inapp/live/6a5da0bdb90d6df8861b2722"
        
        response = self.session.options(url, **kwargs.get('request_kwargs', {}))
        
        return self._handle_response(response)
    
    
    def get_un_cities(self, **kwargs) -> Dict[str, Any]:
        """GET /api/un-cities"""
        url = f"{self.BASE_URL}/api/un-cities"
        
        response = self.session.get(url, **kwargs.get('request_kwargs', {}))
        
        return self._handle_response(response)
    
    
    def get_workrelationship_workfunction_getAll(self, **kwargs) -> Dict[str, Any]:
        """GET /api/workrelationship/workfunction/getAll"""
        url = f"{self.BASE_URL}/api/workrelationship/workfunction/getAll"
        
        response = self.session.get(url, **kwargs.get('request_kwargs', {}))
        
        return self._handle_response(response)
    
    
    def get_campaigns_inapp_live(self, **kwargs) -> Dict[str, Any]:
        """POST /v3/campaigns/inapp/live/stats"""
        url = f"{self.BASE_URL}/v3/campaigns/inapp/live/stats"
        
        json_data = kwargs.get('json', {})
        
        response = self.session.post(url, json=json_data, **kwargs.get('request_kwargs', {}))
        
        return self._handle_response(response)
    

    def _handle_response(self, response: requests.Response) -> Dict[str, Any]:
        """Handle API response"""
        try:
            response.raise_for_status()
            if 'application/json' in response.headers.get('content-type', ''):
                return response.json()
            return {'text': response.text, 'status_code': response.status_code}
        except requests.exceptions.HTTPError as e:
            return {'error': str(e), 'status_code': response.status_code, 'text': response.text[:200]}
        except ValueError:
            return {'error': 'Invalid JSON', 'text': response.text[:200]}


    # Convenience methods
    def search_opportunities(self, **kwargs) -> Dict[str, Any]:
        """Search for opportunities"""
        return self.get_api_public_opportunity_search_result(**kwargs)

    def get_cities(self) -> Dict[str, Any]:
        """Get list of cities"""
        return self.get_api_un_cities()

    def get_work_functions(self) -> Dict[str, Any]:
        """Get work functions"""
        return self.get_api_workrelationship_workfunction_getAll()


# Example usage
if __name__ == '__main__':
    # Initialize client
    client = UnstopAPI()
    
    # Search for opportunities
    # results = client.search_opportunities(q='software engineer')
    # print(json.dumps(results, indent=2))
    
    # Get cities
    # cities = client.get_cities()
    # print(json.dumps(cities, indent=2))