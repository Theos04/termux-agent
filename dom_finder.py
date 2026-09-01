#!/usr/bin/env python3
"""
dom_finder.py - Standalone DOM element finder

A clean, self-contained library for finding and analyzing DOM elements
using Chrome DevTools Protocol (CDP).

Usage:
    from dom_finder import DOMFinder, find_element, find_elements
    
    # Quick find
    element = find_element("#login-btn", port=9227)
    
    # Or use the full API
    finder = DOMFinder(port=9227)
    finder.connect()
    
    # Find by various methods
    buttons = finder.find_by_selector("button")
    login_btn = finder.find_by_text("Login")
    form = finder.find_form_for_action("/api/login")
    
    # Get element info
    info = finder.get_element_info(login_btn)
    
    # Interact
    finder.click(login_btn)
    finder.fill("#email", "user@example.com")
    
    finder.close()
"""

import json
import re
import time
from typing import Dict, List, Optional, Any, Union, Callable
from dataclasses import dataclass, field
from enum import Enum
from urllib.parse import urlparse
import websocket
import requests


# ============================================================================
# Models
# ============================================================================

class ElementType(Enum):
    """Types of DOM elements"""
    BUTTON = "button"
    LINK = "link"
    INPUT = "input"
    SELECT = "select"
    TEXTAREA = "textarea"
    CHECKBOX = "checkbox"
    RADIO = "radio"
    SUBMIT = "submit"
    IMAGE = "image"
    FORM = "form"
    MODAL = "modal"
    DROPDOWN = "dropdown"
    NAV = "nav"
    HEADER = "header"
    SECTION = "section"
    TABLE = "table"
    LIST = "list"


@dataclass
class DOMElement:
    """Rich DOM element representation"""
    node_id: int = 0
    tag_name: str = ""
    text: str = ""
    attributes: Dict[str, str] = field(default_factory=dict)
    selector: str = ""
    xpath: str = ""
    is_visible: bool = True
    is_interactive: bool = False
    is_form_element: bool = False
    confidence: float = 1.0
    bounding_box: Optional[Dict] = None
    parent_id: Optional[int] = None
    children: List[int] = field(default_factory=list)
    
    @property
    def id(self) -> str:
        return self.attributes.get('id', '')
    
    @property
    def classes(self) -> List[str]:
        return self.attributes.get('class', '').split()
    
    @property
    def type(self) -> str:
        return self.attributes.get('type', '').lower()
    
    @property
    def href(self) -> str:
        return self.attributes.get('href', '')
    
    @property
    def value(self) -> str:
        return self.attributes.get('value', '')
    
    @property
    def placeholder(self) -> str:
        return self.attributes.get('placeholder', '')
    
    @property
    def name(self) -> str:
        return self.attributes.get('name', '')
    
    def to_dict(self) -> Dict:
        return {
            "node_id": self.node_id,
            "tag": self.tag_name,
            "text": self.text[:200],
            "attributes": self.attributes,
            "selector": self.selector,
            "xpath": self.xpath,
            "visible": self.is_visible,
            "interactive": self.is_interactive,
            "form_element": self.is_form_element,
            "confidence": self.confidence
        }
    
    def __repr__(self) -> str:
        return f"<DOMElement {self.tag_name} '{self.text[:30]}'>"


# ============================================================================
# CDP Connection
# ============================================================================

