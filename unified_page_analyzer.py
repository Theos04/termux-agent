#!/usr/bin/env python3
"""
UNIFIED PAGE ANALYZER
Combines all analysis into one simple tool:
- Extracts human-readable content
- Identifies actionable elements
- Discovers page purpose
- Works for ANY website without assumptions
"""

import json
import sys
import re
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime

@dataclass
class PageAnalysis:
    """Complete page analysis result"""
    url: str = ""
    title: str = ""
    page_type: str = "unknown"
    purpose: str = ""
    
    # Content
    text_samples: List[str] = field(default_factory=list)
    headings: List[str] = field(default_factory=list)
    links: List[str] = field(default_factory=list)
    
    # Actions
    actions: List[Dict] = field(default_factory=list)
    forms: List[Dict] = field(default_factory=list)
    
    # Extracted data (discovered, not assumed)
    extracted_data: Dict = field(default_factory=dict)
    
    # Summary
    summary: str = ""
    
    def to_dict(self) -> Dict:
        return {
            'url': self.url,
            'title': self.title,
            'page_type': self.page_type,
            'purpose': self.purpose,
            'text_samples': self.text_samples[:10],
            'headings': self.headings[:20],
            'links': self.links[:20],
            'actions': self.actions[:20],
            'forms': self.forms[:10],
            'extracted_data': self.extracted_data,
            'summary': self.summary
        }

