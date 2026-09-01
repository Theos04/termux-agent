from dataclasses import dataclass, field
from typing import Any, Dict, Set
from enum import Enum

class PageType(Enum):
    EMPTY = "empty"          # < 10 nodes
    LANDING = "landing"      # Promotional, few interactives
    CONTENT = "content"      # Readable text
    INTERACTIVE = "interactive"  # Forms, inputs
    COMPLEX = "complex"      # Heavy app

@dataclass
class DOMStats:
    """Single-pass DOM statistics"""
    
    # Node counts
    total_nodes: int = 0
    element_nodes: int = 0
    text_nodes: int = 0
    
    # Interactive elements
    buttons: int = 0
    links: int = 0
    inputs: int = 0
    selects: int = 0
    textareas: int = 0
    interactive_total: int = 0
    
    # Structure
    forms: int = 0
    iframes: int = 0
    scripts: int = 0
    images: int = 0
    headers: int = 0  # h1-h6
    paragraphs: int = 0
    lists: int = 0
    
    # Shadow DOM
    shadow_roots: int = 0
    shadow_hosts: int = 0
    
    # Navigation
    iframe_content_docs: int = 0
    
    # Derived (set after analysis)
    page_type: PageType = PageType.EMPTY
    has_form: bool = False
    has_search: bool = False
    has_navigation: bool = False
    action_elements: list = field(default_factory=list)
    
    @property
    def complexity_score(self) -> float:
        """0.0 - 1.0 based on node count"""
        return min(1.0, self.total_nodes / 5000)
    
    @property
    def interaction_score(self) -> float:
        """0.0 - 1.0 based on interactive density"""
        if self.total_nodes < 10:
            return 0.0
        density = self.interactive_total / self.total_nodes
        return min(1.0, density * 20)  # 5% density = 1.0
    
    @property
    def is_simple(self) -> bool:
        return self.total_nodes < 100 and self.interactive_total < 5


