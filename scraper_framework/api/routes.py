"""Partition-aware API routes"""

from aiohttp import web
import json
import logging
from typing import Dict, Optional

from scraper_framework.core.registry import ScraperRegistry
from scraper_framework.core.models import ScraperConfig
from scraper_framework.core.exceptions import ScraperNotFoundError
from scraper_framework.tasks.scrapers import (
    run_scheduled_scraper,
    run_partition_scrapers,
    run_all_partitions,
    scrape_specific_url
)
from scraper_framework.storage.google_sheets import GoogleSheetsStorage

logger = logging.getLogger(__name__)


class ScraperAPI:
    """Partition-aware scraper API"""
    
    def __init__(self, app: web.Application, partition: str = "default"):
        self.app = app
        self.partition = partition
        self.registry = ScraperRegistry()
        self.storage = GoogleSheetsStorage(partition)
        self.setup_routes()
    
    def setup_routes(self):
        """Setup all scraper API routes"""
        prefix = f"/api/partitions/{self.partition}"
        
        # Scraper management
        self.app.router.add_get(f'{prefix}/scrapers', self.list_scrapers)
        self.app.router.add_get(f'{prefix}/scrapers/{{name}}', self.get_scraper)
        self.app.router.add_post(f'{prefix}/scrapers', self.create_scraper)
        self.app.router.add_put(f'{prefix}/scrapers/{{name}}', self.update_scraper)
        self.app.router.add_delete(f'{prefix}/scrapers/{{name}}', self.delete_scraper)
        
        # Execution
        self.app.router.add_post(f'{prefix}/scrapers/{{name}}/run', self.run_scraper)
        self.app.router.add_post(f'{prefix}/scrapers/run-all', self.run_all)
        
        # Results
        self.app.router.add_get(f'{prefix}/results', self.get_results)
        self.app.router.add_get(f'{prefix}/results/{{scraper_name}}', self.get_scraper_results)
        
        # Stats
        self.app.router.add_get(f'{prefix}/stats', self.get_stats)
        
        # Custom URL scraping
        self.app.router.add_post(f'{prefix}/scrape', self.scrape_url)
    
    async def list_scrapers(self, request):
        """List all scrapers in this partition"""
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
                    'selectors': list(config.selectors.keys()),
                    'run_count': config.run_count,
                    'success_count': config.success_count,
                    'error_count': config.error_count,
                    'last_run': config.last_run
                }
                for name, config in scrapers.items()
            ]
        })
    
    async def get_scraper(self, request):
        """Get a specific scraper"""
        name = request.match_info['name']
        config = self.registry.get_scraper(name, self.partition)
        
        if not config:
            raise ScraperNotFoundError(name, self.partition)
        
        return web.json_response({
            'success': True,
            'partition': self.partition,
            'scraper': config.to_dict()
        })
    
    async def create_scraper(self, request):
        """Create a new scraper in this partition"""
        try:
            data = await request.json()
        except:
            return web.json_response({'error': 'Invalid JSON'}, status=400)
        
        # Validate required fields
        required = ['name', 'url', 'selectors']
        for field in required:
            if field not in data:
                return web.json_response({
                    'success': False,
                    'error': f'Missing required field: {field}'
                }, status=400)
        
        # Create scraper config
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
            'message': f'Scraper {config.name} created in partition {self.partition}',
            'scraper': config.to_dict()
        })
    
    async def update_scraper(self, request):
        """Update an existing scraper"""
        name = request.match_info['name']
        
        try:
            data = await request.json()
        except:
            return web.json_response({'error': 'Invalid JSON'}, status=400)
        
        config = self.registry.get_scraper(name, self.partition)
        if not config:
            return web.json_response({
                'success': False,
                'error': f'Scraper not found: {name} in partition {self.partition}'
            }, status=404)
        
        # Update fields
        updateable_fields = ['url', 'schedule', 'selectors', 'extract_after_navigation',
                           'take_screenshot', 'save_html', 'active', 'timeout', 'retry_count']
        
        for field in updateable_fields:
            if field in data:
                setattr(config, field, data[field])
        
        self.registry.add_scraper(config, self.partition)
        
        return web.json_response({
            'success': True,
            'message': f'Scraper {name} updated in partition {self.partition}',
            'scraper': config.to_dict()
        })
    
    async def delete_scraper(self, request):
        """Delete a scraper"""
        name = request.match_info['name']
        
        config = self.registry.get_scraper(name, self.partition)
        if not config:
            return web.json_response({
                'success': False,
                'error': f'Scraper not found: {name} in partition {self.partition}'
            }, status=404)
        
        self.registry.remove_scraper(name, self.partition)
        
        return web.json_response({
            'success': True,
            'message': f'Scraper {name} deleted from partition {self.partition}'
        })
    
    async def run_scraper(self, request):
        """Run a scraper immediately"""
        name = request.match_info['name']
        
        config = self.registry.get_scraper(name, self.partition)
        if not config:
            return web.json_response({
                'success': False,
                'error': f'Scraper not found: {name} in partition {self.partition}'
            }, status=404)
        
        # Submit task
        task = run_scheduled_scraper.delay(name, self.partition)
        
        return web.json_response({
            'success': True,
            'task_id': task.id,
            'scraper_name': name,
            'partition': self.partition,
            'status': 'submitted'
        })
    
    async def run_all(self, request):
        """Run all scrapers in this partition"""
        task = run_partition_scrapers.delay(self.partition)
        
        return web.json_response({
            'success': True,
            'task_id': task.id,
            'partition': self.partition,
            'status': 'submitted'
        })
    
    async def scrape_url(self, request):
        """Scrape a custom URL"""
        try:
            data = await request.json()
        except:
            return web.json_response({'error': 'Invalid JSON'}, status=400)
        
        url = data.get('url')
        selectors = data.get('selectors', {})
        
        if not url:
            return web.json_response({
                'success': False,
                'error': 'URL is required'
            }, status=400)
        
        if not selectors:
            return web.json_response({
                'success': False,
                'error': 'Selectors are required'
            }, status=400)
        
        task = scrape_specific_url.delay(
            url,
            selectors,
            data.get('session_name'),
            data.get('take_screenshot', True),
            data.get('save_html', True),
            self.partition,
            data.get('timeout', 60)
        )
        
        return web.json_response({
            'success': True,
            'task_id': task.id,
            'url': url,
            'partition': self.partition,
            'status': 'submitted'
        })
    
    async def get_results(self, request):
        """Get all results for this partition"""
        limit = int(request.query.get('limit', 100))
        results = self.storage.get_results(limit=limit)
        
        return web.json_response({
            'success': True,
            'partition': self.partition,
            'count': len(results),
            'results': results
        })
    
    async def get_scraper_results(self, request):
        """Get results for a specific scraper"""
        scraper_name = request.match_info['scraper_name']
        limit = int(request.query.get('limit', 100))
        
        results = self.storage.get_results(scraper_name, limit)
        
        return web.json_response({
            'success': True,
            'partition': self.partition,
            'scraper_name': scraper_name,
            'count': len(results),
            'results': results
        })
    
    async def get_stats(self, request):
        """Get statistics for this partition"""
        scrapers = self.registry.get_all_scrapers(self.partition)
        storage_stats = self.storage.get_stats()
        
        total_runs = sum(s.run_count for s in scrapers.values())
        total_success = sum(s.success_count for s in scrapers.values())
        total_errors = sum(s.error_count for s in scrapers.values())
        
        return web.json_response({
            'success': True,
            'partition': self.partition,
            'scrapers': {
                'total': len(scrapers),
                'active': len([s for s in scrapers.values() if s.active])
            },
            'execution': {
                'total_runs': total_runs,
                'success_count': total_success,
                'error_count': total_errors,
                'success_rate': f"{(total_success / total_runs * 100):.1f}%" if total_runs > 0 else "N/A"
            },
            'storage': storage_stats
        })
