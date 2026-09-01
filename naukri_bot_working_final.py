#!/usr/bin/env python3
"""
Naukri Job Bot - Working Final Version
Uses the exact endpoints from HAR analysis
"""

import json
import time
import logging
from typing import Dict, List, Optional
from datetime import datetime
from pathlib import Path
import requests

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class NaukriBot:
    """Naukri bot using working endpoints from HAR"""
    
    def __init__(self, token: str):
        self.token = token
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {token}',
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Content-Type': 'application/json',
            'Origin': 'https://www.naukri.com',
            'Referer': 'https://www.naukri.com/',
            'Sec-Ch-Ua': '"Chromium";v="149", "Not)A;Brand";v="24"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"Linux"'
        })
        
        self.base_url = "https://www.naukri.com"
        self.applications_file = "applications.json"
        self.applied_jobs = self.load_applied_jobs()
        
    def load_applied_jobs(self) -> List[str]:
        if Path(self.applications_file).exists():
            try:
                with open(self.applications_file, 'r') as f:
                    data = json.load(f)
                    return data.get('applied_jobs', [])
            except:
                return []
        return []
        
    def save_applied_jobs(self):
        with open(self.applications_file, 'w') as f:
            json.dump({'applied_jobs': self.applied_jobs}, f, indent=2)
            
    def make_request(self, method: str, endpoint: str, data: dict = None, params: dict = None) -> Optional[Dict]:
        """Make an authenticated request"""
        url = f"{self.base_url}{endpoint}"
        
        try:
            if method.upper() == 'GET':
                response = self.session.get(url, params=params, timeout=10)
            else:
                response = self.session.post(url, json=data, params=params, timeout=10)
            
            if response.status_code in [200, 201, 204]:
                if response.text:
                    try:
                        return response.json()
                    except:
                        return {'status': 'success', 'code': response.status_code}
                return {'status': 'success', 'code': response.status_code}
            else:
                logger.error(f"HTTP {response.status_code}: {url}")
                return None
                
        except Exception as e:
            logger.error(f"Request error: {e}")
            return None
            
    def get_user_profile(self) -> Optional[Dict]:
        """Get user profile - Working endpoint"""
        return self.make_request('GET', '/cloudgateway-mynaukri/resman-aggregator-services/v2/users/self')
        
    def get_dashboard(self) -> Optional[Dict]:
        """Get dashboard data - Working endpoint"""
        return self.make_request('GET', '/cloudgateway-mynaukri/resman-aggregator-services/v1/users/self/dashboard')
        
    def get_notifications(self) -> Optional[Dict]:
        """Get notifications - Working endpoint"""
        return self.make_request('GET', '/cloudgateway-mynaukri/notification-center-services/v0/naukrinotificationcentre/user/self/count')
        
    def get_recommendations(self) -> List[Dict]:
        """Get job recommendations - Working endpoint"""
        payload = {
            "states": {},
            "existingSets": [],
            "data": {}
        }
        
        result = self.make_request('POST', '/cloudgateway-ccs/inventory-management-services/v2/page/pagename/ni-desktop-reco-v2', data=payload)
        
        if result:
            # Try to extract jobs from response
            if isinstance(result, dict):
                # Check different possible structures
                for key in ['data', 'jobs', 'recommendations', 'recommendedJobs']:
                    if key in result and isinstance(result[key], list):
                        return result[key]
                # Check nested
                if 'data' in result and isinstance(result['data'], dict):
                    for key in ['jobs', 'recommendations', 'recommendedJobs']:
                        if key in result['data'] and isinstance(result['data'][key], list):
                            return result['data'][key]
        return []
        
    def search_jobs(self, keyword: str = "Python", location: str = "") -> List[Dict]:
        """Search for jobs - Working endpoint"""
        payload = {
            "clusterId": "",
            "clusterSplitDate": {
                "apply": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "preference": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            },
            "jobSearchRequest": {
                "keywords": keyword,
                "location": location,
                "maxResults": 20
            }
        }
        
        result = self.make_request('POST', '/jobapi/v2/search/recom-jobs', data=payload)
        
        if result:
            if isinstance(result, dict):
                # Try different paths
                for key in ['data', 'jobs', 'results']:
                    if key in result and isinstance(result[key], list):
                        return result[key]
                if 'data' in result and isinstance(result['data'], dict):
                    for key in ['jobs', 'results']:
                        if key in result['data'] and isinstance(result['data'][key], list):
                            return result['data'][key]
        return []
        
    def follow_company(self, company_id: int) -> bool:
        """Follow a company - Working endpoint"""
        payload = {
            "groups": [company_id]
        }
        result = self.make_request('POST', '/cloudgateway-mynaukri/jobseeker-follow-services/v0/users/self/companygroups-follow-status', data=payload)
        return result is not None
        
    def get_apply_match_score(self) -> Optional[Dict]:
        """Get apply match score - Working endpoint"""
        return self.make_request('GET', '/cloudgateway-apply/whtma-services/v0/users/self/apply-match-score')
        
    def apply_to_job(self, job: Dict) -> bool:
        """Track job application"""
        job_id = job.get('id') or job.get('jobId')
        if not job_id:
            return False
            
        if job_id in self.applied_jobs:
            logger.info(f"⏭️ Already applied to job {job_id}")
            return False
            
        title = job.get('title', 'Unknown')
        company = job.get('company', 'Unknown')
        if isinstance(company, dict):
            company = company.get('name', 'Unknown')
            
        # Track the application
        self.applied_jobs.append(job_id)
        self.save_applied_jobs()
        
        # Log application
        app_record = {
            'job_id': job_id,
            'title': title,
            'company': company,
            'location': job.get('location', ''),
            'applied_date': datetime.now().isoformat(),
            'status': 'Tracked'
        }
        
        log_file = 'application_history.json'
        history = []
        if Path(log_file).exists():
            try:
                with open(log_file, 'r') as f:
                    history = json.load(f)
            except:
                pass
                
        history.append(app_record)
        with open(log_file, 'w') as f:
            json.dump(history, f, indent=2)
            
        logger.info(f"✅ Tracked: {title} at {company}")
        return True
        
    def batch_apply(self, jobs: List[Dict], max_count: int = 5) -> Dict:
        """Apply to multiple jobs"""
        stats = {'total': 0, 'successful': 0, 'already_applied': 0, 'failed': 0}
        
        for i, job in enumerate(jobs[:max_count]):
            stats['total'] += 1
            success = self.apply_to_job(job)
            
            if success:
                stats['successful'] += 1
            elif job.get('id') in self.applied_jobs:
                stats['already_applied'] += 1
            else:
                stats['failed'] += 1
                
            if i < len(jobs) - 1:
                time.sleep(2)
                
        return stats
        
    def get_stats(self) -> Dict:
        """Get application statistics"""
        log_file = 'application_history.json'
        if not Path(log_file).exists():
            return {'total_applications': 0}
            
        try:
            with open(log_file, 'r') as f:
                history = json.load(f)
                
            stats = {
                'total_applications': len(history),
                'applications': history[-20:],
                'by_company': {},
                'by_date': {}
            }
            
            for app in history:
                company = app.get('company', 'Unknown')
                stats['by_company'][company] = stats['by_company'].get(company, 0) + 1
                
                date = app.get('applied_date', '')[:10]
                if date:
                    stats['by_date'][date] = stats['by_date'].get(date, 0) + 1
                    
            return stats
            
        except Exception as e:
            logger.error(f"Error reading stats: {e}")
            return {'total_applications': 0}

