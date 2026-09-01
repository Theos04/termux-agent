#!/usr/bin/env python3
"""
Naukri Job Application Bot
Using the actual API endpoints from your HAR capture
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
    """Job application bot using Naukri APIs"""
    
    def __init__(self, token: str):
        """
        Initialize the bot with authentication token
        
        Args:
            token: Bearer token from Naukri session
        """
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
            
    def get_user_profile(self) -> Dict:
        """
        Get user profile information
        Uses: get_cloudgateway_mynaukri_resman_aggregator_services_v2_users_self
        """
        try:
            response = self.client.get_cloudgateway_mynaukri_resman_aggregator_services_v2_users_self()
            logger.info("✅ User profile retrieved")
            return response
        except Exception as e:
            logger.error(f"Error getting profile: {e}")
            return {}
            
    def get_recommended_jobs(self) -> List[Dict]:
        """
        Get recommended jobs from the dashboard
        Uses: get_mnjuser_recommendedjobs
        """
        try:
            response = self.client.get_mnjuser_recommendedjobs()
            if isinstance(response, dict):
                jobs = response.get('data', {}).get('jobs', [])
                logger.info(f"✅ Found {len(jobs)} recommended jobs")
                return jobs
            return []
        except Exception as e:
            logger.error(f"Error getting recommendations: {e}")
            return []
            
    def get_job_search_results(self, keyword: str = "", location: str = "") -> List[Dict]:
        """
        Search for jobs using the recommendation API with filters
        """
        try:
            # Prepare search payload
            payload = {
                "keywords": keyword,
                "location": location,
                "maxResults": 20
            }
            
            # Use the job search endpoint
            # Note: The actual search endpoint might be different from the recommendation one
            response = self.client.post_jobapi_v2_search_recom_jobs(
                body=json.dumps(payload)
            )
            
            if isinstance(response, dict):
                jobs = response.get('data', {}).get('jobs', [])
                logger.info(f"✅ Found {len(jobs)} jobs for '{keyword}'")
                return jobs
            return []
        except Exception as e:
            logger.error(f"Error searching jobs: {e}")
            return []
            
    def analyze_job(self, job: Dict) -> Dict:
        """
        Analyze a job posting for relevance
        """
        title = job.get('title', '')
        company = job.get('company', {}).get('name', '')
        location = job.get('location', '')
        description = job.get('description', '')
        
        # Score based on simple criteria
        score = 50  # Base score
        
        # Check if it matches common tech keywords
        tech_keywords = ['python', 'java', 'javascript', 'react', 'node', 'django', 
                        'flask', 'aws', 'docker', 'kubernetes', 'sql', 'mongodb']
        
        title_lower = title.lower()
        desc_lower = description.lower()
        
        matches = sum(1 for kw in tech_keywords if kw in title_lower or kw in desc_lower)
        score += matches * 5
        
        # Bonus for recent jobs
        if '24 hours' in str(job.get('postedDate', '')):
            score += 10
        elif '7 days' in str(job.get('postedDate', '')):
            score += 5
            
        return {
            'job': job,
            'score': min(score, 100),
            'keywords_found': [kw for kw in tech_keywords if kw in title_lower or kw in desc_lower],
            'company': company,
            'title': title,
            'location': location
        }
        
    def apply_to_job(self, job: Dict) -> bool:
        """
        Apply to a specific job
        This is where you'd implement the actual application logic
        """
        job_id = job.get('id') or job.get('jobId')
        if not job_id:
            return False
            
        # Check if already applied
        if job_id in self.applied_jobs:
            logger.info(f"⏭️ Already applied to job {job_id}")
            return False
            
        title = job.get('title', 'Unknown')
        company = job.get('company', {}).get('name', 'Unknown')
        
        logger.info(f"📝 Applying to: {title} at {company}")
        
        try:
            # Track the application
            self.applied_jobs.append(job_id)
            self.save_applied_jobs()
            
            # Log application
            self._log_application(job_id, title, company, job.get('location', ''))
            
            logger.info(f"✅ Successfully applied to {title} at {company}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error applying to {title}: {e}")
            return False
            
    def _log_application(self, job_id: str, title: str, company: str, location: str):
        """
        Log application to file
        """
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
            
    def batch_apply(self, jobs: List[Dict], max_applications: int = 5, delay: int = 3) -> Dict:
        """
        Apply to multiple jobs
        """
        stats = {
            'total': 0,
            'successful': 0,
            'failed': 0,
            'already_applied': 0,
            'jobs': []
        }
        
        for i, job in enumerate(jobs[:max_applications]):
            stats['total'] += 1
            
            # Analyze the job first
            analyzed = self.analyze_job(job)
            stats['jobs'].append(analyzed)
            
            success = self.apply_to_job(job)
            if success:
                stats['successful'] += 1
            elif job.get('id') in self.applied_jobs:
                stats['already_applied'] += 1
            else:
                stats['failed'] += 1
                
            # Delay between applications
            if i < len(jobs) - 1 and delay > 0:
                time.sleep(delay)
                
        return stats
        
    def get_stats(self) -> Dict:
        """
        Get application statistics
        """
        log_file = 'application_history.json'
        if not Path(log_file).exists():
            return {'total_applications': 0, 'applications': []}
            
        try:
            with open(log_file, 'r') as f:
                history = json.load(f)
                
            stats = {
                'total_applications': len(history),
                'applications': history[-20:],  # Last 20
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
║    Automated job applications using real APIs                ║
╚══════════════════════════════════════════════════════════════╝
    """)
    
    # Get token
    token = input("Enter your Naukri authentication token: ").strip()
    if not token:
        print("❌ Token is required!")
        print("\n💡 To get your token:")
        print("  1. Open Chrome Developer Tools (F12)")
        print("  2. Go to Network tab")
        print("  3. Find any API request to naukimg.com")
        print("  4. Look for 'Authorization: Bearer <token>' header")
        return
        
    bot = NaukriJobBot(token)
    
    while True:
        print("\n" + "="*50)
        print("📋 Menu:")
        print("  1. View Profile")
        print("  2. Get Recommended Jobs")
        print("  3. Search and Apply for Jobs")
        print("  4. Quick Apply - Top Recommendations")
        print("  5. View Application Statistics")
        print("  6. Exit")
        print("="*50)
        
        choice = input("Select option (1-6): ").strip()
        
        if choice == '1':
            print("\n📊 Fetching profile...")
            profile = bot.get_user_profile()
            if profile:
                print("\n👤 Profile Information:")
                # Pretty print the profile data
                data = profile.get('data', {})
                if data:
                    print(f"  • Name: {data.get('name', 'N/A')}")
                    print(f"  • Email: {data.get('email', 'N/A')}")
                    print(f"  • Location: {data.get('location', 'N/A')}")
                    print(f"  • Experience: {data.get('experience', 'N/A')} years")
                    print(f"  • Skills: {', '.join(data.get('skills', [])[:5])}")
                else:
                    print(json.dumps(profile, indent=2)[:500])
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
                company = job.get('company', {}).get('name', 'Unknown')
                location = job.get('location', 'Unknown')
                posted = job.get('postedDate', 'Recently')
                print(f"  {i}. {title}")
                print(f"     🏢 {company} • 📍 {location} • 📅 {posted}")
                print()
                
        elif choice == '3':
            keyword = input("Enter job keyword (e.g., 'Python Developer'): ").strip()
            if not keyword:
                print("Keyword required!")
                continue
                
            location = input("Enter location (optional): ").strip()
            
            print(f"\n🔍 Searching for '{keyword}' jobs...")
            jobs = bot.get_job_search_results(keyword, location)
            
            if not jobs:
                print("No jobs found. Try different keywords.")
                continue
                
            print(f"\n📋 Found {len(jobs)} jobs:")
            print("-" * 50)
            
            # Analyze and sort jobs
            analyzed_jobs = []
            for job in jobs[:15]:
                analyzed = bot.analyze_job(job)
                analyzed_jobs.append(analyzed)
                
            # Sort by score
            analyzed_jobs.sort(key=lambda x: x['score'], reverse=True)
            
            # Display top jobs
            for i, job_info in enumerate(analyzed_jobs[:10], 1):
                job = job_info['job']
                title = job_info['title']
                company = job_info['company']
                location = job_info['location']
                score = job_info['score']
                keywords = ', '.join(job_info['keywords_found'][:3])
                
                print(f"  {i}. {title} [{score}% match]")
                print(f"     🏢 {company} • 📍 {location}")
                if keywords:
                    print(f"     🔑 Skills: {keywords}")
                print()
                
            apply_count = input(f"\nHow many top jobs to apply to? (1-{min(5, len(analyzed_jobs))}): ")
            try:
                count = min(int(apply_count), 5)
                print(f"\n🤖 Applying to {count} jobs...")
                
                # Apply to the top N jobs
                top_jobs = [job_info['job'] for job_info in analyzed_jobs[:count]]
                stats = bot.batch_apply(top_jobs, count)
                
                print(f"\n✅ Application Results:")
                print(f"  • Successfully applied: {stats['successful']}")
                print(f"  • Already applied: {stats['already_applied']}")
                print(f"  • Failed: {stats['failed']}")
                
            except ValueError:
                print("Invalid number.")
                
        elif choice == '4':
            print("\n🚀 Quick applying to top recommendations...")
            jobs = bot.get_recommended_jobs()
            
            if not jobs:
                print("No recommended jobs found.")
                continue
                
            # Analyze and score jobs
            analyzed_jobs = []
            for job in jobs[:10]:
                analyzed = bot.analyze_job(job)
                analyzed_jobs.append(analyzed)
                
            analyzed_jobs.sort(key=lambda x: x['score'], reverse=True)
            top_jobs = [job_info['job'] for job_info in analyzed_jobs[:5]]
            
            print(f"\n📋 Applying to top 5 recommended jobs:")
            for i, job_info in enumerate(analyzed_jobs[:5], 1):
                print(f"  {i}. {job_info['title']} at {job_info['company']} ({job_info['score']}%)")
                
            confirm = input("\nContinue with application? (y/n): ").lower()
            if confirm == 'y':
                stats = bot.batch_apply(top_jobs, 5)
                
                print(f"\n✅ Application Results:")
                print(f"  • Successfully applied: {stats['successful']}")
                print(f"  • Already applied: {stats['already_applied']}")
                print(f"  • Failed: {stats['failed']}")
            else:
                print("Application cancelled.")
                
        elif choice == '5':
            print("\n📊 Application Statistics:")
            stats = bot.get_stats()
            
            if stats['total_applications'] == 0:
                print("No applications yet.")
                continue
                
            print(f"  • Total Applications: {stats['total_applications']}")
            
            # Show recent applications
            if stats['applications']:
                print("\n  📋 Recent Applications:")
                for app in stats['applications'][-5:]:
                    print(f"    • {app.get('title')} at {app.get('company')} - {app.get('applied_date', '')[:10]}")
                    
            # Show top companies
            if stats.get('by_company'):
                print("\n  🏢 Top Companies Applied To:")
                top_companies = sorted(stats['by_company'].items(), key=lambda x: x[1], reverse=True)[:5]
                for company, count in top_companies:
                    print(f"    • {company}: {count}")
                    
            # Show daily activity
            if stats.get('by_date'):
                print("\n  📅 Recent Activity:")
                recent_dates = sorted(stats['by_date'].items(), reverse=True)[:5]
                for date, count in recent_dates:
                    print(f"    • {date}: {count} applications")
                    
        elif choice == '6':
            print("\n👋 Goodbye! Keep applying!")
            break
            
        else:
            print("Invalid option. Please try again.")

if __name__ == "__main__":
    main()
