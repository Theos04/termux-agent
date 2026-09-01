#!/usr/bin/env python3
"""
AI/ML Orchestrator - Full Stack Intelligence
Integrates: Perception → Intelligence → Decision → Action → Memory → Learning
"""

import json
import sys
import os
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field, asdict
from collections import defaultdict
import random
import math
import threading
import queue

# ============================================================================
# AI/ML Components - The "Brain"
# ============================================================================

class ContextualMAB:
    """
    Multi-Armed Bandit with Context Awareness
    Learns which actions work best in which contexts
    """
    
    def __init__(self, alpha: float = 0.1, gamma: float = 0.9):
        self.alpha = alpha  # Learning rate
        self.gamma = gamma  # Discount factor
        self.q_values = defaultdict(lambda: defaultdict(float))  # Q-values for (context, action)
        self.arm_counts = defaultdict(lambda: defaultdict(int))
        self.context_history = []
        self.reward_history = []
        
    def get_action(self, context: Dict, actions: List[str]) -> str:
        """Choose best action using epsilon-greedy with UCB"""
        context_key = self._context_key(context)
        
        # Explore with probability
        if random.random() < 0.1:  # 10% exploration
            return random.choice(actions)
        
        # Choose best action
        best_action = None
        best_score = -float('inf')
        
        for action in actions:
            # UCB score: Q-value + exploration bonus
            n = self.arm_counts[context_key][action] + 1
            q = self.q_values[context_key][action]
            ucb = math.sqrt(2 * math.log(sum(self.arm_counts[context_key].values()) + 1) / n)
            score = q + ucb
            
            if score > best_score:
                best_score = score
                best_action = action
                
        return best_action or random.choice(actions)
    
    def update(self, context: Dict, action: str, reward: float):
        """Update Q-value for the (context, action) pair"""
        context_key = self._context_key(context)
        
        # Update Q-value with learning rate
        old_q = self.q_values[context_key][action]
        self.q_values[context_key][action] = old_q + self.alpha * (reward - old_q)
        self.arm_counts[context_key][action] += 1
        
        # Store history for analysis
        self.context_history.append({
            'context': context_key,
            'action': action,
            'reward': reward,
            'timestamp': datetime.now().isoformat()
        })
        self.reward_history.append(reward)
    
    def _context_key(self, context: Dict) -> str:
        """Create a string key from context dictionary"""
        # Only use most important context features
        key_parts = []
        for k in sorted(context.keys())[:5]:
            if context.get(k):
                key_parts.append(f"{k}:{context[k]}")
        return ",".join(key_parts) or "default"
    
    def get_stats(self) -> Dict:
        """Get MAB statistics"""
        total_arms = sum(len(arms) for arms in self.arm_counts.values())
        total_pulls = sum(sum(arms.values()) for arms in self.arm_counts.values())
        
        return {
            'total_arms': total_arms,
            'total_pulls': total_pulls,
            'unique_contexts': len(self.arm_counts),
            'avg_reward': sum(self.reward_history) / len(self.reward_history) if self.reward_history else 0,
            'best_action': self._get_best_action()
        }
    
    def _get_best_action(self) -> str:
        """Get the globally best performing action"""
        best_action = None
        best_score = -float('inf')
        
        for context, arms in self.arm_counts.items():
            for action, count in arms.items():
                if count > 5:  # Only consider actions with enough samples
                    q = self.q_values[context][action]
                    if q > best_score:
                        best_score = q
                        best_action = action
                        
        return best_action or "unknown"


class NeuralPerception:
    """
    Neural Perception Layer - Translates DOM "noise" into structured features
    This is the "Mario RAM to Grid" transformation
    """
    
    def __init__(self):
        self.feature_weights = {
            'clickable_count': 0.3,
            'link_count': 0.2,
            'form_count': 0.2,
            'input_count': 0.1,
            'has_login': 0.1,
            'has_pagination': 0.1
        }
    
    def extract_features(self, perception_data: Dict) -> Dict[str, float]:
        """Extract numerical features from perception"""
        features = {}
        
        # Count features
        features['clickable_count'] = min(len(perception_data.get('clickable', [])) / 100, 1.0)
        features['link_count'] = min(len(perception_data.get('links', [])) / 200, 1.0)
        features['form_count'] = min(perception_data.get('metadata', {}).get('formCount', 0) / 10, 1.0)
        features['input_count'] = min(perception_data.get('metadata', {}).get('inputCount', 0) / 20, 1.0)
        
        # Boolean features
        features['has_login'] = 1.0 if perception_data.get('metadata', {}).get('has_login', False) else 0.0
        features['has_pagination'] = 1.0 if self._detect_pagination(perception_data) else 0.0
        features['has_competitors'] = 1.0 if len(perception_data.get('competitor_links', [])) > 0 else 0.0
        
        # Normalize
        total = sum(features.values()) or 1.0
        return {k: v / total for k, v in features.items()}
    
    def _detect_pagination(self, perception_data: Dict) -> bool:
        """Detect if page has pagination"""
        clickable = perception_data.get('clickable', [])
        for el in clickable:
            text = el.get('text', '').lower()
            if any(x in text for x in ['next', 'more', 'load more', 'view all', '下一页']):
                return True
        return False


