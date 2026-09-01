#!/usr/bin/env python3
"""
HarSuite - Complete Web Security Testing Platform
Burp Suite-like functionality built on your HAR capture foundation
"""

import os
import sys
import json
import time
import threading
import queue
import signal
import logging
import traceback
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple, Set
from datetime import datetime
from enum import Enum
from pathlib import Path
import hashlib
import base64
import re
from urllib.parse import urlparse, parse_qs, urljoin
import subprocess
import tempfile

# For proxy functionality
try:
    from mitmproxy import http
    from mitmproxy.tools import main as mitmproxy_main
    MITMPROXY_AVAILABLE = True
except ImportError:
    MITMPROXY_AVAILABLE = False

# For GUI (optional)
try:
    import tkinter as tk
    from tkinter import ttk, scrolledtext, messagebox
    TKINTER_AVAILABLE = True
except ImportError:
    TKINTER_AVAILABLE = False

# Import your existing modules
from quick_capture_har_2 import (
    JourneyHARCapture, CaptureConfig, TabInfo, 
    CaptureStatus, TokenExtractor, AttackSurfaceMapper,
    ConnectionManager, logger
)

# =============================================================================
# CORE DATA MODELS
# =============================================================================

@dataclass
class HttpMessage:
    """Unified HTTP message representation"""
    id: str
    timestamp: float
    method: str
    url: str
    headers: Dict[str, str]
    body: Optional[bytes]
    status_code: Optional[int] = None
    response_headers: Optional[Dict[str, str]] = None
    response_body: Optional[bytes] = None
    elapsed_ms: Optional[float] = None
    source: str = "browser"  # browser, proxy, repeater, intruder
    tab_id: Optional[str] = None
    notes: List[str] = field(default_factory=list)
    
    def to_har_entry(self) -> Dict:
        """Convert to HAR entry format"""
        return {
            'startedDateTime': datetime.fromtimestamp(self.timestamp).isoformat(),
            'request': {
                'method': self.method,
                'url': self.url,
                'headers': [
                    {'name': k, 'value': v} 
                    for k, v in self.headers.items()
                ],
                'bodySize': len(self.body) if self.body else 0,
            },
            'response': {
                'status': self.status_code or 0,
                'statusText': '',
                'headers': [
                    {'name': k, 'value': v}
                    for k, v in (self.response_headers or {}).items()
                ],
                'bodySize': len(self.response_body) if self.response_body else 0,
            },
            'time': self.elapsed_ms or 0
        }
    
    def to_curl(self) -> str:
        """Generate cURL command"""
        curl = f"curl -X {self.method} '{self.url}'"
        for k, v in self.headers.items():
            curl += f" -H '{k}: {v}'"
        if self.body:
            curl += f" -d '{self.body.decode('utf-8', errors='ignore')}'"
        return curl
    
    def to_python(self) -> str:
        """Generate Python requests code"""
        code = f"import requests\n\nresponse = requests.{self.method.lower()}('{self.url}', "
        if self.headers:
            code += f"headers={json.dumps(self.headers)}, "
        if self.body:
            code += f"data={repr(self.body.decode('utf-8', errors='ignore'))}"
        code += ")\n\nprint(response.status_code)\nprint(response.text)"
        return code

# =============================================================================
# MODULE 1: INTERCEPTING PROXY
# =============================================================================

class InterceptingProxy:
    """MITM proxy with intercept and modify capabilities"""
    
    def __init__(self, port: int = 8080):
        self.port = port
        self.intercept_enabled = True
        self.intercept_mode = "request"  # request, response, all, none
        self.pending_intercepts: Dict[str, HttpMessage] = {}
        self.modified_requests: Dict[str, HttpMessage] = {}
        self.all_requests: List[HttpMessage] = []
        self.message_queue: queue.Queue = queue.Queue()
        self.is_running = False
        self.proxy_process = None
        self.capture_callback = None
        self.scope: Dict[str, List[str]] = {
            'include': [],
            'exclude': []
        }
        
    def start(self):
        """Start the proxy"""
        if not MITMPROXY_AVAILABLE:
            logger.error("mitmproxy not installed. Install with: pip install mitmproxy")
            return False
            
        if self.is_running:
            return True
            
        logger.info(f"🚀 Starting proxy on port {self.port}")
        self.is_running = True
        
        # Start mitmproxy as subprocess
        try:
            # Create addon script
            addon_script = self._create_addon_script()
            
            # Start mitmproxy
            cmd = [
                'mitmdump',
                '-p', str(self.port),
                '--scripts', addon_script,
                '--quiet'
            ]
            
            self.proxy_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            # Check if it started successfully
            time.sleep(2)
            if self.proxy_process.poll() is not None:
                stderr = self.proxy_process.stderr.read()
                logger.error(f"Proxy failed to start: {stderr}")
                self.is_running = False
                return False
                
            logger.info(f"✅ Proxy running on port {self.port}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start proxy: {e}")
            self.is_running = False
            return False
    
    def stop(self):
        """Stop the proxy"""
        if not self.is_running:
            return
            
        logger.info("🛑 Stopping proxy")
        
        if self.proxy_process:
            self.proxy_process.terminate()
            try:
                self.proxy_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proxy_process.kill()
            self.proxy_process = None
            
        self.is_running = False
        logger.info("✅ Proxy stopped")
    
    def _create_addon_script(self) -> str:
        """Create the mitmproxy addon script"""
        script_content = '''
import json
import sys
from mitmproxy import http, ctx

class HarSuiteProxy:
    def __init__(self):
        self.intercept_enabled = True
        self.modified_requests = {}
        
    def request(self, flow: http.HTTPFlow) -> None:
        """Intercept and possibly modify requests"""
        if not self.intercept_enabled:
            return
            
        # Log request
        msg = {
            'type': 'request',
            'method': flow.request.method,
            'url': flow.request.pretty_url,
            'headers': dict(flow.request.headers),
            'body': flow.request.content.decode('utf-8', errors='ignore') if flow.request.content else None,
            'timestamp': flow.request.timestamp_start
        }
        
        # Send to main process via stdout
        print(f"PROXY_MSG: {json.dumps(msg)}", flush=True)
        
        # Check for modifications
        if flow.id in self.modified_requests:
            mod = self.modified_requests[flow.id]
            if 'headers' in mod:
                for k, v in mod['headers'].items():
                    flow.request.headers[k] = v
            if 'body' in mod:
                flow.request.content = mod['body'].encode()
            if 'method' in mod:
                flow.request.method = mod['method']
            if 'url' in mod:
                flow.request.url = mod['url']
            del self.modified_requests[flow.id]
    
    def response(self, flow: http.HTTPFlow) -> None:
        """Intercept and possibly modify responses"""
        if not self.intercept_enabled:
            return
            
        # Log response
        msg = {
            'type': 'response',
            'request_id': flow.id,
            'status': flow.response.status_code,
            'headers': dict(flow.response.headers),
            'body': flow.response.content.decode('utf-8', errors='ignore') if flow.response.content else None,
            'timestamp': flow.response.timestamp_start
        }
        
        print(f"PROXY_MSG: {json.dumps(msg)}", flush=True)

addons = [HarSuiteProxy()]
'''
        # Write to temp file
        temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False)
        temp_file.write(script_content)
        temp_file.close()
        return temp_file.name
    
    def is_in_scope(self, url: str) -> bool:
        """Check if URL is in scope"""
        if self.scope['exclude']:
            for pattern in self.scope['exclude']:
                if pattern in url:
                    return False
                    
        if self.scope['include']:
            for pattern in self.scope['include']:
                if pattern in url:
                    return True
            return False
            
        return True
    
    def modify_request(self, request_id: str, modifications: Dict):
        """Queue modifications for a request"""
        # This would be called from the UI/CLI
        # Store modifications to be applied
        pass

