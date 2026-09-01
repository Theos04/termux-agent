#!/usr/bin/env python3
"""
Inspect HAR file to find working API endpoints
"""

import json
from pathlib import Path
from urllib.parse import urlparse
from collections import Counter

def inspect_har(har_file):
    """Inspect HAR for API calls"""
    with open(har_file, 'r') as f:
        data = json.load(f)
    
    entries = data.get('log', {}).get('entries', [])
    
    print("🔍 Inspecting HAR for Working API Calls")
    print("="*60)
    print()
    
    # Find API calls with authorization
    api_calls = []
    
    for entry in entries:
        request = entry.get('request', {})
        url = request.get('url', '')
        method = request.get('method', 'GET')
        headers = request.get('headers', [])
        
        # Handle postData - could be dict or string
        post_data = request.get('postData')
        body = ''
        if post_data:
            if isinstance(post_data, dict):
                body = post_data.get('text', '')
            elif isinstance(post_data, str):
                body = post_data
            elif isinstance(post_data, list):
                body = str(post_data)
        
        # Handle headers - they could be dict or list
        header_dict = {}
        if isinstance(headers, list):
            for h in headers:
                if isinstance(h, dict):
                    name = h.get('name', '')
                    value = h.get('value', '')
                    header_dict[name.lower()] = value
                elif isinstance(h, (list, tuple)) and len(h) >= 2:
                    header_dict[h[0].lower()] = h[1]
        elif isinstance(headers, dict):
            header_dict = {k.lower(): v for k, v in headers.items()}
        
        # Check for authorization
        has_auth = 'authorization' in header_dict
        
        # Skip static assets and tracking
        skip_extensions = ['.js', '.css', '.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico', '.woff', '.woff2', '.webp', '.ts']
        if any(url.endswith(ext) for ext in skip_extensions):
            continue
            
        skip_tracking = ['pixel', 'collect', 'gtm', 'gtag', 'analytics', 'uba', 'akam']
        if any(t in url.lower() for t in skip_tracking):
            continue
        
        # Get status
        status = entry.get('response', {}).get('status', 0)
        
        # Get response body if available
        response_body = ''
        if 'response' in entry and 'content' in entry['response']:
            content = entry['response']['content']
            if isinstance(content, dict):
                response_body = content.get('text', '')
            elif isinstance(content, str):
                response_body = content
        
        # Include API calls
        if has_auth or 'cloudgateway' in url or 'jobapi' in url:
            api_calls.append({
                'method': method,
                'url': url,
                'headers': header_dict,
                'body': body[:200] if body else '',
                'status': status,
                'response_body': response_body[:200] if response_body else ''
            })
    
    if not api_calls:
        print("❌ No API calls found with authorization")
        print("This might be because the HAR file is from a session after logout")
        print("Try capturing a fresh HAR while logged in")
        return
    
    print(f"✅ Found {len(api_calls)} API calls with authorization")
    print()
    
    # Group successful calls
    successful = [call for call in api_calls if call['status'] in [200, 201, 204]]
    failed = [call for call in api_calls if call['status'] not in [200, 201, 204] and call['status'] > 0]
    
    print(f"📊 Status Summary:")
    print(f"  • Successful (200/201/204): {len(successful)}")
    print(f"  • Failed: {len(failed)}")
    print(f"  • Other: {len(api_calls) - len(successful) - len(failed)}")
    print()
    
    if successful:
        print("📋 Working API Endpoints:")
        print("-" * 60)
        
        # Show unique successful endpoints
        seen_urls = set()
        for call in successful:
            # Get the path without query params
            parsed = urlparse(call['url'])
            path = parsed.path
            
            # Skip if we've seen this path before
            if path in seen_urls:
                continue
            seen_urls.add(path)
            
            print(f"\n🔹 {call['method']} {path}")
            print(f"   Status: {call['status']}")
            
            # Show auth header
            if 'authorization' in call['headers']:
                auth = call['headers']['authorization']
                print(f"   🔑 Auth: {auth[:20]}...{auth[-10:] if len(auth) > 30 else ''}")
            
            if call['body']:
                print(f"   📦 Body: {call['body'][:100]}...")
            if call['response_body']:
                print(f"   📬 Response: {call['response_body'][:100]}...")
            print()
        
        print(f"✅ Total unique working endpoints: {len(seen_urls)}")
    else:
        print("❌ No successful API calls found!")
    
    if failed:
        print("\n📋 Failed Endpoints (to avoid):")
        print("-" * 60)
        for call in failed[:5]:
            parsed = urlparse(call['url'])
            print(f"  ❌ {call['method']} {parsed.path} - {call['status']}")
    
    # Extract base URLs
    base_urls = set()
    for call in api_calls:
        parsed = urlparse(call['url'])
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        base_urls.add(base_url)
    
    print()
    print("🌐 Base URLs found:")
    for url in sorted(base_urls):
        print(f"  • {url}")
    
    # Find the most common successful endpoint patterns
    if successful:
        print()
        print("💡 Recommended endpoints to use:")
        patterns = Counter()
        for call in successful:
            parsed = urlparse(call['url'])
            path = parsed.path
            # Get first 3 path segments
            parts = path.split('/')
            if len(parts) >= 3:
                pattern = '/'.join(parts[:3])
                patterns[pattern] += 1
        
        for pattern, count in patterns.most_common(10):
            print(f"  • {pattern} ({count} calls)")
        
        # Also show specific endpoints that look like API calls
        print()
        print("📌 Top 20 API endpoints to use:")
        api_patterns = ['cloudgateway', 'jobapi', 'v1', 'v2', 'services', 'mnjuser']
        endpoint_count = 0
        for call in successful:
            parsed = urlparse(call['url'])
            path = parsed.path
            if any(p in path for p in api_patterns):
                print(f"  • {call['method']} {path}")
                endpoint_count += 1
                if endpoint_count >= 20:
                    break

if __name__ == "__main__":
    har_files = list(Path('.').glob('*.har'))
    
    if not har_files:
        print("No HAR files found")
        exit()
    
    print("Select HAR file to inspect:")
    for i, f in enumerate(har_files, 1):
        size = f.stat().st_size / 1024
        print(f"  {i}. {f.name} ({size:.1f} KB)")
    
    choice = input("\nEnter choice (or press Enter for newest): ").strip()
    
    try:
        if choice:
            idx = int(choice) - 1
        else:
            # Use the newest file
            har_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            idx = 0
        
        if 0 <= idx < len(har_files):
            inspect_har(har_files[idx])
        else:
            print("Invalid choice")
    except ValueError:
        print("Invalid input")
