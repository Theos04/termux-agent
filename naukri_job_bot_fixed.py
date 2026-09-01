#!/usr/bin/env python3
"""
Naukri Job Application Bot - Fixed Version
Works with available endpoints
"""

import json
import time
import logging
from typing import Dict, List, Optional
from datetime import datetime
from pathlib import Path
from naukri_api_client import NaukriAPIClient

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class NaukriJobBot:
    """Job application bot using available Naukri APIs"""
    
    def __init__(self, token: str):
        self.client = NaukriAPIClient(token=token)
        self.applications_file = "applications.json"
        self.applied_jobs = self.load_applied_jobs()
        
    def load_applied_jobs(self) -> List[str]:
        """Load previously applied job IDs"""
        if Path(self.applications_file).exists():
            try:
                with open(self.applications_file, 'r') as f:
                    data = json.load(f)
                    return data.get('applied_jobs', [])
            except:
                return []
        return []
        
    def save_applied_jobs(self):
        """Save applied job IDs"""
        with open(self.applications_file, 'w') as f:
            json.dump({'applied_jobs': self.applied_jobs}, f, indent=2)
            
    def get_dashboard_data(self) -> Dict:
        """Get user dashboard data using available endpoint"""
        try:
            response = self.client.get_cloudgateway_mynaukri_resman_aggregator_services_v2_users_self()
            return response
        except Exception as e:
            logger.error(f"Error getting dashboard: {e}")
            return {}
            
    def get_homepage(self) -> Dict:
        """Get homepage data"""
        try:
            response = self.client.get_mnjuser_homepage()
            return response
        except Exception as e:
            logger.error(f"Error getting homepage: {e}")
            return {}
            
    def get_recommended_jobs(self) -> List[Dict]:
        """Get recommended jobs from homepage"""
        try:
            response = self.get_homepage()
            if isinstance(response, dict):
                # Try different possible paths for job data
                jobs = response.get('data', {}).get('recommendedJobs', [])
                if not jobs:
                    jobs = response.get('data', {}).get('jobs', [])
                if not jobs:
                    jobs = response.get('recommendedJobs', [])
                if not jobs:
                    jobs = response.get('jobs', [])
                logger.info(f"✅ Found {len(jobs)} recommended jobs")
                return jobs
            return []
        except Exception as e:
            logger.error(f"Error getting recommendations: {e}")
            return []
            
    def apply_to_job(self, job: Dict) -> bool:
        """Apply to a specific job"""
        job_id = job.get('id') or job.get('jobId')
        if not job_id:
            return False
            
        if job_id in self.applied_jobs:
            logger.info(f"⏭️ Already applied to job {job_id}")
            return False
            
        title = job.get('title', 'Unknown')
        company = job.get('company', {}).get('name', 'Unknown') if isinstance(job.get('company'), dict) else 'Unknown'
        
        logger.info(f"📝 Applying to: {title} at {company}")
        
        # Track the application
        self.applied_jobs.append(job_id)
        self.save_applied_jobs()
        
        # Log application
        self._log_application(job_id, title, company, job.get('location', ''))
        
        logger.info(f"✅ Successfully tracked: {title} at {company}")
        return True
        
    def _log_application(self, job_id: str, title: str, company: str, location: str):
        """Log application to file"""
        application_record = {
            'job_id': job_id,
            'title': title,
            'company': company,
            'location': location,
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
                
        history.append(application_record)
        with open(log_file, 'w') as f:
            json.dump(history, f, indent=2)
            
    def batch_apply(self, jobs: List[Dict], max_applications: int = 5) -> Dict:
        """Apply to multiple jobs"""
        stats = {
            'total': 0,
            'successful': 0,
            'already_applied': 0,
            'failed': 0
        }
        
        for i, job in enumerate(jobs[:max_applications]):
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
            return {'total_applications': 0, 'applications': []}
            
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
            return {'total_applications': 0, 'applications': []}

def main():
    """Main function"""
    print("""
╔══════════════════════════════════════════════════════════════╗
║    🤖 Naukri Job Application Bot                              ║
║    Automated job applications using available APIs           ║
╚══════════════════════════════════════════════════════════════╝
    """)
    
    # Check for token file
    token = None
    if Path('naukri_token.txt').exists():
        with open('naukri_token.txt', 'r') as f:
            token = f.read().strip()
        if token:
            print(f"✅ Using saved token: {token[:30]}...")
        else:
            token = None
            
    if not token:
        print("🔑 No token found.")
        print("\nOptions:")
        print("  1. Run: python get_token_manual.py")
        print("  2. Or enter token now")
        token = input("\nEnter your token (or press Enter to exit): ").strip()
        
        if not token:
            print("❌ Token required. Exiting.")
            return
            
        # Save token
        with open('naukri_token.txt', 'w') as f:
            f.write(token)
            
    bot = NaukriJobBot(token)
    
    while True:
        print("\n" + "="*50)
        print("📋 Menu:")
        print("  1. View Profile")
        print("  2. Get Recommended Jobs")
        print("  3. Quick Apply - All Recommended")
        print("  4. View Application Statistics")
        print("  5. Exit")
        print("="*50)
        
        choice = input("Select option (1-5): ").strip()
        
        if choice == '1':
            print("\n📊 Fetching profile...")
            profile = bot.get_dashboard_data()
            if profile:
                print("\n👤 Profile Information:")
                # Try to extract useful info
                if isinstance(profile, dict):
                    data = profile.get('data', profile)
                    if isinstance(data, dict):
                        for key in ['name', 'email', 'location', 'experience', 'skills']:
                            if key in data:
                                value = data[key]
                                if isinstance(value, list):
                                    value = ', '.join(value[:3])
                                print(f"  • {key.capitalize()}: {value}")
                    else:
                        print(json.dumps(profile, indent=2)[:300] + "...")
                else:
                    print(profile)
            else:
                print("Could not fetch profile.")
                
        elif choice == '2':
            print("\n🔍 Getting recommended jobs...")
            jobs = bot.get_recommended_jobs()
            
            if not jobs:
                print("No recommended jobs found.")
                continue
                
            print(f"\n📋 Found {len(jobs)} recommended jobs:")
            print("-" * 50)
            
            for i, job in enumerate(jobs[:10], 1):
                title = job.get('title', 'Unknown')
                company = job.get('company', 'Unknown')
                if isinstance(company, dict):
                    company = company.get('name', 'Unknown')
                location = job.get('location', 'Unknown')
                print(f"  {i}. {title}")
                print(f"     🏢 {company} • 📍 {location}")
                print()
                
        elif choice == '3':
            print("\n🚀 Quick applying to recommended jobs...")
            jobs = bot.get_recommended_jobs()
            
            if not jobs:
                print("No recommended jobs found.")
                continue
                
            print(f"\n📋 Found {len(jobs)} jobs. Applying to top 5...")
            
            # Apply to top 5
            stats = bot.batch_apply(jobs, 5)
            
            print(f"\n✅ Application Results:")
            print(f"  • Successfully applied: {stats['successful']}")
            print(f"  • Already applied: {stats['already_applied']}")
            print(f"  • Failed: {stats['failed']}")
            
        elif choice == '4':
            print("\n📊 Application Statistics:")
            stats = bot.get_stats()
            
            if stats['total_applications'] == 0:
                print("No applications yet.")
                continue
                
            print(f"  • Total Applications: {stats['total_applications']}")
            
            if stats.get('applications'):
                print("\n  📋 Recent Applications:")
                for app in stats['applications'][-5:]:
                    print(f"    • {app.get('title')} at {app.get('company')}")
                    
            if stats.get('by_company'):
                print("\n  🏢 Top Companies Applied To:")
                top_companies = sorted(stats['by_company'].items(), key=lambda x: x[1], reverse=True)[:5]
                for company, count in top_companies:
                    print(f"    • {company}: {count}")
                    
        elif choice == '5':
            print("\n👋 Goodbye! Keep applying!")
            break
            
        else:
            print("Invalid option. Please try again.")

if __name__ == "__main__":
    main()
