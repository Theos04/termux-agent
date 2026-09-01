"""Configuration for partitions and scrapers"""

from typing import Dict, List, Optional
from dataclasses import dataclass, field


@dataclass
class PartitionConfig:
    """Configuration for a partition"""
    name: str
    queues: List[str] = field(default_factory=lambda: ['chrome_default'])
    concurrency: int = 2
    scrapers: List[str] = field(default_factory=list)
    storage: str = 'google_sheets'
    storage_config: Dict = field(default_factory=dict)
    retry_count: int = 3
    timeout: int = 60
    active: bool = True
    
    def to_dict(self) -> Dict:
        return {
            'name': self.name,
            'queues': self.queues,
            'concurrency': self.concurrency,
            'scrapers': self.scrapers,
            'storage': self.storage,
            'storage_config': self.storage_config,
            'retry_count': self.retry_count,
            'timeout': self.timeout,
            'active': self.active
        }


# Pre-configured partitions
PARTITIONS = {
    'default': PartitionConfig(
        name='default',
        queues=['chrome_default'],
        concurrency=2,
        scrapers=['unstop_hackathons', 'unstop_jobs', 'github_trending'],
        storage='google_sheets'
    ),
    'production': PartitionConfig(
        name='production',
        queues=['chrome_prod', 'storage_prod'],
        concurrency=4,
        scrapers=['linkedin_jobs', 'naukri_jobs', 'unstop_hackathons'],
        storage='google_sheets',
        retry_count=5,
        timeout=120
    ),
    'staging': PartitionConfig(
        name='staging',
        queues=['chrome_staging'],
        concurrency=2,
        scrapers=['devfolio_hackathons', 'unstop_jobs'],
        storage='google_sheets'
    ),
    'testing': PartitionConfig(
        name='testing',
        queues=['chrome_test'],
        concurrency=1,
        scrapers=[],
        storage='memory'
    ),
    'customer_a': PartitionConfig(
        name='customer_a',
        queues=['chrome_cust_a'],
        concurrency=2,
        scrapers=['unstop_jobs', 'naukri_jobs'],
        storage='google_sheets',
        storage_config={'sheet_id': 'customer_a_sheet_id'}
    ),
    'customer_b': PartitionConfig(
        name='customer_b',
        queues=['chrome_cust_b'],
        concurrency=2,
        scrapers=['linkedin_jobs', 'github_trending'],
        storage='s3',
        storage_config={'bucket': 'customer-b-scrapes'}
    )
}


def get_partition_config(partition_name: str = "default") -> PartitionConfig:
    """Get configuration for a partition"""
    return PARTITIONS.get(partition_name, PARTITIONS['default'])


def get_all_partition_configs() -> Dict[str, PartitionConfig]:
    """Get all partition configurations"""
    return PARTITIONS.copy()