class CDPConnection:
    """Manages WebSocket connection to Chrome DevTools"""
    
    def __init__(self, port: int = 9222, host: str = "127.0.0.1"):
        self.port = port
        self.host = host
        self.ws = None
        self._message_id = 0
        self._pending = {}
        self._connected = False
        self._event_handlers = {}
        
    def connect(self, tab_id: Optional[str] = None) -> bool:
        """Connect to Chrome DevTools"""
        try:
            # Get list of tabs
            response = requests.get(f"http://{self.host}:{self.port}/json")
            if response.status_code != 200:
                return False
                
            tabs = response.json()
            if not tabs:
                return False
            
            # Use specified tab or first available
            if tab_id:
                tab = next((t for t in tabs if t.get('id') == tab_id), None)
            else:
                tab = tabs[0]
            
            if not tab:
                return False
            
            ws_url = tab.get('webSocketDebuggerUrl')
            if not ws_url:
                return False
            
            # Connect WebSocket
            self.ws = websocket.create_connection(ws_url, timeout=10)
            self._connected = True
            
            # Enable required domains
            self._send_command("Page.enable")
            self._send_command("DOM.enable")
            self._send_command("Runtime.enable")
            
            return True
            
        except Exception as e:
            self._connected = False
            return False
    
    def _send_command(self, method: str, params: Dict = None) -> Dict:
        """Send CDP command and wait for response"""
        if not self._connected:
            raise RuntimeError("Not connected to Chrome")
            
        self._message_id += 1
        msg_id = self._message_id
        
        message = {
            "id": msg_id,
            "method": method,
            "params": params or {}
        }
        
        self.ws.send(json.dumps(message))
        
        # Wait for response
        while True:
            response = json.loads(self.ws.recv())
            if response.get("id") == msg_id:
                return response.get("result", {})
            elif "method" in response:
                # Handle event
                self._handle_event(response)
    
    def _handle_event(self, event: Dict):
        """Handle CDP events"""
        method = event.get("method")
        if method in self._event_handlers:
            self._event_handlers[method](event.get("params", {}))
    
    def on(self, event: str, handler: Callable):
        """Register event handler"""
        self._event_handlers[event] = handler
    
    def execute_js(self, script: str, await_promise: bool = True) -> Any:
        """Execute JavaScript and return result"""
        params = {
            "expression": script,
            "returnByValue": True,
            "awaitPromise": await_promise
        }
        result = self._send_command("Runtime.evaluate", params)
        
        if "result" in result:
            return result["result"].get("value")
        return None
    
    def close(self):
        """Close connection"""
        if self.ws:
            self.ws.close()
        self._connected = False


# ============================================================================
# Main DOM Finder
# ============================================================================