# =============================================================================
# MODULE 2: REPEATER
# =============================================================================

class Repeater:
    """Manual request replay like Burp Repeater"""
    
    def __init__(self):
        self.sessions: Dict[str, List[HttpMessage]] = {}
        self.active_sessions: Dict[str, Dict] = {}
        self.request_history: List[HttpMessage] = []
        self.session_counter = 0
        
    def create_session(self, request: HttpMessage) -> str:
        """Create a new repeater session"""
        self.session_counter += 1
        session_id = f"repeater_{self.session_counter}"
        
        self.sessions[session_id] = [request]
        self.active_sessions[session_id] = {
            'name': f"Session {self.session_counter}",
            'created': datetime.now().isoformat(),
            'modified': datetime.now().isoformat()
        }
        
        return session_id
    
    def send_request(self, request: HttpMessage, session_id: Optional[str] = None) -> HttpMessage:
        """Send request and return response"""
        # Clone request
        req = HttpMessage(
            id=f"req_{int(time.time())}",
            timestamp=time.time(),
            method=request.method,
            url=request.url,
            headers=request.headers.copy(),
            body=request.body,
            source="repeater"
        )
        
        # Send via HTTP (using requests)
        try:
            import requests
            import urllib3
            urllib3.disable_warnings()
            
            start_time = time.time()
            
            # Prepare request
            kwargs = {
                'method': req.method,
                'url': req.url,
                'headers': req.headers,
                'verify': False,
                'allow_redirects': False
            }
            
            if req.body:
                kwargs['data'] = req.body
                
            response = requests.request(**kwargs)
            
            # Build response
            req.status_code = response.status_code
            req.response_headers = dict(response.headers)
            req.response_body = response.content
            req.elapsed_ms = (time.time() - start_time) * 1000
            
            # Log
            if session_id and session_id in self.sessions:
                self.sessions[session_id].append(req)
            
            self.request_history.append(req)
            
            return req
            
        except Exception as e:
            logger.error(f"Repeater request failed: {e}")
            req.status_code = 0
            req.response_headers = {}
            req.response_body = str(e).encode()
            return req
    
    def modify_and_send(self, request: HttpMessage, modifications: Dict, session_id: Optional[str] = None) -> HttpMessage:
        """Modify and send request"""
        modified = HttpMessage(
            id=f"mod_{int(time.time())}",
            timestamp=time.time(),
            method=modifications.get('method', request.method),
            url=modifications.get('url', request.url),
            headers=request.headers.copy(),
            body=request.body,
            source="repeater_mod"
        )
        
        # Apply modifications
        if 'headers' in modifications:
            modified.headers.update(modifications['headers'])
            
        if 'body' in modifications:
            modified.body = modifications['body'].encode() if isinstance(modifications['body'], str) else modifications['body']
            
        if 'remove_headers' in modifications:
            for header in modifications['remove_headers']:
                if header in modified.headers:
                    del modified.headers[header]
                    
        return self.send_request(modified, session_id)
    
    def get_session(self, session_id: str) -> Optional[List[HttpMessage]]:
        """Get session history"""
        return self.sessions.get(session_id)
    
    def get_all_sessions(self) -> List[Dict]:
        """Get all sessions"""
        return [
            {
                'id': sid,
                'name': info['name'],
                'created': info['created'],
                'modified': info['modified'],
                'requests': len(self.sessions.get(sid, []))
            }
            for sid, info in self.active_sessions.items()
        ]

# =============================================================================
# MODULE 3: INTRUDER
# =============================================================================

