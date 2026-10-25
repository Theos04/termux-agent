"""
HAR Analyzer - Analyzes parsed HAR data
"""

from typing import Dict, Any, List, Optional
from collections import Counter, defaultdict
from dataclasses import dataclass, field
import json

class HARAnalyzer:
    """Analyze HAR data and extract insights"""
    
    def __init__(self, spec):
        self.spec = spec
        self.results = {}
    
    def analyze(self) -> Dict[str, Any]:
        """Perform comprehensive analysis"""
        self.results = {
            "summary": self._analyze_summary(),
            "methods": self._analyze_methods(),
            "status_codes": self._analyze_status_codes(),
            "endpoints": self._analyze_endpoints(),
            "authentication": self._analyze_auth(),
            "headers": self._analyze_headers(),
            "parameters": self._analyze_parameters(),
            "statistics": self._analyze_statistics()
        }
        return self.results
    
    def _analyze_summary(self) -> Dict[str, Any]:
        """Analyze summary statistics"""
        total_requests = sum(e.count for e in self.spec.endpoints)
        return {
            "base_url": self.spec.base_url or "Not detected",
            "total_endpoints": len(self.spec.endpoints),
            "total_requests": total_requests,
            "auth_type": self.spec.authentication.type,
            "requires_auth": self.spec.authentication.requires_auth
        }
    
    def _analyze_methods(self) -> Dict[str, int]:
        """Analyze HTTP methods"""
        methods = Counter()
        for endpoint in self.spec.endpoints:
            # endpoint.method is a string, not an enum
            methods[endpoint.method] += endpoint.count
        return dict(methods)
    
    def _analyze_status_codes(self) -> Dict[str, int]:
        """Analyze response status codes"""
        status_codes = Counter()
        for endpoint in self.spec.endpoints:
            for status in endpoint.responses.keys():
                status_codes[status] += 1
        return dict(status_codes)
    
    def _analyze_endpoints(self) -> List[Dict[str, Any]]:
        """Analyze individual endpoints"""
        endpoints = []
        for endpoint in self.spec.endpoints:
            endpoints.append({
                "path": endpoint.path,
                "method": endpoint.method,  # string
                "count": endpoint.count,
                "parameters": len(endpoint.parameters),
                "responses": list(endpoint.responses.keys()),
                "has_body": bool(endpoint.request_body),
                "examples": len(endpoint.examples)
            })
        return endpoints
    
    def _analyze_auth(self) -> Dict[str, Any]:
        """Analyze authentication"""
        auth = self.spec.authentication
        return {
            "type": auth.type,
            "header_name": auth.header_name,
            "requires_auth": auth.requires_auth,
            "token_location": auth.token_location
        }
    
    def _analyze_headers(self) -> Dict[str, Any]:
        """Analyze common headers"""
        common_headers = self.spec.common_headers
        return {
            "common_headers": common_headers,
            "count": len(common_headers)
        }
    
    def _analyze_parameters(self) -> Dict[str, Any]:
        """Analyze parameters"""
        all_params = {}
        for endpoint in self.spec.endpoints:
            if endpoint.parameters:
                all_params[endpoint.path] = endpoint.parameters
        return all_params
    
    def _analyze_statistics(self) -> Dict[str, Any]:
        """Analyze statistics"""
        stats = self.spec.metadata or {}
        return {
            "total_entries": stats.get("total_entries", 0),
            "parsed_requests": stats.get("parsed_requests", 0),
            "parse_errors": len(stats.get("parse_errors", [])),
            "success_rate": stats.get("success_rate", 0)
        }
    
    def print_report(self, detailed: bool = False) -> None:
        """Print analysis report"""
        if not self.results:
            self.analyze()
        
        print("\n" + "=" * 60)
        print("📊 HAR ANALYSIS REPORT")
        print("=" * 60)
        
        # Summary
        summary = self.results["summary"]
        print(f"\n📍 Base URL: {summary['base_url']}")
        print(f"📝 Total Endpoints: {summary['total_endpoints']}")
        print(f"📨 Total Requests: {summary['total_requests']}")
        
        if summary['requires_auth']:
            print(f"🔐 Authentication: {summary['auth_type'].upper()}")
        
        # Methods
        methods = self.results["methods"]
        if methods:
            print("\n🔧 HTTP Methods:")
            for method, count in sorted(methods.items(), key=lambda x: x[1], reverse=True):
                print(f"   {method}: {count}")
        
        # Status codes
        status_codes = self.results["status_codes"]
        if status_codes:
            print("\n✅ Status Codes:")
            for code, count in sorted(status_codes.items(), key=lambda x: x[1], reverse=True):
                print(f"   {code}: {count}")
        
        # Common headers
        headers = self.results["headers"]
        if headers["common_headers"]:
            print("\n📋 Common Headers:")
            for name, value in list(headers["common_headers"].items())[:5]:
                print(f"   {name}: {value[:50]}{'...' if len(value) > 50 else ''}")
            if len(headers["common_headers"]) > 5:
                print(f"   ... and {len(headers['common_headers']) - 5} more")
        
        # Detailed endpoints
        if detailed:
            print("\n" + "=" * 60)
            print("🎯 ENDPOINTS DETAIL")
            print("=" * 60)
            
            endpoints = self.results["endpoints"]
            for idx, endpoint in enumerate(endpoints, 1):
                print(f"\n{idx}. {endpoint['method']} {endpoint['path']}")
                print(f"   📊 Count: {endpoint['count']}")
                print(f"   📝 Parameters: {endpoint['parameters']}")
                if endpoint['responses']:
                    print(f"   ✅ Status Codes: {', '.join(endpoint['responses'])}")
                if endpoint['examples']:
                    print(f"   📌 Examples: {endpoint['examples']}")
        
        # Statistics
        stats = self.results["statistics"]
        print("\n" + "=" * 60)
        print("📈 STATISTICS")
        print("=" * 60)
        print(f"   Total Entries: {stats['total_entries']}")
        print(f"   Parsed Requests: {stats['parsed_requests']}")
        print(f"   Parse Errors: {stats['parse_errors']}")
        if stats['success_rate']:
            print(f"   Success Rate: {stats['success_rate']:.1f}%")
        
        print("\n" + "=" * 60)
    
    def to_json(self) -> str:
        """Export analysis as JSON"""
        if not self.results:
            self.analyze()
        return json.dumps(self.results, indent=2, default=str)
    
    def to_markdown(self) -> str:
        """Export analysis as Markdown"""
        if not self.results:
            self.analyze()
        
        lines = []
        lines.append("# HAR Analysis Report\n")
        
        # Summary
        summary = self.results["summary"]
        lines.append("## Summary")
        lines.append(f"- **Base URL**: {summary['base_url']}")
        lines.append(f"- **Total Endpoints**: {summary['total_endpoints']}")
        lines.append(f"- **Total Requests**: {summary['total_requests']}")
        if summary['requires_auth']:
            lines.append(f"- **Authentication**: {summary['auth_type'].upper()}")
        lines.append("")
        
        # Methods
        methods = self.results["methods"]
        if methods:
            lines.append("## HTTP Methods")
            for method, count in sorted(methods.items(), key=lambda x: x[1], reverse=True):
                lines.append(f"- **{method}**: {count}")
            lines.append("")
        
        # Status codes
        status_codes = self.results["status_codes"]
        if status_codes:
            lines.append("## Status Codes")
            for code, count in sorted(status_codes.items(), key=lambda x: x[1], reverse=True):
                lines.append(f"- **{code}**: {count}")
            lines.append("")
        
        # Endpoints
        lines.append("## Endpoints")
        endpoints = self.results["endpoints"]
        for endpoint in endpoints:
            lines.append(f"### {endpoint['method']} {endpoint['path']}")
            lines.append(f"- **Count**: {endpoint['count']}")
            lines.append(f"- **Parameters**: {endpoint['parameters']}")
            if endpoint['responses']:
                lines.append(f"- **Status Codes**: {', '.join(endpoint['responses'])}")
            lines.append("")
        
        return "\n".join(lines)
