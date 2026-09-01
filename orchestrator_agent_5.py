#!/usr/bin/env python3
"""
GENERIC WEB RL AGENT - WORKS ON ANY WEBSITE
FIXED: url_before/url_after NameError
Features:
- Works on ANY website (not site-specific)
- Learns to explore and navigate
- Detects page types dynamically
- Builds internal representation of site structure
- Generic escape mechanisms
- SPA loading detection
- Adaptive exploration
- Strict goal detection (no false positives)
"""

import json
import sys
import os
import time
import hashlib
import gc
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple, Set
from collections import defaultdict, deque, Counter
from dataclasses import dataclass, field
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
    print("⚠️ Dynamic CDP v6 not found")

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
# Episode Tracker
# ============================================================================

class EpisodeTracker:
    def __init__(self):
        self.episodes = []
        self.successful_episodes = []
        
    def add_episode(self, cycle: int, action: str, reward: float, state: str, next_state: str):
        episode = {
            'cycle': cycle,
            'action': action,
            'reward': reward,
            'state': state,
            'next_state': next_state,
            'timestamp': datetime.now().isoformat()
        }
        self.episodes.append(episode)
        if reward > 5.0:
            self.successful_episodes.append(episode)
    
    def get_best_path(self, max_length: int = 5) -> Dict:
        if not self.successful_episodes:
            return {}
        
        best = max(self.successful_episodes, key=lambda e: e['reward'])
        idx = self.episodes.index(best) if best in self.episodes else -1
        if idx == -1:
            return {'actions': [best['action']], 'reward': best['reward']}
        
        start = max(0, idx - max_length + 1)
        path_actions = [e['action'] for e in self.episodes[start:idx+1]]
        
        return {
            'actions': path_actions,
            'reward': best['reward'],
            'cycle': best['cycle']
        }
    
    def get_stats(self) -> Dict:
        if not self.episodes:
            return {'total': 0, 'successful': 0, 'avg_reward': 0, 'max_reward': 0, 'min_reward': 0}
        
        rewards = [e['reward'] for e in self.episodes]
        return {
            'total': len(self.episodes),
            'successful': len(self.successful_episodes),
            'avg_reward': sum(rewards) / len(rewards) if rewards else 0,
            'max_reward': max(rewards) if rewards else 0,
            'min_reward': min(rewards) if rewards else 0
        }

# ============================================================================
# State Extractor - Works on ANY website
# ============================================================================

