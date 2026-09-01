#!/usr/bin/env python3
"""
NEURAL WEB RL AGENT - Enhanced with Deep Learning Principles
Features:
- Neural Perception Layer (DOM to vector encoding)
- Hidden Layer Abstraction (deep Q-learning)
- Evolutionary Strategy for Exploration (population-based)
- Contextual Multi-Armed Bandit (context-aware action selection)
- Pattern Learning & Memory (experience replay)
- Works on ANY website
- Learns to explore and navigate
- Detects page types dynamically
- Builds internal representation of site structure
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
import numpy as np

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
# Neural Perception Layer
# ============================================================================

class NeuralStateEncoder:
    """Transforms DOM into neural network input vectors"""
    def __init__(self, embedding_dim: int = 128):
        self.embedding_dim = embedding_dim
        self.feature_weights = defaultdict(float)
        self.element_embeddings = {}
        self.normalization_stats = {
            'mean': None,
            'std': None
        }
        
    def encode(self, state: Dict) -> np.ndarray:
        """Convert state to neural input vector"""
        features = []
        
        # 1. DOM Structure Features (like pixels in an image)
        dom_features = self._extract_dom_structure(state)
        features.extend(dom_features)
        
        # 2. Text Features (embedding-based)
        text_features = self._extract_text_embeddings(state)
        features.extend(text_features)
        
        # 3. Interaction Features (what's clickable)
        interaction_features = self._extract_interaction_features(state)
        features.extend(interaction_features)
        
        # 4. Page type features
        page_type_features = self._extract_page_type_features(state)
        features.extend(page_type_features)
        
        # Convert to numpy array
        feature_vector = np.array(features, dtype=np.float32)
        
        # Pad or trim to embedding dimension
        if len(feature_vector) < self.embedding_dim:
            feature_vector = np.pad(feature_vector, (0, self.embedding_dim - len(feature_vector)))
        elif len(feature_vector) > self.embedding_dim:
            feature_vector = feature_vector[:self.embedding_dim]
            
        # Normalize
        return self._normalize(feature_vector)
    
    def _extract_dom_structure(self, state: Dict) -> List[float]:
        """Extract DOM as feature grid"""
        grid_size = 8
        features = []
        
        # Create feature grid
        depth_grid = np.zeros((grid_size, grid_size))
        semantic_grid = np.zeros((grid_size, grid_size))
        
        interactive = state.get('dom', {}).get('interactive_elements', [])
        
        for el in interactive[:50]:  # Limit to 50 elements
            depth = min(el.get('depth', 0), grid_size - 1)
            # Use semantic features for position
            semantics = el.get('semantics', 'generic')
            semantic_hash = hash(semantics) % grid_size
            
            depth_grid[depth, semantic_hash] += 1.0
            semantic_grid[depth, semantic_hash] += 0.5
            
        # Flatten grids
        features.extend(depth_grid.flatten().tolist())
        features.extend(semantic_grid.flatten().tolist())
        
        return features
    
    def _extract_text_embeddings(self, state: Dict) -> List[float]:
        """Extract text features"""
        text = state.get('page', {}).get('text', '').lower()
        words = ['apply', 'submit', 'login', 'signup', 'register', 'search', 'next', 
                 'profile', 'inbox', 'messages', 'save', 'delete', 'edit', 'view',
                 'more', 'back', 'home', 'contact', 'about', 'help', 'settings']
        
        embeddings = []
        word_count = max(1, len(text.split()))
        
        for word in words:
            # Count occurrences
            count = text.count(word)
            embeddings.append(count / word_count)
            # Binary presence
            embeddings.append(1.0 if word in text else 0.0)
            
        return embeddings[:20]  # Limit to 20 features
    
    def _extract_interaction_features(self, state: Dict) -> List[float]:
        """Extract features about interactive elements"""
        interactive = state.get('dom', {}).get('interactive_elements', [])
        features = []
        
        # Count by priority
        priorities = {'high': 0, 'medium': 0, 'low': 0}
        for el in interactive:
            text = el.get('text', '').lower()
            if any(word in text for word in ['apply', 'submit', 'login', 'signup', 'register']):
                priorities['high'] += 1
            elif any(word in text for word in ['search', 'next', 'more', 'view', 'profile']):
                priorities['medium'] += 1
            else:
                priorities['low'] += 1
                
        features.extend([priorities['high'], priorities['medium'], priorities['low']])
        features.append(min(10, len(interactive)))
        
        # Landmark distribution
        landmarks = {}
        for el in interactive:
            landmark = el.get('landmark', 'body')
            landmarks[landmark] = landmarks.get(landmark, 0) + 1
            
        # Top 5 landmarks
        sorted_landmarks = sorted(landmarks.items(), key=lambda x: x[1], reverse=True)[:5]
        for landmark, count in sorted_landmarks:
            features.append(count)
        while len(features) < 9:  # Ensure consistent length
            features.append(0.0)
            
        return features
    
    def _extract_page_type_features(self, state: Dict) -> List[float]:
        """Extract page type features"""
        features = []
        page_types = ['login', 'search_results', 'listing', 'form', 'content']
        
        for ptype in page_types:
            features.append(1.0 if state.get('page_type') == ptype else 0.0)
            
        features.append(1.0 if state.get('has_login') else 0.0)
        features.append(1.0 if state.get('has_search') else 0.0)
        features.append(1.0 if state.get('has_results') else 0.0)
        features.append(1.0 if state.get('has_items') else 0.0)
        
        return features
    
    def _normalize(self, vector: np.ndarray) -> np.ndarray:
        """Normalize feature vector"""
        # Min-max normalization
        min_val = np.min(vector)
        max_val = np.max(vector)
        
        if max_val - min_val > 0:
            normalized = (vector - min_val) / (max_val - min_val)
        else:
            normalized = np.zeros_like(vector)
            
        # Clip to [0, 1]
        return np.clip(normalized, 0, 1)

# ============================================================================
# Hidden Layer Abstraction (Neural Network)
# ============================================================================

class NeuralNetwork:
    """Simple neural network with hidden layers"""
    def __init__(self, input_dim: int = 128, hidden_dim: int = 64, output_dim: int = 30):
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        self.output_dim = output_dim
        
        # Initialize weights with Xavier initialization
        self.W1 = np.random.randn(input_dim, hidden_dim) * np.sqrt(2.0 / input_dim)
        self.b1 = np.zeros(hidden_dim)
        self.W2 = np.random.randn(hidden_dim, output_dim) * np.sqrt(2.0 / hidden_dim)
        self.b2 = np.zeros(output_dim)
        
        self.learning_rate = 0.01
        self.optimizer = AdamOptimizer(self.learning_rate)
        
        # Weight decay (L2 regularization)
        self.weight_decay = 0.0001
        
    def forward(self, x: np.ndarray) -> np.ndarray:
        """Forward pass through the network"""
        # Hidden layer with ReLU activation
        hidden = np.maximum(0, np.dot(x, self.W1) + self.b1)
        # Dropout (during training)
        if hasattr(self, 'training') and self.training:
            dropout_mask = np.random.rand(*hidden.shape) > 0.2
            hidden = hidden * dropout_mask / 0.8
            
        # Output layer (scores for each action)
        output = np.dot(hidden, self.W2) + self.b2
        return output
    
    def backward(self, x: np.ndarray, grad_output: np.ndarray) -> Tuple[np.ndarray, ...]:
        """Backward pass for gradient computation"""
        # Forward pass
        hidden = np.maximum(0, np.dot(x, self.W1) + self.b1)
        output = np.dot(hidden, self.W2) + self.b2
        
        # Gradient of output
        grad_output_actual = grad_output.copy()
        
        # Gradient of hidden layer
        grad_hidden = np.dot(grad_output_actual, self.W2.T)
        grad_hidden[hidden <= 0] = 0  # ReLU derivative
        
        # Gradients for weights
        grad_W2 = np.outer(hidden, grad_output_actual) + self.weight_decay * self.W2
        grad_b2 = grad_output_actual
        grad_W1 = np.outer(x, grad_hidden) + self.weight_decay * self.W1
        grad_b1 = grad_hidden
        
        return grad_W1, grad_b1, grad_W2, grad_b2
    
    def update(self, x: np.ndarray, grad_W1: np.ndarray, grad_b1: np.ndarray,
               grad_W2: np.ndarray, grad_b2: np.ndarray):
        """Update weights using optimizer"""
        self.W1, self.b1 = self.optimizer.update(self.W1, self.b1, grad_W1, grad_b1)
        self.W2, self.b2 = self.optimizer.update(self.W2, self.b2, grad_W2, grad_b2)
        
    def get_weights(self) -> Dict:
        """Get network weights for evolution"""
        return {
            'W1': self.W1.copy(),
            'b1': self.b1.copy(),
            'W2': self.W2.copy(),
            'b2': self.b2.copy()
        }
    
    def set_weights(self, weights: Dict):
        """Set network weights"""
        self.W1 = weights['W1'].copy()
        self.b1 = weights['b1'].copy()
        self.W2 = weights['W2'].copy()
        self.b2 = weights['b2'].copy()

class AdamOptimizer:
    """Adam optimizer for neural network training"""
    def __init__(self, learning_rate: float = 0.001, beta1: float = 0.9, beta2: float = 0.999, epsilon: float = 1e-8):
        self.lr = learning_rate
        self.beta1 = beta1
        self.beta2 = beta2
        self.epsilon = epsilon
        self.t = 0
        self.m_W = {}
        self.v_W = {}
        
    def update(self, W: np.ndarray, b: np.ndarray, grad_W: np.ndarray, grad_b: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Update parameters using Adam"""
        self.t += 1
        
        # Update for W
        if id(W) not in self.m_W:
            self.m_W[id(W)] = np.zeros_like(W)
            self.v_W[id(W)] = np.zeros_like(W)
            
        self.m_W[id(W)] = self.beta1 * self.m_W[id(W)] + (1 - self.beta1) * grad_W
        self.v_W[id(W)] = self.beta2 * self.v_W[id(W)] + (1 - self.beta2) * (grad_W ** 2)
        
        m_hat_W = self.m_W[id(W)] / (1 - self.beta1 ** self.t)
        v_hat_W = self.v_W[id(W)] / (1 - self.beta2 ** self.t)
        
        W_new = W - self.lr * m_hat_W / (np.sqrt(v_hat_W) + self.epsilon)
        
        # Update for b
        if id(b) not in self.m_W:
            self.m_W[id(b)] = np.zeros_like(b)
            self.v_W[id(b)] = np.zeros_like(b)
            
        self.m_W[id(b)] = self.beta1 * self.m_W[id(b)] + (1 - self.beta1) * grad_b
        self.v_W[id(b)] = self.beta2 * self.v_W[id(b)] + (1 - self.beta2) * (grad_b ** 2)
        
        m_hat_b = self.m_W[id(b)] / (1 - self.beta1 ** self.t)
        v_hat_b = self.v_W[id(b)] / (1 - self.beta2 ** self.t)
        
        b_new = b - self.lr * m_hat_b / (np.sqrt(v_hat_b) + self.epsilon)
        
        return W_new, b_new

