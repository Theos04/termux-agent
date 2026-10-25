#!/usr/bin/env python3
"""
Investigate what the UUID actually represents
Is it a user account, guest session, cart ID, or something else?
"""

import json
import requests
import re
import time
from pathlib import Path

def main():
    print("=" * 70)
    print("🔍 INVESTIGATE UUID MEANING")
    print("=" * 70)
    
    # Load HAR
    har_file = "agoda_2.json"
    with open(har_file, 'r') as f:
        data = json.load(f)
    
    entries = data.get('log', {}).get('entries', [])
    
    # Get the new UUID from our test
    test_uuid = "6138dd34-82df-4a44-b74e-95d8fc9ef82d"
    
    print(f"\n📌 Testing UUID: {test_uuid}")
    
    # Test 1: Check if UUID appears in the HAR responses
    print("\n" + "=" * 70)
    print("🔬 TEST 1: UUID appears in HAR responses?")
    print("=" * 70)
    
    uuid_locations = []
    for entry in entries:
        response = entry.get('response', {})
        response_text = ''
        try:
            if response.get('content', {}).get('text'):
                response_text = response.get('content', {}).get('text')
            elif response.get('content', {}).get('mimeType') == 'application/json':
                # Try to get from body
                pass
        except:
            pass
        
        # Check if UUID appears in response
        if test_uuid in str(response):
            url = entry.get('request', {}).get('url', '')
            uuid_locations.append({
                'url': url,
                'context': 'response'
            })
    
    if uuid_locations:
        print(f"✅ UUID found in {len(uuid_locations)} responses:")
        for loc in uuid_locations[:5]:
            print(f"   - {loc['url'][:80]}")
    else:
        print("❌ UUID not found in any HAR responses")
    
    # Test 2: Check if UUID is in the booking flow
    print("\n" + "=" * 70)
    print("🔬 TEST 2: UUID in booking flow?")
    print("=" * 70)
    
    booking_urls = []
    for entry in entries:
        url = entry.get('request', {}).get('url', '')
        if 'book' in url or 'booking' in url:
            if test_uuid in str(entry) or 'uid' in url:
                booking_urls.append(url[:100])
    
    if booking_urls:
        print(f"✅ UUID-related booking URLs found: {len(booking_urls)}")
        for url in booking_urls[:5]:
            print(f"   - {url}")
    else:
        print("❌ No UUID in booking URLs")
    
    # Test 3: Check if UUID survives page refresh
    print("\n" + "=" * 70)
    print("🔬 TEST 3: Does UUID survive page refresh?")
    print("=" * 70)
    
    session = requests.Session()
    
    # Set the UUID cookie
    session.cookies.set('agoda.user.03', f'UserId={test_uuid}')
    
    # Add other cookies from HAR
    for entry in entries:
        for h in entry.get('request', {}).get('headers', []):
            if isinstance(h, dict) and h.get('name', '').lower() == 'cookie':
                cookie_str = h.get('value', '')
                for cookie in cookie_str.split('; '):
                    if '=' in cookie and 'agoda.user.03' not in cookie:
                        key, val = cookie.split('=', 1)
                        session.cookies.set(key, val)
    
    # First request with UUID
    resp1 = session.get("https://www.agoda.com/", timeout=10)
    cookie1 = session.cookies.get('agoda.user.03', '')
    
    print(f"   Cookie after first request: {cookie1[:50]}...")
    
    # Second request (simulate page refresh)
    time.sleep(1)
    resp2 = session.get("https://www.agoda.com/", timeout=10)
    cookie2 = session.cookies.get('agoda.user.03', '')
    
    print(f"   Cookie after second request: {cookie2[:50]}...")
    
    if cookie1 == cookie2:
        print("   ✅ UUID persisted across requests")
    else:
        print("   🔄 UUID changed - likely ephemeral")
    
    # Test 4: Check if UUID changes on new session
    print("\n" + "=" * 70)
    print("🔬 TEST 4: Does UUID change with new session?")
    print("=" * 70)
    
    # Create a new session without any cookies
    new_session = requests.Session()
    resp_new = new_session.get("https://www.agoda.com/", timeout=10)
    new_cookie = new_session.cookies.get('agoda.user.03', '')
    
    print(f"   New session cookie: {new_cookie[:50] if new_cookie else 'None'}...")
    
    if new_cookie and new_cookie != cookie1:
        print("   🔄 UUID changed - suggests session ID not account ID")
    else:
        print("   ✅ UUID same - might be account-based")
    
    # Test 5: Check for UUID in JavaScript/HTML
    print("\n" + "=" * 70)
    print("🔬 TEST 5: UUID in page source?")
    print("=" * 70)
    
    try:
        resp = session.get("https://www.agoda.com/", timeout=10)
        if resp.status_code == 200:
            # Look for UUID patterns
            uuids = re.findall(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', resp.text, re.I)
            unique_uuids = set(uuids)
            print(f"   Found {len(unique_uuids)} unique UUIDs in page source")
            print(f"   Our UUID present: {test_uuid in resp.text}")
            
            # Look for the UUID in specific contexts
            contexts = {
                'userId': re.search(r'userId[:\s]+["\']?' + test_uuid, resp.text, re.I),
                'user_id': re.search(r'user_id[:\s]+["\']?' + test_uuid, resp.text, re.I),
                'session': re.search(r'session[:\s]+["\']?' + test_uuid, resp.text, re.I),
                'cart': re.search(r'cart[:\s]+["\']?' + test_uuid, resp.text, re.I),
                'visitor': re.search(r'visitor[:\s]+["\']?' + test_uuid, resp.text, re.I),
                'analytics': re.search(r'analytics[:\s]+["\']?' + test_uuid, resp.text, re.I),
            }
            
            print("\n   UUID context in page source:")
            for context, found in contexts.items():
                if found:
                    print(f"      ✅ {context}: Found")
                else:
                    print(f"      ❌ {context}: Not found")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    # Test 6: Check if UUID is in API responses
    print("\n" + "=" * 70)
    print("🔬 TEST 6: UUID in API responses?")
    print("=" * 70)
    
    try:
        # Try the member API with the UUID cookie
        api_headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36',
        }
        resp = session.get("https://www.agoda.com/api/gw/member/details", headers=api_headers, timeout=10)
        print(f"   Member API status: {resp.status_code}")
        if resp.status_code == 200:
            try:
                data = resp.json()
                print(f"   ✅ API response: {json.dumps(data, indent=2)[:200]}...")
                if 'userId' in data:
                    print(f"   🆔 API UserId: {data.get('userId')}")
                    if data.get('userId') == test_uuid:
                        print("   ✅ UUID matches API userId!")
                    else:
                        print(f"   🔄 UUID different from API userId")
            except:
                print(f"   Response: {resp.text[:200]}")
        else:
            print(f"   ❌ API returned {resp.status_code}")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    print("\n" + "=" * 70)
    print("📊 SUMMARY")
    print("=" * 70)
    
    print("""
    UUID Behavior Analysis:
    
    1. Does it persist across requests?
    2. Does it change with new sessions?
    3. Does it appear in page source?
    4. Is it referenced as userId or session?
    5. Does the API recognize it?
    
    Interpretation:
    - If UUID persists and API recognizes it as userId → Likely account
    - If UUID changes per session → Likely guest/session ID
    - If UUID appears as analytics/tracking → Likely telemetry
    - If UUID appears in booking context → Likely booking/cart ID
    """)

if __name__ == "__main__":
    main()
