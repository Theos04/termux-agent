# storage/local.py
"""Local JSON file storage with partition support"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

from scraper_framework.core.models import ScrapeResult

logger = logging.getLogger(__name__)


class LocalStorage:
    """Local JSON file storage with partition awareness"""

    def __init__(self, partition: str = "default", data_dir: str = "data"):
        self.partition = partition
        self.data_dir = Path(data_dir) / partition
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.results_file = self.data_dir / "results.json"
        self.extracted_file = self.data_dir / "extracted_data.json"
        
        # Initialize files
        self._ensure_files()

    def _ensure_files(self):
        """Ensure data files exist"""
        for file in [self.results_file, self.extracted_file]:
            if not file.exists():
                with open(file, 'w') as f:
                    json.dump([], f)

    def save_result(self, result: ScrapeResult) -> bool:
        """Save a scrape result to local storage"""
        try:
            # Load existing results
            with open(self.results_file, 'r') as f:
                results = json.load(f)

            # Add new result
            result_dict = result.to_dict()
            result_dict['saved_at'] = datetime.now().isoformat()
            results.append(result_dict)

            # Save back
            with open(self.results_file, 'w') as f:
                json.dump(results, f, indent=2, default=str)

            # Save extracted data separately if successful
            if result.success and result.data:
                with open(self.extracted_file, 'r') as f:
                    extracted = json.load(f)

                extracted.append({
                    'scraper_name': result.scraper_name,
                    'timestamp': result.timestamp,
                    'partition': self.partition,
                    'data': result.data,
                    'saved_at': datetime.now().isoformat()
                })

                with open(self.extracted_file, 'w') as f:
                    json.dump(extracted, f, indent=2, default=str)

            logger.info(f"✅ Saved result to local storage (partition: {self.partition})")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to save to local storage: {e}")
            return False

    def get_results(self, scraper_name: Optional[str] = None, limit: int = 100) -> List[Dict]:
        """Get results from local storage"""
        try:
            with open(self.results_file, 'r') as f:
                results = json.load(f)

            # Filter by partition and scraper name
            filtered = [
                r for r in results
                if r.get('partition') == self.partition
                and (not scraper_name or r.get('scraper_name') == scraper_name)
            ]

            return filtered[-limit:]  # Return latest first

        except Exception as e:
            logger.error(f"❌ Failed to get results from local storage: {e}")
            return []

    def get_extracted_data(self, scraper_name: Optional[str] = None, limit: int = 100) -> List[Dict]:
        """Get extracted data from local storage"""
        try:
            with open(self.extracted_file, 'r') as f:
                data = json.load(f)

            filtered = [
                d for d in data
                if d.get('partition') == self.partition
                and (not scraper_name or d.get('scraper_name') == scraper_name)
            ]

            return filtered[-limit:]

        except Exception as e:
            logger.error(f"❌ Failed to get extracted data from local storage: {e}")
            return []

    def get_stats(self) -> Dict:
        """Get storage statistics"""
        results = self.get_results()
        success = len([r for r in results if r.get('success')])
        errors = len([r for r in results if not r.get('success')])

        return {
            'partition': self.partition,
            'storage': 'local_json',
            'data_dir': str(self.data_dir),
            'total_results': len(results),
            'success_count': success,
            'error_count': errors,
            'success_rate': f"{(success / len(results) * 100):.1f}%" if results else "N/A"
        }

    def clear(self) -> bool:
        """Clear all data for this partition"""
        try:
            for file in [self.results_file, self.extracted_file]:
                with open(file, 'w') as f:
                    json.dump([], f)
            logger.info(f"✅ Cleared local storage for partition '{self.partition}'")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to clear local storage: {e}")
            return False