# ============================================================================
# Neural Action Predictor
# ============================================================================

class NeuralActionPredictor:
    """Uses neural network to predict best actions"""
    def __init__(self, input_dim: int = 128, hidden_dim: int = 64, output_dim: int = 30):
        self.network = NeuralNetwork(input_dim, hidden_dim, output_dim)
        self.training = True
        self.experience_replay = deque(maxlen=1000)
        self.batch_size = 32
        self.gamma = 0.9
        
    def predict(self, state_vector: np.ndarray) -> np.ndarray:
        """Forward pass through the network"""
        return self.network.forward(state_vector)
    
    def learn(self, state_vector: np.ndarray, action_idx: int, reward: float,
              next_state_vector: np.ndarray, next_action_idx: int):
        """Store experience and learn from it"""
        # Store experience
        experience = (state_vector, action_idx, reward, next_state_vector, next_action_idx)
        self.experience_replay.append(experience)
        
        # Learn from batch if enough experiences
        if len(self.experience_replay) >= self.batch_size:
            self._learn_from_batch()
            
    def _learn_from_batch(self):
        """Learn from a batch of experiences"""
        # Sample batch
        batch = random.sample(list(self.experience_replay), self.batch_size)
        
        for state, action_idx, reward, next_state, next_action_idx in batch:
            # Forward pass
            current_q = self.network.forward(state)[action_idx]
            
            # Target Q value
            next_q = self.network.forward(next_state)
            max_next_q = np.max(next_q)
            target_q = reward + self.gamma * max_next_q
            
            # TD error
            td_error = target_q - current_q
            
            # Compute gradients
            grad_output = np.zeros(self.network.output_dim)
            grad_output[action_idx] = td_error
            
            # Backward pass
            grad_W1, grad_b1, grad_W2, grad_b2 = self.network.backward(state, grad_output)
            
            # Update weights
            self.network.update(state, grad_W1, grad_b1, grad_W2, grad_b2)
            
    def get_weights(self) -> Dict:
        """Get network weights for evolution"""
        return self.network.get_weights()
    
    def set_weights(self, weights: Dict):
        """Set network weights"""
        self.network.set_weights(weights)

