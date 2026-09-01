#!/usr/bin/env python3
"""
AGI MATH REASONING SYSTEM - DECISIVE ACTION MODE v2
Fixed: Method signature, recursive JEPA prediction, 8-step horizon
Optimized for Termux/Android memory constraints
"""

import json
import sys
import os
import time
import hashlib
import gc
import re
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple, Set
from collections import defaultdict, deque, Counter
import random
import math
import traceback
import numpy as np
from dataclasses import dataclass, field, asdict

# ============================================================================
# AGI MATH CONFIGURATION
# ============================================================================

AGI_CONFIG = {
    "action_delay": 12.0,
    "perception_delay": 15.0,
    "learning_delay": 8.0,
    "evolution_delay": 30.0,
    "max_cycles": 30,
    "embedding_dim": 128,
    "population_size": 5,
    "mutation_rate": 0.08,
    "learning_rate": 0.001,
    "gamma": 0.95,
    "port": 9260,
    "action_space": 30,
    "reasoning_horizon": 8,  # Now properly used
    "repeat_action_penalty": -2.0,
    "novelty_bonus": 1.5,
    "goal_threshold": 5.0,
    "max_memory_mb": 512  # Termux memory limit
}

# ============================================================================
# 1. MATHEMATICAL EMBEDDING SYSTEM
# ============================================================================

class MathematicalEmbedding:
    """JEPA-style encoder - all outputs are embedding_dim (128)"""
    
    def __init__(self, embedding_dim: int = 128):
        self.embedding_dim = embedding_dim
        
        self.W_dom = np.random.randn(256, embedding_dim) * np.sqrt(2.0 / 256)
        self.W_text = np.random.randn(128, embedding_dim) * np.sqrt(2.0 / 128)
        self.W_interactive = np.random.randn(64, embedding_dim) * np.sqrt(2.0 / 64)
        
        self.b_dom = np.zeros(embedding_dim)
        self.b_text = np.zeros(embedding_dim)
        self.b_interactive = np.zeros(embedding_dim)
        
    def encode(self, raw_data: Dict) -> np.ndarray:
        try:
            dom_vector = self._extract_dom_features(raw_data)
            text_vector = self._extract_text_features(raw_data)
            interactive_vector = self._extract_interactive_features(raw_data)
            
            dom_embed = np.dot(dom_vector, self.W_dom) + self.b_dom
            text_embed = np.dot(text_vector, self.W_text) + self.b_text
            inter_embed = np.dot(interactive_vector, self.W_interactive) + self.b_interactive
            
            combined = dom_embed + text_embed + inter_embed
            
            norm = np.linalg.norm(combined)
            if norm > 0:
                combined = combined / norm
                
            return combined
        except:
            return np.random.randn(self.embedding_dim) * 0.01
            
    def _extract_dom_features(self, data: Dict) -> np.ndarray:
        metrics = data.get('metrics', {})
        features = []
        features.append(metrics.get('total_elements', 0) / 10000)
        features.append(metrics.get('forms', 0) / 20)
        features.append(metrics.get('links', 0) / 200)
        features.append(1.0 if metrics.get('interactive_count', 0) > 50 else 0.0)
        
        while len(features) < 256:
            features.append(0.0)
        return np.array(features[:256], dtype=np.float32)
        
    def _extract_text_features(self, data: Dict) -> np.ndarray:
        title = data.get('title', '')
        url = data.get('url', '')
        features = []
        words = ['apply', 'submit', 'register', 'login', 'search', 'next', 'more', 'profile', 'job', 'career']
        text = (title + ' ' + url).lower()
        for word in words:
            features.append(1.0 if word in text else 0.0)
        features.append(len(title) / 100)
        
        while len(features) < 128:
            features.append(0.0)
        return np.array(features[:128], dtype=np.float32)
        
    def _extract_interactive_features(self, data: Dict) -> np.ndarray:
        interactives = data.get('interactives', [])
        features = []
        tags = {'button': 0, 'a': 0, 'input': 0, 'select': 0}
        visible_count = 0
        
        for el in interactives[:50]:
            tag = el.get('tag', '')
            if tag in tags:
                tags[tag] += 1
            if el.get('visible', False):
                visible_count += 1
                
        total = max(1, len(interactives))
        features.extend([
            tags['button'] / max(1, total),
            tags['a'] / max(1, total),
            tags['input'] / max(1, total),
            tags['select'] / max(1, total),
            visible_count / max(1, total)
        ])
        
        avg_depth = sum(el.get('depth', 0) for el in interactives) / max(1, total)
        features.append(avg_depth / 20)
        
        while len(features) < 64:
            features.append(0.0)
        return np.array(features[:64], dtype=np.float32)