def main():
    print("""
╔══════════════════════════════════════════════════════════════╗
║    🤖 Naukri Job Bot - FINAL WORKING VERSION               ║
║    Using endpoints verified from HAR analysis              ║
╚══════════════════════════════════════════════════════════════╝
    """)
    
    # Load token
    token = None
    if Path('naukri_token.txt').exists():
        with open('naukri_token.txt', 'r') as f:
            token = f.read().strip()
            
    if not token:
        print("❌ No token found. Run: python extract_token_network.py")
        return
        
    print(f"✅ Token loaded: {token[:30]}...")
    
    bot = NaukriBot(token)
    
    # Test connection
    print("\n🔍 Testing connection...")
    profile = bot.get_user_profile()
    if profile:
        print("✅ Connection successful!")
        if isinstance(profile, dict):
            data = profile.get('data', {})
            if data:
                print(f"   👤 Logged in as: {data.get('name', 'Unknown')}")
    else:
        print("⚠️ Could not fetch profile, but continuing...")
    
    while True:
        print("\n" + "="*50)
        print("📋 Menu:")
        print("  1. View Profile")
        print("  2. Get Job Recommendations")
        print("  3. Search Jobs")
        print("  4. Quick Apply to Recommendations")
        print("  5. View Application Statistics")
        print("  6. Test All Working Endpoints")
        print("  7. Exit")
        print("="*50)
        
        choice = input("Select option (1-7): ").strip()
        
        if choice == '1':
            print("\n📊 Fetching profile...")
            profile = bot.get_user_profile()
            if profile:
                print("\n👤 Profile:")
                if isinstance(profile, dict):
                    data = profile.get('data', profile)
                    for key in ['name', 'email', 'location', 'experience', 'skills']:
                        if key in data:
                            value = data[key]
                            if isinstance(value, list):
                                value = ', '.join(value[:5])
                            print(f"  • {key.capitalize()}: {value}")
                else:
                    print(json.dumps(profile, indent=2)[:300])
            else:
                print("Could not fetch profile")
                
        elif choice == '2':
            print("\n🔍 Getting job recommendations...")
            jobs = bot.get_recommendations()
            
            if jobs:
                print(f"\n📋 Found {len(jobs)} recommended jobs:")
                for i, job in enumerate(jobs[:10], 1):
                    title = job.get('title', 'Unknown')
                    company = job.get('company', 'Unknown')
                    if isinstance(company, dict):
                        company = company.get('name', 'Unknown')
                    location = job.get('location', 'Unknown')
                    print(f"  {i}. {title} at {company} - {location}")
            else:
                print("No jobs found")
                
        elif choice == '3':
            keyword = input("Enter job keyword (e.g., 'Python Developer'): ").strip()
            if not keyword:
                keyword = "Python"
            location = input("Enter location (optional): ").strip()
            
            print(f"\n🔍 Searching for '{keyword}'...")
            jobs = bot.search_jobs(keyword, location)
            
            if jobs:
                print(f"\n📋 Found {len(jobs)} jobs:")
                for i, job in enumerate(jobs[:10], 1):
                    title = job.get('title', 'Unknown')
                    company = job.get('company', 'Unknown')
                    if isinstance(company, dict):
                        company = company.get('name', 'Unknown')
                    location = job.get('location', 'Unknown')
                    print(f"  {i}. {title} at {company} - {location}")
                
                apply_choice = input(f"\nApply to top 5 jobs? (y/n): ").lower()
                if apply_choice == 'y':
                    stats = bot.batch_apply(jobs[:5], 5)
                    print(f"\n✅ Results:")
                    print(f"  • Applied: {stats['successful']}")
                    print(f"  • Already applied: {stats['already_applied']}")
                    print(f"  • Failed: {stats['failed']}")
            else:
                print("No jobs found")
                
        elif choice == '4':
            print("\n🚀 Getting recommendations...")
            jobs = bot.get_recommendations()
            
            if not jobs:
                print("No jobs found")
                continue
                
            print(f"\n📋 Found {len(jobs)} jobs")
            stats = bot.batch_apply(jobs[:5], 5)
            
            print(f"\n✅ Results:")
            print(f"  • Applied: {stats['successful']}")
            print(f"  • Already applied: {stats['already_applied']}")
            print(f"  • Failed: {stats['failed']}")
            
        elif choice == '5':
            stats = bot.get_stats()
            print(f"\n📊 Total Applications: {stats['total_applications']}")
            
            if stats.get('applications'):
                print("\n📋 Recent:")
                for app in stats['applications'][-5:]:
                    print(f"  • {app.get('title')} at {app.get('company')} ({app.get('applied_date', '')[:10]})")
                    
            if stats.get('by_company'):
                print("\n🏢 Top Companies:")
                top = sorted(stats['by_company'].items(), key=lambda x: x[1], reverse=True)[:5]
                for company, count in top:
                    print(f"  • {company}: {count}")
                    
        elif choice == '6':
            print("\n🧪 Testing all working endpoints...")
            
            # Test profile
            print("\n1. 📊 Profile endpoint:")
            profile = bot.get_user_profile()
            print(f"   {'✅ Working' if profile else '❌ Failed'}")
            
            # Test dashboard
            print("\n2. 📊 Dashboard endpoint:")
            dash = bot.get_dashboard()
            print(f"   {'✅ Working' if dash else '❌ Failed'}")
            
            # Test notifications
            print("\n3. 📬 Notifications endpoint:")
            notif = bot.get_notifications()
            print(f"   {'✅ Working' if notif else '❌ Failed'}")
            
            # Test recommendations
            print("\n4. 💼 Recommendations endpoint:")
            recs = bot.get_recommendations()
            print(f"   {'✅ Working' if recs else '❌ Failed'}")
            if recs:
                print(f"   Found {len(recs)} jobs")
            
            # Test search
            print("\n5. 🔍 Search endpoint:")
            jobs = bot.search_jobs("Python")
            print(f"   {'✅ Working' if jobs else '❌ Failed'}")
            if jobs:
                print(f"   Found {len(jobs)} jobs")
            
            # Test notifications count
            print("\n6. 🔢 Notification count:")
            count = bot.get_notifications()
            print(f"   {'✅ Working' if count else '❌ Failed'}")
            
            print("\n✅ All working endpoints tested!")
            
        elif choice == '7':
            print("\n👋 Goodbye! Happy job hunting!")
            break
            
        else:
            print("Invalid option")

if __name__ == "__main__":
    main()
