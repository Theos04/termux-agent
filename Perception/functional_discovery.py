#!/usr/bin/env python3
"""
FUNCTIONAL DISCOVERY ENGINE
Discovers what you can DO on the page without assumptions
Detects: buttons, forms, inputs, navigation, interactions, etc.
"""

import json
import sys
import re
from pathlib import Path
from typing import Dict, Any, List, Set, Tuple
from collections import defaultdict, Counter
from dataclasses import dataclass, field
from enum import Enum

class InteractionType(Enum):
    """Types of interactions (discovered, not assumed)"""
    CLICK = "click"
    TYPE = "type"
    SELECT = "select"
    SUBMIT = "submit"
    NAVIGATE = "navigate"
    HOVER = "hover"
    FOCUS = "focus"
    DRAG = "drag"
    SCROLL = "scroll"
    UNKNOWN = "unknown"

@dataclass
class DiscoveredAction:
    """An action discovered on the page"""
    type: str  # click, type, select, etc.
    element_type: str  # button, input, link, etc.
    label: str = ""
    id: str = ""
    classes: List[str] = field(default_factory=list)
    attributes: Dict[str, str] = field(default_factory=dict)
    parent_text: str = ""
    child_text: List[str] = field(default_factory=list)
    confidence: float = 0.0
    
    def to_dict(self) -> Dict:
        return {
            'type': self.type,
            'element': self.element_type,
            'label': self.label[:100] if self.label else '',
            'id': self.id,
            'classes': self.classes[:5],
            'attributes': {k: v[:50] for k, v in list(self.attributes.items())[:5]},
            'parent_text': self.parent_text[:100] if self.parent_text else '',
            'confidence': self.confidence
        }

@dataclass
class FunctionalDiscovery:
    """Complete functional discovery of a page"""
    actions: List[DiscoveredAction] = field(default_factory=list)
    forms: List[Dict] = field(default_factory=list)
    navigation: List[Dict] = field(default_factory=list)
    inputs: List[Dict] = field(default_factory=list)
    interactive_elements: List[Dict] = field(default_factory=list)
    
    # Grouped by type
    clickable: List[Dict] = field(default_factory=list)
    typeable: List[Dict] = field(default_factory=list)
    selectable: List[Dict] = field(default_factory=list)
    submittable: List[Dict] = field(default_factory=list)
    
    # Discovered functions
    discovered_functions: Dict[str, List[str]] = field(default_factory=dict)
    
    @property
    def total_actions(self) -> int:
        return len(self.actions)
    
    @property
    def has_click_actions(self) -> bool:
        return len(self.clickable) > 0
    
    @property
    def has_forms(self) -> bool:
        return len(self.forms) > 0
    
    @property
    def has_navigation(self) -> bool:
        return len(self.navigation) > 0

