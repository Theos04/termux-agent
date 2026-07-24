# scraper.py - Full pagination support
import asyncio
import json
import time
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path
import requests
import sys
import re

# Add the models directory to Python path
sys.path.insert(0, str(Path(__file__).parent / "models"))

# Import from models folder
from job_model import JobListing, JobPage, JobScrapeResult
from client import ChromeClient

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class UnstopJobScraper:
    def __init__(self, daemon_url="http://127.0.0.1:5000"):
        self.client = ChromeClient(daemon_url)
        self.base_url = "https://unstop.com/job/"
        self.jobs: List[Job] = []
        self.errors: List[str] = []
        self.total_pages = 0
        self.pages_scraped = 0
        
    def check_daemon(self) -> bool:
        """Check if daemon is running"""
        try:
            response = self.client.health()
            return 'status' in response and response['status'] == 'ok'
        except Exception as e:
            logger.error(f"Daemon check failed: {e}")
            return False
    
    def wait_for_page_load(self, timeout: int = 10) -> bool:
        """Wait for page to load"""
        start = time.time()
        while time.time() - start < timeout:
            try:
                result = self.client.evaluate("document.readyState")
                state = result.get('result', {}).get('result', {}).get('value')
                if state == 'complete':
                    return True
            except:
                pass
            time.sleep(0.5)
        return False
    
    def scroll_to_load_all(self, max_scrolls: int = 10):
        """Scroll to load all lazy-loaded content"""
        print("   Scrolling to load all content...")
        
        previous_count = 0
        for i in range(max_scrolls):
            # Scroll down
            self.client.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(1.5)
            
            # Check how many cards are loaded
            card_count = self.client.evaluate("document.querySelectorAll('app-competition-listing').length")
            count = card_count.get('result', {}).get('result', {}).get('value', 0)
            
            print(f"   Scroll {i+1}: Found {count} cards so far")
            
            # If count hasn't changed in 2 scrolls, we've loaded everything
            if count == previous_count and i > 0:
                print(f"   No new cards loaded, stopping scroll")
                break
            
            previous_count = count
            
            # Check if we've reached the bottom
            result = self.client.evaluate("""
                ({
                    scrollY: window.scrollY,
                    scrollHeight: document.body.scrollHeight,
                    innerHeight: window.innerHeight,
                    atBottom: window.scrollY + window.innerHeight >= document.body.scrollHeight - 100
                })
            """)
            
            at_bottom = result.get('result', {}).get('result', {}).get('value', {}).get('atBottom', False)
            
            if at_bottom and count > 0:
                print(f"   Reached bottom with {count} cards")
                break
            
            # Small delay before next scroll
            time.sleep(0.5)
        
        # Scroll back to top
        self.client.evaluate("window.scrollTo(0, 0)")
        time.sleep(1)
    
    def get_pagination_info(self) -> Dict[str, Any]:
        """Get pagination information from the page"""
        js_code = """
        (function() {
            const pagination = document.querySelector('app-pagination');
            if (!pagination) {
                return { has_pagination: false, current_page: 1, total_pages: 1, has_next: false };
            }
            
            // Get all page numbers
            const pageNumbers = [];
            const numberElements = pagination.querySelectorAll('.pagination-number ul li.num:not(.left-arrow):not(.right-arrow)');
            numberElements.forEach(el => {
                const span = el.querySelector('span.number');
                if (span) {
                    const text = span.textContent.trim();
                    const num = parseInt(text);
                    if (!isNaN(num)) {
                        pageNumbers.push(num);
                    }
                }
            });
            
            // Find active page
            let currentPage = 1;
            const activeEl = pagination.querySelector('.num.active');
            if (activeEl) {
                const span = activeEl.querySelector('span.number');
                if (span) {
                    const text = span.textContent.trim();
                    const num = parseInt(text);
                    if (!isNaN(num)) {
                        currentPage = num;
                    }
                }
            }
            
            // Find next/prev buttons
            let hasNext = false;
            let hasPrev = false;
            const rightArrows = pagination.querySelectorAll('.right-arrow');
            rightArrows.forEach(arrow => {
                if (!arrow.classList.contains('disabled')) {
                    hasNext = true;
                }
            });
            
            const leftArrows = pagination.querySelectorAll('.left-arrow');
            leftArrows.forEach(arrow => {
                if (!arrow.classList.contains('disabled')) {
                    hasPrev = true;
                }
            });
            
            // Total pages - use max page number
            let totalPages = Math.max(...pageNumbers, currentPage);
            
            // If only one page number found, check if there are more
            if (pageNumbers.length <= 1 && hasNext) {
                // Try to get total from the last page number
                const lastPageEl = pagination.querySelector('.pagination-number ul li.num:last-child');
                if (lastPageEl) {
                    const span = lastPageEl.querySelector('span.number');
                    if (span) {
                        const text = span.textContent.trim();
                        const num = parseInt(text);
                        if (!isNaN(num)) {
                            totalPages = num;
                        }
                    }
                }
            }
            
            return {
                has_pagination: true,
                current_page: currentPage,
                total_pages: totalPages,
                has_next: hasNext,
                has_prev: hasPrev,
                page_numbers: pageNumbers
            };
        })();
        """
        
        try:
            result = self.client.evaluate(js_code)
            return result.get('result', {}).get('result', {}).get('value', {})
        except Exception as e:
            logger.error(f"Error getting pagination info: {e}")
            return {}
    
    def extract_page_jobs(self, page_number: int = 1) -> Dict[str, Any]:
        """Extract jobs from current page using JavaScript"""
        
        # First, scroll to load all content
        self.scroll_to_load_all(max_scrolls=15)
        
        # JavaScript extraction code
        js_code = """
        (function() {
            // Use the working selector
            const cards = document.querySelectorAll('app-competition-listing');
            
            console.log(`Found ${cards.length} job cards`);
            
            const jobs = [];
            
            cards.forEach((card, index) => {
                try {
                    const link = card.querySelector('a');
                    
                    // Extract data
                    const title = card.querySelector('h3')?.textContent?.trim() || null;
                    const company = card.querySelector('p.single-wrap')?.textContent?.trim() || null;
                    const href = link?.href || null;
                    
                    // Full URL
                    const fullUrl = href ? (href.startsWith('http') ? href : 'https://unstop.com' + href) : null;
                    
                    // Get job ID from link id or URL
                    let sourceId = null;
                    if (link?.id) {
                        const match = link.id.match(/opp_(\\d+)/);
                        if (match) sourceId = match[1];
                    }
                    if (!sourceId && fullUrl) {
                        const match = fullUrl.match(/\\/jobs\\/([^\\/]+)/);
                        if (match) sourceId = match[1];
                    }
                    
                    // Experience
                    const experienceEl = card.querySelector('.other_fields strong');
                    let experience = null;
                    if (experienceEl) {
                        const expText = experienceEl.textContent.trim();
                        if (expText && !expText.includes('-')) {
                            const yearMatch = expText.match(/(\\d+)/);
                            if (yearMatch) {
                                experience = yearMatch[1] + ' years';
                            }
                        } else if (expText) {
                            experience = expText;
                        }
                    }
                    
                    // Employment type
                    const typeSpans = card.querySelectorAll('.other_fields span');
                    let employmentType = null;
                    typeSpans.forEach(span => {
                        const text = span.textContent.trim();
                        if (text === 'Full Time' || text === 'Internship' || 
                            text === 'Part Time' || text === 'Contract') {
                            employmentType = text;
                        }
                    });
                    
                    // Location
                    const locationEl = card.querySelector('.job_location');
                    const location = locationEl?.textContent?.trim() || null;
                    
                    // Image
                    const image = card.querySelector('img')?.src || null;
                    
                    // Skills
                    const skillElements = card.querySelectorAll('.chip_text');
                    const skills = Array.from(skillElements).map(el => el.textContent.trim());
                    
                    // Tags (includes posted date, days left, etc.)
                    const tagElements = card.querySelectorAll('.tag-text');
                    const tags = Array.from(tagElements).map(el => el.textContent.trim());
                    
                    // Find posted date from tags
                    let postedDate = null;
                    let daysLeft = null;
                    tags.forEach(tag => {
                        if (tag.includes('Posted')) {
                            postedDate = tag.replace('Posted', '').trim();
                        }
                        if (tag.includes('days left')) {
                            daysLeft = tag;
                        }
                    });
                    
                    // Only add if we have at least title or company
                    if (title || company) {
                        jobs.push({
                            title: title || 'Untitled',
                            company: company || 'Unknown Company',
                            location: location || 'Remote',
                            url: fullUrl,
                            posted_date: postedDate || null,
                            description: `${title || 'Job'} at ${company || 'Unknown'}`,
                            job_type: employmentType || null,
                            eligibility: experience || null,
                            skills: skills,
                            source_id: sourceId,
                            days_left: daysLeft,
                            image: image,
                            tags: tags
                        });
                    }
                } catch (e) {
                    console.error('Error extracting job:', e);
                }
            });
            
            console.log(`Extracted ${jobs.length} jobs`);
            
            return {
                jobs: jobs
            };
        })();
        """
        
        try:
            result = self.client.evaluate(js_code)
            
            if 'error' in result:
                self.errors.append(f"Extraction error: {result['error']}")
                logger.error(f"Extraction error: {result['error']}")
                return {}
            
            # Parse the result
            extracted = result.get('result', {}).get('result', {}).get('value', {})
            jobs_found = len(extracted.get('jobs', []))
            logger.info(f"Extracted {jobs_found} jobs from page {page_number}")
            
            return extracted
            
        except Exception as e:
            self.errors.append(f"Extraction exception: {str(e)}")
            logger.error(f"Extraction exception: {e}")
            return {}
    
    def parse_jobs(self, jobs_data: List[Dict]) -> List[Job]:
        """Parse raw job data into Pydantic models"""
        valid_jobs = []
        for job_data in jobs_data:
            try:
                # Clean up data before validation
                cleaned_data = {}
                for key, value in job_data.items():
                    if key == 'skills' and isinstance(value, list):
                        cleaned_data[key] = value
                    elif key in ['tags', 'image', 'days_left', 'raw_data']:
                        continue
                    elif value and isinstance(value, str):
                        cleaned_data[key] = value.strip()
                    else:
                        cleaned_data[key] = value
                
                job = Job(**cleaned_data)
                valid_jobs.append(job)
            except Exception as e:
                try:
                    job = Job(
                        title=job_data.get('title', 'Unknown'),
                        company=job_data.get('company', 'Unknown'),
                        location=job_data.get('location', 'Remote')
                    )
                    valid_jobs.append(job)
                except Exception as e2:
                    self.errors.append(f"Fallback validation failed: {e2}")
        
        logger.info(f"Validated {len(valid_jobs)} jobs")
        return valid_jobs
    
    def navigate_to_page(self, url: str) -> bool:
        """Navigate to a specific page"""
        try:
            result = self.client.navigate(url)
            if 'error' in result:
                self.errors.append(f"Navigation error: {result['error']}")
                logger.error(f"Navigation error: {result['error']}")
                return False
            
            # Wait for page to load
            print("   Waiting for page to load...")
            time.sleep(3)
            if not self.wait_for_page_load(timeout=15):
                logger.warning("Page load timeout, continuing anyway")
            time.sleep(3)
            
            return True
        except Exception as e:
            self.errors.append(f"Navigation exception: {str(e)}")
            logger.error(f"Navigation exception: {e}")
            return False
    
    def scrape_page(self, page_number: int) -> Optional[JobPage]:
        """Scrape a single page"""
        # Construct URL with page parameter
        if page_number == 1:
            url = self.base_url
        else:
            url = f"{self.base_url}?page={page_number}"
        
        logger.info(f"Scraping page {page_number}: {url}")
        print(f"\n📄 Scraping page {page_number}...")
        
        if not self.navigate_to_page(url):
            return None
        
        # Get pagination info
        pagination = self.get_pagination_info()
        total_pages = pagination.get('total_pages', 1)
        has_next = pagination.get('has_next', False)
        
        # Extract jobs
        page_data = self.extract_page_jobs(page_number)
        
        if not page_data:
            logger.warning(f"No jobs found on page {page_number}")
            return JobPage(
                page_number=page_number,
                total_pages=total_pages,
                jobs=[],
                has_next=has_next
            )
        
        # Parse jobs
        jobs = self.parse_jobs(page_data.get('jobs', []))
        
        logger.info(f"Found {len(jobs)} jobs on page {page_number}/{total_pages}")
        print(f"   Found {len(jobs)} jobs on page {page_number} of {total_pages}")
        
        return JobPage(
            page_number=page_number,
            total_pages=total_pages,
            jobs=jobs,
            has_next=has_next
        )
    
    def scrape_all_pages(self, max_pages: int = 50) -> JobScrapeResult:
        """Scrape all pages until no more pages or max_pages reached"""
        start_time = datetime.now()
        
        logger.info("Starting Unstop job scrape")
        print(f"\n🚀 Starting Unstop job scrape at {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)
        
        # Check daemon
        if not self.check_daemon():
            error = "Chrome daemon is not running"
            logger.error(error)
            print(f"❌ {error}")
            print("   Start with: python api.py")
            return JobScrapeResult(
                target_url=self.base_url,
                total_jobs=0,
                pages_scraped=0,
                jobs=[],
                errors=[error],
                started_at=start_time,
                completed_at=datetime.now()
            )
        
        print("✅ Chrome daemon is running")
        
        # Start from page 1
        page_number = 1
        has_next = True
        total_pages = 1
        
        while has_next and page_number <= max_pages:
            page_result = self.scrape_page(page_number)
            
            if not page_result:
                self.errors.append(f"Failed to scrape page {page_number}")
                print(f"❌ Failed to scrape page {page_number}")
                break
            
            # Add jobs
            self.jobs.extend(page_result.jobs)
            self.pages_scraped += 1
            
            # Update pagination info
            has_next = page_result.has_next
            total_pages = page_result.total_pages
            
            # If we have total pages info, and we've reached the last page
            if total_pages > 0 and page_number >= total_pages:
                has_next = False
            
            print(f"   Total jobs so far: {len(self.jobs)}")
            
            # Move to next page
            page_number += 1
            
            # Small delay between pages
            if has_next and page_number <= total_pages:
                print(f"   Moving to page {page_number}...")
                time.sleep(2)
        
        # Create result
        result = JobScrapeResult(
            target_url=self.base_url,
            total_jobs=len(self.jobs),
            pages_scraped=self.pages_scraped,
            jobs=self.jobs,
            errors=self.errors,
            started_at=start_time,
            completed_at=datetime.now(),
            duration_seconds=(datetime.now() - start_time).total_seconds()
        )
        
        logger.info(f"Scraping complete: {result.summary}")
        print(f"\n✅ Scraping complete!")
        print(f"   {result.summary}")
        return result
    
    def save_results(self, result: JobScrapeResult, output_dir: str = "scraped_data"):
        """Save results to files"""
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Convert result to dict (Pydantic v1 compatible)
        result_dict = result.dict()
        
        # Convert jobs to dict
        jobs_dict = [job.dict() for job in result.jobs]
        
        # Save full results
        json_file = output_path / f"jobs_{timestamp}.json"
        with open(json_file, 'w') as f:
            json.dump(result_dict, f, indent=2, default=str)
        
        # Save just jobs
        jobs_file = output_path / f"jobs_only_{timestamp}.json"
        with open(jobs_file, 'w') as f:
            json.dump(jobs_dict, f, indent=2, default=str)
        
        # Save as CSV
        csv_file = output_path / f"jobs_{timestamp}.csv"
        if result.jobs:
            import csv
            fieldnames = ['title', 'company', 'location', 'url', 'posted_date', 
                         'job_type', 'eligibility', 'skills', 'source_id']
            
            with open(csv_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
                writer.writeheader()
                for job in result.jobs:
                    row = job.dict()
                    if isinstance(row.get('skills'), list):
                        row['skills'] = ', '.join(row.get('skills', []))
                    filtered_row = {k: row.get(k, '') for k in fieldnames}
                    writer.writerow(filtered_row)
        
        # Save summary
        summary_file = output_path / f"summary_{timestamp}.txt"
        with open(summary_file, 'w') as f:
            f.write("=" * 60 + "\n")
            f.write("Unstop Job Scraping Summary\n")
            f.write("=" * 60 + "\n\n")
            f.write(f"Scraped at: {result.completed_at.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Total jobs: {result.total_jobs}\n")
            f.write(f"Pages scraped: {result.pages_scraped}\n")
            f.write(f"Duration: {result.duration_seconds:.2f} seconds\n")
            f.write(f"Errors: {len(result.errors)}\n\n")
            
            if result.errors:
                f.write("Errors:\n")
                for error in result.errors[:10]:
                    f.write(f"  - {error}\n")
                if len(result.errors) > 10:
                    f.write(f"  ... and {len(result.errors) - 10} more errors\n")
                f.write("\n")
            
            if result.jobs:
                from collections import Counter
                
                # Company summary
                companies = Counter([job.company for job in result.jobs if job.company])
                f.write("Top 10 Companies:\n")
                for company, count in companies.most_common(10):
                    f.write(f"  {company}: {count} jobs\n")
                
                # Location summary
                f.write("\nTop 10 Locations:\n")
                locations = Counter([job.location for job in result.jobs if job.location])
                for location, count in locations.most_common(10):
                    f.write(f"  {location}: {count} jobs\n")
                
                # Job type summary
                f.write("\nJob Types:\n")
                job_types = Counter([job.job_type for job in result.jobs if job.job_type])
                for job_type, count in job_types.most_common(5):
                    f.write(f"  {job_type}: {count} jobs\n")
                
                # Skills summary
                f.write("\nTop 20 Skills:\n")
                all_skills = []
                for job in result.jobs:
                    all_skills.extend(job.skills)
                skills = Counter(all_skills)
                for skill, count in skills.most_common(20):
                    f.write(f"  {skill}: {count} jobs\n")
        
        logger.info(f"Results saved to {output_dir}")
        print(f"\n📁 Results saved to:")
        print(f"   JSON: {json_file}")
        print(f"   CSV: {csv_file}")
        print(f"   Summary: {summary_file}")
        
        return {
            'json': str(json_file),
            'jobs_only': str(jobs_file),
            'csv': str(csv_file) if result.jobs else None,
            'summary': str(summary_file)
        }

def run_scraper():
    """Main function to be called from cron"""
    scraper = UnstopJobScraper()
    result = scraper.scrape_all_pages()
    
    # Save results
    files = scraper.save_results(result)
    
    # Print final summary
    print(f"\n📊 Final Summary:")
    print(f"   Total jobs: {result.total_jobs}")
    print(f"   Pages: {result.pages_scraped}")
    print(f"   Duration: {result.duration_seconds:.2f}s")
    print(f"   Errors: {len(result.errors)}")
    
    if result.errors:
        print(f"\n⚠️  Errors encountered:")
        for error in result.errors[:5]:
            print(f"   - {error}")
        if len(result.errors) > 5:
            print(f"   ... and {len(result.errors) - 5} more errors")
    
    return 0 if result.total_jobs > 0 else 1

if __name__ == "__main__":
    import sys
    sys.exit(run_scraper())
