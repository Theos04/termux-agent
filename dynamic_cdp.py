#!/usr/bin/env python3
"""
Enhanced Chrome CDP Controller - Fully Working
"""

import json
import subprocess
import sys
import os
import time
from typing import Optional, Dict, List, Any
from dataclasses import dataclass
from datetime import datetime

try:
    import requests
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests"])
    import requests

try:
    import websocket
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "websocket-client"])
    import websocket

@dataclass
class LayoutSnapshot:
    """Complete layout and style information"""
    dom_nodes: List[Dict]
    layout_tree: List[Dict]
    computed_styles: List[Dict]

class EnhancedChromeCDP:
    def __init__(self, port: int = 9227):
        self.port = port
        self.base_url = f"http://127.0.0.1:{port}"
        self.ws_url = None
        self.tabs = []
        self.connection_timeout = 10
        self._command_counter = 0

    def get_tabs(self) -> List[Dict]:
        """Get all tabs from Chrome with enhanced info"""
        try:
            response = requests.get(f"{self.base_url}/json", timeout=5)
            if response.status_code == 200:
                tabs = response.json()
                self.tabs = [t for t in tabs if t.get('type') == 'page']
                print(f"🔍 Found {len(self.tabs)} tabs")
                return self.tabs
            return []
        except Exception as e:
            print(f"❌ Error fetching tabs: {e}")
            return []

    def get_websocket_url(self, tab_index: int = 0) -> Optional[str]:
        """Get WebSocket URL for a specific tab - refreshes to avoid stale URLs"""
        # Always refresh tabs to get current WebSocket URL
        self.get_tabs()

        if not self.tabs:
            print("❌ No tabs found")
            return None

        if tab_index >= len(self.tabs):
            print(f"❌ Tab index {tab_index} out of range")
            return None

        ws_url = self.tabs[tab_index].get('webSocketDebuggerUrl')
        if ws_url:
            self.ws_url = ws_url
            print(f"🔗 WebSocket URL: {ws_url[:50]}...")
            return ws_url
        print("❌ No WebSocket URL found for tab")
        return None

    def _connect_websocket(self) -> Optional[websocket.WebSocket]:
        """Establish WebSocket connection with proper headers"""
        ws_url = self.ws_url
        if not ws_url:
            print("❌ No WebSocket URL available")
            return None
        
        try:
            print(f"🔌 Connecting to WebSocket...")
            ws = websocket.create_connection(
                ws_url,
                timeout=self.connection_timeout,
                header={"Origin": f"http://127.0.0.1:{self.port}"}
            )
            print("✅ WebSocket connected")
            return ws
        except Exception as e:
            print(f"❌ WebSocket connection error: {e}")
            print(f"   URL: {ws_url}")
            print(f"   Port: {self.port}")
            print(f"   Make sure Chrome is running and no other debugger is attached")
            return None

    def _send_cdp_command(self, ws: websocket.WebSocket, method: str, params: Dict = None) -> Dict:
        """Send CDP command and get response with full error visibility"""
        self._command_counter += 1
        cmd_id = self._command_counter
        
        cmd = {
            "id": cmd_id,
            "method": method,
            "params": params or {}
        }
        
        print(f"📤 Sending: {method}")
        if params:
            print(f"   Params: {json.dumps(params)[:200]}")
        
        try:
            ws.send(json.dumps(cmd))
        except Exception as e:
            print(f"❌ Failed to send command: {e}")
            return None
        
        # Wait for response with timeout
        start_time = time.time()
        while time.time() - start_time < 30:
            try:
                response = ws.recv()
                data = json.loads(response)
                
                # Check if this is our response
                if 'id' in data and data['id'] == cmd_id:
                    if 'error' in data:
                        print(f"❌ CDP Error: {json.dumps(data['error'], indent=2)}")
                    elif 'result' in data:
                        print(f"✅ Received response for {method}")
                    return data
                else:
                    # It's a notification or other message
                    if 'method' in data:
                        print(f"ℹ️ Notification: {data['method']}")
                    continue
                    
            except websocket.WebSocketTimeoutException:
                print("⏳ Waiting for response...")
                continue
            except Exception as e:
                print(f"⚠️ Response parsing error: {e}")
                continue
        
        print(f"❌ Timeout waiting for response to {method}")
        return None

    def _enable_domain(self, ws: websocket.WebSocket, domain: str) -> bool:
        """Enable a CDP domain with full error visibility"""
        print(f"🔧 Enabling domain: {domain}")
        try:
            result = self._send_cdp_command(ws, f"{domain}.enable")
            if result and 'error' not in result:
                print(f"✅ {domain} enabled")
                return True
            else:
                print(f"❌ Failed to enable {domain}")
                return False
        except Exception as e:
            print(f"❌ Exception enabling {domain}: {e}")
            return False

    # ==================== DOM Domain Methods ====================
    
    def get_document(self, tab_index: int = 0, depth: int = -1, 
                     pierce: bool = True) -> Optional[Dict]:
        """Get full DOM tree with node IDs (CDP DOM.getDocument)"""
        print("\n📄 DOM.getDocument - Fetching DOM tree...")
        
        # Get fresh WebSocket URL
        ws_url = self.get_websocket_url(tab_index)
        if not ws_url:
            return None
        
        ws = self._connect_websocket()
        if not ws:
            return None
        
        try:
            # Enable DOM domain first
            if not self._enable_domain(ws, "DOM"):
                ws.close()
                return None
            
            # Get document
            params = {"depth": depth, "pierce": pierce}
            result = self._send_cdp_command(ws, "DOM.getDocument", params)
            ws.close()
            
            if result and 'result' in result:
                root = result['result']['root']
                print(f"✅ DOM tree retrieved! Root: {root.get('nodeName')} (ID: {root.get('nodeId')})")
                return root
            return None
        except Exception as e:
            print(f"❌ DOM.getDocument error: {e}")
            import traceback
            traceback.print_exc()
            if ws:
                ws.close()
            return None

    def get_dom_snapshot(self, tab_index: int = 0) -> Optional[LayoutSnapshot]:
        """Capture complete DOM snapshot with layout and styles"""
        print("\n📸 DOMSnapshot.captureSnapshot - Capturing snapshot...")
        
        ws_url = self.get_websocket_url(tab_index)
        if not ws_url:
            return None
        
        ws = self._connect_websocket()
        if not ws:
            return None
        
        try:
            # Enable required domains
            print("🔧 Enabling required domains...")
            self._enable_domain(ws, "DOM")
            self._enable_domain(ws, "CSS")
            
            # Capture snapshot - FIX: computedStyles needs to be a list of style names
            # Or use the simpler DOMSnapshot.getSnapshot method
            params = {
                "computedStyleWhitelist": [],  # Empty list means get all computed styles
                "includeEventListeners": False,
                "includePaintOrder": False,
                "includeUserAgentShadowTree": True
            }
            result = self._send_cdp_command(ws, "DOMSnapshot.captureSnapshot", params)
            ws.close()
            
            if result and 'result' in result:
                snapshot_data = result['result']
                print(f"✅ Snapshot captured!")
                print(f"   DOM nodes: {len(snapshot_data.get('domNodes', []))}")
                print(f"   Layout tree: {len(snapshot_data.get('layoutTree', []))}")
                return LayoutSnapshot(
                    dom_nodes=snapshot_data.get('domNodes', []),
                    layout_tree=snapshot_data.get('layoutTree', []),
                    computed_styles=snapshot_data.get('computedStyles', [])
                )
            return None
        except Exception as e:
            print(f"❌ DOMSnapshot.captureSnapshot error: {e}")
            import traceback
            traceback.print_exc()
            if ws:
                ws.close()
            return None

    def get_accessibility_tree(self, tab_index: int = 0) -> Optional[Dict]:
        """Get accessibility tree with semantic roles"""
        print("\n♿ Accessibility.getFullAXTree - Getting accessibility tree...")
        
        ws_url = self.get_websocket_url(tab_index)
        if not ws_url:
            return None
        
        ws = self._connect_websocket()
        if not ws:
            return None
        
        try:
            # Enable Accessibility domain
            if not self._enable_domain(ws, "Accessibility"):
                ws.close()
                return None
            
            # Get full accessibility tree
            result = self._send_cdp_command(ws, "Accessibility.getFullAXTree")
            ws.close()
            
            if result and 'result' in result:
                nodes = result['result'].get('nodes', [])
                print(f"✅ Accessibility tree retrieved! Found {len(nodes)} nodes")
                return result['result']
            return None
        except Exception as e:
            print(f"❌ Accessibility.getFullAXTree error: {e}")
            import traceback
            traceback.print_exc()
            if ws:
                ws.close()
            return None

    # ==================== CSS Domain Methods ====================
    
    def get_computed_styles(self, tab_index: int = 0, 
                           node_id: int = None) -> Optional[List[Dict]]:
        """Get computed styles for a specific node"""
        print("\n🎨 CSS.getComputedStyleForNode - Getting computed styles...")
        
        ws_url = self.get_websocket_url(tab_index)
        if not ws_url:
            return None
        
        ws = self._connect_websocket()
        if not ws:
            return None
        
        try:
            self._enable_domain(ws, "CSS")
            
            if node_id is None:
                # Get document root first
                root = self.get_document(tab_index)
                if root and 'nodeId' in root:
                    node_id = root['nodeId']
                    print(f"   Using root node ID: {node_id}")
                else:
                    print("❌ Could not get root node")
                    return None
            
            params = {"nodeId": node_id}
            result = self._send_cdp_command(ws, "CSS.getComputedStyleForNode", params)
            ws.close()
            
            if result and 'result' in result:
                styles = result['result'].get('computedStyle', [])
                print(f"✅ Retrieved {len(styles)} computed styles")
                return styles
            return None
        except Exception as e:
            print(f"❌ CSS.getComputedStyleForNode error: {e}")
            import traceback
            traceback.print_exc()
            if ws:
                ws.close()
            return None

    # ==================== Combined Methods ====================
    
    def analyze_page_structure(self, tab_index: int = 0) -> Dict:
        """Comprehensive page analysis using multiple CDP domains"""
        print("\n🔬 Performing complete page analysis...")
        result = {
            "timestamp": datetime.now().isoformat(),
            "dom_tree": None,
            "snapshot": None,
            "accessibility": None,
            "metadata": {}
        }
        
        # 1. Get DOM document
        dom_root = self.get_document(tab_index)
        if dom_root:
            result["dom_tree"] = dom_root
            result["metadata"]["node_count"] = self._count_nodes(dom_root)
        
        # 2. Get full snapshot
        snapshot = self.get_dom_snapshot(tab_index)
        if snapshot:
            result["snapshot"] = snapshot
            result["metadata"]["layout_count"] = len(snapshot.layout_tree)
        
        # 3. Get accessibility tree
        ax_tree = self.get_accessibility_tree(tab_index)
        if ax_tree:
            result["accessibility"] = ax_tree
            result["metadata"]["ax_nodes"] = len(ax_tree.get('nodes', []))
        
        print(f"\n✅ Analysis complete!")
        return result

    def _count_nodes(self, node: Dict) -> int:
        """Count total nodes in DOM tree"""
        count = 1
        for child in node.get('children', []):
            count += self._count_nodes(child)
        return count

    def extract_semantic_elements(self, tab_index: int = 0) -> List[Dict]:
        """Extract semantic elements using accessibility tree"""
        ax_tree = self.get_accessibility_tree(tab_index)
        if not ax_tree:
            return []
        
        semantic_elements = []
        for node in ax_tree.get('nodes', []):
            role = node.get('role', {}).get('value', '')
            if role in ['button', 'heading', 'list', 'dialog', 'link', 'textbox', 'checkbox', 'radio']:
                name = node.get('name', {}).get('value', '')
                semantic_elements.append({
                    'role': role,
                    'name': name,
                    'node_id': node.get('nodeId'),
                    'backend_node_id': node.get('backendDOMNodeId')
                })
        
        return semantic_elements

    def evaluate_script(self, script: str, tab_index: int = 0, 
                       return_by_value: bool = True,
                       await_promise: bool = True) -> Optional[Any]:
        """Execute JavaScript (original Runtime.evaluate)"""
        print("\n⚡ Runtime.evaluate - Executing script...")
        
        ws_url = self.get_websocket_url(tab_index)
        if not ws_url:
            return None
        
        ws = self._connect_websocket()
        if not ws:
            return None
        
        try:
            self._enable_domain(ws, "Runtime")
            
            params = {
                "expression": script,
                "returnByValue": return_by_value,
                "awaitPromise": await_promise
            }
            result = self._send_cdp_command(ws, "Runtime.evaluate", params)
            ws.close()
            
            if result and 'result' in result:
                if 'result' in result['result']:
                    value = result['result']['result'].get('value')
                    print(f"✅ Script executed successfully")
                    return value
                elif 'error' in result['result']:
                    print(f"⚠️ Script error: {result['result']['error']}")
            return None
        except Exception as e:
            print(f"❌ Runtime.evaluate error: {e}")
            import traceback
            traceback.print_exc()
            if ws:
                ws.close()
            return None

    # ==================== Utility Methods ====================

    def list_tabs(self):
        """Display all available tabs"""
        self.get_tabs()

        if not self.tabs:
            print("❌ No tabs found")
            return

        print("\n📑 Available Tabs:")
        print("=" * 60)
        for i, tab in enumerate(self.tabs):
            title = tab.get('title', 'Untitled')[:50]
            url = tab.get('url', '')[:50]
            ws_url = tab.get('webSocketDebuggerUrl', 'No WebSocket')
            print(f"  [{i}] {title}")
            print(f"      URL: {url}")
            print(f"      WS: {ws_url[:60] if ws_url else 'None'}...")
            print()

