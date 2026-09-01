#!/usr/bin/env python3
"""
HAR2API - Convert HAR files to API clients
"""

import argparse
import sys
import json
import os
from pathlib import Path
from datetime import datetime
from collections import Counter

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich import box
from rich.syntax import Syntax
from rich.prompt import Confirm, Prompt

from .core.parser import HARParser
from .core.analyzer import HARAnalyzer
from .generators.client_generator import ClientGenerator
from .generators.docs_generator import DocsGenerator

console = Console()

def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(
        description='HAR2API - Convert HAR files to API clients',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  har2api analyze network.har --detailed
  har2api generate network.har -o client.py -c MyAPI
  har2api generate network.har --docs --openapi
        """
    )

    subparsers = parser.add_subparsers(dest='command', help='Command to execute', required=True)

    # Analyze command
    analyze_parser = subparsers.add_parser('analyze', help='Analyze HAR file')
    analyze_parser.add_argument('har_file', help='Path to HAR file')
    analyze_parser.add_argument('--detailed', '-d', action='store_true', help='Show detailed analysis')
    analyze_parser.add_argument('--output', '-o', help='Output file (JSON or Markdown)')
    analyze_parser.add_argument('--format', '-f', choices=['json', 'markdown'], default='json',
                               help='Output format (default: json)')

    # Generate command
    gen_parser = subparsers.add_parser('generate', help='Generate API client from HAR')
    gen_parser.add_argument('har_file', help='HAR file to analyze')
    gen_parser.add_argument('-o', '--output', help='Output file path', default='api_client.py')
    gen_parser.add_argument('-c', '--class-name', help='API client class name', default='APIClient')
    gen_parser.add_argument('-l', '--language', choices=['python', 'typescript'], default='python')
    gen_parser.add_argument('--docs', action='store_true', help='Generate documentation')
    gen_parser.add_argument('--openapi', action='store_true', help='Generate OpenAPI spec')

    # Parse arguments
    args = parser.parse_args()

    if args.command == 'analyze':
        return analyze_command(args)
    elif args.command == 'generate':
        return generate_command(args)
    else:
        parser.print_help()
        return 1


def analyze_command(args):
    """Analyze HAR file command"""
    har_file = args.har_file

    if not Path(har_file).exists():
        console.print(f"❌ [red]HAR file not found:[/red] {har_file}")
        return 1

    try:
        # Parse the HAR file
        parser = HARParser(strict_mode=False)
        spec = parser.parse_file(har_file)

        # Analyze
        analyzer = HARAnalyzer(spec)
        results = analyzer.analyze()

        # Print report
        analyzer.print_report(detailed=args.detailed)

        # Output
        if args.output:
            if args.format == 'json':
                with open(args.output, 'w') as f:
                    json.dump(results, f, indent=2, default=str)
                console.print(f"\n✅ [green]Analysis saved to[/green] {args.output}")
            else:
                markdown = analyzer.to_markdown()
                with open(args.output, 'w') as f:
                    f.write(markdown)
                console.print(f"\n✅ [green]Analysis saved to[/green] {args.output}")

        # Show parse statistics - handle both method names
        try:
            if hasattr(parser, 'get_parse_statistics'):
                stats = parser.get_parse_statistics()
            elif hasattr(parser, 'get_statistics'):
                stats = parser.get_statistics()
            else:
                stats = {'total_entries': len(parser.entries) if hasattr(parser, 'entries') else 0, 
                        'parsed_requests': len(spec.endpoints) if spec.endpoints else 0,
                        'errors_count': 0}
            console.print(f"\n[dim]📈 Parse Statistics: {stats.get('parsed_requests', 0)}/{stats.get('total_entries', 0)} entries parsed, {stats.get('errors_count', 0)} errors[/dim]")
        except:
            pass

        return 0

    except Exception as e:
        console.print(f"❌ [red]Error analyzing HAR file:[/red] {str(e)}")
        import traceback
        traceback.print_exc()
        return 1


def generate_command(args):
    """Generate API client from HAR"""
    console.print(Panel.fit("🚀 HAR2API Client Generator", style="bold cyan"))

    if not os.path.exists(args.har_file):
        console.print(f"[red]❌ File not found: {args.har_file}[/red]")
        return 1

    try:
        # Parse HAR
        console.print(f"\n[cyan]📖 Parsing HAR file:[/cyan] {args.har_file}")
        parser = HARParser(strict_mode=False)
        spec = parser.parse_file(args.har_file)

        console.print(f"[green]✅ Parsed {len(spec.endpoints)} endpoints[/green]")

        # Generate client
        console.print(f"\n[cyan]🔧 Generating {args.language} client...[/cyan]")
        generator = ClientGenerator()

        if args.language == 'python':
            code = generator.generate_python(spec, args.class_name)
        else:
            code = generator.generate_typescript(spec, args.class_name)

        # Save client
        with open(args.output, 'w') as f:
            f.write(code)

        console.print(f"[green]✅ Client generated: {args.output}[/green]")
        console.print(f"   Language: {args.language}")
        console.print(f"   Class: {args.class_name}")
        console.print(f"   Endpoints: {len(spec.endpoints)}")
        console.print(f"   Base URL: {spec.base_url or 'Not detected'}")

        # Show preview
        if Confirm.ask("\nShow code preview?"):
            preview = code[:1500] + "\n... (truncated)" if len(code) > 1500 else code
            syntax = Syntax(preview, "python" if args.language == 'python' else "typescript", theme="monokai")
            console.print(syntax)

        # Generate documentation
        if args.docs:
            console.print(f"\n[cyan]📚 Generating documentation...[/cyan]")
            docs = DocsGenerator().generate_markdown(spec)
            docs_file = args.output.replace('.py', '_docs.md')
            if args.language == 'typescript':
                docs_file = args.output.replace('.ts', '_docs.md')
            with open(docs_file, 'w') as f:
                f.write(docs)
            console.print(f"[green]✅ Documentation generated: {docs_file}[/green]")

        # Generate OpenAPI spec
        if args.openapi:
            console.print(f"\n[cyan]📋 Generating OpenAPI spec...[/cyan]")
            openapi = _generate_openapi(spec)
            openapi_file = args.output.replace('.py', '_openapi.json')
            with open(openapi_file, 'w') as f:
                json.dump(openapi, f, indent=2)
            console.print(f"[green]✅ OpenAPI spec generated: {openapi_file}[/green]")

        # Show parse statistics - handle both method names
        try:
            if hasattr(parser, 'get_parse_statistics'):
                stats = parser.get_parse_statistics()
            elif hasattr(parser, 'get_statistics'):
                stats = parser.get_statistics()
            else:
                stats = {'total_entries': len(parser.entries) if hasattr(parser, 'entries') else 0, 
                        'parsed_requests': len(spec.endpoints) if spec.endpoints else 0,
                        'errors_count': 0}
            console.print(f"\n[dim]📈 Parse Statistics: {stats.get('parsed_requests', 0)}/{stats.get('total_entries', 0)} entries parsed, {stats.get('errors_count', 0)} errors[/dim]")
        except:
            pass

        return 0

    except Exception as e:
        console.print(f"❌ [red]Error generating client:[/red] {str(e)}")
        import traceback
        traceback.print_exc()
        return 1


def _generate_openapi(spec):
    """Generate OpenAPI spec from spec"""
    openapi = {
        "openapi": "3.0.0",
        "info": {
            "title": getattr(spec, 'title', 'API from HAR Analysis'),
            "version": "1.0.0",
            "description": "Auto-generated from HAR analysis"
        },
        "servers": [{"url": spec.base_url}] if spec.base_url else [],
        "paths": {}
    }

    for endpoint in spec.endpoints[:50]:
        path = endpoint.path or '/'
        
        # Get method string
        if hasattr(endpoint.method, 'value'):
            method = endpoint.method.value.lower()
        else:
            method = str(endpoint.method).lower()
        
        openapi["paths"][path] = {
            method: {
                "summary": f"{method.upper()} {endpoint.path}",
                "parameters": []
            }
        }

        # Add query parameters
        if hasattr(endpoint, 'parameters') and endpoint.parameters:
            if isinstance(endpoint.parameters, dict):
                for param_name, param_info in endpoint.parameters.items():
                    if isinstance(param_info, dict) and param_info.get('in') == 'query':
                        openapi["paths"][path][method]["parameters"].append({
                            "name": param_name,
                            "in": "query",
                            "schema": {"type": "string"},
                            "required": param_info.get('required', False)
                        })

    return openapi


if __name__ == '__main__':
    sys.exit(main())
