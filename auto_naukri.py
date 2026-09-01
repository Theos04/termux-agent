#!/usr/bin/env python3
"""
Naukri Auto Job Fetcher - Fixed with proper encoding handling
"""

import json
import requests
import base64
import time
import sys
import os
import gzip
from datetime import datetime
import logging

# Import CDP capturer
from har2api.capture.cdp_capturer import CDPCapturer

# Disable CDP debug logging
logging.getLogger('har2api').setLevel(logging.WARNING)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class NaukriAutoFetcher:
    """Automatically captures tokens and fetches jobs from Naukri"""
    
    def __init__(self, port=9260, capture_duration=45):
        self.port = port
        self.capture_duration = capture_duration
        self.tokens = None
        self.session = None
        
    def capture_tokens(self):
        """Capture fresh tokens from Chrome with page reload"""
        print("\n" + "="*80)
        print("🔄 CAPTURING FRESH TOKENS FROM CHROME")
        print("="*80)
        print(f"\n⏳ Capturing for {self.capture_duration} seconds...")
        print("   ✅ You're logged into Naukri.com")
        print("   🔄 The page will be reloaded to capture fresh tokens")
        print("   ⏳ Waiting for authenticated API calls to complete...")
        
        try:
            capturer = CDPCapturer(port=self.port)
            
            tabs = capturer.get_tabs()
            if not tabs:
                print("❌ No Chrome tabs found.")
                return False
            
            connected = False
            for tab in tabs:
                if tab.get('type') == 'page':
                    print(f"   Connecting to: {tab.get('title', 'Unknown')[:50]}")
                    if capturer.connect_to_tab(tab['id'], tab['webSocketDebuggerUrl']):
                        connected = True
                        break
            
            if not connected:
                print("❌ Failed to connect to any tab")
                return False
            
            capturer.start_capture()
            time.sleep(2)
            
            print("\n🔄 Reloading page to capture authenticated requests...")
            try:
                for tab_id, ws in capturer.connections.items():
                    ws.send(json.dumps({
                        "id": 999,
                        "method": "Page.reload",
                        "params": {"ignoreCache": True}
                    }))
                    print("   ✅ Page reload command sent")
                    break
            except Exception as e:
                print(f"   ⚠️ Could not reload page: {e}")
                print("   Please manually refresh the page in Chrome")
            
            print("\n⏳ Waiting for page to load and API calls to complete...")
            
            for i in range(self.capture_duration):
                if i % 5 == 0:
                    elapsed = i
                    remaining = self.capture_duration - i
                    print(f"   ⏱️  {elapsed}s elapsed - {remaining}s remaining")
                time.sleep(1)
            
            print("\n🛑 Stopping capture...")
            capturer.stop_capture()
            
            tokens = capturer.get_session_tokens()
            
            if tokens.get('authorization'):
                self.tokens = tokens
                print("\n✅ Fresh tokens captured!")
                print(f"   Bearer Token: {tokens['authorization'][:50]}...")
                print(f"   Cookies: {len(tokens.get('cookies', {}))}")
                
                with open('fresh_tokens.json', 'w') as f:
                    json.dump(tokens, f, indent=2)
                print(f"💾 Tokens saved to: fresh_tokens.json")
                
                return True
            else:
                print("\n❌ No authorization token found!")
                return False
                
        except Exception as e:
            print(f"❌ Error capturing tokens: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def setup_session(self):
        """Setup requests session with captured tokens"""
        if not self.tokens:
            print("❌ No tokens available.")
            return False
        
        self.session = requests.Session()
        
        token = self.tokens.get('authorization', '')
        if token:
            if token.startswith('Bearer '):
                token = token.replace('Bearer ', '')
            auth_header = f'Bearer {token}'
        else:
            print("❌ No token found")
            return False
        
        print(f"   Token length: {len(token)}")
        print(f"   Token preview: {token[:50]}...")
        
        # Set headers - explicitly accept gzip and handle it
        headers = {
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Authorization': auth_header,
            'AppId': '105',
            'X-App-Id': '105',
            'SystemId': 'Naukri',
            'X-System-Id': 'Naukri',
            'Origin': 'https://www.naukri.com',
            'Referer': 'https://www.naukri.com/mnjuser/homepage',
            'X-Requested-With': 'XMLHttpRequest',
            'Connection': 'keep-alive'
        }
        self.session.headers.update(headers)
        
        cookies = self.tokens.get('cookies', {})
        if cookies:
            if 'nauk_at' not in cookies:
                cookies['nauk_at'] = token
            self.session.cookies.update(cookies)
            print(f"   Cookies set: {len(cookies)}")
        else:
            print("   ⚠️ No cookies found")
        
        print("✅ Session configured")
        return True
    
    def decompress_response(self, response):
        """Decompress response if it's gzipped"""
        content_encoding = response.headers.get('Content-Encoding', '')
        if 'gzip' in content_encoding:
            try:
                # Try to decompress the content
                decompressed = gzip.decompress(response.content)
                return decompressed.decode('utf-8')
            except:
                return response.text
        return response.text
    
    def test_session(self):
        """Test if the session is working"""
        print("\n🔍 Testing session...")
        url = "https://www.naukri.com/cloudgateway-mynaukri/resman-aggregator-services/v1/users/self/dashboard"
        
        try:
            print(f"   Testing: {url}")
            response = self.session.get(url)
            print(f"   Status: {response.status_code}")
            print(f"   Content-Type: {response.headers.get('Content-Type', 'N/A')}")
            print(f"   Content-Encoding: {response.headers.get('Content-Encoding', 'N/A')}")
            print(f"   Response length: {len(response.content)}")
            
            if response.status_code == 200:
                # Try to decompress if needed
                text = self.decompress_response(response)
                print(f"   Decompressed length: {len(text)}")
                print(f"   Preview: {text[:200]}...")
                
                try:
                    data = json.loads(text)
                    if 'dashBoard' in data:
                        print(f"   ✅ Dashboard accessible")
                        return True
                    else:
                        print(f"   ❌ Unexpected response structure")
                        return False
                except json.JSONDecodeError as e:
                    print(f"   ❌ JSON Parse Error: {e}")
                    print(f"   Response preview: {text[:200]}")
                    return False
            else:
                print(f"   ❌ Failed: {response.status_code}")
                return False
                
        except Exception as e:
            print(f"   ❌ Error: {e}")
            return False
    
    def get_recommended_jobs(self, limit=30):
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
            print(f"\n📤 Fetching recommended jobs (limit: {limit})...")
            response = self.session.post(url, json=payload)
            
            print(f"   Status: {response.status_code}")
            print(f"   Content-Type: {response.headers.get('Content-Type', 'N/A')}")
            print(f"   Content-Encoding: {response.headers.get('Content-Encoding', 'N/A')}")
            print(f"   Response length: {len(response.content)}")
            
            if response.status_code == 200:
                text = self.decompress_response(response)
                print(f"   Decompressed length: {len(text)}")
                
                try:
                    data = json.loads(text)
                    jobs = data.get('jobDetails', [])
                    total = data.get('noOfJobs', 0)
                    print(f"✅ Found {total} recommended jobs")
                    return data
                except json.JSONDecodeError as e:
                    print(f"❌ JSON Parse Error: {e}")
                    print(f"   Response preview: {text[:300]}")
                    return {'error': str(e), 'jobDetails': []}
            else:
                print(f"❌ Failed: {response.status_code}")
                return {'error': f'Status {response.status_code}', 'jobDetails': []}
                
        except Exception as e:
            print(f"❌ Error: {e}")
            return {'error': str(e), 'jobDetails': []}
    
    def print_jobs(self, jobs, max_display=15):
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
            
            exp = "N/A"
            loc = "N/A"
            sal = "Not specified"
            posted = "Recently"
            
            for placeholder in job.get('placeholders', []):
                ptype = placeholder.get('type', '')
                label = placeholder.get('label', '')
                if ptype == 'experience':
                    exp = label
                elif ptype == 'salary':
                    sal = label
                elif ptype == 'location':
                    loc = label
                elif ptype == 'date':
                    posted = label
            
            tags = job.get('tagsAndSkills', '').split(',')[:3]
            is_walkin = job.get('walkinJob', False)
            is_saved = job.get('isSaved', False)
            
            print(f"\n{i}. 🏢 {title}")
            print(f"   Company: {company}")
            print(f"   📍 Location: {loc}")
            print(f"   💼 Experience: {exp}")
            print(f"   💰 Salary: {sal}")
            print(f"   📅 Posted: {posted}")
            print(f"   🔗 Job ID: {job_id}")
            if is_walkin:
                print(f"   🚶 Walk-in: Yes")
            if is_saved:
                print(f"   ⭐ Saved")
            if tags:
                print(f"   🏷️  Skills: {', '.join(tags)}")
            print(f"   {'-'*60}")
        
        if len(jobs) > max_display:
            print(f"\n   ... and {len(jobs) - max_display} more jobs")
    
    def run(self):
        """Main execution flow"""
        print("="*80)
        print("🚀 NAUKRI AUTO JOB FETCHER")
        print("="*80)
        
        if not self.capture_tokens():
            print("\n❌ Failed to capture tokens. Exiting...")
            return False
        
        if not self.setup_session():
            return False
        
        token = self.tokens.get('authorization', '').replace('Bearer ', '')
        try:
            parts = token.split('.')
            if len(parts) == 3:
                payload = json.loads(base64.urlsafe_b64decode(parts[1] + '==').decode('utf-8'))
                print(f"\n👤 Authenticated as:")
                print(f"   User ID: {payload.get('userId')}")
                print(f"   Email: {payload.get('ud_email')}")
                exp = payload.get('exp', 0)
                if exp:
                    print(f"   Token expires: {datetime.fromtimestamp(exp).isoformat()}")
        except Exception as e:
            print(f"   ⚠️ Could not decode token: {e}")
        
        if not self.test_session():
            print("\n⚠️ Session test failed. Please check your tokens and try again.")
            return False
        
        print("\n" + "="*80)
        print("📡 FETCHING JOBS")
        print("="*80)
        
        print("\n1️⃣ GETTING RECOMMENDED JOBS...")
        result = self.get_recommended_jobs(limit=30)
        
        if 'jobDetails' in result and result['jobDetails']:
            jobs = result['jobDetails']
            total = result.get('noOfJobs', 0)
            self.print_jobs(jobs, max_display=15)
            
            filename = f"recommended_jobs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(filename, 'w') as f:
                json.dump(result, f, indent=2)
            print(f"\n💾 Full job data saved to: {filename}")
            print(f"   Total available: {total} jobs")
        else:
            print(f"❌ {result.get('error', 'No jobs found')}")
        
        print("\n" + "="*80)
        print("✅ COMPLETED")
        print("="*80)
        
        return True


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Naukri Auto Job Fetcher')
    parser.add_argument('--port', type=int, default=9260, help='Chrome debugging port (default: 9260)')
    parser.add_argument('--duration', type=int, default=45, help='Capture duration in seconds (default: 45)')
    args = parser.parse_args()
    
    fetcher = NaukriAutoFetcher(port=args.port, capture_duration=args.duration)
    fetcher.run()


if __name__ == "__main__":
    main()
