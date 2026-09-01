#!/usr/bin/env python3
"""
ONE ANALYZER TO RULE THEM ALL
- Analyzes ANY session
- Discovers patterns without assumptions
- Gives human-readable output
- Extracts actionable data
- Works for ANY website
"""

import json
import sys
import re
from pathlib import Path
from typing import Dict, Any, List, Set
from collections import Counter, defaultdict
from datetime import datetime

class OneAnalyzer:
    """The one analyzer that does everything"""
    
    def __init__(self):
        self.texts = []
        self.headings = []
        self.links = []
        self.actions = []
        self.patterns = {}
        self.stats = {}
        self.extracted = {}
    
    def analyze(self, session_path: str) -> Dict:
        """Analyze a session and return everything"""
        session_path = Path(session_path)
        
        # Find and load DOM data
        dom_files = list(session_path.glob('dom_trees/dom_*.json')) + list(session_path.glob('dom_*.json'))
        if not dom_files:
            return {'error': 'No DOM data found'}
        
        with open(dom_files[0], 'r') as f:
            raw = json.load(f)
            dom_data = raw.get('data', raw)
        
        # Extract everything
        self._extract_all(dom_data)
        
        # Discover patterns
        self._discover_patterns()
        
        # Extract structured data
        self._extract_structured()
        
        # Generate report
        return self._generate_report()
    
    def _extract_all(self, data: Any):
        """Extract ALL data from the DOM"""
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
        
        # Process nodes
        for node in nodes:
            tag = node.get('nodeName', '').lower()
            text = self._get_text(node)
            
            # Skip technical text
            if not text or self._is_technical(text):
                continue
            
            # Categorize
            if tag in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                self.headings.append(f"{tag}: {text}")
            elif tag == 'a':
                attrs = self._get_attrs(node)
                href = attrs.get('href', '')
                if href and not href.startswith(('#', 'javascript:')):
                    self.links.append(f"{text} → {href}" if text else href)
            elif tag in ['button', 'input', 'select', 'textarea']:
                attrs = self._get_attrs(node)
                action_type = self._get_action_type(tag, attrs)
                self.actions.append({
                    'text': text,
                    'type': action_type,
                    'tag': tag
                })
            else:
                # Regular text
                if len(text) > 3:
                    self.texts.append(text)
    
    def _get_text(self, node: Dict) -> str:
        """Get text from node"""
        if node.get('nodeType') == 3:
            return node.get('nodeValue', '').strip()
        
        attrs = self._get_attrs(node)
        for key in ['aria-label', 'title', 'placeholder', 'value']:
            if key in attrs and attrs[key]:
                return attrs[key].strip()
        
        # Check children
        texts = []
        for child_id in node.get('childIds', []):
            # We'd need to look up child nodes
            pass
        
        return ''
    
    def _get_attrs(self, node: Dict) -> Dict:
        """Get attributes"""
        attrs = {}
        attr_list = node.get('attributes', [])
        if isinstance(attr_list, list):
            for i in range(0, len(attr_list), 2):
                if i+1 < len(attr_list):
                    attrs[attr_list[i]] = attr_list[i+1]
        return attrs
    
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
        if re.match(r'^[\d\s\-_.,;:!?]+$', text):  # symbols only
            return True
        return False
    
    def _get_action_type(self, tag: str, attrs: Dict) -> str:
        """Determine action type"""
        if tag == 'button':
            return 'submit' if attrs.get('type') == 'submit' else 'click'
        elif tag == 'a':
            return 'navigate'
        elif tag == 'input':
            input_type = attrs.get('type', 'text')
            if input_type in ['text', 'email', 'password', 'number']:
                return 'type'
            elif input_type == 'submit':
                return 'submit'
            return 'input'
        elif tag == 'select':
            return 'select'
        elif tag == 'textarea':
            return 'type'
        return 'interact'
    
    def _discover_patterns(self):
        """Discover patterns from text"""
        all_text = ' '.join(self.texts).lower()
        
        # Find common phrases (discovered, not assumed)
        phrases = defaultdict(int)
        words = all_text.split()
        for i in range(len(words) - 1):
            phrase = ' '.join(words[i:i+2])
            if len(phrase) > 3:
                phrases[phrase] += 1
            if i + 2 < len(words):
                phrase = ' '.join(words[i:i+3])
                if len(phrase) > 3:
                    phrases[phrase] += 1
        
        self.patterns['common_phrases'] = dict(sorted(phrases.items(), key=lambda x: x[1], reverse=True)[:20])
        
        # Find what the page is about
        word_freq = Counter(w for w in words if len(w) > 3)
        self.patterns['top_words'] = word_freq.most_common(20)
        
        # Determine page type from discovered words
        if any(w in word_freq for w in ['job', 'jobs', 'hiring', 'career', 'opportunity']):
            self.stats['page_type'] = 'job_listing'
        elif any(w in word_freq for w in ['blog', 'article', 'post', 'news']):
            self.stats['page_type'] = 'blog'
        elif any(w in word_freq for w in ['login', 'sign', 'register', 'account']):
            self.stats['page_type'] = 'auth'
        else:
            self.stats['page_type'] = 'content'
    
    def _extract_structured(self):
        """Extract structured data (discovered patterns, not hardcoded)"""
        all_text = ' '.join(self.texts)
        
        # Find numbers (discovered, not assumed to be salary)
        numbers = re.findall(r'\d+[-–]\d+|\d+\+', all_text)
        if numbers:
            self.extracted['numbers'] = list(set(numbers))[:10]
        
        # Find potential names (2+ capital words)
        names = re.findall(r'\b[A-Z][a-z]+ [A-Z][a-z]+\b', all_text)
        if names:
            self.extracted['names'] = list(set(names))[:10]
        
        # Find URLs
        urls = re.findall(r'https?://[^\s]+', all_text)
        if urls:
            self.extracted['urls'] = list(set(urls))[:5]
        
        # Find emails
        emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', all_text)
        if emails:
            self.extracted['emails'] = list(set(emails))[:5]
        
        # Find companies (discovered by looking for common patterns)
        # Check if we have job-related content
        if self.stats.get('page_type') == 'job_listing':
            # Look for potential company names (capitalized words followed by company suffix)
            company_pattern = re.compile(r'\b([A-Z][a-zA-Z]+)\s+(Inc|Ltd|LLC|Corp|Technologies|Solutions|Services|Consulting|Group|Partners|Ventures)\b')
            companies = company_pattern.findall(all_text)
            if companies:
                self.extracted['companies'] = list(set([f"{c[0]} {c[1]}" for c in companies]))[:10]
            
            # Look for salary-like patterns
            salary_pattern = re.compile(r'(\d+[-–]\d+|\d+\+)\s*(?:Lacs?|Lakhs?)\s*(?:P\.A\.|PA)', re.IGNORECASE)
            salaries = salary_pattern.findall(all_text)
            if salaries:
                self.extracted['salaries'] = list(set(salaries))[:10]
    
    def _generate_report(self) -> Dict:
        """Generate complete report"""
        return {
            'page_type': self.stats.get('page_type', 'unknown'),
            'total_texts': len(self.texts),
            'total_headings': len(self.headings),
            'total_links': len(self.links),
            'total_actions': len(self.actions),
            'headings': self.headings[:10],
            'links': self.links[:10],
            'actions': self.actions[:20],
            'patterns': self.patterns,
            'extracted': self.extracted,
            'summary': self._generate_summary()
        }
    
    def _generate_summary(self) -> str:
        """Generate human-readable summary"""
        lines = []
        lines.append(f"📌 PAGE TYPE: {self.stats.get('page_type', 'unknown').upper()}")
        lines.append("")
        
        if self.headings:
            lines.append("📋 HEADINGS:")
            for h in self.headings[:5]:
                lines.append(f"   • {h}")
            lines.append("")
        
        if self.actions:
            lines.append("⚡ ACTIONS:")
            for action in self.actions[:10]:
                lines.append(f"   • {action['text']} ({action['type']})")
            lines.append("")
        
        if self.extracted:
            lines.append("📊 EXTRACTED:")
            for key, values in self.extracted.items():
                if values:
                    lines.append(f"   {key}: {', '.join(str(v) for v in values[:5])}")
            lines.append("")
        
        # What can you do
        if self.actions:
            lines.append("💡 YOU CAN:")
            types = Counter(a['type'] for a in self.actions)
            for action_type, count in types.most_common():
                if action_type == 'click':
                    lines.append(f"   • Click on {count} elements")
                elif action_type == 'type':
                    lines.append(f"   • Type into {count} fields")
                elif action_type == 'navigate':
                    lines.append(f"   • Navigate via {count} links")
                elif action_type == 'submit':
                    lines.append(f"   • Submit {count} forms")
        
        return '\n'.join(lines)


def main():
    import sys
    from pathlib import Path
    
    print("🧠 ONE ANALYZER")
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
    analyzer = OneAnalyzer()
    result = analyzer.analyze(str(session_path))
    
    if 'error' in result:
        print(f"❌ {result['error']}")
        return
    
    print("\n" + "="*60)
    print(result['summary'])
    print("\n" + "="*60)
    
    # Save results
    output_file = session_path / 'one_analysis.json'
    with open(output_file, 'w') as f:
        json.dump(result, f, indent=2, default=str)
    print(f"\n💾 Saved to: {output_file}")

if __name__ == "__main__":
    main()