class FunctionalDiscoverer:
    """
    Discovers what you can DO on the page
    No assumptions about what the page is for
    """
    
    def __init__(self):
        self.discovery = FunctionalDiscovery()
        self.all_texts = []
        self.all_nodes = []
        
    def discover(self, dom_data: Dict) -> FunctionalDiscovery:
        """Discover all functions/actions on the page"""
        print("\n🔍 DISCOVERING PAGE FUNCTIONS (No Assumptions)")
        print("="*60)
        
        # Extract all nodes
        self._extract_nodes(dom_data)
        
        # 1. Discover interactive elements
        self._discover_interactive_elements()
        
        # 2. Discover forms
        self._discover_forms()
        
        # 3. Discover navigation
        self._discover_navigation()
        
        # 4. Discover actions from text patterns
        self._discover_action_patterns()
        
        # 5. Analyze what you can do
        self._analyze_functionality()
        
        return self.discovery
    
    def _extract_nodes(self, data: Any, depth: int = 0):
        """Extract all nodes from DOM"""
        if depth > 20:
            return
        
        if isinstance(data, dict):
            # Store node if it has nodeId
            if 'nodeId' in data:
                self.all_nodes.append(data)
            
            # Extract text
            if 'nodeValue' in data and isinstance(data['nodeValue'], str):
                if data['nodeValue'].strip():
                    self.all_texts.append(data['nodeValue'].strip())
            
            # Recurse
            for key, value in data.items():
                if key not in ['children', 'childNodes']:
                    self._extract_nodes(value, depth + 1)
            
            # Handle children
            for key in ['children', 'childNodes']:
                if key in data and isinstance(data[key], list):
                    for child in data[key]:
                        self._extract_nodes(child, depth + 1)
        
        elif isinstance(data, list):
            for item in data:
                self._extract_nodes(item, depth + 1)
    
    def _discover_interactive_elements(self):
        """Discover all interactive elements"""
        interactive_tags = {'button', 'a', 'input', 'select', 'textarea', 'option'}
        role_patterns = {'button', 'link', 'textbox', 'combobox', 'searchbox', 
                        'checkbox', 'radio', 'menuitem', 'tab', 'slider'}
        
        click_indicators = {'onclick', 'data-action', 'role="button"', 'role="link"'}
        type_indicators = {'type="text"', 'type="email"', 'type="password"', 'type="number"',
                          'type="tel"', 'type="search"', 'role="textbox"'}
        
        for node in self.all_nodes:
            # Get node info
            tag = node.get('nodeName', '').lower()
            attrs = self._get_attributes(node)
            
            # Skip if not interactive
            if tag not in interactive_tags and not any(role in attrs.get('role', '') for role in role_patterns):
                continue
            
            # Determine action type
            action_type = InteractionType.UNKNOWN.value
            
            # Check for clickable
            if tag in ['button', 'a'] or attrs.get('role') in ['button', 'link'] or 'onclick' in node:
                action_type = 'click'
                self._add_action(node, 'click', tag, attrs)
                self.discovery.clickable.append(self._node_to_dict(node, 'click'))
            
            # Check for typeable
            elif tag in ['input', 'textarea'] or attrs.get('role') in ['textbox', 'searchbox']:
                action_type = 'type'
                self._add_action(node, 'type', tag, attrs)
                self.discovery.typeable.append(self._node_to_dict(node, 'type'))
            
            # Check for selectable
            elif tag == 'select' or attrs.get('role') == 'combobox':
                action_type = 'select'
                self._add_action(node, 'select', tag, attrs)
                self.discovery.selectable.append(self._node_to_dict(node, 'select'))
            
            # Check for submit
            elif tag == 'button' and attrs.get('type') == 'submit':
                action_type = 'submit'
                self._add_action(node, 'submit', tag, attrs)
                self.discovery.submittable.append(self._node_to_dict(node, 'submit'))
            
            # Store as interactive element
            self.discovery.interactive_elements.append({
                'tag': tag,
                'type': action_type,
                'attributes': attrs,
                'text': self._get_node_text(node)
            })
        
        print(f"  ✅ Interactive elements: {len(self.discovery.interactive_elements)}")
        print(f"     • Clickable: {len(self.discovery.clickable)}")
        print(f"     • Typeable: {len(self.discovery.typeable)}")
        print(f"     • Selectable: {len(self.discovery.selectable)}")
        print(f"     • Submittable: {len(self.discovery.submittable)}")
    
    def _add_action(self, node: Dict, action_type: str, tag: str, attrs: Dict):
        """Add a discovered action"""
        action = DiscoveredAction(
            type=action_type,
            element_type=tag,
            label=attrs.get('aria-label', '') or attrs.get('title', '') or self._get_node_text(node),
            id=attrs.get('id', ''),
            classes=attrs.get('class', '').split() if attrs.get('class') else [],
            attributes=attrs,
            parent_text=self._get_parent_text(node),
            child_text=self._get_child_text(node),
            confidence=1.0 if tag in ['button', 'input'] else 0.8
        )
        
        self.discovery.actions.append(action)
    
    def _get_attributes(self, node: Dict) -> Dict:
        """Extract attributes from node"""
        attrs = {}
        attr_list = node.get('attributes', [])
        if isinstance(attr_list, list):
            for i in range(0, len(attr_list), 2):
                if i+1 < len(attr_list):
                    attrs[attr_list[i]] = attr_list[i+1]
        return attrs
    
    def _get_node_text(self, node: Dict) -> str:
        """Extract text from node"""
        # Check for value/placeholder
        attrs = self._get_attributes(node)
        for key in ['value', 'placeholder', 'aria-label', 'title']:
            if key in attrs and attrs[key]:
                return attrs[key]
        
        # Check child text nodes
        for child_id in node.get('childIds', []):
            for child in self.all_nodes:
                if child.get('nodeId') == child_id:
                    if child.get('nodeType') == 3:  # Text node
                        return child.get('nodeValue', '').strip()
        
        return ''
    
    def _get_parent_text(self, node: Dict) -> str:
        """Get text from parent node"""
        parent_id = node.get('parentId')
        if parent_id:
            for parent in self.all_nodes:
                if parent.get('nodeId') == parent_id:
                    return self._get_node_text(parent)
        return ''
    
    def _get_child_text(self, node: Dict) -> List[str]:
        """Get text from child nodes"""
        texts = []
        for child_id in node.get('childIds', []):
            for child in self.all_nodes:
                if child.get('nodeId') == child_id:
                    if child.get('nodeType') == 3:
                        text = child.get('nodeValue', '').strip()
                        if text:
                            texts.append(text)
        return texts
    
    def _node_to_dict(self, node: Dict, action_type: str) -> Dict:
        """Convert node to dict for storage"""
        attrs = self._get_attributes(node)
        return {
            'type': action_type,
            'tag': node.get('nodeName', '').lower(),
            'id': attrs.get('id', ''),
            'classes': attrs.get('class', '').split() if attrs.get('class') else [],
            'text': self._get_node_text(node),
            'confidence': 1.0
        }
    
    def _discover_forms(self):
        """Discover all forms on the page"""
        for node in self.all_nodes:
            if node.get('nodeName', '').lower() == 'form':
                attrs = self._get_attributes(node)
                
                # Find inputs in this form
                inputs = []
                for child in self.all_nodes:
                    if child.get('parentId') == node.get('nodeId'):
                        if child.get('nodeName', '').lower() in ['input', 'select', 'textarea']:
                            inputs.append(self._get_node_text(child))
                
                self.discovery.forms.append({
                    'id': attrs.get('id', ''),
                    'action': attrs.get('action', ''),
                    'method': attrs.get('method', 'get'),
                    'inputs_count': len(inputs),
                    'inputs': inputs[:5]
                })
        
        print(f"  ✅ Forms: {len(self.discovery.forms)}")
        for i, form in enumerate(self.discovery.forms[:3]):
            print(f"     • Form {i+1}: action='{form.get('action', '')[:50]}', {form.get('inputs_count')} inputs")
    
    def _discover_navigation(self):
        """Discover navigation elements"""
        nav_indicators = {'nav', 'navigation', 'menu', 'menubar', 'navbar'}
        
        for node in self.all_nodes:
            tag = node.get('nodeName', '').lower()
            attrs = self._get_attributes(node)
            role = attrs.get('role', '')
            
            if tag in nav_indicators or role in nav_indicators:
                # Find links in navigation
                links = []
                for child in self.all_nodes:
                    if child.get('parentId') == node.get('nodeId'):
                        if child.get('nodeName', '').lower() == 'a':
                            links.append(self._get_node_text(child))
                
                self.discovery.navigation.append({
                    'tag': tag,
                    'role': role,
                    'links': links[:10],
                    'link_count': len(links)
                })
        
        print(f"  ✅ Navigation sections: {len(self.discovery.navigation)}")
    
    def _discover_action_patterns(self):
        """Discover action patterns from text"""
        action_keywords = ['click', 'submit', 'apply', 'search', 'find', 'go', 
                          'next', 'prev', 'back', 'forward', 'save', 'cancel',
                          'delete', 'edit', 'update', 'add', 'remove', 'view', 
                          'login', 'signin', 'signup', 'register', 'download',
                          'upload', 'share', 'comment', 'like', 'follow']
        
        action_phrases = defaultdict(list)
        
        for text in self.all_texts:
            text_lower = text.lower()
            for keyword in action_keywords:
                if keyword in text_lower:
                    action_phrases[keyword].append(text)
        
        # Store discovered functions
        self.discovery.discovered_functions['action_keywords'] = {
            kw: len(phrases) for kw, phrases in action_phrases.items() if len(phrases) > 2
        }
        
        # Also discover from button labels
        button_labels = []
        for action in self.discovery.actions:
            if action.label:
                button_labels.append(action.label)
        
        self.discovery.discovered_functions['button_labels'] = button_labels[:20]
    
    def _analyze_functionality(self):
        """Analyze and summarize functionality"""
        print("\n" + "="*60)
        print("🎯 DISCOVERED FUNCTIONALITY")
        print("="*60)
        
        # 1. What can you click?
        if self.discovery.clickable:
            print(f"\n🖱️ CLICKABLE ELEMENTS ({len(self.discovery.clickable)}):")
            for elem in self.discovery.clickable[:10]:
                label = elem.get('text', '') or elem.get('id', '') or elem.get('tag', '')
                if label:
                    print(f"   • {label} ({elem.get('type')})")
        
        # 2. What can you type in?
        if self.discovery.typeable:
            print(f"\n⌨️ TYPEABLE ELEMENTS ({len(self.discovery.typeable)}):")
            for elem in self.discovery.typeable[:10]:
                label = elem.get('text', '') or elem.get('id', '') or elem.get('tag', '')
                if label:
                    print(f"   • {label}")
        
        # 3. What forms exist?
        if self.discovery.forms:
            print(f"\n📝 FORMS ({len(self.discovery.forms)}):")
            for i, form in enumerate(self.discovery.forms[:3]):
                print(f"   • Form {i+1}: {form.get('inputs_count')} inputs")
                if form.get('inputs'):
                    for inp in form.get('inputs')[:3]:
                        if inp:
                            print(f"     - {inp}")
        
        # 4. What navigation exists?
        if self.discovery.navigation:
            print(f"\n🧭 NAVIGATION ({len(self.discovery.navigation)} sections):")
            for nav in self.discovery.navigation[:3]:
                print(f"   • {nav.get('link_count')} links")
                for link in nav.get('links', [])[:3]:
                    if link:
                        print(f"     - {link}")
        
        # 5. Discovered action keywords
        keywords = self.discovery.discovered_functions.get('action_keywords', {})
        if keywords:
            print(f"\n🔑 DISCOVERED ACTION KEYWORDS:")
            for kw, count in sorted(keywords.items(), key=lambda x: x[1], reverse=True)[:10]:
                print(f"   • '{kw}': {count} occurrences")
        
        # 6. Summary
        print(f"\n" + "="*60)
        print("📊 FUNCTIONAL SUMMARY")
        print("="*60)
        print(f"  Total interactive elements: {len(self.discovery.interactive_elements)}")
        print(f"  Total discoverable actions: {len(self.discovery.actions)}")
        print(f"  Clickable: {len(self.discovery.clickable)}")
        print(f"  Typeable: {len(self.discovery.typeable)}")
        print(f"  Selectable: {len(self.discovery.selectable)}")
        print(f"  Forms: {len(self.discovery.forms)}")
        print(f"  Navigation sections: {len(self.discovery.navigation)}")
        
        # 7. What can you DO on this page?
        print(f"\n💡 YOU CAN:")
        if self.discovery.clickable:
            print(f"   • Click on {len(self.discovery.clickable)} elements")
        if self.discovery.typeable:
            print(f"   • Type into {len(self.discovery.typeable)} fields")
        if self.discovery.selectable:
            print(f"   • Select from {len(self.discovery.selectable)} dropdowns")
        if self.discovery.forms:
            print(f"   • Submit {len(self.discovery.forms)} forms")
        if self.discovery.navigation:
            print(f"   • Navigate using {len(self.discovery.navigation)} navigation sections")
        
        # 8. Suggested actions (discovered from keywords)
        suggested = []
        for kw, count in keywords.items():
            if count > 5:
                suggested.append(kw)
        
        if suggested:
            print(f"\n🎯 SUGGESTED ACTIONS (based on discovered text):")
            for action in suggested[:10]:
                print(f"   • {action.capitalize()}")