# ============================================================================
# Evolutionary Strategy for Exploration
# ============================================================================

class EvolutionaryExplorer:
    """Uses evolutionary algorithms for exploration"""
    def __init__(self, population_size: int = 5, network_input_dim: int = 128):
        self.population_size = population_size
        self.network_input_dim = network_input_dim
        self.population = []
        self.fitness_history = []
        self.mutation_rate = 0.15
        self.generation = 0
        self.best_fitness = -float('inf')
        
    def create_agent(self) -> Dict:
        """Create a new agent with random weights"""
        return {
            'weights': {
                'W1': np.random.randn(self.network_input_dim, 64) * np.sqrt(2.0 / self.network_input_dim),
                'b1': np.zeros(64),
                'W2': np.random.randn(64, 30) * np.sqrt(2.0 / 64),
                'b2': np.zeros(30)
            },
            'fitness': 0,
            'actions_taken': [],
            'states_visited': set(),
            'reward_sum': 0,
            'success_count': 0,
            'exploration_rate': random.uniform(0.2, 0.8),
            'temperature': random.uniform(0.5, 2.0)
        }
    
    def initialize_population(self):
        """Initialize population with different exploration strategies"""
        strategies = ['greedy', 'exploratory', 'balanced', 'cautious', 'random']
        
        for i in range(self.population_size):
            agent = self.create_agent()
            agent['strategy'] = strategies[i % len(strategies)]
            # Different temperature for exploration
            agent['temperature'] = random.uniform(0.3, 2.0)
            self.population.append(agent)
            
        print(f"🧬 Initialized population of {self.population_size} agents")
    
    def evaluate_agent(self, agent_idx: int, reward: float, success: bool):
        """Evaluate an agent's performance"""
        agent = self.population[agent_idx]
        agent['reward_sum'] += reward
        agent['fitness'] += reward
        if success:
            agent['success_count'] += 1
            
    def select_best_agent(self) -> Dict:
        """Select the best agent from population"""
        return max(self.population, key=lambda x: x['fitness'])
    
    def evolve(self):
        """Evolve population to next generation"""
        self.generation += 1
        
        # Sort by fitness
        self.population.sort(key=lambda x: x['fitness'], reverse=True)
        
        # Update best fitness
        if self.population[0]['fitness'] > self.best_fitness:
            self.best_fitness = self.population[0]['fitness']
        
        # Keep top 2
        survivors = self.population[:2]
        
        # Create offspring from top agents
        while len(survivors) < self.population_size:
            # Select parents
            parent1 = self.population[random.randint(0, min(2, len(self.population)-1))]
            parent2 = self.population[random.randint(0, min(2, len(self.population)-1))]
            
            # Crossover
            child_weights = {}
            for key in parent1['weights'].keys():
                # Uniform crossover
                mask = np.random.rand(*parent1['weights'][key].shape) > 0.5
                child_weights[key] = np.where(mask, parent1['weights'][key], parent2['weights'][key])
            
            # Mutation
            if random.random() < self.mutation_rate:
                for key in child_weights.keys():
                    noise = np.random.randn(*child_weights[key].shape) * 0.05
                    child_weights[key] += noise
            
            # Create child
            child = {
                'weights': child_weights,
                'fitness': 0,
                'actions_taken': [],
                'states_visited': set(),
                'reward_sum': 0,
                'success_count': 0,
                'strategy': random.choice(['greedy', 'exploratory', 'balanced']),
                'exploration_rate': random.uniform(0.2, 0.8),
                'temperature': random.uniform(0.3, 2.0)
            }
            
            survivors.append(child)
        
        self.population = survivors
        self._log_generation()
    
    def _log_generation(self):
        """Log evolution progress"""
        best_fitness = self.population[0]['fitness']
        avg_fitness = sum(a['fitness'] for a in self.population) / len(self.population)
        
        print(f"\n🧬 Generation {self.generation}:")
        print(f"   Best Fitness: {best_fitness:.2f}")
        print(f"   Avg Fitness: {avg_fitness:.2f}")
        print(f"   Best Strategy: {self.population[0]['strategy']}")
        
    def get_best_weights(self) -> Dict:
        """Get weights of the best agent"""
        best_agent = self.select_best_agent()
        return best_agent['weights']
    
    def mutate_weights(self, weights: Dict, mutation_strength: float = 0.1) -> Dict:
        """Mutate weights with given strength"""
        mutated = {}
        for key in weights.keys():
            noise = np.random.randn(*weights[key].shape) * mutation_strength
            mutated[key] = weights[key] + noise
        return mutated

