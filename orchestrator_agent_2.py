#!/usr/bin/env python3
"""
PRODUCTION RL AGENT - FINAL OPTIMIZED
Fixed issues: 
✅ Better exploration when stuck
✅ Goal achievement with 50-point bonus  
✅ Page change detection
✅ Learning rate adjustment
✅ Success path validation
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
from collections import defaultdict, deque
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
# Enhanced State Extractor
# ============================================================================

class StateExtractor:
    def __init__(self, cdp: CDPWrapper):
        self.cdp = cdp
        
    def extract(self, tab_index: int = 0) -> Dict:
        page_info = self._get_page_info(tab_index)
        dom_features = self._get_dom_features(tab_index)
        goal_features = self._get_goal_features(tab_index)
        
        url = page_info.get('url', '')
        job_id = None
        job_id_match = re.search(r'job[_-]?(\d+)', url)
        if job_id_match:
            job_id = job_id_match.group(1)
        
        state = {
            'page': page_info,
            'dom': dom_features,
            'goals': goal_features,
            'job_id': job_id,
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
                text: document.body ? document.body.innerText : '',
                has_login_form: document.querySelectorAll('input[type="password"]').length > 0,
                has_search: document.querySelectorAll('input[type="search"]').length > 0,
                has_results: document.querySelectorAll('.result, .job, .listing').length > 0,
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
            
            document.querySelectorAll('nav a[href], .nav a[href]').forEach(el => {
                features.navigation_links.push({
                    text: el.textContent.trim(),
                    href: el.getAttribute('href')
                });
            });
            
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
                is_on_confirmation: text.includes('success') || text.includes('thank you') || text.includes('completed'),
                has_application_success: text.includes('application submitted') || 
                                         text.includes('thank you for applying') ||
                                         text.includes('application successfully') ||
                                         text.includes('your application has been submitted')
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
        job_id = state.get('job_id', '')
        
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
            'has_success': goals.get('has_application_success', False),
            'button_count': min(5, page.get('button_count', 0) // 2),
            'job_id': job_id
        }
        
        state_str = json.dumps(features, sort_keys=True)
        return hashlib.md5(state_str.encode()).hexdigest()[:16]

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
# Optimized Q-Learning Agent
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
                 experience_buffer_size: int = 2000,
                 batch_size: int = 32,
                 max_states: int = 500,
                 max_sequence_length: int = 5):
        
        self.lr = learning_rate
        self.gamma = discount_factor
        self.epsilon = exploration_rate
        self.epsilon_decay = exploration_decay
        self.epsilon_min = min_exploration
        self.max_states = max_states
        self.max_sequence_length = max_sequence_length
        
        self.q_table = defaultdict(lambda: defaultdict(float))
        self.experience_buffer = deque(maxlen=experience_buffer_size)
        self.batch_size = batch_size
        
        self.total_actions = 0
        self.state_visits = defaultdict(int)
        self.action_visits = defaultdict(int)
        self.consecutive_repeats = 0
        self.stuck_count = 0
        
        # Action sequence tracking
        self.action_history = deque(maxlen=max_sequence_length)
        self.successful_sequences = deque(maxlen=100)
        self.best_sequences = {}
        
        # Memory of successful paths
        self.successful_paths = deque(maxlen=50)
        self.state_action_memory = defaultdict(list)
        
        # Convergence tracking
        self.is_converged = False
        self.performance_history = deque(maxlen=50)
        self.goal_achieved = False
        
        # Learning rate adaptation
        self.base_lr = learning_rate
        self.stuck_threshold = 5
        
        print(f"🧠 Advanced Q-Learning Agent:")
        print(f"   LR: {self.lr}, γ: {self.gamma}, ε: {self.epsilon}")
        print(f"   Max States: {self.max_states}")
        print(f"   Sequence Length: {max_sequence_length}")
        print(f"   Memory: {self.successful_paths.maxlen} paths")
    
    def choose_action(self, state_id: str, actions: List[Dict]) -> Optional[Dict]:
        if not actions:
            return None
        
        self.total_actions += 1
        self.state_visits[state_id] += 1
        
        # Force exploration if stuck
        if self.stuck_count > self.stuck_threshold:
            self.epsilon = min(0.9, self.epsilon * 1.1)
            print(f"   🚨 Stuck! Increasing exploration to {self.epsilon:.3f}")
            self.stuck_count = 0
        
        # If we've repeated too much, force exploration
        if self.consecutive_repeats > 2:
            self.epsilon = min(0.9, self.epsilon * 1.05)
            self.consecutive_repeats = 0
        
        # Check if we have a successful sequence for this state
        if state_id in self.best_sequences and random.random() < 0.25:
            best_actions = self.best_sequences[state_id]
            for action in actions:
                norm = ActionNormalizer.normalize(action)
                if norm['normalized_key'] in best_actions:
                    print(f"   🔮 Following successful path: {norm['text']}")
                    self.stuck_count = 0
                    return action
        
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
                    ucb = 4.0  # Strong bonus for untried
                
                # Diversity bonus
                diversity = 0.5 if visits < 3 else 0
                
                # Sequence bonus
                sequence_bonus = 0
                if self.action_history:
                    for seq in self.successful_sequences:
                        if normalized['normalized_key'] in seq:
                            sequence_bonus += 0.5
                
                score = q_value + ucb + diversity + sequence_bonus
                action_scores.append((score, action))
            
            action_scores.sort(key=lambda x: x[0], reverse=True)
            
            # More random exploration
            if len(action_scores) >= 3 and random.random() < 0.5:
                chosen = random.choice(action_scores[:3])[1]
            else:
                chosen = action_scores[0][1] if action_scores else random.choice(actions)
            
            # Track if we're repeating
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
            # Exploit
            best_action = None
            best_value = -float('inf')
            
            for action in actions:
                normalized = ActionNormalizer.normalize(action)
                action_key = (state_id, normalized['normalized_key'])
                q_value = self.q_table[state_id][action_key]
                
                # Sequence bonus
                if self.action_history:
                    for seq in self.successful_sequences:
                        if normalized['normalized_key'] in seq:
                            q_value += 0.5
                
                if q_value > best_value:
                    best_value = q_value
                    best_action = action
            
            if best_action:
                self.stuck_count = max(0, self.stuck_count - 1)
            return best_action if best_action else random.choice(actions)
    
    def learn(self, state_id: str, action: Dict, reward: float, next_state_id: str):
        normalized = ActionNormalizer.normalize(action)
        action_key = (state_id, normalized['normalized_key'])
        
        # Track action usage
        self.action_visits[action_key] += 1
        
        # Store state-action memory
        self.state_action_memory[state_id].append((normalized['normalized_key'], reward))
        if len(self.state_action_memory[state_id]) > 10:
            self.state_action_memory[state_id] = self.state_action_memory[state_id][-10:]
        
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
        
        # Track successful sequences
        self.action_history.append(normalized['normalized_key'])
        if reward > 5.0:
            seq = list(self.action_history)
            self.successful_sequences.append(seq)
            
            if state_id not in self.best_sequences:
                self.best_sequences[state_id] = []
            if normalized['normalized_key'] not in self.best_sequences[state_id]:
                self.best_sequences[state_id].append(normalized['normalized_key'])
                if len(self.best_sequences[state_id]) > 3:
                    self.best_sequences[state_id] = self.best_sequences[state_id][-3:]
        
        # Store successful path
        if reward > 3.0:
            path = SuccessfulPath(
                actions=list(self.action_history),
                reward=reward,
                success_count=1
            )
            self.successful_paths.append(path)
        
        # Batch learning
        if len(self.experience_buffer) >= self.batch_size:
            self._batch_learn()
        
        # Action pruning
        self._prune_negative_actions(state_id)
        
        # Decay exploration
        self.epsilon = max(self.epsilon_min, self.epsilon * self.epsilon_decay)
        
        # Adaptive learning rate
        self._adjust_learning_rate()
        
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
    
    def _prune_negative_actions(self, state_id: str):
        if state_id not in self.q_table:
            return
        
        total_visits = sum(1 for _ in self.q_table[state_id].values())
        if total_visits < 5:
            return
        
        negative_actions = []
        for action_key, q_value in self.q_table[state_id].items():
            if q_value < -2.0:
                negative_actions.append(action_key)
        
        for action_key in negative_actions:
            del self.q_table[state_id][action_key]
            if len(self.q_table[state_id]) == 0:
                del self.q_table[state_id]
    
    def _adjust_learning_rate(self):
        if self.epsilon > 0.4:
            self.lr = min(0.25, self.base_lr * 1.5)
        else:
            self.lr = max(0.05, self.base_lr * 0.8)
    
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
        page = state.get('page', {})
        text = page.get('text', '').lower()
        
        success_indicators = [
            'application submitted',
            'thank you for applying',
            'application successfully',
            'your application has been submitted',
            'application complete'
        ]
        
        for indicator in success_indicators:
            if indicator in text:
                self.goal_achieved = True
                return True
        
        if goals.get('has_application_success', False):
            self.goal_achieved = True
            return True
        
        return False
    
    def get_best_path(self) -> Dict:
        if not self.successful_paths:
            return {}
        
        best = max(self.successful_paths, key=lambda p: p.reward)
        return {
            'actions': best.actions,
            'reward': best.reward,
            'success_count': best.success_count
        }
    
    def get_stats(self) -> Dict:
        return {
            'state_count': len(self.q_table),
            'total_q_values': sum(len(v) for v in self.q_table.values()),
            'exploration_rate': self.epsilon,
            'learning_rate': self.lr,
            'total_actions': self.total_actions,
            'unique_actions': len(self.action_visits),
            'consecutive_repeats': self.consecutive_repeats,
            'successful_paths': len(self.successful_paths),
            'best_sequences': len(self.best_sequences),
            'goal_achieved': self.goal_achieved,
            'stuck_count': self.stuck_count
        }

# ============================================================================
# Enhanced Reward Engine
# ============================================================================

class RewardEngine:
    def __init__(self):
        self.reward_history = deque(maxlen=100)
        self.action_history = deque(maxlen=30)
        self.page_history = deque(maxlen=10)
        self.cycle_history = deque(maxlen=10)
        self.success_count = 0
        
        self.rewards = {
            'new_page': 5.0,
            'job_listing': 10.0,
            'apply_button': 15.0,
            'save_button': 10.0,
            'search': 6.0,
            'new_content': 3.0,
            'success_click': 1.0,
            'new_state': 2.0,
            'goal_achieved': 50.0
        }
        
        self.penalties = {
            'duplicate': -0.5,
            'no_change': -0.3,
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
            self.success_count += 1
        
        # State change reward
        state_id_before = state_before.get('state_id', '')
        state_id_after = state_after.get('state_id', '')
        if state_id_before and state_id_after and state_id_before != state_id_after:
            reward += self.rewards['new_state']
            print(f"   🆕 +{self.rewards['new_state']}: New state!")
        
        # Goal achievement detection
        if state_after.get('goals', {}).get('has_application_success', False):
            reward += self.rewards['goal_achieved']
            print(f"   🎉 +{self.rewards['goal_achieved']}: GOAL ACHIEVED!")
            self.success_count += 3
        
        # Check page text for goal indicators
        page_text = state_after.get('page', {}).get('text', '').lower()
        if any(indicator in page_text for indicator in [
            'application submitted', 'thank you for applying',
            'application successfully', 'your application has been submitted'
        ]):
            reward += self.rewards['goal_achieved']
            print(f"   🎉 +{self.rewards['goal_achieved']}: GOAL ACHIEVED! (text detection)")
            self.success_count += 3
        
        # Goal detection (existing rewards)
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
        
        # Penalties for wasting time
        action_key = ActionNormalizer.normalize(action)['normalized_key']
        
        # Duplicate action penalty
        if action_key in self.action_history:
            repeat_count = list(self.action_history).count(action_key)
            if repeat_count > 2:  # Reduced threshold
                reward += self.penalties['wasting_time'] * 0.3
                print(f"   ⏰ {self.penalties['wasting_time'] * 0.3}: Repeating too much!")
        
        # Penalty for going in circles
        if len(self.page_history) >= 4:
            recent_pages = list(self.page_history)[-4:]
            if len(set(recent_pages)) < 3:
                reward += self.penalties['going_in_circles'] * 0.5
                print(f"   🔄 {self.penalties['going_in_circles'] * 0.5}: Going in circles!")
        
        # No change penalty (reduced)
        if url_before == url_after and success:
            reward += self.penalties['no_change'] * 0.5
        
        # Track history
        self.action_history.append(action_key)
        self.reward_history.append(reward)
        self.cycle_history.append(cycle)
        
        # Clamp reward
        return max(-5.0, min(60.0, reward))
    
    def get_progress(self) -> float:
        if not self.reward_history:
            return 0.0
        recent = list(self.reward_history)[-20:]
        return sum(recent) / len(recent) if recent else 0.0
    
    def get_exploration_score(self) -> float:
        unique_pages = len(set(self.page_history))
        return min(1.0, unique_pages / 10)

# ============================================================================
# Action Preparer
# ============================================================================

class ActionPreparer:
    def __init__(self, state: Dict):
        self.state = state
        
    def prepare_actions(self) -> List[Dict]:
        actions = []
        seen_texts = set()
        
        interactive = self.state.get('dom', {}).get('interactive_elements', [])
        
        # Categorize actions
        job_actions = []
        nav_actions = []
        other_actions = []
        
        for el in interactive:
            text = el.get('text', '').strip()
            if not text or len(text) < 2:
                continue
            
            if text in seen_texts:
                continue
            seen_texts.add(text)
            
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
        
        # Prioritize
        ordered_actions = job_actions + nav_actions + other_actions
        
        for text, semantics, priority in ordered_actions[:25]:
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
        
        # Navigation links
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
        self.goal_achieved = False
        self.best_reward = -float('inf')
        self.stuck_reload_count = 0
        
        print("=" * 70)
        print("🚀 PRODUCTION RL AGENT - FINAL OPTIMIZED")
        print("=" * 70)
        print("✅ Enhanced exploration when stuck")
        print("✅ Goal achievement with 50-point bonus")
        print("✅ Page change detection")
        print("✅ Learning rate adjustment")
        print("✅ Success path validation")
        print("=" * 70)
        print(f"Max Cycles: {max_cycles}")
        print(f"Session: {self.session_dir}\n")
        
    def connect(self) -> bool:
        return self.cdp.connect()
    
    def run(self):
        print("🚀 Starting Production Reinforcement Learning...\n")
        
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
                
                # Check if goal achieved
                if self.q_agent.check_goal_achieved(self.current_state):
                    print("\n🎉🎉🎉 GOAL ACHIEVED! 🎉🎉🎉")
                    print("   Application successfully submitted!")
                    self.goal_achieved = True
                    
                    best_path = self.q_agent.get_best_path()
                    if best_path:
                        with open(self.session_dir / "success_path.json", 'w') as f:
                            json.dump({
                                'path': best_path['actions'],
                                'reward': best_path['reward'],
                                'cycle': self.cycle
                            }, f, indent=2)
                        print(f"   💾 Successful path saved!")
                    break
                
                # Check if stuck on same page
                if self.cycle > 3:
                    recent_urls = [ep.get('url', '') for ep in self.episode_history[-3:] if 'url' in ep]
                    if recent_urls and len(set(recent_urls)) == 1:
                        print("   ⚠️ Stuck on same page for 3 cycles!")
                        if self.stuck_reload_count < 2:
                            print("   🔄 Trying to navigate away...")
                            # Try a random navigation action
                            nav_links = self.current_state.get('dom', {}).get('navigation_links', [])
                            if nav_links:
                                random_link = random.choice(nav_links[:3])
                                if random_link.get('href'):
                                    print(f"   🔗 Navigating to: {random_link.get('text', '')[:30]}")
                                    self.cdp.execute_js(f"window.location.href = '{random_link['href']}'", 0)
                                    time.sleep(3)
                                    self.stuck_reload_count += 1
                                    self.current_state = self.state_extractor.extract()
                                    state_id = self.current_state.get('state_id')
                                    continue
                
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
                        self.stuck_reload_count = 0
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
                    'url': new_state.get('page', {}).get('url', ''),
                    'goal_achieved': self.goal_achieved
                })
                
                print(f"\n📊 Results:")
                print(f"   Success: {'✅' if success else '❌'}")
                print(f"   Reward: {reward:.2f}")
                print(f"   States: {self.q_agent.get_stats()['state_count']}")
                print(f"   Q-Values: {self.q_agent.get_stats()['total_q_values']}")
                print(f"   ε: {self.q_agent.epsilon:.3f}")
                print(f"   LR: {self.q_agent.lr:.3f}")
                print(f"   Stuck: {self.q_agent.stuck_count}")
                
                best_path = self.q_agent.get_best_path()
                if best_path:
                    print(f"   🏆 Best Path: {' → '.join(best_path['actions'][-3:])} (reward: {best_path['reward']:.2f})")
                
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
            'goal_achieved': self.goal_achieved,
            'best_reward': self.best_reward,
            'q_stats': self.q_agent.get_stats(),
            'reward_progress': list(self.reward_engine.reward_history)[-20:],
            'episodes': len(self.episode_history),
            'best_path': self.q_agent.get_best_path(),
            'success_count': self.reward_engine.success_count,
            'timestamp': datetime.now().isoformat()
        }
        with open(self.session_dir / "agent_state.json", 'w') as f:
            json.dump(state, f, indent=2, default=str)
        print(f"\n💾 State saved to {self.session_dir}")
    
    def generate_report(self):
        report = []
        report.append("=" * 80)
        report.append("🚀 PRODUCTION RL AGENT - FINAL REPORT")
        report.append("=" * 80)
        report.append(f"Total Cycles: {self.cycle}")
        report.append(f"Goal Achieved: {'✅ YES!' if self.goal_achieved else '🔄 Still learning'}")
        report.append(f"Best Reward: {self.best_reward:.2f}")
        report.append(f"Success Events: {self.reward_engine.success_count}")
        report.append("")
        
        stats = self.q_agent.get_stats()
        report.append("📊 Q-LEARNING STATS:")
        report.append(f"  States Discovered: {stats['state_count']}")
        report.append(f"  Q-Values Learned: {stats['total_q_values']}")
        report.append(f"  Exploration Rate: {stats['exploration_rate']:.3f}")
        report.append(f"  Learning Rate: {stats['learning_rate']:.3f}")
        report.append(f"  Total Actions: {stats['total_actions']}")
        report.append(f"  Unique Actions: {stats['unique_actions']}")
        report.append(f"  Successful Paths: {stats['successful_paths']}")
        report.append(f"  Best Sequences: {stats['best_sequences']}")
        report.append(f"  Stuck Count: {stats['stuck_count']}")
        report.append("")
        
        best_path = self.q_agent.get_best_path()
        if best_path:
            report.append("🏆 BEST PATH FOUND:")
            report.append(f"  {' → '.join(best_path['actions'][-5:])}")
            report.append(f"  Reward: {best_path['reward']:.2f}")
            report.append(f"  Success Count: {best_path['success_count']}")
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
    print("🚀 PRODUCTION RL AGENT - FINAL OPTIMIZED")
    print("=" * 70)
    print("All features optimized:")
    print("  ✅ Enhanced exploration when stuck")
    print("  ✅ Goal achievement with 50-point bonus")
    print("  ✅ Page change detection")
    print("  ✅ Learning rate adjustment")
    print("  ✅ Success path validation")
    print("  ✅ Stuck detection and recovery")
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
