#!/usr/bin/env python3
"""
DOM & Accessibility Analyzer for CDP data
Works with your session_20260731_061442 structure
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Any, Set, Tuple
from dataclasses import dataclass, field
from collections import defaultdict

@dataclass
class AXNode:
    """Accessibility node"""
    node_id: str
    role: str
    name: str
    description: str = ""
    value: str = ""
    parent_id: Optional[str] = None
    child_ids: List[str] = field(default_factory=list)
    dom_node_id: Optional[int] = None
    properties: Dict[str, Any] = field(default_factory=dict)

@dataclass
class DOMNode:
    """DOM node with CDP data"""
    node_id: int
    parent_id: Optional[int] = None
    node_name: str = ""
    node_type: int = 1
    attributes: Dict[str, str] = field(default_factory=dict)
    children: List[int] = field(default_factory=list)
    ax_node_id: Optional[str] = None  # Link to accessibility tree

class DOMAccessibilityAnalyzer:
    """Unified DOM + Accessibility analyzer"""
    
    def __init__(self, session_dir: str):
        self.session_dir = Path(session_dir)
        self.dom_nodes: Dict[int, DOMNode] = {}
        self.ax_nodes: Dict[str, AXNode] = {}
        self.dom_to_ax: Dict[int, str] = {}  # DOM node_id -> AX node_id
        self.ax_to_dom: Dict[str, int] = {}  # AX node_id -> DOM node_id
        self.name_index: Dict[str, List[AXNode]] = defaultdict(list)  # Accessible name -> AX nodes
        self.role_index: Dict[str, List[AXNode]] = defaultdict(list)  # Role -> AX nodes
        
        # Load data
        self._load_data()
        self._build_indexes()
    
    def _load_data(self):
        """Load DOM and accessibility data from session"""
        # Find the latest DOM tree
        dom_dir = self.session_dir / "dom_trees"
        if dom_dir.exists():
            dom_files = list(dom_dir.glob("dom_*.json"))
            if dom_files:
                latest_dom = max(dom_files, key=lambda f: f.stat().st_mtime)
                with open(latest_dom) as f:
                    dom_data = json.load(f)
                    self._parse_dom(dom_data)
        
        # Find the latest accessibility data
        ax_dir = self.session_dir / "accessibility"
        if ax_dir.exists():
            ax_files = list(ax_dir.glob("a11y_*.json"))
            if ax_files:
                latest_ax = max(ax_files, key=lambda f: f.stat().st_mtime)
                with open(latest_ax) as f:
                    ax_data = json.load(f)
                    self._parse_accessibility(ax_data)
        
        # Build cross-references
        self._build_cross_references()
    
    def _parse_dom(self, data: Dict[str, Any]):
        """Parse CDP DOM data"""
        def walk(node_data, parent_id=None):
            node_id = node_data.get('nodeId')
            if not node_id:
                return
            
            # Parse attributes
            attrs = {}
            attr_list = node_data.get('attributes', [])
            for i in range(0, len(attr_list), 2):
                if i + 1 < len(attr_list):
                    attrs[attr_list[i]] = attr_list[i + 1]
            
            node = DOMNode(
                node_id=node_id,
                parent_id=parent_id,
                node_name=node_data.get('nodeName', '').lower(),
                node_type=node_data.get('nodeType', 1),
                attributes=attrs,
                children=[]
            )
            self.dom_nodes[node_id] = node
            
            # Process children
            for child in node_data.get('children', []):
                walk(child, node_id)
                child_id = child.get('nodeId')
                if child_id and child_id in self.dom_nodes:
                    node.children.append(child_id)
        
        # Start with the root (assuming it's the document)
        if 'root' in data:
            walk(data['root'])
        else:
            walk(data)
    
    def _parse_accessibility(self, data: Dict[str, Any]):
        """Parse CDP accessibility data"""
        def walk(node_data, parent_id=None):
            ax_node_id = node_data.get('nodeId')
            if not ax_node_id:
                return
            
            # Get properties
            props = {}
            for prop in node_data.get('properties', []):
                name = prop.get('name')
                value = prop.get('value', {})
                if name:
                    props[name] = value.get('value', '')
            
            node = AXNode(
                node_id=ax_node_id,
                role=props.get('role', 'unknown'),
                name=props.get('name', ''),
                description=props.get('description', ''),
                value=props.get('value', ''),
                parent_id=parent_id,
                child_ids=[],
                properties=props
            )
            self.ax_nodes[ax_node_id] = node
            
            # Process children
            for child in node_data.get('children', []):
                walk(child, ax_node_id)
                child_id = child.get('nodeId')
                if child_id and child_id in self.ax_nodes:
                    node.child_ids.append(child_id)
            
            # Store DOM node ID if available
            dom_node_id = node_data.get('backendDOMNodeId')
            if dom_node_id:
                node.dom_node_id = dom_node_id
                self.ax_to_dom[ax_node_id] = dom_node_id
                self.dom_to_ax[dom_node_id] = ax_node_id
        
        # Walk the accessibility tree
        if 'nodes' in data:
            for node in data['nodes']:
                walk(node)
        else:
            walk(data)
    
    def _build_cross_references(self):
        """Build cross-references between DOM and AX trees"""
        # Update DOM nodes with AX links
        for ax_id, dom_id in self.ax_to_dom.items():
            if dom_id in self.dom_nodes:
                self.dom_nodes[dom_id].ax_node_id = ax_id
    
    def _build_indexes(self):
        """Build search indexes"""
        for ax_id, node in self.ax_nodes.items():
            # Index by name
            if node.name:
                self.name_index[node.name.lower()].append(node)
            
            # Index by role
            if node.role:
                self.role_index[node.role].append(node)
    
    # === Core Query Methods ===
    
    def find_by_accessible_name(self, name: str, exact: bool = False) -> List[AXNode]:
        """Find accessibility nodes by accessible name"""
        name_lower = name.lower()
        results = []
        
        for ax_name, nodes in self.name_index.items():
            if exact:
                if ax_name == name_lower:
                    results.extend(nodes)
            else:
                if name_lower in ax_name or ax_name in name_lower:
                    results.extend(nodes)
        
        return results
    
    def find_by_role(self, role: str) -> List[AXNode]:
        """Find accessibility nodes by role"""
        role_lower = role.lower()
        return self.role_index.get(role_lower, [])
    
    def walk_ancestors(self, node_id: str, tree: str = 'ax') -> List[Dict]:
        """Walk ancestors of a node"""
        if tree == 'ax':
            nodes = self.ax_nodes
            parent_attr = 'parent_id'
        else:
            nodes = self.dom_nodes
            parent_attr = 'parent_id'
        
        ancestors = []
        current_id = node_id
        
        while current_id and current_id in nodes:
            node = nodes[current_id]
            ancestors.append(self._node_to_dict(node, tree))
            current_id = getattr(node, parent_attr)
        
        return ancestors
    
    def walk_descendants(self, node_id: str, tree: str = 'ax') -> List[Dict]:
        """Walk all descendants of a node"""
        if tree == 'ax':
            nodes = self.ax_nodes
            children_attr = 'child_ids'
        else:
            nodes = self.dom_nodes
            children_attr = 'children'
        
        descendants = []
        
        def walk(current_id, depth=0):
            if current_id not in nodes:
                return
            
            node = nodes[current_id]
            descendants.append({
                'node': self._node_to_dict(node, tree),
                'depth': depth
            })
            
            for child_id in getattr(node, children_attr, []):
                walk(child_id, depth + 1)
        
        walk(node_id)
        return descendants
    
    def map_ax_to_dom(self, ax_node_id: str) -> Optional[DOMNode]:
        """Map accessibility node to DOM node"""
        dom_id = self.ax_to_dom.get(ax_node_id)
        if dom_id and dom_id in self.dom_nodes:
            return self.dom_nodes[dom_id]
        return None
    
    def map_dom_to_ax(self, dom_node_id: int) -> Optional[AXNode]:
        """Map DOM node to accessibility node"""
        ax_id = self.dom_to_ax.get(dom_node_id)
        if ax_id and ax_id in self.ax_nodes:
            return self.ax_nodes[ax_id]
        return None
    
    def print_semantic_path(self, ax_node_id: str):
        """Print semantic path (role hierarchy) to a node"""
        ancestors = self.walk_ancestors(ax_node_id, 'ax')
        if not ancestors:
            print(f"Node {ax_node_id} not found")
            return
        
        # Reverse to go from root to target
        path = list(reversed(ancestors))
        
        print("\n🔗 SEMANTIC PATH (role hierarchy):")
        for i, node in enumerate(path):
            indent = "  " * i
            name_info = f" '{node['name']}'" if node['name'] else ""
            print(f"{indent}├─ {node['role']}{name_info} ({node['id']})")
    
    def print_dom_path(self, dom_node_id: int):
        """Print DOM path (tag hierarchy) to a node"""
        ancestors = self.walk_ancestors(dom_node_id, 'dom')
        if not ancestors:
            print(f"Node {dom_node_id} not found")
            return
        
        # Reverse to go from root to target
        path = list(reversed(ancestors))
        
        print("\n📁 DOM PATH (tag hierarchy):")
        for i, node in enumerate(path):
            indent = "  " * i
            id_info = f" id='{node.get('id', '')}'" if node.get('id') else ""
            class_info = f" class='{node.get('class', '')}'" if node.get('class') else ""
            print(f"{indent}├─ {node['tag']}{id_info}{class_info}")
    
    def resolve_duplicate_names(self) -> Dict[str, List[AXNode]]:
        """Find and resolve duplicate accessible names"""
        duplicates = {}
        for name, nodes in self.name_index.items():
            if len(nodes) > 1:
                duplicates[name] = nodes
        
        return duplicates
    
    def _node_to_dict(self, node, tree: str) -> Dict:
        """Convert node to dictionary for display"""
        if tree == 'ax':
            return {
                'id': node.node_id,
                'role': node.role,
                'name': node.name,
                'description': node.description,
                'value': node.value,
                'type': 'accessibility'
            }
        else:
            return {
                'id': node.node_id,
                'tag': node.node_name,
                'type': 'dom',
                **node.attributes
            }
    
    # === Analysis Methods ===
    
    def get_page_summary(self) -> Dict:
        """Get summary statistics"""
        # Count interactive elements by role
        interactive_roles = {'button', 'link', 'textbox', 'combobox', 'checkbox', 'radio', 'slider'}
        interactive = {}
        for role, nodes in self.role_index.items():
            if role in interactive_roles:
                interactive[role] = len(nodes)
        
        # Find main landmarks
        landmarks = {}
        for role in {'banner', 'navigation', 'main', 'complementary', 'contentinfo', 'search'}:
            landmarks[role] = len(self.role_index.get(role, []))
        
        return {
            'total_dom_nodes': len(self.dom_nodes),
            'total_ax_nodes': len(self.ax_nodes),
            'interactive_elements': interactive,
            'landmarks': landmarks,
            'forms': len(self.role_index.get('form', [])),
            'headings': len(self.role_index.get('heading', [])),
            'images': len(self.role_index.get('image', [])),
            'duplicate_names': len(self.resolve_duplicate_names()),
        }
    
    def find_primary_action(self) -> Optional[AXNode]:
        """Find the primary action element (main button/CTA)"""
        # Look for prominent buttons
        buttons = self.role_index.get('button', [])
        
        # Filter by name (skip empty)
        named_buttons = [b for b in buttons if b.name]
        
        # Look for common CTA phrases
        cta_phrases = ['submit', 'sign up', 'sign in', 'login', 'register', 'buy', 'purchase', 'checkout']
        for button in named_buttons:
            name_lower = button.name.lower()
            for phrase in cta_phrases:
                if phrase in name_lower:
                    return button
        
        # Return first named button
        return named_buttons[0] if named_buttons else None


# === Quick CLI Usage ===

def main():
    """Command line interface"""
    import sys
    
    # Use current session directory
    session_dir = "/data/data/com.termux/files/home/automation/chrome-launcher/memory/session_20260731_061442"
    
    if not os.path.exists(session_dir):
        print(f"Session directory not found: {session_dir}")
        return
    
    print("🔍 Loading DOM & Accessibility data...")
    analyzer = DOMAccessibilityAnalyzer(session_dir)
    
    print(f"\n📊 Page Summary:")
    summary = analyzer.get_page_summary()
    for key, value in summary.items():
        if isinstance(value, dict):
            print(f"  {key}:")
            for k, v in value.items():
                print(f"    {k}: {v}")
        else:
            print(f"  {key}: {value}")
    
    # Find interactive elements
    print("\n🎯 Interactive Elements:")
    for role in ['button', 'link', 'textbox']:
        nodes = analyzer.find_by_role(role)
        if nodes:
            print(f"  {role}s ({len(nodes)}):")
            for node in nodes[:5]:  # Show first 5
                name = node.name if node.name else '[no name]'
                print(f"    - {name}")
    
    # Find primary action
    primary = analyzer.find_primary_action()
    if primary:
        print(f"\n⭐ Primary Action: {primary.role} '{primary.name}'")
    
    # Check for duplicates
    duplicates = analyzer.resolve_duplicate_names()
    if duplicates:
        print(f"\n⚠️  Duplicate accessible names found: {len(duplicates)}")
        for name, nodes in list(duplicates.items())[:3]:
            print(f"  '{name}': {len(nodes)} nodes")
    
    # Example: walk semantic path for a button
    buttons = analyzer.find_by_role('button')
    if buttons:
        print("\n🔍 Example: Semantic path for first button")
        analyzer.print_semantic_path(buttons[0].node_id)
    
    # Example: map to DOM
    if buttons:
        button = buttons[0]
        dom_node = analyzer.map_ax_to_dom(button.node_id)
        if dom_node:
            print(f"\n📁 DOM node: {dom_node.node_name}")
            analyzer.print_dom_path(dom_node.node_id)
    
    # Interactive query mode
    print("\n" + "=" * 50)
    print("Interactive query mode. Type 'help' for commands.")
    print("=" * 50)
    
    while True:
        try:
            cmd = input("\n> ").strip().lower()
            if not cmd:
                continue
            
            if cmd == 'exit' or cmd == 'quit':
                break
            
            elif cmd == 'help':
                print("\nCommands:")
                print("  find <name>        - Find by accessible name")
                print("  role <role>        - Find by role")
                print("  path ax <id>       - Show semantic path")
                print("  path dom <id>      - Show DOM path")
                print("  map ax <id>        - Map AX to DOM")
                print("  map dom <id>       - Map DOM to AX")
                print("  summary            - Show summary")
                print("  duplicates         - Show duplicate names")
                print("  exit/quit          - Exit")
            
            elif cmd.startswith('find '):
                name = cmd[5:]
                results = analyzer.find_by_accessible_name(name)
                if results:
                    print(f"\nFound {len(results)} nodes:")
                    for node in results[:10]:
                        print(f"  {node.role}: '{node.name}' ({node.node_id})")
                else:
                    print("No results found")
            
            elif cmd.startswith('role '):
                role = cmd[5:]
                results = analyzer.find_by_role(role)
                if results:
                    print(f"\nFound {len(results)} nodes:")
                    for node in results[:10]:
                        print(f"  {node.role}: '{node.name}' ({node.node_id})")
                else:
                    print("No results found")
            
            elif cmd.startswith('path ax '):
                ax_id = cmd[8:].strip()
                analyzer.print_semantic_path(ax_id)
            
            elif cmd.startswith('path dom '):
                try:
                    dom_id = int(cmd[8:].strip())
                    analyzer.print_dom_path(dom_id)
                except ValueError:
                    print("Invalid DOM node ID")
            
            elif cmd.startswith('map ax '):
                ax_id = cmd[7:].strip()
                dom_node = analyzer.map_ax_to_dom(ax_id)
                if dom_node:
                    print(f"AX {ax_id} -> DOM {dom_node.node_id} ({dom_node.node_name})")
                else:
                    print("No mapping found")
            
            elif cmd.startswith('map dom '):
                try:
                    dom_id = int(cmd[7:].strip())
                    ax_node = analyzer.map_dom_to_ax(dom_id)
                    if ax_node:
                        print(f"DOM {dom_id} -> AX {ax_node.node_id} ({ax_node.role})")
                    else:
                        print("No mapping found")
                except ValueError:
                    print("Invalid DOM node ID")
            
            elif cmd == 'summary':
                summary = analyzer.get_page_summary()
                print("\n📊 Summary:")
                for key, value in summary.items():
                    if isinstance(value, dict):
                        print(f"  {key}:")
                        for k, v in value.items():
                            print(f"    {k}: {v}")
                    else:
                        print(f"  {key}: {value}")
            
            elif cmd == 'duplicates':
                duplicates = analyzer.resolve_duplicate_names()
                if duplicates:
                    print(f"\n⚠️  {len(duplicates)} duplicate names:")
                    for name, nodes in list(duplicates.items())[:10]:
                        roles = [n.role for n in nodes]
                        print(f"  '{name}': {len(nodes)} nodes ({', '.join(roles)})")
                else:
                    print("No duplicate names found")
            
            else:
                print(f"Unknown command: {cmd}. Type 'help' for commands.")
        
        except KeyboardInterrupt:
            print("\nExiting...")
            break
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    main()