class DomAnalyzer:
    """Single-pass DOM analyzer with proper traversal"""
    
    INTERACTIVE_TAGS = {'button', 'a', 'input', 'select', 'textarea', 'option'}
    NAV_TAGS = {'nav', 'menu', 'menubar'}
    HEADER_TAGS = {'h1', 'h2', 'h3', 'h4', 'h5', 'h6'}
    CONTENT_TAGS = {'p', 'article', 'section', 'main'}
    
    def analyze(self, dom_data: Dict[str, Any]) -> DOMStats:
        """Single-pass analysis - walk once, collect all stats"""
        stats = DOMStats()
        self._walk(dom_data, stats)
        self._derive_page_type(stats)
        return stats
    
    def _walk(self, node: Dict[str, Any], stats: DOMStats, depth: int = 0):
        """Single recursive walk, collect everything"""
        stats.total_nodes += 1
        
        node_type = node.get('nodeType')
        node_name = node.get('nodeName', '').lower()
        
        # --- Element node ---
        if node_type == 1:  # ELEMENT_NODE
            stats.element_nodes += 1
            
            # Track interactive elements
            if node_name in self.INTERACTIVE_TAGS:
                stats.interactive_total += 1
                
                if node_name == 'button':
                    stats.buttons += 1
                    self._track_action_element(node, stats, 'button')
                elif node_name == 'input':
                    stats.inputs += 1
                    self._track_action_element(node, stats, 'input')
                    # Check for search specifically
                    if self._is_search_input(node):
                        stats.has_search = True
                elif node_name == 'a':
                    stats.links += 1
                    self._track_action_element(node, stats, 'link')
                elif node_name == 'select':
                    stats.selects += 1
                elif node_name == 'textarea':
                    stats.textareas += 1
            
            # Structure
            elif node_name == 'form':
                stats.forms += 1
                stats.has_form = True
            elif node_name == 'iframe':
                stats.iframes += 1
                # Check if it has contentDocument
                if node.get('contentDocument'):
                    stats.iframe_content_docs += 1
            elif node_name == 'script':
                stats.scripts += 1
            elif node_name == 'img':
                stats.images += 1
            elif node_name in self.HEADER_TAGS:
                stats.headers += 1
            elif node_name in self.CONTENT_TAGS:
                if node_name == 'p':
                    stats.paragraphs += 1
            elif node_name in self.NAV_TAGS or node_name == 'nav':
                stats.has_navigation = True
            
            # Shadow DOM
            shadow_roots = node.get('shadowRoots', [])
            if shadow_roots:
                stats.shadow_roots += len(shadow_roots)
                stats.shadow_hosts += 1
                for shadow in shadow_roots:
                    self._walk(shadow, stats, depth + 1)
            
            # Iframe contentDocument
            content_doc = node.get('contentDocument')
            if content_doc:
                self._walk(content_doc, stats, depth + 1)
            
            # Flattened children
            children = node.get('children', [])
            for child in children:
                self._walk(child, stats, depth + 1)
        
        # --- Text node ---
        elif node_type == 3:  # TEXT_NODE
            stats.text_nodes += 1
    
    def _is_search_input(self, node: Dict[str, Any]) -> bool:
        """Check if input is a search box"""
        attrs = node.get('attributes', {})
        if isinstance(attrs, list):
            # Handle CDP's list format ['name', 'value', ...]
            attrs_dict = {attrs[i]: attrs[i+1] for i in range(0, len(attrs), 2)}
            attrs = attrs_dict
        
        attrs = node.get('attributes', {}) if isinstance(attrs, dict) else {}
        
        # Type is search
        if attrs.get('type') == 'search':
            return True
        
        # Check for search indicators
        search_indicators = {'search', 'query', 'find', 'go'}
        for attr in ['name', 'id', 'class', 'placeholder', 'aria-label']:
            val = attrs.get(attr, '').lower()
            if any(ind in val for ind in search_indicators):
                return True
        return False
    
    def _track_action_element(self, node: Dict[str, Any], stats: DOMStats, elem_type: str):
        """Track important action elements for decision making"""
        # Only track if we're in a form or it's a button
        if elem_type == 'button' or self._is_in_form(node):
            # Get text/label
            label = self._get_element_label(node)
            if label:
                stats.action_elements.append({
                    'type': elem_type,
                    'label': label[:50],  # Truncate for brevity
                    'visible': self._is_visible(node)
                })
    
    def _is_in_form(self, node: Dict[str, Any]) -> bool:
        """Check if node is inside a form (simplified)"""
        # In CDP, we could walk parent chain but skip for performance
        # Return True for now - it's just for tracking
        return True
    
    def _get_element_label(self, node: Dict[str, Any]) -> str:
        """Get text label from element"""
        # Check value/placeholder first
        attrs = node.get('attributes', {})
        if isinstance(attrs, list):
            attrs_dict = {attrs[i]: attrs[i+1] for i in range(0, len(attrs), 2)}
            attrs = attrs_dict
        
        if isinstance(attrs, dict):
            for key in ['value', 'placeholder', 'aria-label', 'title']:
                if key in attrs and attrs[key]:
                    return attrs[key]
        
        # Check child text (simplified)
        children = node.get('children', [])
        for child in children:
            if child.get('nodeType') == 3:  # text node
                text = child.get('nodeValue', '').strip()
                if text:
                    return text
            
            # Check nested elements for text
            if child.get('nodeType') == 1:
                nested_text = self._get_element_label(child)
                if nested_text:
                    return nested_text
        
        return ''
    
    def _is_visible(self, node: Dict[str, Any]) -> bool:
        """Check if element is likely visible (simplified)"""
        # In CDP we could check computed styles, but skip for speed
        # Return True by default for actionable elements
        return True
    
    def _derive_page_type(self, stats: DOMStats):
        """Classify page type from collected stats"""
        
        if stats.total_nodes < 10:
            stats.page_type = PageType.EMPTY
            return
        
        # Complex app: lots of interactives and scripts
        if stats.interactive_total > 20 and stats.scripts > 10:
            stats.page_type = PageType.COMPLEX
            return
        
        # Landing page: lots of images, some text, few interactives
        if stats.images > 5 and stats.headers > 2 and stats.interactive_total < 5:
            stats.page_type = PageType.LANDING
            return
        
        # Interactive: forms, inputs, few scripts
        if stats.has_form or stats.inputs > 3:
            stats.page_type = PageType.INTERACTIVE
            return
        
        # Content: lots of text, paragraphs, headings
        if stats.text_nodes > 50 and stats.paragraphs > 5:
            stats.page_type = PageType.CONTENT
            return
        
        # Default
        stats.page_type = PageType.CONTENT


# === Usage ===

def analyze_page(dom_data: Dict[str, Any]) -> Dict[str, Any]:
    """Quick analysis function"""
    analyzer = DomAnalyzer()
    stats = analyzer.analyze(dom_data)
    
    return {
        'node_count': stats.total_nodes,
        'interactive_count': stats.interactive_total,
        'complexity': stats.complexity_score,
        'interaction_score': stats.interaction_score,
        'has_forms': stats.has_form,
        'has_search': stats.has_search,
        'has_navigation': stats.has_navigation,
        'page_type': stats.page_type.value,
        'is_simple': stats.is_simple,
        'action_elements': stats.action_elements[:5],  # Top 5 actions
        'shadow_dom_count': stats.shadow_roots,
        'iframe_count': stats.iframes,
    }


# === Decision Engine ===

