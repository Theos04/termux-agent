#!/usr/bin/env python3
"""
GENERIC WEB RL AGENT - LEARNS ON ANY WEBSITE (FIXED)
Fixed:
- KeyError: 'low' bug in ActionPreparer
- False positive goal detection
- Better error handling
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
    """Track episodes and find best paths"""

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

        if reward > 3.0:
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
            return {
                'total': 0,
                'successful': 0,
                'avg_reward': 0,
                'max_reward': 0,
                'min_reward': 0
            }

        rewards = [e['reward'] for e in self.episodes]
        return {
            'total': len(self.episodes),
            'successful': len(self.successful_episodes),
            'avg_reward': sum(rewards) / len(rewards) if rewards else 0,
            'max_reward': max(rewards) if rewards else 0,
            'min_reward': min(rewards) if rewards else 0
        }

# ============================================================================
# State Extractor - Enhanced for Generic Pages
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

            const page_info = {
                url: window.location.href,
                domain: window.location.hostname,
                path: window.location.pathname,
                title: document.title || '',
                text: document.body ? document.body.innerText : '',
                has_login_form: document.querySelectorAll('input[type="password"]').length > 0,
                has_search: document.querySelectorAll('input[type="search"], input[name*="search"]').length > 0,
                has_results: document.querySelectorAll('.result, .item, .listing, [data-result]').length > 0,
                word_count: document.body ? document.body.innerText.split(/\\s+/).length : 0,
                link_count: document.querySelectorAll('a[href]').length,
                form_count: document.querySelectorAll('form').length,
                button_count: document.querySelectorAll('button, input[type="submit"]').length,
                input_count: document.querySelectorAll('input:not([type="hidden"])').length
            };

            const dom_features = {
                interactive_elements: [],
                navigation_links: [],
                content_items: []
            };

            // Collect all interactive elements
            document.querySelectorAll('button, a[href], [role="button"], [role="link"], input[type="submit"], input[type="button"]').forEach(el => {
                const rect = el.getBoundingClientRect();
                if (rect.width === 0 || rect.height === 0) return;

                let container = el.closest('nav, header, footer, aside, main, form, section, article, [class*="item"], [data-id]');
                let landmark = 'body';
                if (container) {
                    const tag = container.tagName.toLowerCase();
                    const cls = container.className ? '.' + container.className.split(' ')[0] : '';
                    landmark = tag + cls;
                }

                const is_ad = !!el.closest('[class*="ad"],[class*="sponsor"],[class*="promo"],[id*="ad"]');
                const is_modal = !!el.closest('[class*="modal"],[class*="popup"],[class*="overlay"]');

                dom_features.interactive_elements.push({
                    text: el.textContent.trim().substring(0, 100),
                    tag: el.tagName.toLowerCase(),
                    href: el.getAttribute('href') || null,
                    classes: el.className || '',
                    landmark: landmark,
                    depth: (() => { let d=0, n=el; while(n.parentElement){d++; n=n.parentElement;} return d; })(),
                    selector: getStableSelector(el),
                    is_ad: is_ad,
                    is_modal: is_modal,
                    aria_label: el.getAttribute('aria-label') || '',
                    id: el.id || '',
                    type: el.getAttribute('type') || ''
                });
            });

            // Navigation links
            document.querySelectorAll('nav a[href], .nav a[href], [role="navigation"] a[href], header a[href]').forEach(el => {
                dom_features.navigation_links.push({
                    text: el.textContent.trim(),
                    href: el.getAttribute('href')
                });
            });

            // Content items (generic)
            document.querySelectorAll('.item, .card, .post, .article, .product, .job, [data-item], [data-id]').forEach(el => {
                const title = el.querySelector('.title, .heading, h1, h2, h3, h4, .name');
                const desc = el.querySelector('.desc, .description, .summary, .content');
                dom_features.content_items.push({
                    title: title ? title.textContent.trim() : '',
                    description: desc ? desc.textContent.trim().substring(0, 100) : '',
                    text: el.textContent.trim().substring(0, 200)
                });
            });

            const text = document.body ? document.body.innerText.toLowerCase() : '';
            
            // Generic page type detection
            const page_types = {
                is_homepage: window.location.pathname === '/' || window.location.pathname === '',
                is_listing: document.querySelectorAll('.item, .card, .product, .job, .listing, [data-item]').length > 3,
                is_detail: document.querySelectorAll('.detail, .details, .content, .article, .post').length > 0,
                is_search: document.querySelectorAll('input[type="search"]').length > 0,
                is_login: document.querySelectorAll('input[type="password"]').length > 0,
                is_form: document.querySelectorAll('form').length > 0,
                is_confirmation: text.includes('success') || text.includes('thank you') || text.includes('completed') || text.includes('confirmed'),
                has_items: document.querySelectorAll('.item, .card, .product, .job').length > 0,
                has_pagination: document.querySelectorAll('.pagination, .next, .prev, .pages, .load-more').length > 0,
                has_modal: document.querySelectorAll('.modal, .popup, .overlay, .dialog').length > 0,
                has_search_results: document.querySelectorAll('.result, .search-result, [data-result]').length > 0,
                has_form: document.querySelectorAll('form').length > 0,
                word_count: document.body ? document.body.innerText.split(/\\s+/).length : 0,
                has_images: document.querySelectorAll('img').length > 0,
                has_video: document.querySelectorAll('video, iframe[src*="youtube"], iframe[src*="vimeo"]').length > 0,
                is_dynamic: document.querySelectorAll('[data-reactroot], [data-vue], [ng-app]').length > 0,
                has_success_message: text.includes('success') || text.includes('thank you')
            };

            // Goal detection - more strict
            const goal_features = {
                has_completed_action: (text.includes('success') && !text.includes('no results')) || 
                                     (text.includes('thank you') && text.includes('for your')) ||
                                     text.includes('submitted successfully') ||
                                     text.includes('saved successfully') ||
                                     text.includes('completed successfully'),
                has_error: text.includes('error') || 
                          text.includes('failed') || 
                          text.includes('invalid') ||
                          text.includes('not found'),
                has_form_submit: document.querySelectorAll('input[type="submit"], button[type="submit"]').length > 0,
                has_search: document.querySelectorAll('input[type="search"], button[type="search"]').length > 0,
                has_navigation: document.querySelectorAll('nav, .nav, [role="navigation"]').length > 0,
                is_loading: document.querySelectorAll('.loading, .spinner, .skeleton, [data-loading]').length > 0,
                is_banner_page: text.includes('ad') || text.includes('sponsor') || text.includes('promo')
            };

            return {
                page: page_info,
                dom: dom_features,
                page_types: page_types,
                goals: goal_features
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
                'page_types': result.get('page_types', {}),
                'goals': result.get('goals', {}),
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
            'dom': {'interactive_elements': [], 'navigation_links': [], 'content_items': []},
            'page_types': {},
            'goals': {},
            'state_id': 'empty',
            'timestamp': datetime.now().isoformat()
        }

    def _compute_state_id(self, state: Dict) -> str:
        page = state.get('page', {})
        page_types = state.get('page_types', {})
        dom = state.get('dom', {})
        goals = state.get('goals', {})

        landmark_counts = Counter()
        for el in dom.get('interactive_elements', []):
            landmark = el.get('landmark', 'body')
            landmark_counts[landmark] += 1

        features = {
            'path': page.get('path', ''),
            'domain': page.get('domain', ''),
            'title_hash': hashlib.md5(page.get('title', '').encode()).hexdigest()[:8],
            'is_homepage': page_types.get('is_homepage', False),
            'is_listing': page_types.get('is_listing', False),
            'is_detail': page_types.get('is_detail', False),
            'has_items': page_types.get('has_items', False),
            'has_pagination': page_types.get('has_pagination', False),
            'has_form': page_types.get('has_form', False),
            'is_login': page_types.get('is_login', False),
            'is_dynamic': page_types.get('is_dynamic', False),
            'button_count': min(10, page.get('button_count', 0)),
            'input_count': min(10, page.get('input_count', 0)),
            'word_count_bucket': min(5, page.get('word_count', 0) // 200),
            'landmark_signature': tuple(sorted(landmark_counts.items()))[:5],
            'has_success': goals.get('has_completed_action', False),
            'is_banner': goals.get('is_banner_page', False)
        }

        state_str = json.dumps(features, sort_keys=True)
        return hashlib.md5(state_str.encode()).hexdigest()[:16]

# ============================================================================
# Generic Escape Mechanisms
# ============================================================================

class GenericEscaper:
    """Generic escape mechanisms for any website"""
    
    @staticmethod
    def escape_to_origin(cdp: CDPWrapper) -> bool:
        """Navigate to the site's origin"""
        try:
            print(f"   🔄 Navigating to origin...")
            cdp.execute_js("window.location.href = window.location.origin;", 0)
            time.sleep(3)
            return True
        except Exception as e:
            print(f"   ❌ Escape failed: {e}")
            return False
    
    @staticmethod
    def escape_to_home(cdp: CDPWrapper) -> bool:
        """Try common home page paths"""
        try:
            home_paths = ['/', '/home', '/index', '/main']
            current_path = StateExtractor(cdp).extract().get('page', {}).get('path', '')
            
            for path in home_paths:
                if path != current_path:
                    print(f"   🔄 Trying home path: {path}")
                    cdp.execute_js(f"window.location.href = window.location.origin + '{path}';", 0)
                    time.sleep(3)
                    new_state = StateExtractor(cdp).extract()
                    if new_state.get('page', {}).get('path', '') != current_path:
                        return True
            
            return False
        except Exception as e:
            print(f"   ❌ Home escape failed: {e}")
            return False
    
    @staticmethod
    def escape_back(cdp: CDPWrapper) -> bool:
        """Navigate back in history"""
        try:
            print(f"   🔄 Going back in history...")
            cdp.execute_js("window.history.back();", 0)
            time.sleep(2)
            return True
        except Exception as e:
            print(f"   ❌ Back navigation failed: {e}")
            return False