# ============================================================================
# Contextual Multi-Armed Bandit
# ============================================================================

class ContextualBandit:
    """Context-aware action selection"""
    def __init__(self):
        self.contexts = ['login', 'search_results', 'listing', 'form', 'content', 'generic']
        self.context_weights = defaultdict(lambda: defaultdict(float))
        self.context_visits = defaultdict(lambda: defaultdict(int))
        self.context_successes = defaultdict(lambda: defaultdict(int))
        self.epsilon = 0.1
        
    def choose_action(self, context: str, actions: List[Dict]) -> Optional[Dict]:
        """Choose action based on context"""
        if context not in self.contexts:
            context = 'generic'
            
        if not actions:
            return None
            
        # Exploration
        if random.random() < self.epsilon:
            return random.choice(actions)
            
        # Score each action for this context
        action_scores = []
        for action in actions:
            action_key = self._get_action_key(action)
            
            # Base weight for this context
            base_weight = self.context_weights[context].get(action_key, 0.5)
            
            # UCB for exploration
            visits = self.context_visits[context].get(action_key, 0)
            if visits > 0:
                total_visits = sum(self.context_visits[context].values()) + 1
                ucb = math.sqrt(2 * math.log(total_visits) / visits)
            else:
                ucb = 3.0
                
            # Success rate bonus
            successes = self.context_successes[context].get(action_key, 0)
            success_rate = successes / (visits + 1)
            success_bonus = 2.0 * success_rate
            
            # Priority bonus
            priority_bonus = 1.5 if action.get('priority') == 'high' else 0.0
            
            # Context-specific bonuses
            context_bonus = self._get_context_bonus(context, action)
            
            score = base_weight + ucb + success_bonus + priority_bonus + context_bonus
            action_scores.append((score, action))
            
        # Choose best action
        action_scores.sort(key=lambda x: x[0], reverse=True)
        return action_scores[0][1] if action_scores else None
    
    def update(self, context: str, action: Dict, reward: float, success: bool):
        """Update context weights based on reward"""
        if context not in self.contexts:
            context = 'generic'
            
        action_key = self._get_action_key(action)
        
        # Update weight
        current = self.context_weights[context][action_key]
        self.context_weights[context][action_key] = current + 0.1 * (reward - current)
        self.context_visits[context][action_key] += 1
        
        if success:
            self.context_successes[context][action_key] += 1
            
        # Normalize weights for this context
        total = sum(self.context_weights[context].values()) + 0.01
        for key in self.context_weights[context]:
            self.context_weights[context][key] /= total
            
        # Adjust epsilon
        total_visits = sum(self.context_visits[context].values())
        if total_visits > 50:
            self.epsilon = max(0.05, self.epsilon * 0.99)
    
    def _get_action_key(self, action: Dict) -> str:
        """Get normalized key for action"""
        text = action.get('text', '')[:30]
        semantics = action.get('semantics', 'generic')
        return f"{semantics}|{text}"
    
    def _get_context_bonus(self, context: str, action: Dict) -> float:
        """Get context-specific bonus"""
        text = action.get('text', '').lower()
        
        # Login context
        if context == 'login':
            if any(word in text for word in ['login', 'sign in', 'log in']):
                return 3.0
            if any(word in text for word in ['register', 'sign up']):
                return 1.5
                
        # Search context
        elif context == 'search_results':
            if any(word in text for word in ['next', 'more', 'load']):
                return 2.0
            if any(word in text for word in ['apply', 'view', 'details']):
                return 1.0
                
        # Listing context
        elif context == 'listing':
            if any(word in text for word in ['apply', 'submit']):
                return 3.0
            if any(word in text for word in ['next', 'more', 'load']):
                return 1.5
                
        return 0.0

# ============================================================================
# Pattern Learning & Memory
# ============================================================================

class PatternLearner:
    """Learns patterns in successful sequences"""
    def __init__(self, max_memory: int = 1000):
        self.patterns = defaultdict(list)
        self.sequence_memory = deque(maxlen=max_memory)
        self.successful_sequences = []
        self.pattern_scores = defaultdict(float)
        
    def learn_pattern(self, state: Dict, action: Dict, result: Dict, reward: float):
        """Learn from successful interactions"""
        if result.get('success', False):
            # Record the sequence
            pattern = {
                'state_type': state.get('page_type', 'content'),
                'state_id': state.get('state_id', ''),
                'action_text': action.get('text', '')[:30],
                'action_semantics': action.get('semantics', 'generic'),
                'action_priority': action.get('priority', 'medium'),
                'reward': reward,
                'timestamp': datetime.now().isoformat()
            }
            
            self.sequence_memory.append(pattern)
            
            # Update pattern frequency
            key = f"{pattern['state_type']}|{pattern['action_semantics']}"
            self.patterns[key].append(pattern)
            
            # Update pattern score
            self.pattern_scores[key] = self.pattern_scores.get(key, 0) + reward
            
            # If high reward, add to successful sequences
            if reward > 3.0:
                self.successful_sequences.append(pattern)
                
            # Keep only recent successful sequences
            if len(self.successful_sequences) > 100:
                self.successful_sequences = self.successful_sequences[-100:]
    
    def get_similar_patterns(self, state: Dict, top_k: int = 5) -> List[Dict]:
        """Find patterns similar to current state"""
        state_type = state.get('page_type', 'content')
        state_id = state.get('state_id', '')
        
        similar = []
        
        # Find patterns for this state type
        for key, patterns in self.patterns.items():
            if key.startswith(state_type):
                # Score patterns
                for pattern in patterns:
                    # Calculate similarity score
                    score = 0.0
                    
                    # State ID similarity
                    if pattern.get('state_id') == state_id:
                        score += 2.0
                    
                    # Recency bonus
                    age = (datetime.now() - datetime.fromisoformat(pattern['timestamp'])).seconds
                    if age < 60:  # Less than 1 minute old
                        score += 1.0
                        
                    # Reward bonus
                    score += pattern.get('reward', 0) / 10.0
                    
                    similar.append((score, pattern))
        
        # Sort by score and return top k
        similar.sort(key=lambda x: x[0], reverse=True)
        return [pattern for _, pattern in similar[:top_k]]
    
    def get_best_patterns(self, top_k: int = 10) -> List[Dict]:
        """Get best patterns overall"""
        sorted_patterns = sorted(self.pattern_scores.items(), key=lambda x: x[1], reverse=True)
        result = []
        
        for key, score in sorted_patterns[:top_k]:
            state_type, semantics = key.split('|')
            result.append({
                'state_type': state_type,
                'semantics': semantics,
                'score': score,
                'examples': len(self.patterns.get(key, []))
            })
            
        return result
    
    def get_sequence_stats(self) -> Dict:
        """Get statistics about learned patterns"""
        return {
            'total_patterns': len(self.patterns),
            'total_sequences': len(self.sequence_memory),
            'successful_sequences': len(self.successful_sequences),
            'unique_state_types': len(set(p['state_type'] for p in self.sequence_memory)),
            'unique_actions': len(set(p['action_text'] for p in self.sequence_memory))
        }

