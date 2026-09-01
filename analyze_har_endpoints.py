#!/usr/bin/env python3
"""
Analyze HAR file to find actual API endpoints
"""

import json
from pathlib import Path
from collections import Counter

def analyze_har(har_file):
    """Analyze HAR file for API endpoints"""
    with open(har_file, 'r') as f:
        data = json.load(f)
    
    entries = data.get('log', {}).get('entries', [])
    
    print("📊 HAR File Analysis")
    print("="*50)
    print(f"Total entries: {len(entries)}")
    print()
    
    # Find API endpoints (filter out static assets)
    api_endpoints = []
    
    for entry in entries:
        request = entry.get('request', {})
        url = request.get('url', '')
        method = request.get('method', 'GET')
        headers = request.get('headers', [])
        
        # Check if it's an API call
        is_api = False
        for header in headers:
            if header.get('name', '').lower() == 'authorization':
                is_api = True
                break
        
        # Also check for API paths
        api_paths = ['cloudgateway', 'jobapi', 'api', 'services', 'v1', 'v2']
        if any(path in url for path in api_paths):
            is_api = True
            
        # Skip static assets
        static_extensions = ['.js', '.css', '.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico', '.woff', '.woff2']
        if any(url.endswith(ext) for ext in static_extensions):
            continue
            
        # Skip tracking/analytics
        tracking = ['collect', 'pixel', 'gtm', 'gtag', 'analytics']
        if any(t in url for t in tracking):
            continue
            
        if is_api:
            api_endpoints.append({
                'url': url,
                'method': method,
                'headers': headers
            })
    
    print(f"Found {len(api_endpoints)} API endpoints")
    print()
    
    # Group by base URL
    url_groups = {}
    for endpoint in api_endpoints:
        url = endpoint['url']
        # Extract base URL
        if '?' in url:
            url = url.split('?')[0]
        
        # Group by domain
        domain = url.split('/')[2] if '://' in url else url
        if domain not in url_groups:
            url_groups[domain] = []
        url_groups[domain].append(endpoint)
    
    print("🌐 API Domains Found:")
    for domain, endpoints in sorted(url_groups.items(), key=lambda x: len(x[1]), reverse=True):
        print(f"  • {domain}: {len(endpoints)} endpoints")
    
    print()
    print("📋 Top API Endpoints (by method):")
    
    # Show top endpoints by method
    method_count = Counter()
    for endpoint in api_endpoints[:20]:
        method = endpoint['method']
        method_count[method] += 1
        url = endpoint['url'][:100]
        print(f"  {method} {url}")
    
    print()
    print("📊 Method Distribution:")
    for method, count in sorted(method_count.items()):
        print(f"  • {method}: {count}")
    
    print()
    print("✅ Most Common API Paths:")
    
    # Extract and count paths
    path_count = Counter()
    for endpoint in api_endpoints:
        url = endpoint['url']
        # Remove domain
        if '://' in url:
            path = '/' + '/'.join(url.split('/')[3:])
        else:
            path = url
        
        # Remove query parameters
        if '?' in path:
            path = path.split('?')[0]
        
        path_count[path] += 1
    
    for path, count in path_count.most_common(10):
        print(f"  • {path}: {count} requests")
    
    print()
    print("💡 Suggestion: Use the cloudgateway-mynaukri endpoints")
    print("   Base URL: https://www.naukri.com")
    print("   These contain the actual API calls")

if __name__ == "__main__":
    har_files = list(Path('.').glob('*.har'))
    
    if not har_files:
        print("No HAR files found")
        exit()
    
    print("Select HAR file:")
    for i, f in enumerate(har_files, 1):
        size = f.stat().st_size / 1024
        print(f"  {i}. {f.name} ({size:.1f} KB)")
    
    choice = input("\nEnter choice: ")
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(har_files):
            analyze_har(har_files[idx])
        else:
            print("Invalid choice")
    except ValueError:
        print("Invalid input")
