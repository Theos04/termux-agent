#!/usr/bin/env python3
"""
HarSuite Integration - Connect to existing Chrome sessions
"""

import json
import time
import requests
import subprocess
import sys
import os
from typing import Dict, List, Optional, Any
from pathlib import Path

# Import HarSuite
from harsuite import HarSuite, HarSuiteCLI, logger

class HarSuiteSessionManager:
    """Integration with your session manager"""
    
    def __init__(self, base_dir: str = None):
        self.base_dir = Path(base_dir) if base_dir else Path.home() / "chrome-sessions"
        self.sessions_file = self.base_dir / "sessions.json"
        self.active_sessions: Dict[str, Dict] = {}
        self.load_sessions()
        
    def load_sessions(self):
        """Load active sessions from sessions file"""
        if self.sessions_file.exists():
            try:
                with open(self.sessions_file) as f:
                    self.active_sessions = json.load(f)
                logger.info(f"Loaded {len(self.active_sessions)} active sessions")
            except:
                self.active_sessions = {}
                
    def save_sessions(self):
        """Save sessions to file"""
        with open(self.sessions_file, 'w') as f:
            json.dump(self.active_sessions, f, indent=2)
            
    def get_session_by_port(self, port: int) -> Optional[Dict]:
        """Get session by port number"""
        for session_id, session_data in self.active_sessions.items():
            if session_data.get('port') == port:
                return session_data
        return None
        
    def get_session_by_id(self, session_id: str) -> Optional[Dict]:
        """Get session by ID"""
        return self.active_sessions.get(session_id)
        
    def list_sessions(self) -> List[Dict]:
        """List all active sessions"""
        sessions = []
        for sid, data in self.active_sessions.items():
            sessions.append({
                'id': sid,
                'name': data.get('name', 'Unknown'),
                'port': data.get('port'),
                'pid': data.get('pid'),
                'url': data.get('url', ''),
                'ws_id': data.get('ws_id', ''),
                'vnc_port': data.get('vnc_port', 5900),
                'started': data.get('started', '')
            })
        return sessions
        
    def connect_to_session(self, session_id: str, harsuite: HarSuite) -> bool:
        """Connect HarSuite to an existing session"""
        session = self.get_session_by_id(session_id)
        if not session:
            logger.error(f"Session {session_id} not found")
            return False
            
        port = session.get('port')
        if not port:
            logger.error(f"Session {session_id} has no port")
            return False
            
        ws_id = session.get('ws_id')
        if not ws_id:
            logger.error(f"Session {session_id} has no WebSocket ID")
            return False
            
        # Check if Chrome is running
        try:
            response = requests.get(f"http://127.0.0.1:{port}/json", timeout=2)
            if response.status_code != 200:
                logger.error(f"Chrome not responding on port {port}")
                return False
                
            tabs = response.json()
            # Find the tab with matching WS ID
            for tab in tabs:
                if tab.get('id') == ws_id:
                    # Connection successful
                    harsuite.capture_config.port = port
                    logger.info(f"✅ Connected to session {session_id} on port {port}")
                    return True
                    
        except Exception as e:
            logger.error(f"Failed to connect to Chrome: {e}")
            return False
            
        return False

