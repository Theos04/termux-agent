#!/usr/bin/env python3
"""
Job Scraper Script for Unstop
Connects to Chrome Daemon API and extracts job listings across all pages
"""

import asyncio
import json
import sys
import time
from datetime import datetime
from typing import List, Dict, Any, Optional
import aiohttp
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('job_scraper.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


class UnstopScraper:
    """Scraper for Unstop job listings using Chrome Daemon API"""
    
    def __init__(self, api_url: str = "http://localhost:5000", session_name: str = "unstop", target_url: str = None):
        """
        Initialize the scraper
        
        Args:
            api_url: Base URL for the API server
            session_name: Name of the Chrome session to use
            target_url: URL to scrape (default: https://unstop.com/opportunities)
        """
        self.api_url = api_url.rstrip('/')
        self.session_name = session_name
        self.target_url = target_url or "https://unstop.com/opportunities"
        self.session = None
        self.all_jobs = []
        self.page_number = 1
        self.browser_id = None
        self.ws_id = None
        
    async def __aenter__(self):
        """Async context manager entry"""
        self.session = aiohttp.ClientSession()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.session:
            await self.session.close()
            
    async def health_check(self) -> bool:
        """Check if the API server is running"""
        try:
            async with self.session.get(f"{self.api_url}/health", timeout=5) as resp:
                if resp.status == 200:
                    logger.info("✅ API server is healthy")
                    return True
                else:
                    logger.error(f"API server returned status {resp.status}")
                    return False
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False
            
    async def get_session_status(self) -> Dict[str, Any]:
        """
        Get status of the Unstop session
        
        Returns:
            Session status information
        """
        try:
            async with self.session.get(
                f"{self.api_url}/session/{self.session_name}/status",
                timeout=10
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    logger.error(f"Failed to get session status: {resp.status}")
                    return {}
        except Exception as e:
            logger.error(f"Error getting session status: {e}")
            return {}
            
    async def ensure_session_running(self) -> bool:
        """
        Ensure the Unstop session is running and ready
        
        Returns:
            True if session is ready, False otherwise
        """
        # Get session status
        status = await self.get_session_status()
        
        if not status:
            logger.error("Could not get session status")
            return False
            
        # Check if session is running
        if status.get('status') != 'running':
            logger.warning(f"⚠️ Session '{self.session_name}' is not running (status: {status.get('status')})")
            logger.info("\n📌 To start the session:")
            logger.info("  1. Run: python cdpv119.py")
            logger.info("  2. Select option 2 (Start Session)")
            logger.info("  3. Enter session ID: 6 (for unstop)")
            logger.info("  4. Wait for Chrome to start")
            logger.info("  5. Press Enter to continue when Chrome is ready")
            logger.info("\n💡 Or if you're using a different session, specify it with --session SESSION_NAME")
            return False
            
        # Extract WebSocket ID
        ws_ids = status.get('webSocketIds', [])
        if ws_ids:
            self.ws_id = ws_ids[0]
            logger.info(f"✅ Session is running with WebSocket ID: {self.ws_id}")
        else:
            logger.warning("No WebSocket ID found for session")
            
        self.browser_id = self.session_name
        return True
        
    async def execute_javascript(self, script: str) -> Dict[str, Any]:
        """
        Execute JavaScript in the Unstop session
        
        Args:
            script: JavaScript code to execute
            
        Returns:
            Result from the JavaScript execution
        """
        payload = {
            "script": script
        }
        
        try:
            async with self.session.post(
                f"{self.api_url}/session/{self.session_name}/evaluate",
                json=payload,
                timeout=30
            ) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    return result
                else:
                    error_text = await resp.text()
                    logger.error(f"Failed to execute JavaScript: {error_text}")
                    return {"error": error_text}
        except Exception as e:
            logger.error(f"Error executing JavaScript: {e}")
            return {"error": str(e)}
            
    async def navigate_to_url(self, url: str) -> bool:
        """
        Navigate to a URL in the browser
        
        Args:
            url: URL to navigate to
            
        Returns:
            Success status
        """
        script = f"""
        (function() {{
            console.log("Navigating to: {url}");
            window.location.href = "{url}";
            return true;
        }})();
        """
        
        result = await self.execute_javascript(script)
        
        if "error" in result:
            logger.error(f"Navigation failed: {result.get('error')}")
            return False
            
        # Wait for page to load
        logger.info(f"⏳ Waiting for page to load...")
        await asyncio.sleep(5)
        logger.info(f"✅ Navigated to: {url}")
        return True
        
    def parse_jobs(self, result: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Parse job listings from JavaScript execution result
        
        Args:
            result: Result from execute_javascript
            
        Returns:
            List of job dictionaries
        """
        if "error" in result:
            logger.error(f"Error in result: {result['error']}")
            return []
            
        if "result" not in result:
            logger.warning("No result in response")
            return []
            
        try:
            # The result might be a string representation of JSON
            data = result["result"]
            if isinstance(data, str):
                data = json.loads(data)
                
            if isinstance(data, dict):
                jobs = data.get("jobs", [])
                timestamp = data.get("timestamp", "")
                logger.info(f"📋 Extracted {len(jobs)} jobs from page {self.page_number} (timestamp: {timestamp})")
                return jobs
            else:
                logger.warning(f"Unexpected data format: {type(data)}")
                return []
                
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON: {e}")
            return []
        except Exception as e:
            logger.error(f"Error parsing jobs: {e}")
            return []
            
    def save_results(self, filename: Optional[str] = None):
        """
        Save all scraped jobs to a JSON file
        
        Args:
            filename: Output filename (auto-generated if not provided)
        """
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"unstop_jobs_{timestamp}.json"
            
        output_data = {
            "total_jobs": len(self.all_jobs),
            "scraped_at": datetime.now().isoformat(),
            "source": self.target_url,
            "pages_scraped": self.page_number,
            "jobs": self.all_jobs
        }
        
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(output_data, f, indent=2, ensure_ascii=False)
            logger.info(f"💾 Saved {len(self.all_jobs)} jobs to {filename}")
            print(f"\n✅ Results saved to: {filename}")
        except Exception as e:
            logger.error(f"Failed to save results: {e}")
            
    async def scrape_all_pages(self) -> int:
        """
        Scrape all pages of job listings
        
        Returns:
            Total number of jobs scraped
        """
        # Navigate to the URL
        if not await self.navigate_to_url(self.target_url):
            logger.error("Failed to navigate to URL")
            return 0
            
        self.page_number = 1
        
        while True:
            logger.info(f"\n📄 Scraping page {self.page_number}")
            
            # Read the get-job-list script
            try:
                with open('get-job-list.js', 'r') as f:
                    get_jobs_script = f.read()
            except FileNotFoundError:
                logger.error("❌ get-job-list.js not found in current directory")
                logger.info("   Please ensure the file exists in: " + os.getcwd())
                return 0
                
            # Execute the get-job-list script
            result = await self.execute_javascript(get_jobs_script)
            
            # Parse and save jobs
            jobs = self.parse_jobs(result)
            if jobs:
                self.all_jobs.extend(jobs)
                logger.info(f"✅ Page {self.page_number}: Found {len(jobs)} jobs (Total: {len(self.all_jobs)})")
                
                # Print first few jobs as preview
                for i, job in enumerate(jobs[:3]):
                    logger.info(f"   {i+1}. {job.get('title', 'N/A')} - {job.get('company', 'N/A')}")
            else:
                logger.warning(f"⚠️ No jobs found on page {self.page_number}")
                break
                
            # Try to go to next page
            logger.info(f"➡️ Attempting to navigate to page {self.page_number + 1}")
            
            # Read the pagination script
            try:
                with open('pagination_on.js', 'r') as f:
                    pagination_script = f.read()
            except FileNotFoundError:
                logger.error("❌ pagination_on.js not found in current directory")
                break
                
            pagination_result = await self.execute_javascript(pagination_script)
            
            # Check if we've reached the last page
            if pagination_result.get("result", {}).get("success") == False:
                reason = pagination_result.get("result", {}).get("reason", "unknown")
                logger.info(f"🏁 Reached last page: {reason}")
                break
                
            # Check if navigation was successful
            if pagination_result.get("result", {}).get("success") == True:
                new_page = pagination_result.get("result", {}).get("page", self.page_number + 1)
                logger.info(f"✅ Navigated to page {new_page}")
                self.page_number = new_page
                
                # Wait for page to load
                await asyncio.sleep(3)
            else:
                logger.error("❌ Failed to navigate to next page")
                break
                
        logger.info(f"\n🎉 Scraping complete. Total pages: {self.page_number}, Total jobs: {len(self.all_jobs)}")
        return len(self.all_jobs)
        
    async def run(self, output_file: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Main execution method
        
        Args:
            output_file: Output filename for results
            
        Returns:
            List of all scraped job listings
        """
        try:
            # Check API health
            if not await self.health_check():
                logger.error("API server is not responding")
                return []
                
            # Ensure session is running
            if not await self.ensure_session_running():
                logger.error("Failed to ensure session is running")
                return []
                
            # Start scraping
            await self.scrape_all_pages()
            
            # Save results
            self.save_results(output_file)
            
            return self.all_jobs
            
        except KeyboardInterrupt:
            logger.info("\n⚠️ Scraping interrupted by user")
            if self.all_jobs:
                logger.info(f"Saving {len(self.all_jobs)} jobs collected so far...")
                self.save_results(output_file)
            return self.all_jobs
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            import traceback
            traceback.print_exc()
            return self.all_jobs


async def main():
    """Main entry point"""
    import argparse
    import os
    
    parser = argparse.ArgumentParser(description="Unstop Job Scraper")
    parser.add_argument(
        "--api-url",
        default="http://localhost:5000",
        help="Base URL for the API server (default: http://localhost:5000)"
    )
    parser.add_argument(
        "--session",
        default="unstop",
        help="Chrome session name (default: unstop)"
    )
    parser.add_argument(
        "--url",
        default="https://unstop.com/opportunities",
        help="URL to start scraping from (default: https://unstop.com/opportunities)"
    )
    parser.add_argument(
        "--output",
        help="Output file for job data"
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        help="Maximum number of pages to scrape"
    )
    
    args = parser.parse_args()
    
    print("\n" + "="*70)
    print("🔍 Unstop Job Scraper")
    print("="*70)
    print(f"📡 API URL: {args.api_url}")
    print(f"🖥️  Session: {args.session}")
    print(f"🔗 Target URL: {args.url}")
    if args.max_pages:
        print(f"📄 Max pages: {args.max_pages}")
    print("="*70 + "\n")
    
    # Check if JavaScript files exist
    if not os.path.exists('get-job-list.js'):
        print("⚠️  Warning: get-job-list.js not found in current directory")
        print(f"   Current directory: {os.getcwd()}")
        print("   Please ensure the JavaScript files are in the correct location\n")
    
    if not os.path.exists('pagination_on.js'):
        print("⚠️  Warning: pagination_on.js not found in current directory")
        print(f"   Current directory: {os.getcwd()}")
        print("   Please ensure the JavaScript files are in the correct location\n")
    
    # Create scraper instance
    scraper = UnstopScraper(
        api_url=args.api_url, 
        session_name=args.session,
        target_url=args.url
    )
    
    async with scraper:
        # Run the scraper
        jobs = await scraper.run(output_file=args.output)
        
        print("\n" + "="*70)
        print(f"✅ Scraping complete! Found {len(jobs)} total jobs.")
        print("="*70)
        
        # Display a sample of jobs
        if jobs:
            print("\n📊 Sample of scraped jobs:")
            for i, job in enumerate(jobs[:5]):
                title = job.get('title', 'N/A')[:60]
                company = job.get('company', 'N/A')[:30]
                location = job.get('location', 'N/A')[:30]
                print(f"  {i+1}. {title}")
                print(f"     🏢 {company} | 📍 {location}")
                if job.get('salary') and job.get('salary') != 'N/A':
                    print(f"     💰 {job.get('salary')}")
                print()
            if len(jobs) > 5:
                print(f"  ... and {len(jobs) - 5} more jobs")
        else:
            print("\n⚠️ No jobs were found. Please check:")
            print("  1. The session is properly started")
            print("  2. The URL is correct and accessible")
            print("  3. The JavaScript selectors match the page structure")
            print("  4. The page loads properly in the browser")


if __name__ == "__main__":
    asyncio.run(main())
