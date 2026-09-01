#!/usr/bin/env python3
"""
Debug - Get Raw Response from Naukri API
"""

import requests
import json
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Your token
BEARER_TOKEN = "eyJraWQiOiIzIiwidHlwIjoiSldUIiwiYWxnIjoiUlM1MTIifQ.eyJ1ZF9yZXNJZCI6MTk0Njg5NzY2LCJzdWIiOiIyMDc2Mzk4NjYiLCJ1ZF91c2VybmFtZSI6Im1haWx0by5oYXJzaG1laHRhMDRAZ21haWwuY29tIiwidWRfaXNFbWFpbCI6dHJ1ZSwiaXNzIjoiSW5mb0VkZ2UgSW5kaWEgUHZ0LiBMdGQuIiwidXNlckFnZW50IjoiTW96aWxsYS81LjAgKFgxMTsgTGludXggeDg2XzY0KSBBcHBsZVdlYktpdC81MzcuMzYgKEtIVE1MLCBsaWtlIEdlY2tvKSBDaHJvbWUvMTQ5LjAuMC4wIFNhZmFyaS81MzcuMzYiLCJpcEFkcmVzcyI6IjI0MDE6NDkwMDo4OGZiOjZlNzM6NjU4MTo2OGY3OjJhZDI6OTY0NyIsInVkX2lzVGVjaE9wc0xvZ2luIjpmYWxzZSwidXNlcklkIjoyMDc2Mzk4NjYsInN1YlVzZXJUeXBlIjoiIiwidXNlclN0YXRlIjoiQVVUSEVOVElDQVRFRCIsInVkX2lzUGFpZENsaWVudCI6ZmFsc2UsInVkX2VtYWlsVmVyaWZpZWQiOnRydWUsInVzZXJUeXBlIjoiam9ic2Vla2VyIiwic2Vzc2lvblN0YXRUaW1lIjoiMjAyNi0wNy0xNlQwMzo0MjowMCIsInVkX2VtYWlsIjoibWFpbHRvLmhhcnNobWVodGEwNEBnbWFpbC5jb20iLCJ1c2VyUm9sZSI6InVzZXIiLCJleHAiOjE3ODYzNjgxMDQsInRva2VuVHlwZSI6ImFjY2Vzc1Rva2VuIiwiaWF0IjoxNzg2MzY0NTA0LCJqdGkiOiIwY2I4ZmNjY2VlODc0M2MzYTgyOTFhNzJlNTZiYTk5NSIsInBvZElkIjoicHJvZC01YmJjNmJiNTliLWtibjVjIn0.fjl3Bn7-3G6tGtPRMg-bUn_3XtwLGSJJP3XLlU9gtkrtVIoEtJEfHEdNN1zHPDZp6VDofT236THN5ktBnZ7xQIwc5ObwYmwn0dh9YERlU1gga0d-OCB5tWzFvOjBmn09gEb-KUUqP5DHZTDqJ2qAxp2v6eVUi7Uo3RbWIsvXXD-liFKVC2UZ4mibUEeobht_dnOij7-UrZq_iCJ37mGwIMRL5BuB9KzwIzIG8GI0HxKLKsuohE350rvEqg4CcyKntlw6wCm0Qw0p7ObG411ClrlQ-OdLqjMfwF1ypxSB45pLRDbX0L4TPiLabi7ldpQb_HmzUTDLi26JKG7XJHVotQ"

def debug_request():
    print("="*80)
    print("🔍 DEBUG RAW RESPONSE")
    print("="*80)
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'en-US,en;q=0.9',
        'Authorization': f'Bearer {BEARER_TOKEN}',
        'AppId': '105',
        'X-App-Id': '105',
        'SystemId': 'Naukri',
        'X-System-Id': 'Naukri',
        'Origin': 'https://www.naukri.com',
        'Referer': 'https://www.naukri.com/mnjuser/homepage',
        'Connection': 'keep-alive'
    }
    
    cookies = {
        'nauk_at': BEARER_TOKEN,
        'nauk_sid': '0cb8fcccee8743c3a8291a72e56ba995',
        'nauk_rt': '0cb8fcccee8743c3a8291a72e56ba995',
        'nauk_otl': '0cb8fcccee8743c3a8291a72e56ba995',
        'is_login': '1'
    }
    
    url = "https://www.naukri.com/jobapi/v2/search/recom-jobs"
    payload = {"filterParams": {"pageNo": 1, "pageSize": 10, "searchType": "recom"}}
    
    print(f"\n📡 URL: {url}")
    print(f"📡 Method: POST")
    print(f"📡 Payload: {json.dumps(payload, indent=2)}")
    
    try:
        response = requests.post(url, json=payload, headers=headers, cookies=cookies)
        
        print(f"\n📊 Status Code: {response.status_code}")
        print(f"📊 Headers:")
        for key, value in response.headers.items():
            print(f"   {key}: {value}")
        
        print(f"\n📄 Raw Response:")
        print("-"*60)
        print(response.text)
        print("-"*60)
        
        # Try to parse as JSON
        try:
            json_data = response.json()
            print(f"\n✅ Valid JSON Response")
            print(f"Keys: {list(json_data.keys()) if isinstance(json_data, dict) else 'Not a dict'}")
            if 'jobDetails' in json_data:
                print(f"Number of jobs: {len(json_data['jobDetails'])}")
        except json.JSONDecodeError as e:
            print(f"\n❌ Not valid JSON: {e}")
            print(f"First 500 chars: {response.text[:500]}")
            
    except Exception as e:
        print(f"\n❌ Error: {e}")
    
    print("\n" + "="*80)

if __name__ == "__main__":
    debug_request()
