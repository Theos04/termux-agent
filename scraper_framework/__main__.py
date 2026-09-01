# scraper_framework/__main__.py
"""Package entry point for the scraper framework"""

import sys
import argparse

from scraper_framework.cli.commands import ScraperCLI
from scraper_framework.config.logging import setup_logging


def main():
    """Package entry point"""
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['cli', 'api', 'worker'], default='cli')
    parser.add_argument('--partition', default='default')
    parser.add_argument('--host', default='0.0.0.0')
    parser.add_argument('--port', type=int, default=8080)
    args = parser.parse_args()

    setup_logging(partition=args.partition)

    if args.mode == 'cli':
        cli = ScraperCLI()
        cli.run(sys.argv[1:])
    elif args.mode == 'api':
        from scraper_framework.api.server import run_api_server
        run_api_server(args.partition, args.host, args.port)
    elif args.mode == 'worker':
        # Start Celery worker
        import subprocess
        subprocess.run([
            'celery', '-A', 'celery_config', 'worker',
            '--loglevel=info',
            '--concurrency=2'
        ])


if __name__ == "__main__":
    main()