# ============================================================================
# 2. JEPA WORLD MODEL - RECURSIVE PREDICTION
# ============================================================================

class JEPAWorldModel:
    """Joint Embedding Predictive Architecture - Recursive for multi-step"""
    
    def __init__(self, embedding_dim: int = 128):
        self.embedding_dim = embedding_dim
        
        self.W_state = np.random.randn(embedding_dim, embedding_dim) * np.sqrt(2.0 / embedding_dim)
        self.W_action = np.random.randn(embedding_dim, embedding_dim) * np.sqrt(2.0 / embedding_dim)
        self.b_predict = np.zeros(embedding_dim)
        
        # Adam optimizer
        self.m_W_state = np.zeros_like(self.W_state)
        self.v_W_state = np.zeros_like(self.W_state)
        self.m_W_action = np.zeros_like(self.W_action)
        self.v_W_action = np.zeros_like(self.W_action)
        
        self.t = 0
        self.learning_rate = AGI_CONFIG['learning_rate']
        self.beta1 = 0.9
        self.beta2 = 0.999
        self.epsilon = 1e-8
        
        self.prediction_errors = deque(maxlen=100)
        
    def predict(self, state_embed: np.ndarray, action_embed: np.ndarray) -> np.ndarray:
        """Single-step prediction"""
        if len(state_embed.shape) == 1:
            state_embed = state_embed.reshape(1, -1)
        if len(action_embed.shape) == 1:
            action_embed = action_embed.reshape(1, -1)
            
        state_part = np.dot(state_embed, self.W_state)
        action_part = np.dot(action_embed, self.W_action)
        prediction = np.tanh(state_part + action_part + self.b_predict)
        
        return prediction.flatten()
        
    def predict_sequence(self, state_embed: np.ndarray, action_embeds: List[np.ndarray]) -> List[np.ndarray]:
        """Recursive multi-step prediction"""
        predictions = []
        current_state = state_embed.copy()
        
        for action_embed in action_embeds:
            next_state = self.predict(current_state, action_embed)
            predictions.append(next_state)
            current_state = next_state
            
        return predictions
        
    def learn(self, state_embed: np.ndarray, action_embed: np.ndarray,
              next_state_embed: np.ndarray) -> float:
        """Learn from single step"""
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
        self.prediction_errors.append(np.mean(error**2))
        
        # Gradient descent with memory optimization
        grad_state = np.dot(error.T, state_embed).T * (1 - prediction**2)
        grad_action = np.dot(error.T, action_embed).T * (1 - prediction**2)
        grad_b = np.mean(error * (1 - prediction**2), axis=0)
        
        # Adam update
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
# 3. EVOLUTIONARY STRATEGY
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
# 4. LONG-CHAIN REASONER - FIXED WITH HORIZON
# ============================================================================