class DOMFinder:
    """
    Standalone DOM element finder using CDP
    
    Examples:
        # Basic usage
        finder = DOMFinder()
        finder.connect()
        
        # Find elements
        elements = finder.find("button")  # All buttons
        login = finder.find_by_text("Login")[0]  # Find by text
        
        # Get info and interact
        info = finder.get_info(login)
        finder.click(login)
        
        # Form handling
        form = finder.find_form_for_action("/api/login")
        if form:
            finder.fill_form(form, {"email": "test@example.com", "password": "pass"})
        
        finder.close()
    """
    
    def __init__(self, port: int = 9222, host: str = "127.0.0.1", tab_id: Optional[str] = None):
        """
        Initialize DOM finder
        
        Args:
            port: Chrome DevTools port (default: 9222)
            host: Chrome host (default: localhost)
            tab_id: Specific tab to connect to (optional)
        """
        self.cdp = CDPConnection(port=port, host=host)
        self.tab_id = tab_id
        self._connected = False
        self._cache = {}
        
    def connect(self) -> bool:
        """Connect to Chrome"""
        self._connected = self.cdp.connect(self.tab_id)
        return self._connected
    
    def is_connected(self) -> bool:
        """Check if connected"""
        return self._connected
    
    def close(self):
        """Close connection"""
        self.cdp.close()
        self._connected = False
    
    # ========================================================================
    # Find Methods
    # ========================================================================
    
    def find(self, selector: str, max_results: int = 50) -> List[DOMElement]:
        """
        Find elements by CSS selector
        
        Args:
            selector: CSS selector (e.g., "#id", ".class", "button")
            max_results: Maximum results to return
            
        Returns:
            List of DOMElement objects
        """
        if not selector or not self._connected:
            return []
            
        script = f"""
        () => {{
            const elements = document.querySelectorAll(`{selector}`);
            const results = [];
            for (const el of elements.slice(0, {max_results})) {{
                const rect = el.getBoundingClientRect();
                results.push({{
                    tag: el.tagName,
                    text: el.textContent?.trim() || '',
                    attributes: Array.from(el.attributes).reduce((acc, attr) => {{
                        acc[attr.name] = attr.value;
                        return acc;
                    }}, {{}}),
                    visible: el.offsetParent !== null,
                    interactive: el.tagName === 'BUTTON' || el.tagName === 'A' || 
                                 (el.onclick !== null) || el.getAttribute('role') === 'button',
                    boundingBox: {{
                        x: rect.x, y: rect.y, width: rect.width, height: rect.height
                    }}
                }});
            }}
            return results;
        }}
        """
        
        result = self.cdp.execute_js(script)
        return [self._dict_to_element(el) for el in (result or [])]
    
    def find_by_text(self, text: str, partial: bool = True, 
                     case_sensitive: bool = False, max_results: int = 20) -> List[DOMElement]:
        """
        Find elements by text content
        
        Args:
            text: Text to search for
            partial: Allow partial matches
            case_sensitive: Case sensitive search
            max_results: Maximum results
            
        Returns:
            List of DOMElement objects
        """
        if not text or not self._connected:
            return []
            
        search_text = text if case_sensitive else text.lower()
        
        script = f"""
        () => {{
            const searchText = `{search_text}`;
            const partial = {str(partial).lower()};
            const caseSensitive = {str(case_sensitive).lower()};
            
            const xpath = partial ?
                `//*[contains(text(), '${{searchText}}')]` :
                `//*[text()='${{searchText}}']`;
            
            const result = document.evaluate(
                xpath,
                document,
                null,
                XPathResult.ORDERED_NODE_SNAPSHOT_TYPE,
                null
            );
            
            const elements = [];
            for (let i = 0; i < Math.min(result.snapshotLength, {max_results}); i++) {{
                const el = result.snapshotItem(i);
                const rect = el.getBoundingClientRect();
                elements.push({{
                    tag: el.tagName,
                    text: el.textContent?.trim() || '',
                    attributes: Array.from(el.attributes).reduce((acc, attr) => {{
                        acc[attr.name] = attr.value;
                        return acc;
                    }}, {{}}),
                    visible: el.offsetParent !== null,
                    interactive: el.tagName === 'BUTTON' || el.tagName === 'A' || 
                                 (el.onclick !== null) || el.getAttribute('role') === 'button',
                    boundingBox: {{
                        x: rect.x, y: rect.y, width: rect.width, height: rect.height
                    }}
                }});
            }}
            return elements;
        }}
        """
        
        result = self.cdp.execute_js(script)
        return [self._dict_to_element(el) for el in (result or [])]
    
    def find_by_xpath(self, xpath: str, max_results: int = 20) -> List[DOMElement]:
        """
        Find elements by XPath
        
        Args:
            xpath: XPath expression
            max_results: Maximum results
            
        Returns:
            List of DOMElement objects
        """
        if not xpath or not self._connected:
            return []
            
        script = f"""
        () => {{
            const result = document.evaluate(
                `{xpath}`,
                document,
                null,
                XPathResult.ORDERED_NODE_SNAPSHOT_TYPE,
                null
            );
            
            const elements = [];
            for (let i = 0; i < Math.min(result.snapshotLength, {max_results}); i++) {{
                const el = result.snapshotItem(i);
                if (el && el.nodeType === 1) {{
                    const rect = el.getBoundingClientRect();
                    elements.push({{
                        tag: el.tagName,
                        text: el.textContent?.trim() || '',
                        attributes: Array.from(el.attributes).reduce((acc, attr) => {{
                            acc[attr.name] = attr.value;
                            return acc;
                        }}, {{}}),
                        visible: el.offsetParent !== null,
                        interactive: el.tagName === 'BUTTON' || el.tagName === 'A' || 
                                     (el.onclick !== null) || el.getAttribute('role') === 'button',
                        boundingBox: {{
                            x: rect.x, y: rect.y, width: rect.width, height: rect.height
                        }}
                    }});
                }}
            }}
            return elements;
        }}
        """
        
        result = self.cdp.execute_js(script)
        return [self._dict_to_element(el) for el in (result or [])]
    
    def find_by_type(self, element_type: ElementType, max_results: int = 30) -> List[DOMElement]:
        """
        Find elements by semantic type
        
        Args:
            element_type: ElementType enum value
            max_results: Maximum results
            
        Returns:
            List of DOMElement objects
        """
        selectors = {
            ElementType.BUTTON: 'button, [role="button"], input[type="button"], input[type="submit"]',
            ElementType.LINK: 'a[href]',
            ElementType.INPUT: 'input:not([type="hidden"])',
            ElementType.SELECT: 'select',
            ElementType.TEXTAREA: 'textarea',
            ElementType.CHECKBOX: 'input[type="checkbox"]',
            ElementType.RADIO: 'input[type="radio"]',
            ElementType.SUBMIT: 'input[type="submit"], button[type="submit"]',
            ElementType.IMAGE: 'img',
            ElementType.FORM: 'form',
            ElementType.TABLE: 'table',
            ElementType.HEADER: 'header, h1, h2, h3, h4, h5, h6',
            ElementType.NAV: 'nav',
            ElementType.SECTION: 'section',
            ElementType.MODAL: '[role="dialog"], .modal, .popup',
            ElementType.DROPDOWN: 'select, [role="listbox"], .dropdown'
        }
        
        selector = selectors.get(element_type)
        if not selector:
            return []
            
        return self.find(selector, max_results)
    
    def find_by_attribute(self, attr_name: str, attr_value: Optional[str] = None,
                          partial: bool = False, max_results: int = 20) -> List[DOMElement]:
        """
        Find elements by attribute
        
        Args:
            attr_name: Attribute name (e.g., "data-testid")
            attr_value: Attribute value (optional)
            partial: Allow partial value match
            max_results: Maximum results
            
        Returns:
            List of DOMElement objects
        """
        if not attr_name or not self._connected:
            return []
            
        if attr_value:
            selector = f'[{attr_name}]' if partial else f'[{attr_name}="{attr_value}"]'
            elements = self.find(selector, max_results)
            if partial:
                # Filter for partial match
                val_lower = attr_value.lower()
                elements = [e for e in elements if val_lower in e.attributes.get(attr_name, '').lower()]
            return elements
        else:
            # Find all elements with this attribute
            script = f"""
            () => {{
                const elements = document.querySelectorAll('[{attr_name}]');
                const results = [];
                for (const el of elements.slice(0, {max_results})) {{
                    const rect = el.getBoundingClientRect();
                    results.push({{
                        tag: el.tagName,
                        text: el.textContent?.trim() || '',
                        attributes: Array.from(el.attributes).reduce((acc, attr) => {{
                            acc[attr.name] = attr.value;
                            return acc;
                        }}, {{}}),
                        visible: el.offsetParent !== null,
                        interactive: el.tagName === 'BUTTON' || el.tagName === 'A' || 
                                     (el.onclick !== null) || el.getAttribute('role') === 'button',
                        boundingBox: {{
                            x: rect.x, y: rect.y, width: rect.width, height: rect.height
                        }}
                    }});
                }}
                return results;
            }}
            """
            result = self.cdp.execute_js(script)
            return [self._dict_to_element(el) for el in (result or [])]
    
    def find_interactive(self, max_results: int = 50) -> List[DOMElement]:
        """
        Find all interactive elements on the page
        
        Returns:
            List of DOMElement objects
        """
        return self.find("button, a[href], input:not([type=\"hidden\"]), select, textarea, [role=\"button\"], [onclick]", max_results)
    
    def find_forms(self) -> List[Dict]:
        """
        Find all forms on the page with their inputs
        
        Returns:
            List of form objects with form data and inputs
        """
        if not self._connected:
            return []
            
        script = """
        () => {
            const forms = document.querySelectorAll('form');
            return Array.from(forms).map(form => {
                const inputs = form.querySelectorAll('input, select, textarea');
                return {
                    id: form.id || '',
                    action: form.action || '',
                    method: form.method || 'GET',
                    selector: form.id ? `#${form.id}` : 'form',
                    inputs: Array.from(inputs).map(el => ({
                        name: el.name || '',
                        type: el.type || el.tagName,
                        value: el.value || '',
                        required: el.required || false,
                        placeholder: el.placeholder || '',
                        selector: el.id ? `#${el.id}` : 
                                  el.name ? `[name="${el.name}"]` : 
                                  el.tagName
                    }))
                };
            });
        }
        """
        return self.cdp.execute_js(script) or []
    
    def find_form_for_action(self, action_pattern: str) -> Optional[Dict]:
        """
        Find a form that submits to a specific action
        
        Args:
            action_pattern: Pattern to match in form action
            
        Returns:
            Form data with inputs, or None if not found
        """
        if not action_pattern or not self._connected:
            return None
            
        script = f"""
        () => {{
            const pattern = `{action_pattern}`;
            const forms = document.querySelectorAll('form');
            
            for (const form of forms) {{
                const action = form.action || '';
                if (action.includes(pattern)) {{
                    const inputs = form.querySelectorAll('input, select, textarea');
                    return {{
                        id: form.id || '',
                        action: action,
                        method: form.method || 'GET',
                        selector: form.id ? `#${{form.id}}` : 'form',
                        inputs: Array.from(inputs).map(el => ({{
                            name: el.name || '',
                            type: el.type || el.tagName,
                            value: el.value || '',
                            required: el.required || false,
                            placeholder: el.placeholder || '',
                            selector: el.id ? `#${{el.id}}` : 
                                      el.name ? `[name="${{el.name}}"]` : 
                                      el.tagName
                        }}))
                    }};
                }}
            }}
            return null;
        }}
        """
        return self.cdp.execute_js(script)
    
    # ========================================================================
    # Element Information
    # ========================================================================
    
    def get_info(self, element: DOMElement) -> Dict:
        """
        Get detailed information about an element
        
        Args:
            element: DOMElement object
            
        Returns:
            Dictionary with detailed element information
        """
        info = {
            "tag": element.tag_name,
            "text": element.text,
            "attributes": element.attributes,
            "selector": element.selector,
            "visible": element.is_visible,
            "interactive": element.is_interactive,
            "form_element": element.is_form_element,
            "bbox": element.bounding_box
        }
        
        # Add specific info based on tag
        tag = element.tag_name.lower()
        if tag == 'a':
            info['href'] = element.href
            info['target'] = element.attributes.get('target', '')
        elif tag == 'input':
            info['type'] = element.type
            info['value'] = element.value
            info['placeholder'] = element.placeholder
            info['name'] = element.name
            info['checked'] = element.attributes.get('checked', False)
        elif tag == 'select':
            info['options'] = self._get_select_options(element)
        elif tag == 'img':
            info['src'] = element.attributes.get('src', '')
            info['alt'] = element.attributes.get('alt', '')
        elif tag == 'form':
            info['action'] = element.attributes.get('action', '')
            info['method'] = element.attributes.get('method', 'GET')
            info['form_data'] = self.find_form_for_action(element.attributes.get('action', ''))
        
        return info
    
    def _get_select_options(self, element: DOMElement) -> List[Dict]:
        """Get options from a select element"""
        if not self._connected or not element.selector:
            return []
            
        script = f"""
        () => {{
            const el = document.querySelector('{element.selector}');
            if (!el || el.tagName !== 'SELECT') return [];
            return Array.from(el.options).map(opt => ({{
                value: opt.value,
                text: opt.text,
                selected: opt.selected
            }}));
        }}
        """
        return self.cdp.execute_js(script) or []
    
    # ========================================================================
    # Interaction Methods
    # ========================================================================
    
    def click(self, element_or_selector: Union[DOMElement, str]) -> bool:
        """
        Click an element
        
        Args:
            element_or_selector: DOMElement or CSS selector
            
        Returns:
            True if clicked successfully
        """
        if not self._connected:
            return False
            
        selector = element_or_selector.selector if isinstance(element_or_selector, DOMElement) else element_or_selector
        
        if not selector:
            return False
            
        script = f"""
        () => {{
            const el = document.querySelector(`{selector}`);
            if (!el) return false;
            el.click();
            return true;
        }}
        """
        return self.cdp.execute_js(script) or False
    
    def fill(self, selector: str, value: str, trigger_events: bool = True) -> bool:
        """
        Fill an input element
        
        Args:
            selector: CSS selector for the input
            value: Value to fill
            trigger_events: Trigger input and change events
            
        Returns:
            True if filled successfully
        """
        if not selector or not self._connected:
            return False
            
        script = f"""
        () => {{
            const el = document.querySelector(`{selector}`);
            if (!el) return false;
            
            el.value = `{value}`;
            
            // Trigger events
            el.dispatchEvent(new Event('input', {{ bubbles: true }}));
            if ({str(trigger_events).lower()}) {{
                el.dispatchEvent(new Event('change', {{ bubbles: true }}));
            }}
            return true;
        }}
        """
        return self.cdp.execute_js(script) or False
    
    def fill_form(self, form: Dict, data: Dict[str, str]) -> Dict[str, bool]:
        """
        Fill a form with data
        
        Args:
            form: Form dictionary from find_form_for_action()
            data: Dictionary of field_name -> value
            
        Returns:
            Dictionary of field_name -> success
        """
        results = {}
        
        if not form or not data:
            return results
            
        for input_field in form.get('inputs', []):
            field_name = input_field.get('name')
            if field_name and field_name in data:
                selector = input_field.get('selector')
                if selector:
                    results[field_name] = self.fill(selector, data[field_name])
                else:
                    results[field_name] = False
                    
        return results
    
    def get_text(self, selector: str) -> Optional[str]:
        """Get text content of an element"""
        if not selector or not self._connected:
            return None
            
        script = f"""
        () => {{
            const el = document.querySelector(`{selector}`);
            return el ? el.textContent?.trim() : null;
        }}
        """
        return self.cdp.execute_js(script)
    
    def get_value(self, selector: str) -> Optional[str]:
        """Get value of an input element"""
        if not selector or not self._connected:
            return None
            
        script = f"""
        () => {{
            const el = document.querySelector(`{selector}`);
            return el ? el.value : null;
        }}
        """
        return self.cdp.execute_js(script)
    
    def is_visible(self, selector: str) -> bool:
        """Check if an element is visible"""
        if not selector or not self._connected:
            return False
            
        script = f"""
        () => {{
            const el = document.querySelector(`{selector}`);
            return el ? el.offsetParent !== null : false;
        }}
        """
        return self.cdp.execute_js(script) or False
    
    def wait_for(self, selector: str, timeout: int = 10, visible: bool = True) -> bool:
        """
        Wait for an element to appear
        
        Args:
            selector: CSS selector
            timeout: Maximum time to wait (seconds)
            visible: Wait for element to be visible
            
        Returns:
            True if element found
        """
        if not selector or not self._connected:
            return False
            
        start = time.time()
        while time.time() - start < timeout:
            elements = self.find(selector, 1)
            if elements:
                if not visible or elements[0].is_visible:
                    return True
            time.sleep(0.5)
        return False
    
    def get_page_structure(self) -> Dict:
        """Get DOM structure statistics"""
        if not self._connected:
            return {}
            
        script = """
        () => {
            return {
                total_elements: document.querySelectorAll('*').length,
                interactive: document.querySelectorAll('button, a, input, select, textarea').length,
                forms: document.querySelectorAll('form').length,
                headings: document.querySelectorAll('h1, h2, h3, h4, h5, h6').length,
                links: document.querySelectorAll('a[href]').length,
                images: document.querySelectorAll('img').length,
                inputs: document.querySelectorAll('input:not([type="hidden"])').length,
                buttons: document.querySelectorAll('button, input[type="button"], input[type="submit"]').length
            };
        }
        """
        return self.cdp.execute_js(script) or {}
    
    def get_all_text(self) -> str:
        """Get all visible text on the page"""
        if not self._connected:
            return ""
            
        script = """
        () => {
            return document.body.textContent?.trim() || '';
        }
        """
        return self.cdp.execute_js(script) or ""
    
    # ========================================================================
    # Private Methods
    # ========================================================================
    
    def _dict_to_element(self, data: Dict) -> DOMElement:
        """Convert dict to DOMElement"""
        tag = data.get('tag', '').lower()
        attrs = data.get('attributes', {})
        
        return DOMElement(
            node_id=data.get('node_id', 0),
            tag_name=tag,
            text=data.get('text', ''),
            attributes=attrs,
            selector=self._generate_selector(data),
            is_visible=data.get('visible', True),
            is_interactive=data.get('interactive', tag in ['button', 'a', 'input', 'select', 'textarea']),
            is_form_element=tag in ['input', 'select', 'textarea', 'form'],
            bounding_box=data.get('boundingBox'),
            confidence=1.0
        )
    
    def _generate_selector(self, data: Dict) -> str:
        """Generate CSS selector from element data"""
        attrs = data.get('attributes', {})
        
        if attrs.get('id'):
            return f"#{attrs['id']}"
        
        # Try data attributes
        for attr in ['data-testid', 'data-id', 'data-name']:
            if attrs.get(attr):
                return f"[{attr}='{attrs[attr]}']"
        
        # Use class
        classes = attrs.get('class', '').split()
        if classes:
            tag = data.get('tag', '').lower()
            return f"{tag}.{'.'.join(classes[:2])}"
        
        return data.get('tag', '').lower()


