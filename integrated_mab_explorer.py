#!/usr/bin/env python3
"""
Integrated MAB Explorer
Combines page exploration with contextual bandit decision making
"""

import json
import sys
import sqlite3
import hashlib
import math
import random
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict
from contextlib import contextmanager

# ============================================================================
# 1. DATABASE MANAGER
# ============================================================================

class MABDatabase:
    """Unified database for MAB decisions and page data"""
    
    def __init__(self, db_path="mab_data.db"):
        self.db_path = db_path
        self.init_db()
    
    def init_db(self):
        with self.get_connection() as conn:
            # Pages table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS pages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT,
                    title TEXT,
                    page_type TEXT,
                    node_count INTEGER,
                    heading_count INTEGER,
                    link_count INTEGER,
                    action_count INTEGER,
                    job_mentions INTEGER,
                    company_mentions INTEGER,
                    embedding TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(url)
                )
            """)
            
            # Actions table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS actions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE,
                    description TEXT,
                    success_count INTEGER DEFAULT 0,
                    fail_count INTEGER DEFAULT 0,
                    total_reward REAL DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Decisions table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    page_id INTEGER,
                    action_id INTEGER,
                    selected_action TEXT,
                    reward REAL,
                    confidence REAL,
                    context_features TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (page_id) REFERENCES pages(id),
                    FOREIGN KEY (action_id) REFERENCES actions(id)
                )
            """)
            
            # Similarity cache
            conn.execute("""
                CREATE TABLE IF NOT EXISTS similarity_cache (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    page1_id INTEGER,
                    page2_id INTEGER,
                    similarity REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(page1_id, page2_id)
                )
            """)
            
            # Initialize default actions if not exists
            conn.execute("""
                INSERT OR IGNORE INTO actions (name, description) VALUES 
                    ('extract_jobs', 'Extract job listings from page'),
                    ('extract_links', 'Extract all links from page'),
                    ('extract_content', 'Extract main content text'),
                    ('extract_emails', 'Extract email addresses'),
                    ('extract_contacts', 'Extract contact information'),
                    ('extract_social', 'Extract social media links'),
                    ('explore', 'Explore and discover page content'),
                    ('skip', 'Skip this page'),
                    ('click_cta', 'Click call-to-action button'),
                    ('fill_form', 'Fill and submit form')
            """)
    
    @contextmanager
    def get_connection(self):
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
    
    def get_or_create_page(self, url: str, title: str = "", metadata: Dict = None) -> int:
        with self.get_connection() as conn:
            cursor = conn.execute("SELECT id FROM pages WHERE url = ?", (url,))
            existing = cursor.fetchone()
            
            if existing:
                return existing['id']
            
            cursor = conn.execute("""
                INSERT INTO pages (url, title, page_type, embedding)
                VALUES (?, ?, ?, ?)
            """, (url, title, metadata.get('page_type', 'unknown') if metadata else 'unknown',
                  json.dumps(metadata.get('embedding', [])) if metadata else '[]'))
            return cursor.lastrowid
    
    def update_page_context(self, page_id: int, context: Dict):
        with self.get_connection() as conn:
            conn.execute("""
                UPDATE pages 
                SET page_type = ?, 
                    node_count = ?,
                    heading_count = ?,
                    link_count = ?,
                    action_count = ?,
                    job_mentions = ?,
                    company_mentions = ?
                WHERE id = ?
            """, (
                context.get('page_type', 'unknown'),
                context.get('node_count', 0),
                context.get('heading_count', 0),
                context.get('link_count', 0),
                context.get('action_count', 0),
                context.get('job_mentions', 0),
                context.get('company_mentions', 0),
                page_id
            ))
    
    def record_decision(self, page_id: int, action: str, reward: float, confidence: float, context: Dict):
        with self.get_connection() as conn:
            # Get action id
            cursor = conn.execute("SELECT id FROM actions WHERE name = ?", (action,))
            action_row = cursor.fetchone()
            if action_row:
                action_id = action_row['id']
            else:
                cursor = conn.execute("INSERT INTO actions (name) VALUES (?)", (action,))
                action_id = cursor.lastrowid
            
            conn.execute("""
                INSERT INTO decisions (page_id, action_id, selected_action, reward, confidence, context_features)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (page_id, action_id, action, reward, confidence, json.dumps(context)))
            
            # Update action stats
            conn.execute("""
                UPDATE actions 
                SET success_count = success_count + ?,
                    total_reward = total_reward + ?
                WHERE id = ?
            """, (1 if reward > 0.5 else 0, reward, action_id))
    
    def get_action_stats(self) -> Dict:
        with self.get_connection() as conn:
            cursor = conn.execute("""
                SELECT name, success_count, fail_count, total_reward,
                       (SELECT COUNT(*) FROM decisions WHERE action_id = actions.id) as trials
                FROM actions
                ORDER BY (total_reward / trials) DESC
            """)
            results = {}
            for row in cursor.fetchall():
                trials = row['trials'] or 0
                results[row['name']] = {
                    'success_count': row['success_count'],
                    'trials': trials,
                    'avg_reward': row['total_reward'] / trials if trials > 0 else 0,
                    'success_rate': row['success_count'] / trials if trials > 0 else 0
                }
            return results
    
    def get_similar_pages(self, embedding: List[float], limit: int = 10) -> List[Dict]:
        with self.get_connection() as conn:
            cursor = conn.execute("""
                SELECT id, url, title, page_type, embedding
                FROM pages 
                WHERE embedding != '[]' AND embedding IS NOT NULL
                ORDER BY created_at DESC
                LIMIT 100
            """)
            
            pages = []
            for row in cursor.fetchall():
                try:
                    emb = json.loads(row['embedding'])
                    if emb:
                        pages.append(dict(row))
                except:
                    continue
            
            # Calculate similarity
            similar = []
            for page in pages:
                try:
                    page_emb = json.loads(page['embedding'])
                    sim = self._cosine_similarity(embedding, page_emb)
                    similar.append({
                        'id': page['id'],
                        'url': page['url'],
                        'title': page['title'],
                        'page_type': page['page_type'],
                        'similarity': sim
                    })
                except:
                    continue
            
            similar.sort(key=lambda x: x['similarity'], reverse=True)
            return similar[:limit]
    
    def _cosine_similarity(self, a: List[float], b: List[float]) -> float:
        if not a or not b:
            return 0.0
        dot = sum(x*y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x*x for x in a))
        norm_b = math.sqrt(sum(y*y for y in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

# ============================================================================
# 2. CONTEXTUAL MAB ENGINE
# ============================================================================

class ContextualMABEngine:
    """MAB engine with context and embedding similarity"""
    
    def __init__(self, db: MABDatabase, alpha: float = 0.1, epsilon: float = 0.1):
        self.db = db
        self.alpha = alpha
        self.epsilon = epsilon
        self.action_history = []
    
    def select_action(self, context: Dict) -> Tuple[str, float]:
        """Select best action based on context"""
        actions = self.db.get_action_stats()
        
        if not actions:
            return "explore", 0.5
        
        # Exploration
        if random.random() < self.epsilon:
            action = random.choice(list(actions.keys()))
            return action, 0.3
        
        # Score each action
        best_action = None
        best_score = float('-inf')
        
        for action, stats in actions.items():
            if stats['trials'] == 0:
                return action, 0.5
            
            # Base score: average reward
            base_score = stats['avg_reward']
            
            # Context bonus
            context_bonus = self._context_bonus(action, context)
            
            # UCB bonus for exploration
            total_trials = sum(s['trials'] for s in actions.values())
            ucb_bonus = self.alpha * math.sqrt(math.log(total_trials + 1) / stats['trials'])
            
            score = base_score + context_bonus + ucb_bonus
            
            if score > best_score:
                best_score = score
                best_action = action
        
        return best_action or "explore", min(1.0, best_score)
    
    def _context_bonus(self, action: str, context: Dict) -> float:
        """Calculate bonus based on context similarity"""
        page_type = context.get('page_type', 'unknown')
        
        # Learned preferences from past decisions
        preferences = {
            'job_listing': {
                'extract_jobs': 0.3,
                'extract_links': 0.1,
                'extract_content': 0.1,
                'extract_emails': 0.0,
                'click_cta': 0.2,
            },
            'blog': {
                'extract_content': 0.3,
                'extract_links': 0.2,
                'extract_emails': 0.0,
                'explore': 0.2,
            },
            'auth': {
                'fill_form': 0.3,
                'skip': 0.2,
                'explore': 0.1,
            },
            'social': {
                'extract_links': 0.3,
                'extract_social': 0.3,
                'explore': 0.1,
            },
            'tool': {
                'explore': 0.3,
                'extract_content': 0.2,
                'extract_links': 0.2,
            }
        }
        
        return preferences.get(page_type, {}).get(action, 0.0)
    
    def update(self, action: str, reward: float, context: Dict):
        """Update MAB with feedback"""
        self.action_history.append({
            'action': action,
            'reward': reward,
            'context': context,
            'timestamp': datetime.now().isoformat()
        })
        
        # Store in database
        page_id = context.get('page_id')
        if page_id:
            self.db.record_decision(page_id, action, reward, 0.5, context)

# ============================================================================
# 3. PAGE CONTEXT EXTRACTOR
# ============================================================================

class PageContextExtractor:
    """Extract context from page data"""
    
    def __init__(self):
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
    
    def extract_from_page_data(self, page_data: Dict) -> Dict:
        """Extract context from page data"""
        context = {
            'page_type': 'unknown',
            'node_count': 0,
            'heading_count': 0,
            'link_count': 0,
            'action_count': 0,
            'job_mentions': 0,
            'company_mentions': 0,
            'text_length': 0,
            'embedding': []
        }
        
        # Get metadata
        metadata = page_data.get('metadata', {})
        context['title'] = metadata.get('title', '')
        context['url'] = metadata.get('url', '')
        
        # Extract from page analysis
        analysis = page_data.get('analysis', {})
        if analysis:
            context['node_count'] = analysis.get('node_count', 0)
            context['page_type'] = analysis.get('page_type', 'unknown')
        
        # Extract from links
        links = page_data.get('links', [])
        context['link_count'] = len(links)
        
        # Extract from actions
        actions = page_data.get('actions', [])
        context['action_count'] = len(actions)
        
        # Extract text
        text = ' '.join(page_data.get('texts', []))
        context['text_length'] = len(text)
        
        # Count job mentions
        job_keywords = ['job', 'jobs', 'hiring', 'career', 'opportunity', 'position']
        context['job_mentions'] = sum(1 for kw in job_keywords if kw in text.lower())
        
        # Count company mentions (capitalized words)
        import re
        companies = re.findall(r'\b[A-Z][a-zA-Z]+ (?:Inc|Ltd|LLC|Corp|Technologies|Solutions|Services|Consulting)\b', text)
        context['company_mentions'] = len(companies)
        
        # Generate embedding
        context['embedding'] = self._create_embedding(text)
        
        return context
    
    def _create_embedding(self, text: str) -> List[float]:
        """Create embedding from text"""
        dim = 50
        words = re.findall(r'[a-zA-Z]{3,}', text.lower())
        words = [w for w in words if w not in self.stopwords]
        
        if not words:
            return [0.0] * dim
        
        freq = {}
        for w in words:
            freq[w] = freq.get(w, 0) + 1
        
        embedding = []
        for i in range(dim):
            seed = i * 1000
            hash_val = hashlib.md5(f"{seed}".encode()).hexdigest()
            idx = int(hash_val[:8], 16) % len(words) if words else 0
            word = words[idx] if words else ''
            val = math.log(1 + freq.get(word, 0)) / math.log(1 + len(words))
            embedding.append(val)
        
        # Normalize
        norm = math.sqrt(sum(x*x for x in embedding)) or 1.0
        return [x/norm for x in embedding]

# ============================================================================
# 4. INTEGRATED EXPLORER
# ============================================================================

class IntegratedMABExplorer:
    """Complete integrated system"""
    
    def __init__(self, db_path: str = "mab_data.db"):
        self.db = MABDatabase(db_path)
        self.mab = ContextualMABEngine(self.db)
        self.extractor = PageContextExtractor()
    
    def process_page(self, page_data: Dict) -> Dict:
        """Process a page and decide action"""
        # Extract context
        context = self.extractor.extract_from_page_data(page_data)
        
        # Store page
        page_id = self.db.get_or_create_page(
            context.get('url', ''),
            context.get('title', ''),
            context
        )
        context['page_id'] = page_id
        
        # Update page context
        self.db.update_page_context(page_id, context)
        
        # Select action
        action, confidence = self.mab.select_action(context)
        
        # Record decision
        self.db.record_decision(page_id, action, 0.0, confidence, context)
        
        return {
            'page_id': page_id,
            'context': context,
            'selected_action': action,
            'confidence': confidence,
            'similar_pages': self.db.get_similar_pages(context.get('embedding', []))
        }
    
    def train_with_feedback(self, page_id: int, action: str, reward: float):
        """Train the MAB with feedback"""
        # Get page context
        with self.db.get_connection() as conn:
            cursor = conn.execute("""
                SELECT url, title, page_type, node_count, heading_count, 
                       link_count, action_count, job_mentions, company_mentions
                FROM pages WHERE id = ?
            """, (page_id,))
            row = cursor.fetchone()
            if row:
                context = dict(row)
                self.mab.update(action, reward, context)
                self.db.record_decision(page_id, action, reward, 0.5, context)
    
    def get_statistics(self) -> Dict:
        return {
            'actions': self.db.get_action_stats(),
            'pages': self._get_page_stats()
        }
    
    def _get_page_stats(self) -> Dict:
        with self.db.get_connection() as conn:
            cursor = conn.execute("""
                SELECT COUNT(*) as total_pages,
                       COUNT(DISTINCT page_type) as page_types,
                       SUM(CASE WHEN page_type = 'job_listing' THEN 1 ELSE 0 END) as job_pages,
                       SUM(CASE WHEN page_type = 'blog' THEN 1 ELSE 0 END) as blog_pages
                FROM pages
            """)
            return dict(cursor.fetchone())

# ============================================================================
# 5. CLI INTERFACE
# ============================================================================

def main():
    print("🧠 INTEGRATED MAB EXPLORER")
    print("="*60)
    
    explorer = IntegratedMABExplorer()
    
    while True:
        print("\n📌 Options:")
        print("  1. Analyze Current Page (from geturl.py data)")
        print("  2. Train with Feedback")
        print("  3. View Statistics")
        print("  4. Find Similar Pages")
        print("  5. Export Decisions")
        print("  0. Exit")
        
        choice = input("\nSelect: ").strip()
        
        if choice == "0":
            print("👋 Goodbye!")
            break
        
        elif choice == "1":
            # Load page data from geturl.py output
            try:
                with open('page_data_20260730_210202.json', 'r') as f:
                    page_data = json.load(f)
                result = explorer.process_page(page_data)
                print(f"\n📊 Page: {result['context'].get('title', 'Unknown')}")
                print(f"   Type: {result['context']['page_type']}")
                print(f"   Nodes: {result['context']['node_count']}")
                print(f"   Links: {result['context']['link_count']}")
                print(f"   Actions: {result['context']['action_count']}")
                print(f"   Job Mentions: {result['context']['job_mentions']}")
                print(f"\n🎯 RECOMMENDED ACTION: {result['selected_action']}")
                print(f"   Confidence: {result['confidence']:.2f}")
                if result['similar_pages']:
                    print(f"\n📊 Similar Pages:")
                    for sim in result['similar_pages'][:3]:
                        print(f"   • {sim['title'][:40]} ({sim['similarity']:.3f})")
            except FileNotFoundError:
                print("❌ No page data found. Run geturl.py first and save page data.")
        
        elif choice == "2":
            print("\n🎓 Train with Feedback")
            page_id = int(input("Page ID: ").strip())
            action = input("Action name: ").strip()
            reward = float(input("Reward (0.0-1.0): ").strip())
            explorer.train_with_feedback(page_id, action, reward)
            print("✅ Trained!")
        
        elif choice == "3":
            stats = explorer.get_statistics()
            print("\n📊 STATISTICS:")
            print(f"   Total Pages: {stats['pages']['total_pages']}")
            print(f"   Page Types: {stats['pages']['page_types']}")
            print(f"   Job Pages: {stats['pages']['job_pages']}")
            print(f"   Blog Pages: {stats['pages']['blog_pages']}")
            print("\n   Action Performance:")
            for action, data in stats['actions'].items():
                if data['trials'] > 0:
                    print(f"     • {action}: {data['trials']} trials, {data['avg_reward']:.3f} avg reward")
        
        elif choice == "4":
            print("\n🔍 Find Similar Pages")
            # Use last analyzed page
            try:
                with open('page_data_20260730_210202.json', 'r') as f:
                    page_data = json.load(f)
                context = explorer.extractor.extract_from_page_data(page_data)
                similar = explorer.db.get_similar_pages(context.get('embedding', []))
                print("\n📊 Similar Pages:")
                for sim in similar[:10]:
                    print(f"   • {sim['similarity']:.3f} → {sim['title'][:50]} ({sim['page_type']})")
            except:
                print("❌ No page data found")
        
        elif choice == "5":
            filename = f"mab_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with explorer.db.get_connection() as conn:
                cursor = conn.execute("""
                    SELECT d.*, p.url, p.title, p.page_type, a.name as action_name
                    FROM decisions d
                    JOIN pages p ON d.page_id = p.id
                    JOIN actions a ON d.action_id = a.id
                    ORDER BY d.created_at DESC
                """)
                data = [dict(row) for row in cursor.fetchall()]
                with open(filename, 'w') as f:
                    json.dump(data, f, indent=2, default=str)
            print(f"✅ Exported to {filename}")

if __name__ == "__main__":
    main()