class PatternLearner:
    """
    Pattern Learning Layer - Learns patterns from experiences
    Uses simple association learning
    """
    
    def __init__(self):
        self.patterns = defaultdict(lambda: defaultdict(int))
        self.sequence_patterns = []
        self.success_rate = defaultdict(float)
    
    def learn(self, experience):
        """Learn from an experience"""
        context = experience.get('context', {})
        action = experience.get('action', '')
        reward = experience.get('reward', 0)
        
        # Pattern: context → action → reward
        for key, value in context.items():
            if isinstance(value, (int, float, bool, str)):
                pattern_key = f"{key}:{value}"
                self.patterns[pattern_key][action] += 1
        
        # Track success rate
        if action:
            total = self.success_rate.get(action, 0) + 1
            success = self.success_rate.get(action + "_success", 0) + (1 if reward > 0 else 0)
            self.success_rate[action] = total
            self.success_rate[action + "_success"] = success
    
    def predict(self, context: Dict, actions: List[str]) -> Dict[str, float]:
        """Predict success probability for each action"""
        predictions = {}
        
        for action in actions:
            score = 0
            count = 0
            
            # Match patterns
            for key, value in context.items():
                if isinstance(value, (int, float, bool, str)):
                    pattern_key = f"{key}:{value}"
                    if pattern_key in self.patterns:
                        action_count = self.patterns[pattern_key].get(action, 0)
                        total = sum(self.patterns[pattern_key].values())
                        if total > 0:
                            score += action_count / total
                            count += 1
            
            # Average pattern scores
            if count > 0:
                predictions[action] = score / count
            else:
                # Default prediction based on historical success
                total = self.success_rate.get(action, 1)
                success = self.success_rate.get(action + "_success", 0)
                predictions[action] = success / total if total > 0 else 0.5
                
        return predictions


class RewardOptimizer:
    """
    Reward Optimization Layer - Learns optimal reward functions
    """
    
    def __init__(self):
        self.reward_weights = {
            'success': 1.0,
            'data_extracted': 0.5,
            'navigation': 0.3,
            'time_efficiency': 0.2
        }
        self.history = []
    
    def calculate_reward(self, action_result: Dict, perception_before: Dict, perception_after: Dict) -> float:
        """Calculate reward based on multiple factors"""
        reward = 0
        
        # Success reward
        if action_result.get('success', False):
            reward += self.reward_weights['success']
            
            # Data extraction bonus
            if 'extract' in str(action_result):
                data_size = len(str(action_result.get('result', '')))
                if data_size > 0:
                    reward += self.reward_weights['data_extracted'] * min(data_size / 1000, 1.0)
            
            # Navigation bonus
            if perception_before.get('url') != perception_after.get('url'):
                reward += self.reward_weights['navigation']
                
            # Time efficiency
            duration = action_result.get('duration_ms', 0) / 1000  # seconds
            if duration < 2:
                reward += self.reward_weights['time_efficiency']
        
        return max(-1.0, min(1.0, reward))
    
    def update_weights(self, rewards: List[float], outcomes: List[bool]):
        """Update reward weights based on outcomes"""
        # Simple gradient descent
        for i, outcome in enumerate(outcomes):
            reward = rewards[i]
            if outcome:
                self.reward_weights['success'] += 0.01 * reward
            else:
                self.reward_weights['success'] -= 0.01 * abs(reward)
        
        # Normalize weights
        total = sum(self.reward_weights.values())
        for key in self.reward_weights:
            self.reward_weights[key] /= total


# ============================================================================
# AI Orchestrator - Full Stack
# ============================================================================

