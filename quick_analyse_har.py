#!/usr/bin/env python3
"""
HAR Analyzer & API Wrapper Generator - Fixed version
Handles both header formats in HAR files
"""

import json
import re
from datetime import datetime
from collections import defaultdict, Counter
from urllib.parse import urlparse, parse_qs
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box
from rich.syntax import Syntax

console = Console()

def analyze_har(filename):
    """Analyze HAR file and display insights"""
    with open(filename, 'r') as f:
        har_data = json.load(f)
    
    entries = har_data.get('log', {}).get('entries', [])
    
    console.print(Panel(f"[bold cyan]📊 HAR Analysis: {filename}[/bold cyan]", border_style="green"))
    console.print(f"\n[bold]Total Entries:[/bold] {len(entries)}")
    
    # Group by domain
    domains = Counter()
    methods = Counter()
    statuses = Counter()
    api_endpoints = []
    
    for entry in entries:
        request = entry.get('request', {})
        response = entry.get('response', {})
        url = request.get('url', '')
        
        # Parse URL
        parsed = urlparse(url)
        domains[parsed.netloc] += 1
        methods[request.get('method', '')] += 1
        statuses[response.get('status', 0)] += 1
        
        # Check if API endpoint
        if ('/api/' in url or '/v' in url or 'json' in response.get('content', {}).get('mimeType', '')):
            # Extract headers (handle both formats)
            headers = request.get('headers', [])
            if isinstance(headers, dict):
                # Headers as dict
                header_dict = headers
            else:
                # Headers as list of {name, value}
                header_dict = {}
                for h in headers:
                    if isinstance(h, dict):
                        name = h.get('name', '')
                        value = h.get('value', '')
                        if name:
                            header_dict[name] = value
            
            api_endpoints.append({
                'method': request.get('method', ''),
                'url': url,
                'path': parsed.path,
                'status': response.get('status', 0),
                'headers': header_dict
            })
    
    # Display domains
    console.print("\n[bold cyan]🌐 Domains:[/bold cyan]")
    for domain, count in domains.most_common(10):
        console.print(f"  • {domain}: {count} requests")
    
    # Display methods
    console.print("\n[bold cyan]📌 HTTP Methods:[/bold cyan]")
    for method, count in methods.most_common():
        console.print(f"  • {method}: {count}")
    
    # Display status codes
    console.print("\n[bold cyan]📊 Status Codes:[/bold cyan]")
    for status, count in statuses.most_common():
        emoji = "✅" if 200 <= status < 300 else "⚠️" if 300 <= status < 400 else "❌"
        console.print(f"  {emoji} {status}: {count}")
    
    # Display API endpoints
    console.print(f"\n[bold cyan]🔌 API Endpoints Found: {len(api_endpoints)}[/bold cyan]")
    table = Table(box=box.ROUNDED)
    table.add_column("Method", style="cyan")
    table.add_column("Path", style="green")
    table.add_column("Status", style="yellow")
    
    for api in api_endpoints[:20]:
        path = api['path'][:50]
        table.add_row(api['method'], path, str(api['status']))
    
    console.print(table)
    
    return har_data, api_endpoints

