#!/usr/bin/env python3
"""
HUMAN-READABLE FUNCTIONAL DISCOVERY
Extracts meaningful text and context from page elements
Shows what you can actually DO in plain English
"""

import json
import sys
import re
from pathlib import Path
from typing import Dict, Any, List, Set, Tuple
from collections import defaultdict

class HumanReadableDiscoverer:
    """
    Discovers page functionality and presents it in human-readable form
    """
    
    def __init__(self):
        self.all_nodes = []
        self.node_map = {}
        self.text_map = {}
        self.actions = []
        
    def discover(self, dom_data: Dict) -> Dict:
        """Discover and present human-readable functionality"""
        print("\n👤 DISCOVERING HUMAN-READABLE ACTIONS")
        print("="*60)
        
        # Build node map
        self._build_node_map(dom_data)
        
        # Extract meaningful actions
        self._extract_meaningful_actions()
        
        # Generate human-readable report
        return self._generate_readable_report()
    
    def _build_node_map(self, data: Any):
        """Build a map of all nodes for reference"""
        if isinstance(data, dict):
            if 'nodeId' in data:
                node_id = data.get('nodeId')
                self.node_map[node_id] = data
                
                # Store text content
                text = self._get_node_text(data)
                if text:
                    self.text_map[node_id] = text
            
            # Recurse
            for key, value in data.items():
                if key not in ['children', 'childNodes']:
                    self._build_node_map(value)
            
            # Handle children
            for key in ['children', 'childNodes']:
                if key in data and isinstance(data[key], list):
                    for child in data[key]:
                        self._build_node_map(child)
        
        elif isinstance(data, list):
            for item in data:
                self._build_node_map(item)
    
    def _get_node_text(self, node: Dict) -> str:
        """Extract readable text from a node"""
        # Check for text content
        if node.get('nodeType') == 3:  # Text node
            return node.get('nodeValue', '').strip()
        
        # Check for attribute values
        attrs = self._get_attributes(node)
        for key in ['aria-label', 'title', 'placeholder', 'value']:
            if key in attrs and attrs[key]:
                return attrs[key].strip()
        
        # Check children for text
        child_texts = []
        for child_id in node.get('childIds', []):
            if child_id in self.node_map:
                child = self.node_map[child_id]
                text = self._get_node_text(child)
                if text:
                    child_texts.append(text)
        
        if child_texts:
            return ' '.join(child_texts).strip()
        
        return ''
    
    def _get_attributes(self, node: Dict) -> Dict:
        """Extract attributes from node"""
        attrs = {}
        attr_list = node.get('attributes', [])
        if isinstance(attr_list, list):
            for i in range(0, len(attr_list), 2):
                if i+1 < len(attr_list):
                    attrs[attr_list[i]] = attr_list[i+1]
        return attrs
    
    def _get_parent_context(self, node: Dict) -> str:
        """Get context from parent elements"""
        parent_id = node.get('parentId')
        if parent_id and parent_id in self.node_map:
            parent = self.node_map[parent_id]
            parent_text = self._get_node_text(parent)
            if parent_text and len(parent_text) > 0:
                return parent_text
            
            # Check grandparent
            grandparent_id = parent.get('parentId')
            if grandparent_id and grandparent_id in self.node_map:
                grandparent = self.node_map[grandparent_id]
                grandparent_text = self._get_node_text(grandparent)
                if grandparent_text and len(grandparent_text) > 0:
                    return grandparent_text
        
        return ''
    
    def _extract_meaningful_actions(self):
        """Extract actions with meaningful text"""
        interactive_tags = {'button', 'a', 'input', 'select', 'textarea'}
        
        for node_id, node in self.node_map.items():
            tag = node.get('nodeName', '').lower()
            
            # Skip if not interactive
            if tag not in interactive_tags:
                continue
            
            # Get readable text
            text = self._get_node_text(node)
            if not text:
                continue
            
            # Skip if text is too technical
            if self._is_technical_text(text):
                continue
            
            # Get context
            context = self._get_parent_context(node)
            
            # Determine action type
            action_type = self._determine_action_type(node, tag)
            
            # Determine what this element does
            purpose = self._determine_purpose(text, context, tag)
            
            self.actions.append({
                'text': text,
                'context': context[:100] if context else '',
                'type': action_type,
                'purpose': purpose,
                'tag': tag,
                'node_id': node_id
            })
    
    def _is_technical_text(self, text: str) -> bool:
        """Check if text is technical vs human-readable"""
        # Skip if too short or just symbols
        if len(text) < 2:
            return True
        
        # Skip if it looks like technical class names
        if re.match(r'^[a-z]+[A-Z]', text):  # camelCase
            return True
        if re.match(r'^[a-z]+-[a-z]+', text):  # kebab-case
            return True
        if re.match(r'^[a-z_]+$', text):  # snake_case
            return True
        
        # Skip if it's just numbers or special chars
        if re.match(r'^[\d\s\-_.,;:!?]+$', text):
            return True
        
        return False
    
    def _determine_action_type(self, node: Dict, tag: str) -> str:
        """Determine what type of action this is"""
        attrs = self._get_attributes(node)
        
        if tag == 'button':
            if attrs.get('type') == 'submit':
                return 'Submit'
            return 'Click'
        
        elif tag == 'a':
            return 'Navigate'
        
        elif tag == 'input':
            input_type = attrs.get('type', 'text')
            if input_type in ['text', 'email', 'password', 'number']:
                return 'Type'
            elif input_type == 'submit':
                return 'Submit'
            elif input_type == 'checkbox':
                return 'Check'
            elif input_type == 'radio':
                return 'Select'
            return 'Input'
        
        elif tag == 'select':
            return 'Choose from dropdown'
        
        elif tag == 'textarea':
            return 'Type text'
        
        return 'Interact'
    
    def _determine_purpose(self, text: str, context: str, tag: str) -> str:
        """Determine what this element does based on text and context"""
        text_lower = text.lower()
        context_lower = context.lower()
        
        # Search related
        if any(kw in text_lower or kw in context_lower for kw in ['search', 'find', 'look']):
            return 'Search for content'
        
        # Apply/Submit related
        if any(kw in text_lower or kw in context_lower for kw in ['apply', 'submit', 'send', 'save']):
            return 'Submit information'
        
        # Navigation related
        if any(kw in text_lower or kw in context_lower for kw in ['home', 'back', 'next', 'prev', 'page']):
            return 'Navigate'
        
        # Login/Sign related
        if any(kw in text_lower or kw in context_lower for kw in ['login', 'sign', 'register', 'account']):
            return 'Account action'
        
        # View related
        if any(kw in text_lower or kw in context_lower for kw in ['view', 'show', 'see', 'read']):
            return 'View content'
        
        # Upload/Download related
        if any(kw in text_lower or kw in context_lower for kw in ['upload', 'download', 'import', 'export']):
            return 'File action'
        
        # Social related
        if any(kw in text_lower or kw in context_lower for kw in ['share', 'like', 'comment', 'follow']):
            return 'Social action'
        
        # If it's a button or link with text, it's likely clickable
        if tag in ['button', 'a']:
            return f'Click: {text[:30]}'
        
        return 'Interact with element'
    
    def _generate_readable_report(self) -> Dict:
        """Generate human-readable report"""
        print("\n" + "="*60)
        print("📋 HUMAN-READABLE ACTIONS")
        print("="*60)
        
        if not self.actions:
            print("  No meaningful actions discovered")
            return {'actions': []}
        
        # Group by purpose
        grouped = defaultdict(list)
        for action in self.actions:
            grouped[action['purpose']].append(action)
        
        # Print grouped actions
        print(f"\n🎯 WHAT YOU CAN DO ON THIS PAGE:")
        print("-"*40)
        
        for purpose, actions in sorted(grouped.items()):
            print(f"\n📌 {purpose} ({len(actions)}):")
            for action in actions[:5]:  # Show up to 5 per category
                text = action['text']
                if len(text) > 60:
                    text = text[:60] + '...'
                
                # Show context if available
                if action['context']:
                    context = action['context'][:60]
                    print(f"   • {text} → {context} ({action['type']})")
                else:
                    print(f"   • {text} ({action['type']})")
            
            if len(actions) > 5:
                print(f"   ... and {len(actions) - 5} more")
        
        # Generate plain English summary
        print("\n" + "="*60)
        print("📝 PLAIN ENGLISH SUMMARY")
        print("="*60)
        
        summary_lines = []
        summary_lines.append("🔍 This page allows you to:")
        
        for purpose, actions in sorted(grouped.items()):
            count = len(actions)
            if count == 1:
                summary_lines.append(f"   • {purpose} (1 element)")
            else:
                summary_lines.append(f"   • {purpose} ({count} elements)")
        
        # Add specific examples
        if self.actions:
            summary_lines.append("\n📌 For example:")
            for action in self.actions[:5]:
                text = action['text']
                if action['context']:
                    summary_lines.append(f"   • Click '{text}' (found near '{action['context'][:40]}')")
                else:
                    summary_lines.append(f"   • Click '{text}'")
        
        for line in summary_lines:
            print(line)
        
        # Return structured data
        return {
            'total_actions': len(self.actions),
            'action_categories': dict(grouped),
            'summary': '\n'.join(summary_lines),
            'actions': self.actions[:20]  # Return top 20
        }

def main():
    print("👤 HUMAN-READABLE FUNCTIONAL DISCOVERY")
    print("Extracting meaningful actions from the page")
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
    
    # Discover human-readable actions
    discoverer = HumanReadableDiscoverer()
    result = discoverer.discover(dom_data)
    
    # Save results
    output_file = session_path / 'human_readable_actions.json'
    with open(output_file, 'w') as f:
        json.dump(result, f, indent=2, default=str)
    
    print(f"\n💾 Saved to: {output_file}")

if __name__ == "__main__":
    main()
