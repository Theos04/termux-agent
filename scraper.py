# scraper.py - Fixed CSV export
import asyncio
import json
import time
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path
import requests
import sys

# Add the models directory to Python path
sys.path.insert(0, str(Path(__file__).parent / "models"))

# Import from models folder
from job_model import Job, JobPage, JobScrapeResult
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
    
    def extract_page_jobs(self) -> Dict[str, Any]:
        """Extract jobs from current page using JavaScript - Working selectors"""
        
        # First, scroll to load all content
        self.scroll_to_load_all(max_scrolls=15)
        
        # JavaScript extraction code using the working selector
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
            
            // Check for pagination
            let hasNext = false;
            let totalPages = 1;
            
            // Look for pagination links
            const paginationLinks = document.querySelectorAll('.pagination a, .pager a, [class*="pagination"] a');
            let maxPage = 1;
            for (const link of paginationLinks) {
                const text = link.textContent.trim();
                const num = parseInt(text);
                if (!isNaN(num) && num > maxPage) {
                    maxPage = num;
                }
                if (text.toLowerCase().includes('next') || text === '>' || text === '→') {
                    if (!link.classList.contains('disabled') && !link.hasAttribute('disabled')) {
                        hasNext = true;
                    }
                }
            }
            
            // Check URL for page parameter
            const urlParams = new URLSearchParams(window.location.search);
            const currentPage = parseInt(urlParams.get('page')) || 1;
            
            // Check if there's a load more button
            const loadMore = document.querySelector('[class*="load-more"], [class*="show-more"]');
            if (loadMore && !loadMore.disabled && !loadMore.classList.contains('disabled')) {
                hasNext = true;
            }
            
            // If we found page numbers, use max as total pages
            if (maxPage > 1) {
                totalPages = maxPage;
            } else {
                // Try to find total from text
                const text = document.body.textContent;
                const match = text.match(/(\\d+)\\s*(?:of|out of)\\s*(\\d+)\\s*(?:pages?|results?)/i);
                if (match) {
                    totalPages = parseInt(match[2]);
                }
            }
            
            return {
                page: currentPage,
                total_pages: totalPages,
                has_next: hasNext,
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
            logger.info(f"Extracted {jobs_found} jobs from page")
            
            if jobs_found == 0:
                # Try a simpler approach - just get all links with job IDs
                simple_js = """
                (function() {
                    const jobs = [];
                    const links = document.querySelectorAll('a[href*="/jobs/"]');
                    const seen = new Set();
                    
                    links.forEach(link => {
                        const href = link.getAttribute('href');
                        if (href && !seen.has(href)) {
                            seen.add(href);
                            const fullUrl = href.startsWith('http') ? href : 'https://unstop.com' + href;
                            const match = href.match(/\\/jobs\\/([^\\/]+)/);
                            const title = link.textContent.trim();
                            
                            if (title && title.length > 3) {
                                jobs.push({
                                    title: title.slice(0, 100),
                                    company: 'Unknown',
                                    location: 'Remote',
                                    url: fullUrl,
                                    source_id: match ? match[1] : null
                                });
                            }
                        }
                    });
                    return { jobs: jobs, page: 1, total_pages: 1, has_next: false };
                })();
                """
                simple_result = self.client.evaluate(simple_js)
                extracted = simple_result.get('result', {}).get('result', {}).get('value', {})
                jobs_found = len(extracted.get('jobs', []))
                logger.info(f"Simple extraction found {jobs_found} jobs")
            
            if jobs_found == 0:
                # Save HTML for debugging
                html = self.client.evaluate("document.documentElement.outerHTML")
                if html:
                    debug_file = Path("debug_page.html")
                    with open(debug_file, 'w') as f:
                        f.write(html.get('result', {}).get('result', {}).get('value', ''))
                    logger.info(f"Saved page HTML to {debug_file} for debugging")
                    print(f"📄 Saved page HTML to {debug_file} for debugging")
            
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
                        continue  # Skip extra fields
                    elif value and isinstance(value, str):
                        cleaned_data[key] = value.strip()
                    else:
                        cleaned_data[key] = value
                
                job = Job(**cleaned_data)
                valid_jobs.append(job)
            except Exception as e:
                # If validation fails, try with minimum fields
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
            time.sleep(3)  # Extra wait for dynamic content
            
            return True
        except Exception as e:
            self.errors.append(f"Navigation exception: {str(e)}")
            logger.error(f"Navigation exception: {e}")
            return False
    
    def scrape_page(self, page_number: int) -> Optional[JobPage]:
        """Scrape a single page"""
        if page_number == 1:
            url = self.base_url
        else:
            url = f"{self.base_url}?page={page_number}"
        
        logger.info(f"Scraping page {page_number}: {url}")
        print(f"\n📄 Scraping page {page_number}...")
        
        if not self.navigate_to_page(url):
            return None
        
        # Extract jobs
        page_data = self.extract_page_jobs()
        
        if not page_data:
            logger.warning(f"No jobs found on page {page_number}")
            return JobPage(
                page_number=page_number,
                total_pages=1,
                jobs=[],
                has_next=False
            )
        
        # Parse jobs
        jobs = self.parse_jobs(page_data.get('jobs', []))
        
        # Get pagination info
        total_pages = page_data.get('total_pages', 1)
        has_next = page_data.get('has_next', False)
        
        logger.info(f"Found {len(jobs)} jobs on page {page_number}/{total_pages}")
        print(f"   Found {len(jobs)} jobs")
        
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
            self.total_pages = page_result.total_pages
            
            # If we have total pages info, and we've reached the last page
            if self.total_pages > 0 and page_number >= self.total_pages:
                has_next = False
            
            print(f"   Total jobs so far: {len(self.jobs)}")
            
            # Move to next page
            page_number += 1
            
            # Small delay between pages
            if has_next:
                print("   Loading next page...")
                time.sleep(3)
        
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
        
        # Save as CSV - fixed to only include specific fields
        csv_file = output_path / f"jobs_{timestamp}.csv"
        if result.jobs:
            import csv
            # Define exactly which fields to include in CSV
            fieldnames = ['title', 'company', 'location', 'url', 'posted_date', 
                         'job_type', 'eligibility', 'skills', 'source_id']
            
            with open(csv_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
                writer.writeheader()
                for job in result.jobs:
                    row = job.dict()
                    # Convert skills list to string
                    if isinstance(row.get('skills'), list):
                        row['skills'] = ', '.join(row.get('skills', []))
                    # Only keep fields we want
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
            
            # Add company summary
            if result.jobs:
                from collections import Counter
                companies = Counter([job.company for job in result.jobs if job.company])
                f.write("Top 10 Companies:\n")
                for company, count in companies.most_common(10):
                    f.write(f"  {company}: {count} jobs\n")
                
                # Add location summary
                f.write("\nTop 10 Locations:\n")
                locations = Counter([job.location for job in result.jobs if job.location])
                for location, count in locations.most_common(10):
                    f.write(f"  {location}: {count} jobs\n")
                
                # Add job type summary
                f.write("\nJob Types:\n")
                job_types = Counter([job.job_type for job in result.jobs if job.job_type])
                for job_type, count in job_types.most_common(5):
                    f.write(f"  {job_type}: {count} jobs\n")
        
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