class Intruder:
    """Automated request fuzzing like Burp Intruder"""
    
    def __init__(self):
        self.attacks: Dict[str, Dict] = {}
        self.results: Dict[str, List[Dict]] = {}
        self.attack_counter = 0
        self.payload_sets = {
            'common': ['admin', 'test', 'password', '123456', 'root', 'user'],
            'sql_injection': [
                "' OR '1'='1",
                "' OR 1=1--",
                "'; DROP TABLE users--",
                "' UNION SELECT NULL--",
                "' AND 1=1--",
                "' AND 1=2--",
                "' OR '1'='1' --",
                "' OR '1'='1' ; --",
            ],
            'xss': [
                "<script>alert(1)</script>",
                '"><script>alert(1)</script>',
                "javascript:alert(1)",
                "<img src=x onerror=alert(1)>",
                "'';!--\"<XSS>=&{()}",
            ],
            'path_traversal': [
                "../../../etc/passwd",
                "..\\..\\windows\\win.ini",
                "../../../../etc/passwd",
                "../../../../../../etc/passwd",
            ],
            'ssrf': [
                "http://169.254.169.254/latest/meta-data/",
                "http://localhost:8080/",
                "http://127.0.0.1/",
                "http://0.0.0.0/",
            ],
            'header_injection': [
                "test\r\nX-Injected: header",
                "test%0d%0aX-Injected: header",
                "test%0aX-Injected: header",
            ],
            'command_injection': [
                "; ls",
                "| ls",
                "& ls",
                "`ls`",
                "$(ls)",
                "; id",
                "| id",
                "& id",
            ],
            'xxe': [
                '<?xml version="1.0"?><!DOCTYPE root [<!ENTITY test SYSTEM "file:///etc/passwd">]><root>&test;</root>',
                '<?xml version="1.0"?><!DOCTYPE root [<!ENTITY test SYSTEM "http://169.254.169.254/">]><root>&test;</root>',
            ],
            'idor': [
                '1',
                '2',
                '3',
                '4',
                '5',
                '10',
                '100',
                '999',
                'admin',
                'test',
                'null',
                'true',
                'false',
            ],
        }
        
    def create_attack(self, base_request: HttpMessage, attack_type: str, positions: List[Tuple[str, str]]) -> str:
        """Create a new attack"""
        self.attack_counter += 1
        attack_id = f"attack_{self.attack_counter}"
        
        self.attacks[attack_id] = {
            'id': attack_id,
            'base_request': base_request,
            'type': attack_type,
            'positions': positions,
            'status': 'pending',
            'created': datetime.now().isoformat(),
            'total_payloads': 0,
            'completed': 0
        }
        
        self.results[attack_id] = []
        
        return attack_id
    
    def run_attack(self, attack_id: str, payloads: List[str], concurrent: int = 5) -> List[Dict]:
        """Run attack with payloads"""
        if attack_id not in self.attacks:
            raise ValueError(f"Attack {attack_id} not found")
            
        attack = self.attacks[attack_id]
        base = attack['base_request']
        
        results = []
        attack['total_payloads'] = len(payloads)
        attack['status'] = 'running'
        
        # Run payloads
        for payload in payloads:
            if attack['status'] == 'stopped':
                break
                
            for position_type, position_value in attack['positions']:
                modified = self._inject_payload(base, position_type, position_value, payload)
                response = self._send_request(modified)
                
                result = {
                    'payload': payload,
                    'position': position_type,
                    'position_value': position_value,
                    'status_code': response.status_code,
                    'response_size': len(response.response_body) if response.response_body else 0,
                    'response_time': response.elapsed_ms,
                    'response': response,
                    'timestamp': time.time()
                }
                
                results.append(result)
                self.results[attack_id].append(result)
                
            attack['completed'] += 1
            
        attack['status'] = 'completed'
        return results
    
    def _inject_payload(self, request: HttpMessage, position_type: str, position_value: str, payload: str) -> HttpMessage:
        """Inject payload into request"""
        modified = HttpMessage(
            id=f"intruder_{int(time.time())}",
            timestamp=time.time(),
            method=request.method,
            url=request.url,
            headers=request.headers.copy(),
            body=request.body,
            source="intruder"
        )
        
        if position_type == 'url':
            modified.url = modified.url.replace(position_value, payload)
        elif position_type == 'body':
            if modified.body:
                try:
                    body_str = modified.body.decode('utf-8')
                    modified.body = body_str.replace(position_value, payload).encode()
                except:
                    pass
        elif position_type == 'header':
            # Replace header value
            for key in modified.headers:
                if modified.headers[key] == position_value:
                    modified.headers[key] = payload
        elif position_type == 'cookie':
            # Replace cookie value
            # This is simplified; in production you'd parse cookies properly
            cookie_str = modified.headers.get('Cookie', '')
            cookie_str = cookie_str.replace(position_value, payload)
            modified.headers['Cookie'] = cookie_str
            
        return modified
    
    def _send_request(self, request: HttpMessage) -> HttpMessage:
        """Send request"""
        import requests
        import urllib3
        urllib3.disable_warnings()
        
        try:
            start = time.time()
            kwargs = {
                'method': request.method,
                'url': request.url,
                'headers': request.headers,
                'verify': False,
                'allow_redirects': False,
                'timeout': 30
            }
            
            if request.body:
                kwargs['data'] = request.body
                
            response = requests.request(**kwargs)
            
            request.status_code = response.status_code
            request.response_headers = dict(response.headers)
            request.response_body = response.content
            request.elapsed_ms = (time.time() - start) * 1000
            
            return request
            
        except Exception as e:
            request.status_code = 0
            request.response_body = str(e).encode()
            return request
    
    def analyze_results(self, attack_id: str) -> Dict:
        """Analyze attack results"""
        if attack_id not in self.results:
            return {}
            
        results = self.results[attack_id]
        
        analysis = {
            'total': len(results),
            'status_codes': {},
            'unique_payloads': set(),
            'anomalies': [],
            'potential_vulnerabilities': []
        }
        
        # Analyze status codes
        for result in results:
            code = result['status_code']
            analysis['status_codes'][code] = analysis['status_codes'].get(code, 0) + 1
            analysis['unique_payloads'].add(result['payload'])
            
        # Detect anomalies
        avg_size = sum(r['response_size'] for r in results) / len(results) if results else 0
        
        for result in results:
            if abs(result['response_size'] - avg_size) > avg_size * 0.5:
                analysis['anomalies'].append({
                    'payload': result['payload'],
                    'size_diff': result['response_size'] - avg_size,
                    'status': result['status_code']
                })
                
            # Potential SQL injection (error messages)
            if result['response'] and result['response'].response_body:
                body = result['response'].response_body.decode('utf-8', errors='ignore')
                if any(term in body.lower() for term in ['sql', 'mysql', 'oracle', 'postgresql', 'syntax error']):
                    analysis['potential_vulnerabilities'].append({
                        'type': 'sql_injection',
                        'payload': result['payload'],
                        'evidence': body[:200]
                    })
                    
            # Potential XSS
            if result['payload'] in ['<script>alert(1)</script>', '"><script>alert(1)</script>']:
                if result['response'] and result['response'].response_body:
                    body = result['response'].response_body.decode('utf-8', errors='ignore')
                    if '<script>' in body or 'alert(1)' in body:
                        analysis['potential_vulnerabilities'].append({
                            'type': 'xss',
                            'payload': result['payload'],
                            'evidence': body[:200]
                        })
                        
        return analysis

# =============================================================================
# MODULE 4: SCANNER
# =============================================================================

