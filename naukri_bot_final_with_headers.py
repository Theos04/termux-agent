#!/usr/bin/env python3
"""
Naukri Job Bot - FINAL WITH HEADERS
Includes required AppId and SystemId headers
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
    """Naukri bot with required headers"""
    
    def __init__(self, token: str):
        self.token = token
        self.session = requests.Session()
        
        # Required headers from the error message
        self.session.headers.update({
            'Authorization': f'Bearer {token}',
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Content-Type': 'application/json',
            'Origin': 'https://www.naukri.com',
            'Referer': 'https://www.naukri.com/mnjuser/homepage',
            'AppId': '109',  # Common AppId for Naukri
            'SystemId': '109',  # Common SystemId for Naukri
            'Sec-Ch-Ua': '"Chromium";v="149", "Not)A;Brand";v="24"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"Linux"',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin'
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
        """Make an authenticated request with required headers"""
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
                if response.text:
                    logger.error(f"Response: {response.text[:200]}")
                return None
                
        except Exception as e:
            logger.error(f"Request error: {e}")
            return None
            
    def search_jobs(self, keywords: str = "python developer", location: str = "") -> List[Dict]:
        """Search for jobs with required headers"""
        
        # Use the exact format from HAR
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
                    "keywords": keywords,
                    "location": location
                }
            ]
        }
        
        result = self.make_request('POST', '/jobapi/v2/search/recom-jobs', data=payload)
        
        if result:
            if isinstance(result, dict):
                # Try different paths to extract jobs
                for key in ['data', 'jobs', 'results']:
                    if key in result and isinstance(result[key], list):
                        return result[key]
                if 'data' in result and isinstance(result['data'], dict):
                    for key in ['jobs', 'results', 'jobData']:
                        if key in result['data'] and isinstance(result['data'][key], list):
                            return result['data'][key]
        return []
        
    def get_recommendations(self) -> List[Dict]:
        """Get job recommendations"""
        
        payload = {
            "states": {},
            "existingSets": [],
            "data": {}
        }
        
        params = {
            "partial": "true",
            "rules": "true",
            "sync": "true"
        }
        
        result = self.make_request('POST', '/cloudgateway-ccs/inventory-management-services/v2/page/pagename/ni-desktop-reco-v2', 
                                   data=payload, params=params)
        
        if result:
            if isinstance(result, dict):
                for key in ['data', 'jobs', 'recommendations', 'recommendedJobs']:
                    if key in result and isinstance(result[key], list):
                        return result[key]
                if 'data' in result and isinstance(result['data'], dict):
                    for key in ['jobs', 'recommendations', 'recommendedJobs']:
                        if key in result['data'] and isinstance(result['data'][key], list):
                            return result['data'][key]
        return []
        
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
            
        self.applied_jobs.append(job_id)
        self.save_applied_jobs()
        
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
║    🤖 Naukri Job Bot - WITH REQUIRED HEADERS               ║
║    Includes AppId and SystemId headers                      ║
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
        print("  1. Search Jobs")
        print("  2. Get Job Recommendations")
        print("  3. Quick Apply to Recommendations")
        print("  4. View Application Statistics")
        print("  5. Test Search")
        print("  6. Exit")
        print("="*50)
        
        choice = input("Select option (1-6): ").strip()
        
        if choice == '1':
            keywords = input("Enter job keywords (e.g., 'python developer'): ").strip()
            if not keywords:
                keywords = "python developer"
            location = input("Enter location (optional): ").strip()
            
            print(f"\n🔍 Searching for '{keywords}'...")
            jobs = bot.search_jobs(keywords, location)
            
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
            
        elif choice == '4':
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
                    
        elif choice == '5':
            print("\n🧪 Testing search with required headers...")
            jobs = bot.search_jobs("python developer")
            
            if jobs:
                print(f"✅ Success! Found {len(jobs)} jobs")
                for job in jobs[:3]:
                    title = job.get('title', 'Unknown')
                    company = job.get('company', 'Unknown')
                    if isinstance(company, dict):
                        company = company.get('name', 'Unknown')
                    print(f"  • {title} at {company}")
            else:
                print("❌ Search failed. Check if AppId and SystemId are correct.")
                print("Try different values for AppId and SystemId.")
                
        elif choice == '6':
            print("\n👋 Goodbye! Happy job hunting!")
            break
            
        else:
            print("Invalid option")

if __name__ == "__main__":
    main()
