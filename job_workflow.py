#!/usr/bin/env python3
"""
Complete Job Application Workflow
Combines searching, analysis, and application automation
"""

import json
import time
from typing import Dict, List
from datetime import datetime
from pathlib import Path

from job_automation import JobApplicationBot
from resume_analyzer import ResumeAnalyzer

class JobApplicationWorkflow:
    """Complete workflow for job applications"""
    
    def __init__(self, token: str, resume_path: str):
        """
        Initialize workflow
        
        Args:
            token: Naukri authentication token
            resume_path: Path to your resume file
        """
        self.bot = JobApplicationBot(token)
        self.resume_analyzer = ResumeAnalyzer()
        
        # Load resume
        self.resume_analyzer.load_resume(resume_path)
        
        # Load configuration
        self.config = self.load_config()
        
    def load_config(self) -> Dict:
        """Load user configuration"""
        config_file = "job_config.json"
        default_config = {
            "keywords": ["Python Developer", "Full Stack Developer", "Software Engineer"],
            "locations": ["Bangalore", "Mumbai", "Delhi", "Remote"],
            "experience_level": "Mid Level",
            "max_applications_per_day": 20,
            "delay_between_applications": 5,
            "salary_range": [10, 30],  # LPA
            "preferred_companies": ["Google", "Microsoft", "Amazon", "Flipkart"]
        }
        
        if Path(config_file).exists():
            try:
                with open(config_file, 'r') as f:
                    return json.load(f)
            except Exception:
                pass
                
        # Save default config
        with open(config_file, 'w') as f:
            json.dump(default_config, f, indent=2)
            
        return default_config
        
    def find_best_jobs(self, keywords: List[str], locations: List[str], limit: int = 20) -> List[Dict]:
        """
        Find best matching jobs based on configuration
        
        Args:
            keywords: List of job keywords to search
            locations: List of locations to search
            limit: Maximum jobs to return
            
        Returns:
            List of best matching jobs sorted by relevance
        """
        all_jobs = []
        
        print(f"🔍 Searching for jobs in {len(keywords)} categories...")
        
        for keyword in keywords:
            for location in locations[:2]:  # Limit locations per search
                jobs = self.bot.search_jobs(
                    keywords=keyword,
                    location=location,
                    experience_level=self.config['experience_level'],
                    max_results=10
                )
                
                # Score and filter jobs
                for job in jobs:
                    score = self.score_job(job)
                    job['relevance_score'] = score
                    all_jobs.append(job)
                    
                time.sleep(1)  # Avoid rate limiting
                
        # Sort by score and remove duplicates
        unique_jobs = {}
        for job in all_jobs:
            job_id = job.get('id') or job.get('jobId')
            if job_id:
                if job_id not in unique_jobs or job['relevance_score'] > unique_jobs[job_id]['relevance_score']:
                    unique_jobs[job_id] = job
                    
        sorted_jobs = sorted(unique_jobs.values(), 
                           key=lambda x: x['relevance_score'], 
                           reverse=True)
        
        return sorted_jobs[:limit]
        
    def score_job(self, job: Dict) -> float:
        """
        Score a job based on various factors
        
        Args:
            job: Job dictionary
            
        Returns:
            Relevance score (0-100)
        """
        score = 50  # Base score
        
        # Company preference
        company = job.get('company', {}).get('name', '').lower()
        if any(pref.lower() in company for pref in self.config['preferred_companies']):
            score += 20
            
        # Location preference
        location = job.get('location', '').lower()
        if any(loc.lower() in location for loc in self.config['locations']):
            score += 10
            
        # Salary match
        salary = job.get('salary', '')
        # Simple salary parsing (can be improved)
        if 'lpa' in salary.lower():
            score += 5
            
        # Job age (prefer newer jobs)
        posted_date = job.get('postedDate', '')
        # Give bonus to jobs posted within last 7 days
        score += 5
        
        # Skill match (if we have resume analysis)
        try:
            analysis = self.resume_analyzer.compare_resume_to_job(
                job.get('description', '')
            )
            score += analysis.match_score * 0.3  # Weighted skill match
        except Exception:
            pass
            
        return min(score, 100)
        
    def run_daily_workflow(self):
        """Run the complete daily job application workflow"""
        print("""
╔═══════════════════════════════════════════════════════════╗
║    🚀 Daily Job Application Workflow                      ║
║    Find, analyze, and apply to jobs automatically        ║
╚═══════════════════════════════════════════════════════════╝
        """)
        
        # Get current stats
        stats = self.bot.get_application_statistics()
        print(f"\n📊 Current Applications: {stats['total_applications']}")
        
        # Check if we should apply today
        today_apps = len([app for app in self.bot.applications 
                         if app.applied_date.startswith(datetime.now().strftime('%Y-%m-%d'))])
                         
        max_daily = self.config['max_applications_per_day']
        remaining = max_daily - today_apps
        
        if remaining <= 0:
            print(f"\n✅ You've reached your daily limit of {max_daily} applications.")
            return
            
        print(f"\n📝 You can apply to {remaining} more jobs today.")
        
        # Find best jobs
        print(f"\n🔍 Finding best matching jobs...")
        jobs = self.find_best_jobs(
            self.config['keywords'],
            self.config['locations'],
            limit=remaining
        )
        
        if not jobs:
            print("No matching jobs found.")
            return
            
        # Display top jobs
        print(f"\n📋 Found {len(jobs)} matching jobs:")
        for i, job in enumerate(jobs[:10], 1):
            title = job.get('title', 'Unknown')
            company = job.get('company', {}).get('name', 'Unknown')
            score = job.get('relevance_score', 0)
            print(f"  {i}. {title} at {company} (Score: {score:.0f}%)")
            
        # Apply to top jobs
        apply_count = min(len(jobs), remaining)
        print(f"\n🤖 Applying to top {apply_count} jobs...")
        
        results = self.bot.batch_apply(
            jobs[:apply_count],
            delay_seconds=self.config['delay_between_applications']
        )
        
        print(f"\n✅ Application round complete:")
        print(f"  • Successfully applied: {results['successful']}")
        print(f"  • Failed: {results['failed']}")
        print(f"  • Skipped (already applied): {results['skipped']}")
        
        # Update statistics
        new_stats = self.bot.get_application_statistics()
        print(f"\n📊 Updated Statistics:")
        print(f"  • Total Applications: {new_stats['total_applications']}")
        print(f"  • Today's Applications: {len([app for app in self.bot.applications if app.applied_date.startswith(datetime.now().strftime('%Y-%m-%d'))])}")
        
    def analyze_application_success(self):
        """Analyze application success patterns"""
        stats = self.bot.get_application_statistics()
        
        print("\n📊 Application Success Analysis:")
        print("="*50)
        
        if not self.bot.applications:
            print("No applications yet.")
            return
            
        # Status distribution
        print("\n📈 Status Distribution:")
        for status, count in stats['by_status'].items():
            percentage = count / stats['total_applications'] * 100
            print(f"  • {status}: {count} ({percentage:.1f}%)")
            
        # Top companies applied to
        print("\n🏢 Top Companies Applied To:")
        top_companies = sorted(stats['by_company'].items(), 
                             key=lambda x: x[1], reverse=True)[:10]
        for company, count in top_companies:
            print(f"  • {company}: {count}")
            
        # Application frequency
        print("\n📅 Application Frequency:")
        # Group by week
        weeks = {}
        for app in self.bot.applications:
            week = datetime.fromisoformat(app.applied_date).strftime('%Y-W%W')
            weeks[week] = weeks.get(week, 0) + 1
            
        for week, count in sorted(weeks.items())[-4:]:
            print(f"  • Week {week}: {count} applications")
            
