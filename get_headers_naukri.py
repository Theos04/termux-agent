#!/usr/bin/env python3
"""
Extract AppId and SystemId from HAR capture
"""

import json
import re
from urllib.parse import urlparse, parse_qs

def extract_headers_from_har(har_file):
    """Extract required headers from HAR file"""
    
    with open(har_file, 'r') as f:
        har_data = json.load(f)
    
    required_headers = {
        'appid': [],
        'systemid': [],
        'x-app-id': [],
        'x-system-id': [],
        'app-id': [],
        'system-id': []
    }
    
    # Look for headers in all entries
    for entry in har_data.get('log', {}).get('entries', []):
        request = entry.get('request', {})
        headers = request.get('headers', {})
        
        # If headers is a list (HAR format), convert to dict
        if isinstance(headers, list):
            headers_dict = {}
            for h in headers:
                if isinstance(h, dict):
                    headers_dict[h.get('name', '').lower()] = h.get('value', '')
            headers = headers_dict
        
        # Check for required headers (case insensitive)
        for header_name, header_value in headers.items():
            header_lower = header_name.lower()
            
            if 'appid' in header_lower or 'app-id' in header_lower:
                if header_value not in required_headers['appid']:
                    required_headers['appid'].append(header_value)
                if header_value not in required_headers['x-app-id']:
                    required_headers['x-app-id'].append(header_value)
                    
            if 'systemid' in header_lower or 'system-id' in header_lower:
                if header_value not in required_headers['systemid']:
                    required_headers['systemid'].append(header_value)
                if header_value not in required_headers['x-system-id']:
                    required_headers['x-system-id'].append(header_value)
        
        # Also check request URLs for these parameters
        url = request.get('url', '')
        if url:
            parsed = urlparse(url)
            params = parse_qs(parsed.query)
            for param, values in params.items():
                param_lower = param.lower()
                if 'appid' in param_lower:
                    required_headers['appid'].extend(values)
                if 'systemid' in param_lower:
                    required_headers['systemid'].extend(values)
    
    # Clean up
    for key in required_headers:
        required_headers[key] = list(set(required_headers[key]))
    
    return required_headers

def main():
    print("="*80)
    print("🔍 EXTRACTING REQUIRED HEADERS FROM HAR")
    print("="*80)
    
    # Use your HAR file
    har_file = 'capture.har'
    
    try:
        headers = extract_headers_from_har(har_file)
        
        print(f"\n📋 Found headers in {har_file}:")
        for key, values in headers.items():
            if values:
                print(f"\n  {key}:")
                for value in values:
                    print(f"    - {value}")
            else:
                print(f"\n  {key}: NOT FOUND")
        
        # If no headers found, try to get from other captured requests
        if not any(headers.values()):
            print("\n⚠️ No AppId/SystemId headers found in HAR.")
            print("   These might be sent as query parameters or in specific requests.")
            
            # Search for any request containing appid or systemid
            with open(har_file, 'r') as f:
                har_data = json.load(f)
            
            print("\n🔎 Searching for appid/systemid in all request data...")
            for entry in har_data.get('log', {}).get('entries', []):
                request = entry.get('request', {})
                url = request.get('url', '')
                if 'appid' in url.lower() or 'systemid' in url.lower():
                    print(f"\n  Found in URL: {url[:100]}")
                
                post_data = request.get('postData', {})
                if post_data:
                    text = post_data.get('text', '')
                    if text and ('appid' in text.lower() or 'systemid' in text.lower()):
                        print(f"\n  Found in POST data: {text[:200]}")
        
        # Generate the complete headers for API calls
        print("\n" + "="*80)
        print("📝 HEADERS FOR API CALLS")
        print("="*80)
        
        # Try to determine the correct header names
        app_id = None
        system_id = None
        
        for key, values in headers.items():
            if values:
                if key in ['appid', 'x-app-id'] and not app_id:
                    app_id = values[0]
                if key in ['systemid', 'x-system-id'] and not system_id:
                    system_id = values[0]
        
        if app_id and system_id:
            print(f"\n✅ Found required headers:")
            print(f"   AppId: {app_id}")
            print(f"   SystemId: {system_id}")
            print("\n📌 Use these headers in your API client:")
            print(f"""
headers = {{
    'Authorization': 'Bearer YOUR_TOKEN',
    'AppId': '{app_id}',
    'SystemId': '{system_id}',
    'X-App-Id': '{app_id}',
    'X-System-Id': '{system_id}',
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36',
    'Accept': 'application/json',
    'Origin': 'https://www.naukri.com',
    'Referer': 'https://www.naukri.com/mnjuser/homepage'
}}
""")
        else:
            print("\n❌ Could not determine AppId and SystemId from HAR.")
            print("   You may need to:")
            print("   1. Open Chrome DevTools")
            print("   2. Look for API requests with these headers")
            print("   3. Copy the AppId and SystemId values")
    
    except FileNotFoundError:
        print(f"❌ HAR file '{har_file}' not found!")
        print("   Please run the CDP capture first to generate capture.har")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()
