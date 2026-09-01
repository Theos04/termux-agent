#!/usr/bin/env python3
"""
AGI MATH SYSTEM - INTEGRATED WITH geturl.py
Proper integration using DOMExplorer's actual methods
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
import random
import math
import traceback
import numpy as np
from dataclasses import dataclass, field

# Try to import geturl.py
try:
    from geturl import ChromePage, DOMExplorer
    GETURL_AVAILABLE = True
except ImportError:
    print("⚠️ geturl.py not found, using fallback")
    GETURL_AVAILABLE = False

# ============================================================================
# CONFIGURATION
# ============================================================================

AGI_CONFIG = {
    "action_delay": 12.0,
    "perception_delay": 15.0,
    "max_cycles": 30,
    "embedding_dim": 128,
    "population_size": 5,
    "mutation_rate": 0.08,
    "learning_rate": 0.001,
    "gamma": 0.95,
    "port": 9260,
    "reasoning_horizon": 8,
    "repeat_action_penalty": -2.0,
    "novelty_bonus": 1.5,
}

# ============================================================================
# 1. INTEGRATED CDP WRAPPER (uses geturl.py)
# ============================================================================

class IntegratedCDPWrapper:
    """
    Integrates geturl.py ChromePage and DOMExplorer
    """
    
    def __init__(self, port: int = 9260):
        self.port = port
        self.page = None
        self.explorer = None
        self.connected = False
        
    def connect(self) -> bool:
        """Connect using geturl.py ChromePage"""
        try:
            if GETURL_AVAILABLE:
                self.page = ChromePage(port=self.port)
                if self.page.connect():
                    self.connected = True
                    self.explorer = DOMExplorer(self.page)
                    print(f"🔍 Connected to: {self.page.get_title()}")
                    print(f"📍 {self.page.page_url}")
                    return True
            else:
                # Fallback to direct CDP
                from dynamic_cdp_6 import EnhancedChromeCDP
                self.client = EnhancedChromeCDP(port=self.port)
                tabs = self.client.get_tabs()
                if tabs:
                    self.connected = True
                    print(f"🔍 Connected to {len(tabs)} tabs (fallback)")
                    return True
        except Exception as e:
            print(f"⚠️ Connect error: {e}")
        return False
        
    def get_perception_data(self) -> Dict:
        """
        Get rich perception data using DOMExplorer
        Returns combined data from multiple methods
        """
        if not self.connected or not self.explorer:
            return self._get_fallback_perception()
            
        try:
            # Get all data using DOMExplorer methods
            link_map = self.explorer.map_links()
            competitor_analysis = self.explorer.get_competitor_analysis()
            page_structure = self.explorer.explore_page_structure()
            clickable_elements = self.page.get_clickable_elements()
            form_inputs = self.page.get_form_inputs()
            metadata = self.page.get_page_metadata()
            
            # Get all URLs
            all_urls = self.explorer.get_all_urls()
            
            # Get interactive elements with context
            interactive_elements = []
            for el in clickable_elements[:50]:
                interactive_elements.append({
                    'text': el.get('text', ''),
                    'tag': el.get('tag', ''),
                    'href': el.get('href', ''),
                    'id': el.get('id', ''),
                    'classes': el.get('classes', ''),
                    'position': el.get('position', {}),
                    'form_action': el.get('form_action'),
                    'form_method': el.get('form_method'),
                    'is_visible': el.get('is_visible', True)
                })
                
            return {
                'url': self.page.page_url,
                'title': self.page.get_title(),
                'text': self.page.get_text(),
                'metadata': metadata,
                'interactives': interactive_elements,
                'form_inputs': form_inputs,
                'all_links': link_map,
                'competitor_analysis': competitor_analysis,
                'page_structure': page_structure,
                'all_urls': all_urls,
                'clickable_count': len(clickable_elements),
                'form_count': len(form_inputs),
                'timestamp': time.time()
            }
            
        except Exception as e:
            print(f"⚠️ Perception error: {e}")
            return self._get_fallback_perception()
            
    def _get_fallback_perception(self) -> Dict:
        """Fallback when geturl.py is not available"""
        script = """
        (function() {
            const interactives = [];
            document.querySelectorAll('button, a[href], [role="button"], input, select').forEach(el => {
                const rect = el.getBoundingClientRect();
                interactives.push({
                    text: (el.textContent || '').trim().slice(0, 100),
                    tag: el.tagName.toLowerCase(),
                    href: el.getAttribute('href'),
                    id: el.id || '',
                    classes: el.className || '',
                    visible: rect.width > 0 && rect.height > 0,
                    position: { x: rect.x || 0, y: rect.y || 0 }
                });
            });
            
            return {
                url: window.location.href,
                title: document.title,
                interactives: interactives,
                total_elements: document.querySelectorAll('*').length,
                timestamp: Date.now()
            };
        })()
        """
        
        try:
            if hasattr(self, 'client') and self.client:
                result = self.client.evaluate_script(script)
                if result:
                    return result
        except:
            pass
            
        return {
            'url': '',
            'title': '',
            'interactives': [],
            'total_elements': 0
        }
        
    def execute_action(self, action: Dict) -> Dict:
        """Execute action using geturl.py methods"""
        text = action.get('text', '')
        
        try:
            # Try clicking by text first
            if text and text != '[No text]':
                success = self.page.click_by_text(text)
                if success:
                    return {'success': True, 'method': 'text'}
                
            # Try by selector if available
            selector = action.get('selector', '')
            if selector:
                success = self.page.click_element(selector)
                if success:
                    return {'success': True, 'method': 'selector'}
                
            # Try by ID
            el_id = action.get('id', '')
            if el_id:
                success = self.page.click_element(f"#{el_id}")
                if success:
                    return {'success': True, 'method': 'id'}
                
            # Fallback: try to find by text using JS
            script = f"""
            (function() {{
                const targetText = '{text[:30].replace("'", "\\'")}';
                const elements = document.querySelectorAll('button, a[href], [role="button"]');
                let el = null;
                
                for (let elem of elements) {{
                    const t = elem.textContent.trim();
                    if (t === targetText || t.includes(targetText) || targetText.includes(t)) {{
                        el = elem;
                        break;
                    }}
                }}
                
                if (el) {{
                    el.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                    setTimeout(() => {{
                        el.click();
                        el.dispatchEvent(new MouseEvent('click', {{
                            bubbles: true,
                            cancelable: true,
                            view: window
                        }}));
                    }}, 150);
                    return {{ success: true }};
                }}
                
                return {{ success: false, error: 'Element not found' }};
            }})()
            """
            
            result = self.page.js(script)
            if result and result.get('success', False):
                return {'success': True, 'method': 'fallback_js'}
                
            return {'success': False, 'error': 'Could not click element'}
            
        except Exception as e:
            return {'success': False, 'error': str(e)}

# ============================================================================
# 2. MATHEMATICAL EMBEDDING
# ============================================================================

class MathematicalEmbedding:
    """Embedding using geturl.py data"""
    
    def __init__(self, embedding_dim: int = 128):
        self.embedding_dim = embedding_dim
        
        self.W_interactive = np.random.randn(128, embedding_dim) * np.sqrt(2.0 / 128)
        self.W_structure = np.random.randn(64, embedding_dim) * np.sqrt(2.0 / 64)
        self.W_metadata = np.random.randn(64, embedding_dim) * np.sqrt(2.0 / 64)
        
        self.b_interactive = np.zeros(embedding_dim)
        self.b_structure = np.zeros(embedding_dim)
        self.b_metadata = np.zeros(embedding_dim)
        
    def encode(self, perception_data: Dict) -> np.ndarray:
        """Encode perception data into embedding"""
        try:
            interactive_features = self._extract_interactive_features(perception_data)
            structure_features = self._extract_structure_features(perception_data)
            metadata_features = self._extract_metadata_features(perception_data)
            
            interactive_embed = np.dot(interactive_features, self.W_interactive) + self.b_interactive
            structure_embed = np.dot(structure_features, self.W_structure) + self.b_structure
            metadata_embed = np.dot(metadata_features, self.W_metadata) + self.b_metadata
            
            combined = interactive_embed + structure_embed + metadata_embed
            
            norm = np.linalg.norm(combined)
            if norm > 0:
                combined = combined / norm
                
            return combined
            
        except Exception as e:
            print(f"⚠️ Embedding error: {e}")
            return np.random.randn(self.embedding_dim) * 0.01
            
    def _extract_interactive_features(self, data: Dict) -> np.ndarray:
        """Extract interactive element features"""
        features = []
        interactives = data.get('interactives', [])
        
        # Count by tag
        tag_counts = defaultdict(int)
        decisive_count = 0
        visible_count = 0
        
        for el in interactives:
            tag = el.get('tag', '')
            tag_counts[tag] += 1
            if el.get('visible', False):
                visible_count += 1
                
            text = el.get('text', '').lower()
            if any(kw in text for kw in ['apply', 'submit', 'register', 'login', 'search', 'profile', 'job']):
                decisive_count += 1
                
        # Features
        total = max(1, len(interactives))
        features.extend([
            tag_counts.get('button', 0) / total,
            tag_counts.get('a', 0) / total,
            tag_counts.get('input', 0) / total,
            tag_counts.get('select', 0) / total,
            visible_count / total,
            decisive_count / total,
            min(1.0, total / 30)
        ])
        
        while len(features) < 128:
            features.append(0.0)
            
        return np.array(features[:128], dtype=np.float32)
        
    def _extract_structure_features(self, data: Dict) -> np.ndarray:
        """Extract page structure features"""
        features = []
        
        # Page structure counts
        structure = data.get('page_structure', {})
        for key in ['headers', 'navigation', 'main_content', 'sidebars', 'footer', 'forms', 'lists', 'tables']:
            elements = structure.get(key, [])
            features.append(min(1.0, len(elements) / 10))
            
        # Link statistics
        links = data.get('all_links', {})
        features.append(min(1.0, links.get('total_links', 0) / 100))
        features.append(min(1.0, links.get('unique_internal', 0) / 50))
        features.append(min(1.0, links.get('unique_external', 0) / 50))
        
        # Competitor analysis
        comp = data.get('competitor_analysis', {})
        features.append(min(1.0, comp.get('total_competitor_links', 0) / 20))
        features.append(min(1.0, len(comp.get('competitor_keywords_found', [])) / 10))
        
        while len(features) < 64:
            features.append(0.0)
            
        return np.array(features[:64], dtype=np.float32)
        
    def _extract_metadata_features(self, data: Dict) -> np.ndarray:
        """Extract metadata features"""
        features = []
        metadata = data.get('metadata', {})
        
        # Boolean features
        features.append(1.0 if metadata.get('has_form', False) else 0.0)
        features.append(1.0 if metadata.get('has_login_form', False) else 0.0)
        features.append(1.0 if metadata.get('is_secure', False) else 0.0)
        
        # Counts (normalized)
        features.append(min(1.0, metadata.get('total_links', 0) / 100))
        features.append(min(1.0, metadata.get('total_images', 0) / 50))
        features.append(min(1.0, metadata.get('word_count', 0) / 1000))
        
        # URL features
        url = data.get('url', '')
        features.append(1.0 if 'login' in url.lower() else 0.0)
        features.append(1.0 if 'profile' in url.lower() else 0.0)
        features.append(1.0 if 'job' in url.lower() else 0.0)
        features.append(1.0 if 'search' in url.lower() else 0.0)
        
        while len(features) < 64:
            features.append(0.0)
            
        return np.array(features[:64], dtype=np.float32)

# ============================================================================
# 3. JEPA WORLD MODEL
# ============================================================================

class JEPAWorldModel:
    def __init__(self, embedding_dim: int = 128):
        self.embedding_dim = embedding_dim
        
        self.W_state = np.random.randn(embedding_dim, embedding_dim) * np.sqrt(2.0 / embedding_dim)
        self.W_action = np.random.randn(embedding_dim, embedding_dim) * np.sqrt(2.0 / embedding_dim)
        self.b_predict = np.zeros(embedding_dim)
        
        self.m_W_state = np.zeros_like(self.W_state)
        self.v_W_state = np.zeros_like(self.W_state)
        self.m_W_action = np.zeros_like(self.W_action)
        self.v_W_action = np.zeros_like(self.W_action)
        
        self.t = 0
        self.learning_rate = AGI_CONFIG['learning_rate']
        self.beta1 = 0.9
        self.beta2 = 0.999
        self.epsilon = 1e-8
        
    def predict(self, state_embed: np.ndarray, action_embed: np.ndarray) -> np.ndarray:
        if len(state_embed.shape) == 1:
            state_embed = state_embed.reshape(1, -1)
        if len(action_embed.shape) == 1:
            action_embed = action_embed.reshape(1, -1)
            
        state_part = np.dot(state_embed, self.W_state)
        action_part = np.dot(action_embed, self.W_action)
        prediction = np.tanh(state_part + action_part + self.b_predict)
        
        return prediction.flatten()
        
    def learn(self, state_embed: np.ndarray, action_embed: np.ndarray,
              next_state_embed: np.ndarray) -> float:
        self.t += 1
        
        if len(state_embed.shape) == 1:
            state_embed = state_embed.reshape(1, -1)
        if len(action_embed.shape) == 1:
            action_embed = action_embed.reshape(1, -1)
        if len(next_state_embed.shape) == 1:
            next_state_embed = next_state_embed.reshape(1, -1)
        
        state_part = np.dot(state_embed, self.W_state)
        action_part = np.dot(action_embed, self.W_action)
        prediction = np.tanh(state_part + action_part + self.b_predict)
        
        error = prediction - next_state_embed
        
        grad_state = np.dot(error.T, state_embed).T * (1 - prediction**2)
        grad_action = np.dot(error.T, action_embed).T * (1 - prediction**2)
        grad_b = np.mean(error * (1 - prediction**2), axis=0)
        
        self.m_W_state = self.beta1 * self.m_W_state + (1 - self.beta1) * grad_state
        self.v_W_state = self.beta2 * self.v_W_state + (1 - self.beta2) * (grad_state**2)
        m_hat = self.m_W_state / (1 - self.beta1**self.t)
        v_hat = self.v_W_state / (1 - self.beta2**self.t)
        self.W_state -= self.learning_rate * m_hat / (np.sqrt(v_hat) + self.epsilon)
        
        self.m_W_action = self.beta1 * self.m_W_action + (1 - self.beta1) * grad_action
        self.v_W_action = self.beta2 * self.v_W_action + (1 - self.beta2) * (grad_action**2)
        m_hat = self.m_W_action / (1 - self.beta1**self.t)
        v_hat = self.v_W_action / (1 - self.beta2**self.t)
        self.W_action -= self.learning_rate * m_hat / (np.sqrt(v_hat) + self.epsilon)
        
        self.b_predict -= self.learning_rate * grad_b
        
        return float(np.mean(error**2))

# ============================================================================
# 4. EVOLUTIONARY STRATEGY
# ============================================================================

@dataclass
class EvolutionaryAgent:
    weights: Dict[str, np.ndarray] = field(default_factory=dict)
    fitness: float = 0.0
    actions_taken: int = 0
    total_reward: float = 0.0
    exploration_rate: float = 0.3
    age: int = 0
    strategy: str = "balanced"
    action_history: List[str] = field(default_factory=list)
    unique_actions: Set[str] = field(default_factory=set)
    
class EvolutionaryPopulation:
    def __init__(self, population_size: int = 5, embedding_dim: int = 128):
        self.population_size = population_size
        self.embedding_dim = embedding_dim
        self.population = []
        self.generation = 0
        self.best_fitness = -float('inf')
        self.best_agent = None
        self._initialize_population()
        
    def _initialize_population(self):
        strategies = ['greedy', 'exploratory', 'balanced', 'cautious', 'random']
        for i in range(self.population_size):
            agent = EvolutionaryAgent(
                weights={
                    'W_state': np.random.randn(self.embedding_dim, self.embedding_dim) * 0.1,
                    'W_action': np.random.randn(self.embedding_dim, self.embedding_dim) * 0.1,
                    'b_predict': np.zeros(self.embedding_dim)
                },
                exploration_rate=random.uniform(0.1, 0.5),
                strategy=strategies[i % len(strategies)]
            )
            self.population.append(agent)
            
    def evaluate(self, agent_idx: int, reward: float, success: bool, action_text: str):
        agent = self.population[agent_idx]
        agent.action_history.append(action_text)
        if len(agent.action_history) > 20:
            agent.action_history = agent.action_history[-20:]
        agent.unique_actions.add(action_text)
        
        repeat_count = agent.action_history.count(action_text)
        repetition_penalty = AGI_CONFIG['repeat_action_penalty'] * max(0, repeat_count - 3)
        novelty_bonus = AGI_CONFIG['novelty_bonus'] if len(agent.unique_actions) > 5 else 0
        
        adjusted_reward = reward + repetition_penalty + novelty_bonus
        agent.total_reward += adjusted_reward
        agent.actions_taken += 1
        agent.fitness = agent.total_reward / max(1, agent.actions_taken)
        agent.age += 1
        
        if agent.fitness > self.best_fitness:
            self.best_fitness = agent.fitness
            self.best_agent = agent
            
        return adjusted_reward
        
    def evolve(self):
        self.generation += 1
        self.population.sort(key=lambda x: x.fitness, reverse=True)
        
        survivors = self.population[:2]
        while len(survivors) < self.population_size:
            parent1 = self._tournament_select()
            parent2 = self._tournament_select()
            
            child_weights = {}
            for key in parent1.weights.keys():
                mask = np.random.rand(*parent1.weights[key].shape) > 0.5
                child_weights[key] = np.where(mask, parent1.weights[key], parent2.weights[key])
                
            if random.random() < AGI_CONFIG['mutation_rate']:
                for key in child_weights.keys():
                    noise = np.random.randn(*child_weights[key].shape) * 0.05
                    child_weights[key] += noise
                    
            child = EvolutionaryAgent(
                weights=child_weights,
                exploration_rate=random.uniform(0.1, 0.5),
                strategy=random.choice(['greedy', 'exploratory', 'balanced'])
            )
            survivors.append(child)
            
        self.population = survivors
        
        return {
            'generation': self.generation,
            'best_fitness': self.best_fitness,
            'avg_fitness': sum(a.fitness for a in self.population) / len(self.population),
            'best_strategy': self.population[0].strategy
        }
        
    def _tournament_select(self, k: int = 2) -> EvolutionaryAgent:
        candidates = random.sample(self.population, min(k, len(self.population)))
        return max(candidates, key=lambda x: x.fitness)

# ============================================================================
# 5. LONG-CHAIN REASONER
# ============================================================================

class LongChainReasoner:
    def __init__(self, world_model: JEPAWorldModel, embedding_dim: int = 128):
        self.world_model = world_model
        self.embedding_dim = embedding_dim
        self.horizon = AGI_CONFIG['reasoning_horizon']
        self.action_sequences = deque(maxlen=50)
        self.sequence_rewards = deque(maxlen=50)
        self.hypotheses = []
        
    def propose_sequence(self, state_embed: np.ndarray, actions: List[Dict], 
                        horizon: int = None) -> List[Dict]:
        if horizon is None:
            horizon = self.horizon
            
        if len(actions) < 2:
            return actions[:1]
            
        scored_actions = []
        for action in actions[:15]:
            action_embed = self._action_to_embedding(action)
            score = self._score_action_sequence(state_embed, action_embed, action, horizon)
            scored_actions.append((score, action, action_embed))
            
        scored_actions.sort(key=lambda x: x[0], reverse=True)
        
        best_sequence = []
        best_score = -float('inf')
        
        for start_idx in range(min(3, len(scored_actions))):
            sequence = []
            current_state = state_embed.copy()
            total_score = 0
            used_actions = set()
            
            for step in range(horizon):
                best_action = None
                best_action_score = -float('inf')
                best_action_embed = None
                
                for score, action, embed in scored_actions:
                    action_key = action.get('text', '')[:30]
                    if action_key in used_actions and step > 0:
                        continue
                        
                    next_pred = self.world_model.predict(current_state, embed)
                    future_value = self._estimate_future_value(current_state, next_pred, horizon - step)
                    step_score = self._score_prediction(current_state, next_pred, embed) + future_value
                    
                    if step_score > best_action_score:
                        best_action_score = step_score
                        best_action = action
                        best_action_embed = embed
                        
                if best_action:
                    sequence.append(best_action)
                    used_actions.add(best_action.get('text', '')[:30])
                    current_state = self.world_model.predict(current_state, best_action_embed)
                    total_score += best_action_score
                else:
                    break
                    
            if total_score > best_score:
                best_score = total_score
                best_sequence = sequence
                
        if best_sequence:
            self.hypotheses.append({
                'sequence': [a.get('text', '')[:30] for a in best_sequence],
                'score': best_score,
                'horizon': horizon,
                'timestamp': datetime.now().isoformat()
            })
            
        if len(self.hypotheses) > 20:
            self.hypotheses = self.hypotheses[-20:]
            
        return best_sequence
        
    def _score_action_sequence(self, state_embed: np.ndarray, action_embed: np.ndarray,
                               action: Dict, horizon: int) -> float:
        next_pred = self.world_model.predict(state_embed, action_embed)
        immediate_score = 1.0 / (1.0 + np.linalg.norm(next_pred - state_embed))
        
        text = action.get('text', '').lower()
        text_score = 0.0
        
        decisive = ['login', 'apply', 'submit', 'register', 'search', 'profile', 'job']
        for kw in decisive:
            if kw in text:
                text_score += 0.5
                
        if 'close' in text or 'ad' in text:
            text_score -= 1.0
            
        future_options = self._estimate_future_options(state_embed, action_embed)
        horizon_bonus = future_options * 0.1 * horizon
        
        return immediate_score + text_score + horizon_bonus
        
    def _estimate_future_value(self, current_state: np.ndarray, next_state: np.ndarray, 
                               remaining_steps: int) -> float:
        novelty = np.linalg.norm(next_state - current_state)
        return min(1.0, novelty * 0.1 * remaining_steps)
        
    def _estimate_future_options(self, state_embed: np.ndarray, action_embed: np.ndarray) -> float:
        next_state = self.world_model.predict(state_embed, action_embed)
        change_magnitude = np.linalg.norm(next_state - state_embed)
        return min(1.0, change_magnitude * 0.5)
        
    def _score_prediction(self, current: np.ndarray, predicted: np.ndarray, 
                         action_embed: np.ndarray) -> float:
        quality = 1.0 / (1.0 + np.linalg.norm(predicted - current))
        novelty = np.linalg.norm(action_embed) * 0.1
        return quality + novelty
        
    def _action_to_embedding(self, action: Dict) -> np.ndarray:
        text = action.get('text', '')
        embed = np.zeros(self.embedding_dim)
        
        keywords = ['apply', 'submit', 'login', 'search', 'next', 'more', 'register', 'profile', 'job', 'career']
        for i, kw in enumerate(keywords):
            if kw in text.lower():
                embed[i % self.embedding_dim] = 1.0
                
        score = action.get('score', 0.5)
        embed[20:30] = score * np.ones(10)
        
        norm = np.linalg.norm(embed)
        if norm > 0:
            embed = embed / norm
            
        return embed
        
    def update_from_experience(self, actions: List[Dict], reward: float):
        self.action_sequences.append([a.get('text', '') for a in actions])
        self.sequence_rewards.append(reward)
        
    def get_best_hypothesis(self) -> Dict:
        if not self.hypotheses:
            return {}
        return max(self.hypotheses, key=lambda x: x['score'])

# ============================================================================
# 6. MAIN AGENT - FULLY INTEGRATED
# ============================================================================

class AGIMathAgent:
    """Fully integrated AGI agent with geturl.py"""
    
    def __init__(self, port: int = 9260, max_cycles: int = 30):
        self.port = port
        self.max_cycles = max_cycles
        
        self.session_dir = Path(f"agi_math_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        self.session_dir.mkdir(parents=True, exist_ok=True)
        
        # Integrated CDP with geturl.py
        self.cdp = IntegratedCDPWrapper(port=port)
        self.connected = self.cdp.connect()
        
        # Components
        self.embedder = MathematicalEmbedding(embedding_dim=AGI_CONFIG['embedding_dim'])
        self.world_model = JEPAWorldModel(embedding_dim=AGI_CONFIG['embedding_dim'])
        self.population = EvolutionaryPopulation(
            population_size=AGI_CONFIG['population_size'],
            embedding_dim=AGI_CONFIG['embedding_dim']
        )
        self.reasoner = LongChainReasoner(
            world_model=self.world_model,
            embedding_dim=AGI_CONFIG['embedding_dim']
        )
        
        self.current_cycle = 0
        self.reward_history = deque(maxlen=50)
        self.action_history = deque(maxlen=50)
        
        self.best_reward = -float('inf')
        self.total_rewards = 0
        self.decisive_action_count = 0
        
        self._setup_logging()
        
    def _setup_logging(self):
        self.log_dir = self.session_dir / "logs"
        self.log_dir.mkdir(exist_ok=True)
        
    def _log_json(self, log_type: str, data: Dict):
        entry = {
            "timestamp": datetime.now().isoformat(),
            "cycle": self.current_cycle,
            **data
        }
        with open(self.log_dir / f"{log_type}.jsonl", 'a') as f:
            f.write(json.dumps(entry) + '\n')
            
    def perceive(self) -> Dict:
        """Get perception data from geturl.py"""
        return self.cdp.get_perception_data()
        
    def prepare_actions(self, perception_data: Dict) -> List[Dict]:
        """Prepare actions from perception data"""
        actions = []
        seen = set()
        
        decisive_keywords = ['login', 'apply', 'submit', 'register', 'search', 'profile', 'job', 'career']
        interactives = perception_data.get('interactives', [])
        
        for el in interactives:
            text = el.get('text', '').strip()
            if not text or len(text) < 2:
                continue
                
            if text in seen:
                continue
            seen.add(text)
            
            score = 0.0
            
            # Decisive action bonus
            if any(kw in text.lower() for kw in decisive_keywords):
                score += 3.0
                
            # Navigation bonus
            nav = ['next', 'more', 'view', 'see', 'load']
            if any(kw in text.lower() for kw in nav):
                score += 1.0
                
            # Visibility bonus
            if el.get('visible', True):
                score += 0.5
                
            # Form action bonus
            if el.get('form_action'):
                score += 1.0
                
            # Ad penalty
            if 'close' in text.lower() or 'ad' in text.lower():
                score -= 2.0
                
            actions.append({
                'text': text,
                'score': score,
                'selector': el.get('id', ''),
                'tag': el.get('tag', ''),
                'href': el.get('href', ''),
                'is_decisive': any(kw in text.lower() for kw in decisive_keywords),
                'form_action': el.get('form_action'),
                'position': el.get('position', {})
            })
            
        # Also check competitor links
        all_links = perception_data.get('all_links', {})
        competitor_links = all_links.get('competition_links', [])
        for link in competitor_links[:5]:
            text = link.get('text', '').strip()
            if text and text not in seen:
                score = 1.0  # Competitor links are interesting
                actions.append({
                    'text': text,
                    'score': score,
                    'href': link.get('href', ''),
                    'is_decisive': True,
                    'is_competitor': True
                })
                
        actions.sort(key=lambda x: x.get('score', 0), reverse=True)
        return actions[:25]
        
    def calculate_reward(self, perception_before: Dict, perception_after: Dict,
                         success: bool, action_text: str) -> float:
        """Calculate reward using rich perception data"""
        reward = 0.0
        components = {}
        
        if success:
            reward += 0.5
            components['success'] = 0.5
            
        # Page change
        url_before = perception_before.get('url', '')
        url_after = perception_after.get('url', '')
        if url_before and url_after and url_before != url_after:
            reward += 3.0
            components['page_change'] = 3.0
            
        # More interactive elements
        count_before = len(perception_before.get('interactives', []))
        count_after = len(perception_after.get('interactives', []))
        if count_after > count_before * 1.2:
            reward += 1.5
            components['more_interactive'] = 1.5
            
        # Decisive action bonus
        decisive_keywords = ['login', 'apply', 'submit', 'register', 'search', 'profile', 'job']
        if any(kw in action_text.lower() for kw in decisive_keywords):
            reward += 2.5
            components['decisive'] = 2.5
            self.decisive_action_count += 1
            
        # Competitor detection bonus
        if 'competitor' in action_text.lower() or 'alternative' in action_text.lower():
            reward += 2.0
            components['competitor'] = 2.0
            
        # Ad penalty
        if 'close' in action_text.lower() or 'ad' in action_text.lower():
            reward -= 1.0
            components['ad_penalty'] = -1.0
            
        # Stagnation penalty
        if url_before == url_after and not success:
            reward -= 0.5
            components['stagnation'] = -0.5
            
        self._log_json('rewards', {
            'reward': reward,
            'components': components,
            'success': success,
            'action': action_text[:50],
            'decisive': any(kw in action_text.lower() for kw in decisive_keywords)
        })
        
        return reward
        
    def run(self):
        """Main agent loop"""
        print("🧠 AGI MATH SYSTEM - INTEGRATED with geturl.py")
        print("=" * 70)
        print(f"Perception: DOMExplorer (geturl.py)")
        print(f"Execution: ChromePage.click_by_text()")
        print(f"Reasoning Horizon: {AGI_CONFIG['reasoning_horizon']} steps")
        print(f"Embedding Dim: {AGI_CONFIG['embedding_dim']}")
        print("=" * 70)
        
        if not self.connected:
            print("❌ Not connected")
            return
            
        # Initial perception
        perception_data = self.perceive()
        state_embed = self.embedder.encode(perception_data)
        
        print(f"📍 Starting on: {perception_data.get('url', 'unknown')}")
        print(f"📊 Interactive elements: {len(perception_data.get('interactives', []))}")
        print(f"🎯 Competitor links: {perception_data.get('competitor_analysis', {}).get('total_competitor_links', 0)}")
        
        for cycle in range(1, self.max_cycles + 1):
            self.current_cycle = cycle
            
            print(f"\n{'='*70}")
            print(f"🔄 CYCLE {cycle}/{self.max_cycles}")
            print(f"{'='*70}")
            
            # Perceive
            perception_data = self.perceive()
            state_embed = self.embedder.encode(perception_data)
            
            self._log_json('embeddings', {
                'embedding': state_embed.tolist(),
                'url': perception_data.get('url', ''),
                'interactives': len(perception_data.get('interactives', []))
            })
            
            # Prepare actions
            actions = self.prepare_actions(perception_data)
            
            if not actions:
                print("⏳ No actions available, waiting...")
                time.sleep(AGI_CONFIG['action_delay'])
                continue
                
            print(f"\n📋 Top Actions ({len(actions)} available):")
            for i, action in enumerate(actions[:5], 1):
                score = action.get('score', 0)
                decisive = "🎯" if action.get('is_decisive', False) else "  "
                competitor = "⚔️" if action.get('is_competitor', False) else "  "
                print(f"  {i}. {decisive}{competitor} {action['text'][:40]} (score: {score:.2f})")
                
            # Reason
            sequence = self.reasoner.propose_sequence(
                state_embed, 
                actions, 
                horizon=AGI_CONFIG['reasoning_horizon']
            )
            
            if sequence:
                print(f"\n🔗 Proposed Sequence ({len(sequence)} steps):")
                for i, action in enumerate(sequence[:5], 1):
                    decisive = "🎯" if action.get('is_decisive', False) else "  "
                    competitor = "⚔️" if action.get('is_competitor', False) else "  "
                    print(f"  {i}. {decisive}{competitor} {action.get('text', '')[:40]}")
                    
            # Choose action
            agent_idx = cycle % self.population.population_size
            agent = self.population.population[agent_idx]
            
            if sequence and random.random() < 0.7:
                action = sequence[0]
                print(f"\n🎯 Following sequence (step 1 of {len(sequence)})")
            elif random.random() < min(0.3, agent.exploration_rate * 0.8):
                decisive_actions = [a for a in actions if a.get('is_decisive', False)]
                competitor_actions = [a for a in actions if a.get('is_competitor', False)]
                
                if competitor_actions and random.random() < 0.5:
                    action = random.choice(competitor_actions[:3])
                    print(f"\n⚔️ Exploring competitor action")
                elif decisive_actions and random.random() < 0.6:
                    action = random.choice(decisive_actions[:3])
                    print(f"\n🎲 Exploring decisive action")
                else:
                    action = random.choice(actions[:5])
                    print(f"\n🎲 Exploring random action")
            else:
                # Prioritize decisive or competitor actions
                decisive_actions = [a for a in actions if a.get('is_decisive', False)]
                competitor_actions = [a for a in actions if a.get('is_competitor', False)]
                
                if competitor_actions and random.random() < 0.3:
                    action = competitor_actions[0]
                    print(f"\n⚔️ Greedy: competitor action")
                elif decisive_actions:
                    action = decisive_actions[0]
                    print(f"\n🎯 Greedy: decisive action")
                else:
                    action = actions[0]
                    print(f"\n🎯 Greedy: best action")
                
            print(f"   Chosen: {action.get('text', '')[:50]}")
            print(f"   Strategy: {agent.strategy}")
            print(f"   Fitness: {agent.fitness:.2f}")
            
            # Execute
            time.sleep(AGI_CONFIG['action_delay'])
            result = self.cdp.execute_action(action)
            
            print(f"   ⏳ Settling...")
            time.sleep(AGI_CONFIG['perception_delay'])
            
            # Perceive new state
            new_perception = self.perceive()
            new_state_embed = self.embedder.encode(new_perception)
            
            # Calculate reward
            reward = self.calculate_reward(
                perception_data, new_perception,
                result.get('success', False),
                action.get('text', '')
            )
            
            # Evolutionary evaluation
            adjusted_reward = self.population.evaluate(
                agent_idx, reward, result.get('success', False),
                action.get('text', '')
            )
            
            # Learn
            action_embed = self.reasoner._action_to_embedding(action)
            loss = self.world_model.learn(state_embed, action_embed, new_state_embed)
            
            # Log prediction
            prediction = self.world_model.predict(state_embed, action_embed)
            self._log_json('predictions', {
                'actual': new_state_embed.tolist(),
                'predicted': prediction.tolist(),
                'loss': float(loss)
            })
            
            # Evolve
            if cycle % 3 == 0:
                evolution_stats = self.population.evolve()
                self._log_json('evolution', evolution_stats)
                print(f"\n🧬 Evolution Stats:")
                print(f"  Generation: {evolution_stats['generation']}")
                print(f"  Best Fitness: {evolution_stats['best_fitness']:.2f}")
                print(f"  Avg Fitness: {evolution_stats['avg_fitness']:.2f}")
                
            # Update metrics
            self.reasoner.update_from_experience([action], adjusted_reward)
            self.reward_history.append(adjusted_reward)
            self.total_rewards += adjusted_reward
            self.action_history.append(action.get('text', '')[:30])
            
            if adjusted_reward > self.best_reward:
                self.best_reward = adjusted_reward
                print(f"   📈 New best reward: {adjusted_reward:.2f}")
                
            # Check goal
            if self.decisive_action_count >= 3:
                print(f"\n🎉🎉🎉 DECISIVE ACTION GOAL ACHIEVED! 🎉🎉🎉")
                print(f"   Decisive actions taken: {self.decisive_action_count}")
                break
                
            # Log metrics
            metrics = {
                'reward': adjusted_reward,
                'success': result.get('success', False),
                'loss': float(loss),
                'agent_fitness': agent.fitness,
                'best_reward': self.best_reward,
                'total_rewards': self.total_rewards,
                'decisive_actions': self.decisive_action_count,
                'interactives': len(new_perception.get('interactives', []))
            }
            self._log_json('metrics', metrics)
            
            # Show hypothesis
            best_hyp = self.reasoner.get_best_hypothesis()
            if best_hyp:
                print(f"\n🔬 Best Hypothesis:")
                print(f"  Sequence: {' → '.join(best_hyp.get('sequence', [])[:5])}")
                print(f"  Score: {best_hyp.get('score', 0):.2f}")
                print(f"  Horizon: {best_hyp.get('horizon', 0)}")
                
            print(f"\n📊 Results:")
            print(f"  Reward: {adjusted_reward:.2f}")
            print(f"  Success: {'✅' if result.get('success') else '❌'}")
            print(f"  Loss: {loss:.4f}")
            print(f"  Best Reward: {self.best_reward:.2f}")
            print(f"  Decisive Actions: {self.decisive_action_count}")
            
        self._generate_report()
        
    def _generate_report(self):
        print("\n" + "=" * 80)
        print("🧠 AGI MATH SYSTEM - INTEGRATED REPORT")
        print("=" * 80)
        
        print(f"\n📊 STATISTICS:")
        print(f"  Total Cycles: {self.current_cycle}")
        print(f"  Best Reward: {self.best_reward:.2f}")
        print(f"  Total Rewards: {self.total_rewards:.2f}")
        print(f"  Generation: {self.population.generation}")
        print(f"  Best Fitness: {self.population.best_fitness:.2f}")
        print(f"  Decisive Actions: {self.decisive_action_count}")
        
        best_hyp = self.reasoner.get_best_hypothesis()
        if best_hyp:
            print(f"\n🔬 BEST HYPOTHESIS:")
            print(f"  Sequence: {' → '.join(best_hyp.get('sequence', []))}")
            print(f"  Score: {best_hyp.get('score', 0):.2f}")
            print(f"  Horizon: {best_hyp.get('horizon', 0)}")
            
        best_agent = max(self.population.population, key=lambda x: x.fitness)
        print(f"\n🧬 BEST AGENT:")
        print(f"  Strategy: {best_agent.strategy}")
        print(f"  Fitness: {best_agent.fitness:.2f}")
        print(f"  Actions: {best_agent.actions_taken}")
        print(f"  Unique Actions: {len(best_agent.unique_actions)}")
        print(f"  Exploration Rate: {best_agent.exploration_rate:.2f}")
        
        if self.action_history:
            action_counts = Counter(list(self.action_history))
            print(f"\n📋 ACTION DISTRIBUTION:")
            for action, count in action_counts.most_common(10):
                print(f"  {action}: {count} times")
                
        print(f"\n📁 LOG FILES:")
        for log_file in self.log_dir.glob("*.jsonl"):
            size = log_file.stat().st_size
            print(f"  {log_file.name}: {size} bytes")
            
        print("\n" + "=" * 80)

# ============================================================================
# MAIN
# ============================================================================

def main():
    print("🧠 AGI MATH SYSTEM - INTEGRATED")
    print("=" * 70)
    print("Perception: geturl.py DOMExplorer")
    print("Execution: ChromePage methods")
    print("Reasoning: 8-step JEPA with repetition penalty")
    print("Competitor Detection: Built-in")
    print("=" * 70)
    
    port = AGI_CONFIG['port']
    max_cycles = AGI_CONFIG['max_cycles']
    
    agent = AGIMathAgent(port=port, max_cycles=max_cycles)
    
    if not agent.connected:
        print("❌ Failed to connect")
        print(f"   Make sure Chrome is running on port {port}")
        return
        
    try:
        agent.run()
    except KeyboardInterrupt:
        print("\n👋 Stopped by user")
        agent._generate_report()
        
if __name__ == "__main__":
    main()