def generate_api_wrapper(api_endpoints, class_name="UnstopAPI"):
    """Generate Python API wrapper from endpoints"""
    
    # Find base URL
    base_url = ""
    for api in api_endpoints:
        if api['url']:
            parsed = urlparse(api['url'])
            base_url = f"{parsed.scheme}://{parsed.netloc}"
            break
    
    # Find common headers
    common_headers = {}
    for api in api_endpoints[:10]:
        headers = api.get('headers', {})
        if headers:
            for name, value in headers.items():
                if name and name.lower() not in ['authorization', 'cookie', 'content-length', 'host']:
                    if name not in common_headers:
                        common_headers[name] = value
    
    code = []
    
    # Imports
    code.extend([
        "#!/usr/bin/env python3",
        "\"\"\"",
        f"Auto-generated API wrapper from HAR analysis",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Total Endpoints: {len(api_endpoints)}",
        "\"\"\"",
        "",
        "import requests",
        "from typing import Optional, Dict, Any, List",
        "from datetime import datetime",
        "import json",
        "",
        ""
    ])
    
    # Class
    code.append(f"class {class_name}:")
    code.append('    """API client for Unstop.com"""')
    code.append("    ")
    code.append(f"    BASE_URL = \"{base_url}\"")
    code.append("    ")
    
    # Constructor
    code.append("    def __init__(self, token: Optional[str] = None, **kwargs):")
    code.append('        """Initialize API client"""')
    code.append("        self.token = token")
    code.append("        self.session = requests.Session()")
    code.append("        ")
    code.append("        # Default headers")
    code.append("        self.default_headers = {")
    if common_headers:
        for name, value in list(common_headers.items())[:10]:
            code.append(f'            "{name}": "{value}",')
    else:
        code.append('            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",')
        code.append('            "Accept": "application/json",')
    code.append("        }")
    code.append("        ")
    code.append("        if token:")
    code.append('            self.default_headers["Authorization"] = f"Bearer {token}"')
    code.append("        ")
    code.append("        self.session.headers.update(self.default_headers)")
    code.append("        ")
    code.append("        # Custom headers")
    code.append("        for key, value in kwargs.items():")
    code.append("            if key.startswith('header_'):")
    code.append("                header_name = key.replace('header_', '')")
    code.append("                self.session.headers[header_name] = value")
    code.append("    ")
    
    # Generate methods for each unique endpoint
    seen_paths = set()
    for api in api_endpoints:
        path = api['path']
        method = api['method']
        
        # Generate method name
        clean_path = re.sub(r'^/api/', '', path)
        clean_path = re.sub(r'^/v[0-9]+/', '', clean_path)
        parts = [p for p in clean_path.split('/') if p and p not in ['users', 'self', 'jobs']]
        
        if parts:
            # Clean up method name
            method_name = '_'.join(parts[:3])
            # Remove special characters
            method_name = re.sub(r'[^a-zA-Z0-9_]', '_', method_name)
            # Remove multiple underscores
            method_name = re.sub(r'_+', '_', method_name)
            method_name = f"get_{method_name}"
        else:
            method_name = f"fetch_{method.lower()}"
        
        # Remove duplicates
        if path in seen_paths:
            continue
        seen_paths.add(path)
        
        code.append("    ")
        code.append(f"    def {method_name}(self, **kwargs) -> Dict[str, Any]:")
        code.append(f'        """{method} {path}"""')
        code.append(f"        url = f\"{{self.BASE_URL}}{path}\"")
        code.append("        ")
        
        # Handle query params
        if '?' in path:
            query_string = urlparse(path).query
            if query_string:
                query_params = parse_qs(query_string)
                if query_params:
                    code.append("        params = {}")
                    for param in query_params.keys():
                        code.append(f"        if '{param}' in kwargs:")
                        code.append(f"            params['{param}'] = kwargs['{param}']")
                    code.append("        ")
        
        # Handle body for POST/PUT
        if method.upper() in ['POST', 'PUT', 'PATCH']:
            code.append("        json_data = kwargs.get('json', {})")
            code.append("        ")
        
        # Make request
        if method.upper() == 'GET':
            if 'params' in locals():
                code.append("        response = self.session.get(url, params=params, **kwargs.get('request_kwargs', {}))")
            else:
                code.append("        response = self.session.get(url, **kwargs.get('request_kwargs', {}))")
        elif method.upper() == 'POST':
            code.append("        response = self.session.post(url, json=json_data, **kwargs.get('request_kwargs', {}))")
        elif method.upper() == 'PUT':
            code.append("        response = self.session.put(url, json=json_data, **kwargs.get('request_kwargs', {}))")
        elif method.upper() == 'DELETE':
            code.append("        response = self.session.delete(url, **kwargs.get('request_kwargs', {}))")
        elif method.upper() == 'OPTIONS':
            code.append("        response = self.session.options(url, **kwargs.get('request_kwargs', {}))")
        
        code.append("        ")
        code.append("        return self._handle_response(response)")
        code.append("    ")
    
    # Utility methods
    code.extend([
        "",
        "    def _handle_response(self, response: requests.Response) -> Dict[str, Any]:",
        '        """Handle API response"""',
        "        try:",
        "            response.raise_for_status()",
        "            if 'application/json' in response.headers.get('content-type', ''):",
        "                return response.json()",
        "            return {'text': response.text, 'status_code': response.status_code}",
        "        except requests.exceptions.HTTPError as e:",
        "            return {'error': str(e), 'status_code': response.status_code, 'text': response.text[:200]}",
        "        except ValueError:",
        "            return {'error': 'Invalid JSON', 'text': response.text[:200]}",
        "",
        "",
        "    # Convenience methods",
        "    def search_opportunities(self, **kwargs) -> Dict[str, Any]:",
        '        """Search for opportunities"""',
        "        return self.get_api_public_opportunity_search_result(**kwargs)",
        "",
        "    def get_cities(self) -> Dict[str, Any]:",
        '        """Get list of cities"""',
        "        return self.get_api_un_cities()",
        "",
        "    def get_work_functions(self) -> Dict[str, Any]:",
        '        """Get work functions"""',
        "        return self.get_api_workrelationship_workfunction_getAll()",
        "",
        "",
        "# Example usage",
        "if __name__ == '__main__':",
        "    # Initialize client",
        "    client = UnstopAPI()",
        "    ",
        "    # Search for opportunities",
        "    # results = client.search_opportunities(q='software engineer')",
        "    # print(json.dumps(results, indent=2))",
        "    ",
        "    # Get cities",
        "    # cities = client.get_cities()",
        "    # print(json.dumps(cities, indent=2))",
    ])
    
    return '\n'.join(code)

