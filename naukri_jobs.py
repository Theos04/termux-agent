#!/usr/bin/env python3
"""
Naukri API Client - Simple Working Version
"""

import json
import requests
import base64
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Your token data - copy directly from the debug output
BEARER_TOKEN = "eyJraWQiOiIzIiwidHlwIjoiSldUIiwiYWxnIjoiUlM1MTIifQ.eyJ1ZF9yZXNJZCI6MTk0Njg5NzY2LCJzdWIiOiIyMDc2Mzk4NjYiLCJ1ZF91c2VybmFtZSI6Im1haWx0by5oYXJzaG1laHRhMDRAZ21haWwuY29tIiwidWRfaXNFbWFpbCI6dHJ1ZSwiaXNzIjoiSW5mb0VkZ2UgSW5kaWEgUHZ0LiBMdGQuIiwidXNlckFnZW50IjoiTW96aWxsYS81LjAgKFgxMTsgTGludXggeDg2XzY0KSBBcHBsZVdlYktpdC81MzcuMzYgKEtIVE1MLCBsaWtlIEdlY2tvKSBDaHJvbWUvMTQ5LjAuMC4wIFNhZmFyaS81MzcuMzYiLCJpcEFkcmVzcyI6IjI0MDE6NDkwMDo4OGZiOjZlNzM6NjU4MTo2OGY3OjJhZDI6OTY0NyIsInVkX2lzVGVjaE9wc0xvZ2luIjpmYWxzZSwidXNlcklkIjoyMDc2Mzk4NjYsInN1YlVzZXJUeXBlIjoiIiwidXNlclN0YXRlIjoiQVVUSEVOVElDQVRFRCIsInVkX2lzUGFpZENsaWVudCI6ZmFsc2UsInVkX2VtYWlsVmVyaWZpZWQiOnRydWUsInVzZXJUeXBlIjoiam9ic2Vla2VyIiwic2Vzc2lvblN0YXRUaW1lIjoiMjAyNi0wNy0xNlQwMzo0MjowMCIsInVkX2VtYWlsIjoibWFpbHRvLmhhcnNobWVodGEwNEBnbWFpbC5jb20iLCJ1c2VyUm9sZSI6InVzZXIiLCJleHAiOjE3ODYzNjgxMDQsInRva2VuVHlwZSI6ImFjY2Vzc1Rva2VuIiwiaWF0IjoxNzg2MzY0NTA0LCJqdGkiOiIwY2I4ZmNjY2VlODc0M2MzYTgyOTFhNzJlNTZiYTk5NSIsInBvZElkIjoicHJvZC01YmJjNmJiNTliLWtibjVjIn0.fjl3Bn7-3G6tGtPRMg-bUn_3XtwLGSJJP3XLlU9gtkrtVIoEtJEfHEdNN1zHPDZp6VDofT236THN5ktBnZ7xQIwc5ObwYmwn0dh9YERlU1gga0d-OCB5tWzFvOjBmn09gEb-KUUqP5DHZTDqJ2qAxp2v6eVUi7Uo3RbWIsvXXD-liFKVC2UZ4mibUEeobht_dnOij7-UrZq_iCJ37mGwIMRL5BuB9KzwIzIG8GI0HxKLKsuohE350rvEqg4CcyKntlw6wCm0Qw0p7ObG411ClrlQ-OdLqjMfwF1ypxSB45pLRDbX0L4TPiLabi7ldpQb_HmzUTDLi26JKG7XJHVotQ"

COOKIES = {
    'nauk_at': BEARER_TOKEN,
    'nauk_sid': '0cb8fcccee8743c3a8291a72e56ba995',
    'nauk_rt': '0cb8fcccee8743c3a8291a72e56ba995',
    'nauk_otl': '0cb8fcccee8743c3a8291a72e56ba995',
    'is_login': '1',
    'PHPSESSID': 'hkjips3odbndh506pjfkv67fu9',
    '_ga': 'GA1.1.2042618104.1784153448'
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br',
    'Authorization': f'Bearer {BEARER_TOKEN}',
    'AppId': '105',
    'X-App-Id': '105',
    'SystemId': 'Naukri',
    'X-System-Id': 'Naukri',
    'Origin': 'https://www.naukri.com',
    'Referer': 'https://www.naukri.com/mnjuser/homepage',
    'X-Requested-With': 'XMLHttpRequest',
    'Connection': 'keep-alive'
}


def get_recommended_jobs(limit=30):
    """Get recommended jobs"""
    url = "https://www.naukri.com/jobapi/v2/search/recom-jobs"
    payload = {
        "filterParams": {
            "pageNo": 1,
            "pageSize": limit,
            "searchType": "recom"
        }
    }
    
    try:
        print(f"📤 Fetching recommended jobs (limit: {limit})...")
        
        # Create a session and set headers/cookies
        session = requests.Session()
        session.headers.update(HEADERS)
        session.cookies.update(COOKIES)
        
        response = session.post(url, json=payload)
        
        print(f"Status Code: {response.status_code}")
        print(f"Content-Type: {response.headers.get('Content-Type')}")
        
        if response.status_code == 200:
            data = response.json()
            jobs = data.get('jobDetails', [])
            total = data.get('noOfJobs', 0)
            print(f"✅ Found {total} recommended jobs (showing {len(jobs)})")
            return data
        else:
            print(f"❌ Failed: {response.status_code}")
            print(f"Response: {response.text[:500]}")
            return {'error': f'Status {response.status_code}', 'jobDetails': []}
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return {'error': str(e), 'jobDetails': []}


