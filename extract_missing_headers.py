#!/usr/bin/env python3
"""
Extract missing headers from HAR file
"""

import json
from pathlib import Path

def extract_missing_headers(har_file):
    with open(har_file, 'r') as f:
        data = json.load(f)
    
    entries = data.get('log', {}).get('entries', [])
    
    print("🔍 Looking for missing headers (AppId, SystemId, etc.)")
    print("="*60)
    print()
    
    # Look for the headers in successful API calls
    for entry in entries:
        request = entry.get('request', {})
        url = request.get('url', '')
        
        # Look for the search endpoint
        if 'jobapi/v2/search/recom-jobs' not in url:
            continue
            
        # Check if it was successful
        status = entry.get('response', {}).get('status', 0)
        if status == 200:
            print(f"✅ Found successful search request!")
            print(f"URL: {url}")
            print()
            
            # Get all headers
            headers = request.get('headers', [])
            print("📋 All Headers from successful request:")
            print("-" * 40)
            
            important_headers = [
                'appid', 'appId', 'systemid', 'systemId', 
                'x-app-id', 'x-system-id', 'x-request-id',
                'device-id', 'session-id', 'client-id'
            ]
            
            for h in headers:
                if isinstance(h, dict):
                    name = h.get('name', '')
                    value = h.get('value', '')
                    
                    # Check if it's an important header
                    is_important = any(important in name.lower() for important in important_headers)
                    
                    if is_important or name.lower() in ['content-type', 'accept', 'user-agent']:
                        print(f"  {name}: {value}")
            
            return
    
    print("❌ No successful search request found with status 200")
    print("Looking for any successful API call...")
    
    for entry in entries:
        status = entry.get('response', {}).get('status', 0)
        if status == 200:
            request = entry.get('request', {})
            headers = request.get('headers', [])
            
            print(f"✅ Found successful API call: {request.get('url', '')}")
            print("Headers:")
            for h in headers:
                if isinstance(h, dict):
                    name = h.get('name', '')
                    value = h.get('value', '')
                    if 'id' in name.lower() or 'app' in name.lower() or 'system' in name.lower():
                        print(f"  {name}: {value}")
            return

if __name__ == "__main__":
    har_file = "har_capture_20260802_144837.har"
    if Path(har_file).exists():
        extract_missing_headers(har_file)
    else:
        print("HAR file not found")