class LongChainReasoner:
    """Mathematical long-chain reasoning with proper horizon"""
    
    def __init__(self, world_model: JEPAWorldModel, embedding_dim: int = 128):
        self.world_model = world_model
        self.embedding_dim = embedding_dim
        self.horizon = AGI_CONFIG['reasoning_horizon']
        
        self.action_sequences = deque(maxlen=50)
        self.sequence_rewards = deque(maxlen=50)
        self.hypotheses = []
        
    def propose_sequence(self, state_embed: np.ndarray, actions: List[Dict], 
                        horizon: int = None) -> List[Dict]:
        """
        Propose action sequences with proper horizon handling
        Uses recursive JEPA prediction for multi-step lookahead
        """
        if horizon is None:
            horizon = self.horizon
            
        if len(actions) < 2:
            return actions[:1]
            
        # Score actions with multi-step lookahead
        scored_actions = []
        for action in actions[:15]:
            action_embed = self._action_to_embedding(action)
            score = self._score_action_sequence(state_embed, action_embed, action, horizon)
            scored_actions.append((score, action, action_embed))
            
        scored_actions.sort(key=lambda x: x[0], reverse=True)
        
        # Build best sequence
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
                    
                    # Multi-step value estimation
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
                
        # Store hypothesis
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
        """Score action considering entire sequence"""
        # Immediate prediction
        next_pred = self.world_model.predict(state_embed, action_embed)
        immediate_score = 1.0 / (1.0 + np.linalg.norm(next_pred - state_embed))
        
        # Action text value
        text = action.get('text', '').lower()
        text_score = 0.0
        
        # Decisive action bonuses
        decisive = ['login', 'apply', 'submit', 'register', 'search', 'profile', 'job']
        for kw in decisive:
            if kw in text:
                text_score += 0.5
                
        # Penalty for low-value actions
        if 'close' in text or 'ad' in text:
            text_score -= 1.0
            
        # Horizon bonus: actions that lead to more options get higher score
        future_options = self._estimate_future_options(state_embed, action_embed)
        horizon_bonus = future_options * 0.1 * horizon
        
        return immediate_score + text_score + horizon_bonus
        
    def _estimate_future_value(self, current_state: np.ndarray, next_state: np.ndarray, 
                               remaining_steps: int) -> float:
        """Estimate future value with remaining steps"""
        novelty = np.linalg.norm(next_state - current_state)
        return min(1.0, novelty * 0.1 * remaining_steps)
        
    def _estimate_future_options(self, state_embed: np.ndarray, action_embed: np.ndarray) -> float:
        """Estimate how many options this action opens up"""
        # Simpler: use the magnitude of change as a proxy for new options
        next_state = self.world_model.predict(state_embed, action_embed)
        change_magnitude = np.linalg.norm(next_state - state_embed)
        return min(1.0, change_magnitude * 0.5)
        
    def _score_prediction(self, current: np.ndarray, predicted: np.ndarray, 
                         action_embed: np.ndarray) -> float:
        """Score a single prediction"""
        quality = 1.0 / (1.0 + np.linalg.norm(predicted - current))
        novelty = np.linalg.norm(action_embed) * 0.1
        return quality + novelty
        
    def _action_to_embedding(self, action: Dict) -> np.ndarray:
        """Convert action to embedding_dim vector"""
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
# 5. CDP WRAPPER
# ============================================================================

class CDPWrapper:
    def __init__(self, port: int = 9260):
        self.port = port
        self.client = None
        self.connected = False
        
    def connect(self):
        try:
            from dynamic_cdp_6 import EnhancedChromeCDP
            self.client = EnhancedChromeCDP(port=self.port)
            tabs = self.client.get_tabs()
            if tabs:
                self.connected = True
                return True
        except Exception as e:
            print(f"⚠️ Connect error: {e}")
        return False
        
    def evaluate_script(self, script: str, tab_index: int = 0):
        if not self.client:
            return None
        try:
            return self.client.evaluate_script(script, tab_index)
        except Exception as e:
            return None

# ============================================================================
# 6. MAIN AGENT
# ============================================================================

