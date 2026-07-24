# unstop_hackathon_scraper.py - Full pagination support for hackathons
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
from job_model_listing import JobListing, JobPage, JobScrapeResult
from client import ChromeClient

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class UnstopHackathonScraper:
    def __init__(self, daemon_url="http://127.0.0.1:5000"):
        self.client = ChromeClient(daemon_url)
        self.base_url = "https://unstop.com/hackathons?oppstatus=open"
        self.hackathons: List[Dict] = []
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

    def wait_for_content_update(self, previous_count: int, timeout: int = 30) -> bool:
        """Wait for content to update after pagination click"""
        start = time.time()
        while time.time() - start < timeout:
            try:
                # Check if hackathon cards have been updated
                card_count = self.client.evaluate("document.querySelectorAll('app-competition-listing').length")
                count = card_count.get('result', {}).get('result', {}).get('value', 0)

                # Also check if loading indicator is gone
                loading = self.client.evaluate("document.querySelector('.loading, .spinner, .loader')")
                is_loading = loading.get('result', {}).get('result', {}).get('value') is not None

                if count > previous_count and not is_loading:
                    return True

                # If count hasn't changed but loading is gone, wait a bit more
                if not is_loading:
                    time.sleep(1)
                    card_count = self.client.evaluate("document.querySelectorAll('app-competition-listing').length")
                    count = card_count.get('result', {}).get('result', {}).get('value', 0)
                    if count > previous_count:
                        return True

            except:
                pass
            time.sleep(1)
        return False

    def scroll_to_load_all(self, max_scrolls: int = 10):
        """Scroll to load all lazy-loaded content"""
        print("   Scrolling to load all hackathons...")

        previous_count = 0
        for i in range(max_scrolls):
            # Scroll down
            self.client.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(1.5)

            # Check how many cards are loaded
            card_count = self.client.evaluate("document.querySelectorAll('app-competition-listing').length")
            count = card_count.get('result', {}).get('result', {}).get('value', 0)

            print(f"   Scroll {i+1}: Found {count} hackathons so far")

            if count == previous_count and i > 0:
                print(f"   No new hackathons loaded, stopping scroll")
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
                print(f"   Reached bottom with {count} hackathons")
                break

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

            let totalPages = Math.max(...pageNumbers, currentPage);

            if (pageNumbers.length <= 1 && hasNext) {
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

            const totalPagesAttr = pagination.getAttribute('data-total-pages');
            if (totalPagesAttr) {
                const num = parseInt(totalPagesAttr);
                if (!isNaN(num) && num > totalPages) {
                    totalPages = num;
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

    def click_pagination_button(self, target_page: int) -> bool:
        """Click on a specific page number in the pagination"""
        js_code = f"""
        (function() {{
            const target = {target_page};
            const btn = [...document.querySelectorAll("app-pagination li.num .number")]
                .find(el => parseInt(el.textContent.trim(), 10) === target);

            if (!btn) {{
                return false;
            }}

            btn.dispatchEvent(new MouseEvent("click", {{
                bubbles: true,
                cancelable: true,
                view: window
            }}));

            return true;
        }})();
        """

        try:
            result = self.client.evaluate(js_code)
            clicked = result.get('result', {}).get('result', {}).get('value', False)
            if clicked:
                logger.info(f"Clicked page {target_page}")
                return True
            else:
                logger.warning(f"Could not find page {target_page} to click")
                return False
        except Exception as e:
            logger.error(f"Error clicking page {target_page}: {e}")
            return False

    def click_next_page(self) -> bool:
        """Click the next page button"""
        js_code = """
        (function() {
            const pagination = document.querySelector('app-pagination');
            if (!pagination) return false;

            const rightArrows = pagination.querySelectorAll('.right-arrow');
            for (let arrow of rightArrows) {
                if (!arrow.classList.contains('disabled')) {
                    const link = arrow.querySelector('a');
                    if (link) {
                        link.click();
                        return true;
                    }
                    arrow.click();
                    return true;
                }
            }

            const nextButtons = pagination.querySelectorAll('button, a');
            for (let btn of nextButtons) {
                const text = btn.textContent.trim().toLowerCase();
                if (text.includes('next') && !btn.disabled) {
                    btn.click();
                    return true;
                }
            }

            return false;
        })();
        """

        try:
            result = self.client.evaluate(js_code)
            clicked = result.get('result', {}).get('result', {}).get('value', False)
            if clicked:
                logger.info("Clicked next page button")
                return True
            else:
                logger.warning("Could not find next page button to click")
                return False
        except Exception as e:
            logger.error(f"Error clicking next page: {e}")
            return False

    def extract_page_hackathons(self, page_number: int = 1) -> Dict[str, Any]:
        """Extract hackathons from current page using JavaScript"""
        
        # First, scroll to load all content
        self.scroll_to_load_all(max_scrolls=15)

        # JavaScript extraction code for hackathons
        js_code = """
        (function() {
            const cards = document.querySelectorAll('app-competition-listing');
            console.log(`Found ${cards.length} hackathon cards`);

            const hackathons = [];

            cards.forEach((card, index) => {
                try {
                    const link = card.querySelector('a');

                    // Title
                    const title = card.querySelector('h3')?.textContent?.trim() || null;
                    
                    // Organization/company
                    const org = card.querySelector('p.single-wrap')?.textContent?.trim() || null;

                    // URL
                    const href = link?.href || null;
                    const fullUrl = href ? (href.startsWith('http') ? href : 'https://unstop.com' + href) : null;

                    // ID from URL or link ID
                    let sourceId = null;
                    if (link?.id) {
                        const match = link.id.match(/opp_(\\d+)/);
                        if (match) sourceId = match[1];
                    }
                    if (!sourceId && fullUrl) {
                        const match = fullUrl.match(/\\/hackathons\\/([^\\/]+)/);
                        if (match) sourceId = match[1];
                    }

                    // Location
                    const locationEl = card.querySelector('.job_location');
                    const location = locationEl?.textContent?.trim() || null;

                    // Image/logo
                    const image = card.querySelector('img')?.src || null;

                    // Skills/technologies
                    const skillElements = card.querySelectorAll('.chip_text');
                    const skills = Array.from(skillElements).map(el => el.textContent.trim());

                    // Tags (includes status, dates, etc.)
                    const tagElements = card.querySelectorAll('.tag-text');
                    const tags = Array.from(tagElements).map(el => el.textContent.trim());

                    // Parse tags for specific info
                    let status = null;
                    let startDate = null;
                    let endDate = null;
                    let daysLeft = null;
                    let participants = null;
                    let prizeMoney = null;

                    tags.forEach(tag => {
                        const tagLower = tag.toLowerCase();
                        if (tagLower.includes('open') || tagLower.includes('upcoming') || 
                            tagLower.includes('closed') || tagLower.includes('ongoing')) {
                            status = tag;
                        }
                        if (tagLower.includes('days left')) {
                            daysLeft = tag;
                        }
                        if (tagLower.includes('starts')) {
                            startDate = tag.replace(/starts?/i, '').trim();
                        }
                        if (tagLower.includes('ends') || tagLower.includes('closing')) {
                            endDate = tag.replace(/ends?|closing/i, '').trim();
                        }
                        if (tagLower.includes('participants') || tagLower.includes('teams')) {
                            participants = tag;
                        }
                        if (tagLower.includes('prize') || tagLower.includes('reward')) {
                            prizeMoney = tag;
                        }
                    });

                    // Extract from other fields
                    const otherFields = card.querySelector('.other_fields');
                    let mode = null;
                    let duration = null;

                    if (otherFields) {
                        const spans = otherFields.querySelectorAll('span, strong');
                        spans.forEach(el => {
                            const text = el.textContent.trim();
                            if (text === 'Online' || text === 'Offline' || text === 'Hybrid') {
                                mode = text;
                            }
                            if (text.includes('days') || text.includes('weeks') || text.includes('hours')) {
                                duration = text;
                            }
                        });
                    }

                    // Only add if we have at least title or org
                    if (title || org) {
                        hackathons.push({
                            title: title || 'Untitled Hackathon',
                            organization: org || 'Unknown Organization',
                            location: location || 'Online',
                            url: fullUrl,
                            status: status || 'Open',
                            start_date: startDate || null,
                            end_date: endDate || null,
                            days_left: daysLeft || null,
                            mode: mode || null,
                            duration: duration || null,
                            participants: participants || null,
                            prize_money: prizeMoney || null,
                            skills: skills.length > 0 ? skills : null,
                            image: image || null,
                            tags: tags,
                            source_id: sourceId,
                            description: `${title || 'Hackathon'} by ${org || 'Unknown'}`
                        });
                    }
                } catch (e) {
                    console.error('Error extracting hackathon:', e);
                }
            });

            console.log(`Extracted ${hackathons.length} hackathons`);
            return { hackathons: hackathons };
        })();
        """

        try:
            result = self.client.evaluate(js_code)

            if 'error' in result:
                self.errors.append(f"Extraction error: {result['error']}")
                logger.error(f"Extraction error: {result['error']}")
                return {}

            extracted = result.get('result', {}).get('result', {}).get('value', {})
            hackathons_found = len(extracted.get('hackathons', []))
            logger.info(f"Extracted {hackathons_found} hackathons from page {page_number}")

            return extracted

        except Exception as e:
            self.errors.append(f"Extraction exception: {str(e)}")
            logger.error(f"Extraction exception: {e}")
            return {}

    def parse_hackathons(self, hackathon_data: List[Dict]) -> List[JobListing]:
        """Parse raw hackathon data into Pydantic models"""
        valid_hackathons = []
        for data in hackathon_data:
            try:
                # Map hackathon fields to JobListing model
                cleaned_data = {
                    'title': data.get('title', 'Untitled Hackathon'),
                    'company': data.get('organization', 'Unknown Organization'),
                    'location': data.get('location', 'Online'),
                    'url': data.get('url'),
                    'posted_date': data.get('start_date') or data.get('end_date'),
                    'description': data.get('description', ''),
                    'job_type': data.get('mode') or data.get('status'),
                    'eligibility': data.get('duration') or data.get('participants'),
                    'skills': data.get('skills', []) if data.get('skills') else [],
                    'source_id': data.get('source_id')
                }

                job = JobListing(**cleaned_data)
                valid_hackathons.append(job)
            except Exception as e:
                try:
                    # Fallback with minimal fields
                    job = JobListing(
                        title=data.get('title', 'Untitled Hackathon'),
                        company=data.get('organization', 'Unknown Organization'),
                        location=data.get('location', 'Online')
                    )
                    valid_hackathons.append(job)
                except Exception as e2:
                    self.errors.append(f"Fallback validation failed: {e2}")

        logger.info(f"Validated {len(valid_hackathons)} hackathons")
        return valid_hackathons

    def navigate_to_page(self, url: str) -> bool:
        """Navigate to a specific page"""
        try:
            result = self.client.navigate(url)
            if 'error' in result:
                self.errors.append(f"Navigation error: {result['error']}")
                logger.error(f"Navigation error: {result['error']}")
                return False

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

    def scrape_page(self, page_number: int, initial_load: bool = False) -> Optional[JobPage]:
        """Scrape a single page"""
        if initial_load:
            url = self.base_url
            logger.info(f"Loading page {page_number}: {url}")
            print(f"\n📄 Loading page {page_number}...")

            if not self.navigate_to_page(url):
                return None
        else:
            logger.info(f"Navigating to page {page_number} via pagination click")
            print(f"\n📄 Navigating to page {page_number} via pagination click...")

            current_count = self.client.evaluate("document.querySelectorAll('app-competition-listing').length")
            count_before = current_count.get('result', {}).get('result', {}).get('value', 0)

            if not self.click_pagination_button(page_number):
                if not self.click_next_page():
                    logger.error(f"Could not navigate to page {page_number}")
                    return None

            print("   Waiting for page to load...")
            if not self.wait_for_content_update(count_before, timeout=20):
                logger.warning("Content update timeout, continuing anyway")

            time.sleep(2)

        pagination = self.get_pagination_info()
        total_pages = pagination.get('total_pages', 1)
        has_next = pagination.get('has_next', False)

        page_data = self.extract_page_hackathons(page_number)

        if not page_data:
            logger.warning(f"No hackathons found on page {page_number}")
            return JobPage(
                page_number=page_number,
                total_pages=total_pages,
                jobs=[],
                has_next=has_next
            )

        hackathons = self.parse_hackathons(page_data.get('hackathons', []))

        logger.info(f"Found {len(hackathons)} hackathons on page {page_number}/{total_pages}")
        print(f"   Found {len(hackathons)} hackathons on page {page_number} of {total_pages}")

        return JobPage(
            page_number=page_number,
            total_pages=total_pages,
            jobs=hackathons,
            has_next=has_next
        )

    def scrape_all_pages(self, max_pages: int = 50) -> JobScrapeResult:
        """Scrape all pages until no more pages or max_pages reached"""
        start_time = datetime.now()

        logger.info("Starting Unstop hackathon scrape")
        print(f"\n🚀 Starting Unstop hackathon scrape at {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)

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

        page_number = 1
        has_next = True
        total_pages = 1

        while has_next and page_number <= max_pages:
            is_first_page = (page_number == 1)
            page_result = self.scrape_page(page_number, initial_load=is_first_page)

            if not page_result:
                self.errors.append(f"Failed to scrape page {page_number}")
                print(f"❌ Failed to scrape page {page_number}")
                break

            self.hackathons.extend(page_result.jobs)
            self.pages_scraped += 1

            has_next = page_result.has_next
            total_pages = page_result.total_pages

            if total_pages > 0 and page_number >= total_pages:
                has_next = False

            print(f"   Total hackathons so far: {len(self.hackathons)}")

            page_number += 1

            if has_next and page_number <= total_pages:
                print(f"   Preparing for page {page_number}...")
                time.sleep(2)

        result = JobScrapeResult(
            target_url=self.base_url,
            total_jobs=len(self.hackathons),
            pages_scraped=self.pages_scraped,
            jobs=self.hackathons,
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

        result_dict = result.dict()
        jobs_dict = [job.dict() for job in result.jobs]

        # Save full results
        json_file = output_path / f"hackathons_{timestamp}.json"
        with open(json_file, 'w') as f:
            json.dump(result_dict, f, indent=2, default=str)

        # Save just hackathons
        hackathons_file = output_path / f"hackathons_only_{timestamp}.json"
        with open(hackathons_file, 'w') as f:
            json.dump(jobs_dict, f, indent=2, default=str)

        # Save as CSV
        csv_file = output_path / f"hackathons_{timestamp}.csv"
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
        summary_file = output_path / f"hackathons_summary_{timestamp}.txt"
        with open(summary_file, 'w') as f:
            f.write("=" * 60 + "\n")
            f.write("Unstop Hackathon Scraping Summary\n")
            f.write("=" * 60 + "\n\n")
            f.write(f"Scraped at: {result.completed_at.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Total hackathons: {result.total_jobs}\n")
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

                organizations = Counter([job.company for job in result.jobs if job.company])
                f.write("Top 10 Organizations:\n")
                for org, count in organizations.most_common(10):
                    f.write(f"  {org}: {count} hackathons\n")

                f.write("\nTop 10 Locations:\n")
                locations = Counter([job.location for job in result.jobs if job.location])
                for location, count in locations.most_common(10):
                    f.write(f"  {location}: {count} hackathons\n")

                f.write("\nStatus Distribution:\n")
                statuses = Counter([job.job_type for job in result.jobs if job.job_type])
                for status, count in statuses.most_common(10):
                    f.write(f"  {status}: {count} hackathons\n")

                f.write("\nTop 20 Skills/Technologies:\n")
                all_skills = []
                for job in result.jobs:
                    all_skills.extend(job.skills)
                skills = Counter(all_skills)
                for skill, count in skills.most_common(20):
                    f.write(f"  {skill}: {count} hackathons\n")

        logger.info(f"Results saved to {output_dir}")
        print(f"\n📁 Results saved to:")
        print(f"   JSON: {json_file}")
        print(f"   CSV: {csv_file}")
        print(f"   Summary: {summary_file}")

        return {
            'json': str(json_file),
            'hackathons_only': str(hackathons_file),
            'csv': str(csv_file) if result.jobs else None,
            'summary': str(summary_file)
        }


def run_scraper():
    """Main function to be called from cron"""
    scraper = UnstopHackathonScraper()
    result = scraper.scrape_all_pages()

    files = scraper.save_results(result)

    print(f"\n📊 Final Summary:")
    print(f"   Total hackathons: {result.total_jobs}")
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
