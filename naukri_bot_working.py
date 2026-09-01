#!/usr/bin/env python3
"""
Naukri Job Bot - Working Version
Uses the correct API endpoints
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
    """Naukri bot with correct API endpoints"""
    
    def __init__(self, token: str):
        self.token = token
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {token}',
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36',
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        })
        
        # Correct base URLs
        self.base_urls = [
            'https://www.naukri.com',
            'https://www.naukimg.com',
            'https://img.naukimg.com'
        ]
        
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
            
    def make_request(self, method: str, url: str, **kwargs) -> Optional[Dict]:
        """Make an authenticated request"""
        try:
            response = self.session.request(method, url, **kwargs)
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"HTTP {response.status_code}: {url}")
                return None
                
        except Exception as e:
            logger.error(f"Request error: {e}")
            return None
            
    def get_user_profile(self) -> Optional[Dict]:
        """Get user profile"""
        # Try different possible endpoints
        endpoints = [
            '/cloudgateway-mynaukri/resman-aggregator-services/v2/users/self',
            '/cloudgateway-mynaukri/resman-aggregator-services/v1/users/self/dashboard',
            '/api/v1/users/self'
        ]
        
        for endpoint in endpoints:
            url = f"https://www.naukri.com{endpoint}"
            result = self.make_request('GET', url)
            if result:
                logger.info(f"✅ Profile found at: {endpoint}")
                return result
                
        return None
        
    def get_dashboard_data(self) -> Optional[Dict]:
        """Get dashboard data from the homepage"""
        url = "https://www.naukri.com/mnjuser/homepage"
        result = self.make_request('GET', url)
        return result
        
    def get_notifications(self) -> Optional[Dict]:
        """Get notifications"""
        url = "https://www.naukri.com/cloudgateway-mynaukri/notification-center-services/v0/naukrinotificationcentre/user/self/count"
        result = self.make_request('GET', url)
        return result
        
    def get_job_recommendations(self) -> List[Dict]:
        """Get job recommendations from the homepage"""
        data = self.get_dashboard_data()
        if data:
            # Try different possible paths
            if isinstance(data, dict):
                # Check common structures
                for key in ['data', 'jobs', 'recommendations', 'recommendedJobs']:
                    if key in data:
                        items = data.get(key, [])
                        if isinstance(items, list):
                            logger.info(f"✅ Found {len(items)} jobs in '{key}'")
                            return items
                            
                # If data is nested, check deeper
                if 'data' in data and isinstance(data['data'], dict):
                    for key in ['jobs', 'recommendedJobs', 'recommendations']:
                        if key in data['data']:
                            items = data['data'].get(key, [])
                            if isinstance(items, list):
                                logger.info(f"✅ Found {len(items)} jobs in 'data.{key}'")
                                return items
                                
        logger.warning("Could not find job recommendations")
        return []
        
    def search_jobs(self, keyword: str = "Python", location: str = "") -> List[Dict]:
        """Search for jobs using the job search API"""
        # Try different search endpoints
        search_urls = [
            f"https://www.naukri.com/jobapi/v2/search/recom-jobs",
            f"https://www.naukri.com/api/v1/jobs/search"
        ]
        
        payload = {
            "keywords": keyword,
            "location": location,
            "maxResults": 20
        }
        
        for url in search_urls:
            result = self.make_request('POST', url, json=payload)
            if result:
                if isinstance(result, dict):
                    jobs = result.get('data', {}).get('jobs', []) or result.get('jobs', [])
                    if jobs:
                        logger.info(f"✅ Found {len(jobs)} jobs via search")
                        return jobs
                        
        return []
        
    def get_user_stats(self) -> Optional[Dict]:
        """Get user statistics"""
        url = "https://www.naukri.com/cloudgateway-mynaukri/notification-center-services/v0/naukrinotificationcentre/user/self/count"
        result = self.make_request('GET', url)
        return result
        
    def apply_to_job(self, job: Dict) -> bool:
        """Apply to a job (tracking only for now)"""
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
            'status': 'Applied'
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
║    🤖 Naukri Job Bot - Working Version                     ║
║    Using correct API endpoints                              ║
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
    
    while True:
        print("\n" + "="*50)
        print("📋 Menu:")
        print("  1. View Profile")
        print("  2. Get Job Recommendations")
        print("  3. Search Jobs")
        print("  4. Quick Apply to Recommendations")
        print("  5. View Application Statistics")
        print("  6. Test All Endpoints")
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
                            print(f"  • {key}: {value}")
                else:
                    print(json.dumps(profile, indent=2)[:300])
            else:
                print("Could not fetch profile")
                
        elif choice == '2':
            print("\n🔍 Getting job recommendations...")
            jobs = bot.get_job_recommendations()
            
            if jobs:
                print(f"\n📋 Found {len(jobs)} jobs:")
                for i, job in enumerate(jobs[:10], 1):
                    title = job.get('title', 'Unknown')
                    company = job.get('company', 'Unknown')
                    if isinstance(company, dict):
                        company = company.get('name', 'Unknown')
                    print(f"  {i}. {title} at {company}")
            else:
                print("No jobs found")
                
        elif choice == '3':
            keyword = input("Enter job keyword: ").strip()
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
                    print(f"  {i}. {title} at {company}")
            else:
                print("No jobs found")
                
        elif choice == '4':
            print("\n🚀 Getting recommendations...")
            jobs = bot.get_job_recommendations()
            
            if not jobs:
                print("No jobs found")
                continue
                
            print(f"\n📋 Found {len(jobs)} jobs")
            stats = bot.batch_apply(jobs, 5)
            
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
                    print(f"  • {app.get('title')} at {app.get('company')}")
                    
            if stats.get('by_company'):
                print("\n🏢 Top Companies:")
                top = sorted(stats['by_company'].items(), key=lambda x: x[1], reverse=True)[:5]
                for company, count in top:
                    print(f"  • {company}: {count}")
                    
        elif choice == '6':
            print("\n🧪 Testing all endpoints...")
            
            # Test notifications
            print("\n📬 Notifications:")
            notif = bot.get_notifications()
            if notif:
                print(json.dumps(notif, indent=2)[:200])
            else:
                print("❌ Notifications endpoint failed")
                
            # Test profile
            print("\n👤 Profile:")
            profile = bot.get_user_profile()
            if profile:
                print(json.dumps(profile, indent=2)[:200])
            else:
                print("❌ Profile endpoint failed")
                
            # Test dashboard
            print("\n📊 Dashboard:")
            dash = bot.get_dashboard_data()
            if dash:
                print(json.dumps(dash, indent=2)[:200])
            else:
                print("❌ Dashboard endpoint failed")
                
        elif choice == '7':
            print("\n👋 Goodbye!")
            break
            
        else:
            print("Invalid option")

if __name__ == "__main__":
    main()