def get_dashboard():
    """Get dashboard data"""
    url = "https://www.naukri.com/cloudgateway-mynaukri/resman-aggregator-services/v1/users/self/dashboard"
    
    try:
        print("📤 Fetching dashboard...")
        
        session = requests.Session()
        session.headers.update(HEADERS)
        session.cookies.update(COOKIES)
        
        response = session.get(url)
        
        if response.status_code == 200:
            data = response.json()
            print("✅ Dashboard retrieved")
            return data
        else:
            print(f"❌ Failed: {response.status_code}")
            return {'error': f'Status {response.status_code}'}
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return {'error': str(e)}


def print_jobs(jobs, max_display=15):
    """Print job listings"""
    if not jobs:
        print("\n❌ No jobs found")
        return
    
    print(f"\n{'='*80}")
    print(f"📋 JOB LISTINGS ({len(jobs)} jobs found)")
    print(f"{'='*80}")
    
    for i, job in enumerate(jobs[:max_display], 1):
        title = job.get('title', 'N/A')
        company = job.get('companyName', 'N/A')
        job_id = job.get('jobId', 'N/A')
        
        # Extract details from placeholders
        exp = "N/A"
        loc = "N/A"
        sal = "Not specified"
        
        for placeholder in job.get('placeholders', []):
            ptype = placeholder.get('type', '')
            label = placeholder.get('label', '')
            if ptype == 'experience':
                exp = label
            elif ptype == 'salary':
                sal = label
            elif ptype == 'location':
                loc = label
        
        tags = job.get('tagsAndSkills', '').split(',')[:3]
        is_walkin = job.get('walkinJob', False)
        
        print(f"\n{i}. 🏢 {title}")
        print(f"   Company: {company}")
        print(f"   📍 Location: {loc}")
        print(f"   💼 Experience: {exp}")
        print(f"   💰 Salary: {sal}")
        print(f"   🔗 Job ID: {job_id}")
        if is_walkin:
            print(f"   🚶 Walk-in: Yes")
        if tags:
            print(f"   🏷️  Skills: {', '.join(tags)}")
        print(f"   {'-'*60}")
    
    if len(jobs) > max_display:
        print(f"\n   ... and {len(jobs) - max_display} more jobs")


def main():
    print("="*80)
    print("🔐 NAUKRI API - JOB FETCHER (SIMPLE VERSION)")
    print("="*80)
    
    # Show user info from token
    try:
        parts = BEARER_TOKEN.split('.')
        if len(parts) == 3:
            payload = json.loads(base64.urlsafe_b64decode(parts[1] + '==').decode('utf-8'))
            print(f"\n👤 Authenticated as:")
            print(f"   User ID: {payload.get('userId')}")
            print(f"   Email: {payload.get('ud_email')}")
            print(f"   Token expires: {datetime.fromtimestamp(payload.get('exp', 0)).isoformat()}")
    except:
        pass
    
    print("\n" + "="*80)
    print("📡 FETCHING JOBS")
    print("="*80)
    
    # Get recommended jobs
    print("\n1️⃣ GETTING RECOMMENDED JOBS...")
    result = get_recommended_jobs(limit=30)
    
    if 'jobDetails' in result and result['jobDetails']:
        jobs = result['jobDetails']
        total = result.get('noOfJobs', 0)
        print_jobs(jobs, max_display=15)
        
        # Save to file
        with open('recommended_jobs.json', 'w') as f:
            json.dump(result, f, indent=2)
        print(f"\n💾 Full job data saved to: recommended_jobs.json")
        print(f"   Total available: {total} jobs")
    else:
        print(f"❌ {result.get('error', 'No jobs found')}")
    
    # Get dashboard
    print("\n\n2️⃣ FETCHING DASHBOARD SUMMARY...")
    dashboard = get_dashboard()
    if 'error' not in dashboard and 'dashBoard' in dashboard:
        dash = dashboard['dashBoard']
        print(f"✅ Dashboard retrieved")
        print(f"   Name: {dash.get('name', 'N/A')}")
        print(f"   Profile Score: {dash.get('pc', 0)}%")
        print(f"   Profile Views: {dash.get('profileViewCount', 0)}")
        print(f"   Experience: {dash.get('rawTotalExperience', 'N/A')} years")
        print(f"   Current CTC: {dash.get('rawCtc', 'N/A')} LPA")
    else:
        print(f"❌ {dashboard.get('error', 'Failed to fetch dashboard')}")
    
    print("\n" + "="*80)
    print("✅ COMPLETED")
    print("="*80)


if __name__ == "__main__":
    main()