def decide_action(analysis: Dict[str, Any]) -> str:
    """Simple decision based on analysis"""
    
    if analysis['is_simple']:
        return "direct_scrape"
    
    if analysis['page_type'] == 'empty':
        return "skip"
    
    if analysis['has_search']:
        return "search_interaction"
    
    if analysis['has_forms'] and analysis['interactive_count'] > 3:
        return "form_fill"
    
    if analysis['page_type'] == 'landing':
        return "click_cta"
    
    if analysis['page_type'] == 'content':
        return "extract_text"
    
    if analysis['page_type'] == 'complex':
        return "vision_model"  # Expensive path
    
    return "explore"
# Add this to the end of dom_analysis.py:

if __name__ == "__main__":
    # Create a sample DOM structure
    sample_dom = {
        "nodeType": 1,
        "nodeName": "HTML",
        "children": [
            {
                "nodeType": 1,
                "nodeName": "HEAD",
                "children": [
                    {
                        "nodeType": 1,
                        "nodeName": "SCRIPT",
                        "attributes": ["src", "app.js"]
                    }
                ]
            },
            {
                "nodeType": 1,
                "nodeName": "BODY",
                "children": [
                    {
                        "nodeType": 1,
                        "nodeName": "NAV",
                        "children": [
                            {
                                "nodeType": 1,
                                "nodeName": "A",
                                "attributes": ["href", "/home"],
                                "children": [
                                    {"nodeType": 3, "nodeValue": "Home"}
                                ]
                            }
                        ]
                    },
                    {
                        "nodeType": 1,
                        "nodeName": "H1",
                        "children": [
                            {"nodeType": 3, "nodeValue": "Welcome to My Site"}
                        ]
                    },
                    {
                        "nodeType": 1,
                        "nodeName": "FORM",
                        "attributes": ["action", "/submit"],
                        "children": [
                            {
                                "nodeType": 1,
                                "nodeName": "INPUT",
                                "attributes": ["type", "text", "placeholder", "Enter your name"]
                            },
                            {
                                "nodeType": 1,
                                "nodeName": "INPUT",
                                "attributes": ["type", "email", "placeholder", "Enter email"]
                            },
                            {
                                "nodeType": 1,
                                "nodeName": "BUTTON",
                                "attributes": ["type", "submit"],
                                "children": [
                                    {"nodeType": 3, "nodeValue": "Submit Form"}
                                ]
                            }
                        ]
                    },
                    {
                        "nodeType": 1,
                        "nodeName": "P",
                        "children": [
                            {"nodeType": 3, "nodeValue": "This is a paragraph of text."}
                        ]
                    },
                    {
                        "nodeType": 1,
                        "nodeName": "IMG",
                        "attributes": ["src", "photo.jpg", "alt", "A photo"]
                    }
                ]
            }
        ]
    }
    
    # Run analysis
    print("=" * 50)
    print("RUNNING DOM ANALYSIS")
    print("=" * 50)
    
    result = analyze_page(sample_dom)
    
    print("\n📊 STATISTICS:")
    for key, value in result.items():
        if key == 'action_elements':
            print(f"  {key}:")
            for action in value:
                print(f"    - {action}")
        else:
            print(f"  {key}: {value}")
    
    print("\n🎯 DECISION:")
    action = decide_action(result)
    print(f"  Recommended action: {action}")
    
    # Test with a complex page
    print("\n" + "=" * 50)
    print("TESTING COMPLEX PAGE")
    print("=" * 50)
    
    # Build a more complex DOM (simplified)
    complex_dom = {
        "nodeType": 1,
        "nodeName": "HTML",
        "children": [
            {
                "nodeType": 1,
                "nodeName": "BODY",
                "children": []
            }
        ]
    }
    
    # Add 100 interactive elements
    for i in range(30):
        complex_dom["children"][0]["children"].append({
            "nodeType": 1,
            "nodeName": "BUTTON",
            "children": [{"nodeType": 3, "nodeValue": f"Button {i}"}]
        })
    
    for i in range(20):
        complex_dom["children"][0]["children"].append({
            "nodeType": 1,
            "nodeName": "SCRIPT",
            "attributes": ["src", f"lib{i}.js"]
        })
    
    for i in range(10):
        complex_dom["children"][0]["children"].append({
            "nodeType": 1,
            "nodeName": "FORM",
            "children": [
                {
                    "nodeType": 1,
                    "nodeName": "INPUT",
                    "attributes": ["type", "text", "name", f"field{i}"]
                }
            ]
        })
    
    result = analyze_page(complex_dom)
    print(f"  Node count: {result['node_count']}")
    print(f"  Interactive count: {result['interactive_count']}")
    print(f"  Page type: {result['page_type']}")
    print(f"  Recommended: {decide_action(result)}")
