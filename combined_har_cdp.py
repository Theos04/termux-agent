#!/usr/bin/env python3
"""
ULTIMATE Chrome CDP Controller - Complete Power Pack
Combines: Interactive Automation + Full CDP Debugging + DOM/Accessibility/CSS Analysis
"""

import json
import subprocess
import sys
import os
import time
from typing import Optional, Dict, List, Any, Union
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum

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

# ==================== Data Classes ====================

@dataclass
class LayoutSnapshot:
    """Complete layout and style information"""
    dom_nodes: List[Dict]
    layout_tree: List[Dict]
    computed_styles: List[Dict]
    
    def to_dict(self):
        return {
            'dom_nodes': self.dom_nodes,
            'layout_tree': self.layout_tree,
            'computed_styles': self.computed_styles
        }

@dataclass
class InteractiveElement:
    """Represents an interactive element on the page"""
    index: int
    tag: str
    type: str
    text: str
    visible: bool
    attributes: Dict[str, str]
    selector: Optional[str]
    bounding_rect: Optional[Dict] = None
    
    def __str__(self):
        return f"[{self.index}] {self.tag}: {self.text[:30]}..."

@dataclass
class PageAnalysis:
    """Complete page analysis result"""
    timestamp: str
    url: str
    title: str
    dom_tree: Optional[Dict]
    snapshot: Optional[LayoutSnapshot]
    accessibility: Optional[Dict]
    interactive_elements: List[InteractiveElement]
    semantic_elements: List[Dict]
    metadata: Dict[str, Any]
    
    def to_dict(self):
        return {
            'timestamp': self.timestamp,
            'url': self.url,
            'title': self.title,
            'dom_tree': self.dom_tree,
            'snapshot': self.snapshot.to_dict() if self.snapshot else None,
            'accessibility': self.accessibility,
            'interactive_elements': [asdict(e) for e in self.interactive_elements],
            'semantic_elements': self.semantic_elements,
            'metadata': self.metadata
        }

# ==================== Main Controller ====================

