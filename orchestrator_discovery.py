#!/usr/bin/env python3
"""
Discovery-First Orchestrator - Fixed port handling
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
# Import your existing tools with port handling
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
# CDP Wrapper - Fixed port handling
# ============================================================================

class CDPWrapper:
    def __init__(self, port: int = 9257):
        self.port = port
        self.client = None
        self.connected = False
        
    def connect(self):
        """Connect using available CDP"""
        if CDP_EXTENDED_AVAILABLE:
            try:
                self.client = EnhancedChromeCDP(port=self.port)
                # Try to get tabs to verify connection
                tabs = self.client.get_tabs()
                if tabs:
                    self.connected = True
                    print(f"✅ Connected via Dynamic CDP v6 on port {self.port}")
                    return True
            except Exception as e:
                print(f"⚠️ Dynamic CDP v6 connect error: {e}")
        
        print(f"❌ Could not connect on port {self.port}")
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
        
        # Dynamic CDP v6 uses tab_index parameter
        if CDP_EXTENDED_AVAILABLE and isinstance(self.client, EnhancedChromeCDP):
            try:
                # First ensure we have a WebSocket URL
                ws_url = self.client.get_websocket_url(tab_index)
                if ws_url:
                    # Now get the accessibility tree
                    result = self.client.get_accessibility_tree(tab_index)
                    if result:
                        return result
            except Exception as e:
                print(f"⚠️ AX Tree error: {e}")
        
        return {'nodes': []}
    
    def execute_js(self, script: str, tab_index: int = 0):
        if not self.client:
            return None
        
        # Try evaluate_script method (dynamic_cdp_6)
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
# Discovery Layer - Fixed to use proper CDP
# ============================================================================

class DiscoveryLayer:
    def __init__(self, cdp: CDPWrapper):
        self.cdp = cdp
        
    def discover(self, tab_index: int = 0) -> Dict:
        """Complete discovery"""
        print("\n🗺️ DISCOVERY PHASE: Mapping the territory...")
        print("=" * 60)
        
        results = {
            'urls': [],
            'ax_tree': {'nodes': []},
            'interactive': [],
            'context': {'type': 'unknown'},
            'competitors': [],
            'forms': [],
            'navigation': [],
            'metadata': {}
        }
        
        # 1. Get Accessibility Tree (most reliable)
        print("📡 Getting Accessibility Tree...")
        ax = self.cdp.get_accessibility_tree(tab_index)
        if ax:
            results['ax_tree'] = ax
            print(f"✅ AX Tree: {len(ax.get('nodes', []))} nodes")
        else:
            print("⚠️ No AX Tree data")
        
        # 2. Get DOM
        print("📄 Getting DOM...")
        dom = self.cdp.get_document(tab_index)
        if dom:
            results['metadata']['dom_nodes'] = self._count_nodes(dom)
            print(f"✅ DOM: {results['metadata']['dom_nodes']} nodes")
        
        # 3. Extract interactive elements via JS
        print("🖱️ Finding interactive elements...")
        interactive = self._find_interactive(tab_index)
        results['interactive'] = interactive
        print(f"✅ Interactive: {len(interactive)} elements")
        
        # 4. Analyze context
        print("📊 Analyzing page context...")
        context = self._analyze_context(tab_index)
        results['context'] = context
        print(f"✅ Context: {context.get('type', 'unknown')}")
        
        # 5. Find competitors
        print("🎯 Finding competitors...")
        competitors = self._find_competitors(tab_index)
        results['competitors'] = competitors
        print(f"✅ Competitors: {len(competitors)}")
        
        # 6. Find forms
        print("📝 Finding forms...")
        forms = self._find_forms(tab_index)
        results['forms'] = forms
        print(f"✅ Forms: {len(forms)}")
        
        # 7. Find navigation
        print("🧭 Finding navigation...")
        nav = self._find_navigation(tab_index)
        results['navigation'] = nav
        print(f"✅ Navigation: {len(nav)}")
        
        print("=" * 60)
        print("✅ DISCOVERY COMPLETE")
        
        return results
    
    def _find_interactive(self, tab_index: int) -> List[Dict]:
        """Find interactive elements via JS"""
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
        except Exception as e:
            print(f"⚠️ Interactive elements error: {e}")
            return []
    
    def _analyze_context(self, tab_index: int) -> Dict:
        """Analyze page context"""
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
        except Exception as e:
            print(f"⚠️ Context analysis error: {e}")
        
        return {'type': 'unknown'}
    
    def _find_competitors(self, tab_index: int) -> List[Dict]:
        """Find competitor references"""
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
        """Find forms"""
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
        """Find navigation"""
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
    
    def _count_nodes(self, node: Dict) -> int:
        """Count nodes in DOM"""
        if not node:
            return 0
        count = 1
        for child in node.get('children', []):
            count += self._count_nodes(child)
        return count

# ============================================================================
# Action Preparer
# ============================================================================

class ActionPreparer:
    def __init__(self, discovery: Dict):
        self.discovery = discovery
        self.actions = []
    
    def prepare_actions(self) -> List[Dict]:
        """Prepare actions from discovery"""
        print("\n⚡ PREPARING ACTIONS...")
        
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
        
        # From forms
        for form in self.discovery.get('forms', []):
            actions.append({
                'type': 'form',
                'target': form.get('action', ''),
                'text': f"Form {form.get('index', 0)}",
                'priority': 'medium',
                'iife': self._generate_form_iife(form)
            })
        
        self.actions = actions
        print(f"✅ Prepared {len(actions)} actions")
        return actions
    
    def _prepare_element_action(self, el: Dict) -> Optional[Dict]:
        """Prepare action for element"""
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
        """Generate click IIFE"""
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
        """Generate navigation IIFE"""
        return f"""
        (function() {{
            window.location.href = '{url}';
            return {{ success: true }};
        }})()
        """
    
    def _generate_form_iife(self, form: Dict) -> str:
        """Generate form IIFE"""
        return f"""
        (function() {{
            const forms = document.querySelectorAll('form');
            const form = forms[{form.get('index', 0)}];
            if (!form) return {{ success: false }};
            form.submit();
            return {{ success: true }};
        }})()
        """
    
    def _determine_priority(self, el: Dict) -> str:
        """Determine priority"""
        text = el.get('text', '').lower()
        if 'login' in text or 'sign in' in text:
            return 'high'
        if 'search' in text:
            return 'high'
        if 'next' in text or 'more' in text:
            return 'medium'
        return 'low'


# ============================================================================
# MAB Contextual
# ============================================================================

class ContextualMAB:
    def __init__(self):
        self.arms = defaultdict(lambda: {'success': 0, 'total': 0, 'reward_sum': 0})
    
    def update(self, context: Dict, action: str, reward: float):
        arm = self.arms[action]
        arm['total'] += 1
        arm['reward_sum'] += reward
        if reward > 0:
            arm['success'] += 1
    
    def get_score(self, action: str) -> float:
        arm = self.arms[action]
        if arm['total'] == 0:
            return 0.5
        return arm['reward_sum'] / arm['total']
    
    def get_stats(self) -> Dict:
        return {
            'total_arms': len(self.arms),
            'total_pulls': sum(a['total'] for a in self.arms.values()),
            'avg_reward': sum(a['reward_sum'] for a in self.arms.values()) / 
                         max(1, sum(a['total'] for a in self.arms.values()))
        }


# ============================================================================
# Discovery Orchestrator
# ============================================================================

class DiscoveryOrchestrator:
    def __init__(self, port: int = 9257, session_dir: str = None):
        self.port = port
        self.session_dir = Path(session_dir or f"discovery_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        self.session_dir.mkdir(parents=True, exist_ok=True)
        
        # CDP
        self.cdp = CDPWrapper(port)
        self.discovery = None
        self.actions = []
        self.experiences = []
        self.iterations = 0
        self.mab = ContextualMAB()
        
        print(f"🧠 Discovery Orchestrator initialized")
        print(f"📁 Session: {self.session_dir}")
        print(f"🔌 Port: {self.port}")
    
    def connect(self) -> bool:
        """Connect to Chrome"""
        return self.cdp.connect()
    
    def run_cycle(self) -> Dict:
        """Full cycle"""
        print("\n" + "=" * 70)
        print(f"🔄 CYCLE #{self.iterations + 1}")
        print("=" * 70)
        
        # 1. Discover
        discovery_layer = DiscoveryLayer(self.cdp)
        self.discovery = discovery_layer.discover()
        self._save_discovery()
        
        # 2. Prepare
        preparer = ActionPreparer(self.discovery)
        self.actions = preparer.prepare_actions()
        self._save_actions()
        
        # 3. Decide
        if not self.actions:
            print("❌ No actions to decide")
            return {'error': 'No actions'}
        
        context = self.discovery.get('context', {})
        action = self.actions[0]  # Simple: pick first
        decision = {
            'action': action,
            'context': context,
            'timestamp': datetime.now().isoformat()
        }
        print(f"✅ Decided: {action.get('type')} - {action.get('text', action.get('target', ''))[:50]}")
        
        # 4. Act
        print("\n⚡ Executing action...")
        iife = action.get('iife', '')
        result = None
        success = False
        
        if iife:
            try:
                result = self.cdp.execute_js(iife)
                success = bool(result and result.get('success', False))
            except Exception as e:
                print(f"❌ Execution error: {e}")
        else:
            success = True
            result = {'success': True, 'simulated': True}
        
        action_result = {
            'action': action,
            'success': success,
            'result': result,
            'duration_ms': 0,
            'timestamp': datetime.now().isoformat()
        }
        print(f"✅ {'Success' if success else 'Failed'}")
        
        # 5. Learn
        reward = 1.0 if success else -0.5
        self.mab.update(context, action.get('type', 'unknown'), reward)
        
        experience = {
            'context': context,
            'action': action,
            'reward': reward,
            'timestamp': datetime.now().isoformat()
        }
        self.experiences.append(experience)
        self.iterations += 1
        print(f"📚 Learned: Reward {reward:.2f}")
        
        self.save_state()
        
        return {
            'discovery': self.discovery,
            'decision': decision,
            'action_result': action_result,
            'reward': reward
        }
    
    def _save_discovery(self):
        if self.discovery:
            with open(self.session_dir / "discovery.json", 'w') as f:
                json.dump(self.discovery, f, indent=2, default=str)
    
    def _save_actions(self):
        if self.actions:
            with open(self.session_dir / "actions.json", 'w') as f:
                json.dump(self.actions, f, indent=2, default=str)
    
    def save_state(self):
        state = {
            'iterations': self.iterations,
            'experiences': len(self.experiences),
            'actions': len(self.actions),
            'mab_stats': self.mab.get_stats(),
            'timestamp': datetime.now().isoformat()
        }
        with open(self.session_dir / "state.json", 'w') as f:
            json.dump(state, f, indent=2, default=str)
        print(f"💾 State saved")
    
    def generate_report(self) -> str:
        report = []
        report.append("=" * 70)
        report.append("🗺️ DISCOVERY REPORT")
        report.append("=" * 70)
        
        if self.discovery:
            report.append(f"\n📊 Discovery Results:")
            report.append(f"  AX Nodes: {len(self.discovery.get('ax_tree', {}).get('nodes', []))}")
            report.append(f"  Interactive: {len(self.discovery.get('interactive', []))}")
            report.append(f"  Page Type: {self.discovery.get('context', {}).get('type', 'unknown')}")
            report.append(f"  Competitors: {len(self.discovery.get('competitors', []))}")
            report.append(f"  Forms: {len(self.discovery.get('forms', []))}")
        
        report.append(f"\n⚡ Actions: {len(self.actions)}")
        report.append(f"📚 Experiences: {len(self.experiences)}")
        
        stats = self.mab.get_stats()
        report.append(f"\n🤖 MAB: {stats.get('total_arms', 0)} arms, {stats.get('total_pulls', 0)} pulls")
        
        report.append("\n" + "=" * 70)
        return "\n".join(report)


# ============================================================================
# Main
# ============================================================================

def main():
    print("🗺️ DISCOVERY-FIRST ORCHESTRATOR (FIXED)")
    print("=" * 70)
    
    port = int(input("🔌 Chrome port (default 9257): ").strip() or "9257")
    orchestrator = DiscoveryOrchestrator(port)
    
    if not orchestrator.connect():
        print("❌ Failed to connect. Make sure Chrome is running with:")
        print(f"   chromium-browser --remote-debugging-port={port}")
        return
    
    while True:
        print("\n" + "=" * 70)
        print("📋 Commands:")
        print("  1. Full Discovery Cycle")
        print("  2. Discover Only")
        print("  3. Show Discovery Results")
        print("  4. Show Actions")
        print("  5. Show MAB State")
        print("  6. Generate Report")
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
            discovery = DiscoveryLayer(orchestrator.cdp)
            orchestrator.discovery = discovery.discover()
            orchestrator._save_discovery()
            print("✅ Discovery complete")
        elif choice == "3":
            if orchestrator.discovery:
                d = orchestrator.discovery
                print(f"\n🗺️ Discovery Results:")
                print(f"  AX Nodes: {len(d.get('ax_tree', {}).get('nodes', []))}")
                print(f"  Interactive: {len(d.get('interactive', []))}")
                print(f"  Page Type: {d.get('context', {}).get('type', 'unknown')}")
                print(f"  Competitors: {len(d.get('competitors', []))}")
                print(f"  Forms: {len(d.get('forms', []))}")
            else:
                print("❌ No discovery results")
        elif choice == "4":
            if orchestrator.actions:
                print(f"\n⚡ Actions ({len(orchestrator.actions)}):")
                for i, action in enumerate(orchestrator.actions[:10], 1):
                    print(f"  {i}. {action.get('type')}: {action.get('text', action.get('target', ''))[:50]}")
            else:
                print("❌ No actions")
        elif choice == "5":
            stats = orchestrator.mab.get_stats()
            print("\n🤖 MAB State:")
            for key, value in stats.items():
                print(f"  {key}: {value}")
        elif choice == "6":
            print("\n" + orchestrator.generate_report())

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Interrupted")
        sys.exit(0)
