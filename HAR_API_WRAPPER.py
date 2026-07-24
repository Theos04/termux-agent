#!/usr/bin/env python3
"""
HAR API Wrapper Generator - Automatically Build Python API Clients from HAR Files
Transforms network traffic into reusable, production-ready API wrappers
"""

import json
import re
import sys
import os
from datetime import datetime
from collections import defaultdict
from urllib.parse import urlparse, parse_qs
from typing import Dict, List, Any, Optional
import requests
import websocket
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich import box
from rich.syntax import Syntax
from rich.tree import Tree
from rich.progress import Progress, SpinnerColumn, TextColumn

console = Console()

class HARAPIGenerator:
    """Generate Python API wrappers from HAR files"""
    
    def __init__(self):
        self.har_data = None
        self.entries = []
        self.api_endpoints = []
        self.auth_headers = {}
        self.common_headers = {}
        self.base_url = ""
        self.endpoint_groups = defaultdict(list)
        self.dependencies = []
        
    def load_har(self, filename: str) -> bool:
        """Load HAR file from disk"""
        try:
            with open(filename, 'r') as f:
                self.har_data = json.load(f)
            
            self.entries = self.har_data.get('log', {}).get('entries', [])
            
            if not self.entries:
                console.print("[red]❌ No entries found in HAR file[/red]")
                return False
            
            console.print(f"[green]✅ Loaded {len(self.entries)} entries from {filename}[/green]")
            self._analyze_har()
            return True
            
        except Exception as e:
            console.print(f"[red]❌ Error loading HAR: {e}[/red]")
            return False
    
    def _analyze_har(self):
        """Analyze HAR to extract API patterns"""
        console.print("[dim]Analyzing HAR file for API endpoints...[/dim]")
        
        # Find base URL
        if self.entries:
            first_url = self.entries[0].get('request', {}).get('url', '')
            parsed = urlparse(first_url)
            self.base_url = f"{parsed.scheme}://{parsed.netloc}"
        
        # Extract endpoints
        for entry in self.entries:
            request = entry.get('request', {})
            url = request.get('url', '')
            method = request.get('method', 'GET')
            headers = request.get('headers', {})
            
            # Filter out static assets
            if self._is_api_endpoint(url):
                parsed = urlparse(url)
                endpoint = {
                    'url': url,
                    'path': parsed.path,
                    'method': method,
                    'headers': headers,
                    'query_params': parse_qs(parsed.query),
                    'body': request.get('postData', {}).get('text', ''),
                    'response': entry.get('response', {}),
                    'timestamp': entry.get('startedDateTime', '')
                }
                
                self.api_endpoints.append(endpoint)
                self.endpoint_groups[method].append(endpoint)
        
        # Extract authentication patterns
        self._extract_auth_patterns()
        
        # Find dependencies
        self._find_dependencies()
        
        console.print(f"[green]✅ Found {len(self.api_endpoints)} API endpoints[/green]")
        console.print(f"   GET: {len(self.endpoint_groups.get('GET', []))}")
        console.print(f"   POST: {len(self.endpoint_groups.get('POST', []))}")
        console.print(f"   PUT: {len(self.endpoint_groups.get('PUT', []))}")
        console.print(f"   DELETE: {len(self.endpoint_groups.get('DELETE', []))}")
    
    def _is_api_endpoint(self, url: str) -> bool:
        """Determine if URL is an API endpoint (not static asset)"""
        static_patterns = [
            r'\.(js|css|png|jpg|jpeg|gif|svg|ico|woff|woff2|ttf|eot)$',
            r'/(static|assets|images|fonts|styles|scripts)/',
            r'/(favicon|manifest|robots)\.'
        ]
        
        for pattern in static_patterns:
            if re.search(pattern, url, re.IGNORECASE):
                return False
        
        # Check for API indicators
        api_indicators = [
            r'/api/',
            r'/v[0-9]+/',
            r'/gateway/',
            r'/services/',
            r'\.json$',
            r'/rest/',
            r'/graphql'
        ]
        
        for pattern in api_indicators:
            if re.search(pattern, url, re.IGNORECASE):
                return True
        
        # If URL has query params and isn't static, consider it API
        if '?' in url:
            return True
        
        return False
    
    def _extract_auth_patterns(self):
        """Extract authentication headers from requests"""
        auth_headers = {}
        header_patterns = {
            'authorization': r'^Bearer\s+(.+)$',
            'x-api-key': r'^(.+)$',
            'cookie': r'^(.+)$',
            'x-auth-token': r'^(.+)$'
        }
        
        for entry in self.entries:
            headers = entry.get('request', {}).get('headers', [])
            for header in headers:
                name = header.get('name', '').lower()
                value = header.get('value', '')
                
                for pattern_name, pattern in header_patterns.items():
                    if pattern_name in name:
                        match = re.search(pattern, value)
                        if match:
                            auth_headers[name] = {
                                'name': name,
                                'value_pattern': match.group(1)[:20] + '...' if len(match.group(1)) > 20 else match.group(1),
                                'type': 'bearer' if 'bearer' in value.lower() else 'token'
                            }
        
        self.auth_headers = auth_headers
        
        # Extract common headers
        common_headers = {}
        for entry in self.entries[:10]:  # Sample first 10 requests
            headers = entry.get('request', {}).get('headers', [])
            for header in headers:
                name = header.get('name', '')
                value = header.get('value', '')
                if name and name.lower() not in ['authorization', 'cookie', 'content-length']:
                    common_headers[name] = value
        
        self.common_headers = common_headers
    
    def _find_dependencies(self):
        """Find request dependencies and sequencing"""
        if len(self.entries) < 2:
            return
        
        sorted_entries = sorted(self.entries, key=lambda x: x.get('startedDateTime', ''))
        
        for i in range(1, len(sorted_entries)):
            prev_entry = sorted_entries[i-1]
            curr_entry = sorted_entries[i]
            
            prev_url = prev_entry.get('request', {}).get('url', '')
            curr_url = curr_entry.get('request', {}).get('url', '')
            
            # Check if current request depends on previous
            if self._is_api_endpoint(prev_url) and self._is_api_endpoint(curr_url):
                # Simple dependency: if same domain and previous finished before next started
                self.dependencies.append({
                    'from': prev_url,
                    'to': curr_url,
                    'type': 'sequential'
                })
    
    def generate_wrapper(self, class_name: str = "APIClient") -> str:
        """Generate Python wrapper code"""
        if not self.api_endpoints:
            console.print("[red]No API endpoints found to generate wrapper[/red]")
            return ""
        
        code_lines = []
        
        # Imports
        code_lines.extend([
            "#!/usr/bin/env python3",
            "\"\"\"",
            f"Auto-generated API wrapper from HAR analysis",
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "\"\"\"",
            "",
            "import requests",
            "from typing import Optional, Dict, Any, List",
            "from datetime import datetime",
            "import json",
            "from urllib.parse import urlencode",
            "from concurrent.futures import ThreadPoolExecutor, as_completed",
            "",
            ""
        ])
        
        # Class definition
        code_lines.append(f"class {class_name}:")
        code_lines.append(f'    """Auto-generated API client from HAR analysis"""')
        code_lines.append("    ")
        
        # Base URL
        code_lines.append(f"    BASE_URL = \"{self.base_url}\"")
        code_lines.append("    ")
        
        # Constructor
        code_lines.append("    def __init__(self, token: Optional[str] = None, **kwargs):")
        code_lines.append('        """Initialize API client with authentication"""')
        code_lines.append("        self.token = token")
        code_lines.append("        self.session = requests.Session()")
        code_lines.append("        ")
        
        # Set common headers
        code_lines.append("        # Default headers from HAR analysis")
        code_lines.append("        self.default_headers = {")
        for name, value in list(self.common_headers.items())[:10]:
            code_lines.append(f'            "{name}": "{value}",')
        code_lines.append("        }")
        code_lines.append("        ")
        
        code_lines.append("        if token:")
        code_lines.append('            self.default_headers["Authorization"] = f"Bearer {token}"')
        code_lines.append("        ")
        
        code_lines.append("        self.session.headers.update(self.default_headers)")
        code_lines.append("        ")
        
        # Add custom headers
        code_lines.append("        # Override with custom headers")
        code_lines.append("        for key, value in kwargs.items():")
        code_lines.append("            if key.startswith('header_'):")
        code_lines.append("                header_name = key.replace('header_', '')")
        code_lines.append("                self.session.headers[header_name] = value")
        code_lines.append("    ")
        
        # Generate methods for each endpoint
        for method, endpoints in self.endpoint_groups.items():
            for endpoint in endpoints[:20]:  # Limit to 20 endpoints for readability
                method_name = self._generate_method_name(endpoint)
                method_code = self._generate_method_code(endpoint, method_name)
                code_lines.extend(method_code)
                code_lines.append("")
        
        # Add utility methods
        code_lines.extend([
            "",
            "    # Utility Methods",
            "    def get_all_data(self) -> Dict[str, Any]:",
            '        """Fetch all data in parallel"""',
            "        with ThreadPoolExecutor(max_workers=5) as executor:",
            "            futures = {}",
            "            for attr, method in self._get_all_methods().items():",
            "                futures[attr] = executor.submit(method)",
            "",
            "            results = {}",
            "            for attr, future in futures.items():",
            "                try:",
            "                    results[attr] = future.result(timeout=10)",
            "                except Exception as e:",
            "                    results[attr] = {'error': str(e)}",
            "",
            "        return results",
            "    ",
            "",
            "    def _get_all_methods(self) -> Dict[str, callable]:",
            '        """Get all API methods for parallel execution"""',
            "        methods = {}",
            "        for attr in dir(self):",
            "            if attr.startswith('get_') and callable(getattr(self, attr)):",
            "                methods[attr] = getattr(self, attr)",
            "        return methods",
            "",
            "",
            "    # Response Helpers",
            "    def _handle_response(self, response: requests.Response) -> Dict[str, Any]:",
            '        """Handle API response with error checking"""',
            "        try:",
            "            response.raise_for_status()",
            "            return response.json()",
            "        except requests.exceptions.HTTPError as e:",
            "            return {'error': str(e), 'status_code': response.status_code}",
            "        except ValueError:",
            "            return {'error': 'Invalid JSON response', 'text': response.text[:200]}",
            "",
            "",
            "    # Caching Support",
            "    def _cache_key(self, *args) -> str:",
            '        """Generate cache key for method arguments"""',
            "        return '_'.join(str(arg) for arg in args)",
            "",
            "",
            "    # Rate Limiting",
            "    def _rate_limit(self, method: str):",
            '        """Apply rate limiting for API calls"""',
            "        # Implement rate limiting logic here",
            "        pass",
            "",
            "",
            "# Example usage",
            "if __name__ == '__main__':",
            "    # Initialize with your token",
            "    client = APIClient(token='your_token_here')",
            "    ",
            "    # Get all data",
            "    # data = client.get_all_data()",
            "    # print(json.dumps(data, indent=2))",
        ])
        
        return '\n'.join(code_lines)
    
    def _generate_method_name(self, endpoint: Dict) -> str:
        """Generate a clean method name from URL"""
        path = endpoint.get('path', '')
        method = endpoint.get('method', 'GET').lower()
        
        # Remove /api/ or /v1/ prefixes
        clean_path = re.sub(r'^/api/', '/', path)
        clean_path = re.sub(r'^/v[0-9]+/', '/', clean_path)
        
        # Extract meaningful parts
        parts = [p for p in clean_path.split('/') if p and p != '']
        
        if not parts:
            return f"fetch_{method}_root"
        
        # Build method name
        method_name = method
        for part in parts[:3]:  # Limit depth
            # Remove special characters
            clean_part = re.sub(r'[^a-zA-Z0-9]', '_', part)
            # Remove underscores and capitalize
            clean_part = '_'.join(p for p in clean_part.split('_') if p)
            if clean_part:
                method_name += f"_{clean_part}"
        
        # Remove duplicates
        method_name = '_'.join(dict.fromkeys(method_name.split('_')))
        
        return method_name.lower()
    
    def _generate_method_code(self, endpoint: Dict, method_name: str) -> List[str]:
        """Generate Python method code for an endpoint"""
        code = []
        
        url = endpoint.get('url', '')
        path = endpoint.get('path', '')
        method = endpoint.get('method', 'GET')
        query_params = endpoint.get('query_params', {})
        
        # Docstring
        code.append(f"    def {method_name}(self, **kwargs) -> Dict[str, Any]:")
        code.append(f'        """Auto-generated method for {method} {path}"""')
        
        # Build URL
        rel_path = path.replace(self.base_url, '')
        if rel_path.startswith('//'):
            rel_path = rel_path[1:]
        
        code.append(f"        url = f\"{{self.BASE_URL}}{rel_path}\"")
        code.append("        ")
        
        # Handle query parameters
        if query_params:
            code.append("        # Query parameters")
            code.append("        params = {}")
            for param_name in query_params.keys():
                code.append(f"        if '{param_name}' in kwargs:")
                code.append(f"            params['{param_name}'] = kwargs['{param_name}']")
            code.append("        ")
        
        # Handle body (for POST, PUT)
        if method.upper() in ['POST', 'PUT', 'PATCH']:
            body = endpoint.get('body', '')
            if body and '}' in body:  # Has JSON body
                code.append("        # Request body")
                code.append("        json_data = {}")
                try:
                    body_json = json.loads(body)
                    for key in body_json.keys():
                        code.append(f"        if '{key}' in kwargs:")
                        code.append(f"            json_data['{key}'] = kwargs['{key}']")
                except:
                    code.append("        # Body structure: {body[:50]}...")
                code.append("        ")
        
        # Make request
        if method.upper() in ['GET']:
            if query_params:
                code.append("        response = self.session.get(url, params=params, **kwargs.get('request_kwargs', {}))")
            else:
                code.append("        response = self.session.get(url, **kwargs.get('request_kwargs', {}))")
        elif method.upper() in ['POST']:
            code.append("        response = self.session.post(url, json=json_data, **kwargs.get('request_kwargs', {}))")
        elif method.upper() in ['PUT']:
            code.append("        response = self.session.put(url, json=json_data, **kwargs.get('request_kwargs', {}))")
        elif method.upper() in ['DELETE']:
            code.append("        response = self.session.delete(url, **kwargs.get('request_kwargs', {}))")
        
        # Handle response
        code.append("        ")
        code.append("        return self._handle_response(response)")
        code.append("    ")
        
        return code
    
    def generate_documentation(self) -> str:
        """Generate Markdown documentation"""
        doc_lines = [
            f"# API Client Documentation",
            "",
            f"**Generated from HAR analysis on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}**",
            "",
            "## Overview",
            f"- Total API Endpoints: {len(self.api_endpoints)}",
            f"- Base URL: {self.base_url}",
            "- Authentication: Bearer Token",
            "",
            "## Authentication Headers",
            ""
        ]
        
        for name, info in self.auth_headers.items():
            doc_lines.append(f"### {name}")
            doc_lines.append(f"- Type: {info.get('type', 'unknown')}")
            doc_lines.append(f"- Pattern: `{info.get('value_pattern', '')}`")
            doc_lines.append("")
        
        doc_lines.append("## Common Headers")
        doc_lines.append("")
        for name, value in list(self.common_headers.items())[:10]:
            doc_lines.append(f"- `{name}`: `{value}`")
        
        doc_lines.append("")
        doc_lines.append("## API Endpoints")
        doc_lines.append("")
        
        for method, endpoints in self.endpoint_groups.items():
            doc_lines.append(f"### {method} Endpoints ({len(endpoints)})")
            doc_lines.append("")
            for endpoint in endpoints[:10]:
                path = endpoint.get('path', '')
                method_name = self._generate_method_name(endpoint)
                doc_lines.append(f"- `{method_name}` - `{path}`")
            if len(endpoints) > 10:
                doc_lines.append(f"- ... and {len(endpoints) - 10} more")
            doc_lines.append("")
        
        return '\n'.join(doc_lines)

