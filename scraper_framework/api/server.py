# api/server.py
"""API server for the scraper framework"""

from aiohttp import web
import json
import logging
from typing import Optional

from .routes import ScraperAPI
from scraper_framework.config.logging import setup_logging
from scraper_framework.config.settings import get_partition_config

logger = logging.getLogger(__name__)


def create_app(partition: str = "default") -> web.Application:
    """Create the API application"""
    app = web.Application()
    
    # Setup logging
    setup_logging(partition=partition)
    
    # Setup routes
    api = ScraperAPI(app, partition)
    
    # Root endpoint
    app.router.add_get('/', lambda r: web.json_response({
        'name': 'Scraper Framework API',
        'version': '1.0.0',
        'partition': partition,
        'endpoints': [
            f'/api/partitions/{partition}/scrapers',
            f'/api/partitions/{partition}/scrapers/{{name}}',
            f'/api/partitions/{partition}/scrapers/{{name}}/run',
            f'/api/partitions/{partition}/scrapers/run-all',
            f'/api/partitions/{partition}/stats',
            f'/api/partitions/{partition}/results',
        ]
    }))
    
    # Health check
    app.router.add_get('/health', lambda r: web.json_response({
        'status': 'healthy',
        'partition': partition
    }))
    
    logger.info(f"✅ API application created for partition '{partition}'")
    return app


def run_api_server(partition: str = "default", host: str = "0.0.0.0", port: int = 8080):
    """Run the API server"""
    app = create_app(partition)
    
    logger.info(f"🚀 Starting API server on {host}:{port}")
    web.run_app(app, host=host, port=port)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser()
    parser.add_argument('--partition', default='default')
    parser.add_argument('--host', default='0.0.0.0')
    parser.add_argument('--port', type=int, default=8080)
    args = parser.parse_args()
    
    run_api_server(args.partition, args.host, args.port)
