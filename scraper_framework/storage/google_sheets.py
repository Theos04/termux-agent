"""Google Sheets storage with partition support"""

import json
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from pathlib import Path

from google_sheets_db import get_db, GoogleSheetsDB
from scraper_framework.core.models import ScrapeResult

logger = logging.getLogger(__name__)


class GoogleSheetsStorage:
    """Google Sheets storage with partition awareness"""
    
    def __init__(self, partition: str = "default"):
        self.partition = partition
        self.db = None
        self._init_db()
    
    def _init_db(self):
        try:
            self.db = get_db(interactive=False)
            logger.info(f"✅ Google Sheets initialized for partition '{self.partition}'")
        except Exception as e:
            logger.error(f"❌ Failed to initialize Google Sheets: {e}")
            self.db = None
    
    def save_result(self, result: ScrapeResult):
        """Save a scrape result with partition tag"""
        if not self.db:
            logger.warning("⚠️ Database not available, skipping save")
            return False
        
        try:
            # Save to automation_results
            data = {
                'timestamp': result.timestamp,
                'automation_id': f'scraper_{result.scraper_name}',
                'partition': self.partition,
                'data': json.dumps(result.to_dict(), default=str),
                'status': 'success' if result.success else 'error'
            }
            self.db.insert_row('automation_results', data)
            
            # If successful, save extracted data
            if result.success and result.data:
                for key, value in result.data.items():
                    extracted_data = {
                        'session_id': f'scraper_{result.scraper_name}',
                        'partition': self.partition,
                        'data_key': key,
                        'data_value': json.dumps(value) if isinstance(value, (dict, list)) else str(value),
                        'data_type': type(value).__name__,
                        'captured_at': result.timestamp
                    }
                    self.db.insert_row('extracted_data', extracted_data)
            
            # Save screenshot
            if result.screenshot_path:
                screenshot_data = {
                    'session_id': f'scraper_{result.scraper_name}',
                    'partition': self.partition,
                    'filename': Path(result.screenshot_path).name,
                    'path': result.screenshot_path,
                    'captured_at': result.timestamp
                }
                self.db.insert_row('screenshots', screenshot_data)
            
            logger.info(f"✅ Saved result to Google Sheets (partition: {self.partition})")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to save to Google Sheets: {e}")
            return False
    
    def get_results(self, scraper_name: Optional[str] = None, limit: int = 100) -> List[Dict]:
        """Get results from Google Sheets for this partition"""
        if not self.db:
            return []
        
        try:
            all_results = self.db.get_all_rows('automation_results')
            
            # Filter by partition and optionally by scraper name
            filtered = [
                r for r in all_results 
                if r.get('partition') == self.partition
                and (not scraper_name or scraper_name in r.get('automation_id', ''))
            ]
            
            return filtered[:limit]
            
        except Exception as e:
            logger.error(f"❌ Failed to get results from Google Sheets: {e}")
            return []
    
    def get_stats(self) -> Dict:
        """Get storage statistics for this partition"""
        results = self.get_results()
        
        total = len(results)
        success = len([r for r in results if r.get('status') == 'success'])
        errors = len([r for r in results if r.get('status') == 'error'])
        
        return {
            'partition': self.partition,
            'storage': 'google_sheets',
            'total_results': total,
            'success_count': success,
            'error_count': errors,
            'success_rate': f"{(success / total * 100):.1f}%" if total > 0 else "N/A"
        }
