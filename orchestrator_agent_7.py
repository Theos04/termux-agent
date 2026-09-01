#!/usr/bin/env python3
"""
AGI MATH REASONING SYSTEM - FIXED DIMENSIONS
All vectors now consistently use embedding_dim (128)
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
    "embedding_dim": 128,  # All vectors use this dimension
    "population_size": 5,
    "mutation_rate": 0.15,
    "learning_rate": 0.001,
    "gamma": 0.95,
    "port": 9260,
    "action_space": 30  # Max actions to consider
}

# ============================================================================
# 1. MATHEMATICAL EMBEDDING SYSTEM (JEPA Encoder)
# ============================================================================

class MathematicalEmbedding:
    """
    JEPA-style encoder that transforms DOM into mathematical embeddings
    All outputs are embedding_dim (128)
    """
    
    def __init__(self, embedding_dim: int = 128):
        self.embedding_dim = embedding_dim
        
        # Learnable projection matrices - all output to embedding_dim
        self.W_dom = np.random.randn(256, embedding_dim) * np.sqrt(2.0 / 256)
        self.W_text = np.random.randn(128, embedding_dim) * np.sqrt(2.0 / 128)
        self.W_interactive = np.random.randn(64, embedding_dim) * np.sqrt(2.0 / 64)
        
        # Bias terms
        self.b_dom = np.zeros(embedding_dim)
        self.b_text = np.zeros(embedding_dim)
        self.b_interactive = np.zeros(embedding_dim)
        
        # Normalization constants
        self.norm_constants = {
            'max_elements': 10000,
            'max_text': 50000,
            'max_interactive': 200
        }
        
    def encode(self, raw_data: Dict) -> np.ndarray:
        """Encode raw DOM data into embedding_dim vector"""
        try:
            # Extract features as vectors
            dom_vector = self._extract_dom_features(raw_data)
            text_vector = self._extract_text_features(raw_data)
            interactive_vector = self._extract_interactive_features(raw_data)
            
            # Matrix multiplication (linear algebra)
            dom_embed = np.dot(dom_vector, self.W_dom) + self.b_dom
            text_embed = np.dot(text_vector, self.W_text) + self.b_text
            inter_embed = np.dot(interactive_vector, self.W_interactive) + self.b_interactive
            
            # Combine embeddings
            combined = dom_embed + text_embed + inter_embed
            
            # Normalize (L2 norm)
            norm = np.linalg.norm(combined)
            if norm > 0:
                combined = combined / norm
                
            return combined
            
        except Exception as e:
            print(f"⚠️ Embedding error: {e}")
            return np.random.randn(self.embedding_dim) * 0.01
            
    def _extract_dom_features(self, data: Dict) -> np.ndarray:
        """Extract DOM structure features as vector (256 dims)"""
        metrics = data.get('metrics', {})
        features = []
        
        # Normalize metrics
        features.append(metrics.get('total_elements', 0) / self.norm_constants['max_elements'])
        features.append(metrics.get('forms', 0) / 20)
        features.append(metrics.get('links', 0) / 200)
        features.append(1.0 if metrics.get('interactive_count', 0) > 50 else 0.0)
        
        # Framework detection (one-hot)
        frameworks = data.get('frameworks', {})
        for fw in ['react', 'angular', 'vue', 'jquery']:
            features.append(1.0 if frameworks.get(fw, False) else 0.0)
            
        # Pad to 256
        while len(features) < 256:
            features.append(0.0)
            
        return np.array(features[:256], dtype=np.float32)
        
    def _extract_text_features(self, data: Dict) -> np.ndarray:
        """Extract text features as vector (128 dims)"""
        title = data.get('title', '')
        url = data.get('url', '')
        
        features = []
        
        # Simple text encoding (word presence)
        words = ['apply', 'submit', 'register', 'login', 'search', 
                'next', 'more', 'profile', 'job', 'career']
        
        text = (title + ' ' + url).lower()
        for word in words:
            features.append(1.0 if word in text else 0.0)
            
        # Text length
        features.append(len(title) / 100)
        
        # Pad to 128
        while len(features) < 128:
            features.append(0.0)
            
        return np.array(features[:128], dtype=np.float32)
        
    def _extract_interactive_features(self, data: Dict) -> np.ndarray:
        """Extract interactive elements features (64 dims)"""
        interactives = data.get('interactives', [])
        
        features = []
        
        # Count by tag
        tags = {'button': 0, 'a': 0, 'input': 0, 'select': 0}
        visible_count = 0
        
        for el in interactives[:50]:
            tag = el.get('tag', '')
            if tag in tags:
                tags[tag] += 1
            if el.get('visible', False):
                visible_count += 1
                
        # Normalize
        total = max(1, len(interactives))
        features.extend([
            tags['button'] / max(1, total),
            tags['a'] / max(1, total),
            tags['input'] / max(1, total),
            tags['select'] / max(1, total),
            visible_count / max(1, total)
        ])
        
        # Average depth
        avg_depth = sum(el.get('depth', 0) for el in interactives) / max(1, total)
        features.append(avg_depth / 20)
        
        # Pad to 64
        while len(features) < 64:
            features.append(0.0)
            
        return np.array(features[:64], dtype=np.float32)

# ============================================================================
# 2. JEPA WORLD MODEL - FIXED DIMENSIONS
# ============================================================================

class JEPAWorldModel:
    """
    Joint Embedding Predictive Architecture
    All operations use consistent embedding_dim (128)
    """
    
    def __init__(self, embedding_dim: int = 128):
        self.embedding_dim = embedding_dim
        
        # All weight matrices output to embedding_dim
        self.W_state = np.random.randn(embedding_dim, embedding_dim) * np.sqrt(2.0 / embedding_dim)
        self.W_action = np.random.randn(embedding_dim, embedding_dim) * np.sqrt(2.0 / embedding_dim)
        self.b_predict = np.zeros(embedding_dim)
        
        # Adam optimizer parameters
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
        """
        Predict next state using JEPA:
        s_pred = tanh(W_state * s_t + W_action * a_t + b)
        All vectors are embedding_dim (128)
        """
        # Ensure correct shapes
        if len(state_embed.shape) == 1:
            state_embed = state_embed.reshape(1, -1)
        if len(action_embed.shape) == 1:
            action_embed = action_embed.reshape(1, -1)
            
        # Matrix multiplication (linear algebra)
        state_part = np.dot(state_embed, self.W_state)
        action_part = np.dot(action_embed, self.W_action)
        
        # Combine with tanh nonlinearity
        prediction = np.tanh(state_part + action_part + self.b_predict)
        
        return prediction.flatten()
        
    def learn(self, state_embed: np.ndarray, action_embed: np.ndarray,
              next_state_embed: np.ndarray) -> float:
        """
        Learn using gradient descent
        Loss = ||s_pred - s_actual||^2
        """
        self.t += 1
        
        # Ensure correct shapes
        if len(state_embed.shape) == 1:
            state_embed = state_embed.reshape(1, -1)
        if len(action_embed.shape) == 1:
            action_embed = action_embed.reshape(1, -1)
        if len(next_state_embed.shape) == 1:
            next_state_embed = next_state_embed.reshape(1, -1)
        
        # Forward pass
        state_part = np.dot(state_embed, self.W_state)
        action_part = np.dot(action_embed, self.W_action)
        prediction = np.tanh(state_part + action_part + self.b_predict)
        
        # Calculate gradient (error)
        error = prediction - next_state_embed
        
        # Gradient descent (backpropagation)
        grad_state = np.dot(error.T, state_embed).T * (1 - prediction**2)
        grad_action = np.dot(error.T, action_embed).T * (1 - prediction**2)
        grad_b = np.mean(error * (1 - prediction**2), axis=0)
        
        # Adam update for W_state
        self.m_W_state = self.beta1 * self.m_W_state + (1 - self.beta1) * grad_state
        self.v_W_state = self.beta2 * self.v_W_state + (1 - self.beta2) * (grad_state**2)
        m_hat = self.m_W_state / (1 - self.beta1**self.t)
        v_hat = self.v_W_state / (1 - self.beta2**self.t)
        self.W_state -= self.learning_rate * m_hat / (np.sqrt(v_hat) + self.epsilon)
        
        # Adam update for W_action
        self.m_W_action = self.beta1 * self.m_W_action + (1 - self.beta1) * grad_action
        self.v_W_action = self.beta2 * self.v_W_action + (1 - self.beta2) * (grad_action**2)
        m_hat = self.m_W_action / (1 - self.beta1**self.t)
        v_hat = self.v_W_action / (1 - self.beta2**self.t)
        self.W_action -= self.learning_rate * m_hat / (np.sqrt(v_hat) + self.epsilon)
        
        # Update bias
        self.b_predict -= self.learning_rate * grad_b
        
        loss = np.mean(error**2)
        return float(loss)

# ============================================================================
# 3. EVOLUTIONARY STRATEGY
# ============================================================================

@dataclass
class EvolutionaryAgent:
    """Agent with evolved parameters"""
    weights: Dict[str, np.ndarray] = field(default_factory=dict)
    fitness: float = 0.0
    actions_taken: int = 0
    total_reward: float = 0.0
    exploration_rate: float = 0.3
    age: int = 0
    strategy: str = "balanced"
    
class EvolutionaryPopulation:
    """Evolutionary strategy with fitness-based selection"""
    
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
                exploration_rate=random.uniform(0.1, 0.6),
                strategy=strategies[i % len(strategies)]
            )
            self.population.append(agent)
            
    def evaluate(self, agent_idx: int, reward: float, success: bool):
        agent = self.population[agent_idx]
        agent.total_reward += reward
        agent.actions_taken += 1
        agent.fitness = agent.total_reward / max(1, agent.actions_taken)
        agent.age += 1
        
        if agent.fitness > self.best_fitness:
            self.best_fitness = agent.fitness
            self.best_agent = agent
            
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
                child_weights[key] = np.where(
                    mask,
                    parent1.weights[key],
                    parent2.weights[key]
                )
                
            if random.random() < AGI_CONFIG['mutation_rate']:
                for key in child_weights.keys():
                    noise = np.random.randn(*child_weights[key].shape) * 0.05
                    child_weights[key] += noise
                    
            child = EvolutionaryAgent(
                weights=child_weights,
                exploration_rate=random.uniform(0.1, 0.6),
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
        
    def get_best_weights(self) -> Dict[str, np.ndarray]:
        if self.best_agent:
            return self.best_agent.weights
        return self.population[0].weights

# ============================================================================
# 4. LONG-CHAIN REASONING ENGINE
# ============================================================================

class LongChainReasoner:
    """Mathematical long-chain reasoning using gradient ascent"""
    
    def __init__(self, world_model: JEPAWorldModel, embedding_dim: int = 128):
        self.world_model = world_model
        self.embedding_dim = embedding_dim
        
        self.action_sequences = deque(maxlen=50)
        self.sequence_rewards = deque(maxlen=50)
        self.hypotheses = []
        
    def propose_sequence(self, state_embed: np.ndarray, actions: List[Dict], 
                         horizon: int = 3) -> List[Dict]:
        """Propose action sequences using mathematical optimization"""
        if len(actions) < 2:
            return actions[:1]
            
        action_embeddings = []
        for action in actions[:10]:
            embed = self._action_to_embedding(action)
            action_embeddings.append(embed)
            
        if not action_embeddings:
            return actions[:1]
            
        best_sequence = []
        best_score = -float('inf')
        
        for start_idx in range(min(3, len(action_embeddings))):
            sequence = [actions[start_idx]]
            current_state = state_embed.copy()
            total_score = 0
            
            for _ in range(horizon):
                best_action = None
                best_action_score = -float('inf')
                
                for action, embed in zip(actions, action_embeddings):
                    next_pred = self.world_model.predict(current_state, embed)
                    score = self._score_prediction(current_state, next_pred, embed)
                    
                    if score > best_action_score:
                        best_action_score = score
                        best_action = action
                        best_embed = embed
                        
                if best_action:
                    sequence.append(best_action)
                    current_state = self.world_model.predict(current_state, best_embed)
                    total_score += best_action_score
                    
            if total_score > best_score:
                best_score = total_score
                best_sequence = sequence
                
        self.hypotheses.append({
            'sequence': [a.get('text', '')[:30] for a in best_sequence],
            'score': best_score,
            'timestamp': datetime.now().isoformat()
        })
        
        if len(self.hypotheses) > 20:
            self.hypotheses = self.hypotheses[-20:]
            
        return best_sequence
        
    def _action_to_embedding(self, action: Dict) -> np.ndarray:
        """Convert action to embedding_dim vector"""
        text = action.get('text', '')
        embed = np.zeros(self.embedding_dim)
        
        # Keyword encoding
        keywords = ['apply', 'submit', 'login', 'search', 'next', 'more']
        for i, kw in enumerate(keywords):
            if kw in text.lower():
                embed[i % self.embedding_dim] = 1.0
                
        # Score encoding
        score = action.get('score', 0.5)
        embed[10:20] = score * np.ones(10)
        
        norm = np.linalg.norm(embed)
        if norm > 0:
            embed = embed / norm
            
        return embed
        
    def _score_prediction(self, current: np.ndarray, predicted: np.ndarray, 
                         action_embed: np.ndarray) -> float:
        """Score a prediction"""
        quality = 1.0 / (1.0 + np.linalg.norm(predicted - current))
        novelty = np.linalg.norm(action_embed)
        return quality + 0.3 * novelty
        
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
    """Full AGI-inspired system with mathematical reasoning"""
    
    def __init__(self, port: int = 9260, max_cycles: int = 30):
        self.port = port
        self.max_cycles = max_cycles
        
        self.session_dir = Path(f"agi_math_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        self.session_dir.mkdir(parents=True, exist_ok=True)
        
        # All components use embedding_dim=128 consistently
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
        self.embedding_history = deque(maxlen=50)
        self.reward_history = deque(maxlen=50)
        
        self.best_reward = -float('inf')
        self.total_rewards = 0
        
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
            
            const frameworks = {
                react: !!window.React || !!document.querySelector('[data-reactroot]'),
                angular: !!window.angular || !!document.querySelector('[ng-app]'),
                vue: !!window.Vue || !!document.querySelector('[v-app]'),
                jquery: !!window.jQuery
            };
            
            return {
                url: window.location.href,
                title: document.title,
                interactives: interactives.slice(0, 50),
                metrics: metrics,
                frameworks: frameworks,
                timestamp: Date.now()
            };
        })()
        """
        
        try:
            result = self.cdp.evaluate_script(script)
            if result:
                return result
        except Exception as e:
            print(f"⚠️ Perception error: {e}")
            
        return {'url': '', 'interactives': [], 'metrics': {}, 'frameworks': {}}
        
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
            self._log_json('actions', {
                'action': action,
                'success': False,
                'error': str(e)
            })
            return {'success': False, 'error': str(e)}
            
    def calculate_reward(self, old_state: Dict, new_state: Dict, 
                         success: bool, action_text: str) -> float:
        reward = 0.0
        components = {}
        
        if success:
            reward += 1.0
            components['success'] = 1.0
            
        old_url = old_state.get('url', '')
        new_url = new_state.get('url', '')
        if old_url and new_url and old_url != new_url:
            reward += 2.0
            components['page_change'] = 2.0
            
        old_count = len(old_state.get('interactives', []))
        new_count = len(new_state.get('interactives', []))
        if new_count > old_count * 1.2:
            reward += 1.5
            components['more_interactive'] = 1.5
            
        if old_url == new_url and not success:
            reward -= 0.5
            components['stagnation'] = -0.5
            
        self._log_json('rewards', {
            'reward': reward,
            'components': components,
            'success': success,
            'action': action_text[:50]
        })
        
        return reward
        
    def _prepare_actions(self, state: Dict) -> List[Dict]:
        actions = []
        seen = set()
        
        for el in state.get('interactives', []):
            text = el.get('text', '').strip()
            if not text or len(text) < 2:
                continue
                
            if text in seen:
                continue
            seen.add(text)
            
            score = 0.0
            
            # Valuable keywords
            high_value = ['apply', 'submit', 'register', 'login', 'search']
            if any(kw in text.lower() for kw in high_value):
                score += 2.0
                
            nav = ['next', 'more', 'view', 'see', 'load']
            if any(kw in text.lower() for kw in nav):
                score += 1.0
                
            if el.get('visible', False):
                score += 0.5
                
            depth = el.get('depth', 100)
            score -= max(0, depth - 5) * 0.05
            
            actions.append({
                'text': text,
                'score': score,
                'selector': el.get('id', ''),
                'tag': el.get('tag', ''),
                'depth': el.get('depth', 0)
            })
            
        actions.sort(key=lambda x: x.get('score', 0), reverse=True)
        return actions[:20]
        
    def run(self):
        print("🧠 AGI MATH SYSTEM STARTING")
        print("=" * 70)
        print(f"Embedding Dim: {AGI_CONFIG['embedding_dim']}")
        print(f"Population Size: {AGI_CONFIG['population_size']}")
        print(f"Mutation Rate: {AGI_CONFIG['mutation_rate']}")
        print(f"Learning Rate: {AGI_CONFIG['learning_rate']}")
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
                print(f"  {i}. {action['text'][:40]} (score: {score:.2f})")
                
            # Long-chain reasoning
            sequence = self.reasoner.propose_sequence(
                state_embed, actions, horizon=2
            )
            
            if sequence:
                print(f"\n🔗 Proposed Sequence:")
                for i, action in enumerate(sequence[:3], 1):
                    print(f"  {i}. {action.get('text', '')[:40]}")
                    
            agent_idx = cycle % self.population.population_size
            agent = self.population.population[agent_idx]
            
            if random.random() < agent.exploration_rate:
                print(f"\n🎲 Exploration (rate: {agent.exploration_rate:.2f})")
                action = random.choice(actions[:5])
            else:
                if sequence:
                    action = sequence[0]
                else:
                    action = actions[0]
                    
            print(f"\n🎯 Chosen: {action.get('text', '')[:50]}")
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
            
            action_embed = self.reasoner._action_to_embedding(action)
            loss = self.world_model.learn(state_embed, action_embed, new_state_embed)
            
            prediction = self.world_model.predict(state_embed, action_embed)
            self._log_json('predictions', {
                'actual': new_state_embed.tolist(),
                'predicted': prediction.tolist(),
                'loss': float(loss)
            })
            
            self.population.evaluate(agent_idx, reward, result.get('success', False))
            
            if cycle % 3 == 0:
                evolution_stats = self.population.evolve()
                self._log_json('evolution', evolution_stats)
                print(f"\n🧬 Evolution Stats:")
                print(f"  Generation: {evolution_stats['generation']}")
                print(f"  Best Fitness: {evolution_stats['best_fitness']:.2f}")
                print(f"  Avg Fitness: {evolution_stats['avg_fitness']:.2f}")
                
            self.reasoner.update_from_experience([action], reward)
            
            self.reward_history.append(reward)
            self.total_rewards += reward
            
            if reward > self.best_reward:
                self.best_reward = reward
                print(f"   📈 New best reward: {reward:.2f}")
                
            metrics = {
                'reward': reward,
                'success': result.get('success', False),
                'loss': float(loss),
                'agent_fitness': agent.fitness,
                'best_reward': self.best_reward,
                'total_rewards': self.total_rewards,
                'exploration_rate': agent.exploration_rate
            }
            self._log_json('metrics', metrics)
            
            best_hyp = self.reasoner.get_best_hypothesis()
            if best_hyp:
                print(f"\n🔬 Best Hypothesis:")
                print(f"  Sequence: {' → '.join(best_hyp.get('sequence', []))}")
                print(f"  Score: {best_hyp.get('score', 0):.2f}")
                
            print(f"\n📊 Results:")
            print(f"  Reward: {reward:.2f}")
            print(f"  Success: {'✅' if result.get('success') else '❌'}")
            print(f"  Loss: {loss:.4f}")
            print(f"  Best Reward: {self.best_reward:.2f}")
            
            state = new_state
            state_embed = new_state_embed
            
        self._generate_report()
        
    def _generate_report(self):
        print("\n" + "=" * 80)
        print("🧠 AGI MATH SYSTEM - FINAL REPORT")
        print("=" * 80)
        
        print(f"\n📊 STATISTICS:")
        print(f"  Total Cycles: {self.current_cycle}")
        print(f"  Best Reward: {self.best_reward:.2f}")
        print(f"  Total Rewards: {self.total_rewards:.2f}")
        print(f"  Generation: {self.population.generation}")
        print(f"  Best Fitness: {self.population.best_fitness:.2f}")
        
        best_hyp = self.reasoner.get_best_hypothesis()
        if best_hyp:
            print(f"\n🔬 BEST HYPOTHESIS:")
            print(f"  Sequence: {' → '.join(best_hyp.get('sequence', []))}")
            print(f"  Score: {best_hyp.get('score', 0):.2f}")
            
        best_agent = max(self.population.population, key=lambda x: x.fitness)
        print(f"\n🧬 BEST AGENT:")
        print(f"  Strategy: {best_agent.strategy}")
        print(f"  Fitness: {best_agent.fitness:.2f}")
        print(f"  Actions: {best_agent.actions_taken}")
        print(f"  Exploration Rate: {best_agent.exploration_rate:.2f}")
        
        print(f"\n📁 LOG FILES:")
        for log_file in self.log_dir.glob("*.jsonl"):
            size = log_file.stat().st_size
            print(f"  {log_file.name}: {size} bytes")
            
        print(f"\n🔍 ANALYZE WITH jq:")
        print(f"  # Rewards summary:")
        print(f"  jq '.reward' {self.log_dir}/rewards.jsonl | sort -n")
        print(f"\n  # Success rate:")
        print(f"  jq 'select(.success==true) | .success' {self.log_dir}/actions.jsonl | wc -l")
        print(f"\n  # Evolution progress:")
        print(f"  jq '.generation, .best_fitness' {self.log_dir}/evolution.jsonl")
        
        print("\n" + "=" * 80)

# ============================================================================
# MAIN
# ============================================================================

def main():
    print("🧠 AGI MATH REASONING SYSTEM")
    print("=" * 70)
    print("Mathematical long-chain reasoning with JEPA")
    print("Evolutionary strategies with mutation")
    print("Full JSON/jq logging")
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
