#!/usr/bin/env python3
"""
Enhanced Chrome CDP Controller - All Features Working
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
        self._dom_enabled = False
        self._css_enabled = False
        self._ax_enabled = False

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
            self._dom_enabled = False
            self._css_enabled = False
            self._ax_enabled = False
            return ws
        except Exception as e:
            print(f"❌ WebSocket connection error: {e}")
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

        start_time = time.time()
        while time.time() - start_time < 30:
            try:
                response = ws.recv()
                data = json.loads(response)

                if 'id' in data and data['id'] == cmd_id:
                    if 'error' in data:
                        print(f"❌ CDP Error: {json.dumps(data['error'], indent=2)}")
                    elif 'result' in data:
                        print(f"✅ Received response for {method}")
                    return data
                else:
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
        if domain == "DOM" and self._dom_enabled:
            print(f"✅ {domain} already enabled")
            return True
        if domain == "CSS" and self._css_enabled:
            print(f"✅ {domain} already enabled")
            return True
        if domain == "Accessibility" and self._ax_enabled:
            print(f"✅ {domain} already enabled")
            return True

        print(f"🔧 Enabling domain: {domain}")
        try:
            result = self._send_cdp_command(ws, f"{domain}.enable")
            if result and 'error' not in result:
                print(f"✅ {domain} enabled")
                if domain == "DOM":
                    self._dom_enabled = True
                elif domain == "CSS":
                    self._css_enabled = True
                elif domain == "Accessibility":
                    self._ax_enabled = True
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

        ws_url = self.get_websocket_url(tab_index)
        if not ws_url:
            return None

        ws = self._connect_websocket()
        if not ws:
            return None

        try:
            if not self._enable_domain(ws, "DOM"):
                ws.close()
                return None

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
            if ws:
                ws.close()
            return None

    def get_dom_snapshot(self, tab_index: int = 0) -> Optional[LayoutSnapshot]:
        """Capture complete DOM snapshot using getSnapshot (simpler API)"""
        print("\n📸 DOMSnapshot.getSnapshot - Capturing snapshot...")

        ws_url = self.get_websocket_url(tab_index)
        if not ws_url:
            return None

        ws = self._connect_websocket()
        if not ws:
            return None

        try:
            print("🔧 Enabling required domains...")
            self._enable_domain(ws, "DOM")
            self._enable_domain(ws, "CSS")

            params = {
                "computedStyleWhitelist": [],
                "includeEventListeners": False,
                "includePaintOrder": False,
                "includeUserAgentShadowTree": True
            }
            result = self._send_cdp_command(ws, "DOMSnapshot.getSnapshot", params)
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
            print(f"❌ DOMSnapshot.getSnapshot error: {e}")
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
            if not self._enable_domain(ws, "Accessibility"):
                ws.close()
                return None

            result = self._send_cdp_command(ws, "Accessibility.getFullAXTree")
            ws.close()

            if result and 'result' in result:
                nodes = result['result'].get('nodes', [])
                print(f"✅ Accessibility tree retrieved! Found {len(nodes)} nodes")
                return result['result']
            return None
        except Exception as e:
            print(f"❌ Accessibility.getFullAXTree error: {e}")
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
            # Need DOM enabled first
            self._enable_domain(ws, "DOM")
            self._enable_domain(ws, "CSS")

            if node_id is None:
                # Get the first element node (not document)
                root = self.get_document(tab_index)
                if root:
                    # Find first element node
                    node_id = self._find_first_element(root)
                    if node_id:
                        print(f"   Using first element node ID: {node_id}")
                    else:
                        print("❌ Could not find any element nodes")
                        ws.close()
                        return None
                else:
                    ws.close()
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
            if ws:
                ws.close()
            return None

    def _find_first_element(self, node: Dict) -> Optional[int]:
        """Find the first element node (nodeType 1) in the DOM tree"""
        if node.get('nodeType') == 1:  # Element node
            return node.get('nodeId')

        for child in node.get('children', []):
            result = self._find_first_element(child)
            if result:
                return result
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

        dom_root = self.get_document(tab_index)
        if dom_root:
            result["dom_tree"] = dom_root
            result["metadata"]["node_count"] = self._count_nodes(dom_root)

        snapshot = self.get_dom_snapshot(tab_index)
        if snapshot:
            result["snapshot"] = snapshot
            result["metadata"]["layout_count"] = len(snapshot.layout_tree)

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
            if ws:
                ws.close()
            return None

    # ==================== Interactive Button Methods ====================

    def find_interactive_elements(self, tab_index: int = 0) -> List[Dict]:
        """Find all interactive elements on the page using IIFE"""
        print("\n🔍 Finding interactive elements...")
        
        js_script = """
        (function() {
            const results = [];
            const selectors = [
                'button',
                'input[type="button"]',
                'input[type="submit"]',
                'input[type="reset"]',
                'a[href]',
                '[role="button"]',
                '[role="link"]',
                '[onclick]',
                '[data-action]',
                '.btn',
                '[class*="button"]',
                '[class*="btn"]',
                '[data-testid*="button"]'
            ];
            
            const elements = document.querySelectorAll(selectors.join(','));
            
            elements.forEach((el, index) => {
                const rect = el.getBoundingClientRect();
                const isVisible = rect.width > 0 && rect.height > 0;
                
                // Get all relevant attributes
                const attrs = {};
                ['id', 'class', 'data-action', 'data-testid', 'aria-label', 
                 'title', 'type', 'value', 'href', 'name', 'role'].forEach(attr => {
                    if (el.hasAttribute(attr)) {
                        attrs[attr] = el.getAttribute(attr);
                    }
                });
                
                // Get text content
                let text = el.textContent.trim();
                if (!text && el.tagName === 'INPUT') {
                    text = el.value || el.getAttribute('placeholder') || '';
                }
                
                // Determine element type
                let type = el.tagName.toLowerCase();
                if (type === 'input') {
                    type = `input[${el.type || 'text'}]`;
                }
                
                // Get click handlers
                let hasClickHandler = false;
                try {
                    hasClickHandler = typeof el.onclick === 'function' ||
                                     el.getAttribute('onclick') !== null ||
                                     el._onclick !== undefined;
                } catch(e) {
                    // Cross-origin restrictions may apply
                }
                
                results.push({
                    index: index,
                    tag: el.tagName.toLowerCase(),
                    type: type,
                    text: text.substring(0, 100),
                    visible: isVisible,
                    hasClickHandler: hasClickHandler,
                    attributes: attrs,
                    selector: el.id ? `#${el.id}` : null,
                    canClick: true
                });
            });
            
            return results;
        })();
        """
        
        result = self.evaluate_script(js_script, tab_index)
        if result and isinstance(result, list):
            print(f"✅ Found {len(result)} interactive elements")
            return result
        return []

    def interact_with_element(self, tab_index: int = 0, element_index: int = 0, 
                             action: str = 'click', value: str = None, 
                             delay: float = 0.5) -> Optional[Any]:
        """Interact with a specific element using IIFE with delay support"""
        print(f"\n🎯 Interacting with element #{element_index}...")
        
        # First, verify the element exists and get its properties
        verify_script = f"""
        (function() {{
            const selectors = [
                'button',
                'input[type="button"]',
                'input[type="submit"]',
                'input[type="reset"]',
                'a[href]',
                '[role="button"]',
                '[role="link"]',
                '[onclick]',
                '[data-action]',
                '.btn',
                '[class*="button"]',
                '[class*="btn"]'
            ];
            
            const elements = document.querySelectorAll(selectors.join(','));
            
            if ({element_index} >= elements.length) {{
                return {{ error: 'Element index out of range' }};
            }}
            
            const el = elements[{element_index}];
            
            // Scroll into view if needed
            el.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
            
            return {{
                tag: el.tagName.toLowerCase(),
                text: el.textContent.trim().substring(0, 100),
                visible: el.offsetParent !== null,
                canInteract: true
            }};
        }})();
        """
        
        verify_result = self.evaluate_script(verify_script, tab_index)
        if verify_result and 'error' in verify_result:
            print(f"❌ {verify_result['error']}")
            return None
        
        print(f"   Element: {verify_result.get('tag', 'unknown')}")
        print(f"   Text: {verify_result.get('text', '')}")
        print(f"   Visible: {verify_result.get('visible', False)}")
        
        # Wait a moment for scroll to complete
        time.sleep(delay)
        
        # Perform the action
        if action == 'click':
            click_script = f"""
            (function() {{
                const selectors = [
                    'button',
                    'input[type="button"]',
                    'input[type="submit"]',
                    'input[type="reset"]',
                    'a[href]',
                    '[role="button"]',
                    '[role="link"]',
                    '[onclick]',
                    '[data-action]',
                    '.btn',
                    '[class*="button"]',
                    '[class*="btn"]'
                ];
                
                const elements = document.querySelectorAll(selectors.join(','));
                const el = elements[{element_index}];
                
                if (!el) return {{ error: 'Element not found' }};
                
                // Simulate click with events
                const event = new MouseEvent('click', {{
                    view: window,
                    bubbles: true,
                    cancelable: true
                }});
                
                el.dispatchEvent(event);
                // Also try native click for links and buttons
                if (typeof el.click === 'function') {{
                    el.click();
                }}
                return {{ success: true, tag: el.tagName.toLowerCase() }};
            }})();
            """
            result = self.evaluate_script(click_script, tab_index)
            if result and result.get('success'):
                print(f"✅ Clicked element successfully")
            else:
                print(f"❌ Failed to click element")
        
        elif action == 'type' and value is not None:
            type_script = f"""
            (function() {{
                const selectors = [
                    'input[type="text"]',
                    'input[type="email"]',
                    'input[type="password"]',
                    'input[type="number"]',
                    'input[type="tel"]',
                    'textarea',
                    '[contenteditable="true"]'
                ];
                
                const elements = document.querySelectorAll(selectors.join(','));
                const el = elements[{element_index}];
                
                if (!el) return {{ error: 'Element not found' }};
                
                // Focus the element
                el.focus();
                
                // Set value
                const value = `{value}`;
                el.value = value;
                
                // Dispatch input events
                el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                
                return {{ success: true, value: value }};
            }})();
            """
            result = self.evaluate_script(type_script, tab_index)
            if result and result.get('success'):
                print(f"✅ Typed '{value}' into element")
            else:
                print(f"❌ Failed to type into element")
        
        elif action == 'hover':
            hover_script = f"""
            (function() {{
                const selectors = [
                    'button',
                    'input[type="button"]',
                    'input[type="submit"]',
                    'input[type="reset"]',
                    'a[href]',
                    '[role="button"]',
                    '[role="link"]',
                    '[onclick]',
                    '[data-action]',
                    '.btn',
                    '[class*="button"]',
                    '[class*="btn"]'
                ];
                
                const elements = document.querySelectorAll(selectors.join(','));
                const el = elements[{element_index}];
                
                if (!el) return {{ error: 'Element not found' }};
                
                // Simulate hover
                const event = new MouseEvent('mouseover', {{
                    view: window,
                    bubbles: true,
                    cancelable: true
                }});
                
                el.dispatchEvent(event);
                return {{ success: true }};
            }})();
            """
            result = self.evaluate_script(hover_script, tab_index)
            if result and result.get('success'):
                print(f"✅ Hovered over element")
            else:
                print(f"❌ Failed to hover over element")
        
        return result

    # ==================== Enhanced Interactive Methods ====================

    def interactive_element_explorer(self, tab_index: int = 0):
        """Interactive element explorer with better control"""
        print("\n🎯 Interactive Elements Explorer")
        print("-" * 60)
        
        elements = self.find_interactive_elements(tab_index)
        if not elements:
            print("❌ No interactive elements found")
            return
        
        # Display elements with pagination
        page_size = 10
        total_pages = (len(elements) + page_size - 1) // page_size
        current_page = 0
        selected_indices = []
        
        while True:
            start = current_page * page_size
            end = min(start + page_size, len(elements))
            
            print(f"\n📋 Elements (Page {current_page+1}/{total_pages}):")
            print("=" * 70)
            for i in range(start, end):
                elem = elements[i]
                text = elem.get('text', '')[:40]
                tag = elem.get('tag', 'unknown')
                visible = "👁️" if elem.get('visible') else "🚫"
                handler = "⚡" if elem.get('hasClickHandler') else "  "
                print(f"  [{i:2d}] {handler} {visible} {tag:10s}: {text}")
                if elem.get('attributes'):
                    attrs = elem.get('attributes', {})
                    if 'id' in attrs:
                        print(f"        ID: {attrs['id']}")
                    if 'class' in attrs:
                        print(f"        Class: {attrs['class'][:40]}")
            
            print("\n📌 Commands:")
            print("  [n] Next page  [p] Previous page  [q] Quit")
            print("  [index] Interact with element")
            print("  [index1,index2] Multiple indices (comma-separated)")
            print("  [range] e.g., 5-10 for a range")
            print("  [all] All elements in current page")
            cmd = input("\nEnter command: ").strip()
            
            if cmd.lower() == 'q':
                break
            elif cmd.lower() == 'n' and current_page < total_pages - 1:
                current_page += 1
            elif cmd.lower() == 'p' and current_page > 0:
                current_page -= 1
            elif cmd.lower() == 'all':
                # Select all elements on current page
                selected_indices = list(range(start, end))
                print(f"✅ Selected {len(selected_indices)} elements on this page")
                
                # Ask for action
                print("\n🎮 What to do with selected elements?")
                print("  1. Click all (with delay)")
                print("  2. Get info for all")
                print("  3. Generate script")
                print("  4. Cancel")
                action = input("Select action: ").strip()
                
                if action == '1':
                    delay = float(input("Delay between clicks (seconds, default 0.5): ").strip() or "0.5")
                    for idx in selected_indices:
                        print(f"\n--- Clicking element {idx} ---")
                        self.interact_with_element(tab_index, idx, 'click', delay=delay)
                        time.sleep(delay)
                elif action == '2':
                    for idx in selected_indices:
                        print(f"\n--- Info for element {idx} ---")
                        self.get_element_info(tab_index, idx)
                elif action == '3':
                    self.generate_interaction_script(tab_index, selected_indices)
                    
            elif '-' in cmd:
                # Range selection
                try:
                    parts = cmd.split('-')
                    if len(parts) == 2:
                        start_idx = int(parts[0].strip())
                        end_idx = int(parts[1].strip())
                        if 0 <= start_idx < len(elements) and 0 <= end_idx < len(elements):
                            selected_indices = list(range(start_idx, end_idx + 1))
                            print(f"✅ Selected elements {start_idx}-{end_idx} ({len(selected_indices)} elements)")
                            
                            # Ask for action
                            print("\n🎮 What to do with selected elements?")
                            print("  1. Click all (with delay)")
                            print("  2. Get info for all")
                            print("  3. Generate script")
                            print("  4. Cancel")
                            action = input("Select action: ").strip()
                            
                            if action == '1':
                                delay = float(input("Delay between clicks (seconds, default 0.5): ").strip() or "0.5")
                                for idx in selected_indices:
                                    print(f"\n--- Clicking element {idx} ---")
                                    self.interact_with_element(tab_index, idx, 'click', delay=delay)
                                    time.sleep(delay)
                            elif action == '2':
                                for idx in selected_indices:
                                    print(f"\n--- Info for element {idx} ---")
                                    self.get_element_info(tab_index, idx)
                            elif action == '3':
                                self.generate_interaction_script(tab_index, selected_indices)
                except Exception as e:
                    print(f"❌ Invalid range: {e}")
                    
            elif ',' in cmd:
                # Multiple comma-separated indices
                try:
                    indices = [int(x.strip()) for x in cmd.split(',')]
                    selected_indices = [i for i in indices if 0 <= i < len(elements)]
                    if selected_indices:
                        print(f"✅ Selected {len(selected_indices)} elements: {selected_indices}")
                        
                        # Ask for action
                        print("\n🎮 What to do with selected elements?")
                        print("  1. Click all (with delay)")
                        print("  2. Get info for all")
                        print("  3. Generate script")
                        print("  4. Cancel")
                        action = input("Select action: ").strip()
                        
                        if action == '1':
                            delay = float(input("Delay between clicks (seconds, default 0.5): ").strip() or "0.5")
                            for idx in selected_indices:
                                print(f"\n--- Clicking element {idx} ---")
                                self.interact_with_element(tab_index, idx, 'click', delay=delay)
                                time.sleep(delay)
                        elif action == '2':
                            for idx in selected_indices:
                                print(f"\n--- Info for element {idx} ---")
                                self.get_element_info(tab_index, idx)
                        elif action == '3':
                            self.generate_interaction_script(tab_index, selected_indices)
                except Exception as e:
                    print(f"❌ Invalid indices: {e}")
                    
            elif cmd.isdigit():
                elem_index = int(cmd)
                if 0 <= elem_index < len(elements):
                    # Interactive element menu
                    self.interactive_element_menu(tab_index, elem_index)
                else:
                    print("❌ Invalid index")
            else:
                print("❌ Invalid command")

    def interactive_element_menu(self, tab_index: int = 0, element_index: int = 0):
        """Interactive menu for a single element"""
        while True:
            print(f"\n🎮 Interacting with element {element_index}")
            print("  1. Click")
            print("  2. Type text")
            print("  3. Hover")
            print("  4. Get detailed info")
            print("  5. Generate script for this element")
            print("  6. Back to explorer")
            
            action = input("Select action: ").strip()
            
            if action == '1':
                self.interact_with_element(tab_index, element_index, 'click')
                print("\nPress Enter to continue...")
                input()
            elif action == '2':
                text = input("📝 Enter text to type: ")
                self.interact_with_element(tab_index, element_index, 'type', text)
                print("\nPress Enter to continue...")
                input()
            elif action == '3':
                self.interact_with_element(tab_index, element_index, 'hover')
                print("\nPress Enter to continue...")
                input()
            elif action == '4':
                self.get_element_info(tab_index, element_index)
                print("\nPress Enter to continue...")
                input()
            elif action == '5':
                self.generate_interaction_script(tab_index, [element_index])
                print("\nPress Enter to continue...")
                input()
            elif action == '6':
                break
            else:
                print("❌ Invalid choice")

    def get_element_info(self, tab_index: int = 0, element_index: int = 0) -> Optional[Dict]:
        """Get detailed information about an element"""
        print(f"\n📋 Getting detailed info for element {element_index}...")
        
        info_script = f"""
        (function() {{
            const selectors = [
                'button',
                'input[type="button"]',
                'input[type="submit"]',
                'input[type="reset"]',
                'a[href]',
                '[role="button"]',
                '[role="link"]',
                '[onclick]',
                '[data-action]',
                '.btn',
                '[class*="button"]',
                '[class*="btn"]'
            ];
            
            const elements = document.querySelectorAll(selectors.join(','));
            const el = elements[{element_index}];
            
            if (!el) {{
                return {{ error: 'Element not found' }};
            }}
            
            const rect = el.getBoundingClientRect();
            const style = window.getComputedStyle(el);
            
            return {{
                tag: el.tagName.toLowerCase(),
                text: el.textContent.trim().substring(0, 200),
                innerHTML: el.innerHTML.substring(0, 200),
                visible: rect.width > 0 && rect.height > 0,
                rect: {{
                    x: Math.round(rect.x),
                    y: Math.round(rect.y),
                    width: Math.round(rect.width),
                    height: Math.round(rect.height)
                }},
                style: {{
                    color: style.color,
                    backgroundColor: style.backgroundColor,
                    fontSize: style.fontSize,
                    fontFamily: style.fontFamily,
                    display: style.display,
                    visibility: style.visibility,
                    opacity: style.opacity,
                    cursor: style.cursor,
                    pointerEvents: style.pointerEvents
                }},
                attributes: {{
                    id: el.id || null,
                    class: el.className || null,
                    role: el.getAttribute('role'),
                    'aria-label': el.getAttribute('aria-label'),
                    type: el.getAttribute('type'),
                    value: el.value || null,
                    href: el.getAttribute('href'),
                    target: el.getAttribute('target'),
                    disabled: el.disabled || false,
                    readonly: el.readOnly || false
                }},
                onClickHandler: typeof el.onclick === 'function',
                isFormElement: ['input', 'textarea', 'select', 'button'].includes(el.tagName.toLowerCase()),
                isLink: el.tagName.toLowerCase() === 'a' && el.hasAttribute('href')
            }};
        }})();
        """
        
        result = self.evaluate_script(info_script, tab_index)
        if result and not 'error' in result:
            print("\n📋 Element Details:")
            print("=" * 60)
            for key, value in result.items():
                if isinstance(value, dict):
                    print(f"{key}:")
                    for subkey, subvalue in value.items():
                        print(f"  {subkey}: {subvalue}")
                else:
                    print(f"{key}: {value}")
            print("=" * 60)
            return result
        else:
            print(f"❌ Failed to get info: {result.get('error', 'Unknown error')}")
            return None

    def generate_interaction_script(self, tab_index: int = 0, indices: List[int] = None):
        """Generate a safe IIFE script for specified elements"""
        if not indices:
            print("❌ No indices specified")
            return
            
        # Get elements first to display info
        elements = self.find_interactive_elements(tab_index)
        
        print(f"\n📜 Generating IIFE Script for {len(indices)} elements...")
        
        script_lines = [
            "// Generated IIFE Script for Element Interaction",
            "// =============================================",
            "(function() {",
            "    const results = [];",
            "    const selectors = [",
            "        'button',",
            "        'input[type=\"button\"]',",
            "        'input[type=\"submit\"]',",
            "        'input[type=\"reset\"]',",
            "        'a[href]',",
            "        '[role=\"button\"]',",
            "        '[role=\"link\"]',",
            "        '[onclick]'",
            "    ];",
            "",
            "    const elements = document.querySelectorAll(selectors.join(','));",
            "    const delay = ms => new Promise(resolve => setTimeout(resolve, ms));",
            "",
            "    // Helper function to click an element safely",
            "    async function clickElement(el, index) {",
            "        try {",
            "            if (!el) return { success: false, index, error: 'Element not found' };",
            "            // Scroll into view",
            "            el.scrollIntoView({ behavior: 'smooth', block: 'center' });",
            "            await delay(100);",
            "            // Try multiple click methods",
            "            try {",
            "                const clickEvent = new MouseEvent('click', {",
            "                    view: window,",
            "                    bubbles: true,",
            "                    cancelable: true",
            "                });",
            "                el.dispatchEvent(clickEvent);",
            "            } catch(e) {}",
            "            try {",
            "                if (typeof el.click === 'function') el.click();",
            "            } catch(e) {}",
            "            return { success: true, index, tag: el.tagName.toLowerCase() };",
            "        } catch(e) {",
            "            return { success: false, index, error: e.message };",
            "        }",
            "    }",
            "",
            "    // Main execution",
            "    async function execute() {",
        ]
        
        # Add click operations for each selected index
        for idx in indices:
            elem = elements[idx] if idx < len(elements) else None
            elem_text = elem.get('text', '')[:30] if elem else 'unknown'
            script_lines.append(f"        // Element {idx}: {elem_text}")
            script_lines.append(f"        const result_{idx} = await clickElement(elements[{idx}], {idx});")
            script_lines.append(f"        results.push(result_{idx});")
            script_lines.append(f"        await delay(300); // Delay between clicks")
            script_lines.append("")
        
        script_lines.extend([
            "        return results;",
            "    }",
            "",
            "    // Execute and return results",
            "    return execute();",
            "})();"
        ])
        
        full_script = "\n".join(script_lines)
        
        print("\n📜 Generated IIFE Script:")
        print("=" * 60)
        print(full_script)
        print("=" * 60)
        
        execute = input("\n🔧 Execute this script? (y/n): ").strip().lower()
        if execute == 'y':
            print("\n⚡ Executing script...")
            # The script returns a promise since it's async
            result = self.evaluate_script(full_script, tab_index, await_promise=True)
            if result:
                print(f"\n📊 Execution Results:")
                if isinstance(result, list):
                    for res in result:
                        if res.get('success'):
                            print(f"  ✅ Element {res.get('index')}: Clicked ({res.get('tag')})")
                        else:
                            print(f"  ❌ Element {res.get('index')}: {res.get('error')}")
                else:
                    print(f"Result: {result}")
            else:
                print("❌ Script execution failed")
        
        save = input("\n💾 Save this script to file? (y/n): ").strip().lower()
        if save == 'y':
            filename = f"interaction_script_{datetime.now().strftime('%Y%m%d_%H%M%S')}.js"
            with open(filename, 'w') as f:
                f.write(full_script)
            print(f"✅ Saved to {filename}")

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
    print("🚀 Enhanced Chrome CDP Controller - All Features Working")
    print("=" * 60)
    print("Domains available: DOM, Accessibility, CSS")
    print("=" * 60)

    port_input = input("🔌 Chrome debug port (default 9227): ").strip()
    port = int(port_input) if port_input else 9227

    chrome = EnhancedChromeCDP(port)

    print(f"\n📡 Connecting to Chrome on port {port}...")
    tabs = chrome.get_tabs()

    if not tabs:
        print("❌ No tabs found. Make sure Chrome is running with:")
        print(f"   chromium-browser --remote-debugging-port={port}")
        return

    print(f"✅ Found {len(tabs)} tabs")
    chrome.list_tabs()

    tab_input = input(f"\n📑 Select tab (0-{len(tabs)-1}, default 0): ").strip()
    tab_index = int(tab_input) if tab_input else 0

    while True:
        print("\n" + "=" * 60)
        print("📝 CDP Commands:")
        print("  1. Execute JavaScript (Runtime.evaluate)")
        print("  2. Get DOM Tree (DOM.getDocument) - WORKING ✅")
        print("  3. Get DOM Snapshot (DOMSnapshot.getSnapshot) - WORKING ✅")
        print("  4. Get Accessibility Tree (Accessibility.getFullAXTree) - WORKING ✅")
        print("  5. Complete Page Analysis (All Domains)")
        print("  6. Extract Semantic Elements (Accessibility)")
        print("  7. Get Computed Styles (CSS.getComputedStyleForNode) - FIXED ✅")
        print("  8. List Tabs")
        print("  9. Change Tab (refreshes WebSocket URL)")
        print(" 10. Interactive Element Explorer 🎯 NEW!")
        print(" 11. Generate Custom Interaction Script 🚀")
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
                print(f"✅ Retrieved {len(styles)} computed styles (showing first 20):")
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
            chrome.tabs = []
            chrome.ws_url = None
            chrome._dom_enabled = False
            chrome._css_enabled = False
            chrome._ax_enabled = False
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

        elif choice == "10":
            chrome.interactive_element_explorer(tab_index)

        elif choice == "11":
            print("\n🚀 Generate Custom Interaction Script")
            print("-" * 60)
            
            # First find elements
            elements = chrome.find_interactive_elements(tab_index)
            if not elements:
                print("❌ No interactive elements found")
                continue
            
            print("\n📋 Available elements:")
            for i, elem in enumerate(elements[:20]):
                text = elem.get('text', '')[:40]
                tag = elem.get('tag', 'unknown')
                handler = "⚡" if elem.get('hasClickHandler') else "  "
                print(f"  [{i:2d}] {handler} {tag:10s}: {text}")
            if len(elements) > 20:
                print(f"  ... and {len(elements)-20} more")
            
            print("\n📌 Enter element indices (comma-separated, range, or 'all'):")
            print("  Example: 1,3,5")
            print("  Example: 5-10")
            print("  Example: all")
            indices_input = input("Indices: ").strip()
            
            selected_indices = []
            
            if indices_input.lower() == 'all':
                selected_indices = list(range(len(elements)))
            elif '-' in indices_input:
                try:
                    parts = indices_input.split('-')
                    if len(parts) == 2:
                        start = int(parts[0].strip())
                        end = int(parts[1].strip())
                        selected_indices = list(range(start, end + 1))
                except:
                    print("❌ Invalid range format")
                    continue
            else:
                try:
                    selected_indices = [int(x.strip()) for x in indices_input.split(',') if x.strip()]
                except:
                    print("❌ Invalid indices format")
                    continue
            
            if not selected_indices:
                print("❌ No valid indices selected")
                continue
            
            # Filter to valid indices
            selected_indices = [i for i in selected_indices if 0 <= i < len(elements)]
            
            if not selected_indices:
                print("❌ No valid indices in range")
                continue
            
            print(f"\n✅ Selected {len(selected_indices)} elements:")
            for idx in selected_indices[:10]:
                elem = elements[idx]
                print(f"  [{idx}] {elem.get('tag')}: {elem.get('text')[:40]}")
            if len(selected_indices) > 10:
                print(f"  ... and {len(selected_indices)-10} more")
            
            chrome.generate_interaction_script(tab_index, selected_indices)

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
