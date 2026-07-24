# unstop_job_detail_scraper.py
import json
import time
import logging
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
import sys

# Add models to path
sys.path.insert(0, str(Path(__file__).parent / "models"))

# Updated imports
from job_model_listing import JobListing
from job_model_details import JobDetail
from client import ChromeClient

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class UnstopJobDetailScraper:
    def __init__(self, daemon_url="http://127.0.0.1:5000"):
        self.client = ChromeClient(daemon_url)
        self.details: List[JobDetail] = []  # Now storing JobDetail objects
        self.errors: List[str] = []

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

    def extract_job_details(self, url: str) -> Optional[Dict]:
        """Extract job details from a specific job URL"""
        logger.info(f"Extracting details from: {url}")

        try:
            result = self.client.navigate(url)
            if 'error' in result:
                self.errors.append(f"Navigation error for {url}: {result['error']}")
                return None

            time.sleep(3)
            if not self.wait_for_page_load(timeout=10):
                logger.warning(f"Page load timeout for {url}")
            time.sleep(2)

            js_code = """
            (function() {
                const details = {};

                const titleEl = document.querySelector('h1, .job-title, .opportunity-title');
                if (titleEl) details.title = titleEl.textContent.trim();

                const companyEl = document.querySelector('.company-name, .organization-name, .institute-name');
                if (companyEl) details.company = companyEl.textContent.trim();

                const locationEl = document.querySelector('.location, .job-location, .address');
                if (locationEl) details.location = locationEl.textContent.trim();

                const typeEl = document.querySelector('.job-type, .employment-type, .type');
                if (typeEl) details.job_type = typeEl.textContent.trim();

                const eligibilityEl = document.querySelector('.eligibility, .criteria, .qualification, [class*="eligibility"]');
                if (eligibilityEl) {
                    const items = eligibilityEl.querySelectorAll('li, p, span');
                    if (items.length > 0) {
                        details.eligibility = Array.from(items).map(el => el.textContent.trim()).filter(t => t);
                    } else {
                        details.eligibility = [eligibilityEl.textContent.trim()];
                    }
                }

                const rolesEl = document.querySelector('.roles, .responsibilities, .description, .job-description, [class*="role"]');
                if (rolesEl) {
                    const items = rolesEl.querySelectorAll('li, p, div');
                    if (items.length > 0) {
                        details.responsibilities = Array.from(items)
                            .map(el => el.textContent.trim())
                            .filter(t => t && t.length > 10);
                    } else {
                        details.responsibilities = [rolesEl.textContent.trim()];
                    }
                }

                const reqEl = document.querySelector('.requirements, .qualifications, .skills, .job-requirements');
                if (reqEl) {
                    const items = reqEl.querySelectorAll('li, p, span');
                    if (items.length > 0) {
                        details.requirements = Array.from(items)
                            .map(el => el.textContent.trim())
                            .filter(t => t && t.length > 5);
                    } else {
                        details.requirements = [reqEl.textContent.trim()];
                    }
                }

                const dateEl = document.querySelector('.posted-date, .publish-date, .date, .post-date');
                if (dateEl) details.posted_date = dateEl.textContent.trim();

                const deadlineEl = document.querySelector('.deadline, .apply-by, .last-date');
                if (deadlineEl) details.deadline = deadlineEl.textContent.trim();

                const skillElements = document.querySelectorAll('.skill, .tag, .badge, [class*="skill"], [class*="tag"]');
                if (skillElements.length > 0) {
                    details.skills = Array.from(skillElements)
                        .map(el => el.textContent.trim())
                        .filter(t => t && t.length > 0 && t.length < 50);
                }

                const mainContent = document.querySelector('main, .main-content, .content, .job-content');
                if (mainContent) {
                    details.full_description = mainContent.textContent.trim().slice(0, 5000);
                }

                const sections = document.querySelectorAll('h2, h3, h4, .section-title, .heading');
                const sectionData = {};
                sections.forEach(section => {
                    const title = section.textContent.trim();
                    if (title) {
                        let content = [];
                        let next = section.nextElementSibling;
                        while (next && !next.matches('h2, h3, h4, .section-title, .heading')) {
                            if (next.textContent.trim()) {
                                content.push(next.textContent.trim());
                            }
                            next = next.nextElementSibling;
                        }
                        if (content.length > 0) {
                            sectionData[title] = content;
                        }
                    }
                });
                details.sections = sectionData;

                return details;
            })();
            """

            result = self.client.evaluate(js_code)

            if 'error' in result:
                self.errors.append(f"Extraction error for {url}: {result['error']}")
                return None

            extracted = result.get('result', {}).get('result', {}).get('value', {})

            if extracted:
                extracted['url'] = url
                extracted['detail_url'] = url
                extracted['scraped_at'] = datetime.now().isoformat()
                extracted['detail_scraped_at'] = datetime.now().isoformat()

                logger.info(f"Successfully extracted details from {url}")

                detail_dir = Path("job_details")
                detail_dir.mkdir(exist_ok=True)
                job_id = url.split('/')[-1] if url else 'unknown'
                detail_file = detail_dir / f"{job_id}.json"
                with open(detail_file, 'w') as f:
                    json.dump(extracted, f, indent=2, default=str)

                return extracted

            return None

        except Exception as e:
            self.errors.append(f"Exception for {url}: {str(e)}")
            logger.error(f"Exception extracting details from {url}: {e}")
            return None

    def scrape_all_job_details(self, jobs_file: str = None, max_jobs: int = None):
        """Scrape details for all jobs from a jobs JSON file"""
        start_time = datetime.now()

        if jobs_file:
            with open(jobs_file, 'r') as f:
                data = json.load(f)
                if 'jobs' in data:
                    jobs = data['jobs']
                else:
                    jobs = data
        else:
            data_dir = Path("scraped_data")
            json_files = sorted(data_dir.glob("jobs_*.json"), reverse=True)
            if not json_files:
                logger.error("No jobs file found")
                return
            with open(json_files[0], 'r') as f:
                data = json.load(f)
                jobs = data.get('jobs', [])

        logger.info(f"Found {len(jobs)} jobs to process")

        if max_jobs:
            jobs = jobs[:max_jobs]
            logger.info(f"Limited to {max_jobs} jobs")

        if not self.check_daemon():
            logger.error("Chrome daemon is not running")
            return

        successful = 0
        for i, job in enumerate(jobs, 1):
            url = job.get('url')
            if not url:
                logger.warning(f"No URL for job {i}")
                continue

            logger.info(f"Processing job {i}/{len(jobs)}: {job.get('title', 'Unknown')}")

            details_data = self.extract_job_details(url)

            if details_data:
                try:
                    # Create JobDetail object
                    job_detail = JobDetail(**details_data)
                    self.details.append(job_detail)
                    successful += 1
                except Exception as e:
                    self.errors.append(f"Failed to create JobDetail for {url}: {str(e)}")

            time.sleep(2)

        logger.info(f"Successfully scraped {successful} out of {len(jobs)} job details")
        self.save_all_details()

        return self.details

    def save_all_details(self, output_dir: str = "job_details"):
        """Save all job details"""
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Convert JobDetail objects to dicts
        details_dicts = []
        for detail in self.details:
            if hasattr(detail, 'dict'):
                details_dicts.append(detail.dict())
            else:
                details_dicts.append(detail)

        combined_file = output_path / f"all_details_{timestamp}.json"
        with open(combined_file, 'w') as f:
            json.dump(details_dicts, f, indent=2, default=str)

        summary_file = output_path / f"details_summary_{timestamp}.txt"
        with open(summary_file, 'w') as f:
            f.write("=" * 60 + "\n")
            f.write("Job Details Scraping Summary\n")
            f.write("=" * 60 + "\n\n")
            f.write(f"Total jobs: {len(self.details)}\n")
            f.write(f"Errors: {len(self.errors)}\n\n")

            if self.errors:
                f.write("Errors:\n")
                for error in self.errors[:10]:
                    f.write(f"  - {error}\n")

        logger.info(f"Saved {len(self.details)} job details to {output_dir}")
        return str(combined_file)

def scrape_job_details_from_latest():
    """Scrape job details from the latest jobs file"""
    scraper = UnstopJobDetailScraper()

    data_dir = Path("scraped_data")
    json_files = sorted(data_dir.glob("jobs_*.json"), reverse=True)

    if not json_files:
        print("❌ No jobs file found. Run scraper.py first.")
        return

    latest_file = json_files[0]
    print(f"📂 Using jobs file: {latest_file}")
    print("🔄 Scraping details (limited to 5 for testing)...")
    print("   (Remove max_jobs parameter to scrape all)")

    results = scraper.scrape_all_job_details(str(latest_file))

    print(f"\n✅ Scraped {len(results)} job details")
    print(f"📁 Details saved to: job_details/")

    return results

if __name__ == "__main__":
    scrape_job_details_from_latest()
