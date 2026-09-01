#!/usr/bin/env python3
"""
REINFORCEMENT LEARNING AGENT - FINAL REFINED VERSION
All improvements implemented
"""

import json
import sys
import os
import time
import hashlib
import gc
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from collections import defaultdict, deque
import random
import math
import traceback

# ============================================================================
# CDP Wrapper
# ============================================================================

try:
    from dynamic_cdp_6 import EnhancedChromeCDP
    CDP_AVAILABLE = True
except ImportError:
    CDP_AVAILABLE = False
    print("⚠️ Dynamic CDP v6 not found - install for full functionality")

class CDPWrapper:
    def __init__(self, port: int = 9257):
        self.port = port
        self.client = None
        self.connected = False

    def connect(self):
        if CDP_AVAILABLE:
            try:
                self.client = EnhancedChromeCDP(port=self.port)
                tabs = self.client.get_tabs()
                if tabs:
                    self.connected = True
                    print(f"🔍 Found {len(tabs)} tabs")
                    return True
            except Exception as e:
                print(f"⚠️ Connect error: {e}")
        return False

    def execute_js(self, script: str, tab_index: int = 0):
        if not self.client:
            return None
        if hasattr(self.client, 'evaluate_script'):
            try:
                return self.client.evaluate_script(script, tab_index)
            except:
                pass
        return None

# ============================================================================
# State Extractor - Enhanced
# ============================================================================