def main():
    """Main entry point"""
    print("""
╔═══════════════════════════════════════════════════════════╗
║    🎯 Naukri Job Application Automation Workflow         ║
║    Complete automation for your job search               ║
╚═══════════════════════════════════════════════════════════╝
    """)
    
    # Get credentials
    token = input("Enter your Naukri authentication token: ").strip()
    resume_path = input("Enter path to your resume file: ").strip()
    
    if not token or not resume_path:
        print("❌ Token and resume path are required!")
        return
        
    workflow = JobApplicationWorkflow(token, resume_path)
    
    while True:
        print("\n" + "="*50)
        print("📋 Workflow Menu:")
        print("  1. Run daily application workflow")
        print("  2. Search and analyze jobs manually")
        print("  3. View application statistics")
        print("  4. Analyze success patterns")
        print("  5. Configure settings")
        print("  6. Exit")
        print("="*50)
        
        choice = input("Select option (1-6): ").strip()
        
        if choice == '1':
            workflow.run_daily_workflow()
            
        elif choice == '2':
            keyword = input("Enter job keyword: ")
            location = input("Enter location: ")
            jobs = workflow.bot.search_jobs(keyword, location, max_results=10)
            
            if jobs:
                print(f"\n📋 Found {len(jobs)} jobs:")
                for i, job in enumerate(jobs, 1):
                    title = job.get('title', 'Unknown')
                    company = job.get('company', {}).get('name', 'Unknown')
                    location = job.get('location', 'Unknown')
                    print(f"  {i}. {title} at {company} - {location}")
                    
                apply = input("\nApply to these jobs? (y/n): ").lower()
                if apply == 'y':
                    workflow.bot.batch_apply(jobs)
                    
        elif choice == '3':
            stats = workflow.bot.get_application_statistics()
            print(f"\n📊 Application Statistics:")
            print(f"  Total: {stats['total_applications']}")
            for status, count in stats['by_status'].items():
                print(f"  • {status}: {count}")
                
        elif choice == '4':
            workflow.analyze_application_success()
            
        elif choice == '5':
            print(f"\nCurrent configuration saved in job_config.json")
            print("Edit the file to update your preferences:")
            print("  • keywords: List of job keywords to search")
            print("  • locations: List of preferred locations")
            print("  • max_applications_per_day: Daily application limit")
            print("  • delay_between_applications: Delay in seconds")
            
        elif choice == '6':
            print("\n👋 Good luck with your job search!")
            break
            
        else:
            print("Invalid option. Please try again.")

if __name__ == "__main__":
    main()
