"""Command-line interface for scraper management"""

import argparse
import json
import sys
from typing import Optional

from scraper_framework.core.registry import ScraperRegistry
from scraper_framework.core.models import ScraperConfig
from scraper_framework.tasks.scrapers import run_scheduled_scraper, run_partition_scrapers
from scraper_framework.storage.google_sheets import GoogleSheetsStorage
from scraper_framework.config.settings import get_all_partition_configs


class ScraperCLI:
    """CLI for managing scrapers"""
    
    def __init__(self):
        self.registry = ScraperRegistry()
        self.parser = self._create_parser()
    
    def _create_parser(self):
        parser = argparse.ArgumentParser(
            description='Scraper Framework CLI',
            formatter_class=argparse.RawDescriptionHelpFormatter
        )
        
        parser.add_argument('--partition', default='default', 
                          help='Partition name (default: default)')
        parser.add_argument('--format', choices=['json', 'table'], default='table',
                          help='Output format')
        
        subparsers = parser.add_subparsers(dest='command', help='Commands')
        
        # List command
        list_parser = subparsers.add_parser('list', help='List scrapers')
        list_parser.add_argument('--active', action='store_true', 
                               help='Show only active scrapers')
        list_parser.add_argument('--all', action='store_true',
                               help='Show scrapers from all partitions')
        
        # Show command
        show_parser = subparsers.add_parser('show', help='Show scraper details')
        show_parser.add_argument('name', help='Scraper name')
        
        # Run command
        run_parser = subparsers.add_parser('run', help='Run a scraper')
        run_parser.add_argument('name', help='Scraper name')
        run_parser.add_argument('--async', action='store_true', 
                              help='Run asynchronously via Celery')
        
        # Run-all command
        run_all_parser = subparsers.add_parser('run-all', help='Run all scrapers in partition')
        run_all_parser.add_argument('--async', action='store_true',
                                  help='Run asynchronously via Celery')
        
        # Stats command
        stats_parser = subparsers.add_parser('stats', help='Show statistics')
        stats_parser.add_argument('--partition', help='Partition name')
        
        # Partitions command
        subparsers.add_parser('partitions', help='List all partitions')
        
        # Create command
        create_parser = subparsers.add_parser('create', help='Create a new scraper')
        create_parser.add_argument('--name', required=True, help='Scraper name')
        create_parser.add_argument('--url', required=True, help='URL to scrape')
        create_parser.add_argument('--schedule', default='0 */6 * * *', 
                                 help='Cron schedule')
        create_parser.add_argument('--selectors', required=True,
                                 help='JSON string of selectors')
        
        # Delete command
        delete_parser = subparsers.add_parser('delete', help='Delete a scraper')
        delete_parser.add_argument('name', help='Scraper name')
        delete_parser.add_argument('--force', action='store_true',
                                 help='Force delete without confirmation')
        
        # Test command
        test_parser = subparsers.add_parser('test', help='Test a scraper synchronously')
        test_parser.add_argument('name', help='Scraper name')
        
        # Results command
        results_parser = subparsers.add_parser('results', help='Show scraper results')
        results_parser.add_argument('--scraper', help='Filter by scraper name')
        results_parser.add_argument('--limit', type=int, default=20,
                                  help='Number of results to show')
        
        # Export command
        export_parser = subparsers.add_parser('export', help='Export configuration')
        export_parser.add_argument('--file', default='scrapers_export.json',
                                 help='Output file path')
        
        return parser
    
    def run(self, args=None):
        """Run the CLI"""
        if args is None:
            args = sys.argv[1:]
        
        parsed_args = self.parser.parse_args(args)
        
        if not parsed_args.command:
            self.parser.print_help()
            return
        
        # Execute command
        command = parsed_args.command.replace('-', '_')
        method_name = f'_{command}'
        if hasattr(self, method_name):
            getattr(self, method_name)(parsed_args)
        else:
            print(f"❌ Unknown command: {parsed_args.command}")
    
    def _list(self, args):
        """List scrapers"""
        if args.all:
            # Show all partitions
            all_scrapers = self.registry.get_all_scrapers()
            for partition, scrapers in all_scrapers.items():
                print(f"\n📂 Partition: {partition}")
                self._print_scrapers(scrapers, args.active, args.format)
        else:
            # Show single partition
            scrapers = self.registry.get_all_scrapers(args.partition)
            print(f"\n📂 Partition: {args.partition}")
            self._print_scrapers(scrapers, args.active, args.format)
    
    def _show(self, args):
        """Show scraper details"""
        config = self.registry.get_scraper(args.name, args.partition)
        if not config:
            print(f"❌ Scraper '{args.name}' not found in partition '{args.partition}'")
            return
        
        if args.format == 'json':
            print(json.dumps(config.to_dict(), indent=2, default=str))
        else:
            print(f"\n📋 Scraper: {config.name}")
            print(f"   Partition: {config.partition}")
            print(f"   URL: {config.url}")
            print(f"   Schedule: {config.schedule}")
            print(f"   Active: {'✅' if config.active else '❌'}")
            print(f"   Run Count: {config.run_count}")
            print(f"   Success: {config.success_count}")
            print(f"   Errors: {config.error_count}")
            print(f"   Last Run: {config.last_run or 'Never'}")
            print(f"   Selectors:")
            for key, value in config.selectors.items():
                print(f"      {key}: {value}")
    
    def _run(self, args):
        """Run a scraper"""
        config = self.registry.get_scraper(args.name, args.partition)
        if not config:
            print(f"❌ Scraper '{args.name}' not found in partition '{args.partition}'")
            return
        
        if getattr(args, 'async', False):
            # Run asynchronously via Celery
            task = run_scheduled_scraper.delay(args.name, args.partition)
            print(f"✅ Task submitted: {task.id}")
            print(f"   Run: celery -A celery_config status to check progress")
        else:
            # Run synchronously
            print(f"🔄 Running scraper '{args.name}'...")
            from scraper_framework.core.engine import ScraperEngine
            engine = ScraperEngine(args.partition)
            result = engine.run_scraper(config)
            
            if result.success:
                print(f"✅ Success! {len(result.data)} fields extracted")
                for key, value in result.data.items():
                    print(f"   {key}: {str(value)[:100]}...")
            else:
                print(f"❌ Failed: {result.error}")
    
    def _run_all(self, args):
        """Run all scrapers in partition"""
        if getattr(args, 'async', False):
            # Run asynchronously via Celery
            task = run_partition_scrapers.delay(args.partition)
            print(f"✅ Task submitted: {task.id}")
            print(f"   Run: celery -A celery_config status to check progress")
        else:
            # Run synchronously
            print(f"🔄 Running all scrapers in partition '{args.partition}'...")
            from scraper_framework.core.engine import ScraperEngine
            engine = ScraperEngine(args.partition)
            
            scrapers = self.registry.get_active_scrapers(args.partition)
            results = []
            
            for scraper in scrapers:
                print(f"\n📋 Running: {scraper.name}")
                result = engine.run_scraper(scraper)
                results.append(result)
                status = "✅" if result.success else "❌"
                print(f"   {status} {result.scraper_name} ({result.duration:.2f}s)")
            
            # Summary
            total = len(results)
            success = len([r for r in results if r.success])
            print(f"\n📊 Summary: {success}/{total} successful")
    
    def _stats(self, args):
        """Show statistics"""
        partition = args.partition if hasattr(args, "partition") and args.partition else "default"
        
        # Partition stats
        stats = self.registry.get_partition_stats(partition)
        
        if args.format == 'json':
            print(json.dumps(stats, indent=2))
        else:
            print(f"\n📊 Statistics for partition: {partition}")
            print(f"   Total Scrapers: {stats['total_scrapers']}")
            print(f"   Active Scrapers: {stats['active_scrapers']}")
            print(f"   Total Runs: {stats['total_runs']}")
            print(f"   Success Count: {stats['total_success']}")
            print(f"   Error Count: {stats['total_errors']}")
            print(f"   Success Rate: {stats['success_rate']}")
    
    def _partitions(self, args):
        """List all partitions"""
        partitions = self.registry.get_all_partitions()
        all_configs = get_all_partition_configs()
        
        print(f"\n📂 Partitions: {len(partitions)}")
        for partition in sorted(partitions):
            config = all_configs.get(partition)
            scrapers = self.registry.get_active_scrapers(partition)
            print(f"   • {partition}: {len(scrapers)} active scrapers")
            if config:
                print(f"     Queues: {', '.join(config.queues)}")
                print(f"     Storage: {config.storage}")
    
    def _create(self, args):
        """Create a new scraper"""
        try:
            selectors = json.loads(args.selectors)
        except json.JSONDecodeError:
            print(f"❌ Invalid JSON for selectors: {args.selectors}")
            return
        
        config = ScraperConfig(
            name=args.name,
            url=args.url,
            schedule=args.schedule,
            selectors=selectors,
            partition=args.partition
        )
        
        self.registry.add_scraper(config, args.partition)
        print(f"✅ Scraper '{args.name}' created in partition '{args.partition}'")
    
    def _delete(self, args):
        """Delete a scraper"""
        config = self.registry.get_scraper(args.name, args.partition)
        if not config:
            print(f"❌ Scraper '{args.name}' not found in partition '{args.partition}'")
            return
        
        if not args.force:
            confirm = input(f"Delete scraper '{args.name}'? (y/N): ")
            if confirm.lower() != 'y':
                print("❌ Cancelled")
                return
        
        self.registry.remove_scraper(args.name, args.partition)
        print(f"✅ Scraper '{args.name}' deleted from partition '{args.partition}'")
    
    def _test(self, args):
        """Test a scraper synchronously"""
        config = self.registry.get_scraper(args.name, args.partition)
        if not config:
            print(f"❌ Scraper '{args.name}' not found in partition '{args.partition}'")
            return
        
        print(f"🧪 Testing scraper '{args.name}'...")
        from scraper_framework.core.engine import ScraperEngine
        engine = ScraperEngine(args.partition)
        result = engine.run_scraper(config)
        
        if args.format == 'json':
            print(json.dumps(result.to_dict(), indent=2, default=str))
        else:
            print(result.get_summary())
            if result.success and result.data:
                print(f"\n📊 Extracted Data:")
                for key, value in result.data.items():
                    print(f"   {key}: {str(value)[:100]}...")
            if result.error:
                print(f"\n❌ Error: {result.error}")
    
    def _results(self, args):
        """Show scraper results"""
        storage = GoogleSheetsStorage(args.partition)
        results = storage.get_results(args.scraper, args.limit)
        
        if args.format == 'json':
            print(json.dumps(results, indent=2))
        else:
            print(f"\n📊 Results for partition '{args.partition}':")
            print(f"   Showing {len(results)} of {storage.get_stats()['total_results']} total")
            
            for result in results[:args.limit]:
                status = "✅" if result.get('status') == 'success' else "❌"
                print(f"   {status} {result.get('timestamp')} - {result.get('automation_id')}")
    
    def _export(self, args):
        """Export configuration to file"""
        self.registry.save_to_file(args.file)
        print(f"✅ Exported to {args.file}")
    
    def _print_scrapers(self, scrapers, active_only, format):
        """Print scrapers in the specified format"""
        if not scrapers:
            print("   No scrapers found")
            return
        
        if active_only:
            scrapers = {k: v for k, v in scrapers.items() if v.active}
        
        if format == 'json':
            data = {name: config.to_dict() for name, config in scrapers.items()}
            print(json.dumps(data, indent=2, default=str))
        else:
            for name, config in scrapers.items():
                status = "✅" if config.active else "⏸️"
                print(f"   {status} {name} - {config.url}")
                print(f"      Schedule: {config.schedule}")
                print(f"      Runs: {config.run_count} (S:{config.success_count}/E:{config.error_count})")
                print(f"      Last: {config.last_run or 'Never'}")
                print(f"      Selectors: {len(config.selectors)}")