class StateExtractor:
    def __init__(self, cdp: CDPWrapper):
        self.cdp = cdp
        
    def extract(self, tab_index: int = 0) -> Dict:
        page_info = self._get_page_info(tab_index)
        dom_features = self._get_dom_features(tab_index)
        goal_features = self._get_goal_features(tab_index)
        
        state = {
            'page': page_info,
            'dom': dom_features,
            'goals': goal_features,
            'timestamp': datetime.now().isoformat()
        }
        
        state['state_id'] = self._compute_state_id(state)
        return state
    
    def _get_page_info(self, tab_index: int) -> Dict:
        script = """
        (function() {
            return {
                url: window.location.href,
                domain: window.location.hostname,
                path: window.location.pathname,
                title: document.title || '',
                has_login_form: document.querySelectorAll('input[type="password"]').length > 0,
                has_search: document.querySelectorAll('input[type="search"], input[name*="search"]').length > 0,
                has_results: document.querySelectorAll('.result, .job, .listing, [data-result]').length > 0,
                word_count: document.body ? document.body.innerText.split(/\\s+/).length : 0,
                link_count: document.querySelectorAll('a[href]').length,
                form_count: document.querySelectorAll('form').length,
                button_count: document.querySelectorAll('button, input[type="submit"]').length
            };
        })()
        """
        try:
            result = self.cdp.execute_js(script, tab_index)
            return result if result else {}
        except:
            return {}
    
    def _get_dom_features(self, tab_index: int) -> Dict:
        script = """
        (function() {
            const features = {
                interactive_elements: [],
                navigation_links: [],
                job_cards: []
            };
            
            // Get all interactive elements
            document.querySelectorAll('button, a[href], [role="button"], [role="link"]').forEach(el => {
                const rect = el.getBoundingClientRect();
                const visible = rect.width > 0 && rect.height > 0;
                const text = el.textContent.trim().substring(0, 100);
                
                if (visible && text) {
                    features.interactive_elements.push({
                        text: text,
                        tag: el.tagName.toLowerCase(),
                        href: el.getAttribute('href') || null,
                        classes: el.className || ''
                    });
                }
            });
            
            // Get navigation links
            document.querySelectorAll('nav a[href], .nav a[href]').forEach(el => {
                features.navigation_links.push({
                    text: el.textContent.trim(),
                    href: el.getAttribute('href')
                });
            });
            
            // Get job cards
            document.querySelectorAll('.job, .job-card, .job-listing, [data-job-id]').forEach(el => {
                const title = el.querySelector('.title, .job-title, h3, h2');
                const company = el.querySelector('.company, .org');
                features.job_cards.push({
                    title: title ? title.textContent.trim() : '',
                    company: company ? company.textContent.trim() : '',
                    text: el.textContent.trim().substring(0, 200)
                });
            });
            
            return features;
        })()
        """
        try:
            result = self.cdp.execute_js(script, tab_index)
            return result if result else {}
        except:
            return {}
    
    def _get_goal_features(self, tab_index: int) -> Dict:
        script = """
        (function() {
            const text = document.body ? document.body.innerText.toLowerCase() : '';
            
            return {
                has_job_listings: document.querySelectorAll('.job, .job-card, .job-listing, [data-job-id]').length > 0,
                has_apply_button: Array.from(document.querySelectorAll('button, a')).some(el => 
                    el.textContent.toLowerCase().includes('apply')
                ),
                has_save_button: Array.from(document.querySelectorAll('button, a')).some(el => 
                    el.textContent.toLowerCase().includes('save')
                ),
                has_login: document.querySelectorAll('input[type="password"]').length > 0,
                has_search: document.querySelectorAll('input[type="search"]').length > 0,
                is_on_homepage: window.location.pathname === '/' || window.location.pathname === '',
                is_on_listing: document.querySelectorAll('.job, .product, .item').length > 3,
                is_on_detail: document.querySelectorAll('.detail, .job-detail, .product-detail').length > 0,
                is_on_confirmation: text.includes('success') || text.includes('thank you') || text.includes('completed')
            };
        })()
        """
        try:
            result = self.cdp.execute_js(script, tab_index)
            return result if result else {}
        except:
            return {}

    def _compute_state_id(self, state: Dict) -> str:
        page = state.get('page', {})
        goals = state.get('goals', {})
        
        features = {
            'path': page.get('path', ''),
            'domain': page.get('domain', ''),
            'is_homepage': goals.get('is_on_homepage', False),
            'is_listing': goals.get('is_on_listing', False),
            'is_detail': goals.get('is_on_detail', False),
            'has_jobs': goals.get('has_job_listings', False),
            'has_apply': goals.get('has_apply_button', False),
            'has_save': goals.get('has_save_button', False),
            'has_login': goals.get('has_login', False),
            'has_search': goals.get('has_search', False),
            'button_count': min(5, page.get('button_count', 0) // 2)
        }
        
        state_str = json.dumps(features, sort_keys=True)
        return hashlib.md5(state_str.encode()).hexdigest()[:16]

# ============================================================================
# Action Normalizer & Validator
# ============================================================================

class ActionNormalizer:
    @staticmethod
    def normalize(action: Dict) -> Dict:
        action_type = action.get('type', 'unknown')
        text = action.get('text', '').strip().lower()
        semantics = action.get('semantics', 'generic')
        
        text = ' '.join(text.split())
        if len(text) > 30:
            text = text[:27] + '...'
        
        return {
            'type': action_type,
            'text': text,
            'semantics': semantics,
            'priority': action.get('priority', 'medium'),
            'iife': action.get('iife', ''),
            'normalized_key': f"{action_type}|{text}|{semantics}"
        }

class ActionValidator:
    @staticmethod
    def validate(action: Dict) -> Tuple[bool, str]:
        if not action:
            return False, "Empty action"
        if not action.get('type'):
            return False, "Missing type"
        if action.get('type') == 'click' and not action.get('iife'):
            return False, "Missing IIFE"
        if action.get('type') == 'navigate':
            target = action.get('target', '')
            if not target or target == '#':
                return False, "Invalid target"
        return True, "Valid"
    
    @staticmethod
    def filter_actions(actions: List[Dict]) -> List[Dict]:
        seen = set()
        filtered = []
        for action in actions:
            is_valid, _ = ActionValidator.validate(action)
            if not is_valid:
                continue
            key = ActionNormalizer.normalize(action)['normalized_key']
            if key not in seen:
                seen.add(key)
                filtered.append(action)
        return filtered

# ============================================================================
# Q-Learning Agent - Enhanced
# ============================================================================

class QLearningAgent:
    def __init__(self, 
                 learning_rate: float = 0.15,
                 discount_factor: float = 0.9,
                 exploration_rate: float = 0.6,
                 exploration_decay: float = 0.99,
                 min_exploration: float = 0.1,
                 experience_buffer_size: int = 2000,
                 batch_size: int = 32,
                 max_states: int = 500):
        
        self.lr = learning_rate
        self.gamma = discount_factor
        self.epsilon = exploration_rate
        self.epsilon_decay = exploration_decay
        self.epsilon_min = min_exploration
        self.max_states = max_states
        
        self.q_table = defaultdict(lambda: defaultdict(float))
        self.experience_buffer = deque(maxlen=experience_buffer_size)
        self.batch_size = batch_size
        
        self.total_actions = 0
        self.state_visits = defaultdict(int)
        self.action_visits = defaultdict(int)
        self.consecutive_repeats = 0
        self.is_converged = False
        
        print(f"🧠 Enhanced Q-Learning Agent:")
        print(f"   LR: {self.lr}, γ: {self.gamma}, ε: {self.epsilon}")
        print(f"   Max States: {self.max_states}")
    
    def choose_action(self, state_id: str, actions: List[Dict]) -> Optional[Dict]:
        if not actions:
            return None
        
        self.total_actions += 1
        self.state_visits[state_id] += 1
        
        # If we've repeated too much, force exploration
        if self.consecutive_repeats > 3:
            self.epsilon = min(0.8, self.epsilon * 1.1)
            self.consecutive_repeats = 0
        
        if random.random() < self.epsilon:
            # Exploration with diversity
            action_scores = []
            for action in actions:
                normalized = ActionNormalizer.normalize(action)
                action_key = (state_id, normalized['normalized_key'])
                
                q_value = self.q_table[state_id][action_key]
                visits = self.action_visits[action_key]
                
                # Strong UCB bonus
                if visits > 0:
                    ucb = math.sqrt(2 * math.log(self.total_actions + 1) / visits)
                else:
                    ucb = 3.0  # Strong bonus for untried
                
                # Diversity bonus
                diversity = 0.5 if visits < 3 else 0
                
                score = q_value + ucb + diversity
                action_scores.append((score, action))
            
            action_scores.sort(key=lambda x: x[0], reverse=True)
            
            # More random exploration
            if len(action_scores) >= 3 and random.random() < 0.4:
                chosen = random.choice(action_scores[:3])[1]
            else:
                chosen = action_scores[0][1] if action_scores else random.choice(actions)
            
            # Track if we're repeating
            last_action = getattr(self, '_last_action', None)
            if chosen == last_action:
                self.consecutive_repeats += 1
            else:
                self.consecutive_repeats = 0
            self._last_action = chosen
            
            return chosen
        else:
            # Exploit
            best_action = None
            best_value = -float('inf')
            
            for action in actions:
                normalized = ActionNormalizer.normalize(action)
                action_key = (state_id, normalized['normalized_key'])
                q_value = self.q_table[state_id][action_key]
                
                if q_value > best_value:
                    best_value = q_value
                    best_action = action
            
            return best_action if best_action else random.choice(actions)
    
    def learn(self, state_id: str, action: Dict, reward: float, next_state_id: str):
        normalized = ActionNormalizer.normalize(action)
        action_key = (state_id, normalized['normalized_key'])
        
        self.action_visits[action_key] += 1
        
        # Q-learning update
        current_q = self.q_table[state_id][action_key]
        max_future_q = max(self.q_table[next_state_id].values()) if self.q_table[next_state_id] else 0
        
        new_q = current_q + self.lr * (reward + self.gamma * max_future_q - current_q)
        self.q_table[state_id][action_key] = new_q
        
        # Store experience
        self.experience_buffer.append({
            'state': state_id,
            'action': normalized['normalized_key'],
            'reward': reward,
            'next_state': next_state_id
        })
        
        # Batch learning
        if len(self.experience_buffer) >= self.batch_size:
            self._batch_learn()
        
        # Decay exploration
        self.epsilon = max(self.epsilon_min, self.epsilon * self.epsilon_decay)
        
        # Memory management
        if len(self.q_table) > self.max_states:
            self._trim_q_table()
    
    def _batch_learn(self):
        batch = random.sample(self.experience_buffer, min(self.batch_size, len(self.experience_buffer)))
        for exp in batch:
            state = exp['state']
            action_key = exp['action']
            reward = exp['reward']
            next_state = exp['next_state']
            
            action_tuple = (state, action_key)
            current_q = self.q_table[state][action_tuple]
            max_future_q = max(self.q_table[next_state].values()) if self.q_table[next_state] else 0
            
            self.q_table[state][action_tuple] = current_q + self.lr * (reward + self.gamma * max_future_q - current_q)
    
    def _trim_q_table(self):
        usage_scores = {state: self.state_visits.get(state, 0) for state in self.q_table.keys()}
        sorted_states = sorted(usage_scores.items(), key=lambda x: x[1], reverse=True)
        keep_states = {state for state, _ in sorted_states[:self.max_states]}
        
        for state in list(self.q_table.keys()):
            if state not in keep_states:
                del self.q_table[state]
        gc.collect()
    
    def get_stats(self) -> Dict:
        return {
            'state_count': len(self.q_table),
            'total_q_values': sum(len(v) for v in self.q_table.values()),
            'exploration_rate': self.epsilon,
            'total_actions': self.total_actions,
            'unique_actions': len(self.action_visits),
            'consecutive_repeats': self.consecutive_repeats
        }

# ============================================================================
# Reward Engine - Enhanced
# ============================================================================

class RewardEngine:
    def __init__(self):
        self.reward_history = deque(maxlen=100)
        self.action_history = deque(maxlen=30)
        self.page_history = deque(maxlen=10)
        
        self.rewards = {
            'new_page': 5.0,          # Increased
            'job_listing': 10.0,      # Increased
            'apply_button': 15.0,     # Increased
            'save_button': 10.0,      # Increased
            'search': 6.0,
            'new_content': 3.0,
            'success_click': 1.0,
            'new_state': 2.0          # New state discovery
        }
        
        self.penalties = {
            'duplicate': -0.5,        # Reduced penalty
            'no_change': -0.3,        # Reduced penalty
            'error': -0.5
        }
    
    def calculate_reward(self, 
                         action: Dict,
                         state_before: Dict,
                         state_after: Dict,
                         success: bool) -> float:
        
        reward = 0.0
        
        # Base reward for success
        if success:
            reward += self.rewards['success_click']
        
        # Page change reward
        url_before = state_before.get('page', {}).get('url', '')
        url_after = state_after.get('page', {}).get('url', '')
        if url_before and url_after and url_before != url_after:
            reward += self.rewards['new_page']
            print(f"   🌐 +{self.rewards['new_page']}: New page!")
            self.page_history.append(url_after)
        
        # State change reward
        state_id_before = state_before.get('state_id', '')
        state_id_after = state_after.get('state_id', '')
        if state_id_before and state_id_after and state_id_before != state_id_after:
            reward += self.rewards['new_state']
            print(f"   🆕 +{self.rewards['new_state']}: New state!")
        
        # Goal detection
        goals_before = state_before.get('goals', {})
        goals_after = state_after.get('goals', {})
        
        if goals_after.get('has_job_listings') and not goals_before.get('has_job_listings'):
            reward += self.rewards['job_listing']
            print(f"   💼 +{self.rewards['job_listing']}: Job listings found!")
        
        if goals_after.get('has_apply_button') and not goals_before.get('has_apply_button'):
            reward += self.rewards['apply_button']
            print(f"   📝 +{self.rewards['apply_button']}: Apply button found!")
        
        if goals_after.get('has_save_button') and not goals_before.get('has_save_button'):
            reward += self.rewards['save_button']
            print(f"   💾 +{self.rewards['save_button']}: Save button found!")
        
        if goals_after.get('has_search') and not goals_before.get('has_search'):
            reward += self.rewards['search']
            print(f"   🔍 +{self.rewards['search']}: Search found!")
        
        # Content discovery
        word_before = state_before.get('page', {}).get('word_count', 0)
        word_after = state_after.get('page', {}).get('word_count', 0)
        if word_after > word_before * 1.5:
            reward += self.rewards['new_content']
            print(f"   📄 +{self.rewards['new_content']}: New content!")
        
        # Penalties
        action_key = ActionNormalizer.normalize(action)['normalized_key']
        
        # Reduced duplicate penalty
        if action_key in self.action_history:
            reward += self.penalties['duplicate']
            if self.action_history.count(action_key) > 3:
                reward += self.penalties['duplicate']  # Extra for frequent repeats
        
        # No change penalty
        if url_before == url_after and success:
            reward += self.penalties['no_change']
        
        # Track history
        self.action_history.append(action_key)
        self.reward_history.append(reward)
        
        # Clamp reward
        return max(-2.0, min(25.0, reward))
    
    def get_progress(self) -> float:
        if not self.reward_history:
            return 0.0
        recent = list(self.reward_history)[-20:]
        return sum(recent) / len(recent) if recent else 0.0
    
    def get_exploration_score(self) -> float:
        """How much new stuff has been discovered"""
        unique_pages = len(set(self.page_history))
        return min(1.0, unique_pages / 10)

# ============================================================================
# Action Preparer - Enhanced
# ============================================================================

class ActionPreparer:
    def __init__(self, state: Dict):
        self.state = state
        
    def prepare_actions(self) -> List[Dict]:
        actions = []
        seen_texts = set()
        
        # Get interactive elements
        interactive = self.state.get('dom', {}).get('interactive_elements', [])
        
        # Categorize actions
        job_actions = []
        nav_actions = []
        other_actions = []
        
        for el in interactive:
            text = el.get('text', '').strip()
            if not text or len(text) < 2:
                continue
            
            # Skip if we've seen this text
            if text in seen_texts:
                continue
            seen_texts.add(text)
            
            # Determine semantics
            text_lower = text.lower()
            if any(word in text_lower for word in ['apply', 'submit', 'application']):
                semantics = 'job_application'
                priority = 'high'
                job_actions.append((text, semantics, priority))
            elif any(word in text_lower for word in ['save', 'bookmark', 'favorite']):
                semantics = 'save_content'
                priority = 'high'
                job_actions.append((text, semantics, priority))
            elif any(word in text_lower for word in ['search', 'find', 'look for']):
                semantics = 'search'
                priority = 'high'
                job_actions.append((text, semantics, priority))
            elif any(word in text_lower for word in ['login', 'sign in', 'log in']):
                semantics = 'authentication'
                priority = 'high'
                job_actions.append((text, semantics, priority))
            elif any(word in text_lower for word in ['next', 'more', 'load']):
                semantics = 'pagination'
                priority = 'medium'
                nav_actions.append((text, semantics, priority))
            elif any(word in text_lower for word in ['home', 'back', 'return']):
                semantics = 'navigation'
                priority = 'medium'
                nav_actions.append((text, semantics, priority))
            else:
                semantics = 'generic'
                priority = 'medium'
                other_actions.append((text, semantics, priority))
        
        # Prioritize: job actions first, then nav, then others
        ordered_actions = job_actions + nav_actions + other_actions
        
        for text, semantics, priority in ordered_actions[:20]:
            # Escape special characters for JavaScript
            escaped_text = text.replace("'", "\\'").replace('"', '\\"')
            
            action = {
                'type': 'click',
                'text': text,
                'target': text,
                'semantics': semantics,
                'priority': priority,
                'iife': f"""
                (function() {{
                    try {{
                        const elements = document.querySelectorAll('button, a, [role="button"], [role="link"]');
                        for (let el of elements) {{
                            const elText = el.textContent.trim();
                            if (elText === '{escaped_text}') {{
                                el.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                                setTimeout(() => el.click(), 100);
                                return {{ success: true, element: '{escaped_text}' }};
                            }}
                        }}
                        // Try partial match
                        const lowerText = '{escaped_text}'.toLowerCase();
                        for (let el of elements) {{
                            const elText = el.textContent.trim().toLowerCase();
                            if (elText.includes(lowerText) || lowerText.includes(elText)) {{
                                el.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                                setTimeout(() => el.click(), 100);
                                return {{ success: true, element: '{escaped_text}', partial: true }};
                            }}
                        }}
                        return {{ success: false, error: 'Element not found' }};
                    }} catch(e) {{
                        return {{ success: false, error: e.message }};
                    }}
                }})()
                """
            }
            actions.append(action)
        
        # Also add navigation actions from links
        nav_links = self.state.get('dom', {}).get('navigation_links', [])
        for link in nav_links[:5]:
            text = link.get('text', '').strip()
            href = link.get('href', '')
            if text and href and href not in ['#', 'javascript:void(0)']:
                action = {
                    'type': 'navigate',
                    'text': text,
                    'target': href,
                    'semantics': 'navigation',
                    'priority': 'medium',
                    'iife': f"""
                    (function() {{
                        try {{
                            window.location.href = '{href}';
                            return {{ success: true, url: '{href}' }};
                        }} catch(e) {{
                            return {{ success: false, error: e.message }};
                        }}
                    }})()
                    """
                }
                actions.append(action)
        
        return actions

# ============================================================================
# Main RL Agent
# ============================================================================

class ReinforcementLearningAgent:
    def __init__(self, port: int = 9257, max_cycles: int = 50):
        self.port = port
        self.max_cycles = max_cycles
        
        self.session_dir = Path(f"rl_agent_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        self.session_dir.mkdir(parents=True, exist_ok=True)
        
        self.cdp = CDPWrapper(port)
        self.state_extractor = StateExtractor(self.cdp)
        self.q_agent = QLearningAgent()
        self.reward_engine = RewardEngine()
        
        self.episode_history = []
        self.current_state = None
        self.cycle = 0
        self.no_action_count = 0
        
        print("=" * 70)
        print("🧠 FINAL REFINED REINFORCEMENT LEARNING AGENT")
        print("=" * 70)
        print("✅ Enhanced exploration with forced diversity")
        print("✅ Prioritized actions with partial matching")
        print("✅ Reduced duplicate penalties")
        print("✅ Richer state and reward features")
        print("=" * 70)
        print(f"Max Cycles: {max_cycles}")
        print(f"Session: {self.session_dir}\n")
        
    def connect(self) -> bool:
        return self.cdp.connect()
    
    def run(self):
        print("🚀 Starting Reinforcement Learning...\n")
        
        self.current_state = self.state_extractor.extract()
        state_id = self.current_state.get('state_id')
        
        for self.cycle in range(1, self.max_cycles + 1):
            print(f"\n{'='*70}")
            print(f"🔄 CYCLE {self.cycle}/{self.max_cycles}")
            print(f"{'='*70}")
            
            try:
                page = self.current_state.get('page', {})
                print(f"📍 {page.get('url', 'unknown')[:80]}")
                print(f"📊 State: {state_id}")
                
                # Prepare actions
                preparer = ActionPreparer(self.current_state)
                raw_actions = preparer.prepare_actions()
                actions = ActionValidator.filter_actions(raw_actions)
                print(f"⚡ Actions: {len(actions)} available")
                
                if not actions:
                    self.no_action_count += 1
                    print(f"   ⚠️ No actions ({self.no_action_count}/3 consecutive)")
                    if self.no_action_count >= 3:
                        print("   🔄 Reloading page...")
                        self.cdp.execute_js("location.reload()", 0)
                        time.sleep(3)
                        self.no_action_count = 0
                    time.sleep(2)
                    self.current_state = self.state_extractor.extract()
                    state_id = self.current_state.get('state_id')
                    continue
                else:
                    self.no_action_count = 0
                
                # Show top actions
                print("\n📋 Top Actions:")
                for i, action in enumerate(actions[:5], 1):
                    norm = ActionNormalizer.normalize(action)
                    print(f"   {i}. {norm['type']:8} | {norm['text'][:30]:30} | {norm['semantics']}")
                
                # Choose action
                action = self.q_agent.choose_action(state_id, actions)
                if not action:
                    print("   ⚠️ No action chosen.")
                    time.sleep(2)
                    self.current_state = self.state_extractor.extract()
                    state_id = self.current_state.get('state_id')
                    continue
                
                norm = ActionNormalizer.normalize(action)
                print(f"\n🎯 Chosen: {norm['type']} - '{norm['text']}' [{norm['semantics']}]")
                
                # Execute
                success = False
                iife = action.get('iife')
                if iife:
                    try:
                        result = self.cdp.execute_js(iife)
                        time.sleep(2.5)  # Slightly longer wait
                        success = bool(result and result.get('success', False))
                    except Exception as e:
                        print(f"   ❌ Error: {e}")
                        success = False
                
                # Observe new state
                new_state = self.state_extractor.extract()
                new_state_id = new_state.get('state_id')
                
                # Calculate reward
                reward = self.reward_engine.calculate_reward(
                    action, self.current_state, new_state, success
                )
                
                # Learn
                self.q_agent.learn(state_id, action, reward, new_state_id)
                
                # Record
                self.episode_history.append({
                    'cycle': self.cycle,
                    'action': norm['normalized_key'],
                    'success': success,
                    'reward': reward,
                    'state': state_id,
                    'next_state': new_state_id
                })
                
                print(f"\n📊 Results:")
                print(f"   Success: {'✅' if success else '❌'}")
                print(f"   Reward: {reward:.2f}")
                print(f"   States: {self.q_agent.get_stats()['state_count']}")
                print(f"   Q-Values: {self.q_agent.get_stats()['total_q_values']}")
                print(f"   ε: {self.q_agent.epsilon:.3f}")
                
                # Update state
                self.current_state = new_state
                state_id = new_state_id
                
                if self.cycle % 10 == 0:
                    self.save_state()
                    
            except KeyboardInterrupt:
                print(f"\n⏹️ Stopped at cycle {self.cycle}")
                break
            except Exception as e:
                print(f"   ❌ Error: {e}")
                traceback.print_exc()
                time.sleep(2)
                self.current_state = self.state_extractor.extract()
                state_id = self.current_state.get('state_id')
                continue
        
        self.save_state()
        self.generate_report()
    
    def save_state(self):
        state = {
            'cycle': self.cycle,
            'q_stats': self.q_agent.get_stats(),
            'reward_progress': list(self.reward_engine.reward_history)[-20:],
            'episodes': len(self.episode_history),
            'timestamp': datetime.now().isoformat()
        }
        with open(self.session_dir / "agent_state.json", 'w') as f:
            json.dump(state, f, indent=2, default=str)
        print(f"\n💾 Saved to {self.session_dir}")
    
    def generate_report(self):
        report = []
        report.append("=" * 80)
        report.append("🧠 FINAL RL AGENT - COMPLETE REPORT")
        report.append("=" * 80)
        report.append(f"Total Cycles: {self.cycle}")
        
        stats = self.q_agent.get_stats()
        report.append(f"States Discovered: {stats['state_count']}")
        report.append(f"Q-Values Learned: {stats['total_q_values']}")
        report.append(f"Exploration Rate: {stats['exploration_rate']:.3f}")
        report.append(f"Total Actions: {stats['total_actions']}")
        report.append(f"Unique Actions: {stats['unique_actions']}")
        report.append(f"Consecutive Repeats: {stats['consecutive_repeats']}")
        report.append("")
        
        # Performance
        if self.episode_history:
            recent = self.episode_history[-20:]
            avg_reward = sum(e['reward'] for e in recent) / len(recent)
            success_rate = sum(1 for e in recent if e['success']) / len(recent)
            report.append(f"Recent Performance (last {len(recent)}):")
            report.append(f"  Avg Reward: {avg_reward:.2f}")
            report.append(f"  Success Rate: {success_rate:.1%}")
            
            # Action distribution
            action_counts = defaultdict(int)
            for ep in self.episode_history:
                action_counts[ep['action']] += 1
            report.append(f"\nAction Distribution:")
            for action, count in sorted(action_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
                report.append(f"  {action}: {count} times")
            
            # Reward trend
            rewards = [e['reward'] for e in self.episode_history]
            if len(rewards) > 10:
                first_half = sum(rewards[:len(rewards)//2]) / len(rewards[:len(rewards)//2])
                second_half = sum(rewards[len(rewards)//2:]) / len(rewards[len(rewards)//2:])
                report.append(f"\nLearning Progress:")
                report.append(f"  First Half Avg: {first_half:.2f}")
                report.append(f"  Second Half Avg: {second_half:.2f}")
                if second_half > first_half:
                    report.append("  ✅ Agent is learning! 🎉")
                else:
                    report.append("  ⚠️ Agent needs more exploration")
        
        report.append("")
        report.append("=" * 80)
        
        report_text = "\n".join(report)
        with open(self.session_dir / "report.txt", 'w') as f:
            f.write(report_text)
        
        print("\n" + report_text)

# ============================================================================
# MAIN
# ============================================================================

def main():
    print("🧠 FINAL REINFORCEMENT LEARNING AGENT")
    print("=" * 70)
    print("Features:")
    print("  • Forced exploration with diversity bonus")
    print("  • Partial text matching for better click success")
    print("  • Reduced duplicate penalties")
    print("  • Page reload on no actions")
    print("  • Progress tracking with learning detection")
    print("=" * 70)
    
    port_input = input("🔌 Chrome port (default 9257): ").strip()
    port = int(port_input) if port_input else 9257
    
    cycles_input = input("📊 Max cycles (default 50): ").strip()
    max_cycles = int(cycles_input) if cycles_input else 50
    
    agent = ReinforcementLearningAgent(port=port, max_cycles=max_cycles)
    
    if not agent.connect():
        print("❌ Failed to connect. Make sure Chrome is running with:")
        print(f"   chromium-browser --remote-debugging-port={port}")
        return
    
    try:
        agent.run()
    except KeyboardInterrupt:
        print("\n👋 Stopped by user")
        agent.save_state()
        agent.generate_report()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Interrupted")
        sys.exit(0)
