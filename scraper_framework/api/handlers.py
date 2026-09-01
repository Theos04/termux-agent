# api/handlers.py
"""API request handlers for scraper management"""

import json
import logging
from typing import Dict, Any
from aiohttp import web

from scraper_framework.core.registry import ScraperRegistry
from scraper_framework.core.engine import ScraperEngine
from scraper_framework.core.models import ScraperConfig
from scraper_framework.tasks.scrapers import run_scheduled_scraper, run_partition_scrapers
from scraper_framework.storage.partition_manager import PartitionStorageManager

logger = logging.getLogger(__name__)


class ScraperHandlers:
    """Request handlers for scraper API endpoints"""
    
    def __init__(self, partition: str = "default"):
        self.partition = partition
        self.registry = ScraperRegistry()
        self.storage = PartitionStorageManager()
    
    async def list_scrapers(self, request: web.Request) -> web.Response:
        """List all scrapers in a partition"""
        scrapers = self.registry.get_all_scrapers(self.partition)
        
        return web.json_response({
            'success': True,
            'partition': self.partition,
            'count': len(scrapers),
            'scrapers': [
                {
                    'name': name,
                    'url': config.url,
                    'schedule': config.schedule,
                    'active': config.active,
                    'last_run': config.last_run,
                    'run_count': config.run_count
                }
                for name, config in scrapers.items()
            ]
        })
    
    async def get_scraper(self, request: web.Request) -> web.Response:
        """Get a specific scraper"""
        name = request.match_info.get('name')
        config = self.registry.get_scraper(name, self.partition)
        
        if not config:
            return web.json_response({
                'success': False,
                'error': f'Scraper not found: {name}'
            }, status=404)
        
        return web.json_response({
            'success': True,
            'scraper': config.to_dict()
        })
    
    async def create_scraper(self, request: web.Request) -> web.Response:
        """Create a new scraper"""
        try:
            data = await request.json()
        except:
            return web.json_response({
                'success': False,
                'error': 'Invalid JSON'
            }, status=400)
        
        required = ['name', 'url', 'selectors']
        for field in required:
            if field not in data:
                return web.json_response({
                    'success': False,
                    'error': f'Missing required field: {field}'
                }, status=400)
        
        config = ScraperConfig(
            name=data['name'],
            url=data['url'],
            schedule=data.get('schedule', '0 */6 * * *'),
            selectors=data['selectors'],
            extract_after_navigation=data.get('extract_after_navigation', True),
            take_screenshot=data.get('take_screenshot', True),
            save_html=data.get('save_html', True),
            active=data.get('active', True),
            partition=self.partition,
            timeout=data.get('timeout', 60),
            retry_count=data.get('retry_count', 3)
        )
        
        self.registry.add_scraper(config, self.partition)
        
        return web.json_response({
            'success': True,
            'message': f'Scraper {config.name} created',
            'scraper': config.to_dict()
        }, status=201)
    
    async def update_scraper(self, request: web.Request) -> web.Response:
        """Update an existing scraper"""
        name = request.match_info.get('name')
        
        try:
            data = await request.json()
        except:
            return web.json_response({
                'success': False,
                'error': 'Invalid JSON'
            }, status=400)
        
        config = self.registry.get_scraper(name, self.partition)
        if not config:
            return web.json_response({
                'success': False,
                'error': f'Scraper not found: {name}'
            }, status=404)
        
        # Update fields
        updateable = ['url', 'schedule', 'selectors', 'extract_after_navigation',
                     'take_screenshot', 'save_html', 'active', 'timeout', 'retry_count']
        
        for field in updateable:
            if field in data:
                setattr(config, field, data[field])
        
        self.registry.add_scraper(config, self.partition)
        
        return web.json_response({
            'success': True,
            'message': f'Scraper {name} updated',
            'scraper': config.to_dict()
        })
    
    async def delete_scraper(self, request: web.Request) -> web.Response:
        """Delete a scraper"""
        name = request.match_info.get('name')
        
        config = self.registry.get_scraper(name, self.partition)
        if not config:
            return web.json_response({
                'success': False,
                'error': f'Scraper not found: {name}'
            }, status=404)
        
        self.registry.remove_scraper(name, self.partition)
        
        return web.json_response({
            'success': True,
            'message': f'Scraper {name} deleted'
        })
    
    async def run_scraper(self, request: web.Request) -> web.Response:
        """Run a scraper immediately"""
        name = request.match_info.get('name')
        
        config = self.registry.get_scraper(name, self.partition)
        if not config:
            return web.json_response({
                'success': False,
                'error': f'Scraper not found: {name}'
            }, status=404)
        
        # Submit to Celery
        task = run_scheduled_scraper.delay(name, self.partition)
        
        return web.json_response({
            'success': True,
            'task_id': task.id,
            'scraper_name': name,
            'status': 'submitted'
        })
    
    async def run_all(self, request: web.Request) -> web.Response:
        """Run all scrapers in this partition"""
        task = run_partition_scrapers.delay(self.partition)
        
        return web.json_response({
            'success': True,
            'task_id': task.id,
            'partition': self.partition,
            'status': 'submitted'
        })
    
    async def get_stats(self, request: web.Request) -> web.Response:
        """Get statistics for this partition"""
        stats = self.registry.get_partition_stats(self.partition)
        storage_stats = self.storage.get_stats(self.partition)
        
        return web.json_response({
            'success': True,
            'partition': self.partition,
            'scrapers': stats,
            'storage': storage_stats
        })
    
    async def get_results(self, request: web.Request) -> web.Response:
        """Get results from this partition"""
        limit = int(request.query.get('limit', 100))
        scraper_name = request.query.get('scraper')
        
        results = self.storage.get_results(
            self.partition,
            scraper_name,
            limit
        )
        
        return web.json_response({
            'success': True,
            'partition': self.partition,
            'count': len(results),
            'results': results
        })
    
    async def scrape_url(self, request: web.Request) -> web.Response:
        """Scrape a specific URL"""
        try:
            data = await request.json()
        except:
            return web.json_response({
                'success': False,
                'error': 'Invalid JSON'
            }, status=400)
        
        url = data.get('url')
        if not url:
            return web.json_response({
                'success': False,
                'error': 'URL required'
            }, status=400)
        
        from tasks.scrapers import scrape_specific_url
        
        task = scrape_specific_url.delay(
            url,
            data.get('selectors', {}),
            data.get('session_name'),
            data.get('take_screenshot', True),
            data.get('save_html', True),
            self.partition
        )
        
        return web.json_response({
            'success': True,
            'task_id': task.id,
            'url': url,
            'status': 'submitted'
        })
