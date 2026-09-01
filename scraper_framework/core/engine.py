import json
"""Scraper execution engine"""

import time
import logging
import traceback
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

from .models import ScraperConfig, ScrapeResult
from .registry import ScraperRegistry
from .exceptions import ScraperExecutionError, ScraperTimeoutError

# Import Chrome tasks
from chrome_tasks_enhanced import (
    start_chrome_session_task,
    stop_chrome_session_task,
    navigate_task,
    evaluate_task,
    extract_data_task,
    extract_multiple_task,
    screenshot_task,
    save_html_task,
)

# Import storage
from google_sheets_db import get_db

logger = logging.getLogger(__name__)


class ScraperEngine:
    """Core scraping engine that executes scrapers with partition support"""

    def __init__(self, partition: str = "default"):
        self.partition = partition
        self.db = None
        self.registry = ScraperRegistry()
        self._init_db()

    def _init_db(self):
        """Initialize database connection"""
        try:
            self.db = get_db(interactive=False)
            logger.info(f"✅ Database initialized for partition '{self.partition}'")
        except Exception as e:
            logger.error(f"❌ Failed to initialize database: {e}")
            self.db = None

    def _cleanup_session(self, session_name: str, timeout: int = 10) -> bool:
        """
        Clean up a Chrome session with proper error handling.
        
        Args:
            session_name: Name of the session to clean up
            timeout: Timeout in seconds
        
        Returns:
            True if cleanup was successful, False otherwise
        """
        if not session_name:
            logger.warning("⚠️ Cannot clean up session: session_name is None or empty")
            return False
        
        try:
            logger.debug(f"🧹 Cleaning up session: {session_name}")
            stop_result = stop_chrome_session_task.delay(session_name).get(timeout=timeout)
            
            if stop_result and stop_result.get('success'):
                logger.info(f"✅ Session cleaned up successfully: {session_name}")
                return True
            else:
                error_msg = stop_result.get('error', 'Unknown error') if stop_result else 'No result'
                logger.warning(f"⚠️ Session cleanup returned error: {error_msg}")
                return False
                
        except TimeoutError:
            logger.error(f"⏰ Timeout cleaning up session {session_name} (timeout={timeout}s)")
            return False
        except Exception as e:
            logger.error(f"❌ Failed to clean up session {session_name}: {e}")
            logger.debug(f"   Cleanup error details: {traceback.format_exc()}")
            return False

    def run_scraper(self, config: ScraperConfig) -> ScrapeResult:
        """
        Execute a single scraper synchronously
        This is the main scraping method - runs synchronously for Celery
        """
        start_time = time.time()
        session_name = config.session_name or f"scraper_{config.name}_{int(time.time())}"
        session_started = False  # Track if we successfully started the session

        logger.info(f"🔄 Running scraper: {config.name} (partition: {self.partition})")
        logger.info(f"   URL: {config.url}")
        logger.info(f"   Selectors: {list(config.selectors.keys())}")

        try:
            # 1. Start Chrome session
            logger.info(f"🚀 Starting session: {session_name}")
            start_result = start_chrome_session_task.delay(
                session_name, config.url
            ).get(timeout=config.timeout)

            if not start_result.get('success'):
                error_msg = start_result.get('error', 'Unknown error')
                raise ScraperExecutionError(f"Failed to start session: {error_msg}")
            
            session_started = True
            logger.info(f"✅ Session started: {session_name}")

            # 2. Navigate to URL (if needed)
            if config.url:
                nav_result = navigate_task.delay(
                    session_name, config.url, config.extract_after_navigation
                ).get(timeout=config.timeout)

                if not nav_result.get('success'):
                    error_msg = nav_result.get('error', 'Unknown error')
                    raise ScraperExecutionError(f"Failed to navigate: {error_msg}")

            # 3. Extract data
            extracted_data = {}
            if config.selectors:
                extract_result = extract_multiple_task.delay(
                    session_name,
                    config.selectors,
                    f"{config.name}_extract_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                ).get(timeout=config.timeout)

                if extract_result.get('success'):
                    extracted_data = extract_result.get('data', {})
                    logger.info(f"✅ Extracted {len(extracted_data)} fields from {config.name}")
                else:
                    error_msg = extract_result.get('error', 'Unknown error')
                    logger.warning(f"⚠️ Extraction failed: {error_msg}")

            # 4. Take screenshot
            screenshot_path = None
            if config.take_screenshot:
                try:
                    screenshot_result = screenshot_task.delay(
                        session_name, True
                    ).get(timeout=30)

                    if screenshot_result.get('success'):
                        screenshot_path = screenshot_result.get('saved_path')
                        logger.info(f"📸 Screenshot saved: {screenshot_path}")
                    else:
                        logger.warning(f"⚠️ Screenshot failed: {screenshot_result.get('error', 'Unknown error')}")
                except Exception as e:
                    logger.warning(f"⚠️ Screenshot error (continuing): {e}")

            # 5. Save HTML
            html_path = None
            if config.save_html:
                try:
                    html_result = save_html_task.delay(
                        session_name, True, f"{config.name}_html"
                    ).get(timeout=30)

                    if html_result.get('success'):
                        html_path = html_result.get('filepath')
                        logger.info(f"💾 HTML saved: {html_path}")
                    else:
                        logger.warning(f"⚠️ HTML save failed: {html_result.get('error', 'Unknown error')}")
                except Exception as e:
                    logger.warning(f"⚠️ HTML save error (continuing): {e}")

            # 6. Stop session (clean up)
            self._cleanup_session(session_name, timeout=30)
            session_started = False  # Session is now cleaned up

            # 7. Calculate duration
            duration = time.time() - start_time

            # 8. Create result
            result = ScrapeResult(
                scraper_name=config.name,
                timestamp=datetime.now().isoformat(),
                success=True,
                data=extracted_data,
                screenshot_path=screenshot_path,
                html_path=html_path,
                duration=duration,
                partition=self.partition,
                url=config.url
            )

            # 9. Update scraper stats
            config.run_count += 1
            config.success_count += 1
            config.last_run = result.timestamp
            self.registry.add_scraper(config, self.partition)

            # 10. Save to database
            self._save_result_to_db(config.name, result)

            logger.info(f"✅ Scraper {config.name} completed in {duration:.2f}s")
            return result

        except Exception as e:
            duration = time.time() - start_time
            error_msg = str(e)
            logger.error(f"❌ Scraper {config.name} failed: {error_msg}")
            logger.error(f"   Traceback: {traceback.format_exc()}")

            # Attempt to stop session if it was started
            if session_started:
                logger.info(f"🧹 Attempting to clean up session after error: {session_name}")
                cleanup_success = self._cleanup_session(session_name, timeout=15)
                if not cleanup_success:
                    logger.error(f"⚠️ Failed to clean up session {session_name} after error")
                    # Log to monitoring system if available
                    # Could also send alert here

            # Create failure result
            result = ScrapeResult(
                scraper_name=config.name,
                timestamp=datetime.now().isoformat(),
                success=False,
                data={},
                error=error_msg,
                duration=duration,
                partition=self.partition,
                url=config.url
            )

            # Update scraper stats
            config.run_count += 1
            config.error_count += 1
            config.last_run = result.timestamp
            self.registry.add_scraper(config, self.partition)

            # Save failure to database
            self._save_result_to_db(config.name, result)

            return result

        finally:
            # Ensure session is cleaned up even if something unexpected happens
            if session_started:
                try:
                    self._cleanup_session(session_name, timeout=10)
                except Exception as e:
                    logger.error(f"❌ Critical: Failed to clean up session {session_name} in finally block: {e}")

    def _save_result_to_db(self, scraper_name: str, result: ScrapeResult):
        """Save scraper result to Google Sheets with proper error handling"""
        if not self.db:
            logger.warning("⚠️ Database not available, skipping save")
            return

        try:
            # Save to automation_results with partition tag
            data = {
                'timestamp': result.timestamp,
                'automation_id': f'scraper_{scraper_name}',
                'partition': self.partition,
                'data': json.dumps(result.to_dict(), default=str),
                'status': 'success' if result.success else 'error'
            }
            self.db.insert_row('automation_results', data)

            # If successful, also save extracted data
            if result.success and result.data:
                for key, value in result.data.items():
                    extracted_data = {
                        'session_id': f'scraper_{scraper_name}',
                        'partition': self.partition,
                        'data_key': key,
                        'data_value': json.dumps(value) if isinstance(value, (dict, list)) else str(value),
                        'data_type': type(value).__name__,
                        'captured_at': result.timestamp
                    }
                    self.db.insert_row('extracted_data', extracted_data)

            # If screenshot, log it
            if result.screenshot_path:
                screenshot_data = {
                    'session_id': f'scraper_{scraper_name}',
                    'partition': self.partition,
                    'filename': Path(result.screenshot_path).name,
                    'path': result.screenshot_path,
                    'captured_at': result.timestamp
                }
                self.db.insert_row('screenshots', screenshot_data)

            logger.info(f"✅ Saved scraper result to database: {scraper_name} (partition: {self.partition})")

        except Exception as e:
            logger.error(f"❌ Failed to save scraper result to database: {e}")
