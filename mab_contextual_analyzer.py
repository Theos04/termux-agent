#!/usr/bin/env python3
"""
Contextual Multi-Armed Bandit with Embeddings
Combines page analysis, embeddings, and bandit algorithms for intelligent decision making
"""

import json
import sys
import re
import hashlib
import math
import random
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple, Set
from dataclasses import dataclass, field
from collections import defaultdict, Counter
import sqlite3
from contextlib import contextmanager

# ============================================================================
# 1. EMBEDDINGS GENERATOR (Simple but effective)
# ============================================================================

class PageEmbedding:
    """Generate embeddings from page content using TF-IDF style vectors"""
    
    def __init__(self):
        self.vocab = {}
        self.dim = 100  # Embedding dimension
        self.stopwords = {'the', 'be', 'to', 'of', 'and', 'a', 'in', 'that', 'have', 'i',
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
    
    def create_embedding(self, text: str) -> List[float]:
        """Create embedding from text"""
        # Extract words
        words = re.findall(r'[a-zA-Z]{3,}', text.lower())
        words = [w for w in words if w not in self.stopwords]
        
        if not words:
            return [0.0] * self.dim
        
        # Count word frequencies
        freq = Counter(words)
        
        # Create embedding
        embedding = []
        for i in range(self.dim):
            # Use hash to determine which word to use
            seed = i * 1000
            hash_val = hashlib.md5(f"{seed}".encode()).hexdigest()
            # Use deterministic but distributed selection
            idx = int(hash_val[:8], 16) % len(words) if words else 0
            word = words[idx] if words else ''
            # Compute embedding value
            if word in freq:
                # Use log frequency with some randomness
                val = math.log(1 + freq[word]) / math.log(1 + len(words))
                # Add positional information
                pos = words.index(word) / len(words)
                val = val * (0.5 + 0.5 * math.sin(pos * 2 * math.pi))
            else:
                val = 0.0
            embedding.append(val)
        
        # Normalize
        norm = math.sqrt(sum(x*x for x in embedding)) or 1.0
        embedding = [x/norm for x in embedding]
        
        return embedding
    
    def distance(self, emb1: List[float], emb2: List[float]) -> float:
        """Calculate Euclidean distance between embeddings"""
        if not emb1 or not emb2:
            return float('inf')
        return math.sqrt(sum((a-b)*(a-b) for a, b in zip(emb1, emb2)))
    
    def similarity(self, emb1: List[float], emb2: List[float]) -> float:
        """Calculate cosine similarity between embeddings"""
        if not emb1 or not emb2:
            return 0.0
        dot = sum(a*b for a, b in zip(emb1, emb2))
        norm1 = math.sqrt(sum(a*a for a in emb1))
        norm2 = math.sqrt(sum(b*b for b in emb2))
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return dot / (norm1 * norm2)

# ============================================================================
# 2. CONTEXTUAL FEATURES
# ============================================================================

@dataclass
class PageContext:
    """Contextual features for a page"""
    url: str = ""
    page_type: str = "unknown"
    
    # Structural features
    node_count: int = 0
    heading_count: int = 0
    link_count: int = 0
    action_count: int = 0
    
    # Content features
    word_count: int = 0
    job_mentions: int = 0
    company_mentions: int = 0
    
    # Action features
    clickable_count: int = 0
    typeable_count: int = 0
    form_count: int = 0
    
    # Embedding
    embedding: List[float] = field(default_factory=list)
    
    def to_vector(self) -> List[float]:
        """Convert to feature vector for MAB"""
        return [
            self.node_count / 10000,  # Normalize
            self.heading_count / 50,
            self.link_count / 100,
            self.action_count / 50,
            self.word_count / 1000,
            self.job_mentions / 50,
            self.company_mentions / 20,
            self.clickable_count / 50,
            self.typeable_count / 20,
            self.form_count / 10,
            1.0 if self.page_type == "job_listing" else 0.0,
            1.0 if self.page_type == "blog" else 0.0,
            1.0 if self.page_type == "auth" else 0.0,
            1.0 if self.page_type == "content" else 0.0,
        ]

# ============================================================================
# 3. CONTEXTUAL MULTI-ARMED BANDIT
# ============================================================================

class Arm:
    """An arm (action) in the bandit"""
    def __init__(self, name: str):
        self.name = name
        self.count = 0
        self.reward = 0.0
        self.context_rewards = []  # (context_vector, reward) pairs
        self.embedding_center = None
        self.feature_means = None
    
    @property
    def expected_reward(self) -> float:
        """Average reward"""
        return self.reward / self.count if self.count > 0 else 0.0
    
    def update(self, reward: float, context: PageContext = None):
        """Update arm based on reward and context"""
        self.count += 1
        self.reward += reward
        
        if context and hasattr(context, 'embedding') and context.embedding:
            self.context_rewards.append((context.embedding, reward))
            
            # Update embedding center
            if len(self.context_rewards) > 1:
                emb_sum = [0.0] * len(self.context_rewards[0][0])
                for emb, _ in self.context_rewards:
                    for i, val in enumerate(emb):
                        emb_sum[i] += val
                self.embedding_center = [v / len(self.context_rewards) for v in emb_sum]

class ContextualMAB:
    """Contextual Multi-Armed Bandit with Thompson Sampling"""
    
    def __init__(self, alpha: float = 0.1, epsilon: float = 0.1):
        self.arms = {}
        self.alpha = alpha  # Learning rate
        self.epsilon = epsilon  # Exploration rate
        self.history = []
        self.embedder = PageEmbedding()
    
    def add_arm(self, name: str):
        """Add a new arm/action"""
        if name not in self.arms:
            self.arms[name] = Arm(name)
    
    def get_arm(self, name: str) -> Optional[Arm]:
        """Get an arm by name"""
        return self.arms.get(name)
    
    def select_action(self, context: PageContext) -> str:
        """Select the best action given the context"""
        if not self.arms:
            return "explore"
        
        # Exploration
        if random.random() < self.epsilon:
            return random.choice(list(self.arms.keys()))
        
        # Thompson Sampling: select based on expected reward + uncertainty
        best_arm = None
        best_score = float('-inf')
        
        for name, arm in self.arms.items():
            if arm.count == 0:
                return name  # Try untested arms
            
            # Expected reward
            base_score = arm.expected_reward
            
            # Contextual similarity bonus
            if context.embedding and arm.embedding_center:
                sim = self.embedder.similarity(context.embedding, arm.embedding_center)
                base_score += 0.2 * sim
            
            # UCB-style bonus for exploration
            exploration_bonus = self.alpha * math.sqrt(math.log(len(self.history) + 1) / arm.count)
            score = base_score + exploration_bonus
            
            if score > best_score:
                best_score = score
                best_arm = name
        
        return best_arm or random.choice(list(self.arms.keys()))
    
    def update(self, arm_name: str, reward: float, context: PageContext = None):
        """Update bandit with new observation"""
        if arm_name not in self.arms:
            self.add_arm(arm_name)
        
        self.arms[arm_name].update(reward, context)
        self.history.append({
            'arm': arm_name,
            'reward': reward,
            'timestamp': datetime.now().isoformat(),
            'context': context.to_vector() if context else None
        })

# ============================================================================
# 4. SESSION ANALYZER WITH MAB
# ============================================================================

class IntelligentSessionAnalyzer:
    """Combines session analysis with MAB decision making"""
    
    def __init__(self, db_path: str = "mab_data.db"):
        self.db_path = db_path
        self.embedder = PageEmbedding()
        self.mab = ContextualMAB()
        self.init_db()
        
        # Define possible actions
        self.actions = [
            "extract_jobs",
            "extract_links",
            "extract_content",
            "extract_emails",
            "extract_contacts",
            "extract_prices",
            "extract_reviews",
            "extract_products",
            "extract_social",
            "explore",
            "skip"
        ]
        
        for action in self.actions:
            self.mab.add_arm(action)
    
    def init_db(self):
        """Initialize database for storing decisions"""
        with self.get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS mab_decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    url TEXT,
                    page_type TEXT,
                    selected_action TEXT,
                    reward REAL,
                    context_features TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS page_embeddings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    url TEXT,
                    embedding TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
    
    @contextmanager
    def get_connection(self):
        """Get database connection"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
    
    def analyze_session(self, session_path: str) -> PageContext:
        """Extract context from a session"""
        session_path = Path(session_path)
        
        # Load DOM data
        dom_files = list(session_path.glob('dom_trees/dom_*.json')) + list(session_path.glob('dom_*.json'))
        if not dom_files:
            return PageContext(url=str(session_path))
        
        with open(dom_files[0], 'r') as f:
            raw = json.load(f)
            dom_data = raw.get('data', raw)
        
        # Extract features
        context = self._extract_context(dom_data)
        context.url = str(session_path)
        
        # Generate embedding
        text = self._extract_all_text(dom_data)
        context.embedding = self.embedder.create_embedding(' '.join(text))
        context.word_count = len(' '.join(text).split())
        
        return context
    
    def _extract_context(self, data: Any) -> PageContext:
        """Extract context features from DOM"""
        context = PageContext()
        
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
        context.node_count = len(nodes)
        
        # Count features
        headings = 0
        links = 0
        actions = 0
        clickable = 0
        typeable = 0
        forms = 0
        text_samples = []
        
        for node in nodes:
            tag = node.get('nodeName', '').lower()
            attrs = self._get_attrs(node)
            text = self._get_text(node)
            
            if tag in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                headings += 1
            elif tag == 'a':
                links += 1
            elif tag in ['button', 'input', 'select', 'textarea']:
                actions += 1
                if tag in ['button', 'a']:
                    clickable += 1
                if tag in ['input', 'textarea']:
                    typeable += 1
            elif tag == 'form':
                forms += 1
            
            if text and len(text) > 3 and not self._is_technical(text):
                text_samples.append(text)
        
        context.heading_count = headings
        context.link_count = links
        context.action_count = actions
        context.clickable_count = clickable
        context.typeable_count = typeable
        context.form_count = forms
        
        # Detect page type
        all_text = ' '.join(text_samples).lower()
        if any(w in all_text for w in ['job', 'jobs', 'hiring', 'career', 'opportunity']):
            context.page_type = 'job_listing'
            context.job_mentions = sum(1 for t in text_samples if any(w in t.lower() for w in ['job', 'hiring']))
        elif any(w in all_text for w in ['blog', 'article', 'post', 'news']):
            context.page_type = 'blog'
        elif any(w in all_text for w in ['login', 'sign', 'register', 'account']):
            context.page_type = 'auth'
        else:
            context.page_type = 'content'
        
        # Extract company mentions
        company_pattern = re.compile(r'\b[A-Z][a-z]+ (?:Inc|Ltd|LLC|Corp|Technologies|Solutions|Services|Consulting)\b')
        context.company_mentions = len(company_pattern.findall(all_text))
        
        return context
    
    def _get_attrs(self, node: Dict) -> Dict:
        """Get attributes"""
        attrs = {}
        attr_list = node.get('attributes', [])
        if isinstance(attr_list, list):
            for i in range(0, len(attr_list), 2):
                if i+1 < len(attr_list):
                    attrs[attr_list[i]] = attr_list[i+1]
        return attrs
    
    def _get_text(self, node: Dict) -> str:
        """Get text from node"""
        if node.get('nodeType') == 3:
            return node.get('nodeValue', '').strip()
        attrs = self._get_attrs(node)
        for key in ['aria-label', 'title', 'placeholder', 'value']:
            if key in attrs and attrs[key]:
                return attrs[key].strip()
        return ''
    
    def _is_technical(self, text: str) -> bool:
        """Check if text is technical"""
        if len(text) < 3:
            return True
        if re.match(r'^[a-z]+[A-Z]', text):
            return True
        if re.match(r'^[a-z]+-[a-z]+', text):
            return True
        if re.match(r'^[a-z_]+$', text):
            return True
        return False
    
    def _extract_all_text(self, data: Any) -> List[str]:
        """Extract all text from DOM"""
        texts = []
        def walk(node):
            if isinstance(node, dict):
                if node.get('nodeType') == 3:
                    text = node.get('nodeValue', '').strip()
                    if text:
                        texts.append(text)
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
        return texts
    
    def decide_action(self, session_path: str) -> Dict:
        """Decide what action to take for a session"""
        # Analyze context
        context = self.analyze_session(session_path)
        
        # Select action using MAB
        action = self.mab.select_action(context)
        
        return {
            'session': session_path,
            'context': context,
            'selected_action': action,
            'confidence': self._calculate_confidence(action, context)
        }
    
    def _calculate_confidence(self, action: str, context: PageContext) -> float:
        """Calculate confidence in the decision"""
        arm = self.mab.get_arm(action)
        if not arm or arm.count == 0:
            return 0.5
        
        base_conf = min(0.9, arm.count / 10)
        return base_conf * (0.7 + 0.3 * (arm.expected_reward))
    
    def train(self, session_path: str, action: str, reward: float):
        """Train the MAB with feedback"""
        context = self.analyze_session(session_path)
        self.mab.update(action, reward, context)
        
        # Store in database
        with self.get_connection() as conn:
            conn.execute("""
                INSERT INTO mab_decisions (session_id, url, page_type, selected_action, reward, context_features)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                session_path,
                context.url,
                context.page_type,
                action,
                reward,
                json.dumps(context.to_vector())
            ))
    
    def get_statistics(self) -> Dict:
        """Get MAB statistics"""
        stats = {
            'arms': {},
            'total_decisions': len(self.mab.history)
        }
        
        for name, arm in self.mab.arms.items():
            stats['arms'][name] = {
                'count': arm.count,
                'avg_reward': arm.expected_reward if arm.count > 0 else 0,
                'explored': arm.count > 0
            }
        
        return stats