class AIOrchestrator:
    """
    Full AI Stack Orchestrator
    Integrates: MAB (Decision) + Neural Perception + Pattern Learning + Reward Optimization
    """
    
    def __init__(self, port: int = 9257, session_dir: str = None):
        self.port = port
        self.session_dir = Path(session_dir or f"ai_session_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        self.session_dir.mkdir(parents=True, exist_ok=True)
        
        # AI Components
        self.mab = ContextualMAB()
        self.perception = NeuralPerception()
        self.pattern_learner = PatternLearner()
        self.reward_optimizer = RewardOptimizer()
        
        # State
        self.experiences = []
        self.current_context = {}
        self.iterations = 0
        
        # Action library
        self.action_library = [
            'click_login', 'click_signup', 'click_next', 'click_prev',
            'extract_links', 'extract_text', 'extract_tables',
            'scroll_down', 'scroll_up', 'wait', 'click_first_button'
        ]
        
        # Import your existing modules
        try:
            from har2api.core.parser import HARParser
            from har2api.core.analyzer import HARAnalyzer
            from har2api.generators.client_generator import ClientGenerator
            self.har2api_available = True
        except:
            self.har2api_available = False
            
        try:
            from quick_capture_har import capture_har, get_tabs
            self.capture_available = True
        except:
            self.capture_available = False
            
        try:
            from dcdp import EnhancedChromeCDP
            self.cdp = EnhancedChromeCDP(port)
            self.cdp_available = True
        except:
            self.cdp_available = False
            
        print(f"🧠 AI Orchestrator initialized")
        print(f"📁 Session: {self.session_dir}")
        print(f"📚 Actions: {len(self.action_library)}")
        print(f"🤖 MAB: {self.mab.__class__.__name__}")
        print(f"🧠 Perception: {self.perception.__class__.__name__}")
        print(f"📊 Pattern Learner: {self.pattern_learner.__class__.__name__}")
        print(f"🎯 Reward Optimizer: {self.reward_optimizer.__class__.__name__}")
    
    # ========================================================================
    # Perception Layer (AI)
    # ========================================================================
    
    def perceive(self) -> Dict:
        """Perceive the environment using CDP and extract features"""
        print("\n👁️ Perception Layer: Analyzing environment...")
        
        perception_data = {
            'clickable': [],
            'links': [],
            'competitor_links': [],
            'metadata': {}
        }
        
        if self.cdp_available and self.cdp:
            try:
                # Get DOM
                dom = self.cdp.get_document()
                if dom:
                    perception_data['dom'] = dom
                
                # Get clickable elements
                # This would use your existing methods
                # For now, simulate
                perception_data['clickable'] = []
                perception_data['links'] = []
                perception_data['metadata'] = {
                    'title': 'Sample Page',
                    'url': 'about:blank',
                    'has_login': False,
                    'formCount': 0
                }
            except Exception as e:
                print(f"⚠️ CDP perception error: {e}")
        
        # Extract features
        features = self.perception.extract_features(perception_data)
        
        print(f"✅ Perception: {len(features)} features extracted")
        for k, v in list(features.items())[:5]:
            print(f"   {k}: {v:.3f}")
            
        return {
            'raw': perception_data,
            'features': features
        }
    
    # ========================================================================
    # Decision Layer (MAB)
    # ========================================================================
    
    def decide(self, perception: Dict) -> Dict:
        """Decide on action using MAB + Pattern Learning"""
        print("\n🎯 Decision Layer: Choosing action...")
        
        context = perception['features']
        self.current_context = context
        
        # Get predictions from pattern learner
        predictions = self.pattern_learner.predict(context, self.action_library)
        
        # Get action from MAB
        action = self.mab.get_action(context, self.action_library)
        
        # Calculate confidence
        confidence = predictions.get(action, 0.5) * 0.7 + 0.3  # Weighted with baseline
        
        decision = {
            'action': action,
            'confidence': confidence,
            'predictions': predictions,
            'context': context,
            'timestamp': datetime.now().isoformat()
        }
        
        print(f"✅ Decision: {action} (confidence: {confidence:.2f})")
        print(f"   Predictions: {sorted(predictions.items(), key=lambda x: x[1], reverse=True)[:3]}")
        
        return decision
    
    # ========================================================================
    # Action Layer
    # ========================================================================
    
    def act(self, decision: Dict) -> Dict:
        """Execute the action"""
        print(f"\n⚡ Action Layer: Executing {decision['action']}...")
        
        start_time = time.time()
        success = False
        result = None
        
        # Simulate action execution
        # In reality, this would use CDP to interact with the page
        
        # Simulate different actions
        if decision['action'] == 'click_login':
            success = True
            result = {'message': 'Login clicked', 'url_changed': False}
        elif decision['action'] == 'click_next':
            success = True
            result = {'message': 'Next page clicked', 'url_changed': True}
        elif decision['action'] == 'extract_links':
            success = True
            result = {'links': ['link1', 'link2', 'link3'], 'count': 3}
        elif decision['action'] == 'extract_text':
            success = True
            result = {'text': 'Sample extracted text from the page', 'length': 35}
        elif decision['action'] == 'wait':
            time.sleep(0.5)
            success = True
            result = {'waited': 0.5}
        else:
            success = random.random() > 0.3  # 70% success rate
            result = {'message': f"Executed {decision['action']}", 'success': success}
        
        duration_ms = (time.time() - start_time) * 1000
        
        action_result = {
            'action': decision['action'],
            'success': success,
            'result': result,
            'duration_ms': duration_ms,
            'timestamp': datetime.now().isoformat()
        }
        
        print(f"✅ Action: {'Success' if success else 'Failed'} ({duration_ms:.0f}ms)")
        
        return action_result
    
    # ========================================================================
    # Reward Layer
    # ========================================================================
    
    def reward(self, perception_before: Dict, action_result: Dict) -> float:
        """Calculate reward for the action"""
        print(f"\n🎯 Reward Layer: Calculating reward...")
        
        # Simulate perception after action
        perception_after = self.perceive()
        
        reward = self.reward_optimizer.calculate_reward(
            action_result,
            perception_before['raw'],
            perception_after['raw']
        )
        
        print(f"✅ Reward: {reward:.2f}")
        
        return reward
    
    # ========================================================================
    # Learning Layer
    # ========================================================================
    
    def learn(self, context: Dict, action: str, reward: float, action_result: Dict):
        """Learn from the experience"""
        print(f"\n📚 Learning Layer: Updating models...")
        
        # Update MAB
        self.mab.update(context, action, reward)
        
        # Update pattern learner
        experience = {
            'context': context,
            'action': action,
            'reward': reward,
            'success': action_result.get('success', False)
        }
        self.pattern_learner.learn(experience)
        
        # Store experience
        self.experiences.append(experience)
        self.iterations += 1
        
        # Save state periodically
        if self.iterations % 10 == 0:
            self.save_state()
        
        print(f"✅ Learned from experience #{self.iterations}")
    
    # ========================================================================
    # Main Loop - The Learning Cycle
    # ========================================================================
    
    def run_cycle(self) -> Dict:
        """One complete AI cycle"""
        print("\n" + "=" * 70)
        print(f"🔄 AI CYCLE #{self.iterations + 1}")
        print("=" * 70)
        
        # 1. Perceive
        perception_before = self.perceive()
        
        # 2. Decide
        decision = self.decide(perception_before)
        
        # 3. Act
        action_result = self.act(decision)
        
        # 4. Reward
        reward = self.reward(perception_before, action_result)
        
        # 5. Learn
        self.learn(perception_before['features'], decision['action'], reward, action_result)
        
        return {
            'perception': perception_before,
            'decision': decision,
            'action': action_result,
            'reward': reward,
            'timestamp': datetime.now().isoformat()
        }
    
    def run(self, cycles: int = 10):
        """Run multiple cycles"""
        print(f"\n🚀 Running {cycles} learning cycles...")
        
        for i in range(cycles):
            try:
                self.run_cycle()
            except KeyboardInterrupt:
                print(f"\n⏹️ Stopped at cycle {i+1}")
                break
            except Exception as e:
                print(f"❌ Error in cycle {i+1}: {e}")
                continue
        
        self.save_state()
        self.generate_report()
    
    # ========================================================================
    # State Management
    # ========================================================================
    
    def save_state(self):
        """Save AI state"""
        state_file = self.session_dir / "ai_state.json"
        
        state = {
            'iterations': self.iterations,
            'mab': self.mab.get_stats(),
            'patterns': {
                'total_patterns': len(self.pattern_learner.patterns),
                'success_rate': dict(self.pattern_learner.success_rate)
            },
            'reward_weights': self.reward_optimizer.reward_weights,
            'experiences': len(self.experiences),
            'timestamp': datetime.now().isoformat()
        }
        
        with open(state_file, 'w') as f:
            json.dump(state, f, indent=2, default=str)
        
        print(f"💾 State saved: {state_file}")
    
    def generate_report(self) -> str:
        """Generate AI report"""
        report = []
        report.append("=" * 70)
        report.append("🧠 AI ORCHESTRATOR REPORT")
        report.append("=" * 70)
        
        # Statistics
        report.append(f"\n📊 Statistics:")
        report.append(f"  Iterations: {self.iterations}")
        report.append(f"  Experiences: {len(self.experiences)}")
        
        # MAB Stats
        mab_stats = self.mab.get_stats()
        report.append(f"\n🤖 MAB Stats:")
        report.append(f"  Total Arms: {mab_stats['total_arms']}")
        report.append(f"  Total Pulls: {mab_stats['total_pulls']}")
        report.append(f"  Avg Reward: {mab_stats['avg_reward']:.3f}")
        report.append(f"  Best Action: {mab_stats['best_action']}")
        
        # Reward Weights
        report.append(f"\n🎯 Reward Weights:")
        for key, value in self.reward_optimizer.reward_weights.items():
            report.append(f"  {key}: {value:.3f}")
        
        # Success Rate
        if self.pattern_learner.success_rate:
            report.append(f"\n📈 Success Rates:")
            for action in sorted(self.action_library)[:10]:
                total = self.pattern_learner.success_rate.get(action, 0)
                success = self.pattern_learner.success_rate.get(action + "_success", 0)
                if total > 0:
                    rate = success / total
                    report.append(f"  {action}: {rate*100:.1f}% ({success}/{total})")
        
        report.append("\n" + "=" * 70)
        
        # Save report
        report_file = self.session_dir / "ai_report.txt"
        with open(report_file, 'w') as f:
            f.write("\n".join(report))
        
        print("\n" + "\n".join(report))
        return "\n".join(report)


# ============================================================================
# CLI Interface
# ============================================================================

def main():
    print("🧠 AI ORCHESTRATOR - Full Stack Intelligence")
    print("=" * 70)
    print("Layers: Perception → MAB Decision → Action → Reward → Learning")
    print("=" * 70)
    
    port = int(input("🔌 Chrome port (default 9257): ").strip() or "9257")
    orchestrator = AIOrchestrator(port)
    
    while True:
        print("\n" + "=" * 70)
        print("📋 AI Commands:")
        print("  1. Run AI Cycle (Perceive → Decide → Act → Learn)")
        print("  2. Run N Cycles (auto-learning)")
        print("  3. Show MAB State")
        print("  4. Show Pattern Learner")
        print("  5. Show Reward Weights")
        print("  6. Show Action Predictions")
        print("  7. Show Experience History")
        print("  8. Generate AI Report")
        print("  9. Export State")
        print("  0. Exit")
        print("=" * 70)
        
        choice = input("Select: ").strip()
        
        if choice == "0":
            orchestrator.save_state()
            print("👋 Goodbye!")
            break
            
        elif choice == "1":
            orchestrator.run_cycle()
            
        elif choice == "2":
            cycles = int(input("Number of cycles: ").strip() or "5")
            orchestrator.run(cycles)
            
        elif choice == "3":
            stats = orchestrator.mab.get_stats()
            print("\n🤖 MAB Stats:")
            for key, value in stats.items():
                print(f"  {key}: {value}")
                
        elif choice == "4":
            print("\n📚 Pattern Learner:")
            print(f"  Total Patterns: {len(orchestrator.pattern_learner.patterns)}")
            print(f"  Success Rates:")
            for action in orchestrator.action_library[:10]:
                total = orchestrator.pattern_learner.success_rate.get(action, 0)
                success = orchestrator.pattern_learner.success_rate.get(action + "_success", 0)
                if total > 0:
                    rate = success / total
                    print(f"    {action}: {rate*100:.1f}% ({success}/{total})")
                    
        elif choice == "5":
            print("\n🎯 Reward Weights:")
            for key, value in orchestrator.reward_optimizer.reward_weights.items():
                print(f"  {key}: {value:.3f}")
                
        elif choice == "6":
            print("\n📈 Action Predictions:")
            context = orchestrator.current_context or orchestrator.perceive()['features']
            predictions = orchestrator.pattern_learner.predict(context, orchestrator.action_library)
            for action, score in sorted(predictions.items(), key=lambda x: x[1], reverse=True)[:10]:
                print(f"  {action}: {score:.3f}")
                
        elif choice == "7":
            print(f"\n💾 Experience History ({len(orchestrator.experiences)}):")
            for exp in orchestrator.experiences[-10:]:
                print(f"  [{exp.get('timestamp', '')[:19]}] {exp.get('action', '')} → {exp.get('reward', 0):.2f}")
                
        elif choice == "8":
            orchestrator.generate_report()
            
        elif choice == "9":
            orchestrator.save_state()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Interrupted")
        sys.exit(0)