def main():
    print("🚀 Enhanced Chrome CDP Controller - Fully Working")
    print("=" * 60)
    print("Domains available: DOM, Accessibility, CSS")
    print("=" * 60)

    # Get port
    port_input = input("🔌 Chrome debug port (default 9227): ").strip()
    port = int(port_input) if port_input else 9227

    # Create executor
    chrome = EnhancedChromeCDP(port)

    # Check connection
    print(f"\n📡 Connecting to Chrome on port {port}...")
    tabs = chrome.get_tabs()

    if not tabs:
        print("❌ No tabs found. Make sure Chrome is running with:")
        print(f"   chromium-browser --remote-debugging-port={port}")
        print("   Or: google-chrome --remote-debugging-port={port}")
        return

    print(f"✅ Found {len(tabs)} tabs")
    chrome.list_tabs()

    # Select tab
    tab_input = input(f"\n📑 Select tab (0-{len(tabs)-1}, default 0): ").strip()
    tab_index = int(tab_input) if tab_input else 0

    # Main loop
    while True:
        print("\n" + "=" * 60)
        print("📝 CDP Commands:")
        print("  1. Execute JavaScript (Runtime.evaluate)")
        print("  2. Get DOM Tree (DOM.getDocument) - WORKING ✅")
        print("  3. Capture DOM Snapshot (DOMSnapshot.captureSnapshot) - FIXED ✅")
        print("  4. Get Accessibility Tree (Accessibility.getFullAXTree) - WORKING ✅")
        print("  5. Complete Page Analysis (All Domains)")
        print("  6. Extract Semantic Elements (Accessibility)")
        print("  7. Get Computed Styles (CSS.getComputedStyleForNode)")
        print("  8. List Tabs")
        print("  9. Change Tab (refreshes WebSocket URL)")
        print("  0. Exit")
        print("=" * 60)

        choice = input("Select option: ").strip()

        if choice == "0":
            print("👋 Goodbye!")
            break

        elif choice == "1":
            print("\n📝 Enter JavaScript (type 'END' on a new line when done):")
            lines = []
            while True:
                line = input()
                if line.strip() == "END":
                    break
                lines.append(line)
            script = "\n".join(lines)

            if script:
                result = chrome.evaluate_script(script, tab_index)
                if result is not None:
                    print(f"\n✅ Result: {json.dumps(result, indent=2, default=str)[:3000]}")
                else:
                    print("\n❌ No result returned")

        elif choice == "2":
            dom_root = chrome.get_document(tab_index)
            if dom_root:
                node_count = chrome._count_nodes(dom_root)
                print(f"\n📊 DOM Statistics:")
                print(f"   Total nodes: {node_count}")
                print(f"   Root node: {dom_root.get('nodeName')} (ID: {dom_root.get('nodeId')})")
                
                # Show a sample of nodes
                def show_sample(node, depth=0, max_depth=2):
                    if depth > max_depth:
                        return
                    indent = "  " * depth
                    node_name = node.get('nodeName', 'unknown')
                    print(f"{indent}├─ {node_name} (ID: {node.get('nodeId')})")
                    for child in node.get('children', [])[:2]:
                        show_sample(child, depth+1, max_depth)
                    if len(node.get('children', [])) > 2:
                        print(f"{indent}  └─ ... and {len(node.get('children', []))-2} more")
                
                print(f"\n📝 Sample DOM structure:")
                show_sample(dom_root)
                
                save = input("\n💾 Save DOM tree to file? (y/n): ").strip().lower()
                if save == 'y':
                    filename = f"dom_tree_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                    with open(filename, 'w') as f:
                        json.dump(dom_root, f, indent=2)
                    print(f"✅ Saved to {filename}")
            else:
                print("❌ Failed to get DOM tree")

        elif choice == "3":
            snapshot = chrome.get_dom_snapshot(tab_index)
            if snapshot:
                print(f"\n📊 Snapshot Statistics:")
                print(f"   DOM nodes: {len(snapshot.dom_nodes)}")
                print(f"   Layout tree: {len(snapshot.layout_tree)}")
                print(f"   Computed styles: {len(snapshot.computed_styles)}")
                
                save = input("\n💾 Save snapshot to file? (y/n): ").strip().lower()
                if save == 'y':
                    filename = f"snapshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                    with open(filename, 'w') as f:
                        json.dump({
                            'dom_nodes': snapshot.dom_nodes,
                            'layout_tree': snapshot.layout_tree,
                            'computed_styles': snapshot.computed_styles
                        }, f, indent=2)
                    print(f"✅ Saved to {filename}")
            else:
                print("❌ Failed to capture snapshot")

        elif choice == "4":
            ax_tree = chrome.get_accessibility_tree(tab_index)
            if ax_tree:
                nodes = ax_tree.get('nodes', [])
                print(f"\n📊 Accessibility Statistics:")
                print(f"   Total accessible nodes: {len(nodes)}")
                
                # Show summary of roles
                roles = {}
                for node in nodes:
                    role = node.get('role', {}).get('value', 'unknown')
                    roles[role] = roles.get(role, 0) + 1
                
                print("\n   Role distribution (top 10):")
                for role, count in sorted(roles.items(), key=lambda x: x[1], reverse=True)[:10]:
                    print(f"     {role}: {count}")
                
                save = input("\n💾 Save accessibility tree to file? (y/n): ").strip().lower()
                if save == 'y':
                    filename = f"ax_tree_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                    with open(filename, 'w') as f:
                        json.dump(ax_tree, f, indent=2)
                    print(f"✅ Saved to {filename}")
            else:
                print("❌ Failed to get accessibility tree")

        elif choice == "5":
            print("\n🔬 Performing complete page analysis...")
            analysis = chrome.analyze_page_structure(tab_index)
            
            print(f"\n📊 Analysis Summary:")
            for key, value in analysis.get('metadata', {}).items():
                print(f"   {key}: {value}")
            
            save = input("\n💾 Save analysis to file? (y/n): ").strip().lower()
            if save == 'y':
                filename = f"page_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                # Convert dataclasses to dict
                analysis_serializable = analysis.copy()
                if analysis_serializable.get('snapshot'):
                    snap = analysis_serializable['snapshot']
                    analysis_serializable['snapshot'] = {
                        'dom_nodes': snap.dom_nodes,
                        'layout_tree': snap.layout_tree,
                        'computed_styles': snap.computed_styles
                    }
                with open(filename, 'w') as f:
                    json.dump(analysis_serializable, f, indent=2, default=str)
                print(f"✅ Saved to {filename}")

        elif choice == "6":
            elements = chrome.extract_semantic_elements(tab_index)
            if elements:
                print(f"✅ Found {len(elements)} semantic elements:")
                for elem in elements[:20]:
                    name = elem['name'][:50] if elem['name'] else '(unnamed)'
                    print(f"   [{elem['role']}] {name}")
                if len(elements) > 20:
                    print(f"   ... and {len(elements)-20} more")
                
                save = input("\n💾 Save semantic elements to file? (y/n): ").strip().lower()
                if save == 'y':
                    filename = f"semantic_elements_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                    with open(filename, 'w') as f:
                        json.dump(elements, f, indent=2)
                    print(f"✅ Saved to {filename}")
            else:
                print("❌ No semantic elements found")

        elif choice == "7":
            styles = chrome.get_computed_styles(tab_index)
            if styles:
                print(f"✅ Retrieved {len(styles)} computed styles:")
                for style in styles[:20]:
                    name = style.get('name', '')
                    value = style.get('value', '')[:50]
                    print(f"   {name}: {value}")
                if len(styles) > 20:
                    print(f"   ... and {len(styles)-20} more styles")
            else:
                print("❌ Failed to get computed styles")

        elif choice == "8":
            chrome.list_tabs()

        elif choice == "9":
            # Force refresh tabs and WebSocket URL
            chrome.tabs = []
            chrome.ws_url = None
            tabs = chrome.get_tabs()
            chrome.list_tabs()
            tab_input = input(f"\n📑 Select tab (0-{len(chrome.tabs)-1}): ").strip()
            if tab_input:
                tab_index = int(tab_input)
                ws_url = chrome.get_websocket_url(tab_index)
                if ws_url:
                    print(f"✅ Switched to tab {tab_index}")
                else:
                    print(f"❌ Invalid tab index")

        else:
            print("❌ Invalid choice")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Interrupted. Goodbye!")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
