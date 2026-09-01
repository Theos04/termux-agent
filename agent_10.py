#!/usr/bin/env python3
"""
AGI MATH SYSTEM - FIXED INTEGRATION
Properly implements DOMExplorer.extract_hierarchy()
Validates all perception data before embedding
Fixes repetition penalty tracking
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
# CONFIGURATION
# ============================================================================

AGI_CONFIG = {
    "action_delay": 8.0,  # Reduced for faster cycles
    "perception_delay": 10.0,
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
# 1. FIXED DOM EXPLORER - With extract_hierarchy method
# ============================================================================

class FixedDOMExplorer:
    """
    Extended DOMExplorer with extract_hierarchy method
    Properly builds the hierarchical DOM tree
    """
    
    def __init__(self, page):
        self.page = page
        self.visited = set()
        self.links_map: Dict[str, List[Dict]] = {}
        
    def extract_hierarchy(self, max_depth: int = 10) -> Dict:
        """
        Extract DOM hierarchy as structured tree
        This is the method the orchestrator expects
        """
        script = f"""
        (function() {{
            function buildTree(node, depth) {{
                if (depth > {max_depth}) return null;
                if (!node || node.nodeType !== 1) return null;
                
                const rect = node.getBoundingClientRect();
                const style = window.getComputedStyle(node);
                
                const children = [];
                const childNodes = node.children;
                for (let i = 0; i < Math.min(childNodes.length, 20); i++) {{
                    const child = buildTree(childNodes[i], depth + 1);
                    if (child) children.push(child);
                }}
                
                return {{
                    tag: node.tagName.toLowerCase(),
                    id: node.id || '',
                    classes: node.className || '',
                    text: (node.textContent || '').trim().slice(0, 200),
                    depth: depth,
                    visible: rect.width > 0 && rect.height > 0,
                    position: {{
                        x: rect.x || 0,
                        y: rect.y || 0,
                        width: rect.width || 0,
                        height: rect.height || 0
                    }},
                    style: {{
                        display: style.display || 'block',
                        visibility: style.visibility || 'visible',
                        opacity: parseFloat(style.opacity) || 1.0,
                        zIndex: parseInt(style.zIndex) || 0
                    }},
                    children: children,
                    child_count: children.length
                }};
            }}
            
            return {{
                root: document.body ? buildTree(document.body, 0) : null,
                total_elements: document.querySelectorAll('*').length,
                timestamp: Date.now()
            }};
        }})()
        """
        
        try:
            result = self.page.js(script)
            if result:
                return result
        except Exception as e:
            print(f"⚠️ Hierarchy extraction error: {e}")
            
        return {'root': None, 'total_elements': 0}
        
    def get_all_urls(self) -> List[str]:
        """Get all URLs from the page"""
        links = self.page.get_all_links()
        urls = []
        for link in links:
            href = link.get('href', '')
            if href and not href.startswith('#') and not href.startswith('javascript:'):
                if href.startswith('/') or href.startswith('./') or href.startswith('../'):
                    from urllib.parse import urljoin
                    full_url = urljoin(self.page.page_url, href)
                    urls.append(full_url)
                elif href.startswith(('http://', 'https://')):
                    urls.append(href)
        return list(set(urls))
        
    def map_links(self) -> Dict:
        """Map all links on the page"""
        links = self.page.get_all_links()
        internal = []
        external = []
        anchor = []
        
        for link in links:
            href = link.get('href', '')
            if href.startswith('#'):
                anchor.append(link)
            elif href.startswith(('http://', 'https://')):
                if self.page.base_domain in href:
                    internal.append(link)
                else:
                    external.append(link)
            elif href.startswith('/') or href.startswith('./') or href.startswith('../'):
                from urllib.parse import urljoin
                link['href'] = urljoin(self.page.page_url, href)
                internal.append(link)
                
        return {
            'internal_links': internal,
            'external_links': external,
            'anchor_links': anchor,
            'total_links': len(links)
        }
        
    def get_competitor_analysis(self) -> Dict:
        """Analyze page for competitor content"""
        competitor_keywords = ['competitor', 'alternative', 'vs', 'compare', 'similar', 'rival']
        text = self.page.get_text().lower()
        
        found_keywords = [kw for kw in competitor_keywords if kw in text]
        links = self.page.get_all_links()
        competitor_links = [l for l in links if any(kw in l.get('text', '').lower() for kw in competitor_keywords)]
        
        return {
            'competitor_keywords_found': found_keywords,
            'competitor_links': competitor_links,
            'total_competitor_links': len(competitor_links)
        }
        
    def explore_page_structure(self) -> Dict:
        """Analyze page structure"""
        structure = {
            'headers': self.page.find_elements_by_selector('h1, h2, h3'),
            'navigation': self.page.find_elements_by_selector('nav, header nav, .nav'),
            'forms': self.page.find_elements_by_selector('form'),
            'buttons': self.page.find_elements_by_selector('button, [role="button"]')
        }
        return structure

# ============================================================================
# 2. FIXED CDP WRAPPER - Uses FixedDOMExplorer
# ============================================================================

class FixedCDPWrapper:
    """
    CDP wrapper that properly integrates FixedDOMExplorer
    """
    
    def __init__(self, port: int = 9260):
        self.port = port
        self.page = None
        self.explorer = None
        self.connected = False
        
    def connect(self) -> bool:
        """Connect using ChromePage"""
        try:
            from geturl import ChromePage
            self.page = ChromePage(port=self.port)
            if self.page.connect():
                self.connected = True
                self.explorer = FixedDOMExplorer(self.page)
                print(f"🔍 Connected to: {self.page.get_title()}")
                print(f"📍 {self.page.page_url}")
                return True
        except Exception as e:
            print(f"⚠️ Connect error: {e}")
            
        # Fallback
        try:
            from dynamic_cdp_6 import EnhancedChromeCDP
            self.client = EnhancedChromeCDP(port=self.port)
            tabs = self.client.get_tabs()
            if tabs:
                self.connected = True
                print(f"🔍 Connected to {len(tabs)} tabs (fallback)")
                return True
        except:
            pass
            
        return False
        
    def get_perception_data(self) -> Dict:
        """Get perception data with validated hierarchy"""
        if not self.connected or not self.explorer:
            return self._get_fallback_perception()
            
        try:
            # Get hierarchy (now works!)
            hierarchy = self.explorer.extract_hierarchy()
            
            # Get other data
            link_map = self.explorer.map_links()
            competitor = self.explorer.get_competitor_analysis()
            structure = self.explorer.explore_page_structure()
            clickable = self.page.get_clickable_elements()
            
            # Build validated perception data
            return {
                'url': self.page.page_url,
                'title': self.page.get_title(),
                'text': self.page.get_text(),
                'hierarchy': hierarchy,
                'interactives': clickable[:50],
                'link_map': link_map,
                'competitor': competitor,
                'structure': structure,
                'total_elements': hierarchy.get('total_elements', 0),
                'timestamp': time.time()
            }
            
        except Exception as e:
            print(f"⚠️ Perception error: {e}")
            return self._get_fallback_perception()
            
    def _get_fallback_perception(self) -> Dict:
        """Fallback perception"""
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
            
        return {'url': '', 'title': '', 'interactives': [], 'total_elements': 0}
        
    def execute_action(self, action: Dict) -> Dict:
        """Execute action with proper validation"""
        text = action.get('text', '')
        if not text or text == '[No text]':
            return {'success': False, 'error': 'No valid text'}
            
        try:
            # Try clicking by text
            success = self.page.click_by_text(text)
            if success:
                return {'success': True, 'method': 'text'}
                
            # Try by selector
            selector = action.get('selector', '')
            if selector:
                success = self.page.click_element(selector)
                if success:
                    return {'success': True, 'method': 'selector'}
                    
            return {'success': False, 'error': 'Could not click'}
            
        except Exception as e:
            return {'success': False, 'error': str(e)}

# ============================================================================
# 3. FIXED MATHEMATICAL EMBEDDING - Validates data
# ============================================================================

class FixedMathematicalEmbedding:
    """
    Mathematical embedding with proper None validation
    """
    
    def __init__(self, embedding_dim: int = 128):
        self.embedding_dim = embedding_dim
        
        self.W_hierarchy = np.random.randn(256, embedding_dim) * np.sqrt(2.0 / 256)
        self.W_interactive = np.random.randn(128, embedding_dim) * np.sqrt(2.0 / 128)
        self.W_structure = np.random.randn(64, embedding_dim) * np.sqrt(2.0 / 64)
        
        self.b_hierarchy = np.zeros(embedding_dim)
        self.b_interactive = np.zeros(embedding_dim)
        self.b_structure = np.zeros(embedding_dim)
        
    def encode(self, perception_data: Dict) -> np.ndarray:
        """Encode with proper None validation"""
        try:
            # Validate and extract features with safe defaults
            hierarchy_features = self._extract_hierarchy_features(perception_data)
            interactive_features = self._extract_interactive_features(perception_data)
            structure_features = self._extract_structure_features(perception_data)
            
            # Embed
            hierarchy_embed = np.dot(hierarchy_features, self.W_hierarchy) + self.b_hierarchy
            interactive_embed = np.dot(interactive_features, self.W_interactive) + self.b_interactive
            structure_embed = np.dot(structure_features, self.W_structure) + self.b_structure
            
            # Combine
            combined = hierarchy_embed + interactive_embed + structure_embed
            
            norm = np.linalg.norm(combined)
            if norm > 0:
                combined = combined / norm
                
            return combined
            
        except Exception as e:
            print(f"⚠️ Embedding error: {e}")
            return np.random.randn(self.embedding_dim) * 0.01
            
    def _extract_hierarchy_features(self, data: Dict) -> np.ndarray:
        """Extract hierarchy features safely"""
        features = []
        
        hierarchy = data.get('hierarchy', {})
        root = hierarchy.get('root', {})
        total = hierarchy.get('total_elements', 0)
        
        # Safely extract depth counts
        depth_counts = defaultdict(int)
        
        def count_depth(node, depth):
            if not node:
                return
            depth_counts[depth] += 1
            for child in node.get('children', []):
                count_depth(child, depth + 1)
        
        if root:
            count_depth(root, 0)
            
        # Flatten depth features
        for d in range(10):
            features.append(depth_counts.get(d, 0) / max(1, total))
            
        # Tag counts
        tag_counts = defaultdict(int)
        
        def count_tags(node):
            if not node:
                return
            tag = node.get('tag', '')
            if tag:
                tag_counts[tag] += 1
            for child in node.get('children', []):
                count_tags(child)
                
        if root:
            count_tags(root)
            
        for tag in ['div', 'section', 'article', 'main', 'nav', 'header', 'footer', 'form']:
            features.append(tag_counts.get(tag, 0) / max(1, total))
            
        while len(features) < 256:
            features.append(0.0)
            
        return np.array(features[:256], dtype=np.float32)
        
    def _extract_interactive_features(self, data: Dict) -> np.ndarray:
        """Extract interactive features safely"""
        features = []
        interactives = data.get('interactives', [])
        
        total = max(1, len(interactives))
        
        # Count by tag
        tag_counts = defaultdict(int)
        visible_count = 0
        decisive_count = 0
        
        for el in interactives:
            tag = el.get('tag', '')
            if tag:
                tag_counts[tag] += 1
            if el.get('visible', False):
                visible_count += 1
                
            text = el.get('text', '').lower()
            if any(kw in text for kw in ['apply', 'submit', 'register', 'login', 'search', 'profile', 'job']):
                decisive_count += 1
                
        features.extend([
            tag_counts.get('button', 0) / total,
            tag_counts.get('a', 0) / total,
            tag_counts.get('input', 0) / total,
            visible_count / total,
            decisive_count / total,
            min(1.0, total / 30)
        ])
        
        while len(features) < 128:
            features.append(0.0)
            
        return np.array(features[:128], dtype=np.float32)
        
    def _extract_structure_features(self, data: Dict) -> np.ndarray:
        """Extract structure features safely"""
        features = []
        structure = data.get('structure', {})
        
        for key in ['headers', 'navigation', 'forms', 'buttons']:
            elements = structure.get(key, [])
            features.append(min(1.0, len(elements) / 10))
            
        link_map = data.get('link_map', {})
        features.append(min(1.0, link_map.get('total_links', 0) / 100))
        
        competitor = data.get('competitor', {})
        features.append(min(1.0, competitor.get('total_competitor_links', 0) / 20))
        features.append(min(1.0, len(competitor.get('competitor_keywords_found', [])) / 10))
        
        while len(features) < 64:
            features.append(0.0)
            
        return np.array(features[:64], dtype=np.float32)

# ============================================================================
# 4. JEPA WORLD MODEL (unchanged)
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
        self.prediction_errors = deque(maxlen=100)
        
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
        self.prediction_errors.append(np.mean(error**2))
        
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
# 5. EVOLUTIONARY POPULATION (with proper tracking)
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
    state_embeddings: List[np.ndarray] = field(default_factory=list)  # Track state for repetition
    
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
            
    def evaluate(self, agent_idx: int, reward: float, success: bool, 
                 action_text: str, state_embed: np.ndarray = None):
        agent = self.population[agent_idx]
        
        # Track action history
        agent.action_history.append(action_text)
        if len(agent.action_history) > 20:
            agent.action_history = agent.action_history[-20:]
        agent.unique_actions.add(action_text)
        
        # Track state embeddings for repetition detection
        if state_embed is not None:
            agent.state_embeddings.append(state_embed)
            if len(agent.state_embeddings) > 20:
                agent.state_embeddings = agent.state_embeddings[-20:]
        
        # Calculate repetition penalty based on both action and state
        repeat_count = agent.action_history.count(action_text)
        repetition_penalty = 0.0
        
        if repeat_count > 3:
            repetition_penalty = AGI_CONFIG['repeat_action_penalty'] * (repeat_count - 3)
            
        # State similarity penalty (if we have embeddings)
        if len(agent.state_embeddings) > 1:
            # Check if we're in the same state repeatedly
            current_state = agent.state_embeddings[-1]
            similar_states = 0
            for prev_state in agent.state_embeddings[:-1]:
                if prev_state is not None and current_state is not None:
                    similarity = np.dot(prev_state, current_state) / (np.linalg.norm(prev_state) * np.linalg.norm(current_state) + 1e-8)
                    if similarity > 0.95:  # Very similar states
                        similar_states += 1
                        
            if similar_states > 3:
                repetition_penalty += AGI_CONFIG['repeat_action_penalty'] * 0.5 * (similar_states - 3)
        
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
# 6. LONG-CHAIN REASONER (simplified but functional)
# ============================================================================

class LongChainReasoner:
    def __init__(self, world_model: JEPAWorldModel, embedding_dim: int = 128):
        self.world_model = world_model
        self.embedding_dim = embedding_dim
        self.horizon = AGI_CONFIG['reasoning_horizon']
        self.hypotheses = []
        
    def propose_sequence(self, state_embed: np.ndarray, actions: List[Dict], 
                        horizon: int = None) -> List[Dict]:
        if horizon is None:
            horizon = self.horizon
            
        if len(actions) < 2:
            return actions[:1]
            
        # Score each action with lookahead
        scored_actions = []
        for action in actions[:15]:
            text = action.get('text', '')
            if not text or text == '[No text]':
                continue
                
            action_embed = self._text_to_embedding(text)
            score = self._score_action(state_embed, action_embed, action)
            scored_actions.append((score, action))
            
        scored_actions.sort(key=lambda x: x[0], reverse=True)
        
        # Build sequence
        sequence = []
        if scored_actions:
            sequence = [scored_actions[0][1]]
            
            # Add follow-up actions if available
            if len(scored_actions) > 1:
                sequence.append(scored_actions[1][1])
            if len(scored_actions) > 2:
                sequence.append(scored_actions[2][1])
                
        # Store hypothesis
        if sequence:
            self.hypotheses.append({
                'sequence': [a.get('text', '')[:30] for a in sequence],
                'score': scored_actions[0][0] if scored_actions else 0,
                'horizon': horizon,
                'timestamp': datetime.now().isoformat()
            })
            
        if len(self.hypotheses) > 20:
            self.hypotheses = self.hypotheses[-20:]
            
        return sequence
        
    def _score_action(self, state_embed: np.ndarray, action_embed: np.ndarray,
                      action: Dict) -> float:
        """Score action based on embedding and text"""
        # Prediction quality
        next_pred = self.world_model.predict(state_embed, action_embed)
        quality = 1.0 / (1.0 + np.linalg.norm(next_pred - state_embed))
        
        # Text score
        text = action.get('text', '').lower()
        text_score = 0.0
        
        decisive = ['login', 'apply', 'submit', 'register', 'search', 'profile', 'job']
        for kw in decisive:
            if kw in text:
                text_score += 0.5
                
        if 'close' in text or 'ad' in text:
            text_score -= 1.0
            
        return quality + text_score
        
    def _text_to_embedding(self, text: str) -> np.ndarray:
        """Convert text to embedding"""
        embed = np.zeros(self.embedding_dim)
        
        keywords = ['apply', 'submit', 'login', 'search', 'next', 'more', 'register', 'profile', 'job', 'career']
        for i, kw in enumerate(keywords):
            if kw in text.lower():
                embed[i % self.embedding_dim] = 1.0
                
        norm = np.linalg.norm(embed)
        if norm > 0:
            embed = embed / norm
            
        return embed
        
    def get_best_hypothesis(self) -> Dict:
        if not self.hypotheses:
            return {}
        return max(self.hypotheses, key=lambda x: x['score'])

# ============================================================================
# 7. FIXED MAIN AGENT
# ============================================================================

class FixedAGIMathAgent:
    """Fixed AGI agent with proper integration"""
    
    def __init__(self, port: int = 9260, max_cycles: int = 30):
        self.port = port
        self.max_cycles = max_cycles
        
        self.session_dir = Path(f"agi_fixed_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        self.session_dir.mkdir(parents=True, exist_ok=True)
        
        self.cdp = FixedCDPWrapper(port=port)
        self.connected = self.cdp.connect()
        
        self.embedder = FixedMathematicalEmbedding(embedding_dim=AGI_CONFIG['embedding_dim'])
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
        self.state_history = deque(maxlen=50)
        
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
        """Prepare actions with filtering"""
        actions = []
        seen = set()
        
        decisive_keywords = ['login', 'apply', 'submit', 'register', 'search', 'profile', 'job', 'career']
        interactives = perception_data.get('interactives', [])
        
        for el in interactives:
            text = el.get('text', '').strip()
            if not text or len(text) < 2 or text == '[No text]':
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
                
            # Ad penalty
            if 'close' in text.lower() or 'ad' in text.lower():
                score -= 2.0
                
            actions.append({
                'text': text,
                'score': score,
                'selector': el.get('id', ''),
                'tag': el.get('tag', ''),
                'href': el.get('href', ''),
                'is_decisive': any(kw in text.lower() for kw in decisive_keywords)
            })
            
        actions.sort(key=lambda x: x.get('score', 0), reverse=True)
        return actions[:25]
        
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
        
    def run(self):
        print("🧠 AGI MATH SYSTEM - FIXED INTEGRATION")
        print("=" * 70)
        print(f"Perception: FixedDOMExplorer with extract_hierarchy")
        print(f"Execution: ChromePage.click_by_text()")
        print(f"Reasoning Horizon: {AGI_CONFIG['reasoning_horizon']} steps")
        print(f"Embedding Dim: {AGI_CONFIG['embedding_dim']}")
        print("=" * 70)
        
        if not self.connected:
            print("❌ Not connected")
            return
            
        perception_data = self.perceive()
        state_embed = self.embedder.encode(perception_data)
        
        print(f"📍 Starting on: {perception_data.get('url', 'unknown')}")
        print(f"📊 Interactive elements: {len(perception_data.get('interactives', []))}")
        print(f"📊 Total elements: {perception_data.get('total_elements', 0)}")
        
        for cycle in range(1, self.max_cycles + 1):
            self.current_cycle = cycle
            
            print(f"\n{'='*70}")
            print(f"🔄 CYCLE {cycle}/{self.max_cycles}")
            print(f"{'='*70}")
            
            perception_data = self.perceive()
            state_embed = self.embedder.encode(perception_data)
            self.state_history.append(state_embed)
            
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
                
            sequence = self.reasoner.propose_sequence(
                state_embed, 
                actions, 
                horizon=AGI_CONFIG['reasoning_horizon']
            )
            
            if sequence:
                print(f"\n🔗 Proposed Sequence ({len(sequence)} steps):")
                for i, action in enumerate(sequence[:5], 1):
                    decisive = "🎯" if action.get('is_decisive', False) else "  "
                    print(f"  {i}. {decisive} {action.get('text', '')[:40]}")
                    
            agent_idx = cycle % self.population.population_size
            agent = self.population.population[agent_idx]
            
            # Choose action
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
            
            # Pass state_embed for repetition detection
            adjusted_reward = self.population.evaluate(
                agent_idx, reward, result.get('success', False),
                action.get('text', ''),
                state_embed
            )
            
            action_embed = self.reasoner._text_to_embedding(action.get('text', ''))
            loss = self.world_model.learn(state_embed, action_embed, new_state_embed)
            
            self._log_json('predictions', {
                'loss': float(loss),
                'state_norm': float(np.linalg.norm(state_embed)),
                'new_state_norm': float(np.linalg.norm(new_state_embed))
            })
            
            if cycle % 3 == 0:
                evolution_stats = self.population.evolve()
                self._log_json('evolution', evolution_stats)
                print(f"\n🧬 Evolution Stats:")
                print(f"  Generation: {evolution_stats['generation']}")
                print(f"  Best Fitness: {evolution_stats['best_fitness']:.2f}")
                print(f"  Avg Fitness: {evolution_stats['avg_fitness']:.2f}")
                
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
                'decisive_actions': self.decisive_action_count,
                'interactives': len(new_perception.get('interactives', []))
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
            print(f"  State Norm: {np.linalg.norm(state_embed):.4f}")
            
        self._generate_report()
        
    def _generate_report(self):
        print("\n" + "=" * 80)
        print("🧠 AGI MATH SYSTEM - FIXED INTEGRATION REPORT")
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
    print("🧠 AGI MATH SYSTEM - FIXED INTEGRATION")
    print("=" * 70)
    print("Perception: FixedDOMExplorer with extract_hierarchy()")
    print("Execution: ChromePage methods with validation")
    print("Reasoning: 8-step JEPA with repetition tracking")
    print("=" * 70)
    
    port = AGI_CONFIG['port']
    max_cycles = AGI_CONFIG['max_cycles']
    
    agent = FixedAGIMathAgent(port=port, max_cycles=max_cycles)
    
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
