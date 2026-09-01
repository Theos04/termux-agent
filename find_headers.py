#!/usr/bin/env python3
"""
Find successful API calls and extract all headers
"""

import json
from pathlib import Path

def find_headers(har_file):
    with open(har_file, 'r') as f:
        data = json.load(f)
    
    entries = data.get('log', {}).get('entries', [])
    
    print("🔍 Looking for successful API calls with headers")
    print("="*60)
    print()
    
    found = 0
    for entry in entries:
        status = entry.get('response', {}).get('status', 0)
        
        if status == 200:
            request = entry.get('request', {})
            url = request.get('url', '')
            method = request.get('method', 'GET')
            
            # Skip static assets
            if any(url.endswith(ext) for ext in ['.js', '.css', '.png', '.jpg', '.svg', '.ico', '.woff', '.woff2']):
                continue
            
            # Skip data URLs
            if url.startswith('data:'):
                continue
                
            print(f"✅ {method} {url}")
            print(f"Status: {status}")
            
            headers = request.get('headers', [])
            print("📋 Headers:")
            for h in headers:
                if isinstance(h, dict):
                    name = h.get('name', '')
                    value = h.get('value', '')
                    
                    # Show all headers that might be important
                    important_keys = ['id', 'app', 'system', 'auth', 'content', 'accept', 'user-agent', 'origin', 'referer', 'cookie']
                    if any(key in name.lower() for key in important_keys):
                        if name.lower() == 'authorization':
                            value = value[:30] + '...'
                        print(f"  {name}: {value}")
            
            print("-" * 40)
            found += 1
            
            if found >= 3:
                break

if __name__ == "__main__":
    har_file = "har_capture_20260802_144837.har"
    if Path(har_file).exists():
        find_headers(har_file)
    else:
        print("HAR file not found")