# ============================================================================
# Convenience Functions
# ============================================================================

def find_element(selector: str, port: int = 9222, host: str = "127.0.0.1") -> Optional[DOMElement]:
    """
    Quick function to find a single element
    
    Example:
        button = find_element("#login-btn")
        if button:
            print(button.text)
    """
    finder = DOMFinder(port=port, host=host)
    if not finder.connect():
        return None
    try:
        elements = finder.find(selector, 1)
        return elements[0] if elements else None
    finally:
        finder.close()


def find_elements(selector: str, max_results: int = 10, port: int = 9222, host: str = "127.0.0.1") -> List[DOMElement]:
    """
    Quick function to find multiple elements
    
    Example:
        buttons = find_elements("button")
        for btn in buttons:
            print(btn.text)
    """
    finder = DOMFinder(port=port, host=host)
    if not finder.connect():
        return []
    try:
        return finder.find(selector, max_results)
    finally:
        finder.close()


def find_by_text(text: str, port: int = 9222, host: str = "127.0.0.1") -> List[DOMElement]:
    """
    Quick function to find elements by text
    
    Example:
        login_btn = find_by_text("Login")
    """
    finder = DOMFinder(port=port, host=host)
    if not finder.connect():
        return []
    try:
        return finder.find_by_text(text)
    finally:
        finder.close()