class HarSuiteIntegrationCLI:
    """Extended CLI with session management"""
    
    def __init__(self):
        self.suite = HarSuite()
        self.session_manager = HarSuiteSessionManager()
        self.current_session_id = None
        self.commands = {
            'help': self.cmd_help,
            'start': self.cmd_start,
            'stop': self.cmd_stop,
            'sessions': self.cmd_sessions,
            'connect': self.cmd_connect,
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
║              🛡️ HAR SUITE - Session Manager               ║
║         Integrated with Chrome Session Manager              ║
║                                                             ║
║  Type 'help' for commands                                   ║
╚══════════════════════════════════════════════════════════════╝
        """)
        
        # Auto-load sessions
        sessions = self.session_manager.list_sessions()
        if sessions:
            print(f"\n📋 Found {len(sessions)} active sessions:")
            for s in sessions:
                print(f"  [{s['id']}] {s['name']} (port {s['port']}) - {s.get('url', '')[:50]}")
            print("\n  Use 'connect <id>' to connect to a session")
            print("  Use 'capture <port>' to capture from a specific port\n")
        
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
                import traceback
                traceback.print_exc()
    
    def cmd_help(self, args):
        """Show help"""
        print("""
📚 Available Commands:

  sessions                 - List active Chrome sessions
  connect <id>            - Connect to a Chrome session
  capture [duration] [port] - Capture from current session
  proxy [start|stop|status] - Control intercepting proxy
  repeat <id> [mods]      - Send request to Repeater
  intruder <id> [options] - Run Intruder on request
  scan <url|id>           - Run scanner on target
  compare <id1> <id2>     - Compare two requests
  decode <type> <data>    - Decode data
  history [n]             - Show request history
  export <file.har>       - Export session as HAR
  target [add|remove] <url> - Manage targets
  scope [add|remove] <url>  - Manage scope
  clear                   - Clear session data
  exit                    - Exit the tool

Examples:
  sessions                - List active Chrome sessions
  connect 30              - Connect to session 30
  capture 60              - Capture from current session
  repeat 1 --method POST  - Replay request #1 as POST
  intruder 1 --type sql_injection
  scan https://example.com
  decode base64 SGVsbG8=
  compare 1 2
""")
    
    def cmd_sessions(self, args):
        """List active sessions"""
        sessions = self.session_manager.list_sessions()
        
        if not sessions:
            print("❌ No active sessions found")
            return
            
        print("\n📋 Active Chrome Sessions:")
        print("  ID    Name                    Port    VNC     Status     URL")
        print("  " + "-" * 80)
        
        for s in sessions:
            status = "✅" if self.session_manager.connect_to_session(s['id'], self.suite) else "❌"
            vnc = f"590{s['port'] % 10}" if s.get('vnc_port') else "N/A"
            name = s['name'][:20] + "..." if len(s['name']) > 20 else s['name']
            url = s.get('url', '')[:40] + "..." if len(s.get('url', '')) > 40 else s.get('url', '')
            print(f"  {s['id']:3}   {name:20}  {s['port']:4}   {vnc:5}   {status}    {url}")
            
    def cmd_connect(self, args):
        """Connect to a Chrome session"""
        if not args:
            print("Usage: connect <session_id>")
            return
            
        session_id = args[0]
        
        # Check if session exists
        session = self.session_manager.get_session_by_id(session_id)
        if not session:
            print(f"❌ Session {session_id} not found")
            print("Use 'sessions' to list available sessions")
            return
            
        # Connect
        if self.session_manager.connect_to_session(session_id, self.suite):
            self.current_session_id = session_id
            print(f"✅ Connected to session: {session.get('name', session_id)}")
            print(f"   Port: {session.get('port')}")
            print(f"   URL: {session.get('url', '')}")
            print("\n📡 Ready to capture traffic!")
            print("   Use 'capture <duration>' to start capturing")
        else:
            print("❌ Failed to connect")
            
    def cmd_capture(self, args):
        """Capture from Chrome"""
        # Determine port to use
        port = None
        duration = 60
        
        if args:
            try:
                duration = int(args[0])
                if len(args) > 1:
                    port = int(args[1])
            except ValueError:
                # Check if it's a session ID
                session = self.session_manager.get_session_by_id(args[0])
                if session:
                    port = session.get('port')
                else:
                    try:
                        port = int(args[0])
                    except:
                        print(f"❌ Invalid argument: {args[0]}")
                        return
                        
        # If no port specified, try current session or auto-detect
        if not port:
            if self.current_session_id:
                session = self.session_manager.get_session_by_id(self.current_session_id)
                if session:
                    port = session.get('port')
                    
        if not port:
            # Auto-detect from sessions
            sessions = self.session_manager.list_sessions()
            if sessions:
                print("📋 Available sessions:")
                for s in sessions:
                    print(f"  [{s['id']}] {s['name']} (port {s['port']})")
                choice = input("Select session ID: ").strip()
                session = self.session_manager.get_session_by_id(choice)
                if session:
                    port = session.get('port')
                    self.current_session_id = choice
                    
        if not port:
            print("❌ No session selected. Use 'sessions' to list available sessions")
            return
            
        print(f"📡 Capturing from Chrome on port {port} for {duration} seconds...")
        print("   Interact with the browser normally")
        print("   Press Ctrl+C to stop early")
        
        # Update config
        self.suite.capture_config.port = port
        self.suite.capture_config.duration = duration
        
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
        positions = [('body', '')]
        
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
        time.sleep(2)
        
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
        
        from harsuite import Decoder
        
        operations = {
            'base64': Decoder.base64_decode,
            'base64-encode': Decoder.base64_encode,
            'url': Decoder.url_decode,
            'url-encode': Decoder.url_encode,
            'html': Decoder.html_decode,
            'html-encode': Decoder.html_encode,
            'hex': Decoder.hex_decode,
            'hex-encode': Decoder.hex_encode,
            'unicode': Decoder.unicode_decode,
            'unicode-encode': Decoder.unicode_encode,
            'md5': Decoder.hash_md5,
            'sha1': Decoder.hash_sha1,
            'sha256': Decoder.hash_sha256
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
            
    def cmd_start(self, args):
        """Start HarSuite"""
        self.suite.start()
        print("✅ HarSuite started")
        
    def cmd_stop(self, args):
        """Stop HarSuite"""
        self.suite.stop()
        print("✅ HarSuite stopped")
        
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


def main():
    """Main entry point"""
    cli = HarSuiteIntegrationCLI()
    cli.run()


if __name__ == "__main__":
    main()