class AGIMathAgent:
    def __init__(self, port: int = 9260, max_cycles: int = 30):
        self.port = port
        self.max_cycles = max_cycles
        
        self.session_dir = Path(f"agi_math_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        self.session_dir.mkdir(parents=True, exist_ok=True)
        
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
        
        self.cdp = CDPWrapper(port=port)
        self.connected = self.cdp.connect()
        
        self.current_cycle = 0
        self.state_history = deque(maxlen=50)
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
        script = """
        (function() {
            const interactives = [];
            document.querySelectorAll('button, a[href], [role="button"], input, select').forEach(el => {
                const rect = el.getBoundingClientRect();
                interactives.push({
                    text: (el.textContent || '').trim().slice(0, 100),
                    tag: el.tagName.toLowerCase(),
                    href: el.getAttribute('href'),
                    id: el.id,
                    classes: el.className,
                    depth: (() => { let d=0, n=el; while(n.parentElement){d++; n=n.parentElement;} return d; })(),
                    visible: rect.width > 0 && rect.height > 0
                });
            });
            
            const metrics = {
                total_elements: document.querySelectorAll('*').length,
                interactive_count: interactives.length,
                forms: document.querySelectorAll('form').length,
                links: document.querySelectorAll('a[href]').length
            };
            
            return {
                url: window.location.href,
                title: document.title,
                interactives: interactives.slice(0, 50),
                metrics: metrics,
                timestamp: Date.now()
            };
        })()
        """
        
        try:
            result = self.cdp.evaluate_script(script)
            return result or {'url': '', 'interactives': [], 'metrics': {}}
        except:
            return {'url': '', 'interactives': [], 'metrics': {}}
            
    def execute_action(self, action: Dict) -> Dict:
        text = action.get('text', '')
        
        iife = f"""
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
        
        try:
            result = self.cdp.evaluate_script(iife)
            success = bool(result and result.get('success', False))
            
            self._log_json('actions', {
                'action': action,
                'success': success,
                'result': result
            })
            
            return {'success': success}
        except Exception as e:
            return {'success': False, 'error': str(e)}
            
    def calculate_reward(self, old_state: Dict, new_state: Dict, 
                         success: bool, action_text: str) -> float:
        reward = 0.0
        components = {}
        
        if success:
            reward += 0.5
            components['success'] = 0.5
            
        old_url = old_state.get('url', '')
        new_url = new_state.get('url', '')
        if old_url and new_url and old_url != new_url:
            reward += 3.0
            components['page_change'] = 3.0
            
        old_count = len(old_state.get('interactives', []))
        new_count = len(new_state.get('interactives', []))
        if new_count > old_count * 1.2:
            reward += 1.5
            components['more_interactive'] = 1.5
            
        decisive_keywords = ['login', 'apply', 'submit', 'register', 'search', 'profile', 'job']
        if any(kw in action_text.lower() for kw in decisive_keywords):
            reward += 2.5
            components['decisive'] = 2.5
            self.decisive_action_count += 1
            
        if 'close' in action_text.lower() or 'ad' in action_text.lower():
            reward -= 1.0
            components['ad_penalty'] = -1.0
            
        if old_url == new_url and not success:
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
        
    def _prepare_actions(self, state: Dict) -> List[Dict]:
        actions = []
        seen = set()
        
        decisive_keywords = ['login', 'apply', 'submit', 'register', 'search', 'profile', 'job', 'career']
        
        for el in state.get('interactives', []):
            text = el.get('text', '').strip()
            if not text or len(text) < 2:
                continue
                
            if text in seen:
                continue
            seen.add(text)
            
            score = 0.0
            
            if any(kw in text.lower() for kw in decisive_keywords):
                score += 3.0
                
            nav = ['next', 'more', 'view', 'see', 'load']
            if any(kw in text.lower() for kw in nav):
                score += 1.0
                
            if el.get('visible', False):
                score += 0.5
                
            depth = el.get('depth', 100)
            score -= max(0, depth - 5) * 0.05
            
            if 'close' in text.lower() or 'ad' in text.lower():
                score -= 2.0
                
            actions.append({
                'text': text,
                'score': score,
                'selector': el.get('id', ''),
                'tag': el.get('tag', ''),
                'depth': el.get('depth', 0),
                'is_decisive': any(kw in text.lower() for kw in decisive_keywords)
            })
            
        actions.sort(key=lambda x: x.get('score', 0), reverse=True)
        return actions[:25]
        
    def run(self):
        print("🧠 AGI MATH SYSTEM - DECISIVE ACTION MODE")
        print("=" * 70)
        print(f"Embedding Dim: {AGI_CONFIG['embedding_dim']}")
        print(f"Reasoning Horizon: {AGI_CONFIG['reasoning_horizon']} steps")
        print(f"Repeat Penalty: {AGI_CONFIG['repeat_action_penalty']}")
        print("=" * 70)
        
        state = self.perceive()
        state_embed = self.embedder.encode(state)
        
        print(f"📍 Starting on: {state.get('url', 'unknown')}")
        print(f"📊 Interactive elements: {len(state.get('interactives', []))}")
        
        for cycle in range(1, self.max_cycles + 1):
            self.current_cycle = cycle
            
            print(f"\n{'='*70}")
            print(f"🔄 CYCLE {cycle}/{self.max_cycles}")
            print(f"{'='*70}")
            
            state = self.perceive()
            state_embed = self.embedder.encode(state)
            
            self._log_json('embeddings', {
                'embedding': state_embed.tolist(),
                'url': state.get('url', '')
            })
            
            actions = self._prepare_actions(state)
            
            if not actions:
                print("⏳ No actions available, waiting...")
                time.sleep(AGI_CONFIG['action_delay'])
                continue
                
            print(f"\n📋 Top Actions ({len(actions)} available):")
            for i, action in enumerate(actions[:5], 1):
                score = action.get('score', 0)
                decisive = "🎯" if action.get('is_decisive', False) else "  "
                print(f"  {i}. {decisive} {action['text'][:40]} (score: {score:.2f})")
                
            # Use the horizon parameter properly
            sequence = self.reasoner.propose_sequence(
                state_embed, 
                actions, 
                horizon=AGI_CONFIG['reasoning_horizon']  # Now properly passed
            )
            
            if sequence:
                print(f"\n🔗 Proposed Sequence ({len(sequence)} steps):")
                for i, action in enumerate(sequence[:5], 1):
                    decisive = "🎯" if action.get('is_decisive', False) else "  "
                    print(f"  {i}. {decisive} {action.get('text', '')[:40]}")
                    
            agent_idx = cycle % self.population.population_size
            agent = self.population.population[agent_idx]
            
            # Follow sequence if available
            if sequence and random.random() < 0.7:
                action = sequence[0]
                print(f"\n🎯 Following sequence (step 1 of {len(sequence)})")
            elif random.random() < min(0.3, agent.exploration_rate * 0.8):
                decisive_actions = [a for a in actions if a.get('is_decisive', False)]
                if decisive_actions and random.random() < 0.6:
                    action = random.choice(decisive_actions[:3])
                    print(f"\n🎲 Exploring decisive action")
                else:
                    action = random.choice(actions[:5])
                    print(f"\n🎲 Exploring random action")
            else:
                action = actions[0]
                print(f"\n🎯 Greedy: best action")
                
            print(f"   Chosen: {action.get('text', '')[:50]}")
            print(f"   Strategy: {agent.strategy}")
            print(f"   Fitness: {agent.fitness:.2f}")
            
            time.sleep(AGI_CONFIG['action_delay'])
            result = self.execute_action(action)
            
            print(f"   ⏳ Settling...")
            time.sleep(AGI_CONFIG['perception_delay'])
            
            new_state = self.perceive()
            new_state_embed = self.embedder.encode(new_state)
            
            reward = self.calculate_reward(
                state, new_state, 
                result.get('success', False),
                action.get('text', '')
            )
            
            adjusted_reward = self.population.evaluate(
                agent_idx, reward, result.get('success', False),
                action.get('text', '')
            )
            
            action_embed = self.reasoner._action_to_embedding(action)
            loss = self.world_model.learn(state_embed, action_embed, new_state_embed)
            
            prediction = self.world_model.predict(state_embed, action_embed)
            self._log_json('predictions', {
                'actual': new_state_embed.tolist(),
                'predicted': prediction.tolist(),
                'loss': float(loss)
            })
            
            if cycle % 3 == 0:
                evolution_stats = self.population.evolve()
                self._log_json('evolution', evolution_stats)
                print(f"\n🧬 Evolution Stats:")
                print(f"  Generation: {evolution_stats['generation']}")
                print(f"  Best Fitness: {evolution_stats['best_fitness']:.2f}")
                print(f"  Avg Fitness: {evolution_stats['avg_fitness']:.2f}")
                
            self.reasoner.update_from_experience([action], adjusted_reward)
            
            self.reward_history.append(adjusted_reward)
            self.total_rewards += adjusted_reward
            self.action_history.append(action.get('text', '')[:30])
            
            if adjusted_reward > self.best_reward:
                self.best_reward = adjusted_reward
                print(f"   📈 New best reward: {adjusted_reward:.2f}")
                
            if self.decisive_action_count >= 3:
                print(f"\n🎉🎉🎉 DECISIVE ACTION GOAL ACHIEVED! 🎉🎉🎉")
                print(f"   Decisive actions taken: {self.decisive_action_count}")
                break
                
            metrics = {
                'reward': adjusted_reward,
                'success': result.get('success', False),
                'loss': float(loss),
                'agent_fitness': agent.fitness,
                'best_reward': self.best_reward,
                'total_rewards': self.total_rewards,
                'decisive_actions': self.decisive_action_count
            }
            self._log_json('metrics', metrics)
            
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
            
            state = new_state
            state_embed = new_state_embed
            
        self._generate_report()
        
    def _generate_report(self):
        print("\n" + "=" * 80)
        print("🧠 AGI MATH SYSTEM - DECISIVE ACTION REPORT")
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
    print("🧠 AGI MATH REASONING SYSTEM - DECISIVE ACTION MODE v2")
    print("=" * 70)
    print(f"Reasoning Horizon: {AGI_CONFIG['reasoning_horizon']} steps")
    print("Recursive JEPA prediction for multi-step lookahead")
    print("Repetition penalty to prevent local optima")
    print("=" * 70)
    
    port = AGI_CONFIG['port']
    max_cycles = AGI_CONFIG['max_cycles']
    
    agent = AGIMathAgent(port=port, max_cycles=max_cycles)
    
    if not agent.connected:
        print("❌ Failed to connect to Chrome")
        print(f"   Make sure Chrome is running on port {port}")
        return
        
    try:
        agent.run()
    except KeyboardInterrupt:
        print("\n👋 Stopped by user")
        agent._generate_report()
        
if __name__ == "__main__":
    main()
