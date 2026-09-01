#!/usr/bin/env python3
"""
Extract exact request payloads from HAR file
"""

import json
from pathlib import Path
from urllib.parse import urlparse

def extract_payloads(har_file):
    with open(har_file, 'r') as f:
        data = json.load(f)
    
    entries = data.get('log', {}).get('entries', [])
    
    print("📦 Extracting exact request payloads")
    print("="*60)
    print()
    
    for entry in entries:
        request = entry.get('request', {})
        url = request.get('url', '')
        method = request.get('method', 'GET')
        
        # Only show API endpoints we care about
        if 'jobapi' not in url and 'cloudgateway-ccs' not in url:
            continue
            
        print(f"🔹 {method} {url}")
        print("-" * 40)
        
        # Get headers
        headers = request.get('headers', [])
        print("📋 Headers:")
        for h in headers:
            if isinstance(h, dict):
                name = h.get('name', '')
                value = h.get('value', '')
                if name.lower() in ['authorization', 'content-type', 'accept']:
                    if name.lower() == 'authorization':
                        value = value[:30] + '...'
                    print(f"  {name}: {value}")
        
        # Get body
        post_data = request.get('postData')
        if post_data:
            print("\n📦 Body:")
            if isinstance(post_data, dict):
                body = post_data.get('text', '')
                if body:
                    try:
                        parsed = json.loads(body)
                        print(json.dumps(parsed, indent=2)[:500])
                    except:
                        print(body[:500])
            elif isinstance(post_data, str):
                try:
                    parsed = json.loads(post_data)
                    print(json.dumps(parsed, indent=2)[:500])
                except:
                    print(post_data[:500])
        print("\n" + "="*60 + "\n")

if __name__ == "__main__":
    har_file = "har_capture_20260802_144837.har"
    if Path(har_file).exists():
        extract_payloads(har_file)
    else:
        print("HAR file not found")
