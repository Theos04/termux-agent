#!/usr/bin/env python3
"""
Investigate if the new session is a real account or anonymous
"""

import json
import requests
import urllib.parse
import re
from pathlib import Path

def main():
    print("=" * 70)
    print("🔍 INVESTIGATE NEW SESSION")
    print("=" * 70)
    
    # Load HAR to get original cookies
    har_file = "agoda_2.json"
    with open(har_file, 'r') as f:
        data = json.load(f)
    
    entries = data.get('log', {}).get('entries', [])
    
    # Get original cookie from HAR
    original_cookie = None
    for entry in entries:
        for h in entry.get('request', {}).get('headers', []):
            if isinstance(h, dict) and h.get('name', '').lower() == 'cookie':
                cookie_str = h.get('value', '')
                for cookie in cookie_str.split('; '):
                    if 'agoda.user.03' in cookie:
                        original_cookie = cookie
                        break
            if original_cookie:
                break
        if original_cookie:
            break
    
    print(f"\n📌 Original cookie: {original_cookie}")
    
    # Use the new session to test various endpoints
    session = requests.Session()
    
    # Set the new cookie we got from the test
    new_cookie = "agoda.user.03=UserId=6138dd34-82df-4a44-b74e-95d8fc9ef82d"
    session.cookies.set('agoda.user.03', 'UserId=6138dd34-82df-4a44-b74e-95d8fc9ef82d')
    
    # Add other cookies from HAR
    for entry in entries:
        for h in entry.get('request', {}).get('headers', []):
            if isinstance(h, dict) and h.get('name', '').lower() == 'cookie':
                cookie_str = h.get('value', '')
                for cookie in cookie_str.split('; '):
                    if '=' in cookie and 'agoda.user.03' not in cookie:
                        key, val = cookie.split('=', 1)
                        session.cookies.set(key, val)
    
    print("\n" + "=" * 70)
    print("🔬 TESTING NEW SESSION CAPABILITIES")
    print("=" * 70)
    
    # Test 1: Check if we can access the user's profile
    print("\n📌 Test 1: Access Profile Page")
    try:
        resp = session.get("https://www.agoda.com/account/profile.html", timeout=10, allow_redirects=False)
        print(f"   Status: {resp.status_code}")
        if resp.status_code == 200:
            # Check for user data in the page
            if 'profile' in resp.text.lower() or 'account' in resp.text.lower():
                print("   ✅ Profile page accessed!")
                # Try to find email or name
                email_match = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', resp.text)
                if email_match:
                    print(f"   📧 Found email: {email_match.group()}")
                name_match = re.search(r'([A-Z][a-z]+)\s+([A-Z][a-z]+)', resp.text)
                if name_match:
                    print(f"   👤 Found name: {name_match.group()}")
            else:
                print("   ⚠️ Profile page loaded but no user data visible")
        elif resp.status_code in [301, 302, 303, 307, 308]:
            print(f"   ⚠️ Redirected to: {resp.headers.get('Location', '')}")
        else:
            print(f"   ❌ Failed (status {resp.status_code})")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    # Test 2: Check if we can see bookings
    print("\n📌 Test 2: Access Bookings Page")
    try:
        resp = session.get("https://www.agoda.com/trips", timeout=10, allow_redirects=False)
        print(f"   Status: {resp.status_code}")
        if resp.status_code == 200:
            if 'booking' in resp.text.lower() or 'trip' in resp.text.lower():
                print("   ✅ Bookings page accessed!")
            else:
                print("   ⚠️ Bookings page loaded but no data visible")
        elif resp.status_code in [301, 302, 303, 307, 308]:
            print(f"   ⚠️ Redirected to: {resp.headers.get('Location', '')}")
            # Follow redirect
            follow = session.get(resp.headers.get('Location'), timeout=10)
            if follow.status_code == 200:
                if 'booking' in follow.text.lower() or 'trip' in follow.text.lower():
                    print("   ✅ Bookings page accessed after redirect!")
                else:
                    print("   ⚠️ Redirect page loaded but no bookings data")
        else:
            print(f"   ❌ Failed (status {resp.status_code})")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    # Test 3: Check if the new UserId is in the page
    print("\n📌 Test 3: Look for UserId in page content")
    try:
        resp = session.get("https://www.agoda.com/", timeout=10)
        if resp.status_code == 200:
            # Look for the new UserId in the page
            new_uid = "6138dd34-82df-4a44-b74e-95d8fc9ef82d"
            if new_uid in resp.text:
                print(f"   ✅ Found new UserId in page: {new_uid}")
            else:
                print(f"   ❌ New UserId not found in page")
            
            # Look for any user identifier
            uid_matches = re.findall(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', resp.text)
            if uid_matches:
                print(f"   Found UUIDs in page: {set(uid_matches)}")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    # Test 4: Try accessing the API directly with the new cookie
    print("\n📌 Test 4: Direct API access with new cookie")
    try:
        api_headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36',
        }
        resp = session.get("https://www.agoda.com/api/gw/member/details", headers=api_headers, timeout=10)
        print(f"   Status: {resp.status_code}")
        if resp.status_code == 200:
            try:
                data = resp.json()
                print(f"   ✅ API responded with data!")
                if 'email' in data:
                    print(f"   📧 Email: {data.get('email')}")
                if 'name' in data:
                    print(f"   👤 Name: {data.get('name')}")
                if 'userId' in data:
                    print(f"   🆔 UserId from API: {data.get('userId')}")
            except:
                print(f"   Response: {resp.text[:200]}")
        else:
            print(f"   ❌ API access failed (status {resp.status_code})")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    print("\n" + "=" * 70)
    print("📊 SUMMARY")
    print("=" * 70)
    print("""
    ✅ New session created with UserId: 6138dd34-82df-4a44-b74e-95d8fc9ef82d
    ✅ Modified request accepted (200)
    ✅ Cookie changed from original
    
    Questions to answer:
    1. Is this a real user account or an anonymous session?
    2. Can we access real user data with this cookie?
    3. Does the UserId persist across requests?
    
    The 302 redirect to pagenotfound.html suggests the session might be invalid
    or the profile page might not exist for this UserId.
    """)

if __name__ == "__main__":
    main()
