#!/usr/bin/env python3
"""
Extract key headers and endpoints from HAR file
"""

import json
import sys
from urllib.parse import urlparse

def analyze_har(har_file):
    with open(har_file, 'r') as f:
        data = json.load(f)
    
    entries = data.get('log', {}).get('entries', [])
    
    # Track unique endpoints
    endpoints = {}
    cookies = {}
    headers_info = {}
    
    for entry in entries:
        request = entry.get('request', {})
        url = request.get('url', '')
        method = request.get('method', '')
        parsed = urlparse(url)
        
        # Track endpoints
        endpoint = parsed.path
        if endpoint not in endpoints:
            endpoints[endpoint] = {'count': 0, 'methods': set()}
        endpoints[endpoint]['count'] += 1
        endpoints[endpoint]['methods'].add(method)
        
        # Look for cookies
        for header in request.get('headers', []):
            if header.get('name', '').lower() == 'cookie':
                cookie_str = header.get('value', '')
                for cookie in cookie_str.split('; '):
                    if '=' in cookie:
                        key, value = cookie.split('=', 1)
                        if key not in cookies:
                            cookies[key] = set()
                        cookies[key].add(value)
    
    # Print results
    print("=" * 60)
    print("🔍 HAR ANALYSIS RESULTS")
    print("=" * 60)
    
    print("\n📌 ENDPOINTS FOUND:")
    for endpoint, info in sorted(endpoints.items()):
        print(f"  {endpoint} ({info['count']} requests)")
    
    print("\n🍪 COOKIES FOUND:")
    for key, values in sorted(cookies.items()):
        print(f"  {key}: {', '.join(list(values)[:3])}{'...' if len(values) > 3 else ''}")
    
    # Find agoda.user.03 specifically
    if 'agoda.user.03' in cookies:
        print(f"\n🔴 CRITICAL COOKIE: agoda.user.03")
        for val in cookies['agoda.user.03']:
            print(f"  → {val}")
    
    return endpoints, cookies

if __name__ == "__main__":
    # The HAR is in the paste - save it to a file first
    print("Please save the HAR content to a file first, then run:")
    print("python extract_har_headers.py <har_file.json>")
