#!/usr/bin/env python3
"""
Simple token test
"""

import requests
from pathlib import Path

# Load token
token_file = Path('naukri_token.txt')
if not token_file.exists():
    print("❌ No token found")
    exit()

with open(token_file, 'r') as f:
    token = f.read().strip()

print(f"Token: {token[:30]}...")
print()

# Test with homepage
headers = {
    'Authorization': f'Bearer {token}',
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'
}

try:
    response = requests.get('https://www.naukri.com/mnjuser/homepage', headers=headers, timeout=10)
    print(f"Homepage: {response.status_code}")
    
    if response.status_code == 200:
        print("✅ Token is valid")
    else:
        print("❌ Token might be expired")
except Exception as e:
    print(f"Error: {e}")
