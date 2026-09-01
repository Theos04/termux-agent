#!/usr/bin/env python3
"""
TRULY UNIVERSAL SESSION ANALYZER
No hardcoded patterns - discovers structure dynamically
Works for ANY website: YouTube, Naukri, Amazon, Twitter, etc.
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Set, Union
from collections import Counter, defaultdict
import re

class UniversalAnalyzer:
    """
    Analyzes ANY session data without assumptions about content.
    Discovers patterns, structure, and insights dynamically.
    """
    
    def __init__(self):
        self.data = {}
        self.metrics = {
            'dom_nodes': 0,
            'ax_nodes': 0,
            'text_snippets': 0,
            'unique_texts': 0,
            'structure_types': Counter(),
            'attributes_found': Counter(),
            'text_domains': Counter(),
            'discovered_patterns': {}
        }
        self.all_texts = []
        self.node_samples = []
    
    def analyze_session(self, session_path: str) -> Dict:
        """Analyze a session by discovering its structure"""
        self.session_path = Path(session_path)
        print(f"\n🔍 Analyzing: {self.session_path.name}")
        print("="*60)
        
        # Find all JSON files
        json_files = list(self.session_path.glob('**/*.json'))
        
        # Exclude metadata files
        exclude = ['analysis_results.json', 'index.json', 'state.json', 
                  'universal_analysis.json']
        json_files = [f for f in json_files if f.name not in exclude]
        
        print(f"📄 Found {len(json_files)} data files")
        
        for filepath in json_files:
            self._process_file(filepath)
        
        self._discover_structure()
        return self.metrics
    
    def _process_file(self, filepath: Path):
        """Process a single JSON file - discover its structure"""
        try:
            with open(filepath, 'r') as f:
                raw = json.load(f)
            
            # Extract actual data (handle wrappers)
            data = self._unwrap_data(raw)
            
            # Determine what type of data this is
            data_type = self._detect_data_type(data)
            self.metrics['structure_types'][data_type] += 1
            
            # Store sample
            self.node_samples.append({
                'file': filepath.name,
                'type': data_type,
                'keys': list(data.keys()) if isinstance(data, dict) else 'list',
                'sample': str(data)[:200]
            })
            
            # Count nodes
            node_count = self._count_nodes(data)
            if data_type == 'dom':
                self.metrics['dom_nodes'] += node_count
            elif data_type == 'accessibility':
                self.metrics['ax_nodes'] += node_count
            
            # Extract ALL text
            texts = self._extract_all_text(data)
            self.all_texts.extend(texts)
            self.metrics['text_snippets'] += len(texts)
            
            # Find attributes/keys
            if isinstance(data, dict):
                for key in data.keys():
                    self.metrics['attributes_found'][key] += 1
                
                # Look for nested keys
                for value in data.values():
                    if isinstance(value, dict):
                        for subkey in value.keys():
                            self.metrics['attributes_found'][f"{key}.{subkey}"] += 1
            
            print(f"  ✅ {filepath.name}: {data_type} ({node_count} nodes, {len(texts)} texts)")
            
        except Exception as e:
            print(f"  ⚠️ Error processing {filepath.name}: {e}")
    
    def _unwrap_data(self, data: Any, depth: int = 0) -> Any:
        """Unwrap common wrapper patterns recursively"""
        if depth > 5:
            return data
        
        if isinstance(data, dict):
            # Common wrapper keys
            for wrapper in ['data', 'result', 'root', 'value', 'response']:
                if wrapper in data:
                    return self._unwrap_data(data[wrapper], depth + 1)
            
            # Check if it's a CDP response
            if 'result' in data and isinstance(data['result'], dict):
                return self._unwrap_data(data['result'], depth + 1)
        
        return data
    
    def _detect_data_type(self, data: Any) -> str:
        """Detect what type of data this is by structure, not content"""
        if isinstance(data, dict):
            # DOM detection
            if 'nodeId' in data or 'nodeType' in data:
                if 'children' in data:
                    return 'dom'
                return 'dom_node'
            
            # Accessibility detection
            if 'nodes' in data and isinstance(data['nodes'], list):
                if data['nodes'] and 'role' in data['nodes'][0]:
                    return 'accessibility'
                return 'node_list'
            
            # Snapshot detection
            if 'domNodes' in data or 'layoutTree' in data:
                return 'snapshot'
            
            # Generic structure
            if len(data) > 0:
                return f"dict_{len(data)}"
            return 'empty_dict'
        
        elif isinstance(data, list):
            if data and isinstance(data[0], dict):
                return f"list_of_dicts"
            return f"list_{len(data)}"
        
        else:
            return type(data).__name__
    
    def _count_nodes(self, data: Any) -> int:
        """Count nodes in ANY structure dynamically"""
        if isinstance(data, dict):
            count = 1
            for value in data.values():
                count += self._count_nodes(value)
            return count
        elif isinstance(data, list):
            return sum(self._count_nodes(item) for item in data)
        else:
            return 0
    
    def _extract_all_text(self, data: Any, depth: int = 0) -> List[str]:
        """Extract ALL text without assumptions about field names"""
        if depth > 20:
            return []
        
        texts = []
        
        if isinstance(data, dict):
            for key, value in data.items():
                # Skip large structures to avoid recursion depth
                if key in ['children', 'nodes', 'childNodes']:
                    continue
                
                # If value is string, add it
                if isinstance(value, str) and value.strip():
                    texts.append(value.strip())
                
                # Recurse
                texts.extend(self._extract_all_text(value, depth + 1))
            
            # Special handling for children/nodes
            for key in ['children', 'nodes', 'childNodes']:
                if key in data and isinstance(data[key], list):
                    for item in data[key]:
                        texts.extend(self._extract_all_text(item, depth + 1))
        
        elif isinstance(data, list):
            for item in data:
                texts.extend(self._extract_all_text(item, depth + 1))
        
        return texts
    
    def _discover_structure(self):
        """Discover patterns and structure dynamically"""
        print("\n" + "="*60)
        print("📊 DISCOVERED STRUCTURE")
        print("="*60)
        
        # 1. Text analysis
        self._analyze_texts()
        
        # 2. Detect structure patterns
        self._detect_patterns()
        
        # 3. Generate insights
        self._generate_insights()
    
    def _analyze_texts(self):
        """Analyze text without assumptions"""
        if not self.all_texts:
            return
        
        self.metrics['unique_texts'] = len(set(self.all_texts))
        
        # Find common text patterns (discovered, not assumed)
        text_lengths = [len(t) for t in self.all_texts]
        
        self.metrics['text_stats'] = {
            'total': len(self.all_texts),
            'unique': len(set(self.all_texts)),
            'min_length': min(text_lengths),
            'max_length': max(text_lengths),
            'avg_length': sum(text_lengths) / len(text_lengths)
        }
        
        # Find common words (discover domains)
        all_words = []
        for text in self.all_texts:
            words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
            all_words.extend(words)
        
        word_freq = Counter(all_words)
        self.metrics['common_words'] = word_freq.most_common(20)
        
        # Detect if this might be a job site from discovered words
        job_indicators = {'job', 'hiring', 'position', 'salary', 'experience'}
        if job_indicators.intersection(set(word_freq.keys())):
            self.metrics['discovered_domain'] = 'job_site'
        
        # Detect if this might be social media
        social_indicators = {'like', 'comment', 'share', 'follow', 'subscribe'}
        if social_indicators.intersection(set(word_freq.keys())):
            self.metrics['discovered_domain'] = 'social_media'
        
        # Detect if this might be e-commerce
        ecommerce_indicators = {'cart', 'price', 'buy', 'checkout', 'delivery'}
        if ecommerce_indicators.intersection(set(word_freq.keys())):
            self.metrics['discovered_domain'] = 'ecommerce'
        
        # Detect if this might be news
        news_indicators = {'news', 'article', 'published', 'author', 'headline'}
        if news_indicators.intersection(set(word_freq.keys())):
            self.metrics['discovered_domain'] = 'news_site'
    
    def _detect_patterns(self):
        """Detect patterns from the data structure"""
        # Find what attributes are most common
        top_attrs = self.metrics['attributes_found'].most_common(20)
        
        self.metrics['discovered_patterns']['common_attributes'] = top_attrs
        
        # Detect if there's a pattern in node structures
        if self.node_samples:
            # Group by type
            types = Counter()
            for sample in self.node_samples:
                types[sample['type']] += 1
            
            self.metrics['discovered_patterns']['structure_types'] = dict(types)
    
    def _generate_insights(self):
        """Generate insights without assumptions"""
        print(f"\n🔬 INSIGHTS (Discovered, Not Assumed):")
        print("-"*40)
        
        # Data structure discovered
        struct_types = self.metrics.get('structure_types', Counter())
        if struct_types:
            print(f"📂 Data Types Found:")
            for data_type, count in struct_types.most_common():
                print(f"   • {data_type}: {count} file(s)")
        
        # Domain discovery
        domain = self.metrics.get('discovered_domain')
        if domain:
            print(f"\n🌐 Discovered Domain: {domain}")
        else:
            print(f"\n🌐 Discovered Domain: Unknown (mixed content)")
        
        # Text stats
        text_stats = self.metrics.get('text_stats', {})
        if text_stats:
            print(f"\n📝 Text Statistics:")
            print(f"   • Total snippets: {text_stats.get('total', 0)}")
            print(f"   • Unique snippets: {text_stats.get('unique', 0)}")
            print(f"   • Average length: {text_stats.get('avg_length', 0):.0f} chars")
        
        # Node counts
        print(f"\n📦 Node Counts:")
        print(f"   • DOM Nodes: {self.metrics.get('dom_nodes', 0)}")
        print(f"   • Accessibility Nodes: {self.metrics.get('ax_nodes', 0)}")
        
        # Discovered patterns
        patterns = self.metrics.get('discovered_patterns', {})
        if patterns.get('common_attributes'):
            print(f"\n🏷️ Discovered Attributes (Top 5):")
            for attr, count in patterns['common_attributes'][:5]:
                print(f"   • {attr}: {count}")
        
        # Common words (context discovery)
        common_words = self.metrics.get('common_words', [])
        if common_words:
            print(f"\n📖 Discovered Vocabulary (Top 10):")
            for word, count in common_words[:10]:
                print(f"   • {word}: {count}")
    
    def save_results(self):
        """Save analysis results"""
        output_file = self.session_path / 'discovered_analysis.json'
        
        # Convert to serializable format
        serializable = {
            'metrics': {
                'dom_nodes': self.metrics.get('dom_nodes', 0),
                'ax_nodes': self.metrics.get('ax_nodes', 0),
                'text_snippets': self.metrics.get('text_snippets', 0),
                'unique_texts': self.metrics.get('unique_texts', 0),
                'discovered_domain': self.metrics.get('discovered_domain', 'unknown'),
                'structure_types': dict(self.metrics.get('structure_types', {})),
                'text_stats': self.metrics.get('text_stats', {}),
                'common_words': self.metrics.get('common_words', [])[:20],
                'discovered_patterns': {
                    'common_attributes': [
                        (k, v) for k, v in self.metrics.get('discovered_patterns', {}).get('common_attributes', [])
                    ][:10]
                }
            },
            'node_samples': self.node_samples[:5],
            'timestamp': datetime.now().isoformat()
        }
        
        with open(output_file, 'w') as f:
            json.dump(serializable, f, indent=2)
        
        print(f"\n💾 Saved to: {output_file}")


def main():
    print("🧠 TRULY UNIVERSAL SESSION ANALYZER")
    print("Discovering structure without assumptions")
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
    
    # Analyze
    analyzer = UniversalAnalyzer()
    analyzer.analyze_session(str(session_path))
    analyzer.save_results()

if __name__ == "__main__":
    main()
