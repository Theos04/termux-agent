"""Multi-partition scraper registry with thread safety"""

from typing import Dict, List, Optional, Set, Callable
from collections import defaultdict
import threading
import json
from pathlib import Path
import logging

from .models import ScraperConfig
from .exceptions import ScraperNotFoundError, PartitionNotFoundError

logger = logging.getLogger(__name__)


class ScraperRegistry:
    """Thread-safe multi-partition scraper registry"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._scrapers = defaultdict(dict)
                    cls._instance._partitions = set()
                    cls._instance._listeners = defaultdict(list)
                    cls._instance._loaded_defaults = False
        return cls._instance
    
    def __init__(self):
        """Initialize with default scrapers if not loaded"""
        if not self._loaded_defaults:
            self._load_default_scrapers()
            self._loaded_defaults = True
    
    def _load_default_scrapers(self):
        """Load default scrapers for all partitions"""
        from .defaults import DEFAULT_SCRAPERS
        
        for partition, scrapers in DEFAULT_SCRAPERS.items():
            for name, config in scrapers.items():
                self.add_scraper(config, partition)
        
        logger.info(f"✅ Loaded default scrapers across {len(DEFAULT_SCRAPERS)} partitions")
    
    def add_scraper(self, config: ScraperConfig, partition: str = "default"):
        """Add or update a scraper in a partition"""
        with self._lock:
            self._scrapers[partition][config.name] = config
            self._partitions.add(partition)
            self._notify_listeners('added', config, partition)
            logger.info(f"✅ Added scraper '{config.name}' to partition '{partition}'")
    
    def get_scraper(self, name: str, partition: str = "default") -> Optional[ScraperConfig]:
        """Get a scraper by name from a specific partition"""
        return self._scrapers.get(partition, {}).get(name)
    
    def get_scraper_or_raise(self, name: str, partition: str = "default") -> ScraperConfig:
        """Get a scraper or raise an exception if not found"""
        scraper = self.get_scraper(name, partition)
        if not scraper:
            raise ScraperNotFoundError(name, partition)
        return scraper
    
    def get_active_scrapers(self, partition: str = "default") -> List[ScraperConfig]:
        """Get all active scrapers in a partition"""
        return [s for s in self._scrapers.get(partition, {}).values() if s.active]
    
    def get_all_scrapers(self, partition: str = "default") -> Dict[str, ScraperConfig]:
        """Get all scrapers in a partition"""
        return dict(self._scrapers.get(partition, {}))
    
    def get_all_partitions(self) -> Set[str]:
        """Get all partition names"""
        return set(self._partitions)
    
    def remove_scraper(self, name: str, partition: str = "default"):
        """Remove a scraper from a partition"""
        with self._lock:
            if name in self._scrapers.get(partition, {}):
                config = self._scrapers[partition].pop(name)
                self._notify_listeners('removed', config, partition)
                logger.info(f"🗑️ Removed scraper '{name}' from partition '{partition}'")
                
                # Clean up empty partitions
                if not self._scrapers[partition]:
                    self._partitions.discard(partition)
    
    def update_scraper(self, name: str, updates: Dict, partition: str = "default") -> Optional[ScraperConfig]:
        """Update a scraper's configuration"""
        config = self.get_scraper(name, partition)
        if not config:
            return None
        
        with self._lock:
            for key, value in updates.items():
                if hasattr(config, key):
                    setattr(config, key, value)
            
            self._notify_listeners('updated', config, partition)
            logger.info(f"🔄 Updated scraper '{name}' in partition '{partition}'")
            return config
    
    def get_partition_stats(self, partition: str = "default") -> Dict:
        """Get statistics for a partition"""
        scrapers = self._scrapers.get(partition, {})
        active = [s for s in scrapers.values() if s.active]
        
        total_runs = sum(s.run_count for s in scrapers.values())
        total_success = sum(s.success_count for s in scrapers.values())
        total_errors = sum(s.error_count for s in scrapers.values())
        
        return {
            'partition': partition,
            'total_scrapers': len(scrapers),
            'active_scrapers': len(active),
            'total_runs': total_runs,
            'total_success': total_success,
            'total_errors': total_errors,
            'success_rate': f"{(total_success / total_runs * 100):.1f}%" if total_runs > 0 else "N/A"
        }
    
    def register_listener(self, callback: Callable, partition: Optional[str] = None):
        """Register a listener for scraper events"""
        key = partition or 'all'
        self._listeners[key].append(callback)
    
    def _notify_listeners(self, event: str, config: ScraperConfig, partition: str):
        """Notify listeners of scraper events"""
        for key, callbacks in self._listeners.items():
            if key == 'all' or key == partition:
                for callback in callbacks:
                    try:
                        callback(event, config, partition)
                    except Exception as e:
                        logger.error(f"Listener error: {e}")
    
    def save_to_file(self, path: str = "scrapers.json"):
        """Save registry to a JSON file"""
        data = {}
        for partition, scrapers in self._scrapers.items():
            data[partition] = {
                name: config.to_dict() for name, config in scrapers.items()
            }
        
        with open(path, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        logger.info(f"💾 Saved registry to {path}")
    
    def load_from_file(self, path: str = "scrapers.json"):
        """Load registry from a JSON file"""
        if not Path(path).exists():
            logger.warning(f"⚠️ File {path} not found")
            return
        
        with open(path, 'r') as f:
            data = json.load(f)
        
        for partition, scrapers in data.items():
            for name, config_data in scrapers.items():
                config = ScraperConfig.from_dict(config_data)
                self.add_scraper(config, partition)
        
        logger.info(f"📂 Loaded registry from {path}")


# ============================================================================
# Default Scraper Configurations
# ============================================================================

class DefaultScrapers:
    """Default scraper configurations for all partitions"""
    
    # Default partition
    DEFAULT = {
        'unstop_hackathons': ScraperConfig(
            name='unstop_hackathons',
            url='https://unstop.com/hackathons',
            schedule='0 */6 * * *',
            selectors={
                'hackathon_name': '.hackathon-card .title',
                'organizer': '.hackathon-card .organizer',
                'mode': '.hackathon-card .mode',
                'prize': '.hackathon-card .prize',
                'deadline': '.hackathon-card .deadline',
            }
        ),
        'unstop_jobs': ScraperConfig(
            name='unstop_jobs',
            url='https://unstop.com/jobs',
            schedule='0 */4 * * *',
            selectors={
                'job_title': '.job-card .title',
                'company': '.job-card .company',
                'location': '.job-card .location',
                'type': '.job-card .type',
                'deadline': '.job-card .deadline',
            }
        ),
        'github_trending': ScraperConfig(
            name='github_trending',
            url='https://github.com/trending',
            schedule='0 */6 * * *',
            selectors={
                'repo_name': '.h3 a',
                'description': '.col-9 .text-gray',
                'language': '.f6 .repo-language-color + span',
                'stars': '.f6 a[href*="stargazers"]',
            }
        ),
    }
    
    # Production partition
    PRODUCTION = {
        'linkedin_jobs': ScraperConfig(
            name='linkedin_jobs',
            url='https://www.linkedin.com/jobs/',
            schedule='0 */12 * * *',
            selectors={
                'job_title': '.job-card-list__title',
                'company': '.job-card-list__company-name',
                'location': '.job-card-list__location',
            },
            partition='production'
        ),
        'naukri_jobs': ScraperConfig(
            name='naukri_jobs',
            url='https://www.naukri.com/',
            schedule='0 */8 * * *',
            selectors={
                'job_title': '.jobTuple .title',
                'company': '.jobTuple .subTitle',
                'location': '.jobTuple .location',
                'salary': '.jobTuple .salary',
            },
            partition='production'
        ),
    }
    
    # Staging partition
    STAGING = {
        'devfolio_hackathons': ScraperConfig(
            name='devfolio_hackathons',
            url='https://devfolio.co/hackathons',
            schedule='0 */12 * * *',
            selectors={
                'hackathon_name': '.hackathon-card .name',
                'organizer': '.hackathon-card .organizer',
                'mode': '.hackathon-card .mode',
                'prize': '.hackathon-card .prize',
                'deadline': '.hackathon-card .deadline',
            },
            partition='staging'
        ),
    }
    
    @classmethod
    def get_all(cls) -> Dict[str, Dict[str, ScraperConfig]]:
        """Get all default scrapers by partition"""
        return {
            'default': cls.DEFAULT,
            'production': cls.PRODUCTION,
            'staging': cls.STAGING,
        }
