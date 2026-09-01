#!/usr/bin/env python3
"""
Test search with cookies from the session
"""

import json
import requests
from pathlib import Path

# Load token
token_file = Path('naukri_token.txt')
if not token_file.exists():
    print("❌ No token found")
    exit()

with open(token_file, 'r') as f:
    token = f.read().strip()

# Create a session to maintain cookies
session = requests.Session()

# Add headers
session.headers.update({
    'Authorization': f'Bearer {token}',
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Content-Type': 'application/json',
    'Origin': 'https://www.naukri.com',
    'Referer': 'https://www.naukri.com/mnjuser/homepage',
    'Sec-Ch-Ua': '"Chromium";v="149", "Not)A;Brand";v="24"',
    'Sec-Ch-Ua-Mobile': '?0',
    'Sec-Ch-Ua-Platform': '"Linux"',
    'Sec-Fetch-Dest': 'empty',
    'Sec-Fetch-Mode': 'cors',
    'Sec-Fetch-Site': 'same-origin'
})

# First, visit the homepage to get cookies
print("🌐 Visiting homepage to get cookies...")
homepage_response = session.get('https://www.naukri.com/mnjuser/homepage')
print(f"Status: {homepage_response.status_code}")
print(f"Cookies: {session.cookies.get_dict()}")

# Now try the search with cookies
payload = {
    "clusterId": "",
    "src": "recommClusterApi",
    "clusterSplitDate": {
        "apply": "2026-02-08 14:46:30",
        "preference": "2026-02-08 14:47:46",
        "profile": "2026-02-08 14:47:28",
        "similar_jobs": "2026-02-08 14:47:46"
    },
    "searches": [
        {
            "keywords": "python developer",
            "location": ""
        }
    ]
}

print("\n🔍 Testing search with cookies...")
response = session.post(
    'https://www.naukri.com/jobapi/v2/search/recom-jobs',
    json=payload
)

print(f"Status: {response.status_code}")
print(f"Response Headers: {dict(response.headers)}")
print()

if response.status_code == 200:
    print("✅ Success!")
    data = response.json()
    print(f"Response: {json.dumps(data, indent=2)[:500]}...")
elif response.status_code == 400:
    print("❌ Bad Request")
    print(f"Request Headers: {dict(session.headers)}")
    print(f"Response body: {response.text[:500]}")
elif response.status_code == 401:
    print("❌ Unauthorized - Token expired")
else:
    print(f"❌ Error: {response.status_code}")
    print(f"Response: {response.text[:500]}")