# ============================================================================
# CLI Interface
# ============================================================================

def main():
    """Command-line interface for DOM finder"""
    import argparse
    import json
    
    parser = argparse.ArgumentParser(description="DOM Finder - Find elements in Chrome")
    parser.add_argument("selector", nargs="?", help="CSS selector to find")
    parser.add_argument("--port", type=int, default=9222, help="Chrome DevTools port")
    parser.add_argument("--text", help="Find by text instead of selector")
    parser.add_argument("--type", help="Element type (button, link, input, etc.)")
    parser.add_argument("--attribute", help="Find by attribute")
    parser.add_argument("--value", help="Attribute value")
    parser.add_argument("--max", type=int, default=10, help="Maximum results")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--structure", action="store_true", help="Show page structure")
    parser.add_argument("--forms", action="store_true", help="Show forms")
    
    args = parser.parse_args()
    
    finder = DOMFinder(port=args.port)
    if not finder.connect():
        print("❌ Failed to connect to Chrome")
        return
    
    try:
        if args.structure:
            structure = finder.get_page_structure()
            if args.json:
                print(json.dumps(structure, indent=2))
            else:
                print("📊 Page Structure:")
                for key, value in structure.items():
                    print(f"  {key}: {value}")
            return
        
        if args.forms:
            forms = finder.find_forms()
            if args.json:
                print(json.dumps(forms, indent=2))
            else:
                print(f"📝 Found {len(forms)} forms")
                for i, form in enumerate(forms, 1):
                    print(f"\nForm {i}:")
                    print(f"  Action: {form.get('action', '')}")
                    print(f"  Method: {form.get('method', 'GET')}")
                    print(f"  Inputs: {len(form.get('inputs', []))}")
            return
        
        if args.text:
            elements = finder.find_by_text(args.text, max_results=args.max)
            method = "text"
        elif args.type:
            try:
                element_type = ElementType(args.type.lower())
                elements = finder.find_by_type(element_type, max_results=args.max)
                method = f"type '{args.type}'"
            except ValueError:
                print(f"❌ Invalid type: {args.type}")
                print(f"Valid types: {[e.value for e in ElementType]}")
                return
        elif args.attribute:
            elements = finder.find_by_attribute(args.attribute, args.value, max_results=args.max)
            method = f"attribute '{args.attribute}'"
        elif args.selector:
            elements = finder.find(args.selector, max_results=args.max)
            method = f"selector '{args.selector}'"
        else:
            elements = finder.find_interactive(max_results=args.max)
            method = "interactive elements"
        
        if args.json:
            print(json.dumps([e.to_dict() for e in elements], indent=2))
        else:
            if elements:
                print(f"✅ Found {len(elements)} elements by {method}:")
                for i, el in enumerate(elements, 1):
                    print(f"\n{i}. {el.tag_name} {'🟢 visible' if el.is_visible else '🔴 hidden'}")
                    print(f"   Text: {el.text[:80]}")
                    print(f"   Selector: {el.selector}")
                    if el.id:
                        print(f"   ID: {el.id}")
                    if el.href:
                        print(f"   href: {el.href}")
            else:
                print(f"❌ No elements found by {method}")
    
    finally:
        finder.close()


if __name__ == "__main__":
    main()