class UnifiedPageAnalyzer:
    """One analyzer to rule them all"""
    
    def analyze(self, dom_data: Dict, url: str = "") -> PageAnalysis:
        """Analyze page and return human-readable results"""
        result = PageAnalysis()
        result.url = url
        
        # Extract all nodes
        nodes = self._extract_nodes(dom_data)
        
        # Extract title
        result.title = self._find_title(nodes)
        
        # Extract headings
        result.headings = self._extract_headings(nodes)
        
        # Extract text
        texts = self._extract_texts(nodes)
        result.text_samples = texts[:20]
        
        # Extract links
        result.links = self._extract_links(nodes)
        
        # Extract actions
        result.actions = self._extract_actions(nodes)
        
        # Extract forms
        result.forms = self._extract_forms(nodes)
        
        # Detect page type (discovered from content, not assumed)
        result.page_type = self._detect_page_type(texts, result.headings, result.links)
        
        # Determine purpose
        result.purpose = self._determine_purpose(result)
        
        # Extract structured data (discovered from patterns)
        result.extracted_data = self._extract_structured_data(texts)
        
        # Generate summary
        result.summary = self._generate_summary(result)
        
        return result
    
    def _extract_nodes(self, data: Any) -> List[Dict]:
        """Extract all nodes from DOM"""
        nodes = []
        
        def walk(node):
            if isinstance(node, dict):
                if 'nodeId' in node:
                    nodes.append(node)
                for key, value in node.items():
                    if key not in ['children', 'childNodes']:
                        walk(value)
                for key in ['children', 'childNodes']:
                    if key in node and isinstance(node[key], list):
                        for child in node[key]:
                            walk(child)
            elif isinstance(node, list):
                for item in node:
                    walk(item)
        
        walk(data)
        return nodes
    
    def _get_attrs(self, node: Dict) -> Dict:
        """Get attributes from node"""
        attrs = {}
        attr_list = node.get('attributes', [])
        if isinstance(attr_list, list):
            for i in range(0, len(attr_list), 2):
                if i+1 < len(attr_list):
                    attrs[attr_list[i]] = attr_list[i+1]
        return attrs
    
    def _get_node_text(self, node: Dict) -> str:
        """Get text from node"""
        if node.get('nodeType') == 3:
            return node.get('nodeValue', '').strip()
        
        attrs = self._get_attrs(node)
        for key in ['aria-label', 'title', 'placeholder', 'value']:
            if key in attrs and attrs[key]:
                return attrs[key].strip()
        
        return ''
    
    def _find_title(self, nodes: List[Dict]) -> str:
        """Find page title"""
        for node in nodes:
            tag = node.get('nodeName', '').lower()
            if tag == 'title':
                # Get text from children
                for child_id in node.get('childIds', []):
                    for n in nodes:
                        if n.get('nodeId') == child_id:
                            if n.get('nodeType') == 3:
                                return n.get('nodeValue', '').strip()
        
        # Look for h1
        for node in nodes:
            tag = node.get('nodeName', '').lower()
            if tag == 'h1':
                text = self._get_node_text(node)
                if text:
                    return text
        
        return "Untitled"
    
    def _extract_headings(self, nodes: List[Dict]) -> List[str]:
        """Extract all headings (h1-h6)"""
        headings = []
        for node in nodes:
            tag = node.get('nodeName', '').lower()
            if tag in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                text = self._get_node_text(node)
                if text and len(text) > 2:
                    headings.append(f"{tag}: {text}")
        return headings
    
    def _extract_texts(self, nodes: List[Dict]) -> List[str]:
        """Extract all meaningful text"""
        texts = []
        seen = set()
        
        for node in nodes:
            if node.get('nodeType') == 3:
                text = node.get('nodeValue', '').strip()
                if text and len(text) > 2:
                    # Skip if too technical
                    if not self._is_technical(text):
                        if text not in seen:
                            seen.add(text)
                            texts.append(text)
        
        return texts
    
    def _is_technical(self, text: str) -> bool:
        """Check if text is technical"""
        if len(text) < 3:
            return True
        if re.match(r'^[a-z]+[A-Z]', text):  # camelCase
            return True
        if re.match(r'^[a-z]+-[a-z]+', text):  # kebab-case
            return True
        if re.match(r'^[a-z_]+$', text):  # snake_case
            return True
        if re.match(r'^[\d\s\-_.,;:!?]+$', text):  # only symbols
            return True
        return False
    
    def _extract_links(self, nodes: List[Dict]) -> List[str]:
        """Extract all links with text"""
        links = []
        for node in nodes:
            tag = node.get('nodeName', '').lower()
            if tag == 'a':
                attrs = self._get_attrs(node)
                href = attrs.get('href', '')
                text = self._get_node_text(node)
                if href and not href.startswith(('javascript:', '#')):
                    if text:
                        links.append(f"{text} → {href[:50]}")
                    else:
                        links.append(f"Link: {href[:50]}")
        return links
    
    def _extract_actions(self, nodes: List[Dict]) -> List[Dict]:
        """Extract actionable elements"""
        actions = []
        interactive = {'button', 'a', 'input', 'select', 'textarea'}
        
        for node in nodes:
            tag = node.get('nodeName', '').lower()
            if tag in interactive:
                text = self._get_node_text(node)
                if not text or self._is_technical(text):
                    continue
                
                attrs = self._get_attrs(node)
                action_type = 'click'
                if tag == 'input':
                    input_type = attrs.get('type', 'text')
                    if input_type in ['text', 'email', 'password']:
                        action_type = 'type'
                    elif input_type == 'submit':
                        action_type = 'submit'
                elif tag == 'select':
                    action_type = 'select'
                elif tag == 'textarea':
                    action_type = 'type'
                
                actions.append({
                    'text': text,
                    'type': action_type,
                    'tag': tag,
                    'attributes': {k: v[:50] for k, v in list(attrs.items())[:3]}
                })
        
        return actions
    
    def _extract_forms(self, nodes: List[Dict]) -> List[Dict]:
        """Extract forms"""
        forms = []
        for node in nodes:
            if node.get('nodeName', '').lower() == 'form':
                attrs = self._get_attrs(node)
                forms.append({
                    'id': attrs.get('id', ''),
                    'action': attrs.get('action', ''),
                    'method': attrs.get('method', 'get'),
                })
        return forms
    
    def _detect_page_type(self, texts: List[str], headings: List[str], links: List[str]) -> str:
        """Detect page type from content"""
        all_text = ' '.join(texts).lower()
        all_heading = ' '.join(headings).lower()
        
        # Job site detection
        job_indicators = ['job', 'hiring', 'position', 'salary', 'experience', 'opportunity']
        if any(kw in all_text or kw in all_heading for kw in job_indicators):
            return 'job_listing'
        
        # Blog/News
        blog_indicators = ['blog', 'article', 'news', 'published']
        if any(kw in all_text or kw in all_heading for kw in blog_indicators):
            return 'blog'
        
        # Dashboard
        dashboard_indicators = ['dashboard', 'profile', 'account']
        if any(kw in all_text or kw in all_heading for kw in dashboard_indicators):
            return 'dashboard'
        
        # Login
        if 'login' in all_text or 'sign in' in all_text:
            return 'login'
        
        return 'content'
    
    def _determine_purpose(self, analysis: PageAnalysis) -> str:
        """Determine page purpose"""
        if analysis.page_type == 'job_listing':
            return 'Browse and apply for job opportunities'
        elif analysis.page_type == 'blog':
            return 'Read articles and blog posts'
        elif analysis.page_type == 'dashboard':
            return 'Manage account and view activities'
        elif analysis.page_type == 'login':
            return 'Authenticate user'
        
        # Check for specific actions
        if analysis.actions:
            first_action = analysis.actions[0]['text']
            if 'search' in first_action.lower():
                return 'Search for content'
            if 'apply' in first_action.lower():
                return 'Apply for opportunities'
        
        return 'Browse content'
    
    def _extract_structured_data(self, texts: List[str]) -> Dict:
        """Extract structured data from text (discovered, not assumed)"""
        result = {}
        
        # Find patterns in text
        all_text = ' '.join(texts)
        
        # Extract numbers
        numbers = re.findall(r'\d+[-–]\d+|\d+\+', all_text)
        if numbers:
            result['numbers'] = list(set(numbers))[:10]
        
        # Extract potential names (capitalized words)
        names = re.findall(r'\b[A-Z][a-z]+ [A-Z][a-z]+\b', all_text)
        if names:
            result['names'] = list(set(names))[:10]
        
        # Extract URLs
        urls = re.findall(r'https?://[^\s]+', all_text)
        if urls:
            result['urls'] = urls[:5]
        
        # Extract email-like patterns
        emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', all_text)
        if emails:
            result['emails'] = emails[:5]
        
        return result
    
    def _generate_summary(self, analysis: PageAnalysis) -> str:
        """Generate human-readable summary"""
        lines = []
        lines.append(f"📌 PAGE: {analysis.title}")
        lines.append(f"📂 TYPE: {analysis.page_type}")
        lines.append(f"🎯 PURPOSE: {analysis.purpose}")
        
        if analysis.headings:
            lines.append(f"\n📋 HEADINGS:")
            for h in analysis.headings[:5]:
                lines.append(f"   • {h}")
        
        if analysis.actions:
            lines.append(f"\n⚡ ACTIONS:")
            for action in analysis.actions[:10]:
                lines.append(f"   • {action['text']} ({action['type']})")
        
        if analysis.links:
            lines.append(f"\n🔗 LINKS:")
            for link in analysis.links[:5]:
                lines.append(f"   • {link[:60]}")
        
        if analysis.extracted_data:
            lines.append(f"\n📊 EXTRACTED DATA:")
            for key, values in analysis.extracted_data.items():
                if values:
                    lines.append(f"   • {key}: {', '.join(str(v) for v in values[:5])}")
        
        return '\n'.join(lines)