class StateExtractor:
    def __init__(self, cdp: CDPWrapper):
        self.cdp = cdp
        
    def extract(self, tab_index: int = 0) -> Dict:
        script = """
        (function() {
            function getStableSelector(el) {
                if (el.id) return '#' + el.id;
                let path = [];
                let current = el;
                while (current && current !== document.body) {
                    let selector = current.tagName.toLowerCase();
                    if (current.className) {
                        let classes = current.className.split(' ').filter(c => c && !c.match(/^[0-9]/)).slice(0, 2);
                        if (classes.length) selector += '.' + classes.join('.');
                    }
                    if (current.id) {
                        selector = '#' + current.id;
                        path = [selector];
                        break;
                    }
                    let parent = current.parentElement;
                    if (parent) {
                        let siblings = Array.from(parent.children);
                        let idx = siblings.indexOf(current) + 1;
                        if (siblings.filter(s => s.tagName === current.tagName).length > 1) {
                            selector += ':nth-child(' + idx + ')';
                        }
                    }
                    path.unshift(selector);
                    current = current.parentElement;
                }
                return path.join(' > ');
            }

            // Page info
            const page_info = {
                url: window.location.href,
                domain: window.location.hostname,
                path: window.location.pathname,
                title: document.title || '',
                text: document.body ? document.body.innerText : '',
                word_count: document.body ? document.body.innerText.split(/\\s+/).length : 0,
                link_count: document.querySelectorAll('a[href]').length,
                form_count: document.querySelectorAll('form').length,
                button_count: document.querySelectorAll('button, input[type="submit"]').length
            };

            // DOM features
            const dom_features = {
                interactive_elements: [],
                navigation_links: [],
                all_links: []
            };

            // Get ALL links for navigation
            document.querySelectorAll('a[href]').forEach(el => {
                const href = el.getAttribute('href');
                if (href && !href.startsWith('#') && !href.startsWith('javascript:')) {
                    dom_features.all_links.push({
                        text: el.textContent.trim().substring(0, 80) || href,
                        href: href
                    });
                }
            });

            // Get interactive elements
            document.querySelectorAll('button, a[href], [role="button"], [role="link"], input[type="submit"]').forEach(el => {
                const rect = el.getBoundingClientRect();
                if (rect.width === 0 || rect.height === 0) return;

                let container = el.closest('nav, header, footer, aside, main, form, [class*="item"], [class*="card"], [data-id]');
                let landmark = 'body';
                if (container) {
                    const tag = container.tagName.toLowerCase();
                    const cls = container.className ? '.' + container.className.split(' ')[0] : '';
                    landmark = tag + cls;
                }

                const is_ad = !!el.closest('[class*="ad"],[class*="sponsor"],[class*="promo"],[id*="ad"]');

                dom_features.interactive_elements.push({
                    text: el.textContent.trim().substring(0, 100),
                    tag: el.tagName.toLowerCase(),
                    href: el.getAttribute('href') || null,
                    classes: el.className || '',
                    landmark: landmark,
                    depth: (() => { let d=0, n=el; while(n.parentElement){d++; n=n.parentElement;} return d; })(),
                    selector: getStableSelector(el),
                    is_ad: is_ad,
                    aria_label: el.getAttribute('aria-label') || '',
                    id: el.id || ''
                });
            });

            // Navigation links
            document.querySelectorAll('nav a[href], .nav a[href], [role="navigation"] a[href]').forEach(el => {
                dom_features.navigation_links.push({
                    text: el.textContent.trim(),
                    href: el.getAttribute('href')
                });
            });

            // Detect page type
            const text = document.body ? document.body.innerText.toLowerCase() : '';
            const has_login = document.querySelectorAll('input[type="password"]').length > 0;
            const has_search = document.querySelectorAll('input[type="search"]').length > 0;
            const has_results = document.querySelectorAll('.result, .item, .card, .listing, [data-result]').length > 0;
            const has_items = document.querySelectorAll('.item, .card, .job, .product, .post').length > 3;
            
            let page_type = 'content';
            if (has_login) page_type = 'login';
            else if (has_search && has_results) page_type = 'search_results';
            else if (has_items) page_type = 'listing';
            else if (document.querySelectorAll('form').length > 0) page_type = 'form';

            return {
                page: page_info,
                dom: dom_features,
                page_type: page_type,
                has_login: has_login,
                has_search: has_search,
                has_results: has_results,
                has_items: has_items
            };
        })()
        """
        
        try:
            result = self.cdp.execute_js(script, tab_index)
            if not result:
                return self._empty_state()
            
            state = {
                'page': result.get('page', {}),
                'dom': result.get('dom', {}),
                'page_type': result.get('page_type', 'content'),
                'has_login': result.get('has_login', False),
                'has_search': result.get('has_search', False),
                'has_results': result.get('has_results', False),
                'has_items': result.get('has_items', False),
                'timestamp': datetime.now().isoformat()
            }
            
            state['state_id'] = self._compute_state_id(state)
            return state
            
        except Exception as e:
            print(f"   ⚠️ State extraction error: {e}")
            return self._empty_state()
    
    def _empty_state(self) -> Dict:
        return {
            'page': {'url': '', 'path': '', 'domain': '', 'text': ''},
            'dom': {'interactive_elements': [], 'navigation_links': [], 'all_links': []},
            'page_type': 'content',
            'has_login': False,
            'has_search': False,
            'has_results': False,
            'has_items': False,
            'state_id': 'empty',
            'timestamp': datetime.now().isoformat()
        }
    
    def _compute_state_id(self, state: Dict) -> str:
        page = state.get('page', {})
        dom = state.get('dom', {})
        
        landmark_counts = Counter()
        for el in dom.get('interactive_elements', []):
            landmark = el.get('landmark', 'body')
            landmark_counts[landmark] += 1
        
        features = {
            'path': page.get('path', ''),
            'domain': page.get('domain', ''),
            'page_type': state.get('page_type', 'content'),
            'has_login': state.get('has_login', False),
            'has_search': state.get('has_search', False),
            'has_results': state.get('has_results', False),
            'has_items': state.get('has_items', False),
            'button_count': min(5, page.get('button_count', 0) // 2),
            'landmark_signature': tuple(sorted(landmark_counts.items()))[:5]
        }
        
        state_str = json.dumps(features, sort_keys=True)
        return hashlib.md5(state_str.encode()).hexdigest()[:16]

# ============================================================================
# Action Preparer - Works on ANY website
# ============================================================================

class ActionPreparer:
    def __init__(self, state: Dict):
        self.state = state
        
    def prepare_actions(self) -> List[Dict]:
        actions = []
        seen_texts = set()
        
        interactive = self.state.get('dom', {}).get('interactive_elements', [])
        
        high_priority = []
        medium_priority = []
        low_priority = []
        
        for el in interactive:
            text = el.get('text', '').strip()
            if not text or len(text) < 2:
                continue
            
            if el.get('is_ad', False):
                continue
            
            landmark = el.get('landmark', '')
            if landmark.startswith('footer'):
                continue
            
            if text in seen_texts:
                continue
            seen_texts.add(text)
            
            text_lower = text.lower()
            selector = el.get('selector', '')
            
            if any(word in text_lower for word in ['apply', 'submit', 'register', 'sign up', 'login', 'sign in']):
                semantics = 'authentication'
                priority = 'high'
            elif any(word in text_lower for word in ['search', 'find', 'look for']):
                semantics = 'search'
                priority = 'high'
            elif any(word in text_lower for word in ['next', 'more', 'load', 'see all', 'view all']):
                semantics = 'pagination'
                priority = 'high'
            elif any(word in text_lower for word in ['home', 'back', 'return']):
                semantics = 'navigation'
                priority = 'medium'
            elif any(word in text_lower for word in ['save', 'bookmark', 'favorite', 'like']):
                semantics = 'save_content'
                priority = 'medium'
            else:
                semantics = 'generic'
                priority = 'medium'
            
            action = {
                'type': 'click',
                'text': text,
                'selector': selector,
                'semantics': semantics,
                'priority': priority,
                'landmark': landmark,
                'iife': f"""
                (function() {{
                    try {{
                        let el = document.querySelector('{selector}');
                        if (el) {{
                            el.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                            setTimeout(() => el.click(), 100);
                            return {{ success: true, method: 'selector' }};
                        }}
                        
                        const elements = document.querySelectorAll('button, a, [role="button"], [role="link"]');
                        for (let el of elements) {{
                            const elText = el.textContent.trim();
                            if (elText === '{text.replace("'", "\\'")}') {{
                                el.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                                setTimeout(() => el.click(), 100);
                                return {{ success: true, method: 'text' }};
                            }}
                        }}
                        
                        const lowerText = '{text.replace("'", "\\'")}'.toLowerCase();
                        for (let el of elements) {{
                            const elText = el.textContent.trim().toLowerCase();
                            if (elText.includes(lowerText) || lowerText.includes(elText)) {{
                                el.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                                setTimeout(() => el.click(), 100);
                                return {{ success: true, method: 'partial' }};
                            }}
                        }}
                        return {{ success: false, error: 'Element not found' }};
                    }} catch(e) {{
                        return {{ success: false, error: e.message }};
                    }}
                }})()
                """
            }
            
            if priority == 'high':
                high_priority.append(action)
            elif priority == 'medium':
                medium_priority.append(action)
            else:
                low_priority.append(action)
        
        # Add navigation links as actions
        all_links = self.state.get('dom', {}).get('all_links', [])
        for link in all_links[:10]:
            text = link.get('text', '').strip()
            href = link.get('href', '')
            if text and href and href not in ['#', 'javascript:void(0)']:
                if any(a.get('text') == text for a in high_priority + medium_priority):
                    continue
                action = {
                    'type': 'navigate',
                    'text': text[:50],
                    'target': href,
                    'semantics': 'navigation',
                    'priority': 'medium',
                    'landmark': 'link',
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
                medium_priority.append(action)
        
        actions = high_priority + medium_priority + low_priority
        return actions[:30]

# ============================================================================
# Action Normalizer
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
# Q-Learning Agent
# ============================================================================

@dataclass
class SuccessfulPath:
    actions: List[str]
    reward: float
    success_count: int = 1
    last_used: float = field(default_factory=time.time)

class QLearningAgent:
    def __init__(self, 
                 learning_rate: float = 0.15,
                 discount_factor: float = 0.9,
                 exploration_rate: float = 0.7,
                 exploration_decay: float = 0.995,
                 min_exploration: float = 0.15,
                 max_states: int = 500):
        
        self.lr = learning_rate
        self.gamma = discount_factor
        self.epsilon = exploration_rate
        self.epsilon_decay = exploration_decay
        self.epsilon_min = min_exploration
        self.max_states = max_states
        
        self.q_table = defaultdict(lambda: defaultdict(float))
        self.state_visits = defaultdict(int)
        self.action_visits = defaultdict(int)
        self.consecutive_repeats = 0
        self.stuck_count = 0
        
        self.successful_paths = deque(maxlen=50)
        self.episode_tracker = EpisodeTracker()
        self.base_lr = learning_rate
        
        print(f"🧠 Generic Q-Learning Agent:")
        print(f"   LR: {self.lr}, γ: {self.gamma}, ε: {self.epsilon}")
        print(f"   Max States: {self.max_states}")
    
    def choose_action(self, state_id: str, actions: List[Dict]) -> Optional[Dict]:
        if not actions:
            return None
        
        self.state_visits[state_id] += 1
        
        if self.stuck_count > 3:
            self.epsilon = min(0.9, self.epsilon * 1.05)
            self.stuck_count = 0
        
        if self.consecutive_repeats > 2:
            self.epsilon = min(0.9, self.epsilon * 1.02)
            self.consecutive_repeats = 0
        
        if random.random() < self.epsilon:
            action_scores = []
            for action in actions:
                normalized = self._normalize_action(action)
                action_key = (state_id, normalized)
                
                q_value = self.q_table[state_id][action_key]
                visits = self.action_visits[action_key]
                
                if visits > 0:
                    ucb = math.sqrt(2 * math.log(sum(self.state_visits.values()) + 1) / visits)
                else:
                    ucb = 4.0
                
                priority_bonus = 1.0 if action.get('priority') == 'high' else 0
                score = q_value + ucb + priority_bonus
                action_scores.append((score, action))
            
            action_scores.sort(key=lambda x: x[0], reverse=True)
            
            if len(action_scores) >= 3 and random.random() < 0.4:
                chosen = random.choice(action_scores[:3])[1]
            else:
                chosen = action_scores[0][1] if action_scores else random.choice(actions)
            
            last_action = getattr(self, '_last_action', None)
            if chosen == last_action:
                self.consecutive_repeats += 1
                self.stuck_count += 1
            else:
                self.consecutive_repeats = 0
                self.stuck_count = max(0, self.stuck_count - 1)
            self._last_action = chosen
            
            return chosen
        else:
            best_action = None
            best_value = -float('inf')
            
            for action in actions:
                normalized = self._normalize_action(action)
                action_key = (state_id, normalized)
                q_value = self.q_table[state_id][action_key]
                
                if q_value > best_value:
                    best_value = q_value
                    best_action = action
            
            return best_action if best_action else random.choice(actions)
    
    def _normalize_action(self, action: Dict) -> str:
        return f"{action.get('type', 'unknown')}|{action.get('text', '')[:30]}|{action.get('semantics', 'generic')}"
    
    def learn(self, state_id: str, action: Dict, reward: float, next_state_id: str):
        normalized = self._normalize_action(action)
        action_key = (state_id, normalized)
        
        self.action_visits[action_key] += 1
        
        current_q = self.q_table[state_id][action_key]
        max_future_q = max(self.q_table[next_state_id].values()) if self.q_table[next_state_id] else 0
        
        new_q = current_q + self.lr * (reward + self.gamma * max_future_q - current_q)
        self.q_table[state_id][action_key] = new_q
        
        self.episode_tracker.add_episode(
            cycle=len(self.episode_tracker.episodes) + 1,
            action=normalized,
            reward=reward,
            state=state_id,
            next_state=next_state_id
        )
        
        if reward > 3.0:
            best = self.episode_tracker.get_best_path()
            if best:
                self.successful_paths.append(SuccessfulPath(
                    actions=best['actions'],
                    reward=best['reward']
                ))
        
        self.epsilon = max(self.epsilon_min, self.epsilon * self.epsilon_decay)
        
        if self.epsilon > 0.4:
            self.lr = min(0.25, self.base_lr * 1.5)
        else:
            self.lr = max(0.05, self.base_lr * 0.8)
        
        if len(self.q_table) > self.max_states:
            self._trim_q_table()
    
    def _trim_q_table(self):
        usage_scores = {state: self.state_visits.get(state, 0) for state in self.q_table.keys()}
        sorted_states = sorted(usage_scores.items(), key=lambda x: x[1], reverse=True)
        keep_states = {state for state, _ in sorted_states[:self.max_states]}
        
        for state in list(self.q_table.keys()):
            if state not in keep_states:
                del self.q_table[state]
        gc.collect()
    
    def check_goal_achieved(self, state: Dict) -> bool:
        page = state.get('page', {})
        text = page.get('text', '').lower()
        
        success_indicators = [
            'application submitted',
            'thank you for applying',
            'application successfully',
            'your application has been submitted',
            'order confirmed',
            'purchase complete',
            'registration complete'
        ]
        
        for indicator in success_indicators:
            if indicator in text:
                return True
        
        return False
    
    def get_best_path(self) -> Dict:
        return self.episode_tracker.get_best_path()
    
    def get_stats(self) -> Dict:
        episode_stats = self.episode_tracker.get_stats()
        return {
            'state_count': len(self.q_table),
            'total_q_values': sum(len(v) for v in self.q_table.values()),
            'exploration_rate': self.epsilon,
            'learning_rate': self.lr,
            'total_actions': len(self.action_visits),
            'unique_actions': len(self.action_visits),
            'consecutive_repeats': self.consecutive_repeats,
            'stuck_count': self.stuck_count,
            'episodes': episode_stats['total'],
            'successful_episodes': episode_stats['successful'],
            'avg_reward': episode_stats['avg_reward'],
            'max_reward': episode_stats['max_reward'],
            'min_reward': episode_stats['min_reward']
        }

# ============================================================================
# Reward Engine - Generic
# ============================================================================

class RewardEngine:
    def __init__(self):
        self.reward_history = deque(maxlen=100)
        self.action_history = deque(maxlen=30)
        self.page_history = deque(maxlen=10)
        self.success_count = 0
        self.discovered_pages = set()
        
        self.rewards = {
            'new_page': 5.0,
            'new_state': 2.0,
            'new_content': 3.0,
            'pagination': 3.0,
            'form_action': 3.5,
            'success_click': 1.0,
            'goal_achieved': 50.0
        }
        
        self.penalties = {
            'duplicate': -0.3,
            'no_change': -0.1,
            'error': -0.5,
            'wasting_time': -1.0,
            'going_in_circles': -2.0
        }
    
    def calculate_reward(self, 
                         action: Dict,
                         state_before: Dict,
                         state_after: Dict,
                         success: bool,
                         cycle: int) -> float:
        
        reward = 0.0
        
        if success:
            reward += self.rewards['success_click']
        
        # Page change - FIXED: use proper variable names
        url_before = state_before.get('page', {}).get('url', '')
        url_after = state_after.get('page', {}).get('url', '')
        if url_before and url_after and url_before != url_after:
            reward += self.rewards['new_page']
            print(f"   🌐 +{self.rewards['new_page']}: New page!")
            self.page_history.append(url_after)
            self.success_count += 1
        
        # State change
        state_id_before = state_before.get('state_id', '')
        state_id_after = state_after.get('state_id', '')
        if state_id_before and state_id_after and state_id_before != state_id_after:
            reward += self.rewards['new_state']
            print(f"   🆕 +{self.rewards['new_state']}: New state!")
        
        # Content discovery
        word_before = state_before.get('page', {}).get('word_count', 0)
        word_after = state_after.get('page', {}).get('word_count', 0)
        if word_after > word_before * 1.5 and word_after > 100:
            reward += self.rewards['new_content']
            print(f"   📄 +{self.rewards['new_content']}: New content!")
        
        # Pagination detection
        if state_after.get('has_items', False) and state_after.get('page_type') == 'listing':
            reward += self.rewards['pagination']
            print(f"   📄 +{self.rewards['pagination']}: Pagination!")
        
        # Form/action detection
        if state_after.get('has_login', False) or state_after.get('has_search', False):
            reward += self.rewards['form_action']
            print(f"   ⚡ +{self.rewards['form_action']}: Form/action!")
        
        # Goal achievement
        if self._check_goal_achieved(state_after):
            reward += self.rewards['goal_achieved']
            print(f"   🎉 +{self.rewards['goal_achieved']}: GOAL ACHIEVED!")
            self.success_count += 3
        
        # Penalties
        action_key = ActionNormalizer.normalize(action)['normalized_key']
        
        if action_key in self.action_history:
            repeat_count = list(self.action_history).count(action_key)
            if repeat_count > 2:
                penalty = self.penalties['duplicate'] * min(3, repeat_count - 2)
                reward += penalty
                print(f"   🔄 Penalty: {penalty:.1f} (repeated action)")
        
        if url_before == url_after and success:
            reward += self.penalties['no_change']
            print(f"   ⚠️ Penalty: {self.penalties['no_change']:.1f} (no change)")
        
        self.action_history.append(action_key)
        self.reward_history.append(reward)
        
        return max(-5.0, min(60.0, reward))
    
    def _check_goal_achieved(self, state: Dict) -> bool:
        page = state.get('page', {})
        text = page.get('text', '').lower()
        
        success_indicators = [
            'application submitted',
            'thank you for applying',
            'application successfully',
            'your application has been submitted',
            'order confirmed',
            'purchase complete',
            'registration complete'
        ]
        
        for indicator in success_indicators:
            if indicator in text:
                return True
        return False
    
    def get_progress(self) -> float:
        if not self.reward_history:
            return 0.0
        recent = list(self.reward_history)[-20:]
        return sum(recent) / len(recent) if recent else 0.0

# ============================================================================
# Main RL Agent - Generic
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
        self.goal_achieved = False
        self.best_reward = -float('inf')
        self.no_progress_count = 0
        self.visited_states = set()
        
        print("=" * 70)
        print("🚀 GENERIC WEB RL AGENT - WORKS ON ANY WEBSITE")
        print("=" * 70)
        print("Features:")
        print("  ✅ Works on ANY website (not site-specific)")
        print("  ✅ Learns to explore and navigate")
        print("  ✅ Detects page types dynamically")
        print("  ✅ Builds internal representation of site structure")
        print("  ✅ Generic escape mechanisms")
        print("  ✅ SPA loading detection")
        print("  ✅ Adaptive exploration")
        print("  ✅ Strict goal detection (no false positives)")
        print("=" * 70)
        print(f"Max Cycles: {max_cycles}")
        print(f"Session: {self.session_dir}\n")
        
    def connect(self) -> bool:
        return self.cdp.connect()
    
    def run(self):
        print("🚀 Starting Generic Web RL Agent...\n")
        
        self.current_state = self.state_extractor.extract()
        state_id = self.current_state.get('state_id')
        self.visited_states.add(state_id)
        
        print(f"📍 Starting on: {self.current_state.get('page', {}).get('url', 'unknown')}")
        print(f"📊 Initial state: {state_id}")
        
        for self.cycle in range(1, self.max_cycles + 1):
            print(f"\n{'='*70}")
            print(f"🔄 CYCLE {self.cycle}/{self.max_cycles}")
            print(f"{'='*70}")
            
            try:
                page = self.current_state.get('page', {})
                print(f"📍 {page.get('url', 'unknown')[:80]}")
                print(f"📊 State: {state_id}")
                print(f"🏷️  Type: {self._get_page_type_emoji(self.current_state)}")
                print(f"🏷️  Landmarks: {self._get_landmark_summary(self.current_state)}")
                
                # Check if stuck with no progress
                if self._check_stuck():
                    print(f"   ⚠️ No progress detected ({self.no_progress_count} cycles)")
                    if self.no_progress_count >= 4:
                        print("   🔄 Attempting generic escape...")
                        self._generic_escape()
                        self.no_progress_count = 0
                        self.current_state = self.state_extractor.extract()
                        state_id = self.current_state.get('state_id')
                        continue
                
                # Prepare actions
                preparer = ActionPreparer(self.current_state)
                raw_actions = preparer.prepare_actions()
                actions = ActionValidator.filter_actions(raw_actions)
                print(f"⚡ Actions: {len(actions)} available (filtered from {len(raw_actions)})")
                
                if not actions:
                    self.no_action_count += 1
                    print(f"   ⏳ No actions - checking if page is loading...")
                    
                    if self.no_action_count >= 3:
                        print("   🔄 Attempting generic escape (no actions)...")
                        self._generic_escape()
                        self.no_action_count = 0
                        self.current_state = self.state_extractor.extract()
                        state_id = self.current_state.get('state_id')
                        continue
                    
                    # Wait and retry for SPA loading
                    for retry in range(3):
                        print(f"   🔄 Retry {retry+1}/3: waiting {1.5*(retry+1)}s...")
                        time.sleep(1.5 * (retry + 1))
                        self.current_state = self.state_extractor.extract()
                        actions = ActionValidator.filter_actions(
                            ActionPreparer(self.current_state).prepare_actions()
                        )
                        if actions:
                            print(f"   ✅ Found {len(actions)} actions after waiting!")
                            break
                    
                    if not actions:
                        print("   ⚠️ Still no actions, skipping cycle...")
                        self.no_action_count += 1
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
                    priority = action.get('priority', 'med')
                    print(f"   {i}. [{priority}] {norm['text'][:30]:30} | {norm['semantics']}")
                
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
                if action.get('selector'):
                    print(f"   📍 Selector: {action['selector'][:60]}")
                
                # Execute
                success = False
                iife = action.get('iife')
                if iife:
                    try:
                        result = self.cdp.execute_js(iife)
                        time.sleep(2.5)
                        success = bool(result and result.get('success', False))
                    except Exception as e:
                        print(f"   ❌ Execution error: {e}")
                        success = False
                
                # Observe new state
                new_state = self.state_extractor.extract()
                new_state_id = new_state.get('state_id')
                
                # Track visited states
                if new_state_id not in self.visited_states:
                    self.visited_states.add(new_state_id)
                    print(f"   🆕 New state discovered!")
                
                # Calculate reward
                reward = self.reward_engine.calculate_reward(
                    action, self.current_state, new_state, success, self.cycle
                )
                
                # Track progress - FIXED: use url_before/url_after properly
                url_before = self.current_state.get('page', {}).get('url', '')
                url_after = new_state.get('page', {}).get('url', '')
                if new_state_id == state_id and url_before == url_after:
                    self.no_progress_count += 1
                else:
                    self.no_progress_count = 0
                
                # Track best reward
                if reward > self.best_reward:
                    self.best_reward = reward
                    print(f"   📈 New best reward: {reward:.2f}")
                
                # Learn
                self.q_agent.learn(state_id, action, reward, new_state_id)
                
                # Record
                self.episode_history.append({
                    'cycle': self.cycle,
                    'action': norm['normalized_key'],
                    'success': success,
                    'reward': reward,
                    'state': state_id,
                    'next_state': new_state_id,
                    'url': new_state.get('page', {}).get('url', '')
                })
                
                print(f"\n📊 Results:")
                print(f"   Success: {'✅' if success else '❌'}")
                print(f"   Reward: {reward:.2f}")
                print(f"   States: {self.q_agent.get_stats()['state_count']}")
                print(f"   Q-Values: {self.q_agent.get_stats()['total_q_values']}")
                print(f"   ε: {self.q_agent.epsilon:.3f}")
                print(f"   LR: {self.q_agent.lr:.3f}")
                print(f"   Unique States: {len(self.visited_states)}")
                
                best_path = self.q_agent.get_best_path()
                if best_path:
                    path_str = ' → '.join(best_path['actions'][-3:])
                    print(f"   🏆 Best Path: {path_str} (reward: {best_path['reward']:.2f})")
                
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
    
    def _get_page_type_emoji(self, state: Dict) -> str:
        page_type = state.get('page_type', 'content')
        emojis = {
            'login': '🔐',
            'search_results': '🔍',
            'listing': '📋',
            'form': '📝',
            'content': '📄'
        }
        return f"{emojis.get(page_type, '📄')} {page_type.title()}"
    
    def _get_landmark_summary(self, state: Dict) -> str:
        landmark_counts = Counter()
        for el in state.get('dom', {}).get('interactive_elements', []):
            landmark = el.get('landmark', 'body')
            landmark_counts[landmark] += 1
        
        if not landmark_counts:
            return "No landmarks"
        
        top = landmark_counts.most_common(3)
        return ", ".join([f"{l}:{c}" for l, c in top])
    
    def _check_stuck(self) -> bool:
        if len(self.episode_history) < 3:
            return False
        
        recent = self.episode_history[-3:]
        recent_urls = [ep.get('url', '') for ep in recent]
        
        if len(set(recent_urls)) == 1 and recent_urls[0]:
            self.no_progress_count += 1
            return True
        
        return False
    
    def _generic_escape(self):
        """Generic escape mechanism - works on any site"""
        try:
            escape_strategies = [
                "window.location.href = window.location.origin;",
                "window.history.back();",
                "location.reload();"
            ]
            
            for strategy in escape_strategies:
                print(f"   🔄 Trying escape: {strategy[:40]}...")
                result = self.cdp.execute_js(strategy, 0)
                time.sleep(2)
                
                test_state = self.state_extractor.extract()
                new_url = test_state.get('page', {}).get('url', '')
                if new_url and new_url != self.current_state.get('page', {}).get('url', ''):
                    print(f"   ✅ Escaped successfully to: {new_url[:60]}")
                    return True
            
            print("   ⚠️ All escape strategies failed")
            return False
            
        except Exception as e:
            print(f"   ❌ Escape error: {e}")
            return False
    
    def save_state(self):
        state = {
            'cycle': self.cycle,
            'goal_achieved': self.goal_achieved,
            'best_reward': self.best_reward,
            'q_stats': self.q_agent.get_stats(),
            'reward_progress': list(self.reward_engine.reward_history)[-20:],
            'episodes': len(self.episode_history),
            'best_path': self.q_agent.get_best_path(),
            'success_count': self.reward_engine.success_count,
            'unique_states': len(self.visited_states),
            'timestamp': datetime.now().isoformat()
        }
        with open(self.session_dir / "agent_state.json", 'w') as f:
            json.dump(state, f, indent=2, default=str)
        print(f"\n💾 State saved to {self.session_dir}")
    
    def generate_report(self):
        report = []
        report.append("=" * 80)
        report.append("🚀 GENERIC WEB RL AGENT - FINAL REPORT")
        report.append("=" * 80)
        report.append(f"Total Cycles: {self.cycle}")
        report.append(f"Goal Achieved: {'✅ YES!' if self.goal_achieved else '🔄 Still learning'}")
        report.append(f"Best Reward: {self.best_reward:.2f}")
        report.append(f"Success Events: {self.reward_engine.success_count}")
        report.append(f"States Discovered: {len(self.visited_states)}")
        report.append("")
        
        stats = self.q_agent.get_stats()
        report.append("📊 Q-LEARNING STATS:")
        report.append(f"  States in Q-Table: {stats['state_count']}")
        report.append(f"  Q-Values Learned: {stats['total_q_values']}")
        report.append(f"  Exploration Rate: {stats['exploration_rate']:.3f}")
        report.append(f"  Learning Rate: {stats['learning_rate']:.3f}")
        report.append(f"  Total Actions: {stats['total_actions']}")
        report.append(f"  Unique Actions: {stats['unique_actions']}")
        report.append(f"  Episodes: {stats['episodes']}")
        report.append(f"  Successful Episodes: {stats['successful_episodes']}")
        report.append(f"  Avg Reward: {stats['avg_reward']:.2f}")
        report.append(f"  Max Reward: {stats['max_reward']:.2f}")
        report.append(f"  Min Reward: {stats['min_reward']:.2f}")
        report.append("")
        
        best_path = self.q_agent.get_best_path()
        if best_path:
            report.append("🏆 BEST PATH FOUND:")
            report.append(f"  {' → '.join(best_path['actions'][-5:])}")
            report.append(f"  Reward: {best_path['reward']:.2f}")
            report.append("")
        
        if self.episode_history:
            recent = self.episode_history[-20:]
            avg_reward = sum(e['reward'] for e in recent) / len(recent)
            success_rate = sum(1 for e in recent if e['success']) / len(recent)
            report.append(f"📈 Recent Performance (last {len(recent)}):")
            report.append(f"  Avg Reward: {avg_reward:.2f}")
            report.append(f"  Success Rate: {success_rate:.1%}")
            
            rewards = [e['reward'] for e in self.episode_history]
            if len(rewards) > 10:
                first_half = sum(rewards[:len(rewards)//2]) / len(rewards[:len(rewards)//2])
                second_half = sum(rewards[len(rewards)//2:]) / len(rewards[len(rewards)//2:])
                report.append(f"\n📈 Learning Progress:")
                report.append(f"  First Half Avg: {first_half:.2f}")
                report.append(f"  Second Half Avg: {second_half:.2f}")
                if second_half > first_half * 1.2:
                    report.append("  ✅ Agent is learning significantly! 🎉")
                elif second_half > first_half:
                    report.append("  ✅ Agent is learning slowly")
                else:
                    report.append("  ⚠️ Agent needs more exploration")
            
            action_counts = defaultdict(int)
            for ep in self.episode_history:
                action_counts[ep['action']] += 1
            report.append(f"\n📋 Action Distribution:")
            for action, count in sorted(action_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
                report.append(f"  {action}: {count} times")
        
        visited_urls = []
        for ep in self.episode_history:
            url = ep.get('url', '')
            if url and url not in visited_urls:
                visited_urls.append(url)
        
        if visited_urls:
            report.append(f"\n🌐 Visited Pages:")
            for i, url in enumerate(visited_urls[:10], 1):
                report.append(f"  {i}. {url[:80]}")
        
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
    print("🚀 GENERIC WEB RL AGENT")
    print("=" * 70)
    print("This agent works on ANY website and learns to explore!")
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