def main():
    console.clear()
    console.print(Panel("[bold cyan]🔍 HAR Analyzer & API Wrapper Generator[/bold cyan]", border_style="green"))
    console.print()
    
    # Get HAR file
    filename = input("📂 HAR filename [har_25]: ").strip()
    if not filename:
        filename = "har_25"
    
    try:
        # Analyze
        har_data, api_endpoints = analyze_har(filename)
        
        if not api_endpoints:
            console.print("[yellow]⚠️ No API endpoints found![/yellow]")
            return
        
        # Generate wrapper
        console.print("\n[bold cyan]🚀 Generating API Wrapper...[/bold cyan]")
        class_name = input("Class name [UnstopAPI]: ").strip()
        if not class_name:
            class_name = "UnstopAPI"
        
        code = generate_api_wrapper(api_endpoints, class_name)
        
        # Save wrapper
        output_file = f"{class_name.lower()}.py"
        with open(output_file, 'w') as f:
            f.write(code)
        
        console.print(f"[green]✅ API wrapper saved to: {output_file}[/green]")
        console.print(f"[dim]   {len(api_endpoints)} endpoints wrapped[/dim]")
        
        # Show preview
        if input("\n📄 Show code preview? (y/n) ").lower() == 'y':
            # Show only the class methods section
            lines = code.split('\n')
            preview_start = 0
            for i, line in enumerate(lines):
                if 'class ' + class_name in line:
                    preview_start = i
                    break
            
            preview = '\n'.join(lines[preview_start:preview_start+40]) + "\n... (truncated)"
            syntax = Syntax(preview, "python", theme="monokai")
            console.print(syntax)
        
        # Show next steps
        console.print("\n[bold cyan]📋 Next Steps:[/bold cyan]")
        console.print(f"  1. pip install requests")
        console.print(f"  2. python {output_file}")
        console.print("  3. Use the client to fetch data")
        console.print("  4. Customize methods for your use case")
        
        # Show available methods
        console.print("\n[bold green]Available Methods:[/bold green]")
        for api in api_endpoints[:10]:
            method = api['method']
            path = api['path'][:40]
            console.print(f"  • {method} {path}")
        
    except FileNotFoundError:
        console.print(f"[red]❌ File not found: {filename}[/red]")
    except Exception as e:
        console.print(f"[red]❌ Error: {e}[/red]")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