# ============================================================================
# Q-Learning Agent - Enhanced for Generic Pages
# ============================================================================

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
        
        self.page_type_exploration = defaultdict(int)
        self.discovered_patterns = []

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

                priority_bonus = 0
                semantics = action.get('semantics', 'generic')
                if semantics in ['action', 'search', 'authentication']:
                    priority_bonus = 1.0
                elif semantics in ['pagination', 'navigation', 'explore']:
                    priority_bonus = 0.5
                
                score = q_value + ucb + priority_bonus
                action_scores.append((score, action))

            action_scores.sort(key=lambda x: x[0], reverse=True)

            if len(action_scores) >= 3 and random.random() < 0.3:
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
        goals = state.get('goals', {})
        page_types = state.get('page_types', {})
        page = state.get('page', {})
        
        # STRICT: Only consider it a goal if there's a clear success message
        if goals.get('has_completed_action', False):
            return True
        
        if page_types.get('is_confirmation', False):
            # Make sure it's not a banner/ad page
            if not goals.get('is_banner_page', False):
                return True
        
        # Check text for CLEAR success indicators
        text = page.get('text', '').lower()
        strict_success_patterns = [
            'thank you for your',
            'submitted successfully',
            'saved successfully',
            'completed successfully',
            'congratulations',
            'your application has been submitted',
            'order confirmed'
        ]
        
        for pattern in strict_success_patterns:
            if pattern in text:
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