class Scanner:
    """Automated vulnerability scanner"""
    
    def __init__(self):
        self.scan_results: Dict[str, Dict] = {}
        self.scan_counter = 0
        self.scan_tasks: queue.Queue = queue.Queue()
        self.is_running = False
        self.worker_thread: Optional[threading.Thread] = None
        
    def start_scanner(self):
        """Start the scanner worker thread"""
        if self.is_running:
            return
            
        self.is_running = True
        self.worker_thread = threading.Thread(target=self._worker, daemon=True)
        self.worker_thread.start()
        logger.info("Scanner started")
        
    def stop_scanner(self):
        """Stop the scanner"""
        self.is_running = False
        if self.worker_thread:
            self.worker_thread.join(timeout=3)
            self.worker_thread = None
            
    def scan_url(self, url: str, context: Optional[Dict] = None) -> str:
        """Queue a URL for scanning"""
        self.scan_counter += 1
        scan_id = f"scan_{self.scan_counter}"
        
        self.scan_tasks.put({
            'id': scan_id,
            'url': url,
            'context': context or {},
            'status': 'queued',
            'created': time.time()
        })
        
        return scan_id
    
    def get_result(self, scan_id: str) -> Optional[Dict]:
        """Get scan results"""
        return self.scan_results.get(scan_id)
    
    def _worker(self):
        """Worker thread for scanning"""
        import requests
        import urllib3
        urllib3.disable_warnings()
        
        while self.is_running:
            try:
                task = self.scan_tasks.get(timeout=1)
                if not task:
                    continue
                    
                task['status'] = 'running'
                results = self._run_scans(task)
                
                task['status'] = 'completed'
                task['completed_at'] = time.time()
                self.scan_results[task['id']] = {
                    'task': task,
                    'results': results
                }
                
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Scanner worker error: {e}")
                
    def _run_scans(self, task: Dict) -> Dict:
        """Run all scans on a URL"""
        url = task['url']
        results = {
            'url': url,
            'timestamp': datetime.now().isoformat(),
            'checks': []
        }
        
        # Check 1: Sensitive information in response
        try:
            response = requests.get(url, timeout=10, verify=False)
            
            # Check for sensitive info
            if response.text:
                sensitive_patterns = [
                    (r'api[_-]key\s*[:=]\s*[a-zA-Z0-9_-]+', 'API Key'),
                    (r'secret\s*[:=]\s*[a-zA-Z0-9_-]+', 'Secret'),
                    (r'token\s*[:=]\s*[a-zA-Z0-9_.-]+', 'Token'),
                    (r'password\s*[:=]\s*[a-zA-Z0-9_-]+', 'Password'),
                    (r'\\"auth\\"\s*:\s*\\"[a-zA-Z0-9_.-]+\\"', 'Auth Token'),
                    (r'eyJ[a-zA-Z0-9_-]+\\.eyJ[a-zA-Z0-9_-]+\\.[a-zA-Z0-9_-]+', 'JWT Token'),
                ]
                
                findings = []
                for pattern, name in sensitive_patterns:
                    matches = re.findall(pattern, response.text, re.IGNORECASE)
                    if matches:
                        findings.append({
                            'type': 'sensitive_info',
                            'name': name,
                            'matches': len(matches),
                            'severity': 'high',
                            'examples': matches[:3]
                        })
                        
                if findings:
                    results['checks'].append({
                        'name': 'Sensitive Information Disclosure',
                        'status': 'warning',
                        'findings': findings
                    })
                    
        except Exception as e:
            pass
            
        # Check 2: Security headers
        try:
            response = requests.get(url, timeout=10, verify=False)
            headers = response.headers
            
            security_headers = {
                'Strict-Transport-Security': 'HSTS missing',
                'Content-Security-Policy': 'CSP missing',
                'X-Content-Type-Options': 'X-Content-Type-Options missing',
                'X-Frame-Options': 'X-Frame-Options missing',
                'Referrer-Policy': 'Referrer-Policy missing',
                'X-XSS-Protection': 'X-XSS-Protection missing'
            }
            
            missing = []
            for header, desc in security_headers.items():
                if header not in headers:
                    missing.append(desc)
                    
            if missing:
                results['checks'].append({
                    'name': 'Missing Security Headers',
                    'status': 'warning',
                    'findings': missing,
                    'severity': 'medium'
                })
                
        except Exception as e:
            pass
            
        # Check 3: Directory listing
        paths = ['/admin', '/backup', '/backups', '/logs', '/tmp', '/temp', '/test', '/dev', '/old']
        
        findings = []
        for path in paths:
            try:
                test_url = urljoin(url, path)
                response = requests.get(test_url, timeout=5, verify=False)
                
                if response.status_code == 200:
                    # Check if it's a directory listing
                    body = response.text.lower()
                    if 'index of' in body or 'directory' in body and ('parent directory' in body or 'directory listing' in body):
                        findings.append({
                            'path': path,
                            'type': 'directory_listing',
                            'severity': 'high'
                        })
            except:
                pass
                
        if findings:
            results['checks'].append({
                'name': 'Directory Listing',
                'status': 'warning',
                'findings': findings
            })
            
        # Check 4: Common admin panels
        admin_paths = [
            '/admin', '/administrator', '/adminpanel', '/wp-admin', 
            '/login', '/signin', '/auth', '/console', '/dashboard'
        ]
        
        findings = []
        for path in admin_paths:
            try:
                test_url = urljoin(url, path)
                response = requests.get(test_url, timeout=5, verify=False)
                
                if response.status_code == 200:
                    # Check if it's a login/admin page
                    body = response.text.lower()
                    if any(term in body for term in ['login', 'password', 'admin', 'sign in', 'sign in']):
                        findings.append({
                            'path': path,
                            'type': 'admin_panel',
                            'severity': 'medium'
                        })
            except:
                pass
                
        if findings:
            results['checks'].append({
                'name': 'Admin Panel Discovery',
                'status': 'info',
                'findings': findings
            })
            
        # Check 5: HTTP Methods
        methods = ['OPTIONS', 'TRACE', 'PUT', 'DELETE', 'PATCH']
        findings = []
        
        for method in methods:
            try:
                response = requests.request(method, url, timeout=5, verify=False)
                if response.status_code in [200, 204, 405]:
                    findings.append({
                        'method': method,
                        'status': response.status_code,
                        'severity': 'medium' if method in ['PUT', 'DELETE', 'PATCH'] else 'low'
                    })
            except:
                pass
                
        if findings:
            results['checks'].append({
                'name': 'HTTP Method Discovery',
                'status': 'info',
                'findings': findings
            })
            
        return results

# =============================================================================
# MODULE 5: COMPARER
# =============================================================================

class Comparer:
    """Compare requests/responses like Burp Comparer"""
    
    @staticmethod
    def compare_headers(headers1: Dict, headers2: Dict) -> Dict:
        """Compare two header dictionaries"""
        all_keys = set(headers1.keys()) | set(headers2.keys())
        
        same = []
        different = []
        only_in_1 = []
        only_in_2 = []
        
        for key in all_keys:
            if key in headers1 and key in headers2:
                if headers1[key] == headers2[key]:
                    same.append(key)
                else:
                    different.append({
                        'key': key,
                        'value1': headers1[key],
                        'value2': headers2[key]
                    })
            elif key in headers1:
                only_in_1.append(key)
            else:
                only_in_2.append(key)
                
        return {
            'same': same,
            'different': different,
            'only_in_first': only_in_1,
            'only_in_second': only_in_2
        }
    
    @staticmethod
    def compare_bodies(body1: bytes, body2: bytes) -> Dict:
        """Compare two request bodies"""
        if body1 is None:
            body1 = b''
        if body2 is None:
            body2 = b''
            
        # Try to parse as JSON for better comparison
        try:
            json1 = json.loads(body1.decode('utf-8'))
            json2 = json.loads(body2.decode('utf-8'))
            
            return {
                'type': 'json',
                'comparison': Comparer._compare_json(json1, json2)
            }
        except:
            pass
            
        # Try to parse as form data
        try:
            form1 = parse_qs(body1.decode('utf-8'))
            form2 = parse_qs(body2.decode('utf-8'))
            
            return {
                'type': 'form',
                'comparison': Comparer._compare_form(form1, form2)
            }
        except:
            pass
            
        # Raw text comparison
        text1 = body1.decode('utf-8', errors='ignore')
        text2 = body2.decode('utf-8', errors='ignore')
        
        import difflib
        diff = difflib.unified_diff(
            text1.splitlines(),
            text2.splitlines(),
            lineterm=''
        )
        
        return {
            'type': 'text',
            'comparison': {
                'length1': len(body1),
                'length2': len(body2),
                'similarity': difflib.SequenceMatcher(None, text1, text2).ratio() * 100,
                'diff': '\n'.join(diff)
            }
        }
    
    @staticmethod
    def _compare_json(json1: Dict, json2: Dict) -> Dict:
        """Compare two JSON objects"""
        all_keys = set(json1.keys()) | set(json2.keys())
        
        same = []
        different = []
        only_in_1 = []
        only_in_2 = []
        
        for key in all_keys:
            if key in json1 and key in json2:
                if json1[key] == json2[key]:
                    same.append(key)
                else:
                    different.append({
                        'key': key,
                        'value1': json1[key],
                        'value2': json2[key]
                    })
            elif key in json1:
                only_in_1.append(key)
            else:
                only_in_2.append(key)
                
        return {
            'same': same,
            'different': different,
            'only_in_first': only_in_1,
            'only_in_second': only_in_2
        }
    
    @staticmethod
    def _compare_form(form1: Dict, form2: Dict) -> Dict:
        """Compare two form data dictionaries"""
        all_keys = set(form1.keys()) | set(form2.keys())
        
        same = []
        different = []
        only_in_1 = []
        only_in_2 = []
        
        for key in all_keys:
            if key in form1 and key in form2:
                if form1[key] == form2[key]:
                    same.append(key)
                else:
                    different.append({
                        'key': key,
                        'value1': form1[key],
                        'value2': form2[key]
                    })
            elif key in form1:
                only_in_1.append(key)
            else:
                only_in_2.append(key)
                
        return {
            'same': same,
            'different': different,
            'only_in_first': only_in_1,
            'only_in_second': only_in_2
        }