def main():
    print("🧠 FUNCTIONAL DISCOVERY ENGINE")
    print("Discovering what you can DO on the page")
    print("="*60)
    
    # Find sessions
    memory_dir = Path('/data/data/com.termux/files/home/automation/chrome-launcher/memory')
    sessions = sorted(memory_dir.glob('session_*'), key=lambda x: x.stat().st_mtime, reverse=True)
    
    if sessions:
        print("\n📂 Recent sessions:")
        for i, session in enumerate(sessions[:5]):
            print(f"  [{i}] {session.name}")
        
        choice = input("\nSelect session [0-4] or enter path: ").strip()
        
        if choice.isdigit():
            idx = int(choice)
            if 0 <= idx < len(sessions):
                session_path = sessions[idx]
            else:
                print("❌ Invalid selection")
                return
        else:
            session_path = Path(choice) if choice else sessions[0]
    else:
        session_path = Path(input("📁 Enter session path: ").strip())
    
    if not session_path.exists():
        print(f"❌ Session not found: {session_path}")
        return
    
    # Load DOM data
    dom_files = list(session_path.glob('dom_trees/dom_*.json')) + list(session_path.glob('dom_*.json'))
    if not dom_files:
        print("❌ No DOM data found in session")
        return
    
    with open(dom_files[0], 'r') as f:
        raw = json.load(f)
        # Handle wrapper
        dom_data = raw.get('data', raw)
    
    # Discover functionality
    discoverer = FunctionalDiscoverer()
    discovery = discoverer.discover(dom_data)
    
    # Save results
    output_file = session_path / 'functional_discovery.json'
    result = {
        'total_actions': discovery.total_actions,
        'clickable': len(discovery.clickable),
        'typeable': len(discovery.typeable),
        'selectable': len(discovery.selectable),
        'forms': len(discovery.forms),
        'navigation': len(discovery.navigation),
        'discovered_functions': {
            'action_keywords': discovery.discovered_functions.get('action_keywords', {}),
            'button_labels': discovery.discovered_functions.get('button_labels', [])[:20]
        },
        'sample_actions': [a.to_dict() for a in discovery.actions[:20]]
    }
    
    with open(output_file, 'w') as f:
        json.dump(result, f, indent=2)
    
    print(f"\n💾 Saved to: {output_file}")

if __name__ == "__main__":
    main()
