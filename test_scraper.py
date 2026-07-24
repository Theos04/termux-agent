# test_scraper.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "models"))

from scraper import UnstopJobScraper
import json

def test_single_page():
    """Test scraping just one page"""
    scraper = UnstopJobScraper()
    
    print("🔍 Testing Unstop Job Scraper...")
    print("=" * 60)
    
    if not scraper.check_daemon():
        print("❌ Daemon not running. Start with: python api.py")
        return
    
    print("✅ Daemon is running")
    print("🔄 Scraping first page...")
    
    # Navigate and extract
    scraper.navigate_to_page("https://unstop.com/job/")
    page_data = scraper.extract_page_jobs()
    
    print(f"\n📊 Results:")
    print(f"   Page: {page_data.get('page', 1)}")
    print(f"   Total pages: {page_data.get('total_pages', 1)}")
    print(f"   Has next: {page_data.get('has_next', False)}")
    
    jobs = page_data.get('jobs', [])
    print(f"   Jobs found: {len(jobs)}")
    
    if jobs:
        print(f"\n📝 Sample jobs:")
        for i, job in enumerate(jobs[:5], 1):
            print(f"\n   {i}. {job.get('title', 'N/A')}")
            print(f"      Company: {job.get('company', 'N/A')}")
            print(f"      Location: {job.get('location', 'N/A')}")
            if job.get('job_type'):
                print(f"      Type: {job.get('job_type')}")
            if job.get('skills'):
                print(f"      Skills: {', '.join(job.get('skills', [])[:3])}")
            if job.get('url'):
                print(f"      URL: {job.get('url')}")
        
        # Validate with Pydantic
        parsed_jobs = scraper.parse_jobs(jobs)
        print(f"\n✅ Validated {len(parsed_jobs)} jobs with Pydantic")
        
        # Show first validated job
        if parsed_jobs:
            print(f"\n📊 First validated job:")
            job = parsed_jobs[0]
            print(f"   Title: {job.title}")
            print(f"   Company: {job.company}")
            print(f"   Location: {job.location}")
            print(f"   Type: {job.job_type}")
            if job.skills:
                print(f"   Skills: {', '.join(job.skills[:5])}")
    else:
        print("\n⚠️  No jobs found!")

if __name__ == "__main__":
    test_single_page()