# =============================================================================
# MODULE 6: SEQUENCER
# =============================================================================

class Sequencer:
    """Token/session analysis like Burp Sequencer"""
    
    def __init__(self):
        self.analyses: Dict[str, Dict] = {}
        self.analysis_counter = 0
        
    def analyze_tokens(self, tokens: List[str], token_type: str = 'bearer') -> Dict:
        """Analyze tokens for randomness and patterns"""
        self.analysis_counter += 1
        analysis_id = f"seq_{self.analysis_counter}"
        
        results = {
            'id': analysis_id,
            'token_type': token_type,
            'total_tokens': len(tokens),
            'unique_tokens': len(set(tokens)),
            'analysis': {}
        }
        
        if not tokens:
            results['analysis'] = {'error': 'No tokens provided'}
            return results
            
        # Length analysis
        lengths = [len(t) for t in tokens]
        results['analysis']['length'] = {
            'min': min(lengths),
            'max': max(lengths),
            'avg': sum(lengths) / len(lengths),
            'std_dev': self._std_dev(lengths)
        }
        
        # Character distribution
        char_counts = {}
        for token in tokens:
            for char in token:
                char_counts[char] = char_counts.get(char, 0) + 1
                
        results['analysis']['characters'] = {
            'total_chars': sum(char_counts.values()),
            'unique_chars': len(char_counts),
            'distribution': char_counts
        }
        
        # Entropy calculation
        results['analysis']['entropy'] = self._calculate_entropy(tokens)
        
        # Pattern detection
        results['analysis']['patterns'] = self._detect_patterns(tokens)
        
        # JWT specific analysis
        if token_type == 'jwt' or any(len(t.split('.')) == 3 for t in tokens):
            results['analysis']['jwt'] = self._analyze_jwt(tokens)
            
        self.analyses[analysis_id] = results
        return results
    
    def _std_dev(self, values: List[float]) -> float:
        """Calculate standard deviation"""
        if len(values) < 2:
            return 0
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / (len(values) - 1)
        return variance ** 0.5
    
    def _calculate_entropy(self, tokens: List[str]) -> float:
        """Calculate entropy of tokens"""
        if not tokens:
            return 0
            
        # Combine all tokens
        combined = ''.join(tokens)
        char_counts = {}
        for char in combined:
            char_counts[char] = char_counts.get(char, 0) + 1
            
        total = len(combined)
        entropy = 0
        for count in char_counts.values():
            if count > 0:
                p = count / total
                entropy -= p * (p ** 0.5 if p > 0 else 0)  # Simplified entropy
                
        return entropy
    
    def _detect_patterns(self, tokens: List[str]) -> List[Dict]:
        """Detect patterns in tokens"""
        patterns = []
        
        # Check for timestamp patterns
        for token in tokens[:10]:  # Sample first 10
            if 'exp' in token or 'iat' in token:
                patterns.append({
                    'type': 'timestamp',
                    'description': 'Contains timestamp fields',
                    'confidence': 'high'
                })
                break
                
        # Check for base64 patterns
        import base64
        for token in tokens[:10]:
            try:
                decoded = base64.b64decode(token + '==')
                if decoded:
                    patterns.append({
                        'type': 'base64',
                        'description': 'Appears to be base64 encoded',
                        'confidence': 'high'
                    })
                    break
            except:
                pass
                
        # Check for hex patterns
        if all(c in '0123456789abcdefABCDEF' for c in tokens[0] if c.isdigit() or c.isalpha()):
            patterns.append({
                'type': 'hexadecimal',
                'description': 'Looks like hexadecimal encoding',
                'confidence': 'medium'
            })
            
        return patterns
    
    def _analyze_jwt(self, tokens: List[str]) -> Dict:
        """Analyze JWT tokens"""
        jwt_analysis = {
            'algorithms': set(),
            'claims': set(),
            'issues': []
        }
        
        for token in tokens:
            try:
                parts = token.split('.')
                if len(parts) == 3:
                    # Decode header
                    header = json.loads(base64.b64decode(parts[0] + '==').decode('utf-8'))
                    jwt_analysis['algorithms'].add(header.get('alg', 'unknown'))
                    
                    # Decode payload
                    payload = json.loads(base64.b64decode(parts[1] + '==').decode('utf-8'))
                    for key in payload.keys():
                        jwt_analysis['claims'].add(key)
                        
                    # Check for issues
                    if payload.get('exp') and payload.get('exp') < time.time():
                        jwt_analysis['issues'].append('Expired token')
                    if header.get('alg') == 'none':
                        jwt_analysis['issues'].append('Algorithm "none" is insecure')
                    if header.get('alg') == 'HS256' and len(parts[2]) < 32:
                        jwt_analysis['issues'].append('Short secret key (weak)')
                        
            except:
                pass
                
        jwt_analysis['algorithms'] = list(jwt_analysis['algorithms'])
        jwt_analysis['claims'] = list(jwt_analysis['claims'])
        
        return jwt_analysis

# =============================================================================
# MODULE 7: EXTENDER
# =============================================================================

class Extender:
    """Plugin system like Burp Extender"""
    
    def __init__(self):
        self.plugins: Dict[str, Dict] = {}
        self.plugin_counter = 0
        self.hooks = {
            'before_request': [],
            'after_response': [],
            'on_finding': [],
            'on_scan_complete': []
        }
        
    def register_plugin(self, name: str, plugin_code: str, hooks: List[str]) -> str:
        """Register a new plugin"""
        self.plugin_counter += 1
        plugin_id = f"plugin_{self.plugin_counter}"
        
        # Compile plugin
        try:
            # Create namespace
            namespace = {}
            exec(plugin_code, namespace)
            
            # Check for plugin class
            if 'Plugin' not in namespace:
                return "Error: Plugin class not found"
                
            plugin_class = namespace['Plugin']
            plugin_instance = plugin_class()
            
            self.plugins[plugin_id] = {
                'id': plugin_id,
                'name': name,
                'instance': plugin_instance,
                'hooks': hooks,
                'enabled': True,
                'registered': datetime.now().isoformat()
            }
            
            # Register hooks
            for hook in hooks:
                if hook in self.hooks:
                    self.hooks[hook].append(plugin_id)
                    
            return plugin_id
            
        except Exception as e:
            return f"Error loading plugin: {e}"
    
    def run_hook(self, hook_name: str, *args, **kwargs):
        """Run all plugins registered for a hook"""
        if hook_name not in self.hooks:
            return
            
        for plugin_id in self.hooks[hook_name]:
            if plugin_id in self.plugins:
                plugin = self.plugins[plugin_id]
                if plugin['enabled']:
                    try:
                        plugin['instance'].handle_hook(hook_name, *args, **kwargs)
                    except Exception as e:
                        logger.error(f"Plugin {plugin_id} error in {hook_name}: {e}")

