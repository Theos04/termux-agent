ACTION_DELAY = 12
#!/usr/bin/env python3
"""
Agent Orchestrator - Continuous Discovery → Action → Learning Loop
Runs multiple cycles, each time discovering the page state, choosing an action, executing it, and learning
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

# ============================================================================
# Import your existing tools
# ============================================================================

try:
    from dynamic_cdp_6 import EnhancedChromeCDP
    CDP_EXTENDED_AVAILABLE = True
    print("✅ Dynamic CDP v6 loaded")
except ImportError:
    CDP_EXTENDED_AVAILABLE = False
    print("⚠️ Dynamic CDP v6 not found")

try:
    from geturl import ChromePage, DOMExplorer
    DOM_EXPLORER_AVAILABLE = True
    print("✅ GetURL loaded")
except ImportError:
    DOM_EXPLORER_AVAILABLE = False
    print("⚠️ GetURL not found")

# ============================================================================
# CDP Wrapper
# ============================================================================

class CDPWrapper:
    def __init__(self, port: int = 9257):
        self.port = port
        self.client = None
        self.connected = False
        
    def connect(self):
        if CDP_EXTENDED_AVAILABLE:
            try:
                self.client = EnhancedChromeCDP(port=self.port)
                tabs = self.client.get_tabs()
                if tabs:
                    self.connected = True
                    print(f"✅ Connected on port {self.port}")
                    return True
            except Exception as e:
                print(f"⚠️ Connect error: {e}")
        return False
    
    def get_tabs(self):
        if not self.client:
            return []
        if hasattr(self.client, 'get_tabs'):
            return self.client.get_tabs()
        return []
    
    def get_accessibility_tree(self, tab_index: int = 0):
        if not self.client:
            return {'nodes': []}
        if CDP_EXTENDED_AVAILABLE and isinstance(self.client, EnhancedChromeCDP):
            try:
                ws_url = self.client.get_websocket_url(tab_index)
                if ws_url:
                    result = self.client.get_accessibility_tree(tab_index)
                    if result:
                        return result
            except Exception as e:
                print(f"⚠️ AX Tree error: {e}")
        return {'nodes': []}
    
    def execute_js(self, script: str, tab_index: int = 0):
        if not self.client:
            return None
        if hasattr(self.client, 'evaluate_script'):
            try:
                return self.client.evaluate_script(script, tab_index)
            except:
                pass
        return None
    
    def get_document(self, tab_index: int = 0):
        if not self.client:
            return None
        if hasattr(self.client, 'get_document'):
            try:
                return self.client.get_document(tab_index)
            except:
                pass
        return None
    
    def disconnect(self):
        if self.client and hasattr(self.client, 'close_session'):
            try:
                self.client.close_session()
            except:
                pass
        self.connected = False

# ============================================================================
# Discovery Layer
# ============================================================================

class DiscoveryLayer:
    def __init__(self, cdp: CDPWrapper):
        self.cdp = cdp
        
    def discover(self, tab_index: int = 0) -> Dict:
        """Complete discovery of current page state"""
        results = {
            'ax_tree': {'nodes': []},
            'interactive': [],
            'context': {'type': 'unknown'},
            'competitors': [],
            'forms': [],
            'navigation': [],
            'url': '',
            'title': ''
        }
        
        # Get Accessibility Tree
        ax = self.cdp.get_accessibility_tree(tab_index)
        if ax:
            results['ax_tree'] = ax
        
        # Get interactive elements
        interactive = self._find_interactive(tab_index)
        results['interactive'] = interactive
        
        # Get context
        context = self._analyze_context(tab_index)
        results['context'] = context
        results['url'] = context.get('url', '')
        results['title'] = context.get('title', '')
        
        # Get competitors
        results['competitors'] = self._find_competitors(tab_index)
        
        # Get forms
        results['forms'] = self._find_forms(tab_index)
        
        # Get navigation
        results['navigation'] = self._find_navigation(tab_index)
        
        return results
    
    def _find_interactive(self, tab_index: int) -> List[Dict]:
        script = """
        (function() {
            const results = [];
            const selectors = [
                'button', 'a[href]', '[role="button"]', '[role="link"]',
                'input[type="submit"]', 'input[type="button"]',
                '[onclick]', '[data-action]', '.btn'
            ];
            
            document.querySelectorAll(selectors.join(',')).forEach((el, idx) => {
                const rect = el.getBoundingClientRect();
                results.push({
                    index: idx,
                    tag: el.tagName.toLowerCase(),
                    text: el.textContent.trim().substring(0, 100),
                    visible: rect.width > 0 && rect.height > 0,
                    selector: el.id ? '#' + el.id : null,
                    href: el.getAttribute('href') || null,
                    role: el.getAttribute('role') || null,
                    aria_label: el.getAttribute('aria-label') || null
                });
            });
            return results;
        })()
        """
        try:
            result = self.cdp.execute_js(script, tab_index)
            return result if result else []
        except:
            return []
    
    def _analyze_context(self, tab_index: int) -> Dict:
        script = """
        (function() {
            return {
                title: document.title || '',
                url: window.location.href || '',
                domain: window.location.hostname || '',
                has_login: document.querySelectorAll('input[type="password"]').length > 0,
                has_search: document.querySelectorAll('input[type="search"], input[name*="search"]').length > 0,
                has_pagination: document.querySelectorAll('a[rel="next"], .pagination, .next').length > 0,
                has_forms: document.querySelectorAll('form').length > 0,
                word_count: document.body ? document.body.innerText.split(/\\s+/).length : 0
            };
        })()
        """
        try:
            result = self.cdp.execute_js(script, tab_index)
            if result:
                if result.get('has_login'):
                    result['type'] = 'login'
                elif result.get('has_pagination') and result.get('has_forms'):
                    result['type'] = 'listing'
                elif result.get('has_forms'):
                    result['type'] = 'form'
                elif result.get('has_search'):
                    result['type'] = 'search'
                else:
                    result['type'] = 'content'
                return result
        except:
            pass
        return {'type': 'unknown'}
    
    def _find_competitors(self, tab_index: int) -> List[Dict]:
        script = """
        (function() {
            const keywords = ['competitor', 'alternative', 'vs', 'compare', 'similar'];
            const results = [];
            document.querySelectorAll('a, p, div').forEach(el => {
                const text = el.textContent.toLowerCase();
                if (keywords.some(kw => text.includes(kw))) {
                    results.push({
                        text: el.textContent.trim().substring(0, 200),
                        href: el.getAttribute('href') || ''
                    });
                }
            });
            return results;
        })()
        """
        try:
            result = self.cdp.execute_js(script, tab_index)
            return result if result else []
        except:
            return []
    
    def _find_forms(self, tab_index: int) -> List[Dict]:
        script = """
        (function() {
            const results = [];
            document.querySelectorAll('form').forEach((form, idx) => {
                const inputs = form.querySelectorAll('input, select, textarea');
                results.push({
                    index: idx,
                    action: form.getAttribute('action') || '',
                    method: form.getAttribute('method') || 'GET',
                    inputs: Array.from(inputs).map(inp => ({
                        type: inp.getAttribute('type') || inp.tagName.toLowerCase(),
                        name: inp.getAttribute('name') || '',
                        required: inp.hasAttribute('required')
                    }))
                });
            });
            return results;
        })()
        """
        try:
            result = self.cdp.execute_js(script, tab_index)
            return result if result else []
        except:
            return []
    
    def _find_navigation(self, tab_index: int) -> List[Dict]:
        script = """
        (function() {
            const results = [];
            document.querySelectorAll('nav, .nav, #nav, [role="navigation"]').forEach(el => {
                const links = el.querySelectorAll('a[href]');
                results.push({
                    element: el.tagName,
                    links: Array.from(links).map(link => ({
                        text: link.textContent.trim(),
                        href: link.getAttribute('href') || ''
                    }))
                });
            });
            return results;
        })()
        """
        try:
            result = self.cdp.execute_js(script, tab_index)
            return result if result else []
        except:
            return []

# ============================================================================
# Action Preparer - Creates IIFE-ready actions from discovery
# ============================================================================

class ActionPreparer:
    def __init__(self, discovery: Dict):
        self.discovery = discovery
        self.actions = []
    
    def prepare_actions(self) -> List[Dict]:
        actions = []
        
        # From interactive elements
        for el in self.discovery.get('interactive', []):
            if el.get('visible', False):
                action = self._prepare_element_action(el)
                if action:
                    actions.append(action)
        
        # From navigation
        for nav in self.discovery.get('navigation', []):
            for link in nav.get('links', []):
                if link.get('href'):
                    actions.append({
                        'type': 'navigate',
                        'target': link.get('href'),
                        'text': link.get('text', ''),
                        'priority': 'medium',
                        'iife': self._generate_navigate_iife(link.get('href'))
                    })
        
        self.actions = actions
        return actions
    
    def _prepare_element_action(self, el: Dict) -> Optional[Dict]:
        tag = el.get('tag', '')
        text = el.get('text', '')
        selector = el.get('selector')
        href = el.get('href')
        
        if tag == 'a' and href:
            return {
                'type': 'navigate',
                'target': href,
                'text': text,
                'priority': 'high' if 'login' in text.lower() else 'medium',
                'iife': self._generate_navigate_iife(href)
            }
        else:
            return {
                'type': 'click',
                'target': selector or text,
                'text': text,
                'priority': self._determine_priority(el),
                'iife': self._generate_click_iife(selector or text)
            }
    
    def _generate_click_iife(self, target: str) -> str:
        if target and target.startswith('#'):
            return f"""
            (function() {{
                const el = document.querySelector('{target}');
                if (el) {{
                    el.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                    setTimeout(() => el.click(), 100);
                    return {{ success: true }};
                }}
                return {{ success: false }};
            }})()
            """
        else:
            safe_target = target.replace("'", "\\'") if target else ''
            return f"""
            (function() {{
                const elements = document.querySelectorAll('button, a, [role="button"]');
                for (let el of elements) {{
                    if (el.textContent.trim() === '{safe_target}') {{
                        el.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                        setTimeout(() => el.click(), 100);
                        return {{ success: true }};
                    }}
                }}
                return {{ success: false }};
            }})()
            """
    
    def _generate_navigate_iife(self, url: str) -> str:
        return f"""
        (function() {{
            window.location.href = '{url}';
            return {{ success: true }};
        }})()
        """
    
    def _determine_priority(self, el: Dict) -> str:
        text = el.get('text', '').lower()
        if 'login' in text or 'sign in' in text:
            return 'high'
        if 'search' in text:
            return 'high'
        if 'next' in text or 'more' in text:
            return 'medium'
        return 'low'

# ============================================================================
# MAB - Multi-Armed Bandit
# ============================================================================

class ContextualMAB:
    def __init__(self):
        self.arms = defaultdict(lambda: {'success': 0, 'total': 0, 'reward_sum': 0})
        self.action_history = []
    
    def choose_action(self, actions: List[Dict]) -> Dict:
        """Choose the best action using UCB"""
        if not actions:
            return None
        
        # If we have few experiences, explore
        if len(self.action_history) < 5:
            return random.choice(actions)
        
        # Calculate UCB scores
        best_action = None
        best_score = -float('inf')
        
        for action in actions:
            action_type = action.get('type', 'unknown')
            arm = self.arms[action_type]
            
            if arm['total'] == 0:
                score = 1.0  # Explore untested actions
            else:
                success_rate = arm['success'] / arm['total']
                exploration = math.sqrt(2 * math.log(len(self.action_history) + 1) / arm['total'])
                score = success_rate + exploration
            
            # Add priority bonus
            priority_bonus = {'high': 0.3, 'medium': 0.1, 'low': 0}.get(action.get('priority', 'low'), 0)
            score += priority_bonus
            
            if score > best_score:
                best_score = score
                best_action = action
        
        return best_action
    
    def update(self, action_type: str, success: bool, reward: float):
        """Update arm statistics"""
        arm = self.arms[action_type]
        arm['total'] += 1
        arm['reward_sum'] += reward
        if success:
            arm['success'] += 1
        
        self.action_history.append({
            'action': action_type,
            'success': success,
            'reward': reward,
            'timestamp': datetime.now().isoformat()
        })
    
    def get_stats(self) -> Dict:
        return {
            'total_arms': len(self.arms),
            'total_pulls': sum(a['total'] for a in self.arms.values()),
            'avg_reward': sum(a['reward_sum'] for a in self.arms.values()) / 
                         max(1, sum(a['total'] for a in self.arms.values())),
            'arms': {k: {'success': v['success'], 'total': v['total'], 
                        'rate': v['success']/v['total'] if v['total'] > 0 else 0}
                    for k, v in self.arms.items()}
        }

# ============================================================================
# Agent - The Main Loop
# ============================================================================

class Agent:
    """
    The Agent runs a continuous loop:
    1. Discover current page state
    2. Prepare actions from discovery
    3. MAB chooses best action
    4. Execute the action
    5. Discover new state (page may have changed)
    6. Learn from the experience
    7. Repeat
    """
    
    def __init__(self, port: int = 9257, max_actions: int = 20):
        self.port = port
        self.max_actions = max_actions
        self.session_dir = Path(f"agent_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        self.session_dir.mkdir(parents=True, exist_ok=True)
        
        self.cdp = CDPWrapper(port)
        self.mab = ContextualMAB()
        self.experiences = []
        self.action_count = 0
        self.success_count = 0
        
        print(f"🤖 Agent initialized")
        print(f"📁 Session: {self.session_dir}")
        print(f"📊 Max actions: {max_actions}")
    
    def connect(self) -> bool:
        return self.cdp.connect()
    
    def run(self):
        """Main agent loop"""
        print("\n" + "=" * 70)
        print("🤖 AGENT RUNNING - Continuous Discovery → Action → Learning")
        print("=" * 70)
        
        for cycle in range(self.max_actions):
            print(f"\n🔄 CYCLE {cycle + 1}/{self.max_actions}")
            print("-" * 50)
            
            try:
                # 1. Discover current state
                print("📡 Discovering page state...")
                discovery = DiscoveryLayer(self.cdp).discover()
                print(f"   📍 URL: {discovery.get('url', 'unknown')[:60]}")
                print(f"   🖱️ Interactive: {len(discovery.get('interactive', []))}")
                print(f"   📄 Type: {discovery.get('context', {}).get('type', 'unknown')}")
                
                # 2. Prepare actions
                preparer = ActionPreparer(discovery)
                actions = preparer.prepare_actions()
                print(f"   ⚡ Actions prepared: {len(actions)}")
                
                if not actions:
                    print("   ⚠️ No actions available, waiting...")
                    time.sleep(2)
                    continue
                
                # 3. MAB chooses action
                action = self.mab.choose_action(actions)
                if not action:
                    print("   ⚠️ No action chosen, waiting...")
                    time.sleep(2)
                    continue
                
                print(f"   🎯 Chosen: {action.get('type')} - {action.get('text', action.get('target', ''))[:50]}")
                
                # 4. Execute action
                iife = action.get('iife', '')
                success = False
                result = None
                
                if iife:
                    try:
                        result = self.cdp.execute_js(iife)
                        time.sleep(ACTION_DELAY)
                        success = bool(result and result.get('success', False))
                    except Exception as e:
                        print(f"   ❌ Execution error: {e}")
                        success = False
                else:
                    success = True
                    result = {'simulated': True}
                
                # 5. Discover new state (page may have changed)
                time.sleep(2)  # Wait for page to settle
                new_discovery = DiscoveryLayer(self.cdp).discover()
                
                # 6. Calculate reward
                reward = 1.0 if success else -0.5
                if success and new_discovery.get('url') != discovery.get('url'):
                    reward += 0.5  # Bonus for navigation
                
                # 7. Learn
                self.mab.update(action.get('type', 'unknown'), success, reward)
                
                # Store experience
                experience = {
                    'cycle': cycle + 1,
                    'action': action.get('type'),
                    'target': action.get('text', action.get('target', '')),
                    'success': success,
                    'reward': reward,
                    'url_before': discovery.get('url'),
                    'url_after': new_discovery.get('url'),
                    'timestamp': datetime.now().isoformat()
                }
                self.experiences.append(experience)
                
                self.action_count += 1
                if success:
                    self.success_count += 1
                
                print(f"   📊 Reward: {reward:.2f} | Success: {'✅' if success else '❌'}")
                print(f"   📈 Success rate: {self.success_count}/{self.action_count} ({100*self.success_count/self.action_count:.1f}%)")
                
                # Save state periodically
                if (cycle + 1) % 5 == 0:
                    self.save_state()
                
            except KeyboardInterrupt:
                print(f"\n⏹️ Stopped at cycle {cycle + 1}")
                break
            except Exception as e:
                print(f"   ❌ Error: {e}")
                time.sleep(2)
                continue
        
        # Final save and report
        self.save_state()
        self.generate_report()
    
    def save_state(self):
        state = {
            'action_count': self.action_count,
            'success_count': self.success_count,
            'experiences': len(self.experiences),
            'mab_stats': self.mab.get_stats(),
            'timestamp': datetime.now().isoformat()
        }
        with open(self.session_dir / "state.json", 'w') as f:
            json.dump(state, f, indent=2, default=str)
        print(f"💾 State saved")
    
    def generate_report(self):
        report = []
        report.append("=" * 70)
        report.append("🤖 AGENT REPORT")
        report.append("=" * 70)
        report.append(f"Total Actions: {self.action_count}")
        report.append(f"Success Rate: {self.success_count}/{self.action_count} ({100*self.success_count/self.action_count:.1f}%)")
        
        stats = self.mab.get_stats()
        report.append(f"\n📊 MAB Stats:")
        report.append(f"  Total Arms: {stats['total_arms']}")
        report.append(f"  Total Pulls: {stats['total_pulls']}")
        report.append(f"  Avg Reward: {stats['avg_reward']:.3f}")
        
        if stats.get('arms'):
            report.append(f"\n📈 Arm Performance:")
            for arm, data in sorted(stats['arms'].items(), key=lambda x: x[1]['rate'], reverse=True):
                report.append(f"  {arm}: {data['rate']*100:.1f}% ({data['success']}/{data['total']})")
        
        report.append("\n" + "=" * 70)
        
        # Save report
        with open(self.session_dir / "report.txt", 'w') as f:
            f.write("\n".join(report))
        print("\n" + "\n".join(report))

# ============================================================================
# Main
# ============================================================================

def main():
    print("🤖 AGENT - Continuous Discovery → Action → Learning")
    print("=" * 70)
    
    port = int(input("🔌 Chrome port (default 9257): ").strip() or "9257")
    max_actions = int(input("📊 Max actions (default 20): ").strip() or "20")
    
    agent = Agent(port, max_actions)
    
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
