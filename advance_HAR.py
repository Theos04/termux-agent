#!/usr/bin/env python3
"""
Enhanced Chrome CDP Controller - Working Version
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
    dom_nodes: List[Dict]
    layout_tree: List[Dict]
    computed_styles: List[Dict]

class EnhancedChromeCDP:
    def __init__(self, port: int = 9227):
        self.port = port
        self.base_url = f"http://127.0.0.1:{port}"
        self.ws_url = None
        self.tabs = []
        self.connection_timeout = 5
        self._command_counter = 0
        self._ws = None
        self._dom_enabled = False
        self._css_enabled = False
        self._ax_enabled = False
        self._runtime_enabled = False

    def get_tabs(self) -> List[Dict]:
        try:
            response = requests.get(f"{self.base_url}/json", timeout=3)
            if response.status_code == 200:
                tabs = response.json()
                self.tabs = [t for t in tabs if t.get('type') == 'page']
                return self.tabs
            return []
        except Exception as e:
            print(f"❌ Error fetching tabs: {e}")
            return []

    def get_websocket_url(self, tab_index: int = 0) -> Optional[str]:
        self.get_tabs()
        if not self.tabs or tab_index >= len(self.tabs):
            return None
        ws_url = self.tabs[tab_index].get('webSocketDebuggerUrl')
        if ws_url:
            self.ws_url = ws_url
            return ws_url
        return None

    def _connect_websocket(self) -> bool:
        try:
            if self._ws:
                try:
                    self._ws.close()
                except:
                    pass
                self._ws = None
            
            if not self.ws_url:
                return False
            
            print(f"🔌 Connecting to WebSocket...")
            self._ws = websocket.create_connection(
                self.ws_url,
                timeout=self.connection_timeout
            )
            print("✅ WebSocket connected")
            return True
        except Exception as e:
            print(f"❌ WebSocket connection error: {e}")
            return False

    def _close_websocket(self):
        if self._ws:
            try:
                self._ws.close()
            except:
                pass
            self._ws = None

    def _send_cdp_command(self, method: str, params: Dict = None) -> Optional[Dict]:
        if not self._ws:
            return None
        
        self._command_counter += 1
        cmd_id = self._command_counter
        
        cmd = {"id": cmd_id, "method": method, "params": params or {}}
        
        try:
            self._ws.send(json.dumps(cmd))
        except Exception as e:
            print(f"❌ Failed to send command: {e}")
            return None
        
        start_time = time.time()
        while time.time() - start_time < 10:
            try:
                self._ws.settimeout(1)
                response = self._ws.recv()
                data = json.loads(response)
                
                if 'id' in data and data['id'] == cmd_id:
                    if 'error' in data:
                        print(f"❌ CDP Error: {data['error']}")
                    return data
            except websocket.WebSocketTimeoutException:
                continue
            except Exception as e:
                print(f"⚠️ Error: {e}")
                continue
        
        print(f"❌ Timeout waiting for response to {method}")
        return None

    def _enable_domain(self, domain: str) -> bool:
        if not self._ws:
            return False
        
        try:
            result = self._send_cdp_command(f"{domain}.enable")
            if result and 'error' not in result:
                if domain == "DOM":
                    self._dom_enabled = True
                elif domain == "CSS":
                    self._css_enabled = True
                elif domain == "Accessibility":
                    self._ax_enabled = True
                elif domain == "Runtime":
                    self._runtime_enabled = True
                return True
            return False
        except Exception as e:
            print(f"❌ Error enabling {domain}: {e}")
            return False

    # ==================== DOM Methods ====================

    def get_document(self, tab_index: int = 0, depth: int = -1, pierce: bool = True) -> Optional[Dict]:
        print("\n📄 Getting DOM tree...")
        
        if not self.get_websocket_url(tab_index) or not self._connect_websocket():
            return None
        
        try:
            if not self._enable_domain("DOM"):
                return None
            
            result = self._send_cdp_command("DOM.getDocument", {"depth": depth, "pierce": pierce})
            
            if result and 'result' in result:
                root = result['result']['root']
                print(f"✅ DOM tree retrieved!")
                return root
            return None
        except Exception as e:
            print(f"❌ Error: {e}")
            return None
        finally:
            self._close_websocket()

    def get_dom_snapshot(self, tab_index: int = 0) -> Optional[LayoutSnapshot]:
        print("\n📸 Getting DOM snapshot...")
        
        if not self.get_websocket_url(tab_index) or not self._connect_websocket():
            return None
        
        try:
            self._enable_domain("DOM")
            self._enable_domain("CSS")
            
            result = self._send_cdp_command("DOMSnapshot.getSnapshot", {
                "computedStyleWhitelist": [],
                "includeEventListeners": False,
                "includePaintOrder": False,
                "includeUserAgentShadowTree": True
            })
            
            if result and 'result' in result:
                data = result['result']
                print(f"✅ Snapshot captured!")
                return LayoutSnapshot(
                    dom_nodes=data.get('domNodes', []),
                    layout_tree=data.get('layoutTree', []),
                    computed_styles=data.get('computedStyles', [])
                )
            return None
        except Exception as e:
            print(f"❌ Error: {e}")
            return None
        finally:
            self._close_websocket()

    def get_accessibility_tree(self, tab_index: int = 0) -> Optional[Dict]:
        print("\n♿ Getting accessibility tree...")
        
        if not self.get_websocket_url(tab_index) or not self._connect_websocket():
            return None
        
        try:
            if not self._enable_domain("Accessibility"):
                return None
            
            result = self._send_cdp_command("Accessibility.getFullAXTree")
            
            if result and 'result' in result:
                nodes = result['result'].get('nodes', [])
                print(f"✅ Accessibility tree retrieved! Found {len(nodes)} nodes")
                return result['result']
            return None
        except Exception as e:
            print(f"❌ Error: {e}")
            return None
        finally:
            self._close_websocket()

    def get_computed_styles(self, tab_index: int = 0, node_id: int = None) -> Optional[List[Dict]]:
        print("\n🎨 Getting computed styles...")
        
        if not self.get_websocket_url(tab_index) or not self._connect_websocket():
            return None
        
        try:
            self._enable_domain("DOM")
            self._enable_domain("CSS")
            
            if node_id is None:
                root = self.get_document(tab_index)
                if root:
                    node_id = self._find_first_element(root)
                    if not node_id:
                        print("❌ Could not find any element nodes")
                        return None
            
            result = self._send_cdp_command("CSS.getComputedStyleForNode", {"nodeId": node_id})
            
            if result and 'result' in result:
                styles = result['result'].get('computedStyle', [])
                print(f"✅ Retrieved {len(styles)} computed styles")
                return styles
            return None
        except Exception as e:
            print(f"❌ Error: {e}")
            return None
        finally:
            self._close_websocket()

    def _find_first_element(self, node: Dict) -> Optional[int]:
        if node.get('nodeType') == 1:
            return node.get('nodeId')
        for child in node.get('children', []):
            result = self._find_first_element(child)
            if result:
                return result
        return None

    # ==================== JavaScript Methods ====================

    def evaluate_script(self, script: str, tab_index: int = 0,
                       return_by_value: bool = True,
                       await_promise: bool = True) -> Optional[Any]:
        print("\n⚡ Executing script...")
        
        if not self.get_websocket_url(tab_index) or not self._connect_websocket():
            return None
        
        try:
            self._enable_domain("Runtime")
            
            result = self._send_cdp_command("Runtime.evaluate", {
                "expression": script,
                "returnByValue": return_by_value,
                "awaitPromise": await_promise
            })
            
            if result and 'result' in result:
                if 'result' in result['result']:
                    value = result['result']['result'].get('value')
                    print(f"✅ Script executed successfully")
                    return value
                elif 'error' in result['result']:
                    print(f"⚠️ Script error: {result['result']['error']}")
            return None
        except Exception as e:
            print(f"❌ Error: {e}")
            return None
        finally:
            self._close_websocket()

    # ==================== Interactive Element Methods ====================

    def find_interactive_elements(self, tab_index: int = 0) -> List[Dict]:
        print("\n🔍 Finding interactive elements...")
        
        js_script = """
        (function() {
            const results = [];
            const selectors = [
                'button', 'input[type="button"]', 'input[type="submit"]',
                'input[type="reset"]', 'a[href]', '[role="button"]',
                '[role="link"]', '[onclick]', '[data-action]',
                '.btn', '[class*="button"]', '[class*="btn"]',
                '[data-testid*="button"]'
            ];
            
            const elements = document.querySelectorAll(selectors.join(','));
            
            elements.forEach((el, index) => {
                const rect = el.getBoundingClientRect();
                const isVisible = rect.width > 0 && rect.height > 0;
                
                const attrs = {};
                ['id', 'class', 'data-action', 'data-testid', 'aria-label',
                 'title', 'type', 'value', 'href', 'name', 'role'].forEach(attr => {
                    if (el.hasAttribute(attr)) {
                        attrs[attr] = el.getAttribute(attr);
                    }
                });
                
                let text = el.textContent.trim();
                if (!text && el.tagName === 'INPUT') {
                    text = el.value || el.getAttribute('placeholder') || '';
                }
                
                let type = el.tagName.toLowerCase();
                if (type === 'input') {
                    type = `input[${el.type || 'text'}]`;
                }
                
                results.push({
                    index: index,
                    tag: el.tagName.toLowerCase(),
                    type: type,
                    text: text.substring(0, 100),
                    visible: isVisible,
                    attributes: attrs,
                    selector: el.id ? `#${el.id}` : null
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
                             action: str = 'click', value: str = None) -> Optional[Any]:
        print(f"\n🎯 Interacting with element #{element_index}...")
        
        if action == 'click':
            js_script = f"""
            (function() {{
                const selectors = [
                    'button', 'input[type="button"]', 'input[type="submit"]',
                    'input[type="reset"]', 'a[href]', '[role="button"]',
                    '[role="link"]', '[onclick]', '[data-action]',
                    '.btn', '[class*="button"]', '[class*="btn"]'
                ];
                
                const elements = document.querySelectorAll(selectors.join(','));
                const el = elements[{element_index}];
                
                if (!el) return {{ error: 'Element not found' }};
                
                el.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                setTimeout(() => {{
                    const event = new MouseEvent('click', {{
                        view: window,
                        bubbles: true,
                        cancelable: true
                    }});
                    el.dispatchEvent(event);
                    if (typeof el.click === 'function') el.click();
                }}, 100);
                
                return {{ success: true, tag: el.tagName.toLowerCase() }};
            }})();
            """
            result = self.evaluate_script(js_script, tab_index, await_promise=True)
            if result and result.get('success'):
                print(f"✅ Clicked element successfully")
            else:
                print(f"❌ Failed to click element")
            return result
            
        elif action == 'type' and value is not None:
            js_script = f"""
            (function() {{
                const selectors = [
                    'input[type="text"]', 'input[type="email"]',
                    'input[type="password"]', 'input[type="number"]',
                    'input[type="tel"]', 'textarea', '[contenteditable="true"]'
                ];
                
                const elements = document.querySelectorAll(selectors.join(','));
                const el = elements[{element_index}];
                
                if (!el) return {{ error: 'Element not found' }};
                
                el.focus();
                el.value = `{value}`;
                el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                
                return {{ success: true, value: `{value}` }};
            }})();
            """
            result = self.evaluate_script(js_script, tab_index)
            if result and result.get('success'):
                print(f"✅ Typed '{value}' into element")
            else:
                print(f"❌ Failed to type into element")
            return result
        
        return None

    def interactive_element_explorer(self, tab_index: int = 0):
        print("\n🎯 Interactive Elements Explorer")
        print("-" * 60)
        
        elements = self.find_interactive_elements(tab_index)
        if not elements:
            print("❌ No interactive elements found")
            return
        
        page_size = 10
        total_pages = (len(elements) + page_size - 1) // page_size
        current_page = 0
        
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
                print(f"  [{i:2d}] {visible} {tag:10s}: {text}")
            
            print("\n📌 Commands:")
            print("  [n] Next page  [p] Previous page  [q] Quit")
            print("  [index] Click element")
            print("  [type index text] Type text into element")
            cmd = input("\nEnter command: ").strip()
            
            if cmd.lower() == 'q':
                break
            elif cmd.lower() == 'n' and current_page < total_pages - 1:
                current_page += 1
            elif cmd.lower() == 'p' and current_page > 0:
                current_page -= 1
            elif cmd.startswith('type '):
                parts = cmd.split(' ', 2)
                if len(parts) == 3:
                    idx = int(parts[1])
                    text = parts[2]
                    if 0 <= idx < len(elements):
                        self.interact_with_element(tab_index, idx, 'type', text)
                    else:
                        print("❌ Invalid index")
                else:
                    print("❌ Usage: type <index> <text>")
            elif cmd.isdigit():
                elem_index = int(cmd)
                if 0 <= elem_index < len(elements):
                    self.interact_with_element(tab_index, elem_index, 'click')
                else:
                    print("❌ Invalid index")
            else:
                print("❌ Invalid command")

    # ==================== Analysis Methods ====================

    def analyze_page_structure(self, tab_index: int = 0) -> Dict:
        print("\n🔬 Performing complete page analysis...")
        result = {
            "timestamp": datetime.now().isoformat(),
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
        count = 1
        for child in node.get('children', []):
            count += self._count_nodes(child)
        return count

    def extract_semantic_elements(self, tab_index: int = 0) -> List[Dict]:
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

    def list_tabs(self):
        self.get_tabs()
        if not self.tabs:
            print("❌ No tabs found")
            return
        
        print("\n📑 Available Tabs:")
        print("=" * 60)
        for i, tab in enumerate(self.tabs):
            title = tab.get('title', 'Untitled')[:50]
            url = tab.get('url', '')[:50]
            print(f"  [{i}] {title}")
            print(f"      URL: {url}")
            print()

def main():
    print("🚀 Enhanced Chrome CDP Controller")
    print("=" * 60)
    print("Features: DOM, Accessibility, CSS, JavaScript, Interactive Elements")
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
        print("  1. Execute JavaScript")
        print("  2. Get DOM Tree")
        print("  3. Get DOM Snapshot")
        print("  4. Get Accessibility Tree")
        print("  5. Complete Page Analysis")
        print("  6. Get Computed Styles")
        print("  7. Extract Semantic Elements")
        print("  8. Interactive Element Explorer 🎯")
        print("  9. List Tabs")
        print(" 10. Change Tab")
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
                print(f"   Root node: {dom_root.get('nodeName')}")
                
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
        
        elif choice == "7":
            elements = chrome.extract_semantic_elements(tab_index)
            if elements:
                print(f"✅ Found {len(elements)} semantic elements:")
                for elem in elements[:20]:
                    name = elem['name'][:50] if elem['name'] else '(unnamed)'
                    print(f"   [{elem['role']}] {name}")
                if len(elements) > 20:
                    print(f"   ... and {len(elements)-20} more")
            else:
                print("❌ No semantic elements found")
        
        elif choice == "8":
            chrome.interactive_element_explorer(tab_index)
        
        elif choice == "9":
            chrome.list_tabs()
        
        elif choice == "10":
            chrome._close_websocket()
            chrome.tabs = []
            tabs = chrome.get_tabs()
            chrome.list_tabs()
            tab_input = input(f"\n📑 Select tab (0-{len(chrome.tabs)-1}): ").strip()
            if tab_input:
                tab_index = int(tab_input)
                print(f"✅ Switched to tab {tab_index}")
        
        else:
            print("❌ Invalid choice")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Interrupted. Goodbye!")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