# =============================================================================
# MAIN APPLICATION - HarSuite
# =============================================================================

class HarSuite:
    """Main application orchestrating all modules"""
    
    def __init__(self):
        # Core modules
        self.proxy = InterceptingProxy()
        self.repeater = Repeater()
        self.intruder = Intruder()
        self.scanner = Scanner()
        self.comparer = Comparer()
        self.sequencer = Sequencer()
        self.extender = Extender()
        
        # HAR capture
        self.capture = None
        self.capture_config = CaptureConfig()
        
        # Session data
        self.session_history: List[HttpMessage] = []
        self.current_session = {
            'id': f"session_{int(time.time())}",
            'started': datetime.now().isoformat(),
            'requests': [],
            'findings': []
        }
        
        # State
        self.is_running = False
        self.targets: List[str] = []
        self.scope: Dict[str, List[str]] = {
            'include': [],
            'exclude': []
        }
        
    def start(self):
        """Start the HarSuite"""
        self.is_running = True
        self.scanner.start_scanner()
        
        logger.info("""
╔══════════════════════════════════════════════════════════════╗
║                  🛡️ HAR SUITE v1.0                         ║
║         Complete Web Security Testing Platform              ║
║                                                             ║
║   Modules:                                                  ║
║   • Proxy   - HTTP/HTTPS intercepting proxy                ║
║   • Repeater - Manual request replay                       ║
║   • Intruder - Automated fuzzing                           ║
║   • Scanner  - Vulnerability scanning                      ║
║   • Decoder  - Encoding/decoding tools                    ║
║   • Comparer - Request/response comparison                 ║
║   • Sequencer - Token/session analysis                     ║
║   • Extender - Plugin system                               ║
╚══════════════════════════════════════════════════════════════╝
        """)
        
    def stop(self):
        """Stop the HarSuite"""
        self.is_running = False
        self.proxy.stop()
        self.scanner.stop_scanner()
        
    def capture_from_browser(self, duration: int = 60, port: int = 9258) -> bool:
        """Capture traffic from Chrome browser"""
        try:
            self.capture = JourneyHARCapture(self.capture_config)
            
            # Get tabs
            tabs = self.capture.get_page_tabs()
            if not tabs:
                logger.error("No Chrome tabs found")
                return False
                
            # Select all tabs with WebSocket
            tab_ids = [tid for tid, info in tabs.items() if info.ws_url]
            
            if not tab_ids:
                logger.error("No tabs with WebSocket URL found")
                return False
                
            logger.info(f"Capturing {len(tab_ids)} tabs for {duration} seconds")
            
            # Start capture
            self.capture.capture_journey(tab_ids)
            result = self.capture.save_har()
            
            if result:
                logger.info(f"✅ HAR file saved: {result}")
                
                # Import HAR entries into session
                har_data = self.capture.build_har_data()
                for entry in har_data['log']['entries']:
                    self._import_har_entry(entry)
                    
                return True
            else:
                return False
                
        except Exception as e:
            logger.error(f"Capture failed: {e}")
            return False
            
    def _import_har_entry(self, entry: Dict):
        """Import a HAR entry into the session"""
        request = entry.get('request', {})
        response = entry.get('response', {})
        
        msg = HttpMessage(
            id=f"import_{int(time.time())}_{len(self.session_history)}",
            timestamp=time.time(),
            method=request.get('method', 'GET'),
            url=request.get('url', ''),
            headers={h['name']: h['value'] for h in request.get('headers', [])},
            body=request.get('postData', {}).get('text', '').encode() if 'postData' in request else None,
            status_code=response.get('status'),
            response_headers={h['name']: h['value'] for h in response.get('headers', [])},
            response_body=response.get('content', {}).get('text', '').encode(),
            source='har_import'
        )
        
        self.session_history.append(msg)
        self.current_session['requests'].append(msg)
        
    def export_session(self, filename: str):
        """Export session data"""
        data = {
            'session': self.current_session,
            'requests': [msg.__dict__ for msg in self.session_history],
            'targets': self.targets,
            'scope': self.scope,
            'exported_at': datetime.now().isoformat()
        }
        
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2, default=str)
            
        logger.info(f"Session exported to {filename}")

# =============================================================================
# CLI INTERFACE
# =============================================================================

