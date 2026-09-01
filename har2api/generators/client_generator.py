"""
API client code generation using Jinja2 templates
Enhanced with token extraction and authentication support
"""

import re
import os
import json
from typing import List, Dict, Any, Optional
from datetime import datetime
from jinja2 import Environment, FileSystemLoader, TemplateNotFound

from ..core.models import APISpec, EndpointModel, HttpMethod

class ClientGenerator:
    """Generate API client code from API specification with token support"""

    def __init__(self, template_dir: Optional[str] = None):
        if template_dir is None:
            template_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'templates')

        if not os.path.exists(template_dir):
            os.makedirs(template_dir)

        self.env = Environment(
            loader=FileSystemLoader(template_dir),
            trim_blocks=True,
            lstrip_blocks=True
        )

        # Register the pyliteral filter
        self.env.filters['pyliteral'] = self._safe_string_literal

    def generate_python(self, spec: APISpec, class_name: str = "APIClient") -> str:
        """Generate Python client code with token extraction"""
        try:
            template = self.env.get_template('python_client.j2')
        except TemplateNotFound:
            return self._generate_embedded_python(spec, class_name)

        methods = []
        for endpoint in spec.endpoints[:50]:
            methods.append(self._prepare_endpoint_method(endpoint))

        context = {
            'class_name': class_name,
            'base_url': spec.base_url or '',
            'authentication': spec.authentication,
            'common_headers': spec.common_headers or {},
            'endpoints': spec.endpoints[:50],
            'methods': methods,
            'generated_at': datetime.now().isoformat(),
            'total_endpoints': len(spec.endpoints),
            'auth_config': {
                'type': getattr(spec.authentication, 'type', 'none'),
                'requires_auth': getattr(spec.authentication, 'requires_auth', False),
                'token_type': getattr(spec.authentication, 'token_type', ''),
                'token_location': getattr(spec.authentication, 'token_location', ''),
                'cookie_name': getattr(spec.authentication, 'cookie_name', '')
            }
        }

        return template.render(**context)

    def generate_typescript(self, spec: APISpec, class_name: str = "APIClient") -> str:
        """Generate TypeScript client code"""
        try:
            template = self.env.get_template('typescript_client.j2')
        except TemplateNotFound:
            return self._generate_simple_typescript(spec, class_name)

        methods = []
        for endpoint in spec.endpoints[:50]:
            methods.append(self._prepare_endpoint_method(endpoint))

        context = {
            'class_name': class_name,
            'base_url': spec.base_url or '',
            'authentication': spec.authentication,
            'common_headers': spec.common_headers or {},
            'endpoints': spec.endpoints[:50],
            'methods': methods,
            'generated_at': datetime.now().isoformat(),
            'total_endpoints': len(spec.endpoints),
            'auth_config': {
                'type': getattr(spec.authentication, 'type', 'none'),
                'requires_auth': getattr(spec.authentication, 'requires_auth', False),
                'token_type': getattr(spec.authentication, 'token_type', ''),
                'token_location': getattr(spec.authentication, 'token_location', ''),
                'cookie_name': getattr(spec.authentication, 'cookie_name', '')
            }
        }

        return template.render(**context)

    def _prepare_endpoint_method(self, endpoint: EndpointModel) -> Dict[str, Any]:
        """Prepare endpoint data for template"""
        method_name = self._generate_method_name(endpoint)

        if hasattr(endpoint.method, 'value'):
            method_str = endpoint.method.value
        else:
            method_str = str(endpoint.method).upper()

        path = endpoint.path or '/'

        query_params = []
        if hasattr(endpoint, 'parameters') and endpoint.parameters:
            if isinstance(endpoint.parameters, dict):
                for param_name, param_info in endpoint.parameters.items():
                    if isinstance(param_info, dict):
                        if param_info.get('in') == 'query':
                            query_params.append(param_name)
                    else:
                        query_params.append(param_name)
        elif hasattr(endpoint, 'query_params') and endpoint.query_params:
            query_params = list(endpoint.query_params)

        frequency = 0
        if hasattr(endpoint, 'count'):
            frequency = endpoint.count
        elif hasattr(endpoint, 'frequency'):
            frequency = endpoint.frequency

        return {
            'name': method_name,
            'method': method_str,
            'path': path,
            'query_params': query_params[:10],
            'has_body': method_str in ['POST', 'PUT', 'PATCH'],
            'examples': endpoint.examples[:1] if hasattr(endpoint, 'examples') and endpoint.examples else [],
            'frequency': frequency
        }

    def _generate_method_name(self, endpoint: EndpointModel) -> str:
        """Generate clean method name from endpoint"""
        if hasattr(endpoint.method, 'value'):
            method_str = endpoint.method.value.lower()
        else:
            method_str = str(endpoint.method).lower()

        path = endpoint.path or '/'

        path = re.sub(r'^/api/', '/', path)
        path = re.sub(r'^/v[0-9]+/', '/', path)

        parts = [p for p in path.split('/') if p and p != '']

        if not parts:
            return f"{method_str}_root"

        method_parts = [method_str]

        for part in parts[:3]:
            clean = re.sub(r'[^a-zA-Z0-9]', '_', part)
            clean = '_'.join(p for p in clean.split('_') if p)
            if clean:
                method_parts.append(clean)

        seen = set()
        method_parts = [x for x in method_parts if not (x in seen or seen.add(x))]

        return '_'.join(method_parts).lower()

    def _safe_string_literal(self, value: str) -> str:
        """Generate a safe Python string literal using repr()"""
        if not value:
            return "''"
        # repr() handles all edge cases: quotes, backslashes, newlines, etc.
        return repr(value)

    def _generate_embedded_python(self, spec: APISpec, class_name: str) -> str:
        """Generate Python client without template (embedded) with token support"""
        lines = [
            '#!/usr/bin/env python3',
            '"""',
            f'Auto-generated API client from HAR analysis',
            f'Generated: {datetime.now().isoformat()}',
            f'Total Endpoints: {len(spec.endpoints)}',
            '"""',
            '',
            'import requests',
            'import json',
            'from typing import Optional, Dict, Any, List',
            'from datetime import datetime',
            'from urllib.parse import urlencode',
            'import logging',
            'import re',
            'import base64',
            '',
            'logger = logging.getLogger(__name__)',
            '',
            '',
            'class TokenExtractor:',
            '    """Extract and manage tokens from responses"""',
            '',
            '    @staticmethod',
            '    def extract_from_response(response: requests.Response) -> Dict[str, Any]:',
            '        """Extract tokens from response headers and body"""',
            '        tokens = {}',
            '',
            '        # Check response headers',
            '        auth_header = response.headers.get("Authorization")',
            '        if auth_header and auth_header.startswith("Bearer "):',
            '            tokens["bearer_token"] = auth_header[7:]',
            '',
            '        # Check Set-Cookie headers',
            '        set_cookies = response.headers.get("Set-Cookie", "")',
            '        if set_cookies:',
            '            cookies = TokenExtractor._parse_cookies(set_cookies)',
            '            for name, value in cookies.items():',
            '                if any(key in name.lower() for key in ["token", "jwt", "auth", "session"]):',
            '                    tokens.setdefault("cookies", {})[name] = value',
            '',
            '        # Check response body for tokens',
            '        try:',
            '            body = response.json()',
            '            if isinstance(body, dict):',
            '                # Look for token in common fields',
            '                for key in ["token", "access_token", "refresh_token", "auth_token", "jwt"]:',
            '                    if key in body:',
            '                        tokens[key] = body[key]',
            '                # Check nested objects',
            '                if "data" in body and isinstance(body["data"], dict):',
            '                    for key in ["token", "access_token", "refresh_token"]:',
            '                        if key in body["data"]:',
            '                            tokens[f"data_{key}"] = body["data"][key]',
            '        except:',
            '            pass',
            '',
            '        return tokens',
            '',
            '    @staticmethod',
            '    def _parse_cookies(cookie_str: str) -> Dict[str, str]:',
            '        """Parse cookie string into dictionary"""',
            '        cookies = {}',
            '        for cookie in cookie_str.split(","):',
            '            cookie = cookie.strip()',
            '            if "=" in cookie:',
            '                parts = cookie.split(";")',
            '                if parts:',
            '                    key, value = parts[0].split("=", 1)',
            '                    cookies[key.strip()] = value.strip()',
            '        return cookies',
            '',
            '    @staticmethod',
            '    def decode_jwt(token: str) -> Optional[Dict]:',
            '        """Decode JWT without verification"""',
            '        try:',
            '            parts = token.split(".")',
            '            if len(parts) != 3:',
            '                return None',
            '            header = json.loads(base64.urlsafe_b64decode(parts[0] + "==").decode("utf-8"))',
            '            payload = json.loads(base64.urlsafe_b64decode(parts[1] + "==").decode("utf-8"))',
            '            return {',
            '                "header": header,',
            '                "payload": payload,',
            '                "algorithm": header.get("alg", "unknown"),',
            '                "expires_at": payload.get("exp"),',
            '                "issued_at": payload.get("iat"),',
            '                "issuer": payload.get("iss"),',
            '                "subject": payload.get("sub")',
            '            }',
            '        except:',
            '            return None',
            '',
            '',
            f'class {class_name}:',
            f'    """Auto-generated API client from HAR analysis"""',
            '',
            f'    BASE_URL = {self._safe_string_literal(spec.base_url or "")}',
            '',
            '    def __init__(self, ',
            '                 token: Optional[str] = None,',
            '                 cookies: Optional[Dict[str, str]] = None,',
            '                 api_key: Optional[str] = None,',
            '                 auto_extract_tokens: bool = True,',
            '                 **kwargs):',
            '        """Initialize the API client with authentication"""',
            '        self.token = token',
            '        self.api_key = api_key',
            '        self.cookies = cookies or {}',
            '        self.auto_extract_tokens = auto_extract_tokens',
            '        self.extracted_tokens = []',
            '        self.session = requests.Session()',
            '        ',
            '        # Default headers',
            '        self.default_headers = {',
            '            "User-Agent": "APIClient/1.0",',
            '            "Accept": "application/json",',
            '            "Content-Type": "application/json"',
            '        }',
            ''
        ]

        # Add common headers with proper escaping
        if spec.common_headers:
            lines.append('        # Common headers from HAR analysis')
            for name, value in list(spec.common_headers.items())[:10]:
                safe_name = self._safe_string_literal(str(name))
                safe_value = self._safe_string_literal(str(value))
                lines.append(f'        self.default_headers[{safe_name}] = {safe_value}')
            lines.append('')

        # Add authentication support based on detected auth type
        auth_type = getattr(spec.authentication, 'type', 'none')
        lines.extend([
            '        # Apply authentication',
            '        if token:',
            '            self.default_headers["Authorization"] = f"Bearer {token}"',
            '        elif api_key:',
            '            self.default_headers["X-API-Key"] = api_key',
            '',
            '        # Apply cookies',
            '        if cookies:',
            '            cookie_str = "; ".join([f"{k}={v}" for k, v in cookies.items()])',
            '            self.default_headers["Cookie"] = cookie_str',
            '',
            '        for key, value in kwargs.items():',
            '            if key.startswith("header_"):',
            '                header_name = key.replace("header_", "")',
            '                self.default_headers[header_name] = value',
            '',
            '        self.session.headers.update(self.default_headers)',
            '',
            '    def update_auth(self, token: Optional[str] = None,',
            '                    cookies: Optional[Dict[str, str]] = None,',
            '                    api_key: Optional[str] = None):',
            '        """Update authentication credentials"""',
            '        if token:',
            '            self.token = token',
            '            self.session.headers["Authorization"] = f"Bearer {token}"',
            '        if cookies:',
            '            self.cookies.update(cookies)',
            '            cookie_str = "; ".join([f"{k}={v}" for k, v in self.cookies.items()])',
            '            self.session.headers["Cookie"] = cookie_str',
            '        if api_key:',
            '            self.api_key = api_key',
            '            self.session.headers["X-API-Key"] = api_key',
            '',
            '    def get_auth_info(self) -> Dict[str, Any]:',
            '        """Get current authentication information"""',
            '        return {',
            '            "token": self.token,',
            '            "api_key": self.api_key,',
            '            "cookies": self.cookies,',
            '            "extracted_tokens": self.extracted_tokens,',
            '            "headers": dict(self.session.headers)',
            '        }',
            '',
            '    def _extract_tokens_from_response(self, response: requests.Response) -> Dict[str, Any]:',
            '        """Extract and store tokens from response"""',
            '        tokens = TokenExtractor.extract_from_response(response)',
            '        if tokens:',
            '            self.extracted_tokens.append({',
            '                "timestamp": datetime.now().isoformat(),',
            '                "url": response.url,',
            '                "status": response.status_code,',
            '                "tokens": tokens',
            '            })',
            '            # Auto-update token if found',
            '            if "access_token" in tokens and not self.token:',
            '                self.update_auth(token=tokens["access_token"])',
            '        return tokens',
            '',
            '    def _request(self, method: str, path: str,',
            '                  params: Optional[Dict] = None,',
            '                  json_data: Optional[Dict] = None,',
            '                  extract_tokens: bool = True,',
            '                  **kwargs) -> Dict[str, Any]:',
            '        """Make API request with error handling and token extraction"""',
            '        url = f"{self.BASE_URL}{path}"',
            '        try:',
            '            response = self.session.request(',
            '                method=method,',
            '                url=url,',
            '                params=params,',
            '                json=json_data,',
            '                **kwargs',
            '            )',
            '            ',
            '            # Extract tokens from response',
            '            if extract_tokens and self.auto_extract_tokens:',
            '                tokens = self._extract_tokens_from_response(response)',
            '                if tokens:',
            '                    logger.debug(f"Extracted tokens from {response.url}: {list(tokens.keys())}")',
            '',
            '            response.raise_for_status()',
            '            return response.json()',
            '        except requests.exceptions.RequestException as e:',
            '            logger.error(f"Request error: {e}")',
            '            return {"error": str(e)}',
            '        except json.JSONDecodeError as e:',
            '            logger.error(f"JSON decode error: {e}")',
            '            return {"error": "Invalid JSON response"}',
            ''
        ])

        # Add methods for each endpoint
        for endpoint in spec.endpoints[:50]:
            method_name = self._generate_method_name(endpoint)

            if hasattr(endpoint.method, 'value'):
                method_str = endpoint.method.value
            else:
                method_str = str(endpoint.method).upper()

            path = endpoint.path or '/'

            query_params = []
            if hasattr(endpoint, 'parameters') and endpoint.parameters:
                if isinstance(endpoint.parameters, dict):
                    for param_name, param_info in endpoint.parameters.items():
                        if isinstance(param_info, dict):
                            if param_info.get('in') == 'query':
                                query_params.append(param_name)
                        else:
                            query_params.append(param_name)
            elif hasattr(endpoint, 'query_params') and endpoint.query_params:
                query_params = list(endpoint.query_params)

            lines.extend([
                f'    def {method_name}(self,',
            ])

            if query_params:
                for param in query_params[:5]:
                    lines.append(f'                     {param}: Optional[str] = None,')

            lines.extend([
                '                     extract_tokens: bool = True,',
                '                     **kwargs) -> Dict[str, Any]:',
                f'        """{method_str} {path}"""',
                '        params = {}',
            ])

            for param in query_params[:5]:
                lines.append(f'        if {param} is not None:')
                lines.append(f'            params["{param}"] = {param}')

            has_body = method_str in ['POST', 'PUT', 'PATCH']
            if has_body:
                lines.append('        json_data = kwargs.get("json_data", {})')
                lines.append('        for key, value in kwargs.items():')
                lines.append('            if key not in ["json_data", "extract_tokens"]:')
                lines.append('                json_data[key] = value')
            else:
                lines.append('        json_data = None')

            lines.extend([
                '',
                f'        return self._request(',
                f'            method={self._safe_string_literal(method_str)},',
                f'            path={self._safe_string_literal(path)},',
                '            params=params,',
                '            json_data=json_data,',
                '            extract_tokens=extract_tokens,',
                '            **kwargs.get("request_kwargs", {})',
                '        )',
                ''
            ])

        lines.extend([
            '',
            '    def get_all_data(self, max_workers: int = 5) -> Dict[str, Any]:',
            '        """Fetch data from all endpoints in parallel"""',
            '        from concurrent.futures import ThreadPoolExecutor, as_completed',
            '        results = {}',
            '        endpoints = [m for m in dir(self) if callable(getattr(self, m)) and m.startswith(("get_", "post_", "put_", "delete_"))]',
            '        with ThreadPoolExecutor(max_workers=max_workers) as executor:',
            '            futures = {endpoint: executor.submit(getattr(self, endpoint)) for endpoint in endpoints}',
            '            for endpoint, future in futures.items():',
            '                try:',
            '                    results[endpoint] = future.result(timeout=30)',
            '                except Exception as e:',
            '                    results[endpoint] = {"error": str(e)}',
            '        return results',
            '',
            '    def get_extracted_tokens(self) -> List[Dict[str, Any]]:',
            '        """Get all extracted tokens from API calls"""',
            '        return self.extracted_tokens',
            '',
            '    def clear_extracted_tokens(self):',
            '        """Clear extracted tokens history"""',
            '        self.extracted_tokens = []',
            '',
            '',
            '# Example usage',
            'if __name__ == "__main__":',
            '    # Initialize with token',
            f'    client = {class_name}(token="your_token_here")',
            '    ',
            '    # Example: Make API calls',
            '    # result = client.get_some_endpoint()',
            '    ',
            '    # Example: Extract tokens from response',
            '    # result = client.post_login(json_data={"username": "user", "password": "pass"})',
            '    # tokens = client.get_extracted_tokens()',
            '    ',
            '    print("API Client Generated Successfully!")',
            f'    print(f"Base URL: {client.BASE_URL}")',
            f'    print(f"Available methods: {{len([m for m in dir(client) if callable(getattr(client, m)) and not m.startswith(\"_\")])}}")',
            '    print(f"Auth info: {client.get_auth_info()}")'
        ])

        return '\n'.join(lines)

    def _generate_simple_typescript(self, spec: APISpec, class_name: str) -> str:
        """Generate simple TypeScript client with token support if template not found"""
        lines = [
            f'/**',
            f' * Auto-generated TypeScript API client',
            f' * Generated: {datetime.now().isoformat()}',
            f' */',
            '',
            'interface AuthConfig {',
            '  token?: string;',
            '  apiKey?: string;',
            '  cookies?: Record<string, string>;',
            '}',
            '',
            f'export class {class_name} {{',
            f'  private baseURL: string = {json.dumps(spec.base_url or "")};',
            '  private token: string | null = null;',
            '  private apiKey: string | null = null;',
            '  private cookies: Record<string, string> = {};',
            '  private extractedTokens: any[] = [];',
            '',
            '  constructor(config: AuthConfig & { baseURL?: string } = {}) {',
            '    if (config.baseURL) this.baseURL = config.baseURL;',
            '    if (config.token) {',
            '      this.token = config.token;',
            '    }',
            '    if (config.apiKey) {',
            '      this.apiKey = config.apiKey;',
            '    }',
            '    if (config.cookies) {',
            '      this.cookies = config.cookies;',
            '    }',
            '  }',
            '',
            '  private getHeaders(): HeadersInit {',
            '    const headers: HeadersInit = {',
            '      "Content-Type": "application/json",',
            '    };',
            '    if (this.token) {',
            '      headers["Authorization"] = `Bearer ${this.token}`;',
            '    }',
            '    if (this.apiKey) {',
            '      headers["X-API-Key"] = this.apiKey;',
            '    }',
            '    if (Object.keys(this.cookies).length > 0) {',
            '      headers["Cookie"] = Object.entries(this.cookies)',
            '        .map(([k, v]) => `${k}=${v}`)',
            '        .join("; ");',
            '    }',
            '    return headers;',
            '  }',
            '',
            '  private extractTokensFromResponse(response: Response): void {',
            '    const tokens: any = {};',
            '    // Extract from headers',
            '    const authHeader = response.headers.get("Authorization");',
            '    if (authHeader && authHeader.startsWith("Bearer ")) {',
            '      tokens["bearer_token"] = authHeader.substring(7);',
            '    }',
            '    // Extract from Set-Cookie',
            '    const setCookie = response.headers.get("Set-Cookie");',
            '    if (setCookie) {',
            '      const cookies = setCookie.split(",");',
            '      for (const cookie of cookies) {',
            '        const parts = cookie.split(";");',
            '        if (parts.length > 0) {',
            '          const [key, value] = parts[0].split("=");',
            '          if (key && value && /token|jwt|auth|session/i.test(key)) {',
            '            tokens[key.trim()] = value.trim();',
            '          }',
            '        }',
            '      }',
            '    }',
            '    if (Object.keys(tokens).length > 0) {',
            '      this.extractedTokens.push({',
            '        timestamp: new Date().toISOString(),',
            '        url: response.url,',
            '        status: response.status,',
            '        tokens',
            '      });',
            '      // Auto-update token',
            '      if (tokens.access_token && !this.token) {',
            '        this.token = tokens.access_token;',
            '      }',
            '    }',
            '  }',
            '',
            '  private async request(method: string, path: string, body?: any): Promise<any> {',
            '    const response = await fetch(`${this.baseURL}${path}`, {',
            '      method,',
            '      headers: this.getHeaders(),',
            '      body: body ? JSON.stringify(body) : undefined',
            '    });',
            '    // Extract tokens from response',
            '    this.extractTokensFromResponse(response.clone());',
            '    if (!response.ok) {',
            '      throw new Error(`HTTP ${response.status}: ${response.statusText}`);',
            '    }',
            '    return response.json();',
            '  }',
            ''
        ]

        # Add methods for endpoints
        for endpoint in spec.endpoints[:20]:
            method_name = self._generate_method_name(endpoint)

            if hasattr(endpoint.method, 'value'):
                method_str = endpoint.method.value.lower()
            else:
                method_str = str(endpoint.method).lower()

            path = endpoint.path or '/'

            lines.extend([
                f'  async {method_name}(params?: any): Promise<any> {{',
                f'    let path = {json.dumps(path)};',
                '    if (params) {',
                '      const query = new URLSearchParams(params).toString();',
                '      path += query ? "?" + query : "";',
                '    }',
                f'    return this.request({json.dumps(method_str)}, path);',
                '  }}',
                ''
            ])

        lines.extend([
            '  async getAllData(): Promise<Record<string, any>> {',
            '    const methods = Object.getOwnPropertyNames(Object.getPrototypeOf(this))',
            '      .filter(m => m.startsWith("get") && typeof this[m] === "function");',
            '    const results: Record<string, any> = {};',
            '    for (const method of methods) {',
            '      try {',
            '        results[method] = await this[method]();',
            '      } catch (error) {',
            '        results[method] = { error: error.message };',
            '      }',
            '    }',
            '    return results;',
            '  }',
            '',
            '  getExtractedTokens(): any[] {',
            '    return this.extractedTokens;',
            '  }',
            '',
            '  clearExtractedTokens(): void {',
            '    this.extractedTokens = [];',
            '  }',
            '}'
        ])

        return '\n'.join(lines)
