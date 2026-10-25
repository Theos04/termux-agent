"""
Documentation generation from API specifications
"""

from datetime import datetime
from typing import List, Dict, Any

from ..core.models import APISpec, EndpointModel


class DocsGenerator:
    """Generate API documentation"""
    
    def generate_markdown(self, spec: APISpec) -> str:
        """Generate Markdown documentation"""
        # Get title from spec or use default
        title = getattr(spec, 'title', 'API from HAR Analysis')
        
        lines = [
            f"# {title}",
            "",
            f"**Generated from HAR analysis on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}**",
            "",
            "## Overview",
            "",
            f"- **Base URL**: `{spec.base_url or 'Not detected'}`",
            f"- **Total Endpoints**: {len(spec.endpoints)}",
        ]
        
        # Add authentication info
        if hasattr(spec, 'authentication') and spec.authentication:
            auth_type = getattr(spec.authentication, 'type', 'none')
            if auth_type and auth_type != 'none':
                lines.append(f"- **Authentication**: {auth_type.upper()}")
        else:
            lines.append("- **Authentication**: None detected")
        
        lines.append("")
        
        # Add authentication details if available
        if hasattr(spec, 'authentication') and spec.authentication:
            auth_type = getattr(spec.authentication, 'type', None)
            if auth_type and auth_type != 'none':
                lines.extend([
                    "## Authentication",
                    "",
                    f"- **Type**: {auth_type.upper()}",
                ])
                if hasattr(spec.authentication, 'header_name') and spec.authentication.header_name:
                    lines.append(f"- **Header**: `{spec.authentication.header_name}`")
                if hasattr(spec.authentication, 'confidence') and spec.authentication.confidence:
                    lines.append(f"- **Confidence**: {spec.authentication.confidence * 100:.1f}%")
                lines.append("")
        
        # Common headers
        if spec.common_headers:
            lines.extend([
                "## Common Headers",
                ""
            ])
            for name, value in list(spec.common_headers.items())[:10]:
                safe_value = value.replace('`', '')
                lines.append(f"- `{name}`: `{safe_value[:50]}...`" if len(safe_value) > 50 else f"- `{name}`: `{safe_value}`")
            if len(spec.common_headers) > 10:
                lines.append(f"- ... and {len(spec.common_headers) - 10} more")
            lines.append("")
        
        # Endpoints
        lines.extend([
            "## Endpoints",
            ""
        ])
        
        # Group by method
        grouped = {}
        for endpoint in spec.endpoints:
            # Get method string
            if hasattr(endpoint.method, 'value'):
                method = endpoint.method.value
            else:
                method = str(endpoint.method).upper()
            
            if method not in grouped:
                grouped[method] = []
            grouped[method].append(endpoint)
        
        for method, endpoints in grouped.items():
            lines.append(f"### {method} Methods ({len(endpoints)})")
            lines.append("")
            lines.append("| Path | Frequency | Query Params |")
            lines.append("|------|-----------|--------------|")
            
            for endpoint in endpoints[:20]:
                path = endpoint.path or '/'
                frequency = getattr(endpoint, 'count', getattr(endpoint, 'frequency', 0))
                
                # Get query params
                params = []
                if hasattr(endpoint, 'parameters') and endpoint.parameters:
                    if isinstance(endpoint.parameters, dict):
                        for param_name, param_info in endpoint.parameters.items():
                            if isinstance(param_info, dict):
                                if param_info.get('in') == 'query':
                                    params.append(param_name)
                            else:
                                params.append(param_name)
                elif hasattr(endpoint, 'query_params') and endpoint.query_params:
                    params = list(endpoint.query_params)
                
                params_str = ", ".join(params[:5])
                if len(params) > 5:
                    params_str += "..."
                
                lines.append(f"| `{path}` | {frequency} | {params_str} |")
            
            if len(endpoints) > 20:
                lines.append(f"| ... and {len(endpoints) - 20} more | | |")
            
            lines.append("")
        
        # Add usage example
        lines.extend([
            "## Usage Example",
            "",
            "```python",
            "from moneycontrol_client import MoneyControlAPI",
            "",
            "# Initialize client",
            "client = MoneyControlAPI(token='your_token_here')",
            "",
            "# Get all data",
            "# data = client.get_all_data()",
            "",
            "# Or call specific endpoints",
            "# result = client.get_syncframe()",
            "```",
            "",
            "## Notes",
            "",
            "- This client was auto-generated from HAR analysis",
            "- Some endpoints may require authentication",
            "- Rate limiting may apply to API calls",
            "- Check the actual API documentation for detailed parameters"
        ])
        
        return "\n".join(lines)