class HarSuiteCLI:
    """Command-line interface for HarSuite"""
    
    def __init__(self):
        self.suite = HarSuite()
        self.commands = {
            'help': self.cmd_help,
            'start': self.cmd_start,
            'stop': self.cmd_stop,
            'capture': self.cmd_capture,
            'proxy': self.cmd_proxy,
            'repeat': self.cmd_repeat,
            'intruder': self.cmd_intruder,
            'scan': self.cmd_scan,
            'compare': self.cmd_compare,
            'decode': self.cmd_decode,
            'history': self.cmd_history,
            'export': self.cmd_export,
            'target': self.cmd_target,
            'scope': self.cmd_scope,
            'clear': self.cmd_clear,
            'exit': self.cmd_exit
        }
        
    def run(self):
        """Main CLI loop"""
        print("""
╔══════════════════════════════════════════════════════════════╗
║                  🛡️ HAR SUITE CLI                         ║
║         Web Security Testing Platform                       ║
║                                                             ║
║  Type 'help' for commands                                   ║
╚══════════════════════════════════════════════════════════════╝
        """)
        
        while True:
            try:
                cmd_input = input("\nHarSuite> ").strip()
                if not cmd_input:
                    continue
                    
                parts = cmd_input.split()
                cmd = parts[0].lower()
                args = parts[1:]
                
                if cmd in self.commands:
                    self.commands[cmd](args)
                else:
                    print(f"Unknown command: {cmd}")
                    print("Type 'help' for available commands")
                    
            except KeyboardInterrupt:
                print("\n")
                self.cmd_exit([])
                break
            except Exception as e:
                print(f"Error: {e}")
                traceback.print_exc()
                
    def cmd_help(self, args):
        """Show help"""
        print("""
📚 Available Commands:

  start                    - Start HarSuite
  stop                     - Stop HarSuite
  capture [duration] [port] - Capture from Chrome browser
  proxy [start|stop|status] - Control intercepting proxy
  repeat <id> [mods]       - Send request to Repeater
  intruder <id> [options]  - Run Intruder on request
  scan <url|id>            - Run scanner on target
  compare <id1> <id2>      - Compare two requests
  decode <type> <data>     - Decode data
  history [n]              - Show request history
  export <file.har>        - Export session as HAR
  target [add|remove] <url> - Manage targets
  scope [add|remove] <url>  - Manage scope
  clear                    - Clear session data
  exit                     - Exit the tool

Examples:
  capture 30 9258         - Capture for 30 seconds on port 9258
  repeat 1 --method POST   - Replay request #1 as POST
  intruder 1 --type sql_injection
  scan https://example.com
  decode base64 SGVsbG8=
  compare 1 2
""")
    
    def cmd_start(self, args):
        """Start HarSuite"""
        self.suite.start()
        print("✅ HarSuite started")
        
    def cmd_stop(self, args):
        """Stop HarSuite"""
        self.suite.stop()
        print("✅ HarSuite stopped")
        
    def cmd_capture(self, args):
        """Capture from Chrome"""
        duration = int(args[0]) if args else 60
        port = int(args[1]) if len(args) > 1 else 9258
        
        print(f"📡 Capturing from Chrome on port {port} for {duration} seconds...")
        print("   Interact with the browser normally")
        print("   Press Ctrl+C to stop early")
        
        try:
            success = self.suite.capture_from_browser(duration, port)
            if success:
                print("✅ Capture complete!")
                print(f"   Total requests: {len(self.suite.session_history)}")
            else:
                print("❌ Capture failed")
        except KeyboardInterrupt:
            print("\n⏹️ Capture interrupted")
            
    def cmd_proxy(self, args):
        """Control proxy"""
        if not args:
            print("Usage: proxy [start|stop|status]")
            return
            
        action = args[0]
        if action == 'start':
            port = int(args[1]) if len(args) > 1 else 8080
            self.suite.proxy.port = port
            if self.suite.proxy.start():
                print(f"🚀 Proxy started on port {port}")
                print("   Configure your browser to use 127.0.0.1:8080 as proxy")
                print("   Install mitmproxy certificate: http://mitm.it")
            else:
                print("❌ Failed to start proxy")
        elif action == 'stop':
            self.suite.proxy.stop()
            print("🛑 Proxy stopped")
        elif action == 'status':
            status = "running" if self.suite.proxy.is_running else "stopped"
            print(f"📡 Proxy status: {status}")
        else:
            print(f"Unknown action: {action}")
            
    def cmd_repeat(self, args):
        """Send request to Repeater"""
        if not args:
            print("Usage: repeat <request_id> [--method <method>] [--body <body>] [--header <key:value>]")
            return
            
        req_id = args[0]
        
        # Find request
        try:
            idx = int(req_id) - 1
            if idx < 0 or idx >= len(self.suite.session_history):
                print(f"❌ Request {req_id} not found")
                return
            request = self.suite.session_history[idx]
        except ValueError:
            print(f"❌ Invalid request ID: {req_id}")
            return
            
        # Parse modifications
        modifications = {}
        i = 1
        while i < len(args):
            if args[i] == '--method' and i + 1 < len(args):
                modifications['method'] = args[i + 1]
                i += 2
            elif args[i] == '--body' and i + 1 < len(args):
                modifications['body'] = args[i + 1]
                i += 2
            elif args[i] == '--header' and i + 1 < len(args):
                key, value = args[i + 1].split(':', 1)
                modifications.setdefault('headers', {})[key.strip()] = value.strip()
                i += 2
            else:
                i += 1
                
        print(f"🔄 Repeating request to: {request.url}")
        response = self.suite.repeater.modify_and_send(request, modifications)
        
        print(f"✅ Response: {response.status_code}")
        print(f"   Headers: {len(response.response_headers or {})}")
        print(f"   Body size: {len(response.response_body or b'')}")
        
    def cmd_intruder(self, args):
        """Run Intruder"""
        if not args:
            print("Usage: intruder <request_id> [--type <type>] [--positions <pos1,pos2>]")
            print("  Types: common, sql_injection, xss, path_traversal, ssrf, command_injection")
            return
            
        req_id = args[0]
        
        # Find request
        try:
            idx = int(req_id) - 1
            if idx < 0 or idx >= len(self.suite.session_history):
                print(f"❌ Request {req_id} not found")
                return
            request = self.suite.session_history[idx]
        except ValueError:
            print(f"❌ Invalid request ID: {req_id}")
            return
            
        # Parse options
        attack_type = 'common'
        positions = [('body', '')]  # Default position
        
        i = 1
        while i < len(args):
            if args[i] == '--type' and i + 1 < len(args):
                attack_type = args[i + 1]
                i += 2
            elif args[i] == '--positions' and i + 1 < len(args):
                positions = []
                for pos in args[i + 1].split(','):
                    if ':' in pos:
                        pos_type, pos_value = pos.split(':', 1)
                        positions.append((pos_type, pos_value))
                    else:
                        positions.append((pos, ''))
                i += 2
            else:
                i += 1
                
        # Get payloads
        payloads = self.suite.intruder.payload_sets.get(attack_type, [])
        if not payloads:
            print(f"❌ Unknown attack type: {attack_type}")
            return
            
        print(f"🔨 Running Intruder ({attack_type}) with {len(payloads)} payloads")
        print(f"   Positions: {positions}")
        
        attack_id = self.suite.intruder.create_attack(request, attack_type, positions)
        results = self.suite.intruder.run_attack(attack_id, payloads)
        
        analysis = self.suite.intruder.analyze_results(attack_id)
        
        print(f"✅ Completed: {len(results)} requests")
        print(f"   Status codes: {analysis['status_codes']}")
        print(f"   Anomalies: {len(analysis['anomalies'])}")
        print(f"   Potential vulnerabilities: {len(analysis['potential_vulnerabilities'])}")
        
        if analysis['potential_vulnerabilities']:
            print("\n   ⚠️ Potential Vulnerabilities:")
            for vuln in analysis['potential_vulnerabilities']:
                print(f"     - {vuln['type']}: {vuln['payload']}")
                
    def cmd_scan(self, args):
        """Run scanner"""
        if not args:
            print("Usage: scan <url|request_id>")
            return
            
        target = args[0]
        
        # Check if it's a URL or request ID
        if target.startswith('http'):
            print(f"🔍 Scanning URL: {target}")
            scan_id = self.suite.scanner.scan_url(target)
        else:
            try:
                idx = int(target) - 1
                if idx < 0 or idx >= len(self.suite.session_history):
                    print(f"❌ Request {target} not found")
                    return
                request = self.suite.session_history[idx]
                print(f"🔍 Scanning request: {request.url}")
                scan_id = self.suite.scanner.scan_url(request.url, {'request': request})
            except ValueError:
                print(f"❌ Invalid target: {target}")
                return
                
        print(f"📋 Scan started: {scan_id}")
        print("   Results will be available when scan completes")
        
        # Wait for results
        import time
        time.sleep(2)  # Give scanner time to start
        
        # Check for results
        result = self.suite.scanner.get_result(scan_id)
        if result:
            self._display_scan_results(result)
        else:
            print("   (Scan in progress. Use history to check later)")
            
    def _display_scan_results(self, result: Dict):
        """Display scan results"""
        print("\n📊 Scan Results:")
        print(f"   URL: {result['task']['url']}")
        print(f"   Status: {result['task']['status']}")
        
        findings = result.get('results', {}).get('checks', [])
        if not findings:
            print("   ✅ No issues found")
            return
            
        for check in findings:
            status = check.get('status', 'info')
            emoji = "⚠️" if status == 'warning' else "ℹ️"
            print(f"\n   {emoji} {check['name']}")
            
            if 'findings' in check:
                for finding in check['findings']:
                    if isinstance(finding, str):
                        print(f"      - {finding}")
                    else:
                        print(f"      - {finding}")
                        
    def cmd_compare(self, args):
        """Compare two requests"""
        if len(args) < 2:
            print("Usage: compare <id1> <id2>")
            return
            
        try:
            idx1 = int(args[0]) - 1
            idx2 = int(args[1]) - 1
            
            if idx1 >= len(self.suite.session_history) or idx2 >= len(self.suite.session_history):
                print("❌ Request ID out of range")
                return
                
            req1 = self.suite.session_history[idx1]
            req2 = self.suite.session_history[idx2]
            
            print(f"📊 Comparing request {args[0]} and {args[1]}")
            print("   Headers:")
            
            header_diff = self.suite.comparer.compare_headers(req1.headers, req2.headers)
            if header_diff['same']:
                print(f"     Same: {len(header_diff['same'])} headers")
            if header_diff['different']:
                print(f"     Different: {len(header_diff['different'])} headers")
            if header_diff['only_in_first']:
                print(f"     Only in first: {header_diff['only_in_first']}")
            if header_diff['only_in_second']:
                print(f"     Only in second: {header_diff['only_in_second']}")
                
            body_diff = self.suite.comparer.compare_bodies(req1.body or b'', req2.body or b'')
            print(f"\n   Body: {body_diff['type']}")
            print(f"     Similarity: {body_diff['comparison'].get('similarity', 0):.1f}%")
            
        except ValueError:
            print("❌ Invalid request IDs")
            
    def cmd_decode(self, args):
        """Decode data"""
        if len(args) < 2:
            print("Usage: decode <type> <data>")
            print("Types: base64, url, html, hex, unicode, md5, sha1, sha256")
            return
            
        decode_type = args[0]
        data = ' '.join(args[1:])
        
        decoder = Decoder  # Use static methods from Decoder class
        
        operations = {
            'base64': decoder.base64_decode,
            'base64-encode': decoder.base64_encode,
            'url': decoder.url_decode,
            'url-encode': decoder.url_encode,
            'html': decoder.html_decode,
            'html-encode': decoder.html_encode,
            'hex': decoder.hex_decode,
            'hex-encode': decoder.hex_encode,
            'unicode': decoder.unicode_decode,
            'unicode-encode': decoder.unicode_encode,
            'md5': decoder.hash_md5,
            'sha1': decoder.hash_sha1,
            'sha256': decoder.hash_sha256
        }
        
        if decode_type not in operations:
            print(f"❌ Unknown decode type: {decode_type}")
            return
            
        try:
            result = operations[decode_type](data)
            print(f"🔓 Decoded ({decode_type}):")
            print("=" * 60)
            print(result)
            print("=" * 60)
        except Exception as e:
            print(f"❌ Decode error: {e}")
            
    def cmd_history(self, args):
        """Show request history"""
        n = int(args[0]) if args and args[0].isdigit() else 10
        history = self.suite.session_history[-n:]
        
        print(f"\n📋 Last {len(history)} requests:")
        print("  ID    Method  Status  Source    URL")
        print("  " + "-" * 70)
        
        start_idx = len(self.suite.session_history) - len(history)
        for i, req in enumerate(history, start_idx + 1):
            status = req.status_code or 0
            status_emoji = "✅" if 200 <= status < 300 else "⚠️" if 300 <= status < 400 else "❌"
            url = req.url[:50] + "..." if len(req.url) > 50 else req.url
            print(f"  {i:3}   {req.method:6}  {status_emoji}{status:3}   {req.source:8}   {url}")
            
    def cmd_export(self, args):
        """Export session"""
        if not args:
            print("Usage: export <filename>")
            return
            
        filename = args[0]
        if not filename.endswith('.har'):
            filename += '.har'
            
        self.suite.export_session(filename)
        print(f"💾 Session exported to: {filename}")
        
    def cmd_target(self, args):
        """Manage targets"""
        if not args:
            print(f"Current targets: {self.suite.targets}")
            return
            
        action = args[0]
        if action == 'add' and len(args) > 1:
            url = args[1]
            if url not in self.suite.targets:
                self.suite.targets.append(url)
                print(f"✅ Added target: {url}")
            else:
                print(f"ℹ️ Target already exists: {url}")
        elif action == 'remove' and len(args) > 1:
            url = args[1]
            if url in self.suite.targets:
                self.suite.targets.remove(url)
                print(f"✅ Removed target: {url}")
            else:
                print(f"❌ Target not found: {url}")
        else:
            print(f"Usage: target [add|remove] <url>")
            
    def cmd_scope(self, args):
        """Manage scope"""
        if not args:
            print("Scope:")
            print(f"  Include: {self.suite.scope['include']}")
            print(f"  Exclude: {self.suite.scope['exclude']}")
            return
            
        action = args[0]
        if action == 'add' and len(args) > 1:
            url = args[1]
            if url not in self.suite.scope['include']:
                self.suite.scope['include'].append(url)
                print(f"✅ Added to scope: {url}")
            else:
                print(f"ℹ️ Already in scope: {url}")
        elif action == 'remove' and len(args) > 1:
            url = args[1]
            if url in self.suite.scope['include']:
                self.suite.scope['include'].remove(url)
                print(f"✅ Removed from scope: {url}")
            else:
                print(f"❌ Not in scope: {url}")
        elif action == 'exclude' and len(args) > 1:
            url = args[1]
            if url not in self.suite.scope['exclude']:
                self.suite.scope['exclude'].append(url)
                print(f"✅ Excluded: {url}")
        else:
            print(f"Unknown action: {action}")
            
    def cmd_clear(self, args):
        """Clear session data"""
        confirm = input("⚠️ Clear all session data? (y/n): ")
        if confirm.lower() == 'y':
            self.suite.session_history = []
            self.suite.targets = []
            self.suite.scope = {'include': [], 'exclude': []}
            self.suite.current_session = {
                'id': f"session_{int(time.time())}",
                'started': datetime.now().isoformat(),
                'requests': [],
                'findings': []
            }
            print("✅ Session cleared")
            
    def cmd_exit(self, args):
        """Exit the tool"""
        print("👋 Goodbye!")
        sys.exit(0)

# =============================================================================
# ENTRY POINT
# =============================================================================

def main():
    """Main entry point"""
    cli = HarSuiteCLI()
    cli.run()

if __name__ == "__main__":
    main()