# ============================================================================
# 5. CLI INTERFACE
# ============================================================================

class MABCLI:
    """Interactive CLI for MAB analysis"""
    
    def __init__(self):
        self.analyzer = IntelligentSessionAnalyzer()
    
    def run(self):
        """Main loop"""
        print("🧠 CONTEXTUAL MAB ANALYZER")
        print("="*60)
        print("Multi-Armed Bandit with Embeddings and Context")
        print("="*60)
        
        while True:
            print("\n📌 Options:")
            print("  1. Analyze Session (Decide Action)")
            print("  2. Train with Feedback")
            print("  3. View Statistics")
            print("  4. Find Similar Sessions")
            print("  5. Export Decisions")
            print("  0. Exit")
            
            choice = input("\nSelect: ").strip()
            
            if choice == "0":
                print("👋 Goodbye!")
                break
            
            elif choice == "1":
                self._analyze_session()
            
            elif choice == "2":
                self._train_with_feedback()
            
            elif choice == "3":
                self._view_stats()
            
            elif choice == "4":
                self._find_similar()
            
            elif choice == "5":
                self._export_decisions()
    
    def _analyze_session(self):
        """Analyze a session and decide action"""
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
                session_path = sessions[0]
        else:
            session_path = Path(input("📁 Enter session path: ").strip())
        
        if not session_path.exists():
            print(f"❌ Session not found: {session_path}")
            return
        
        print(f"\n🔍 Analyzing: {session_path.name}")
        decision = self.analyzer.decide_action(str(session_path))
        
        context = decision['context']
        print(f"\n📊 CONTEXT:")
        print(f"   Page Type: {context.page_type}")
        print(f"   Nodes: {context.node_count}")
        print(f"   Headings: {context.heading_count}")
        print(f"   Links: {context.link_count}")
        print(f"   Actions: {context.action_count}")
        print(f"   Clickable: {context.clickable_count}")
        print(f"   Typeable: {context.typeable_count}")
        print(f"   Forms: {context.form_count}")
        print(f"   Job Mentions: {context.job_mentions}")
        print(f"   Company Mentions: {context.company_mentions}")
        
        print(f"\n🎯 RECOMMENDED ACTION: {decision['selected_action']}")
        print(f"   Confidence: {decision['confidence']:.2f}")
        
        # Show arm statistics
        stats = self.analyzer.get_statistics()
        print(f"\n📈 ARM STATISTICS:")
        for name, data in stats['arms'].items():
            if data['count'] > 0:
                print(f"   • {name}: {data['count']} trials, avg reward: {data['avg_reward']:.3f}")
    
    def _train_with_feedback(self):
        """Train the MAB with feedback"""
        print("\n🎓 TRAIN WITH FEEDBACK")
        print("-"*40)
        
        # Select session
        memory_dir = Path('/data/data/com.termux/files/home/automation/chrome-launcher/memory')
        sessions = sorted(memory_dir.glob('session_*'), key=lambda x: x.stat().st_mtime, reverse=True)
        
        if sessions:
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
                session_path = sessions[0]
        else:
            session_path = Path(input("📁 Enter session path: ").strip())
        
        if not session_path.exists():
            print(f"❌ Session not found: {session_path}")
            return
        
        # Get action and reward
        print("\n📌 Available actions:")
        for i, action in enumerate(self.analyzer.actions, 1):
            print(f"  [{i}] {action}")
        
        action_choice = input("\nSelect action number: ").strip()
        try:
            idx = int(action_choice) - 1
            if 0 <= idx < len(self.analyzer.actions):
                action = self.analyzer.actions[idx]
            else:
                print("❌ Invalid action")
                return
        except:
            print("❌ Invalid input")
            return
        
        reward = float(input("Enter reward (0.0 - 1.0): ").strip() or "0.5")
        reward = max(0.0, min(1.0, reward))
        
        # Train
        self.analyzer.train(str(session_path), action, reward)
        print(f"✅ Trained: {action} with reward {reward:.2f}")
    
    def _view_stats(self):
        """View MAB statistics"""
        stats = self.analyzer.get_statistics()
        
        print("\n📊 MAB STATISTICS")
        print("="*60)
        print(f"Total Decisions: {stats['total_decisions']}")
        print("\nArm Statistics:")
        print("-"*40)
        
        for name, data in sorted(stats['arms'].items(), key=lambda x: x[1]['avg_reward'], reverse=True):
            status = "✅" if data['explored'] else "⏳"
            print(f"  {status} {name}:")
            print(f"     Trials: {data['count']}")
            print(f"     Avg Reward: {data['avg_reward']:.3f}")
    
    def _find_similar(self):
        """Find similar sessions using embeddings"""
        print("\n🔍 FIND SIMILAR SESSIONS")
        print("-"*40)
        
        # Get all sessions
        memory_dir = Path('/data/data/com.termux/files/home/automation/chrome-launcher/memory')
        sessions = list(memory_dir.glob('session_*'))
        
        if not sessions:
            print("❌ No sessions found")
            return
        
        # Analyze all sessions
        print("Analyzing sessions...")
        contexts = {}
        for session in sessions:
            try:
                context = self.analyzer.analyze_session(str(session))
                if context.embedding:
                    contexts[session.name] = context
            except:
                continue
        
        if not contexts:
            print("❌ No valid contexts found")
            return
        
        # Select reference
        print("\n📂 Available sessions:")
        names = list(contexts.keys())
        for i, name in enumerate(names[:10]):
            print(f"  [{i}] {name}")
        
        choice = input("\nSelect reference session: ").strip()
        if not choice.isdigit():
            return
        
        idx = int(choice)
        if idx >= len(names):
            print("❌ Invalid selection")
            return
        
        ref_name = names[idx]
        ref_context = contexts[ref_name]
        
        # Find similar
        print(f"\n🔍 Finding sessions similar to {ref_name}...")
        similarities = []
        
        for name, context in contexts.items():
            if name == ref_name:
                continue
            sim = self.analyzer.embedder.similarity(ref_context.embedding, context.embedding)
            similarities.append((name, sim, context.page_type))
        
        # Sort by similarity
        similarities.sort(key=lambda x: x[1], reverse=True)
        
        print("\n📊 MOST SIMILAR SESSIONS:")
        print("-"*40)
        for name, sim, page_type in similarities[:10]:
            print(f"  {sim:.3f} → {name} ({page_type})")
    
    def _export_decisions(self):
        """Export decisions to JSON"""
        output_file = f"mab_decisions_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        with self.analyzer.get_connection() as conn:
            cursor = conn.execute("""
                SELECT * FROM mab_decisions ORDER BY created_at DESC
            """)
            decisions = [dict(row) for row in cursor.fetchall()]
        
        with open(output_file, 'w') as f:
            json.dump(decisions, f, indent=2, default=str)
        
        print(f"✅ Exported {len(decisions)} decisions to {output_file}")

# ============================================================================
# 6. MAIN
# ============================================================================

def main():
    cli = MABCLI()
    try:
        cli.run()
    except KeyboardInterrupt:
        print("\n👋 Interrupted")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