def analyze_session(session_path: str) -> PageAnalysis:
    """Analyze a session and return human-readable results"""
    session_path = Path(session_path)
    
    # Find DOM file
    dom_files = list(session_path.glob('dom_trees/dom_*.json')) + list(session_path.glob('dom_*.json'))
    if not dom_files:
        print("❌ No DOM data found")
        return None
    
    # Load DOM data
    with open(dom_files[0], 'r') as f:
        raw = json.load(f)
        dom_data = raw.get('data', raw)
    
    # Analyze
    analyzer = UnifiedPageAnalyzer()
    result = analyzer.analyze(dom_data)
    
    # Try to get URL from metadata
    index_file = session_path / 'index.json'
    if index_file.exists():
        with open(index_file, 'r') as f:
            index = json.load(f)
            if 'metadata' in index and 'url' in index['metadata']:
                result.url = index['metadata']['url']
    
    return result

def main():
    import sys
    from pathlib import Path
    
    print("🧠 UNIFIED PAGE ANALYZER")
    print("="*60)
    
    # Find sessions
    memory_dir = Path('/data/data/com.termux/files/home/automation/chrome-launcher/memory')
    sessions = sorted(memory_dir.glob('session_*'), key=lambda x: x.stat().st_mtime, reverse=True)
    
    if sessions:
        print("\n📂 Recent sessions:")
        for i, session in enumerate(sessions[:5]):
            print(f"  [{i}] {session.name}")
        
        choice = input("\nSelect session [0-4]: ").strip()
        
        if choice.isdigit():
            idx = int(choice)
            if 0 <= idx < len(sessions):
                session_path = sessions[idx]
            else:
                print("❌ Invalid selection")
                return
        else:
            session_path = sessions[0] if not choice else Path(choice)
    else:
        session_path = Path(input("📁 Enter session path: ").strip())
    
    if not session_path.exists():
        print(f"❌ Session not found: {session_path}")
        return
    
    # Analyze
    print(f"\n🔍 Analyzing: {session_path.name}")
    result = analyze_session(str(session_path))
    
    if result:
        print("\n" + "="*60)
        print(result.summary)
        print("\n" + "="*60)
        
        # Save results
        output_file = session_path / 'unified_analysis.json'
        with open(output_file, 'w') as f:
            json.dump(result.to_dict(), f, indent=2, default=str)
        print(f"\n💾 Saved to: {output_file}")
        
        # Print extracted data
        if result.extracted_data:
            print("\n📊 EXTRACTED DATA:")
            for key, values in result.extracted_data.items():
                if values:
                    print(f"   {key}:")
                    for v in values[:5]:
                        print(f"     • {v}")

if __name__ == "__main__":
    main()
