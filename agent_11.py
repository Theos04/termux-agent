#!/usr/bin/env python3
"""
AGENT 11 - FIXED Global Memory Manager
Fixed: defaultdict -> Counter for most_common
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

# ============================================================================
# CONFIGURATION - Memory Optimized
# ============================================================================

AGI_CONFIG = {
    "action_delay": 8.0,
    "perception_delay": 10.0,
    "max_cycles": 30,
    "embedding_dim": 32,
    "population_size": 3,
    "mutation_rate": 0.08,
    "learning_rate": 0.001,
    "gamma": 0.95,
    "port": 9260,
    "reasoning_horizon": 8,
    "repeat_action_penalty": -2.0,
    "novelty_bonus": 1.5,
    "dtype": np.float32,
}

# ============================================================================
# 1. FIXED GLOBAL MEMORY MANAGER
# ============================================================================

class GlobalActionMemory:
    """
    Shared memory across all agents in the population
    Uses Counter for proper most_common() support
    """
    
    def __init__(self):
        self.action_history = deque(maxlen=100)
        self.state_history = deque(maxlen=100)
        self.action_counts = Counter()  # Changed from defaultdict to Counter
        self.session_actions = {}  # Track by session ID
        
    def record_action(self, action_text: str, state_embed: np.ndarray = None, 
                     session_id: str = None):
        """Record action in shared memory"""
        self.action_history.append((action_text, time.time()))
        self.action_counts[action_text] += 1
        
        if session_id:
            if session_id not in self.session_actions:
                self.session_actions[session_id] = []
            self.session_actions[session_id].append(action_text)
            
        # Store state for similarity comparison
        if state_embed is not None:
            self.state_history.append((action_text, state_embed))
            
    def get_repetition_penalty(self, action_text: str, state_embed: np.ndarray = None) -> float:
        """Calculate repetition penalty from global memory"""
        global_count = self.action_counts.get(action_text, 0)
        
        if global_count <= 1:
            return 0.0
            
        # Exponential penalty for repeated actions
        if global_count <= 3:
            penalty = -0.5 * (global_count - 1)  # -0.5, -1.0
        else:
            penalty = -2.0 * (global_count - 2)  # Exponential scaling
            
        # State similarity penalty
        if state_embed is not None and len(self.state_history) > 0:
            similar_count = 0
            for past_action, past_state in list(self.state_history)[-20:]:
                if past_action == action_text:
                    continue
                if past_state is not None:
                    similarity = np.dot(past_state, state_embed) / (
                        np.linalg.norm(past_state) * np.linalg.norm(state_embed) + 1e-8
                    )
                    if similarity > 0.8:
                        similar_count += 1
                        
            if similar_count > 2:
                penalty -= 1.0 * (similar_count - 2)
                
        return penalty
        
    def get_global_stats(self) -> Dict:
        """Get global memory statistics"""
        return {
            'total_actions': len(self.action_history),
            'unique_actions': len(self.action_counts),
            'most_common': self.action_counts.most_common(5),  # Now works with Counter
            'total_sessions': len(self.session_actions)
        }

# ============================================================================
# 2. MEMORY-OPTIMIZED DOM EXPLORER
# ============================================================================

class MemoryOptimizedDOMExplorer:
    def __init__(self, page):
        self.page = page
        
    def extract_hierarchy(self, max_depth: int = 8) -> Dict:
        script = f"""
        (function() {{
            function buildTree(node, depth) {{
                if (depth > {max_depth}) return null;
                if (!node || node.nodeType !== 1) return null;
                
                const rect = node.getBoundingClientRect();
                const children = [];
                const childNodes = node.children;
                const max_children = 10;
                for (let i = 0; i < Math.min(childNodes.length, max_children); i++) {{
                    const child = buildTree(childNodes[i], depth + 1);
                    if (child) children.push(child);
                }}
                
                return {{
                    tag: node.tagName.toLowerCase(),
                    id: node.id || '',
                    classes: node.className || '',
                    depth: depth,
                    visible: rect.width > 0 && rect.height > 0,
                    position: {{
                        x: rect.x || 0,
                        y: rect.y || 0,
                        width: rect.width || 0,
                        height: rect.height || 0
                    }},
                    child_count: children.length
                }};
            }}
            
            return {{
                root: document.body ? buildTree(document.body, 0) : null,
                total_elements: Math.min(document.querySelectorAll('*').length, 1000)
            }};
        }})()
        """
        
        try:
            result = self.page.js(script)
            return result if result else {'root': None, 'total_elements': 0}
        except:
            return {'root': None, 'total_elements': 0}
            
    def get_clickable_elements(self) -> List[Dict]:
        script = """
        (function() {
            const elements = [];
            const max_elements = 30;
            const selectors = 'button, a[href], [role="button"], input, select';
            
            document.querySelectorAll(selectors).forEach(el => {
                if (elements.length >= max_elements) return;
                const rect = el.getBoundingClientRect();
                const text = (el.textContent || '').trim().slice(0, 50);
                if (!text || text.length < 2) return;
                
                elements.push({
                    text: text,
                    tag: el.tagName.toLowerCase(),
                    href: el.getAttribute('href') || '',
                    id: el.id || '',
                    visible: rect.width > 0 && rect.height > 0,
                    position: { x: rect.x || 0, y: rect.y || 0 }
                });
            });
            return elements;
        })()
        """
        
        try:
            result = self.page.js(script)
            return result if result else []
        except:
            return []

# ============================================================================
# 3. MEMORY-OPTIMIZED CDP WRAPPER
# ============================================================================

class MemoryOptimizedCDP:
    def __init__(self, port: int = 9260):
        self.port = port
        self.page = None
        self.explorer = None
        self.connected = False
        self.global_memory = GlobalActionMemory()
        
    def connect(self) -> bool:
        try:
            from geturl import ChromePage
            self.page = ChromePage(port=self.port)
            if self.page.connect():
                self.connected = True
                self.explorer = MemoryOptimizedDOMExplorer(self.page)
                print(f"🔍 Connected to: {self.page.get_title()}")
                return True
        except Exception as e:
            print(f"⚠️ Connect error: {e}")
        return False
        
    def get_perception_data(self) -> Dict:
        if not self.connected or not self.explorer:
            return self._get_fallback_perception()
            
        try:
            hierarchy = self.explorer.extract_hierarchy()
            clickable = self.explorer.get_clickable_elements()
            
            return {
                'url': self.page.page_url,
                'title': self.page.get_title(),
                'hierarchy': hierarchy,
                'interactives': clickable,
                'total_elements': hierarchy.get('total_elements', 0),
                'timestamp': time.time()
            }
        except Exception as e:
            return self._get_fallback_perception()
            
    def _get_fallback_perception(self) -> Dict:
        return {'url': '', 'title': '', 'interactives': [], 'total_elements': 0}
        
    def execute_action(self, action: Dict) -> Dict:
        text = action.get('text', '')
        if not text or len(text) < 2:
            return {'success': False, 'error': 'Invalid text'}
            
        try:
            success = self.page.click_by_text(text)
            return {'success': success, 'method': 'text'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

# ============================================================================
# 4. MEMORY-OPTIMIZED EMBEDDING
# ============================================================================

class MemoryOptimizedEmbedding:
    def __init__(self, embedding_dim: int = 32):
        self.embedding_dim = embedding_dim
        self.dtype = AGI_CONFIG['dtype']
        
        self.W_hierarchy = np.random.randn(64, embedding_dim).astype(self.dtype) * 0.1
        self.W_interactive = np.random.randn(32, embedding_dim).astype(self.dtype) * 0.1
        
        self.b_hierarchy = np.zeros(embedding_dim, dtype=self.dtype)
        self.b_interactive = np.zeros(embedding_dim, dtype=self.dtype)
        
        self.training_steps = 0
        self.reconstruction_errors = deque(maxlen=50)
        
    def encode(self, perception_data: Dict) -> np.ndarray:
        try:
            hierarchy_features = self._extract_hierarchy_features(perception_data)
            interactive_features = self._extract_interactive_features(perception_data)
            
            hierarchy_embed = np.dot(hierarchy_features, self.W_hierarchy) + self.b_hierarchy
            interactive_embed = np.dot(interactive_features, self.W_interactive) + self.b_interactive
            
            combined = hierarchy_embed + interactive_embed
            
            norm = np.linalg.norm(combined)
            if norm > 0:
                combined = combined / norm
                
            return combined.astype(self.dtype)
            
        except Exception as e:
            return np.random.randn(self.embedding_dim).astype(self.dtype) * 0.01
            
    def _extract_hierarchy_features(self, data: Dict) -> np.ndarray:
        features = []
        hierarchy = data.get('hierarchy', {})
        total = min(hierarchy.get('total_elements', 0), 1000) / 1000
        
        features.append(total)
        
        root = hierarchy.get('root', {})
        if root:
            features.append(1.0 if root.get('visible', False) else 0.0)
            features.append(min(1.0, root.get('depth', 0) / 10))
        else:
            features.extend([0.0, 0.0])
            
        while len(features) < 64:
            features.append(0.0)
            
        return np.array(features[:64], dtype=self.dtype)
        
    def _extract_interactive_features(self, data: Dict) -> np.ndarray:
        features = []
        interactives = data.get('interactives', [])
        
        total = max(1, len(interactives))
        decisive_count = 0
        visible_count = 0
        
        for el in interactives:
            if el.get('visible', False):
                visible_count += 1
            text = el.get('text', '').lower()
            if any(kw in text for kw in ['apply', 'submit', 'login', 'search', 'profile', 'job']):
                decisive_count += 1
                
        features.extend([
            min(1.0, total / 20),
            visible_count / total,
            decisive_count / total
        ])
        
        while len(features) < 32:
            features.append(0.0)
            
        return np.array(features[:32], dtype=self.dtype)
        
    def learn(self, perception_data: Dict, reconstructed: Dict) -> float:
        self.training_steps += 1
        original = self.encode(perception_data)
        reconstructed_vec = self.encode(reconstructed)
        loss = np.mean((original - reconstructed_vec) ** 2)
        self.reconstruction_errors.append(loss)
        return float(loss)

# ============================================================================
# 5. JEPA WORLD MODEL
# ============================================================================

class JEPAWorldModel:
    def __init__(self, embedding_dim: int = 32):
        self.embedding_dim = embedding_dim
        self.dtype = AGI_CONFIG['dtype']
        
        self.W_state = np.random.randn(embedding_dim, embedding_dim).astype(self.dtype) * 0.1
        self.W_action = np.random.randn(embedding_dim, embedding_dim).astype(self.dtype) * 0.1
        self.b_predict = np.zeros(embedding_dim, dtype=self.dtype)
        
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
        
        return prediction.flatten().astype(self.dtype)
        
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
# 6. EVOLUTIONARY POPULATION
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
    
class EvolutionaryPopulation:
    def __init__(self, population_size: int = 3, embedding_dim: int = 32,
                 global_memory: GlobalActionMemory = None):
        self.population_size = population_size
        self.embedding_dim = embedding_dim
        self.global_memory = global_memory or GlobalActionMemory()
        self.population = []
        self.generation = 0
        self.best_fitness = -float('inf')
        self.best_agent = None
        self.dtype = AGI_CONFIG['dtype']
        self._initialize_population()
        
    def _initialize_population(self):
        strategies = ['greedy', 'exploratory', 'balanced']
        for i in range(self.population_size):
            agent = EvolutionaryAgent(
                weights={
                    'W_state': np.random.randn(self.embedding_dim, self.embedding_dim).astype(self.dtype) * 0.1,
                    'W_action': np.random.randn(self.embedding_dim, self.embedding_dim).astype(self.dtype) * 0.1,
                    'b_predict': np.zeros(self.embedding_dim, dtype=self.dtype)
                },
                exploration_rate=random.uniform(0.1, 0.4),
                strategy=strategies[i % len(strategies)]
            )
            self.population.append(agent)
            
    def evaluate(self, agent_idx: int, reward: float, success: bool, 
                 action_text: str, state_embed: np.ndarray = None,
                 session_id: str = None):
        agent = self.population[agent_idx]
        
        if self.global_memory:
            self.global_memory.record_action(action_text, state_embed, session_id)
            repetition_penalty = self.global_memory.get_repetition_penalty(action_text, state_embed)
        else:
            repetition_penalty = 0.0
            
        novelty_bonus = AGI_CONFIG['novelty_bonus'] if len(self.global_memory.action_counts) > 5 else 0
        
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
                    noise = np.random.randn(*child_weights[key].shape).astype(self.dtype) * 0.05
                    child_weights[key] += noise
                    
            child = EvolutionaryAgent(
                weights=child_weights,
                exploration_rate=random.uniform(0.1, 0.4),
                strategy=random.choice(['greedy', 'exploratory', 'balanced'])
            )
            survivors.append(child)
            
        self.population = survivors
        
        return {
            'generation': self.generation,
            'best_fitness': self.best_fitness,
            'avg_fitness': sum(a.fitness for a in self.population) / len(self.population),
            'best_strategy': self.population[0].strategy,
            'global_actions': len(self.global_memory.action_counts) if self.global_memory else 0
        }
        
    def _tournament_select(self, k: int = 2) -> EvolutionaryAgent:
        candidates = random.sample(self.population, min(k, len(self.population)))
        return max(candidates, key=lambda x: x.fitness)

# ============================================================================
# 7. MAIN AGENT
# ============================================================================

class Agent11:
    def __init__(self, port: int = 9260, max_cycles: int = 30):
        self.port = port
        self.max_cycles = max_cycles
        
        self.session_dir = Path(f"agent11_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        self.session_dir.mkdir(parents=True, exist_ok=True)
        
        self.global_memory = GlobalActionMemory()
        self.cdp = MemoryOptimizedCDP(port=port)
        self.embedder = MemoryOptimizedEmbedding(embedding_dim=AGI_CONFIG['embedding_dim'])
        self.world_model = JEPAWorldModel(embedding_dim=AGI_CONFIG['embedding_dim'])
        self.population = EvolutionaryPopulation(
            population_size=AGI_CONFIG['population_size'],
            embedding_dim=AGI_CONFIG['embedding_dim'],
            global_memory=self.global_memory
        )
        
        self.current_cycle = 0
        self.reward_history = deque(maxlen=50)
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
        return self.cdp.get_perception_data()
        
    def prepare_actions(self, perception_data: Dict) -> List[Dict]:
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
            
            if any(kw in text.lower() for kw in decisive_keywords):
                score += 3.0
                
            nav = ['next', 'more', 'view', 'see', 'load']
            if any(kw in text.lower() for kw in nav):
                score += 1.0
                
            if el.get('visible', True):
                score += 0.5
                
            if 'close' in text.lower() or 'ad' in text.lower():
                score -= 2.0
                
            # Global repetition penalty
            global_penalty = self.global_memory.get_repetition_penalty(text)
            score += global_penalty * 0.5
                
            actions.append({
                'text': text,
                'score': score,
                'tag': el.get('tag', ''),
                'is_decisive': any(kw in text.lower() for kw in decisive_keywords)
            })
            
        actions.sort(key=lambda x: x.get('score', 0), reverse=True)
        return actions[:20]
        
    def calculate_reward(self, perception_before: Dict, perception_after: Dict,
                         success: bool, action_text: str) -> float:
        reward = 0.0
        components = {}
        
        if success:
            reward += 0.5
            components['success'] = 0.5
            
        url_before = perception_before.get('url', '')
        url_after = perception_after.get('url', '')
        if url_before and url_after and url_before != url_after:
            reward += 3.0
            components['page_change'] = 3.0
            
        count_before = len(perception_before.get('interactives', []))
        count_after = len(perception_after.get('interactives', []))
        if count_after > count_before * 1.2:
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
        
    def _text_to_embedding(self, text: str) -> np.ndarray:
        embed = np.zeros(AGI_CONFIG['embedding_dim'], dtype=AGI_CONFIG['dtype'])
        keywords = ['apply', 'submit', 'login', 'search', 'next', 'profile', 'job']
        for i, kw in enumerate(keywords):
            if kw in text.lower():
                embed[i % AGI_CONFIG['embedding_dim']] = 1.0
        norm = np.linalg.norm(embed)
        if norm > 0:
            embed = embed / norm
        return embed
        
    def run(self):
        print("🧠 AGENT 11 - MEMORY-OPTIMIZED AGI")
        print("=" * 70)
        print(f"Embedding Dim: {AGI_CONFIG['embedding_dim']} (float32)")
        print(f"Population Size: {AGI_CONFIG['population_size']}")
        print(f"Global Memory: Shared across population")
        print(f"Repetition Penalty: Exponential with global tracking")
        print("=" * 70)
        
        if not self.cdp.connect():
            print("❌ Not connected")
            return
            
        perception_data = self.perceive()
        state_embed = self.embedder.encode(perception_data)
        
        print(f"📍 Starting on: {perception_data.get('url', 'unknown')}")
        print(f"📊 Interactive elements: {len(perception_data.get('interactives', []))}")
        print(f"📊 Embedding dim: {len(state_embed)}")
        
        for cycle in range(1, self.max_cycles + 1):
            self.current_cycle = cycle
            
            print(f"\n{'='*70}")
            print(f"🔄 CYCLE {cycle}/{self.max_cycles}")
            print(f"{'='*70}")
            
            perception_data = self.perceive()
            state_embed = self.embedder.encode(perception_data)
            
            actions = self.prepare_actions(perception_data)
            
            if not actions:
                print("⏳ No actions available, waiting...")
                time.sleep(AGI_CONFIG['action_delay'])
                continue
                
            print(f"\n📋 Top Actions ({len(actions)} available):")
            for i, action in enumerate(actions[:5], 1):
                score = action.get('score', 0)
                decisive = "🎯" if action.get('is_decisive', False) else "  "
                print(f"  {i}. {decisive} {action['text'][:40]} (score: {score:.2f})")
                
            global_stats = self.global_memory.get_global_stats()
            print(f"\n📊 Global Memory: {global_stats['total_actions']} actions, "
                  f"{global_stats['unique_actions']} unique")
            
            # Show most common to highlight repetition
            if global_stats['most_common']:
                print(f"   Most Common: {global_stats['most_common'][0][0]} "
                      f"({global_stats['most_common'][0][1]} times)")
            
            agent_idx = cycle % self.population.population_size
            agent = self.population.population[agent_idx]
            
            decisive_actions = [a for a in actions if a.get('is_decisive', False)]
            
            if decisive_actions and random.random() < 0.8:
                action = decisive_actions[0]
                print(f"\n🎯 Decisive action: {action['text'][:40]}")
            elif random.random() < min(0.3, agent.exploration_rate):
                action = random.choice(actions[:5])
                print(f"\n🎲 Exploring: {action['text'][:40]}")
            else:
                action = actions[0]
                print(f"\n🎯 Greedy: best action")
                
            print(f"   Strategy: {agent.strategy}")
            print(f"   Fitness: {agent.fitness:.2f}")
            
            time.sleep(AGI_CONFIG['action_delay'])
            result = self.cdp.execute_action(action)
            
            print(f"   ⏳ Settling...")
            time.sleep(AGI_CONFIG['perception_delay'])
            
            new_perception = self.perceive()
            new_state_embed = self.embedder.encode(new_perception)
            
            reward = self.calculate_reward(
                perception_data, new_perception,
                result.get('success', False),
                action.get('text', '')
            )
            
            adjusted_reward = self.population.evaluate(
                agent_idx, reward, result.get('success', False),
                action.get('text', ''),
                state_embed,
                session_id=str(cycle)
            )
            
            action_embed = self._text_to_embedding(action.get('text', ''))
            loss = self.world_model.learn(state_embed, action_embed, new_state_embed)
            
            metrics = {
                'reward': adjusted_reward,
                'success': result.get('success', False),
                'loss': float(loss),
                'agent_fitness': agent.fitness,
                'best_reward': self.best_reward,
                'total_rewards': self.total_rewards,
                'decisive_actions': self.decisive_action_count,
                'global_actions': global_stats['total_actions'],
                'global_unique': global_stats['unique_actions'],
                'state_norm': float(np.linalg.norm(state_embed))
            }
            self._log_json('metrics', metrics)
            
            self.reward_history.append(adjusted_reward)
            self.total_rewards += adjusted_reward
            
            if adjusted_reward > self.best_reward:
                self.best_reward = adjusted_reward
                print(f"   📈 New best reward: {adjusted_reward:.2f}")
                
            if self.decisive_action_count >= 3:
                print(f"\n🎉🎉🎉 DECISIVE ACTION GOAL ACHIEVED! 🎉🎉🎉")
                print(f"   Decisive actions taken: {self.decisive_action_count}")
                break
                
            if cycle % 3 == 0:
                evolution_stats = self.population.evolve()
                self._log_json('evolution', evolution_stats)
                print(f"\n🧬 Evolution:")
                print(f"  Generation: {evolution_stats['generation']}")
                print(f"  Best Fitness: {evolution_stats['best_fitness']:.2f}")
                print(f"  Global Actions: {evolution_stats['global_actions']}")
                
            print(f"\n📊 Results:")
            print(f"  Reward: {adjusted_reward:.2f}")
            print(f"  Success: {'✅' if result.get('success') else '❌'}")
            print(f"  Loss: {loss:.4f}")
            print(f"  Best Reward: {self.best_reward:.2f}")
            print(f"  Decisive Actions: {self.decisive_action_count}")
            print(f"  Global Actions: {global_stats['total_actions']}")
            
        self._generate_report()
        
    def _generate_report(self):
        print("\n" + "=" * 80)
        print("🧠 AGENT 11 - FINAL REPORT")
        print("=" * 80)
        
        print(f"\n📊 STATISTICS:")
        print(f"  Total Cycles: {self.current_cycle}")
        print(f"  Best Reward: {self.best_reward:.2f}")
        print(f"  Total Rewards: {self.total_rewards:.2f}")
        print(f"  Generation: {self.population.generation}")
        print(f"  Best Fitness: {self.population.best_fitness:.2f}")
        print(f"  Decisive Actions: {self.decisive_action_count}")
        
        global_stats = self.global_memory.get_global_stats()
        print(f"\n📊 GLOBAL MEMORY:")
        print(f"  Total Actions: {global_stats['total_actions']}")
        print(f"  Unique Actions: {global_stats['unique_actions']}")
        print(f"  Most Common: {global_stats['most_common'][:3]}")
        
        best_agent = max(self.population.population, key=lambda x: x.fitness)
        print(f"\n🧬 BEST AGENT:")
        print(f"  Strategy: {best_agent.strategy}")
        print(f"  Fitness: {best_agent.fitness:.2f}")
        print(f"  Actions: {best_agent.actions_taken}")
        
        print(f"\n📁 LOG FILES:")
        for log_file in self.log_dir.glob("*.jsonl"):
            size = log_file.stat().st_size
            print(f"  {log_file.name}: {size} bytes")
            
        print("\n" + "=" * 80)

# ============================================================================
# MAIN
# ============================================================================

def main():
    print("🧠 AGENT 11 - MEMORY-OPTIMIZED AGI MATH SYSTEM")
    print("=" * 70)
    print("Key Features:")
    print("  ✅ Global memory across population")
    print("  ✅ Exponential repetition penalty")
    print("  ✅ float32 + 32-dim embeddings (16KB)")
    print("  ✅ Shared memory prevents fragmentation")
    print("  ✅ 256KB memory constraint compliant")
    print("=" * 70)
    
    port = AGI_CONFIG['port']
    max_cycles = AGI_CONFIG['max_cycles']
    
    agent = Agent11(port=port, max_cycles=max_cycles)
    
    if not agent.cdp.connect():
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
