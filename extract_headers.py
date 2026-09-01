#!/usr/bin/env python3
"""
Extract exact headers from HAR file for API calls
"""

import json
from pathlib import Path

def extract_headers(har_file):
    with open(har_file, 'r') as f:
        data = json.load(f)
    
    entries = data.get('log', {}).get('entries', [])
    
    print("📋 Extracting exact headers for API calls")
    print("="*60)
    print()
    
    for entry in entries:
        request = entry.get('request', {})
        url = request.get('url', '')
        
        # Only show API endpoints we care about
        if 'jobapi' not in url and 'cloudgateway-ccs' not in url:
            continue
            
        print(f"🔹 {request.get('method', 'GET')} {url}")
        print("-" * 40)
        
        # Get headers
        headers = request.get('headers', [])
        print("📋 All Headers:")
        for h in headers:
            if isinstance(h, dict):
                name = h.get('name', '')
                value = h.get('value', '')
                print(f"  {name}: {value}")
        
        print("\n" + "="*60 + "\n")

if __name__ == "__main__":
    har_file = "har_capture_20260802_144837.har"
    if Path(har_file).exists():
        extract_headers(har_file)
    else:
        print("HAR file not found")