# ============================================================================
# Episode Tracker (Enhanced)
# ============================================================================

class EpisodeTracker:
    def __init__(self):
        self.episodes = []
        self.successful_episodes = []
        self.experience_buffer = deque(maxlen=2000)

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

    def add_experience(self, state_vector: np.ndarray, action_idx: int, reward: float,
                      next_state_vector: np.ndarray, done: bool):
        """Add experience for replay buffer"""
        self.experience_buffer.append((state_vector, action_idx, reward, next_state_vector, done))

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
# State Extractor (Enhanced)
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

            // Get interactive elements with more details
            document.querySelectorAll('button, a[href], [role="button"], [role="link"], input[type="submit"], input[type="button"]').forEach(el => {
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
                const aria_role = el.getAttribute('role') || '';
                const aria_label = el.getAttribute('aria-label') || '';

                dom_features.interactive_elements.push({
                    text: el.textContent.trim().substring(0, 100),
                    tag: el.tagName.toLowerCase(),
                    href: el.getAttribute('href') || null,
                    classes: el.className || '',
                    landmark: landmark,
                    depth: (() => { let d=0, n=el; while(n.parentElement){d++; n=n.parentElement;} return d; })(),
                    selector: getStableSelector(el),
                    is_ad: is_ad,
                    aria_label: aria_label,
                    aria_role: aria_role,
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
# Action Preparer (Enhanced)
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

        # Sort by depth and semantic importance
        interactive.sort(key=lambda x: (x.get('depth', 100), len(x.get('text', ''))))

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
            aria_label = el.get('aria_label', '')
            aria_role = el.get('aria_role', '')

            # Enhanced semantics detection
            semantics, priority = self._detect_semantics(text_lower, el)

            # Build robust selector with multiple strategies
            robust_selector = self._build_robust_selector(el)

            action = {
                'type': 'click',
                'text': text,
                'selector': selector,
                'robust_selector': robust_selector,
                'semantics': semantics,
                'priority': priority,
                'landmark': landmark,
                'aria_label': aria_label,
                'aria_role': aria_role,
                'depth': el.get('depth', 0),
                'iife': self._build_robust_iife(el, text, selector, robust_selector)
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
                    'priority': 'medium' if any(w in text.lower() for w in ['profile', 'inbox', 'search']) else 'low',
                    'landmark': 'link',
                    'iife': self._build_navigation_iife(href)
                }
                medium_priority.append(action)

        actions = high_priority + medium_priority + low_priority
        return actions[:30]

    def _build_robust_selector(self, el: Dict) -> str:
        """Build multiple fallback selector strategies"""
        selectors = []
        
        # Strategy 1: ID if available
        if el.get('id'):
            selectors.append(f"#{el.get('id')}")
        
        # Strategy 2: Data attributes
        if el.get('aria_label'):
            selectors.append(f'[aria-label="{el.get("aria_label")}"]')
        if el.get('aria_role'):
            selectors.append(f'[role="{el.get("aria_role")}"]')
        
        # Strategy 3: Class + text matching
        classes = el.get('classes', '').split()
        if classes:
            class_selector = '.' + '.'.join(classes[:2])
            selectors.append(class_selector)
        
        # Strategy 4: Tag + text
        tag = el.get('tag', '')
        text = el.get('text', '').strip()
        if tag and text and len(text) < 30:
            selectors.append(f'{tag}[text*="{text[:20]}"]')
        
        # Strategy 5: Full selector as fallback
        if el.get('selector'):
            selectors.append(el.get('selector'))
        
        return '|'.join(selectors)

    def _build_robust_iife(self, el: Dict, text: str, selector: str, robust_selector: str) -> str:
        """Build a robust IIFE with multiple fallback strategies"""
        selectors_list = robust_selector.split('|')
        
        iife = f"""
        (function() {{
            try {{
                // Strategy 1: Try all selectors
                const selectors = {json.dumps(selectors_list)};
                let el = null;
                
                for (let sel of selectors) {{
                    try {{
                        el = document.querySelector(sel);
                        if (el) break;
                    }} catch(e) {{ continue; }}
                }}
                
                // Strategy 2: Try by text if selector failed
                if (!el) {{
                    const elements = document.querySelectorAll('button, a, [role="button"], [role="link"], input[type="submit"]');
                    const targetText = '{text.replace("'", "\\'")}';
                    
                    for (let elem of elements) {{
                        const elemText = elem.textContent.trim();
                        if (elemText === targetText || 
                            elemText.includes(targetText) || 
                            targetText.includes(elemText)) {{
                            el = elem;
                            break;
                        }}
                    }}
                }}
                
                // Strategy 3: Try by aria-label
                if (!el && '{el.get('aria_label', '')}') {{
                    const label = '{el.get('aria_label', '').replace("'", "\\'")}';
                    el = document.querySelector(`[aria-label="${{label}}"]`);
                }}
                
                if (el) {{
                    el.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                    
                    // Multiple click strategies for SPA compatibility
                    setTimeout(() => {{
                        el.click();
                        // Some SPAs need synthetic click
                        el.dispatchEvent(new MouseEvent('click', {{
                            bubbles: true,
                            cancelable: true,
                            view: window
                        }}));
                    }}, 150);
                    
                    return {{ success: true, method: 'click' }};
                }}
                
                return {{ success: false, error: 'Element not found' }};
            }} catch(e) {{
                return {{ success: false, error: e.message }};
            }}
        }})()
        """
        
        return iife

    def _detect_semantics(self, text_lower: str, el: Dict) -> Tuple[str, str]:
        """Enhanced semantic detection with better priority"""
        # High priority: Critical actions
        if any(word in text_lower for word in [
            'apply now', 'submit application', 'register', 'sign up', 'login', 'sign in',
            'complete profile', 'profile', 'my profile'
        ]):
            return 'critical', 'high'
        
        # Search actions
        if any(word in text_lower for word in ['search', 'find', 'look for', 'explore']):
            return 'search', 'high'
        
        # Navigation to important sections
        if any(word in text_lower for word in ['inbox', 'messages', 'notifications', 'dashboard']):
            return 'navigation_important', 'high'
        
        # Pagination
        if any(word in text_lower for word in ['next', 'more', 'load', 'see all', 'view all', 'show more']):
            return 'pagination', 'medium'
        
        # Save/Bookmark
        if any(word in text_lower for word in ['save', 'bookmark', 'favorite', 'like']):
            return 'save_content', 'medium'
        
        # Generic navigation
        if any(word in text_lower for word in ['home', 'back', 'return', 'go to']):
            return 'navigation', 'medium'
        
        # Check aria roles
        aria_role = el.get('aria_role', '').lower()
        if aria_role in ['button', 'link']:
            return 'interactive', 'medium'
        
        return 'generic', 'medium'

    def _build_navigation_iife(self, href: str) -> str:
        return f"""
        (function() {{
            try {{
                if ('{href}'.startsWith('http')) {{
                    window.location.href = '{href}';
                }} else if ('{href}'.startsWith('/')) {{
                    window.location.href = window.location.origin + '{href}';
                }} else {{
                    window.location.href = window.location.origin + '/' + '{href}';
                }}
                return {{ success: true, url: window.location.href }};
            }} catch(e) {{
                return {{ success: false, error: e.message }};
            }}
        }})()
        """

# ============================================================================
# Action Normalizer & Validator (Enhanced)
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
# Reward Engine (Enhanced with Neural Signals)
# ============================================================================

class RewardEngine:
    def __init__(self):
        self.reward_history = deque(maxlen=100)
        self.action_history = deque(maxlen=30)
        self.page_history = deque(maxlen=10)
        self.success_count = 0
        self.discovered_pages = set()
        self.discovery_rate = 0.0
        self.consecutive_successes = 0

        self.rewards = {
            'new_page': 5.0,
            'new_state': 2.0,
            'new_content': 3.0,
            'pagination': 3.0,
            'form_action': 3.5,
            'success_click': 1.0,
            'goal_achieved': 50.0,
            'novel_discovery': 4.0,
            'pattern_match': 2.0
        }

        self.penalties = {
            'duplicate': -0.3,
            'no_change': -0.1,
            'error': -0.5,
            'wasting_time': -1.0,
            'going_in_circles': -2.0,
            'repeated_failure': -0.5
        }

    def calculate_reward(self,
                         action: Dict,
                         state_before: Dict,
                         state_after: Dict,
                         success: bool,
                         cycle: int,
                         pattern_match: bool = False) -> float:

        reward = 0.0

        if success:
            reward += self.rewards['success_click']
            self.consecutive_successes += 1
        else:
            self.consecutive_successes = 0

        # Page change
        url_before = state_before.get('page', {}).get('url', '')
        url_after = state_after.get('page', {}).get('url', '')
        if url_before and url_after and url_before != url_after:
            # Novel page discovery
            if url_after not in self.discovered_pages:
                reward += self.rewards['novel_discovery']
                self.discovered_pages.add(url_after)
                print(f"   🌐 +{self.rewards['novel_discovery']}: Novel discovery!")
            else:
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

        # Pattern matching bonus
        if pattern_match:
            reward += self.rewards['pattern_match']
            print(f"   🧩 +{self.rewards['pattern_match']}: Pattern matched!")

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

        # Consecutive failures penalty
        if not success and self.consecutive_successes < 0:
            reward += self.penalties['repeated_failure']
            print(f"   ⚠️ Penalty: {self.penalties['repeated_failure']:.1f} (repeated failure)")

        self.action_history.append(action_key)
        self.reward_history.append(reward)

        # Update discovery rate
        self.discovery_rate = len(self.discovered_pages) / max(1, len(self.page_history))

        return max(-10.0, min(60.0, reward))

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
            'registration complete',
            'profile completed',
            'welcome to'
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
    
    def get_discovery_rate(self) -> float:
        return self.discovery_rate

# ============================================================================
# Main Neural RL Agent
# ============================================================================

class NeuralReinforcementLearningAgent:
    def __init__(self, port: int = 9257, max_cycles: int = 50):
        self.port = port
        self.max_cycles = max_cycles
        
        self.session_dir = Path(f"neural_rl_agent_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        self.session_dir.mkdir(parents=True, exist_ok=True)
        
        # Core components
        self.cdp = CDPWrapper(port)
        self.state_extractor = StateExtractor(self.cdp)
        
        # Neural components
        self.state_encoder = NeuralStateEncoder(embedding_dim=128)
        self.action_predictor = NeuralActionPredictor(input_dim=128, hidden_dim=64, output_dim=30)
        self.evolutionary_explorer = EvolutionaryExplorer(population_size=5, network_input_dim=128)
        self.contextual_bandit = ContextualBandit()
        self.pattern_learner = PatternLearner()
        self.reward_engine = RewardEngine()
        
        # Initialize population
        self.evolutionary_explorer.initialize_population()
        self.current_agent_idx = 0
        
        # Training state
        self.episode_history = []
        self.current_state = None
        self.cycle = 0
        self.no_action_count = 0
        self.goal_achieved = False
        self.best_reward = -float('inf')
        self.no_progress_count = 0
        self.visited_states = set()
        self.episode_tracker = EpisodeTracker()
        
        print("=" * 70)
        print("🧠 NEURAL WEB RL AGENT - Enhanced with Deep Learning")
        print("=" * 70)
        print("Features:")
        print("  ✅ Neural Perception Layer (DOM to vector encoding)")
        print("  ✅ Hidden Layer Abstraction (deep Q-learning)")
        print("  ✅ Evolutionary Strategy for Exploration")
        print("  ✅ Contextual Multi-Armed Bandit")
        print("  ✅ Pattern Learning & Memory")
        print("  ✅ Works on ANY website")
        print("  ✅ Adaptive exploration")
        print("=" * 70)
        print(f"Max Cycles: {max_cycles}")
        print(f"Session: {self.session_dir}\n")

    def connect(self) -> bool:
        return self.cdp.connect()

    def run(self):
        print("🧠 Starting Neural Web RL Agent...\n")

        self.current_state = self.state_extractor.extract()
        state_id = self.current_state.get('state_id')
        self.visited_states.add(state_id)

        print(f"📍 Starting on: {self.current_state.get('page', {}).get('url', 'unknown')}")
        print(f"📊 Initial state: {state_id}")
        print(f"🧬 Population size: {self.evolutionary_explorer.population_size}")

        for self.cycle in range(1, self.max_cycles + 1):
            print(f"\n{'='*70}")
            print(f"🔄 CYCLE {self.cycle}/{self.max_cycles}")
            print(f"{'='*70}")

            try:
                page = self.current_state.get('page', {})
                print(f"📍 {page.get('url', 'unknown')[:80]}")
                print(f"📊 State: {state_id}")
                print(f"🏷️  Type: {self._get_page_type_emoji(self.current_state)}")
                print(f"🧬 Agent: {self.current_agent_idx + 1}/{self.evolutionary_explorer.population_size}")

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

                # Neural encoding of current state
                state_vector = self.state_encoder.encode(self.current_state)
                
                # Get context for bandit
                context = self.current_state.get('page_type', 'content')
                
                # Action selection with neural prediction
                action_scores = self.action_predictor.predict(state_vector)
                
                # Scale to action count
                if len(action_scores) < len(actions):
                    action_scores = np.pad(action_scores, (0, len(actions) - len(action_scores)))
                else:
                    action_scores = action_scores[:len(actions)]
                
                # Contextual bandit influence
                bandit_action = self.contextual_bandit.choose_action(context, actions)
                if bandit_action:
                    bandit_idx = actions.index(bandit_action) if bandit_action in actions else 0
                    action_scores[bandit_idx] += 2.0
                
                # Pattern learning influence
                similar_patterns = self.pattern_learner.get_similar_patterns(self.current_state)
                if similar_patterns:
                    pattern_texts = [p['action_text'] for p in similar_patterns[:3]]
                    for i, action in enumerate(actions):
                        if action.get('text', '')[:30] in pattern_texts:
                            action_scores[i] += 1.5
                            print(f"   🧩 Pattern match: '{action.get('text', '')[:30]}'")
                
                # Choose action with exploration
                if random.random() < 0.3:  # Exploration
                    top_indices = np.argsort(action_scores)[-5:]
                    action_idx = random.choice(top_indices) if len(top_indices) > 0 else 0
                    chosen_action = actions[action_idx]
                else:
                    action_idx = np.argmax(action_scores) if len(action_scores) > 0 else 0
                    chosen_action = actions[action_idx] if action_idx < len(actions) else actions[0]

                norm = ActionNormalizer.normalize(chosen_action)
                print(f"\n🎯 Chosen: {norm['type']} - '{norm['text']}' [{norm['semantics']}]")
                if chosen_action.get('selector'):
                    print(f"   📍 Selector: {chosen_action['selector'][:60]}")
                print(f"   🧠 Neural Score: {action_scores[action_idx]:.3f}")

                # Execute
                success = False
                iife = chosen_action.get('iife')
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
                new_state_vector = self.state_encoder.encode(new_state)

                # Track visited states
                if new_state_id not in self.visited_states:
                    self.visited_states.add(new_state_id)
                    print(f"   🆕 New state discovered!")

                # Pattern learning
                self.pattern_learner.learn_pattern(
                    self.current_state, chosen_action,
                    {'success': success, 'next_state': new_state_id},
                    self.reward_engine.rewards['success_click'] if success else 0
                )

                # Calculate reward
                reward = self.reward_engine.calculate_reward(
                    chosen_action, self.current_state, new_state, 
                    success, self.cycle, 
                    pattern_match=bool(similar_patterns)
                )

                # Track progress
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

                # Neural learning (backpropagation)
                next_action_scores = self.action_predictor.predict(new_state_vector)
                next_action_idx = np.argmax(next_action_scores) if len(next_action_scores) > 0 else 0
                
                self.action_predictor.learn(
                    state_vector, action_idx, reward,
                    new_state_vector, next_action_idx
                )

                # Update contextual bandit
                self.contextual_bandit.update(context, chosen_action, reward, success)

                # Update evolutionary population
                self.evolutionary_explorer.evaluate_agent(self.current_agent_idx, reward, success)
                
                # Rotate through population
                self.current_agent_idx = (self.current_agent_idx + 1) % self.evolutionary_explorer.population_size
                
                # Evolve periodically
                if self.cycle % 10 == 0:
                    self.evolutionary_explorer.evolve()
                    # Apply best weights to main network
                    best_weights = self.evolutionary_explorer.get_best_weights()
                    self.action_predictor.set_weights(best_weights)

                # Episode tracking
                self.episode_tracker.add_episode(
                    self.cycle, norm['normalized_key'], reward, state_id, new_state_id
                )

                # Record
                self.episode_history.append({
                    'cycle': self.cycle,
                    'action': norm['normalized_key'],
                    'success': success,
                    'reward': reward,
                    'state': state_id,
                    'next_state': new_state_id,
                    'url': new_state.get('page', {}).get('url', ''),
                    'neural_score': float(action_scores[action_idx]) if len(action_scores) > 0 else 0,
                    'agent_idx': self.current_agent_idx
                })

                print(f"\n📊 Results:")
                print(f"   Success: {'✅' if success else '❌'}")
                print(f"   Reward: {reward:.2f}")
                print(f"   Unique States: {len(self.visited_states)}")
                print(f"   Pattern Memory: {len(self.pattern_learner.sequence_memory)}")
                print(f"   Discovery Rate: {self.reward_engine.get_discovery_rate():.2%}")
                print(f"   Best Reward: {self.best_reward:.2f}")

                best_path = self.episode_tracker.get_best_path()
                if best_path:
                    path_str = ' → '.join(best_path['actions'][-3:])
                    print(f"   🏆 Best Path: {path_str} (reward: {best_path['reward']:.2f})")

                # Update state
                self.current_state = new_state
                state_id = new_state_id

                if self.cycle % 10 == 0:
                    self.save_state()

                # Check goal achievement
                if reward > 40.0:
                    self.goal_achieved = True
                    print("\n🎉🎉🎉 GOAL ACHIEVED! 🎉🎉🎉")
                    break

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
            'episodes': len(self.episode_history),
            'best_path': self.episode_tracker.get_best_path(),
            'success_count': self.reward_engine.success_count,
            'unique_states': len(self.visited_states),
            'discovery_rate': self.reward_engine.get_discovery_rate(),
            'pattern_stats': self.pattern_learner.get_sequence_stats(),
            'evolution_generation': self.evolutionary_explorer.generation,
            'timestamp': datetime.now().isoformat()
        }
        with open(self.session_dir / "agent_state.json", 'w') as f:
            json.dump(state, f, indent=2, default=str)
        print(f"\n💾 State saved to {self.session_dir}")

    def generate_report(self):
        report = []
        report.append("=" * 80)
        report.append("🧠 NEURAL WEB RL AGENT - FINAL REPORT")
        report.append("=" * 80)
        report.append(f"Total Cycles: {self.cycle}")
        report.append(f"Goal Achieved: {'✅ YES!' if self.goal_achieved else '🔄 Still learning'}")
        report.append(f"Best Reward: {self.best_reward:.2f}")
        report.append(f"Success Events: {self.reward_engine.success_count}")
        report.append(f"States Discovered: {len(self.visited_states)}")
        report.append(f"Discovery Rate: {self.reward_engine.get_discovery_rate():.2%}")
        report.append("")

        # Pattern learning stats
        pattern_stats = self.pattern_learner.get_sequence_stats()
        report.append("🧩 PATTERN LEARNING STATS:")
        report.append(f"  Total Patterns: {pattern_stats['total_patterns']}")
        report.append(f"  Total Sequences: {pattern_stats['total_sequences']}")
        report.append(f"  Successful Sequences: {pattern_stats['successful_sequences']}")
        report.append(f"  Unique State Types: {pattern_stats['unique_state_types']}")
        report.append(f"  Unique Actions: {pattern_stats['unique_actions']}")
        report.append("")

        # Best patterns
        best_patterns = self.pattern_learner.get_best_patterns(5)
        if best_patterns:
            report.append("🏆 BEST PATTERNS:")
            for pattern in best_patterns:
                report.append(f"  {pattern['state_type']} → {pattern['semantics']}: {pattern['score']:.2f} (n={pattern['examples']})")
            report.append("")

        # Evolution stats
        report.append("🧬 EVOLUTION STATS:")
        report.append(f"  Generation: {self.evolutionary_explorer.generation}")
        report.append(f"  Population Size: {self.evolutionary_explorer.population_size}")
        if self.evolutionary_explorer.population:
            best_fitness = self.evolutionary_explorer.population[0]['fitness']
            report.append(f"  Best Fitness: {best_fitness:.2f}")
        report.append("")

        # Contextual bandit stats
        report.append("🎯 CONTEXTUAL BANDIT STATS:")
        report.append(f"  Contexts: {', '.join(self.contextual_bandit.contexts)}")
        report.append(f"  Epsilon: {self.contextual_bandit.epsilon:.3f}")
        report.append("")

        # Episode stats
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

            # Action distribution
            action_counts = defaultdict(int)
            for ep in self.episode_history:
                action_counts[ep['action']] += 1
            report.append(f"\n📋 Action Distribution:")
            for action, count in sorted(action_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
                report.append(f"  {action}: {count} times")

        # Visited pages
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
    print("🧠 NEURAL WEB RL AGENT")
    print("=" * 70)
    print("Enhanced with Deep Learning Principles:")
    print("  - Neural Perception Layer")
    print("  - Hidden Layer Abstraction")
    print("  - Evolutionary Strategy")
    print("  - Contextual Multi-Armed Bandit")
    print("  - Pattern Learning & Memory")
    print("=" * 70)

    port_input = input("🔌 Chrome port (default 9257): ").strip()
    port = int(port_input) if port_input else 9257

    cycles_input = input("📊 Max cycles (default 50): ").strip()
    max_cycles = int(cycles_input) if cycles_input else 50

    agent = NeuralReinforcementLearningAgent(port=port, max_cycles=max_cycles)

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
