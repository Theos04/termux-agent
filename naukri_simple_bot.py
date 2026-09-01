#!/usr/bin/env python3
"""
Simple Naukri bot with correct headers
"""

import json
import requests
from pathlib import Path

def main():
    print("🚀 Simple Naukri Bot")
    print("="*40)
    
    # Load token
    token_file = Path('naukri_token.txt')
    if not token_file.exists():
        print("❌ No token found. Run: python extract_token_network.py")
        return
    
    with open(token_file, 'r') as f:
        token = f.read().strip()
    
    print(f"✅ Token loaded: {token[:30]}...")
    
    # Headers from HAR analysis
    headers = {
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
    }
    
    # Try to find the correct AppId and SystemId from the HAR
    # These are common values used by Naukri
    # Try different combinations
    app_ids = ['109', '111', '112', '113', '114']
    system_ids = ['109', '111', '112', '113', '114']
    
    print("\n🔍 Testing different AppId/SystemId combinations...")
    print()
    
    for app_id in app_ids[:2]:
        for system_id in system_ids[:2]:
            headers['AppId'] = app_id
            headers['SystemId'] = system_id
            
            print(f"Testing AppId={app_id}, SystemId={system_id}")
            
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
            
            try:
                response = requests.post(
                    'https://www.naukri.com/jobapi/v2/search/recom-jobs',
                    headers=headers,
                    json=payload,
                    timeout=10
                )
                
                print(f"  Status: {response.status_code}")
                
                if response.status_code == 200:
                    print("  ✅ Success!")
                    data = response.json()
                    jobs = data.get('data', {}).get('jobs', [])
                    print(f"  Found {len(jobs)} jobs")
                    break
                elif response.status_code == 400:
                    print("  ❌ Bad Request")
                elif response.status_code == 401:
                    print("  ❌ Unauthorized")
                else:
                    print(f"  ❌ Error: {response.status_code}")
                    if response.text:
                        print(f"  Response: {response.text[:100]}")
            except Exception as e:
                print(f"  ❌ Error: {e}")
            
            print()

if __name__ == "__main__":
    main()
