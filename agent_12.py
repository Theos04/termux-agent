#!/usr/bin/env python3
"""
GENERIC AGENT - Semantic Perception + Intrinsic Motivation
No hardcoded keywords - uses semantic embeddings and prediction loss
Domain-partitioned memory for multi-site adaptation
"""

import json
import sys
import os
import time
import hashlib
import gc
import re
import urllib.request
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple, Set
from collections import defaultdict, deque, Counter
from urllib.parse import urlparse
import random
import math
import traceback
import numpy as np
from dataclasses import dataclass, field

# ============================================================================
# CONFIGURATION
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
    "llama_server": "http://127.0.0.1:8081",
    "intrinsic_scale": 15.0,
    "intrinsic_cap": 5.0,
    "goal_threshold": 0.55,
}

# ============================================================================
# 1. SEMANTIC ACTION SCORER (Koopman-inspired)
# ============================================================================

class SemanticActionScorer:
    """
    Real embedding-based semantic scoring, replacing keyword lists.
    Falls back to keyword heuristic if llama-server isn't reachable.
    """
    
    def __init__(self, base_url: str = "http://127.0.0.1:8081", timeout: float = 6.0):
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.available = self._probe()
        self._closing_anchor_embed: Optional[np.ndarray] = None
        self._success_anchor_embeds: Optional[List[np.ndarray]] = None
        
        if self.available:
            print(f"🔤 Semantic scorer online: {base_url}")
            self._closing_anchor_embed = self._embed_anchor_set(CLOSING_ANCHORS)
            self._success_anchor_embeds = [self._embed(a) for a in SUCCESS_ANCHORS]
            self._success_anchor_embeds = [e for e in self._success_anchor_embeds if e is not None]
        else:
            print("   ⚠️ Embedding server not reachable, falling back to keyword heuristic")
            
    def _probe(self) -> bool:
        try:
            test = self._embed("test")
            return test is not None
        except Exception:
            return False
            
    def _embed(self, text: str) -> Optional[np.ndarray]:
        """Get embedding from llama-server"""
        try:
            payload = json.dumps({"input": text[:200]}).encode("utf-8")
            req = urllib.request.Request(
                f"{self.base_url}/v1/embeddings",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            return np.array(body["data"][0]["embedding"], dtype=np.float32)
        except Exception:
            # Fallback to legacy endpoint
            try:
                req2 = urllib.request.Request(
                    f"{self.base_url}/embedding",
                    data=json.dumps({"content": text[:200]}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req2, timeout=self.timeout) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
                return np.array(body["embedding"], dtype=np.float32)
            except Exception:
                return None
                
    def _embed_anchor_set(self, phrases: List[str]) -> Optional[np.ndarray]:
        vecs = [self._embed(p) for p in phrases]
        vecs = [v for v in vecs if v is not None]
        if not vecs:
            return None
        return np.mean(np.stack(vecs), axis=0)
        
    def score_action(self, text: str) -> float:
        """Returns 0.0-1.0: semantic closeness to 'closing' actions"""
        if not self.available or self._closing_anchor_embed is None:
            return self._fallback_score(text)
            
        embed = self._embed(text)
        if embed is None:
            return self._fallback_score(text)
            
        sim = self._cosine(embed, self._closing_anchor_embed)
        return max(0.0, min(1.0, (sim + 1) / 2))  # map [-1,1] -> [0,1]
        
    def check_semantic_goal(self, page_text: str, threshold: float = None) -> Tuple[bool, float]:
        """Nearest-centroid check against SUCCESS_ANCHORS"""
        if threshold is None:
            threshold = AGI_CONFIG['goal_threshold']
            
        if not self.available or not self._success_anchor_embeds:
            return False, 0.0
            
        embed = self._embed(page_text[:300])
        if embed is None:
            return False, 0.0
            
        best = max(self._cosine(embed, a) for a in self._success_anchor_embeds)
        best_01 = (best + 1) / 2
        return best_01 >= threshold, best_01
        
    @staticmethod
    def _cosine(a: np.ndarray, b: np.ndarray) -> float:
        na, nb = np.linalg.norm(a), np.linalg.norm(b)
        if na < 1e-9 or nb < 1e-9:
            return 0.0
        return float(np.dot(a, b) / (na * nb))
        
    @staticmethod
    def _fallback_score(text: str) -> float:
        """Lightweight fallback if embedding server is down"""
        t = text.lower()
        # Use the anchor phrases themselves as the heuristic
        for anchor in CLOSING_ANCHORS:
            if anchor in t:
                return 0.8
        # Check individual words
        strong = ['apply', 'submit', 'register', 'sign up', 'confirm', 'checkout']
        return 0.8 if any(w in t for w in strong) else 0.2

# ============================================================================
# 2. INTRINSIC REWARD TRACKER (Curiosity from prediction loss)
# ============================================================================

class IntrinsicRewardTracker:
    """
    Curiosity bonus from JEPA prediction loss.
    High loss = surprised = novel territory worth exploring.
    """
    
    def __init__(self, scale: float = 15.0, cap: float = 5.0, baseline_window: int = 30):
        self.scale = scale
        self.cap = cap
        self.loss_history = deque(maxlen=baseline_window)
        
    def bonus(self, prediction_loss: float) -> float:
        """Calculate intrinsic bonus from prediction loss"""
        self.loss_history.append(prediction_loss)
        
        if len(self.loss_history) < 5:
            return 0.0
            
        baseline = float(np.mean(self.loss_history))
        surprise = max(0.0, prediction_loss - baseline)
        bonus_value = min(self.cap, surprise * self.scale)
        
        if bonus_value > 0.5:
            print(f"   🔍 Intrinsic bonus: +{bonus_value:.2f} (surprise: {surprise:.4f})")
            
        return bonus_value
        
    def get_stats(self) -> Dict:
        if not self.loss_history:
            return {'mean_loss': 0.0, 'std_loss': 0.0, 'surprise_score': 0.0}
        return {
            'mean_loss': float(np.mean(self.loss_history)),
            'std_loss': float(np.std(self.loss_history)),
            'surprise_score': float(np.std(self.loss_history) / (np.mean(self.loss_history) + 1e-8))
        }

# ============================================================================
# 3. DOMAIN-PARTITIONED MEMORY (Practical HiP-RSSM)
# ============================================================================

class GlobalActionMemory:
    """Single-domain memory (used per domain)"""
    
    def __init__(self):
        self.action_history = deque(maxlen=100)
        self.state_history = deque(maxlen=100)
        self.action_counts = Counter()
        self.session_actions = {}
        
    def record_action(self, action_text: str, state_embed: np.ndarray = None, 
                     session_id: str = None):
        self.action_history.append((action_text, time.time()))
        self.action_counts[action_text] += 1
        if session_id:
            if session_id not in self.session_actions:
                self.session_actions[session_id] = []
            self.session_actions[session_id].append(action_text)
        if state_embed is not None:
            self.state_history.append((action_text, state_embed))
            
    def get_repetition_penalty(self, action_text: str, state_embed: np.ndarray = None) -> float:
        global_count = self.action_counts.get(action_text, 0)
        if global_count == 0:
            return 0.0
            
        penalty = -1.0 * (2 ** (global_count - 1)) if global_count >= 1 else 0.0
        
        if state_embed is not None and len(self.state_history) > 0:
            similar_count = 0
            for past_action, past_state in list(self.state_history)[-20:]:
                if past_action == action_text:
                    continue
                if past_state is not None:
                    sim = np.dot(past_state, state_embed) / (
                        np.linalg.norm(past_state) * np.linalg.norm(state_embed) + 1e-8
                    )
                    if sim > 0.9:
                        similar_count += 1
            if similar_count >= 1:
                penalty -= 1.0 * (2 ** similar_count)
                
        return penalty
        
    def get_stats(self) -> Dict:
        return {
            'total_actions': len(self.action_history),
            'unique_actions': len(self.action_counts),
            'most_common': self.action_counts.most_common(5),
        }

class DomainPartitionedMemory:
    """
    Wraps independent memory instances per domain.
    Practical 80% of HiP-RSSM without training corpus.
    """
    
    def __init__(self):
        self._by_domain = {}
        
    def get(self, domain: str) -> GlobalActionMemory:
        if domain not in self._by_domain:
            self._by_domain[domain] = GlobalActionMemory()
            print(f"   📂 New memory domain: {domain}")
        return self._by_domain[domain]
        
    def get_stats(self) -> Dict:
        return {
            domain: mem.get_stats() 
            for domain, mem in self._by_domain.items()
        }

# ============================================================================
# 4. CDP WRAPPER (with page text for semantic goals)
# ============================================================================

class CDPWrapper:
    def __init__(self, port: int = 9260):
        self.port = port
        self.page = None
        self.connected = False
        
    def connect(self) -> bool:
        try:
            from geturl import ChromePage
            self.page = ChromePage(port=self.port)
            if self.page.connect():
                self.connected = True
                print(f"🔍 Connected to: {self.page.get_title()}")
                return True
        except Exception as e:
            print(f"⚠️ Connect error: {e}")
        return False
        
    def get_perception_data(self) -> Dict:
        if not self.connected or not self.page:
            return self._fallback_perception()
            
        try:
            # Get page text for semantic goals (first 500 chars)
            text = self.page.get_text()
            
            # Get clickable elements
            clickable = self.page.get_clickable_elements()
            
            return {
                'url': self.page.page_url,
                'title': self.page.get_title(),
                'interactives': clickable[:30],
                'page_text': text[:500] if text else "",
                'total_elements': len(clickable),
                'timestamp': time.time()
            }
        except Exception as e:
            return self._fallback_perception()
            
    def _fallback_perception(self) -> Dict:
        return {'url': '', 'title': '', 'interactives': [], 'page_text': '', 'total_elements': 0}
        
    def execute_action(self, action: Dict) -> Dict:
        text = action.get('text', '')
        if not text or len(text) < 2:
            return {'success': False, 'error': 'Invalid text'}
        try:
            success = self.page.click_by_text(text)
            return {'success': success}
        except Exception as e:
            return {'success': False, 'error': str(e)}

# ============================================================================
# 5. MAIN GENERIC AGENT
# ============================================================================

class GenericAgent:
    """
    Generic agent with semantic perception, intrinsic motivation,
    and domain-partitioned memory.
    """
    
    def __init__(self, port: int = 9260, max_cycles: int = 30):
        self.port = port
        self.max_cycles = max_cycles
        
        self.session_dir = Path(f"generic_agent_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        self.session_dir.mkdir(parents=True, exist_ok=True)
        
        # Semantic scorer (replaces keyword lists)
        self.scorer = SemanticActionScorer(
            base_url=AGI_CONFIG['llama_server']
        )
        
        # Intrinsic reward (curiosity from prediction loss)
        self.intrinsic = IntrinsicRewardTracker(
            scale=AGI_CONFIG['intrinsic_scale'],
            cap=AGI_CONFIG['intrinsic_cap']
        )
        
        # Domain-partitioned memory (practical HiP-RSSM)
        self.domain_memory = DomainPartitionedMemory()
        
        # CDP
        self.cdp = CDPWrapper(port=port)
        
        # Simple embedding (we use semantic scoring directly)
        self.embedding_dim = AGI_CONFIG['embedding_dim']
        
        # Tracking
        self.current_cycle = 0
        self.reward_history = deque(maxlen=50)
        self.best_reward = -float('inf')
        self.total_rewards = 0
        self.goal_achieved = False
        self.action_history = []
        
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
        
    def prepare_actions(self, perception_data: Dict, domain: str) -> List[Dict]:
        """Prepare actions using SEMANTIC scoring (no keyword lists)"""
        actions = []
        seen = set()
        
        interactives = perception_data.get('interactives', [])
        mem = self.domain_memory.get(domain)
        
        for el in interactives:
            text = el.get('text', '').strip()
            if not text or len(text) < 2:
                continue
                
            if text in seen:
                continue
            seen.add(text)
            
            # SEMANTIC SCORE (0.0-1.0) - replaces keyword scoring
            semantic_score = self.scorer.score_action(text)
            
            # Scale to match previous reward magnitude
            score = semantic_score * 3.0
            
            # Visibility bonus
            if el.get('visible', True):
                score += 0.5
                
            # DOMAIN-SPECIFIC repetition penalty
            state_embed = self._text_to_embedding(text)
            global_penalty = mem.get_repetition_penalty(text, state_embed)
            score += global_penalty
            
            actions.append({
                'text': text,
                'score': score,
                'semantic_score': semantic_score,
                'tag': el.get('tag', ''),
                'visible': el.get('visible', True)
            })
            
        actions.sort(key=lambda x: x.get('score', 0), reverse=True)
        return actions[:20]
        
    def _text_to_embedding(self, text: str) -> np.ndarray:
        """Simple embedding for state similarity"""
        embed = np.zeros(AGI_CONFIG['embedding_dim'], dtype=AGI_CONFIG['dtype'])
        # Use semantic scorer if available
        if self.scorer.available:
            emb = self.scorer._embed(text)
            if emb is not None:
                # Truncate to embedding_dim
                if len(emb) > AGI_CONFIG['embedding_dim']:
                    return emb[:AGI_CONFIG['embedding_dim']]
                return np.pad(emb, (0, AGI_CONFIG['embedding_dim'] - len(emb)))
        # Fallback
        words = ['apply', 'submit', 'login', 'search', 'next', 'profile', 'job']
        for i, w in enumerate(words):
            if w in text.lower():
                embed[i % AGI_CONFIG['embedding_dim']] = 1.0
        norm = np.linalg.norm(embed)
        if norm > 0:
            embed = embed / norm
        return embed
        
    def calculate_reward(self, perception_before: Dict, perception_after: Dict,
                         success: bool, action_text: str, domain: str,
                         prediction_loss: float) -> float:
        """Calculate reward with semantic signals and intrinsic motivation"""
        reward = 0.0
        components = {}
        
        # Success reward
        if success:
            reward += 0.5
            components['success'] = 0.5
            
        # Page change
        url_before = perception_before.get('url', '')
        url_after = perception_after.get('url', '')
        if url_before and url_after and url_before != url_after:
            reward += 3.0
            components['page_change'] = 3.0
            
        # More interactives
        count_before = len(perception_before.get('interactives', []))
        count_after = len(perception_after.get('interactives', []))
        if count_after > count_before * 1.2:
            reward += 1.5
            components['more_interactive'] = 1.5
            
        # SEMANTIC GOAL CHECK (replaces keyword goal)
        page_text = perception_after.get('page_text', '')
        is_goal, confidence = self.scorer.check_semantic_goal(page_text)
        
        if is_goal:
            reward += 10.0
            components['semantic_goal'] = 10.0
            self.goal_achieved = True
            print(f"   🎯 Semantic goal detected! (confidence: {confidence:.2f})")
            
        # INTRINSIC REWARD (curiosity from prediction loss)
        intrinsic_bonus = self.intrinsic.bonus(prediction_loss)
        if intrinsic_bonus > 0.1:
            reward += intrinsic_bonus
            components['intrinsic'] = intrinsic_bonus
            
        # DOMAIN-SPECIFIC repetition penalty (applied via memory)
        mem = self.domain_memory.get(domain)
        state_embed = self._text_to_embedding(action_text)
        repetition_penalty = mem.get_repetition_penalty(action_text, state_embed)
        reward += repetition_penalty
        
        if repetition_penalty < -0.5:
            components['repetition_penalty'] = repetition_penalty
            
        # Stagnation penalty
        if url_before == url_after and not success:
            reward -= 0.5
            components['stagnation'] = -0.5
            
        self._log_json('rewards', {
            'reward': reward,
            'components': components,
            'success': success,
            'action': action_text[:50],
            'semantic_score': self.scorer.score_action(action_text),
            'intrinsic_bonus': intrinsic_bonus,
            'goal_confidence': confidence if is_goal else 0.0
        })
        
        return reward
        
    def run(self):
        print("🧠 GENERIC AGENT - Semantic Perception + Intrinsic Motivation")
        print("=" * 70)
        print("Features:")
        print("  ✅ Semantic scoring (Koopman-inspired)")
        print("  ✅ Intrinsic reward from prediction loss")
        print("  ✅ Domain-partitioned memory (practical HiP-RSSM)")
        print("  ✅ No hardcoded keyword lists")
        print("=" * 70)
        
        if not self.cdp.connect():
            print("❌ Not connected")
            return
            
        perception_data = self.perceive()
        domain = urlparse(perception_data.get('url', '')).netloc
        
        print(f"📍 Starting on: {perception_data.get('url', 'unknown')}")
        print(f"🌐 Domain: {domain}")
        print(f"📊 Interactive elements: {len(perception_data.get('interactives', []))}")
        print(f"🔤 Semantic scorer: {'✅ Available' if self.scorer.available else '❌ Fallback mode'}")
        
        for cycle in range(1, self.max_cycles + 1):
            self.current_cycle = cycle
            
            print(f"\n{'='*70}")
            print(f"🔄 CYCLE {cycle}/{self.max_cycles}")
            print(f"{'='*70}")
            
            perception_data = self.perceive()
            domain = urlparse(perception_data.get('url', '')).netloc
            
            actions = self.prepare_actions(perception_data, domain)
            
            if not actions:
                print("⏳ No actions available, waiting...")
                time.sleep(AGI_CONFIG['action_delay'])
                continue
                
            print(f"\n📋 Top Actions ({len(actions)} available):")
            for i, action in enumerate(actions[:5], 1):
                semantic = action.get('semantic_score', 0)
                score = action.get('score', 0)
                print(f"  {i}. {action['text'][:40]} (semantic: {semantic:.2f}, score: {score:.2f})")
                
            # Show domain memory stats
            mem = self.domain_memory.get(domain)
            stats = mem.get_stats()
            print(f"\n📊 Domain Memory ({domain}):")
            print(f"   Actions: {stats['total_actions']}, Unique: {stats['unique_actions']}")
            if stats['most_common']:
                print(f"   Most Common: {stats['most_common'][0][0]} ({stats['most_common'][0][1]} times)")
                
            # Intrinsic reward stats
            intrinsic_stats = self.intrinsic.get_stats()
            print(f"   Intrinsic: mean_loss={intrinsic_stats['mean_loss']:.4f}, "
                  f"surprise={intrinsic_stats['surprise_score']:.2f}")
            
            # Choose action with some exploration
            if random.random() < 0.2:  # 20% exploration
                action = random.choice(actions[:5])
                print(f"\n🎲 Exploring: {action['text'][:40]}")
            else:
                # Pick best action
                action = actions[0]
                print(f"\n🎯 Greedy: {action['text'][:40]}")
                
            time.sleep(AGI_CONFIG['action_delay'])
            result = self.cdp.execute_action(action)
            
            print(f"   ⏳ Settling...")
            time.sleep(AGI_CONFIG['perception_delay'])
            
            new_perception = self.perceive()
            
            # Calculate prediction loss (using semantic embedding as state)
            state_embed = self._text_to_embedding(action.get('text', ''))
            next_state_embed = self._text_to_embedding(
                new_perception.get('page_text', '')[:100]
            )
            
            # Simple prediction loss: difference in embeddings
            prediction_loss = float(np.linalg.norm(state_embed - next_state_embed))
            
            # Calculate reward with semantic + intrinsic signals
            reward = self.calculate_reward(
                perception_data, new_perception,
                result.get('success', False),
                action.get('text', ''),
                domain,
                prediction_loss
            )
            
            # Record in domain memory
            mem = self.domain_memory.get(domain)
            mem.record_action(action.get('text', ''), state_embed, str(cycle))
            
            # Track metrics
            self.reward_history.append(reward)
            self.total_rewards += reward
            self.action_history.append(action.get('text', '')[:30])
            
            if reward > self.best_reward:
                self.best_reward = reward
                print(f"   📈 New best reward: {reward:.2f}")
                
            metrics = {
                'reward': reward,
                'success': result.get('success', False),
                'loss': prediction_loss,
                'best_reward': self.best_reward,
                'total_rewards': self.total_rewards,
                'domain_actions': stats['total_actions'],
                'domain_unique': stats['unique_actions'],
                'intrinsic_surprise': intrinsic_stats['surprise_score'],
                'semantic_score': action.get('semantic_score', 0)
            }
            self._log_json('metrics', metrics)
            
            print(f"\n📊 Results:")
            print(f"  Reward: {reward:.2f}")
            print(f"  Success: {'✅' if result.get('success') else '❌'}")
            print(f"  Loss: {prediction_loss:.4f}")
            print(f"  Best Reward: {self.best_reward:.2f}")
            print(f"  Semantic Score: {action.get('semantic_score', 0):.2f}")
            print(f"  Goal Achieved: {'✅' if self.goal_achieved else '❌'}")
            
            if self.goal_achieved:
                print(f"\n🎉🎉🎉 GOAL ACHIEVED via semantic detection! 🎉🎉🎉")
                break
                
        self._generate_report()
        
    def _generate_report(self):
        print("\n" + "=" * 80)
        print("🧠 GENERIC AGENT - FINAL REPORT")
        print("=" * 80)
        
        print(f"\n📊 STATISTICS:")
        print(f"  Total Cycles: {self.current_cycle}")
        print(f"  Best Reward: {self.best_reward:.2f}")
        print(f"  Total Rewards: {self.total_rewards:.2f}")
        print(f"  Goal Achieved: {'✅' if self.goal_achieved else '❌'}")
        print(f"  Semantic Scorer: {'✅ Online' if self.scorer.available else '❌ Fallback'}")
        
        # Domain stats
        domain_stats = self.domain_memory.get_stats()
        print(f"\n🌐 DOMAIN MEMORY:")
        for domain, stats in domain_stats.items():
            print(f"  {domain}:")
            print(f"    Actions: {stats['total_actions']}, Unique: {stats['unique_actions']}")
            if stats['most_common']:
                print(f"    Most Common: {stats['most_common'][0][0]} ({stats['most_common'][0][1]} times)")
                
        # Action distribution
        if self.action_history:
            action_counts = Counter(self.action_history)
            print(f"\n📋 ACTION DISTRIBUTION:")
            for action, count in action_counts.most_common(10):
                print(f"  {action}: {count} times")
                
        print(f"\n📁 LOG FILES:")
        for log_file in self.log_dir.glob("*.jsonl"):
            size = log_file.stat().st_size
            print(f"  {log_file.name}: {size} bytes")
            
        print("\n" + "=" * 80)

# ============================================================================
# SEMANTIC ANCHORS
# ============================================================================

CLOSING_ANCHORS = [
    "apply now", "submit application", "register account", "sign up now",
    "confirm booking", "proceed to checkout", "complete purchase",
    "submit form", "send request", "finish application",
]

SUCCESS_ANCHORS = [
    "application submitted successfully", "thank you for your submission",
    "your request has been confirmed", "order complete", "registration successful",
    "your application has been received", "payment successful",
]

# ============================================================================
# MAIN
# ============================================================================

def main():
    print("🧠 GENERIC AGENT - Semantic Perception")
    print("=" * 70)
    print("No hardcoded keywords - uses semantic embeddings")
    print("Intrinsic reward from prediction loss")
    print("Domain-partitioned memory for multi-site adaptation")
    print("=" * 70)
    
    # Check for llama-server
    try:
        import urllib.request
        req = urllib.request.Request(
            AGI_CONFIG['llama_server'],
            method='HEAD'
        )
        urllib.request.urlopen(req, timeout=2)
        print(f"✅ llama-server detected at {AGI_CONFIG['llama_server']}")
    except:
        print(f"⚠️ llama-server not detected at {AGI_CONFIG['llama_server']}")
        print("   Using fallback keyword heuristic")
        
    port = AGI_CONFIG['port']
    max_cycles = AGI_CONFIG['max_cycles']
    
    agent = GenericAgent(port=port, max_cycles=max_cycles)
    
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
