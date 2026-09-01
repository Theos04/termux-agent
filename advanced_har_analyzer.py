#!/usr/bin/env python3
"""
Enhanced HAR Capture & Analysis - Advanced Features
Adds: Token correlation, API endpoint discovery, sensitive data detection
"""

import json
import re
import os
import sys
from collections import defaultdict, Counter
from typing import Dict, List, Any, Set
from datetime import datetime
from urllib.parse import urlparse


class AdvancedHARAnalyzer:
    """Advanced analysis of HAR files with correlation and pattern detection"""
    
    def __init__(self, har_file: str, analysis_file: str = None):
        self.har_file = har_file
        self.analysis_file = analysis_file or har_file.replace('.har', '_advanced_analysis.json')
        self.har_data = None
        self.entries = []
        
        # Analysis results
        self.api_endpoints = defaultdict(lambda: {'methods': set(), 'count': 0, 'tokens': [], 'statuses': [], 'urls': []})
        self.token_correlation = defaultdict(list)
        self.sensitive_data = []
        self.session_flows = []
        self.entry_timeline = []
        
        self.load_har()
        
    def load_har(self):
        """Load HAR file"""
        with open(self.har_file, 'r') as f:
            self.har_data = json.load(f)
            self.entries = self.har_data.get('log', {}).get('entries', [])
            print(f"📊 Loaded {len(self.entries)} entries from {self.har_file}")
    
    def analyze_api_endpoints(self):
        """Discover and analyze API endpoints"""
        print("\n🔍 Analyzing API endpoints...")
        
        for entry in self.entries:
            request = entry.get('request', {})
            url = request.get('url', '')
            method = request.get('method', '')
            status = entry.get('response', {}).get('status', 0)
            
            # Extract API path (remove domain and query params)
            try:
                parsed = urlparse(url)
                path = parsed.path
                # Remove IDs from path for pattern matching
                path_pattern = re.sub(r'/\d+', '/{id}', path)
                path_pattern = re.sub(r'/[a-f0-9]{24,}', '/{objectId}', path_pattern)
                path_pattern = re.sub(r'/[A-Za-z0-9_-]{20,}', '/{token}', path_pattern)
                
                # Remove file extensions
                path_pattern = re.sub(r'\.(json|xml|html|js|css|png|jpg|jpeg|gif|svg|ico)$', '', path_pattern)
                
                key = f"{method} {path_pattern}"
                self.api_endpoints[key]['methods'].add(method)
                self.api_endpoints[key]['count'] += 1
                self.api_endpoints[key]['statuses'].append(status)
                self.api_endpoints[key]['urls'].append(url)
            except:
                continue
        
        # Sort by frequency
        self.api_endpoints = dict(sorted(
            self.api_endpoints.items(),
            key=lambda x: x[1]['count'],
            reverse=True
        ))
        
        print(f"   Found {len(self.api_endpoints)} unique API endpoints")
        return self.api_endpoints
    
    def correlate_tokens_with_requests(self):
        """Correlate tokens with requests to understand token usage"""
        print("\n🔑 Correlating tokens with requests...")
        
        # If analysis file doesn't exist, try to find tokens directly from entries
        if not os.path.exists(self.analysis_file):
            print("   Analysis file not found, extracting tokens from HAR...")
            
            # Extract tokens directly from entries
            for entry in self.entries:
                request = entry.get('request', {})
                headers = request.get('headers', {})
                url = request.get('url', '')
                
                # Check for Bearer tokens
                for key, value in headers.items():
                    if key.lower() == 'authorization' and 'Bearer' in value:
                        token = value.replace('Bearer', '').strip()
                        parsed = urlparse(url)
                        domain = parsed.netloc
                        path_pattern = re.sub(r'/\d+', '/{id}', parsed.path)
                        endpoint_key = f"{domain}{path_pattern}"
                        
                        self.token_correlation[endpoint_key].append({
                            'type': 'Bearer',
                            'value': token[:20] + '...' if len(token) > 20 else token,
                            'url': url
                        })
                    elif 'token' in key.lower() or 'api' in key.lower():
                        if len(str(value)) > 20 and not value in ['true', 'false', 'null']:
                            parsed = urlparse(url)
                            domain = parsed.netloc
                            path_pattern = re.sub(r'/\d+', '/{id}', parsed.path)
                            endpoint_key = f"{domain}{path_pattern}"
                            
                            self.token_correlation[endpoint_key].append({
                                'type': 'API_Key',
                                'value': str(value)[:20] + '...' if len(str(value)) > 20 else str(value),
                                'url': url
                            })
        
        # Count tokens by endpoint
        token_endpoints = {}
        for endpoint, tokens in self.token_correlation.items():
            token_types = defaultdict(int)
            for token in tokens:
                token_types[token['type']] += 1
            token_endpoints[endpoint] = dict(token_types)
        
        print(f"   Found {len(self.token_correlation)} endpoints with token usage")
        return token_endpoints
    
    def detect_sensitive_data(self):
        """Detect sensitive data in requests and responses"""
        print("\n🛡️ Detecting sensitive data...")
        
        sensitive_patterns = {
            'email': re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'),
            'phone': re.compile(r'\b\d{10,15}\b'),
            'aadhar': re.compile(r'\b\d{4}\s?\d{4}\s?\d{4}\b'),
            'pan': re.compile(r'[A-Z]{5}[0-9]{4}[A-Z]{1}'),
            'date_of_birth': re.compile(r'\d{1,2}[-/]\d{1,2}[-/]\d{2,4}'),
            'salary': re.compile(r'₹?\s?[\d,]+\.?\d*\s?(?:LPA|Lakh|K|Crore)'),
            'credit_card': re.compile(r'\b(?:\d{4}[- ]?){3}\d{4}\b'),
            'ip_address': re.compile(r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b'),
            'bearer_token': re.compile(r'Bearer\s+[A-Za-z0-9\-_.]+'),
            'api_key': re.compile(r'[a-zA-Z0-9]{32,64}'),
            'password': re.compile(r'password["\']?\s*[:=]\s*["\']?([^"\',]+)["\']?', re.IGNORECASE),
            'jwt': re.compile(r'eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+'),
        }
        
        sensitive_found = []
        
        for i, entry in enumerate(self.entries):
            request = entry.get('request', {})
            response = entry.get('response', {})
            url = request.get('url', '')
            
            # Check request headers
            headers = request.get('headers', {})
            if isinstance(headers, dict):
                for key, value in headers.items():
                    if isinstance(value, str):
                        for pattern_name, pattern in sensitive_patterns.items():
                            matches = pattern.findall(value)
                            for match in matches:
                                if match and len(match) > 3:  # Avoid false positives
                                    sensitive_found.append({
                                        'type': pattern_name,
                                        'value': match[:50] + '...' if len(match) > 50 else match,
                                        'location': f"{key} header",
                                        'url': url[:100],
                                        'entry': i
                                    })
            
            # Check request body - FIXED: Handle both dict and string
            post_data = request.get('postData', {})
            body = ''
            if isinstance(post_data, dict):
                body = post_data.get('text', '')
                # Also check params if text is empty
                if not body and 'params' in post_data:
                    params = post_data.get('params', [])
                    if isinstance(params, list):
                        body = json.dumps(params)
            elif isinstance(post_data, str):
                body = post_data
            
            if body and isinstance(body, str) and len(body) < 100000:
                for pattern_name, pattern in sensitive_patterns.items():
                    matches = pattern.findall(body)
                    for match in matches:
                        if match and len(match) > 3:
                            sensitive_found.append({
                                'type': pattern_name,
                                'value': match[:50] + '...' if len(match) > 50 else match,
                                'location': 'request body',
                                'url': url[:100],
                                'entry': i
                            })
            
            # Check response body - FIXED: Handle content properly
            content = response.get('content', {})
            response_body = ''
            if isinstance(content, dict):
                response_body = content.get('text', '')
            elif isinstance(content, str):
                response_body = content
            
            if response_body and isinstance(response_body, str) and len(response_body) < 100000:
                for pattern_name, pattern in sensitive_patterns.items():
                    matches = pattern.findall(response_body)
                    for match in matches:
                        if match and len(match) > 3:
                            sensitive_found.append({
                                'type': pattern_name,
                                'value': match[:50] + '...' if len(match) > 50 else match,
                                'location': 'response body',
                                'url': url[:100],
                                'entry': i
                            })
        
        self.sensitive_data = sensitive_found
        print(f"   Found {len(sensitive_found)} potential sensitive data occurrences")
        return sensitive_found
    
    def analyze_session_flow(self):
        """Analyze the flow of a session"""
        print("\n🔀 Analyzing session flow...")
        
        # Track navigation and API calls
        nav_events = []
        api_calls = []
        
        for entry in self.entries:
            request = entry.get('request', {})
            url = request.get('url', '')
            method = request.get('method', '')
            timestamp = entry.get('startedDateTime', '')
            
            # Check if it's a navigation (HTML page load)
            response = entry.get('response', {})
            content_type = response.get('content', {}).get('mimeType', '')
            
            if 'text/html' in content_type or (method == 'GET' and ('html' in url or 'page' in url)):
                nav_events.append({
                    'timestamp': timestamp,
                    'url': url[:100],
                    'status': response.get('status', 0)
                })
            elif 'api' in url or 'json' in content_type or '/v1/' in url or '/v2/' in url:
                # API call
                api_calls.append({
                    'timestamp': timestamp,
                    'method': method,
                    'url': url[:100],
                    'status': response.get('status', 0)
                })
        
        self.session_flows = {
            'navigation_events': len(nav_events),
            'api_calls': len(api_calls),
            'navigations': nav_events[:10],  # First 10
            'apis': api_calls[:20]  # First 20
        }
        
        print(f"   Navigation events: {len(nav_events)}")
        print(f"   API calls: {len(api_calls)}")
        return self.session_flows
    
    def generate_timeline(self):
        """Generate a timeline of events"""
        print("\n📅 Generating event timeline...")
        
        timeline = []
        for entry in self.entries[:50]:  # First 50 entries
            request = entry.get('request', {})
            response = entry.get('response', {})
            timestamp = entry.get('startedDateTime', '')
            duration = entry.get('time', 0)
            
            timeline.append({
                'time': timestamp,
                'method': request.get('method', ''),
                'url': request.get('url', '')[:80],
                'status': response.get('status', 0),
                'duration_ms': duration
            })
        
        self.entry_timeline = timeline
        print(f"   Generated timeline with {len(timeline)} events")
        return timeline
    
    def generate_security_report(self):
        """Generate a security report"""
        print("\n🛡️ Generating security report...")
        
        # Check for security issues
        issues = []
        recommendations = []
        
        # Check for missing security headers
        security_headers_seen = set()
        for entry in self.entries:
            headers = entry.get('response', {}).get('headers', {})
            if isinstance(headers, dict):
                for key in headers:
                    if key.lower() in ['strict-transport-security', 'content-security-policy', 
                                      'x-frame-options', 'x-content-type-options']:
                        security_headers_seen.add(key.lower())
        
        missing = []
        important_headers = ['strict-transport-security', 'content-security-policy', 'x-frame-options']
        for header in important_headers:
            if header not in security_headers_seen:
                missing.append(header)
        
        if missing:
            issues.append(f"Missing security headers: {', '.join(missing)}")
            recommendations.append(f"Add {', '.join(missing)} headers to improve security")
        
        # Check for sensitive data exposure
        if self.sensitive_data:
            sensitive_types = Counter([s['type'] for s in self.sensitive_data])
            for stype, count in sensitive_types.items():
                if count > 5:
                    issues.append(f"Found {count} occurrences of {stype} in responses")
                    recommendations.append(f"Review {stype} exposure in API responses")
        
        # Check for authentication issues
        auth_failures = sum(1 for e in self.entries if e.get('response', {}).get('status', 0) == 401)
        if auth_failures > 0:
            issues.append(f"Found {auth_failures} authentication failures (401)")
            recommendations.append("Check token expiration and refresh mechanisms")
        
        # Check for tokens in URLs
        tokens_in_url = 0
        for entry in self.entries:
            url = entry.get('request', {}).get('url', '')
            if 'token=' in url or 'auth=' in url or 'api_key=' in url or 'access_token=' in url:
                tokens_in_url += 1
        if tokens_in_url > 0:
            issues.append(f"Found {tokens_in_url} requests with tokens in URL")
            recommendations.append("Avoid exposing tokens in URLs, use headers instead")
        
        security_report = {
            'issues': issues,
            'recommendations': recommendations,
            'security_headers_present': len(security_headers_seen),
            'missing_headers': missing,
            'auth_failures': auth_failures,
            'tokens_in_url': tokens_in_url
        }
        
        print(f"   Found {len(issues)} security issues")
        return security_report
    
    def save_advanced_analysis(self):
        """Save advanced analysis to file"""
        print(f"\n💾 Saving advanced analysis to: {self.analysis_file}")
        
        # Get security report without re-running detection
        security_issues = self.detect_security_issues()
        
        advanced_analysis = {
            'summary': {
                'total_entries': len(self.entries),
                'api_endpoints': len(self.api_endpoints),
                'tokens_correlated': len(self.token_correlation),
                'sensitive_data_found': len(self.sensitive_data),
                'security_issues': len(security_issues)
            },
            'api_endpoints': {k: {
                'count': v['count'],
                'methods': list(v['methods']),
                'statuses': list(v['statuses'])
            } for k, v in list(self.api_endpoints.items())[:30]},
            'token_correlation': {k: v[:10] for k, v in list(self.token_correlation.items())[:20]},
            'sensitive_data': self.sensitive_data[:50],
            'session_flow': self.session_flows,
            'timeline': self.entry_timeline,
            'security_report': self.generate_security_report(),
            'timestamp': datetime.now().isoformat()
        }
        
        with open(self.analysis_file, 'w') as f:
            json.dump(advanced_analysis, f, indent=2, default=str)
        
        print(f"✅ Advanced analysis saved!")
        return self.analysis_file
    
    def detect_security_issues(self):
        """Detect security issues"""
        issues = []
        
        # Check for tokens in URLs (exposure)
        for entry in self.entries:
            url = entry.get('request', {}).get('url', '')
            if 'token=' in url or 'auth=' in url or 'api_key=' in url or 'access_token=' in url:
                issues.append(f"Token in URL: {url[:80]}")
        
        # Check for sensitive data in headers
        for entry in self.entries:
            headers = entry.get('request', {}).get('headers', {})
            if isinstance(headers, dict):
                for key, value in headers.items():
                    if 'password' in key.lower() or 'secret' in key.lower():
                        issues.append(f"Sensitive header: {key}")
        
        # Check for missing HTTPS
        for entry in self.entries:
            url = entry.get('request', {}).get('url', '')
            if url.startswith('http://') and 'localhost' not in url and '127.0.0.1' not in url:
                issues.append(f"HTTP request (not HTTPS): {url[:80]}")
                break  # Just report once
        
        return issues
    
    def print_summary(self):
        """Print a comprehensive summary"""
        print("\n" + "="*70)
        print("📊 ADVANCED ANALYSIS SUMMARY")
        print("="*70)
        
        # API Endpoints
        print(f"\n🔗 API Endpoints: {len(self.api_endpoints)}")
        print("   Top 10 endpoints:")
        for i, (endpoint, data) in enumerate(list(self.api_endpoints.items())[:10], 1):
            status_counts = dict(Counter(data['statuses']))
            print(f"   {i}. {endpoint}")
            print(f"      Calls: {data['count']}, Statuses: {status_counts}")
        
        # Token Correlation
        print(f"\n🔑 Token Usage: {len(self.token_correlation)} endpoints use tokens")
        if self.token_correlation:
            print("   Top 5 endpoints with tokens:")
            for i, (endpoint, tokens) in enumerate(list(self.token_correlation.items())[:5], 1):
                token_types = Counter([t['type'] for t in tokens])
                print(f"   {i}. {endpoint[:50]}")
                print(f"      {dict(token_types)}")
        
        # Sensitive Data
        print(f"\n🛡️ Sensitive Data: {len(self.sensitive_data)} occurrences")
        if self.sensitive_data:
            sensitive_types = Counter([s['type'] for s in self.sensitive_data])
            for stype, count in sensitive_types.most_common(5):
                print(f"   • {stype}: {count}")
        
        # Security Issues
        security_issues = self.detect_security_issues()
        print(f"\n⚠️ Security Issues: {len(security_issues)}")
        if security_issues:
            for issue in security_issues[:5]:
                print(f"   • {issue[:80]}")
            if len(security_issues) > 5:
                print(f"   ... and {len(security_issues) - 5} more")
        
        # Session Flow
        print(f"\n🔀 Session Flow:")
        print(f"   • Navigation events: {self.session_flows.get('navigation_events', 0)}")
        print(f"   • API calls: {self.session_flows.get('api_calls', 0)}")
        
        print("\n" + "="*70)
        print(f"💾 Full analysis saved to: {self.analysis_file}")
        print("="*70)


def analyze_har(har_file: str):
    """Analyze a HAR file with advanced features"""
    print(f"\n🔍 Advanced analysis of: {har_file}")
    print("="*50)
    
    # Create analyzer
    analyzer = AdvancedHARAnalyzer(har_file)
    
    # Run analyses
    analyzer.analyze_api_endpoints()
    analyzer.correlate_tokens_with_requests()
    analyzer.detect_sensitive_data()
    analyzer.analyze_session_flow()
    analyzer.generate_timeline()
    
    # Save and print summary
    analyzer.save_advanced_analysis()
    analyzer.print_summary()
    
    return analyzer


if __name__ == "__main__":
    # If HAR file provided, analyze it
    if len(sys.argv) > 1:
        har_file = sys.argv[1]
        analyze_har(har_file)
    else:
        print("Usage: python advanced_har_analyzer.py <har_file.har>")
        print("\nExample:")
        print("  python advanced_har_analyzer.py har_capture_20260802_161434.har")
