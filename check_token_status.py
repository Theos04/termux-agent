#!/usr/bin/env python3
"""
Check if the token is valid and get a new one if needed
"""

import json
import requests
from pathlib import Path

def check_token(token):
    """Check if token is valid"""
    print("🔍 Checking token validity...")
    print()
    
    # Try multiple endpoints with different approaches
    tests = [
        {
            'url': 'https://www.naukri.com/mnjuser/homepage',
            'method': 'GET',
            'desc': 'Homepage'
        },
        {
            'url': 'https://www.naukri.com/cloudgateway-mynaukri/resman-aggregator-services/v2/users/self',
            'method': 'GET',
            'desc': 'Profile API'
        },
        {
            'url': 'https://www.naukri.com/jobapi/v2/search/recom-jobs',
            'method': 'POST',
            'desc': 'Search API',
            'data': {
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
        }
    ]
    
    headers = {
        'Authorization': f'Bearer {token}',
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'en-US,en;q=0.9',
        'Content-Type': 'application/json',
        'Origin': 'https://www.naukri.com',
        'Referer': 'https://www.naukri.com/'
    }
    
    valid = False
    
    for test in tests:
        try:
            if test['method'] == 'GET':
                response = requests.get(test['url'], headers=headers, timeout=10)
            else:
                response = requests.post(test['url'], headers=headers, json=test.get('data', {}), timeout=10)
            
            status = response.status_code
            print(f"📡 {test['desc']} ({test['method']}):")
            print(f"   URL: {test['url']}")
            print(f"   Status: {status}")
            
            if status == 200:
                print(f"   ✅ Valid!")
                valid = True
                try:
                    data = response.json()
                    print(f"   Response preview: {json.dumps(data, indent=2)[:200]}...")
                except:
                    pass
            elif status == 400:
                print(f"   ❌ Bad Request - The request format is wrong but token might be valid")
                # Still could be valid, just wrong format
                valid = True
            elif status == 401:
                print(f"   ❌ Unauthorized - Token is expired or invalid")
            elif status == 403:
                print(f"   ❌ Forbidden - Token doesn't have permission")
            else:
                print(f"   ❌ Error: {status}")
            print()
            
        except Exception as e:
            print(f"   ❌ Error: {e}")
            print()
    
    return valid

def get_new_token():
    """Guide user to get a new token"""
    print("\n" + "="*60)
    print("🔄 Getting a new token...")
    print("="*60)
    print()
    print("Option 1: Extract from Chrome (recommended)")
    print("  Run: python extract_token_network.py")
    print()
    print("Option 2: Extract from HAR file")
    print("  Run: python extract_token_from_har.py")
    print()
    print("Option 3: Manual entry")
    print("  Run: python get_token_manual.py")
    print()
    
    choice = input("Which option? (1/2/3): ").strip()
    
    if choice == '1':
        import subprocess
        subprocess.run(['python', 'extract_token_network.py'])
    elif choice == '2':
        import subprocess
        subprocess.run(['python', 'extract_token_from_har.py'])
    elif choice == '3':
        import subprocess
        subprocess.run(['python', 'get_token_manual.py'])
    else:
        print("Invalid choice")

if __name__ == "__main__":
    # Load existing token
    token_file = Path('naukri_token.txt')
    if not token_file.exists():
        print("❌ No token file found. Getting new token...")
        get_new_token()
    else:
        with open(token_file, 'r') as f:
            token = f.read().strip()
        
        print(f"📂 Loaded token: {token[:30]}...")
        print()
        
        if check_token(token):
            print("✅ Token is valid!")
        else:
            print("⚠️ Token might be expired. Getting new token...")
            # Backup old token
            backup_file = Path('naukri_token.txt.bak')
            if not backup_file.exists():
                token_file.rename(backup_file)
                print(f"💾 Old token backed up to {backup_file}")
            get_new_token()
