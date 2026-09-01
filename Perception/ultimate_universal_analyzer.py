#!/usr/bin/env python3
"""
ULTIMATE UNIVERSAL ANALYZER
Zero assumptions - discovers everything dynamically
No hardcoded patterns for jobs, salaries, locations, etc.
Works for ANY website: YouTube, Naukri, Amazon, Twitter, etc.
"""

import json
import sys
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Set, Union, Tuple
from collections import Counter, defaultdict
import math

class UltimateUniversalAnalyzer:
    """
    Discovers everything without assumptions:
    - What kind of data is this?
    - What patterns exist?
    - What's the content about?
    - What structure does it have?
    All discovered dynamically.
    """
    
    def __init__(self):
        self.data = {}
        self.all_texts = []
        self.all_keys = []
        self.structure_metrics = {}
        self.text_clusters = defaultdict(list)
        self.pattern_clusters = defaultdict(list)
        self.discovered_categories = {}
        
    def analyze_session(self, session_path: str) -> Dict:
        """Analyze without any assumptions"""
        self.session_path = Path(session_path)
        print(f"\n🔍 Analyzing: {self.session_path.name}")
        print("="*60)
        
        # 1. Load and unwrap all data
        json_files = list(self.session_path.glob('**/*.json'))
        exclude = ['analysis_results.json', 'index.json', 'state.json', 
                  'universal_analysis.json', 'discovered_analysis.json']
        json_files = [f for f in json_files if f.name not in exclude]
        
        print(f"📄 Found {len(json_files)} data files")
        
        for filepath in json_files:
            self._load_file(filepath)
        
        # 2. Discover patterns without assumptions
        self._discover_without_assumptions()
        
        # 3. Generate insights
        return self._generate_report()
    
    def _load_file(self, filepath: Path):
        """Load and extract data without assumptions"""
        try:
            with open(filepath, 'r') as f:
                raw = json.load(f)
            
            # Extract data (handle wrappers)
            data = self._extract_data(raw)
            
            # Store by detected type
            data_type = self._detect_type(data)
            self.data[data_type] = data
            
            # Extract ALL text
            texts = self._extract_all_texts(data)
            self.all_texts.extend(texts)
            
            # Extract ALL keys/attributes
            keys = self._extract_all_keys(data)
            self.all_keys.extend(keys)
            
            print(f"  ✅ {filepath.name}: {data_type} ({len(texts)} texts, {len(keys)} keys)")
            
        except Exception as e:
            print(f"  ⚠️ Error: {filepath.name}: {e}")
    
    def _extract_data(self, data: Any) -> Any:
        """Extract from wrappers without assumptions"""
        if isinstance(data, dict):
            # Common wrappers
            for wrapper in ['data', 'result', 'root', 'value', 'response']:
                if wrapper in data:
                    return self._extract_data(data[wrapper])
        
        return data
    
    def _detect_type(self, data: Any) -> str:
        """Detect data type by structure only"""
        if isinstance(data, dict):
            # DOM
            if 'nodeId' in data and 'children' in data:
                return 'dom'
            # Accessibility
            if 'nodes' in data and isinstance(data['nodes'], list):
                return 'accessibility'
            # Snapshot
            if 'domNodes' in data or 'layoutTree' in data:
                return 'snapshot'
            # Generic dict
            return 'dict'
        elif isinstance(data, list):
            return 'list'
        else:
            return type(data).__name__
    
    def _extract_all_texts(self, data: Any, depth: int = 0) -> List[str]:
        """Extract ALL text without assumptions about field names"""
        if depth > 20:
            return []
        
        texts = []
        
        if isinstance(data, dict):
            for key, value in data.items():
                # Skip structure fields to avoid recursion
                if key in ['children', 'nodes', 'childNodes']:
                    continue
                
                # If it's a string, add it
                if isinstance(value, str) and value.strip():
                    texts.append(value.strip())
                
                # Recurse
                texts.extend(self._extract_all_texts(value, depth + 1))
            
            # Handle children/nodes
            for key in ['children', 'nodes', 'childNodes']:
                if key in data and isinstance(data[key], list):
                    for item in data[key]:
                        texts.extend(self._extract_all_texts(item, depth + 1))
        
        elif isinstance(data, list):
            for item in data:
                texts.extend(self._extract_all_texts(item, depth + 1))
        
        return texts
    
    def _extract_all_keys(self, data: Any) -> List[str]:
        """Extract all keys/attributes without assumptions"""
        keys = []
        
        if isinstance(data, dict):
            for key in data.keys():
                keys.append(str(key))
                # Recurse
                keys.extend(self._extract_all_keys(data[key]))
        
        elif isinstance(data, list):
            for item in data:
                keys.extend(self._extract_all_keys(item))
        
        return keys
    
    def _discover_without_assumptions(self):
        """Discover everything without assumptions"""
        print("\n" + "="*60)
        print("🔬 DISCOVERING WITHOUT ASSUMPTIONS")
        print("="*60)
        
        # 1. Discover text patterns
        self._discover_text_patterns()
        
        # 2. Discover structure patterns
        self._discover_structure_patterns()
        
        # 3. Discover content categories
        self._discover_categories()
    
    def _discover_text_patterns(self):
        """Discover patterns in text without assumptions"""
        if not self.all_texts:
            return
        
        # Analyze text lengths
        lengths = [len(t) for t in self.all_texts]
        self.structure_metrics['text_lengths'] = {
            'total': len(self.all_texts),
            'unique': len(set(self.all_texts)),
            'min': min(lengths),
            'max': max(lengths),
            'avg': sum(lengths) / len(lengths) if lengths else 0,
            'median': sorted(lengths)[len(lengths)//2] if lengths else 0
        }
        
        # Find common substrings (discover patterns)
        common_phrases = self._find_common_patterns(self.all_texts)
        self.structure_metrics['common_patterns'] = common_phrases
        
        # Group texts by similarity
        self._cluster_texts()
    
    def _find_common_patterns(self, texts: List[str], min_freq: int = 3) -> Dict:
        """Find common patterns without assumptions"""
        patterns = defaultdict(int)
        
        # Look for common substrings (2-5 words)
        for text in texts:
            if len(text.split()) >= 2:
                words = text.split()
                for i in range(len(words) - 1):
                    # 2-word phrases
                    phrase = ' '.join(words[i:i+2])
                    if len(phrase) > 3:
                        patterns[phrase] += 1
                    
                    # 3-word phrases
                    if i + 2 < len(words):
                        phrase = ' '.join(words[i:i+3])
                        if len(phrase) > 3:
                            patterns[phrase] += 1
        
        # Sort by frequency and return top
        return dict(sorted(patterns.items(), key=lambda x: x[1], reverse=True)[:50])
    
    def _cluster_texts(self):
        """Group texts by similarity without assumptions"""
        # Simple clustering by first word (discover groups)
        clusters = defaultdict(list)
        for text in self.all_texts:
            first_word = text.split()[0].lower() if text.split() else ''
            if first_word:
                clusters[first_word].append(text)
        
        # Keep clusters with > 5 items
        self.text_clusters = {k: v for k, v in clusters.items() if len(v) > 5}
    
    def _discover_structure_patterns(self):
        """Discover structure patterns without assumptions"""
        # Key patterns
        key_freq = Counter(self.all_keys)
        self.structure_metrics['common_keys'] = key_freq.most_common(20)
        
        # Value patterns (by key)
        value_patterns = {}
        for key, freq in key_freq.most_common(10):
            # Find values for this key
            values = []
            # This would require deeper analysis
            value_patterns[key] = {'frequency': freq}
        
        self.structure_metrics['value_patterns'] = value_patterns
    
    def _discover_categories(self):
        """Discover categories without assumptions"""
        # 1. Discover by text length (short = labels, medium = titles, long = content)
        short = [t for t in self.all_texts if len(t) < 20]
        medium = [t for t in self.all_texts if 20 <= len(t) < 100]
        long = [t for t in self.all_texts if len(t) >= 100]
        
        self.discovered_categories['by_length'] = {
            'short (labels/names)': len(short),
            'medium (titles/phrases)': len(medium),
            'long (descriptions/content)': len(long)
        }
        
        # 2. Discover by structure (numeric, URL, etc.)
        numeric = [t for t in self.all_texts if t.replace(',', '').replace('.', '').isdigit()]
        url_pattern = re.compile(r'https?://|www\.')
        urls = [t for t in self.all_texts if url_pattern.search(t)]
        email_pattern = re.compile(r'@|\.com|\.org|\.net')
        emails = [t for t in self.all_texts if email_pattern.search(t) and '@' in t]
        
        self.discovered_categories['by_type'] = {
            'numeric_values': len(numeric),
            'urls_links': len(urls),
            'email_addresses': len(emails),
            'other_text': len(self.all_texts) - len(numeric) - len(urls) - len(emails)
        }
        
        # 3. Discover word frequencies (show what the content is about)
        all_words = []
        for text in self.all_texts:
            # Clean and split
            clean = re.sub(r'[^a-zA-Z\s]', '', text)
            words = clean.lower().split()
            all_words.extend(words)
        
        word_freq = Counter(all_words)
        # Filter out common words
        stopwords = {'the', 'be', 'to', 'of', 'and', 'a', 'in', 'that', 'have', 'i',
                    'it', 'for', 'not', 'on', 'with', 'he', 'as', 'you', 'do', 'at',
                    'this', 'but', 'his', 'by', 'from', 'they', 'we', 'say', 'her',
                    'she', 'or', 'an', 'will', 'my', 'one', 'all', 'would', 'there',
                    'their', 'what', 'so', 'up', 'out', 'if', 'about', 'who', 'get',
                    'which', 'go', 'me', 'when', 'make', 'can', 'like', 'time', 'no',
                    'just', 'him', 'know', 'take', 'people', 'into', 'year', 'your',
                    'good', 'some', 'could', 'them', 'see', 'other', 'than', 'then',
                    'now', 'look', 'only', 'come', 'its', 'over', 'think', 'also',
                    'back', 'after', 'use', 'two', 'how', 'our', 'work', 'first',
                    'well', 'way', 'even', 'new', 'want', 'because', 'any', 'these',
                    'give', 'day', 'most', 'us'}
        
        meaningful_words = {w: freq for w, freq in word_freq.items() 
                           if w not in stopwords and len(w) > 2}
        
        self.discovered_categories['top_topics'] = dict(Counter(meaningful_words).most_common(30))
    
    def _generate_report(self) -> Dict:
        """Generate report without assumptions"""
        print("\n" + "="*60)
        print("📊 DISCOVERY REPORT (No Assumptions Made)")
        print("="*60)
        
        # 1. Data Discovery
        print(f"\n📂 DATA DISCOVERED:")
        print(f"   • Total text snippets: {len(self.all_texts)}")
        print(f"   • Unique snippets: {len(set(self.all_texts))}")
        print(f"   • Files analyzed: {len(self.data)}")
        
        # 2. Structure Discovery
        print(f"\n🏗️ STRUCTURE DISCOVERED:")
        if self.structure_metrics.get('text_lengths'):
            lengths = self.structure_metrics['text_lengths']
            print(f"   • Text lengths: min={lengths['min']}, max={lengths['max']}, avg={lengths['avg']:.0f}")
            print(f"   • Median length: {lengths['median']}")
        
        if self.structure_metrics.get('common_keys'):
            print(f"\n   🔑 Most common keys/attributes:")
            for key, freq in self.structure_metrics['common_keys'][:10]:
                print(f"      • {key}: {freq}")
        
        # 3. Content Categories (discovered automatically)
        print(f"\n📚 CONTENT CATEGORIES (Discovered):")
        for category, count in self.discovered_categories.get('by_length', {}).items():
            print(f"   • {category}: {count}")
        
        print(f"\n   📝 Content types discovered:")
        for type_name, count in self.discovered_categories.get('by_type', {}).items():
            print(f"      • {type_name}: {count}")
        
        # 4. Topics (discovered, not assumed)
        print(f"\n📖 TOP TOPICS (Discovered from content):")
        topics = list(self.discovered_categories.get('top_topics', {}).items())
        if topics:
            for word, count in topics[:20]:
                print(f"   • {word}: {count}")
        else:
            print("   (No significant topics discovered)")
        
        # 5. Text Clusters (discovered groups)
        print(f"\n🔍 TEXT CLUSTERS (Discovered groups):")
        clusters = sorted(self.text_clusters.items(), key=lambda x: len(x[1]), reverse=True)[:10]
        if clusters:
            for word, texts in clusters:
                print(f"   • Starts with '{word}': {len(texts)} texts")
                # Show first 2 examples
                for text in texts[:2]:
                    print(f"      - {text[:80]}...")
        else:
            print("   (No significant clusters discovered)")
        
        # 6. Common Patterns (discovered)
        print(f"\n🔄 COMMON PATTERNS (Discovered):")
        patterns = self.structure_metrics.get('common_patterns', {})
        if patterns:
            for phrase, count in list(patterns.items())[:10]:
                print(f"   • '{phrase}': {count}")
        
        # 7. What can be done (no assumptions)
        print(f"\n💡 WHAT WE DISCOVERED WITHOUT ASSUMPTIONS:")
        print(f"   • {len(self.all_texts)} total text snippets")
        print(f"   • {len(set(self.all_texts))} are unique")
        print(f"   • Content types: {', '.join(self.discovered_categories.get('by_type', {}).keys())}")
        print(f"   • Top topics: {', '.join([w for w, _ in topics[:5]])}")
        
        # Save everything
        self._save_results()
        
        return {
            'total_texts': len(self.all_texts),
            'unique_texts': len(set(self.all_texts)),
            'categories': self.discovered_categories,
            'topics': self.discovered_categories.get('top_topics', {}),
            'patterns': patterns
        }
    
    def _save_results(self):
        """Save everything without assumptions"""
        output_file = self.session_path / 'ultimate_analysis.json'
        
        result = {
            'summary': {
                'total_texts': len(self.all_texts),
                'unique_texts': len(set(self.all_texts)),
                'files_analyzed': len(self.data)
            },
            'structure_metrics': self.structure_metrics,
            'discovered_categories': self.discovered_categories,
            'text_clusters': {
                word: texts[:5] for word, texts in list(self.text_clusters.items())[:20]
            },
            'common_patterns': list(self.structure_metrics.get('common_patterns', {}).items())[:50],
            'top_keys': self.structure_metrics.get('common_keys', [])[:20],
            'timestamp': datetime.now().isoformat(),
            'no_assumptions': True
        }
        
        with open(output_file, 'w') as f:
            json.dump(result, f, indent=2)
        
        print(f"\n💾 Saved to: {output_file}")

def main():
    print("🧠 ULTIMATE UNIVERSAL ANALYZER")
    print("Zero assumptions - pure discovery")
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
    
    # Analyze without assumptions
    analyzer = UltimateUniversalAnalyzer()
    analyzer.analyze_session(str(session_path))

if __name__ == "__main__":
    main()
