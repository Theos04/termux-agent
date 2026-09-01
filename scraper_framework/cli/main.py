# cli/main.py
"""CLI entry point for the scraper framework"""

import sys
from .commands import ScraperCLI
from scraper_framework.config.logging import setup_logging


def main():
    """Main CLI entry point"""
    # Setup logging
    setup_logging()
    
    # Run CLI
    cli = ScraperCLI()
    cli.run()


if __name__ == "__main__":
    main()