class UltimateChromeCDP:
    """Ultimate Chrome CDP Controller - All features combined"""
    
    def __init__(self, port: int = 9227, verbose: bool = True):
        self.port = port
        self.base_url = f"http://127.0.0.1:{port}"
        self.ws_url = None
        self.tabs = []
        self.verbose = verbose
        self.connection_timeout = 15
        self._command_counter = 0
        self._ws = None
        self._dom_enabled = False
        self._css_enabled = False
        self._ax_enabled = False
        self._runtime_enabled = False
        self._page_enabled = False
        self._network_enabled = False
        
        # Session state
        self.current_tab_index = 0
        self.current_tab_info = None
        
    # ==================== Connection Management ====================
    
    def get_tabs(self, refresh: bool = True) -> List[Dict]:
        """Get all tabs from Chrome with enhanced info"""
        try:
            response = requests.get(f"{self.base_url}/json", timeout=5)
            if response.status_code == 200:
                tabs = response.json()
                self.tabs = [t for t in tabs if t.get('type') == 'page']
                if self.verbose:
                    print(f"🔍 Found {len(self.tabs)} tabs")
                return self.tabs
            return []
        except Exception as e:
            if self.verbose:
                print(f"❌ Error fetching tabs: {e}")
            return []
    
    def get_websocket_url(self, tab_index: int = None) -> Optional[str]:
        """Get WebSocket URL for a specific tab"""
        if tab_index is None:
            tab_index = self.current_tab_index
            
        self.get_tabs()
        
        if not self.tabs:
            if self.verbose:
                print("❌ No tabs found")
            return None
            
        if tab_index >= len(self.tabs):
            if self.verbose:
                print(f"❌ Tab index {tab_index} out of range")
            return None
            
        ws_url = self.tabs[tab_index].get('webSocketDebuggerUrl')
        if ws_url:
            self.ws_url = ws_url
            self.current_tab_index = tab_index
            self.current_tab_info = self.tabs[tab_index]
            if self.verbose:
                print(f"🔗 WebSocket URL: {ws_url[:50]}...")
            return ws_url
        if self.verbose:
            print("❌ No WebSocket URL found for tab")
        return None
    
    def _connect_websocket(self) -> bool:
        """Establish WebSocket connection with proper headers"""
        try:
            if self._ws:
                try:
                    self._ws.close()
                except:
                    pass
                self._ws = None
                
            if not self.ws_url:
                return False
                
            if self.verbose:
                print(f"🔌 Connecting to WebSocket...")
                
            self._ws = websocket.create_connection(
                self.ws_url,
                timeout=self.connection_timeout,
                header={"Origin": f"http://127.0.0.1:{self.port}"}
            )
            
            if self.verbose:
                print("✅ WebSocket connected")
                
            # Reset domain states
            self._dom_enabled = False
            self._css_enabled = False
            self._ax_enabled = False
            self._runtime_enabled = False
            self._page_enabled = False
            self._network_enabled = False
            
            return True
        except Exception as e:
            if self.verbose:
                print(f"❌ WebSocket connection error: {e}")
            return False
    
    def _close_websocket(self):
        """Close WebSocket connection if open"""
        if self._ws:
            try:
                self._ws.close()
            except:
                pass
            self._ws = None
    
    def _ensure_connection(self, tab_index: int = None) -> bool:
        """Ensure we have a valid connection"""
        if tab_index is None:
            tab_index = self.current_tab_index
            
        if self._ws:
            return True
            
        if not self.get_websocket_url(tab_index):
            return False
            
        return self._connect_websocket()
    
    def _send_cdp_command(self, method: str, params: Dict = None, 
                          timeout: int = 30) -> Optional[Dict]:
        """Send CDP command and get response with full error visibility"""
        if not self._ws:
            if self.verbose:
                print("❌ No WebSocket connection")
            return None
            
        self._command_counter += 1
        cmd_id = self._command_counter
        
        cmd = {"id": cmd_id, "method": method, "params": params or {}}
        
        if self.verbose:
            print(f"📤 Sending: {method}")
            if params:
                print(f"   Params: {json.dumps(params)[:200]}")
                
        try:
            self._ws.send(json.dumps(cmd))
        except Exception as e:
            if self.verbose:
                print(f"❌ Failed to send command: {e}")
            return None
            
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                self._ws.settimeout(1)
                response = self._ws.recv()
                data = json.loads(response)
                
                if 'id' in data and data['id'] == cmd_id:
                    if 'error' in data:
                        if self.verbose:
                            print(f"❌ CDP Error: {json.dumps(data['error'], indent=2)}")
                    elif 'result' in data and self.verbose:
                        print(f"✅ Received response for {method}")
                    return data
                else:
                    # Handle notifications
                    if 'method' in data and self.verbose:
                        print(f"ℹ️ Notification: {data['method']}")
                    continue
                    
            except websocket.WebSocketTimeoutException:
                if self.verbose:
                    print("⏳ Waiting for response...")
                continue
            except Exception as e:
                if self.verbose:
                    print(f"⚠️ Response parsing error: {e}")
                continue
                
        if self.verbose:
            print(f"❌ Timeout waiting for response to {method}")
        return None
    
    def _enable_domain(self, domain: str) -> bool:
        """Enable a CDP domain"""
        if not self._ws:
            return False
            
        # Check if already enabled
        if domain == "DOM" and self._dom_enabled:
            return True
        if domain == "CSS" and self._css_enabled:
            return True
        if domain == "Accessibility" and self._ax_enabled:
            return True
        if domain == "Runtime" and self._runtime_enabled:
            return True
        if domain == "Page" and self._page_enabled:
            return True
        if domain == "Network" and self._network_enabled:
            return True
            
        if self.verbose:
            print(f"🔧 Enabling domain: {domain}")
            
        try:
            result = self._send_cdp_command(f"{domain}.enable")
            if result and 'error' not in result:
                if self.verbose:
                    print(f"✅ {domain} enabled")
                if domain == "DOM":
                    self._dom_enabled = True
                elif domain == "CSS":
                    self._css_enabled = True
                elif domain == "Accessibility":
                    self._ax_enabled = True
                elif domain == "Runtime":
                    self._runtime_enabled = True
                elif domain == "Page":
                    self._page_enabled = True
                elif domain == "Network":
                    self._network_enabled = True
                return True
            else:
                if self.verbose:
                    print(f"❌ Failed to enable {domain}")
                return False
        except Exception as e:
            if self.verbose:
                print(f"❌ Exception enabling {domain}: {e}")
            return False
    
    # ==================== DOM Domain Methods ====================
    
    def get_document(self, tab_index: int = None, depth: int = -1, 
                     pierce: bool = True) -> Optional[Dict]:
        """Get full DOM tree with node IDs"""
        if self.verbose:
            print("\n📄 DOM.getDocument - Fetching DOM tree...")
            
        if not self._ensure_connection(tab_index):
            return None
            
        try:
            if not self._enable_domain("DOM"):
                return None
                
            params = {"depth": depth, "pierce": pierce}
            result = self._send_cdp_command("DOM.getDocument", params)
            
            if result and 'result' in result:
                root = result['result']['root']
                if self.verbose:
                    print(f"✅ DOM tree retrieved! Root: {root.get('nodeName')} (ID: {root.get('nodeId')})")
                return root
            return None
        except Exception as e:
            if self.verbose:
                print(f"❌ DOM.getDocument error: {e}")
            return None
    
    def get_dom_snapshot(self, tab_index: int = None) -> Optional[LayoutSnapshot]:
        """Capture complete DOM snapshot"""
        if self.verbose:
            print("\n📸 DOMSnapshot.getSnapshot - Capturing snapshot...")
            
        if not self._ensure_connection(tab_index):
            return None
            
        try:
            self._enable_domain("DOM")
            self._enable_domain("CSS")
            
            params = {
                "computedStyleWhitelist": [],
                "includeEventListeners": False,
                "includePaintOrder": False,
                "includeUserAgentShadowTree": True
            }
            result = self._send_cdp_command("DOMSnapshot.getSnapshot", params)
            
            if result and 'result' in result:
                data = result['result']
                if self.verbose:
                    print(f"✅ Snapshot captured!")
                    print(f"   DOM nodes: {len(data.get('domNodes', []))}")
                    print(f"   Layout tree: {len(data.get('layoutTree', []))}")
                return LayoutSnapshot(
                    dom_nodes=data.get('domNodes', []),
                    layout_tree=data.get('layoutTree', []),
                    computed_styles=data.get('computedStyles', [])
                )
            return None
        except Exception as e:
            if self.verbose:
                print(f"❌ DOMSnapshot.getSnapshot error: {e}")
            return None
    
    # ==================== Accessibility Domain Methods ====================
    
    def get_accessibility_tree(self, tab_index: int = None) -> Optional[Dict]:
        """Get accessibility tree with semantic roles"""
        if self.verbose:
            print("\n♿ Accessibility.getFullAXTree - Getting accessibility tree...")
            
        if not self._ensure_connection(tab_index):
            return None
            
        try:
            if not self._enable_domain("Accessibility"):
                return None
                
            result = self._send_cdp_command("Accessibility.getFullAXTree")
            
            if result and 'result' in result:
                nodes = result['result'].get('nodes', [])
                if self.verbose:
                    print(f"✅ Accessibility tree retrieved! Found {len(nodes)} nodes")
                return result['result']
            return None
        except Exception as e:
            if self.verbose:
                print(f"❌ Accessibility.getFullAXTree error: {e}")
            return None
    
    def extract_semantic_elements(self, tab_index: int = None) -> List[Dict]:
        """Extract semantic elements using accessibility tree"""
        ax_tree = self.get_accessibility_tree(tab_index)
        if not ax_tree:
            return []
            
        semantic_elements = []
        for node in ax_tree.get('nodes', []):
            role = node.get('role', {}).get('value', '')
            if role in ['button', 'heading', 'list', 'dialog', 'link', 'textbox', 
                       'checkbox', 'radio', 'navigation', 'main', 'complementary',
                       'banner', 'search', 'form', 'region']:
                name = node.get('name', {}).get('value', '')
                semantic_elements.append({
                    'role': role,
                    'name': name,
                    'node_id': node.get('nodeId'),
                    'backend_node_id': node.get('backendDOMNodeId'),
                    'description': node.get('description', {}).get('value', '')
                })
                
        return semantic_elements
    
    # ==================== CSS Domain Methods ====================
    
    def get_computed_styles(self, tab_index: int = None, 
                           node_id: int = None) -> Optional[List[Dict]]:
        """Get computed styles for a specific node"""
        if self.verbose:
            print("\n🎨 CSS.getComputedStyleForNode - Getting computed styles...")
            
        if not self._ensure_connection(tab_index):
            return None
            
        try:
            self._enable_domain("DOM")
            self._enable_domain("CSS")
            
            # If no node_id provided, find first element
            if node_id is None:
                doc = self.get_document(tab_index)
                if not doc:
                    return None
                node_id = self._find_first_element(doc)
                if not node_id:
                    if self.verbose:
                        print("❌ Could not find any element nodes")
                    return None
                    
            result = self._send_cdp_command("CSS.getComputedStyleForNode", 
                                           {"nodeId": node_id})
            
            if result and 'result' in result:
                styles = result['result'].get('computedStyle', [])
                if self.verbose:
                    print(f"✅ Retrieved {len(styles)} computed styles")
                return styles
            return None
        except Exception as e:
            if self.verbose:
                print(f"❌ CSS.getComputedStyleForNode error: {e}")
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
    
    # ==================== JavaScript/Page Methods ====================
    
    def evaluate_script(self, script: str, tab_index: int = None,
                       return_by_value: bool = True,
                       await_promise: bool = True) -> Optional[Any]:
        """Execute JavaScript in the page context"""
        if self.verbose:
            print("\n⚡ Runtime.evaluate - Executing script...")
            
        if not self._ensure_connection(tab_index):
            return None
            
        try:
            self._enable_domain("Runtime")
            
            params = {
                "expression": script,
                "returnByValue": return_by_value,
                "awaitPromise": await_promise
            }
            result = self._send_cdp_command("Runtime.evaluate", params)
            
            if result and 'result' in result:
                if 'result' in result['result']:
                    value = result['result']['result'].get('value')
                    if self.verbose:
                        print(f"✅ Script executed successfully")
                    return value
                elif 'exceptionDetails' in result['result']:
                    if self.verbose:
                        print(f"⚠️ Script error: {result['result']['exceptionDetails']}")
            return None
        except Exception as e:
            if self.verbose:
                print(f"❌ Runtime.evaluate error: {e}")
            return None
    
    def get_page_info(self, tab_index: int = None) -> Dict:
        """Get page information (URL, title, etc.)"""
        if self.verbose:
            print("\n📄 Getting page info...")
            
        if not self._ensure_connection(tab_index):
            return {}
            
        try:
            self._enable_domain("Page")
            result = self._send_cdp_command("Page.getNavigationHistory")
            
            page_info = {
                'url': '',
                'title': '',
                'timestamp': datetime.now().isoformat()
            }
            
            if result and 'result' in result:
                entries = result['result'].get('entries', [])
                if entries:
                    current = entries[result['result'].get('currentIndex', 0)]
                    page_info['url'] = current.get('url', '')
                    page_info['title'] = current.get('title', '')
                    
            # Fallback to tab info
            if not page_info['url'] and self.tabs:
                tab = self.tabs[tab_index if tab_index is not None else self.current_tab_index]
                page_info['url'] = tab.get('url', '')
                page_info['title'] = tab.get('title', '')
                
            if self.verbose:
                print(f"✅ Page: {page_info['title'][:50]} - {page_info['url'][:50]}")
                
            return page_info
        except Exception as e:
            if self.verbose:
                print(f"❌ Error getting page info: {e}")
            return {}
    
    # ==================== Interactive Element Methods ====================
    
    def find_interactive_elements(self, tab_index: int = None, 
                                  include_hidden: bool = False) -> List[InteractiveElement]:
        """Find all interactive elements on the page"""
        if self.verbose:
            print("\n🔍 Finding interactive elements...")
            
        if not self._ensure_connection(tab_index):
            return []
            
        # Extended selector list
        js_script = """
        (function() {
            const results = [];
            const selectors = [
                'button', 'input[type="button"]', 'input[type="submit"]',
                'input[type="reset"]', 'input[type="file"]',
                'a[href]', '[role="button"]', '[role="link"]',
                '[onclick]', '[data-action]', '[data-testid*="button"]',
                '.btn', '[class*="button"]', '[class*="btn"]',
                'input[type="text"]', 'input[type="email"]', 'input[type="password"]',
                'input[type="number"]', 'input[type="tel"]', 'input[type="checkbox"]',
                'input[type="radio"]', 'input[type="date"]', 'input[type="time"]',
                'select', 'textarea', '[contenteditable="true"]',
                'details', 'summary', '[tabindex]:not([tabindex="-1"])'
            ];
            
            const elements = document.querySelectorAll(selectors.join(','));
            
            elements.forEach((el, index) => {
                const rect = el.getBoundingClientRect();
                const isVisible = rect.width > 0 && rect.height > 0 && 
                                  el.offsetParent !== null;
                
                const attrs = {};
                ['id', 'class', 'data-action', 'data-testid', 'aria-label',
                 'title', 'type', 'value', 'href', 'name', 'role', 
                 'placeholder', 'aria-expanded', 'aria-pressed'].forEach(attr => {
                    if (el.hasAttribute(attr)) {
                        attrs[attr] = el.getAttribute(attr);
                    }
                });
                
                let text = el.textContent.trim();
                if (!text && el.tagName === 'INPUT') {
                    text = el.value || el.getAttribute('placeholder') || '';
                }
                if (!text && el.tagName === 'SELECT') {
                    text = el.options[el.selectedIndex]?.text || '';
                }
                if (!text && el.tagName === 'TEXTAREA') {
                    text = el.value || '';
                }
                
                let type = el.tagName.toLowerCase();
                if (type === 'input') {
                    type = `input[${el.type || 'text'}]`;
                }
                
                // Determine action type
                let action = 'click';
                if (type.startsWith('input') || type === 'textarea') {
                    action = 'input';
                } else if (type === 'select') {
                    action = 'select';
                } else if (type === 'details') {
                    action = 'toggle';
                }
                
                results.push({
                    index: index,
                    tag: el.tagName.toLowerCase(),
                    type: type,
                    action: action,
                    text: text.substring(0, 200),
                    visible: isVisible,
                    attributes: attrs,
                    selector: el.id ? `#${el.id}` : null,
                    boundingRect: {
                        x: rect.x, y: rect.y, 
                        width: rect.width, height: rect.height
                    }
                });
            });
            
            return results;
        })();
        """
        
        result = self.evaluate_script(js_script, tab_index)
        if result and isinstance(result, list):
            elements = []
            for item in result:
                if include_hidden or item.get('visible', False):
                    elements.append(InteractiveElement(**item))
            if self.verbose:
                print(f"✅ Found {len(elements)} interactive elements")
            return elements
        return []
    
    def interact_with_element(self, element_index: int, 
                             action: str = 'click', value: str = None,
                             tab_index: int = None) -> Optional[Dict]:
        """Interact with an element (click, type, select, etc.)"""
        if self.verbose:
            print(f"\n🎯 Interacting with element #{element_index}...")
            
        if not self._ensure_connection(tab_index):
            return None
            
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
                
                return new Promise((resolve) => {{
                    setTimeout(() => {{
                        const event = new MouseEvent('click', {{
                            view: window,
                            bubbles: true,
                            cancelable: true,
                            clientX: el.getBoundingClientRect().x + 10,
                            clientY: el.getBoundingClientRect().y + 10
                        }});
                        el.dispatchEvent(event);
                        if (typeof el.click === 'function') el.click();
                        
                        resolve({{ 
                            success: true, 
                            tag: el.tagName.toLowerCase(),
                            text: el.textContent.trim().substring(0, 100)
                        }});
                    }}, 200);
                }});
            }})();
            """
            result = self.evaluate_script(js_script, tab_index, await_promise=True)
            if result and result.get('success'):
                if self.verbose:
                    print(f"✅ Clicked element successfully")
                return result
            else:
                if self.verbose:
                    print(f"❌ Failed to click element")
                return result
                
        elif action == 'type' and value is not None:
            js_script = f"""
            (function() {{
                const selectors = [
                    'input[type="text"]', 'input[type="email"]',
                    'input[type="password"]', 'input[type="number"]',
                    'input[type="tel"]', 'input[type="url"]',
                    'textarea', '[contenteditable="true"]'
                ];
                
                const elements = document.querySelectorAll(selectors.join(','));
                const el = elements[{element_index}];
                
                if (!el) return {{ error: 'Element not found' }};
                
                el.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                el.focus();
                
                // Clear existing value
                if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') {{
                    el.value = '';
                    el.value = `{value}`;
                }} else {{
                    el.textContent = `{value}`;
                }}
                
                // Dispatch events
                el.dispatchEvent(new Event('focus', {{ bubbles: true }}));
                el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                el.dispatchEvent(new Event('blur', {{ bubbles: true }}));
                
                return {{ 
                    success: true, 
                    value: `{value}`,
                    tag: el.tagName.toLowerCase()
                }};
            }})();
            """
            result = self.evaluate_script(js_script, tab_index)
            if result and result.get('success'):
                if self.verbose:
                    print(f"✅ Typed '{value}' into element")
                return result
            else:
                if self.verbose:
                    print(f"❌ Failed to type into element")
                return result
                
        elif action == 'select' and value is not None:
            js_script = f"""
            (function() {{
                const selectors = ['select'];
                const elements = document.querySelectorAll(selectors.join(','));
                const el = elements[{element_index}];
                
                if (!el) return {{ error: 'Element not found' }};
                
                el.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                
                // Find option by text or value
                let option = Array.from(el.options).find(opt => 
                    opt.text.includes(`{value}`) || opt.value === `{value}`
                );
                
                if (!option) return {{ error: 'Option not found' }};
                
                el.value = option.value;
                el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                
                return {{ 
                    success: true, 
                    selected: option.text,
                    value: option.value
                }};
            }})();
            """
            result = self.evaluate_script(js_script, tab_index)
            if result and result.get('success'):
                if self.verbose:
                    print(f"✅ Selected '{result.get('selected')}'")
                return result
            else:
                if self.verbose:
                    print(f"❌ Failed to select option")
                return result
                
        elif action == 'hover':
            js_script = f"""
            (function() {{
                const selectors = [
                    'button', 'a', '[role="button"]', '[role="link"]',
                    '.btn', '[class*="button"]', '*[data-hover]'
                ];
                
                const elements = document.querySelectorAll(selectors.join(','));
                const el = elements[{element_index}];
                
                if (!el) return {{ error: 'Element not found' }};
                
                el.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                
                const event = new MouseEvent('mouseenter', {{
                    view: window,
                    bubbles: true,
                    cancelable: true
                }});
                el.dispatchEvent(event);
                
                // Also trigger hover effect
                el.dispatchEvent(new MouseEvent('mouseover', {{
                    view: window,
                    bubbles: true,
                    cancelable: true
                }}));
                
                return {{ success: true, tag: el.tagName.toLowerCase() }};
            }})();
            """
            result = self.evaluate_script(js_script, tab_index)
            if result and result.get('success'):
                if self.verbose:
                    print(f"✅ Hovered over element")
                return result
            else:
                if self.verbose:
                    print(f"❌ Failed to hover")
                return result
        
        return None
    
    def interactive_element_explorer(self, tab_index: int = None):
        """Interactive CLI for exploring and interacting with elements"""
        print("\n🎯 Interactive Elements Explorer")
        print("=" * 70)
        
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
            print("=" * 80)
            for i in range(start, end):
                elem = elements[i]
                text = elem.text[:50]
                tag = elem.tag
                visible = "👁️" if elem.visible else "🚫"
                action = elem.attributes.get('type', elem.action)
                print(f"  [{i:2d}] {visible} {tag:12s} [{action:8s}]: {text}")
                
            print("\n📌 Commands:")
            print("  [n] Next page  [p] Previous page  [q] Quit")
            print("  [index] Click element")
            print("  [type index text] Type text into element")
            print("  [select index value] Select option from dropdown")
            print("  [hover index] Hover over element")
            print("  [info index] Show element details")
            print("  [find text] Search for text in elements")
            
            cmd = input("\n▶ Enter command: ").strip()
            
            if cmd.lower() == 'q':
                break
            elif cmd.lower() == 'n' and current_page < total_pages - 1:
                current_page += 1
            elif cmd.lower() == 'p' and current_page > 0:
                current_page -= 1
            elif cmd.startswith('find '):
                search_text = cmd[5:].strip().lower()
                found = [e for e in elements if search_text in e.text.lower()]
                if found:
                    print(f"✅ Found {len(found)} matching elements:")
                    for e in found[:10]:
                        print(f"  [{e.index}] {e.tag}: {e.text[:50]}")
                else:
                    print("❌ No matches found")
            elif cmd.startswith('type '):
                parts = cmd.split(' ', 2)
                if len(parts) == 3:
                    try:
                        idx = int(parts[1])
                        text = parts[2]
                        if 0 <= idx < len(elements):
                            self.interact_with_element(idx, 'type', text, tab_index)
                        else:
                            print("❌ Invalid index")
                    except ValueError:
                        print("❌ Invalid index format")
                else:
                    print("❌ Usage: type <index> <text>")
            elif cmd.startswith('select '):
                parts = cmd.split(' ', 2)
                if len(parts) == 3:
                    try:
                        idx = int(parts[1])
                        value = parts[2]
                        if 0 <= idx < len(elements):
                            self.interact_with_element(idx, 'select', value, tab_index)
                        else:
                            print("❌ Invalid index")
                    except ValueError:
                        print("❌ Invalid index format")
                else:
                    print("❌ Usage: select <index> <value>")
            elif cmd.startswith('hover '):
                parts = cmd.split(' ', 1)
                if len(parts) == 2:
                    try:
                        idx = int(parts[1])
                        if 0 <= idx < len(elements):
                            self.interact_with_element(idx, 'hover', None, tab_index)
                        else:
                            print("❌ Invalid index")
                    except ValueError:
                        print("❌ Invalid index format")
                else:
                    print("❌ Usage: hover <index>")
            elif cmd.startswith('info '):
                parts = cmd.split(' ', 1)
                if len(parts) == 2:
                    try:
                        idx = int(parts[1])
                        if 0 <= idx < len(elements):
                            elem = elements[idx]
                            print(f"\n📋 Element Details:")
                            print(f"  Index: {elem.index}")
                            print(f"  Tag: {elem.tag}")
                            print(f"  Type: {elem.type}")
                            print(f"  Action: {elem.action}")
                            print(f"  Visible: {elem.visible}")
                            print(f"  Text: {elem.text}")
                            print(f"  Attributes: {json.dumps(elem.attributes, indent=2)}")
                            print(f"  Bounding Rect: {elem.bounding_rect}")
                        else:
                            print("❌ Invalid index")
                    except ValueError:
                        print("❌ Invalid index format")
                else:
                    print("❌ Usage: info <index>")
            elif cmd.isdigit():
                idx = int(cmd)
                if 0 <= idx < len(elements):
                    self.interact_with_element(idx, 'click', None, tab_index)
                else:
                    print("❌ Invalid index")
            else:
                print("❌ Invalid command")
    
    # ==================== Analysis Methods ====================
    
    def analyze_page_structure(self, tab_index: int = None) -> Dict:
        """Comprehensive page analysis using all domains"""
        if self.verbose:
            print("\n🔬 Performing complete page analysis...")
            
        result = {
            "timestamp": datetime.now().isoformat(),
            "metadata": {}
        }
        
        # Get page info
        page_info = self.get_page_info(tab_index)
        result.update(page_info)
        
        # DOM Tree
        dom_root = self.get_document(tab_index)
        if dom_root:
            result["dom_tree"] = dom_root
            result["metadata"]["node_count"] = self._count_nodes(dom_root)
            
        # Snapshot
        snapshot = self.get_dom_snapshot(tab_index)
        if snapshot:
            result["snapshot"] = snapshot
            result["metadata"]["layout_count"] = len(snapshot.layout_tree)
            
        # Accessibility
        ax_tree = self.get_accessibility_tree(tab_index)
        if ax_tree:
            result["accessibility"] = ax_tree
            result["metadata"]["ax_nodes"] = len(ax_tree.get('nodes', []))
            
        # Interactive Elements
        elements = self.find_interactive_elements(tab_index, include_hidden=False)
        result["interactive_elements"] = [asdict(e) for e in elements]
        result["metadata"]["interactive_count"] = len(elements)
        
        # Semantic Elements
        semantic = self.extract_semantic_elements(tab_index)
        result["semantic_elements"] = semantic
        result["metadata"]["semantic_count"] = len(semantic)
        
        if self.verbose:
            print(f"\n✅ Analysis complete!")
            print(f"   Total nodes: {result['metadata'].get('node_count', 0)}")
            print(f"   Interactive elements: {len(elements)}")
            print(f"   Semantic elements: {len(semantic)}")
            
        return result
    
    def _count_nodes(self, node: Dict) -> int:
        """Count total nodes in DOM tree"""
        count = 1
        for child in node.get('children', []):
            count += self._count_nodes(child)
        return count
    
    # ==================== Utility Methods ====================
    
    def list_tabs(self, show_details: bool = False):
        """Display all available tabs"""
        self.get_tabs()
        
        if not self.tabs:
            print("❌ No tabs found")
            return
            
        print("\n📑 Available Tabs:")
        print("=" * 80)
        for i, tab in enumerate(self.tabs):
            title = tab.get('title', 'Untitled')[:60]
            url = tab.get('url', '')[:60]
            print(f"  [{i}] {title}")
            print(f"      URL: {url}")
            if show_details:
                ws = tab.get('webSocketDebuggerUrl', '')
                if ws:
                    print(f"      WS: {ws[:70]}...")
            print()
    
    def save_to_file(self, data: Any, prefix: str = "output"):
        """Save data to a JSON file with timestamp"""
        filename = f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        print(f"✅ Saved to {filename}")
        return filename
    
    def set_verbose(self, verbose: bool):
        """Set verbose mode"""
        self.verbose = verbose
    
    def change_tab(self, tab_index: int) -> bool:
        """Change to a different tab"""
        self._close_websocket()
        self.ws_url = None
        if self.get_websocket_url(tab_index):
            self.current_tab_index = tab_index
            return True
        return False
    
    def reset(self):
        """Reset connection state"""
        self._close_websocket()
        self.ws_url = None
        self._dom_enabled = False
        self._css_enabled = False
        self._ax_enabled = False
        self._runtime_enabled = False
        self._page_enabled = False
        self._network_enabled = False

# ==================== Main Interactive Shell ====================

def main():
    print("🚀 ULTIMATE Chrome CDP Controller")
    print("=" * 70)
    print("✨ Features: DOM | Accessibility | CSS | JavaScript | Automation")
    print("🎯 Interactive Elements | Complete Analysis | Debug Mode")
    print("=" * 70)
    
    # Get port
    port_input = input("🔌 Chrome debug port (default 9227): ").strip()
    port = int(port_input) if port_input else 9227
    
    # Get verbose mode
    verbose_input = input("🔊 Verbose mode? (y/n, default y): ").strip().lower()
    verbose = verbose_input != 'n'
    
    chrome = UltimateChromeCDP(port, verbose)
    
    print(f"\n📡 Connecting to Chrome on port {port}...")
    tabs = chrome.get_tabs()
    
    if not tabs:
        print("❌ No tabs found. Make sure Chrome is running with:")
        print(f"   chromium-browser --remote-debugging-port={port}")
        print("   OR")
        print(f"   google-chrome --remote-debugging-port={port}")
        return
    
    print(f"✅ Found {len(tabs)} tabs")
    chrome.list_tabs()
    
    tab_input = input(f"\n📑 Select tab (0-{len(tabs)-1}, default 0): ").strip()
    tab_index = int(tab_input) if tab_input else 0
    
    if not chrome.change_tab(tab_index):
        print("❌ Failed to select tab")
        return
        
    print(f"✅ Using tab {tab_index}")
    
    # Main loop
    while True:
        print("\n" + "=" * 70)
        print("📝 ULTIMATE CDP Commands:")
        print("  🔍 EXPLORATION:")
        print("   1. Get DOM Tree")
        print("   2. Get DOM Snapshot")
        print("   3. Get Accessibility Tree")
        print("   4. Get Computed Styles")
        print("   5. Extract Semantic Elements")
        print("  🎮 INTERACTION:")
        print("   6. Execute JavaScript")
        print("   7. Find Interactive Elements")
        print("   8. Interactive Element Explorer 🎯")
        print("   9. Quick Action (click/type/select)")
        print("  📊 ANALYSIS:")
        print("  10. Complete Page Analysis")
        print("  11. Page Info")
        print("  📁 TABS:")
        print("  12. List Tabs")
        print("  13. Change Tab")
        print("  ⚙️ SETTINGS:")
        print("  14. Toggle Verbose Mode")
        print("  15. Reset Connection")
        print("  0. Exit")
        print("=" * 70)
        
        choice = input("Select option: ").strip()
        
        if choice == "0":
            print("👋 Goodbye!")
            break
            
        elif choice == "1":
            dom_root = chrome.get_document()
            if dom_root:
                node_count = chrome._count_nodes(dom_root)
                print(f"\n📊 DOM Statistics:")
                print(f"   Total nodes: {node_count}")
                print(f"   Root node: {dom_root.get('nodeName')} (ID: {dom_root.get('nodeId')})")
                
                save = input("\n💾 Save DOM tree to file? (y/n): ").strip().lower()
                if save == 'y':
                    chrome.save_to_file(dom_root, "dom_tree")
            else:
                print("❌ Failed to get DOM tree")
                
        elif choice == "2":
            snapshot = chrome.get_dom_snapshot()
            if snapshot:
                print(f"\n📊 Snapshot Statistics:")
                print(f"   DOM nodes: {len(snapshot.dom_nodes)}")
                print(f"   Layout tree: {len(snapshot.layout_tree)}")
                print(f"   Computed styles: {len(snapshot.computed_styles)}")
                
                save = input("\n💾 Save snapshot to file? (y/n): ").strip().lower()
                if save == 'y':
                    chrome.save_to_file(snapshot.to_dict(), "snapshot")
            else:
                print("❌ Failed to capture snapshot")
                
        elif choice == "3":
            ax_tree = chrome.get_accessibility_tree()
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
                    chrome.save_to_file(ax_tree, "ax_tree")
            else:
                print("❌ Failed to get accessibility tree")
                
        elif choice == "4":
            styles = chrome.get_computed_styles()
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
                
        elif choice == "5":
            elements = chrome.extract_semantic_elements()
            if elements:
                print(f"✅ Found {len(elements)} semantic elements:")
                for elem in elements[:20]:
                    name = elem['name'][:50] if elem['name'] else '(unnamed)'
                    desc = elem.get('description', '')[:30]
                    print(f"   [{elem['role']}] {name}")
                    if desc:
                        print(f"      Description: {desc}")
                if len(elements) > 20:
                    print(f"   ... and {len(elements)-20} more")
                    
                save = input("\n💾 Save semantic elements to file? (y/n): ").strip().lower()
                if save == 'y':
                    chrome.save_to_file(elements, "semantic_elements")
            else:
                print("❌ No semantic elements found")
                
        elif choice == "6":
            print("\n📝 Enter JavaScript (type 'END' on a new line when done):")
            lines = []
            while True:
                line = input()
                if line.strip() == "END":
                    break
                lines.append(line)
            script = "\n".join(lines)
            
            if script:
                result = chrome.evaluate_script(script)
                if result is not None:
                    print(f"\n✅ Result: {json.dumps(result, indent=2, default=str)[:3000]}")
                else:
                    print("\n❌ No result returned")
                    
        elif choice == "7":
            elements = chrome.find_interactive_elements()
            if elements:
                print(f"\n📋 Interactive Elements ({len(elements)} found):")
                print("=" * 80)
                for elem in elements[:20]:
                    text = elem.text[:40]
                    visible = "👁️" if elem.visible else "🚫"
                    print(f"  [{elem.index:2d}] {visible} {elem.tag:12s}: {text}")
                if len(elements) > 20:
                    print(f"  ... and {len(elements)-20} more")
                    
                save = input("\n💾 Save elements to file? (y/n): ").strip().lower()
                if save == 'y':
                    chrome.save_to_file([asdict(e) for e in elements], "interactive_elements")
            else:
                print("❌ No interactive elements found")
                
        elif choice == "8":
            chrome.interactive_element_explorer()
            
        elif choice == "9":
            print("\n🎯 Quick Action:")
            print("  Click element: click <index>")
            print("  Type text: type <index> <text>")
            print("  Select option: select <index> <value>")
            print("  Hover: hover <index>")
            
            cmd = input("\n▶ Enter quick action: ").strip()
            if not cmd:
                continue
                
            parts = cmd.split(' ', 2)
            action = parts[0].lower()
            
            if action == 'click' and len(parts) >= 2:
                try:
                    idx = int(parts[1])
                    chrome.interact_with_element(idx, 'click')
                except ValueError:
                    print("❌ Invalid index")
                    
            elif action == 'type' and len(parts) == 3:
                try:
                    idx = int(parts[1])
                    text = parts[2]
                    chrome.interact_with_element(idx, 'type', text)
                except ValueError:
                    print("❌ Invalid index")
                    
            elif action == 'select' and len(parts) == 3:
                try:
                    idx = int(parts[1])
                    value = parts[2]
                    chrome.interact_with_element(idx, 'select', value)
                except ValueError:
                    print("❌ Invalid index")
                    
            elif action == 'hover' and len(parts) >= 2:
                try:
                    idx = int(parts[1])
                    chrome.interact_with_element(idx, 'hover')
                except ValueError:
                    print("❌ Invalid index")
            else:
                print("❌ Invalid action format")
                
        elif choice == "10":
            analysis = chrome.analyze_page_structure()
            print(f"\n📊 Analysis Summary:")
            for key, value in analysis.get('metadata', {}).items():
                print(f"   {key}: {value}")
                
            save = input("\n💾 Save complete analysis to file? (y/n): ").strip().lower()
            if save == 'y':
                chrome.save_to_file(analysis, "page_analysis")
                
        elif choice == "11":
            info = chrome.get_page_info()
            print(f"\n📄 Page Information:")
            print(f"   Title: {info.get('title', 'N/A')}")
            print(f"   URL: {info.get('url', 'N/A')}")
            print(f"   Timestamp: {info.get('timestamp', 'N/A')}")
            
        elif choice == "12":
            chrome.list_tabs(show_details=True)
            
        elif choice == "13":
            chrome.reset()
            tabs = chrome.get_tabs()
            chrome.list_tabs()
            tab_input = input(f"\n📑 Select tab (0-{len(chrome.tabs)-1}): ").strip()
            if tab_input:
                try:
                    new_tab = int(tab_input)
                    if chrome.change_tab(new_tab):
                        print(f"✅ Switched to tab {new_tab}")
                    else:
                        print("❌ Failed to switch tab")
                except ValueError:
                    print("❌ Invalid tab index")
                    
        elif choice == "14":
            current = "ON" if chrome.verbose else "OFF"
            toggle = input(f"Verbose mode is {current}. Toggle? (y/n): ").strip().lower()
            if toggle == 'y':
                chrome.set_verbose(not chrome.verbose)
                print(f"✅ Verbose mode: {'ON' if chrome.verbose else 'OFF'}")
                
        elif choice == "15":
            chrome.reset()
            print("✅ Connection reset")
            
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
        sys.exit(1)
