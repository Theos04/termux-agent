# storage/partition_manager.py
"""Multi-partition storage manager"""

import logging
from typing import Dict, List, Optional, Any
from pathlib import Path

from .google_sheets import GoogleSheetsStorage
from .local import LocalStorage

logger = logging.getLogger(__name__)


class PartitionStorageManager:
    """Manages storage across multiple partitions"""

    def __init__(self, config: Dict[str, str] = None):
        """
        Initialize storage manager
        
        Args:
            config: Partition to storage type mapping
                    e.g., {'default': 'google_sheets', 'production': 's3'}
        """
        self.config = config or {}
        self.storages: Dict[str, Any] = {}
        self._initialize_storages()

    def _initialize_storages(self):
        """Initialize storages based on configuration"""
        # Default storage type per partition
        default_types = {
            'default': 'google_sheets',
            'production': 'google_sheets',
            'staging': 'google_sheets',
            'testing': 'local',
        }

        # Merge with provided config
        storage_types = {**default_types, **self.config}

        for partition, storage_type in storage_types.items():
            if storage_type == 'google_sheets':
                self.storages[partition] = GoogleSheetsStorage(partition)
            elif storage_type == 'local':
                self.storages[partition] = LocalStorage(partition)
            # Add more storage types here (S3, etc.)

        logger.info(f"✅ Initialized {len(self.storages)} storage backends")

    def get_storage(self, partition: str = "default"):
        """Get storage instance for a partition"""
        if partition not in self.storages:
            # Create default storage for unknown partition
            self.storages[partition] = GoogleSheetsStorage(partition)
        return self.storages[partition]

    def save_result(self, result: Any, partition: str = "default"):
        """Save a result using the appropriate storage backend"""
        storage = self.get_storage(partition)
        return storage.save_result(result)

    def get_results(self, partition: str = "default", 
                    scraper_name: Optional[str] = None,
                    limit: int = 100) -> List[Dict]:
        """Get results from a partition"""
        storage = self.get_storage(partition)
        return storage.get_results(scraper_name, limit)

    def get_stats(self, partition: str = "default") -> Dict:
        """Get storage statistics for a partition"""
        storage = self.get_storage(partition)
        return storage.get_stats()

    def get_all_stats(self) -> Dict[str, Dict]:
        """Get statistics for all partitions"""
        stats = {}
        for partition in self.storages:
            stats[partition] = self.get_stats(partition)
        return stats