def display_analysis_report(generator: HARAPIGenerator):
    """Display analysis report"""
    console.print("\n[bold cyan]📊 HAR Analysis Report[/bold cyan]")
    
    # API Endpoints Table
    table = Table(title="API Endpoints", box=box.ROUNDED)
    table.add_column("Method", style="cyan")
    table.add_column("Path", style="green")
    table.add_column("Parameters", style="yellow")
    
    for endpoint in generator.api_endpoints[:15]:
        path = endpoint.get('path', '')[:60]
        method = endpoint.get('method', '')
        params = list(endpoint.get('query_params', {}).keys())
        params_str = ', '.join(params[:3]) + ('...' if len(params) > 3 else '')
        
        table.add_row(method, path, params_str)
    
    console.print(table)
    
    # Dependencies
    if generator.dependencies:
        console.print("\n[bold]🔗 Detected Dependencies:[/bold]")
        for dep in generator.dependencies[:5]:
            console.print(f"  • {dep.get('from', '')[:40]} → {dep.get('to', '')[:40]}")

def main():
    console.clear()
    console.print(Panel("[bold cyan]🚀 HAR API Wrapper Generator[/bold cyan]", border_style="green"))
    console.print("[dim]Transform HAR files into Python API clients[/dim]")
    console.print()
    
    generator = HARAPIGenerator()
    
    # Load HAR file
    filename = Prompt.ask("📂 HAR file path", default="network.har")
    
    if not os.path.exists(filename):
        console.print("[red]❌ File not found[/red]")
        return
    
    if not generator.load_har(filename):
        return
    
    # Display analysis
    display_analysis_report(generator)
    
    # Generate wrapper
    if Confirm.ask("\n[cyan]Generate Python API wrapper?[/cyan]"):
        class_name = Prompt.ask("Class name", default="APIClient")
        code = generator.generate_wrapper(class_name)
        
        if code:
            # Save to file
            output_file = Prompt.ask("Output filename", default=f"{class_name.lower()}.py")
            
            with open(output_file, 'w') as f:
                f.write(code)
            
            console.print(f"[green]✅ Wrapper saved to {output_file}[/green]")
            
            # Display preview
            if Confirm.ask("Show code preview?"):
                syntax = Syntax(code[:1000] + "\n... (truncated)", "python", theme="monokai")
                console.print(syntax)
    
    # Generate documentation
    if Confirm.ask("\n[cyan]Generate documentation?[/cyan]"):
        doc = generator.generate_documentation()
        doc_file = Prompt.ask("Documentation filename", default="API_DOCS.md")
        
        with open(doc_file, 'w') as f:
            f.write(doc)
        
        console.print(f"[green]✅ Documentation saved to {doc_file}[/green]")
        
        # Display doc preview
        console.print(Panel(doc[:1000] + "\n... (truncated)", title="Documentation Preview", border_style="blue"))
    
    console.print("\n[bold green]🎉 API wrapper generation complete![/bold green]")
    
    # Next steps
    console.print("\n[bold]Next Steps:[/bold]")
    console.print("  1. Install dependencies: pip install requests")
    console.print("  2. Add your authentication token")
    console.print("  3. Test the client: python your_wrapper.py")
    console.print("  4. Customize methods for your specific needs")
    console.print("  5. Add error handling and retry logic")
    
    console.print("\n[dim]Tip: Look at the generated code and modify it to fit your use case.[/dim]")

if __name__ == "__main__":
    main()