@dataclass
class SuccessfulPath:
    actions: List[str]
    reward: float
    success_count: int = 1
    last_used: float = field(default_factory=time.time)

# ============================================================================
# Action Preparer - FIXED KeyError
# ============================================================================

class ActionPreparer:
    def __init__(self, state: Dict):
        self.state = state

    def prepare_actions(self) -> List[Dict]:
        actions = []
        seen_texts = set()

        interactive = self.state.get('dom', {}).get('interactive_elements', [])

        # FIXED: Initialize with all keys
        categorized_actions = {
            'high': [],
            'medium': [],
            'low': []
        }

        for el in interactive:
            text = el.get('text', '').strip()
            if not text or len(text) < 2:
                continue

            if el.get('is_ad', False):
                continue
            
            if el.get('depth', 0) > 20:
                continue

            if text in seen_texts:
                continue
            seen_texts.add(text)

            text_lower = text.lower()
            selector = el.get('selector', '')
            landmark = el.get('landmark', '')
            tag = el.get('tag', '')
            href = el.get('href', '')

            semantics = 'generic'
            priority = 'low'  # Default to low

            # High priority actions
            if any(word in text_lower for word in ['submit', 'apply', 'save', 'download', 'buy', 'purchase', 'sign up', 'register']):
                semantics = 'action'
                priority = 'high'
            elif any(word in text_lower for word in ['search', 'find', 'look for', 'query']):
                semantics = 'search'
                priority = 'high'
            elif any(word in text_lower for word in ['login', 'sign in', 'log in', 'signin']):
                semantics = 'authentication'
                priority = 'high'
            elif text_lower in ['next', 'more', 'load more', 'show more', 'see more']:
                semantics = 'pagination'
                priority = 'high'
            
            # Medium priority actions
            elif any(word in text_lower for word in ['read more', 'learn more', 'details', 'view more']):
                semantics = 'explore'
                priority = 'medium'
            elif any(word in text_lower for word in ['home', 'back', 'return', 'menu']):
                semantics = 'navigation'
                priority = 'medium'
            elif any(word in text_lower for word in ['previous', 'prev', 'earlier']):
                semantics = 'navigation'
                priority = 'medium'
            elif any(word in text_lower for word in ['accept', 'agree', 'continue', 'ok']):
                semantics = 'consent'
                priority = 'medium'
            
            # Boost priority for buttons with good landmarks
            if landmark in ['main', 'nav', 'header', 'content']:
                if priority == 'low':
                    priority = 'medium'
            
            # Boost priority for links with href
            if tag == 'a' and href and not href.startswith('#'):
                if priority == 'low':
                    priority = 'medium'

            # FIXED: Use the exact key
            categorized_actions[priority].append((text, semantics, priority, selector, landmark))

        # Order: high -> medium -> low
        ordered_actions = (categorized_actions['high'] + 
                          categorized_actions['medium'] + 
                          categorized_actions['low'])

        for text, semantics, priority, selector, landmark in ordered_actions[:30]:
            escaped_text = text.replace("'", "\\'").replace('"', '\\"')

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
                            return {{ success: true, method: 'selector', element: '{selector}' }};
                        }}

                        const elements = document.querySelectorAll('button, a, [role="button"], [role="link"]');
                        for (let el of elements) {{
                            const elText = el.textContent.trim();
                            if (elText === '{escaped_text}') {{
                                el.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                                setTimeout(() => el.click(), 100);
                                return {{ success: true, method: 'text', element: '{escaped_text}' }};
                            }}
                        }}

                        const lowerText = '{escaped_text}'.toLowerCase();
                        for (let el of elements) {{
                            const elText = el.textContent.trim().toLowerCase();
                            if (elText.includes(lowerText) || lowerText.includes(elText)) {{
                                el.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                                setTimeout(() => el.click(), 100);
                                return {{ success: true, method: 'partial', element: '{escaped_text}' }};
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

        return actions

# ============================================================================
# Reward Engine - Enhanced for Generic Pages
# ============================================================================

class RewardEngine:
    def __init__(self):
        self.reward_history = deque(maxlen=100)
        self.action_history = deque(maxlen=30)
        self.page_history = deque(maxlen=10)
        self.success_count = 0
        
        self.discovered_pages = set()
        self.visited_urls = set()

        self.rewards = {
            'new_page': 5.0,
            'new_state': 2.0,
            'new_page_type': 8.0,
            'content_discovery': 4.0,
            'successful_click': 1.0,
            'new_content': 3.0,
            'pagination': 3.0,
            'search': 5.0,
            'form_submit': 7.0,
            'goal_achieved': 50.0,
            'navigation': 2.0,
            'exploration': 3.0
        }

        self.penalties = {
            'duplicate': -0.5,
            'no_change': -0.3,
            'error': -0.5,
            'wasting_time': -1.0,
            'going_in_circles': -2.0,
            'stale_content': -0.2
        }

    def calculate_reward(self,
                         action: Dict,
                         state_before: Dict,
                         state_after: Dict,
                         success: bool,
                         cycle: int) -> float:

        reward = 0.0

        if success:
            reward += self.rewards['successful_click']
            self.success_count += 1

        # Page change detection
        url_before = state_before.get('page', {}).get('url', '')
        url_after = state_after.get('page', {}).get('url', '')
        if url_before and url_after and url_before != url_after:
            reward += self.rewards['new_page']
            print(f"   🌐 +{self.rewards['new_page']}: New page!")
            
            if url_after not in self.visited_urls:
                self.visited_urls.add(url_after)
                reward += 1.0

        # State change
        state_id_before = state_before.get('state_id', '')
        state_id_after = state_after.get('state_id', '')
        if state_id_before and state_id_after and state_id_before != state_id_after:
            reward += self.rewards['new_state']
            print(f"   🆕 +{self.rewards['new_state']}: New state!")

        # Page type discovery
        page_types_before = state_before.get('page_types', {})
        page_types_after = state_after.get('page_types', {})
        
        for key in ['is_listing', 'is_detail', 'is_search', 'is_homepage', 'is_login']:
            if page_types_after.get(key) and not page_types_before.get(key):
                reward += self.rewards['new_page_type']
                print(f"   📋 +{self.rewards['new_page_type']}: Discovered {key}!")
                break

        # Content discovery
        items_before = len(state_before.get('dom', {}).get('content_items', []))
        items_after = len(state_after.get('dom', {}).get('content_items', []))
        if items_after > items_before:
            reward += min(items_after - items_before, 3) * 1.5
            print(f"   📄 +{(items_after - items_before) * 1.5:.1f}: New content items!")

        # Action-specific rewards
        semantics = action.get('semantics', 'generic')
        if semantics == 'pagination' and url_before == url_after:
            reward += self.rewards['pagination']
            print(f"   📄 +{self.rewards['pagination']}: Pagination!")
        elif semantics == 'search':
            reward += self.rewards['search']
            print(f"   🔍 +{self.rewards['search']}: Search action!")
        elif semantics in ['action', 'authentication']:
            reward += self.rewards['form_submit'] * 0.5
            print(f"   ⚡ +{self.rewards['form_submit'] * 0.5:.1f}: Form/action!")

        # Goal achievement - STRICT
        if state_after.get('goals', {}).get('has_completed_action', False):
            reward += self.rewards['goal_achieved']
            print(f"   🎉 +{self.rewards['goal_achieved']}: GOAL ACHIEVED!")
            self.success_count += 3
        
        if state_after.get('page_types', {}).get('is_confirmation', False):
            # Check if it's not a banner page
            if not state_after.get('goals', {}).get('is_banner_page', False):
                reward += self.rewards['goal_achieved']
                print(f"   🎉 +{self.rewards['goal_achieved']}: CONFIRMATION PAGE!")
                self.success_count += 3

        # Penalties
        action_key = ActionNormalizer.normalize(action)['normalized_key']
        
        if action_key in self.action_history:
            repeat_count = list(self.action_history).count(action_key)
            if repeat_count > 2:
                penalty = self.penalties['wasting_time'] * 0.3
                reward += penalty
                print(f"   🔄 Penalty: {penalty:.1f} (repeated action)")

        if url_before == url_after and success:
            reward += self.penalties['no_change'] * 0.5
            print(f"   ⚠️ Penalty: {self.penalties['no_change'] * 0.5:.1f} (no change)")

        # Bonus for exploring new areas
        if state_after.get('page_types', {}).get('has_items', False) and not state_before.get('page_types', {}).get('has_items', False):
            reward += self.rewards['content_discovery']
            print(f"   💡 +{self.rewards['content_discovery']}: Content discovered!")

        self.action_history.append(action_key)
        self.reward_history.append(reward)

        return max(-5.0, min(60.0, reward))

    def get_progress(self) -> float:
        if not self.reward_history:
            return 0.0
        recent = list(self.reward_history)[-20:]
        return sum(recent) / len(recent) if recent else 0.0

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
        self.stuck_count = 0
        self.discovery_count = 0
        self.consecutive_no_change = 0

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
        
        print(f"📍 Starting on: {self.current_state.get('page', {}).get('url', 'unknown')[:80]}")
        print(f"📊 Initial state: {state_id}")

        for self.cycle in range(1, self.max_cycles + 1):
            print(f"\n{'='*70}")
            print(f"🔄 CYCLE {self.cycle}/{self.max_cycles}")
            print(f"{'='*70}")

            try:
                page = self.current_state.get('page', {})
                page_types = self.current_state.get('page_types', {})
                
                print(f"📍 {page.get('url', 'unknown')[:80]}")
                print(f"📊 State: {state_id}")
                print(f"🏷️  Type: {self._get_page_type_label(page_types)}")
                print(f"🏷️  Landmarks: {self._get_landmark_summary(self.current_state)}")

                # Check if we're stuck
                if self.consecutive_no_change > 3:
                    print(f"   ⚠️ No progress detected ({self.consecutive_no_change} cycles)")
                    self.stuck_count += 1
                    
                    if self.stuck_count >= 2:
                        print("   🔄 Attempting generic escape...")
                        escape_methods = [
                            lambda: GenericEscaper.escape_to_origin(self.cdp),
                            lambda: GenericEscaper.escape_to_home(self.cdp),
                            lambda: GenericEscaper.escape_back(self.cdp)
                        ]
                        
                        for method in escape_methods:
                            if method():
                                time.sleep(2)
                                break
                        
                        self.stuck_count = 0
                        self.consecutive_no_change = 0
                        self.current_state = self.state_extractor.extract()
                        state_id = self.current_state.get('state_id')
                        continue

                # Check goal - STRICT
                if self.q_agent.check_goal_achieved(self.current_state):
                    print("\n🎉🎉🎉 GOAL ACHIEVED! 🎉🎉🎉")
                    print("   Successfully completed an action!")
                    self.goal_achieved = True
                    break

                # Prepare actions
                preparer = ActionPreparer(self.current_state)
                raw_actions = preparer.prepare_actions()
                actions = ActionValidator.filter_actions(raw_actions)
                print(f"⚡ Actions: {len(actions)} available (filtered from {len(raw_actions)})")

                # SPA loading detection
                if not actions:
                    print(f"   ⏳ No actions - checking if page is loading...")
                    
                    for retry in range(3):
                        print(f"   🔄 Retry {retry+1}/3: waiting 1.5s...")
                        time.sleep(1.5)
                        
                        retry_state = self.state_extractor.extract()
                        retry_preparer = ActionPreparer(retry_state)
                        retry_raw = retry_preparer.prepare_actions()
                        retry_actions = ActionValidator.filter_actions(retry_raw)
                        
                        if retry_actions:
                            print(f"   ✅ Found {len(retry_actions)} actions after waiting!")
                            self.current_state = retry_state
                            state_id = self.current_state.get('state_id')
                            actions = retry_actions
                            break
                    
                    if not actions:
                        self.no_action_count += 1
                        if self.no_action_count >= 3:
                            print("   🔄 True dead-end - attempting escape...")
                            GenericEscaper.escape_to_origin(self.cdp)
                            self.no_action_count = 0
                            self.consecutive_no_change += 1
                        
                        time.sleep(2)
                        self.current_state = self.state_extractor.extract()
                        state_id = self.current_state.get('state_id')
                        continue

                self.no_action_count = 0

                # Show top actions
                print("\n📋 Top Actions:")
                for i, action in enumerate(actions[:5], 1):
                    norm = ActionNormalizer.normalize(action)
                    priority = action.get('priority', 'medium')
                    print(f"   {i}. [{priority}] {norm['text'][:25]:25} | {norm['semantics']:15}")

                # Choose action
                action = self.q_agent.choose_action(state_id, actions)
                if not action:
                    print("   ⚠️ No action chosen.")
                    time.sleep(1)
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

                # Calculate reward
                reward = self.reward_engine.calculate_reward(
                    action, self.current_state, new_state, success, self.cycle
                )

                if reward > self.best_reward:
                    self.best_reward = reward
                    print(f"   📈 New best reward: {reward:.2f}")

                # Check for no change
                if self.current_state.get('state_id') == new_state_id:
                    self.consecutive_no_change += 1
                else:
                    self.consecutive_no_change = 0
                    self.discovery_count += 1

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

                best_path = self.q_agent.get_best_path()
                if best_path:
                    path_str = ' → '.join(best_path['actions'][-3:])
                    print(f"   🏆 Best Path: {path_str} (reward: {best_path['reward']:.2f})")

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

    def _get_page_type_label(self, page_types: Dict) -> str:
        labels = []
        if page_types.get('is_homepage'):
            labels.append('🏠 Home')
        if page_types.get('is_listing'):
            labels.append('📋 Listing')
        if page_types.get('is_detail'):
            labels.append('📄 Detail')
        if page_types.get('is_search'):
            labels.append('🔍 Search')
        if page_types.get('is_login'):
            labels.append('🔐 Login')
        if page_types.get('has_modal'):
            labels.append('📱 Modal')
        if page_types.get('is_dynamic'):
            labels.append('⚡ SPA')
        if page_types.get('has_pagination'):
            labels.append('📑 Pages')
        if page_types.get('has_items'):
            labels.append('📦 Items')
        return ' | '.join(labels) if labels else '📄 Unknown'

    def _get_landmark_summary(self, state: Dict) -> str:
        landmark_counts = Counter()
        for el in state.get('dom', {}).get('interactive_elements', []):
            landmark = el.get('landmark', 'body')
            landmark_counts[landmark] += 1

        if not landmark_counts:
            return "No landmarks"

        top = landmark_counts.most_common(3)
        return ", ".join([f"{l}:{c}" for l, c in top])

    def save_state(self):
        state = {
            'cycle': self.cycle,
            'goal_achieved': self.goal_achieved,
            'best_reward': self.best_reward,
            'discovery_count': self.discovery_count,
            'q_stats': self.q_agent.get_stats(),
            'reward_progress': list(self.reward_engine.reward_history)[-20:],
            'episodes': len(self.episode_history),
            'best_path': self.q_agent.get_best_path(),
            'success_count': self.reward_engine.success_count,
            'visited_urls': list(self.reward_engine.visited_urls)[-10:],
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
        report.append(f"Pages Discovered: {len(self.reward_engine.visited_urls)}")
        report.append(f"States Discovered: {self.discovery_count}")
        report.append("")

        stats = self.q_agent.get_stats()
        report.append("📊 Q-LEARNING STATS:")
        report.append(f"  States Discovered: {stats['state_count']}")
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

            report.append(f"\n🌐 Visited Pages:")
            for url in list(self.reward_engine.visited_urls)[-5:]:
                report.append(f"  {url[:80]}")

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
