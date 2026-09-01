#!/usr/bin/env python3
"""
Run complete analysis pipeline on session data
Supports organized directory structure:
- dom_trees/ for DOM data
- accessibility/ for AX data  
- snapshots/ for snapshot data
- computed_styles/ for styles
- logs/ for session logs
"""

import json
import sys
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List

# Import all modules
try:
    from dom_analysis import analyze_page, decide_action
    from accessibility_analysis import analyze_accessibility
    from context_understanding import ContextAnalyzer
except ImportError as e:
    print(f"⚠️ Import error: {e}")
    print("Make sure all modules are in the same directory")
    sys.exit(1)


class SessionAnalyzer:
    """Complete analysis pipeline for a session with organized data"""
    
    # File patterns and their subdirectories
    DATA_PATTERNS = {
        'dom': {
            'patterns': ['dom_*.json', 'dom_tree_*.json'],
            'dirs': ['dom_trees', '.', 'dom']
        },
        'accessibility': {
            'patterns': ['a11y_*.json', 'accessibility_*.json', 'ax_*.json'],
            'dirs': ['accessibility', '.', 'ax']
        },
        'snapshot': {
            'patterns': ['snapshot_*.json', 'dom_snapshot_*.json'],
            'dirs': ['snapshots', '.', 'snapshot']
        },
        'computed_styles': {
            'patterns': ['styles_*.json', 'computed_*.json'],
            'dirs': ['computed_styles', '.', 'styles']
        }
    }
    
    def __init__(self, session_path: str):
        self.session_path = Path(session_path)
        self.dom_data = None
        self.ax_data = None
        self.snapshot_data = None
        self.styles_data = None
        self.results = {}
        self.files_found = {}
        
        self._load_data()
    
    def _find_files(self, data_type: str) -> List[Path]:
        """Find files of a specific type in organized directories"""
        found_files = []
        config = self.DATA_PATTERNS.get(data_type, {})
        
        patterns = config.get('patterns', [])
        directories = config.get('dirs', ['.'])
        
        for dir_name in directories:
            search_dir = self.session_path / dir_name
            if search_dir.exists():
                for pattern in patterns:
                    found_files.extend(list(search_dir.glob(pattern)))
        
        # Sort by modification time (newest first)
        found_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        return found_files
    
    def _load_data(self):
        """Load all data files from organized session"""
        print(f"📁 Loading session: {self.session_path}")
        
        if not self.session_path.exists():
            print(f"  ❌ Session directory not found: {self.session_path}")
            return
        
        # Show directory structure
        print(f"  📂 Session structure:")
        for item in self.session_path.iterdir():
            if item.is_dir():
                files = list(item.glob('*.json'))
                print(f"     📁 {item.name}/ ({len(files)} files)")
            elif item.suffix == '.json':
                print(f"     📄 {item.name}")
        print()
        
        # 1. Load DOM tree
        dom_files = self._find_files('dom')
        if dom_files:
            try:
                with open(dom_files[0]) as f:
                    self.dom_data = json.load(f)
                self.files_found['dom'] = dom_files[0].name
                print(f"  ✅ DOM data: {len(self.dom_data.get('children', []))} top nodes")
                print(f"     📄 From: {dom_files[0].parent.name}/{dom_files[0].name}")
            except Exception as e:
                print(f"  ⚠️ Could not load DOM data: {e}")
        else:
            print("  ⚠️ No DOM tree found")
        
        # 2. Load Accessibility tree
        ax_files = self._find_files('accessibility')
        if ax_files:
            try:
                with open(ax_files[0]) as f:
                    self.ax_data = json.load(f)
                self.files_found['accessibility'] = ax_files[0].name
                print(f"  ✅ Accessibility data: {len(self.ax_data.get('nodes', []))} nodes")
                print(f"     📄 From: {ax_files[0].parent.name}/{ax_files[0].name}")
            except Exception as e:
                print(f"  ⚠️ Could not load accessibility data: {e}")
        else:
            print("  ⚠️ No accessibility tree found")
        
        # 3. Load Snapshot
        snapshot_files = self._find_files('snapshot')
        if snapshot_files:
            try:
                with open(snapshot_files[0]) as f:
                    self.snapshot_data = json.load(f)
                self.files_found['snapshot'] = snapshot_files[0].name
                print(f"  ✅ Snapshot data loaded")
                print(f"     📄 From: {snapshot_files[0].parent.name}/{snapshot_files[0].name}")
            except Exception as e:
                print(f"  ⚠️ Could not load snapshot data: {e}")
        
        # 4. Load Computed Styles (optional)
        styles_files = self._find_files('computed_styles')
        if styles_files:
            try:
                with open(styles_files[0]) as f:
                    self.styles_data = json.load(f)
                self.files_found['styles'] = styles_files[0].name
                print(f"  ✅ Styles data loaded")
                print(f"     📄 From: {styles_files[0].parent.name}/{styles_files[0].name}")
            except Exception as e:
                print(f"  ⚠️ Could not load styles data: {e}")
    
    def analyze(self) -> Dict:
        """Run complete analysis pipeline"""
        print("\n🔍 Running analysis pipeline...")
        
        # 1. DOM Analysis
        if self.dom_data:
            try:
                print("  📄 DOM Analysis...")
                dom_result = analyze_page(self.dom_data)
                self.results['dom'] = dom_result
                dom_decision = decide_action(dom_result)
                self.results['dom_decision'] = dom_decision
                print(f"     ✓ Page Type: {dom_result.get('page_type')}")
                print(f"     ✓ Nodes: {dom_result.get('node_count')}")
                print(f"     ✓ Recommended: {dom_decision}")
            except Exception as e:
                print(f"  ⚠️ DOM Analysis error: {e}")
        
        # 2. Accessibility Analysis
        if self.ax_data:
            try:
                print("  ♿ Accessibility Analysis...")
                ax_result = analyze_accessibility(self.ax_data)
                self.results['accessibility'] = ax_result
                print(f"     ✓ AX Nodes: {ax_result.get('total_nodes')}")
                print(f"     ✓ Buttons: {ax_result.get('buttons')}")
                print(f"     ✓ Headings: {ax_result.get('headings')}")
            except Exception as e:
                print(f"  ⚠️ Accessibility Analysis error: {e}")
        
        # 3. Context Understanding
        if self.dom_data and self.ax_data:
            try:
                print("  🧠 Context Understanding...")
                context_analyzer = ContextAnalyzer(self.dom_data, self.ax_data, self.snapshot_data)
                context = context_analyzer.analyze()
                self.results['context'] = {
                    'page_type': context.page_type,
                    'purpose': context.purpose,
                    'main_action': context.main_action,
                    'confidence': context.confidence,
                    'job_listings_count': len(context.job_listings),
                    'job_listings': context.job_listings[:5],
                    'key_companies': context.key_companies[:5],
                    'primary_actions': context.primary_actions[:5]
                }
                print(f"     ✓ Page Purpose: {context.purpose[:50]}")
                print(f"     ✓ Job Listings: {len(context.job_listings)}")
                print(f"     ✓ Confidence: {context.confidence:.2f}")
            except Exception as e:
                print(f"  ⚠️ Context Analysis error: {e}")
        
        # 4. Summary
        self.results['summary'] = self._generate_summary()
        self.results['files'] = self.files_found  # Track what files were used
        
        return self.results
    
    def _generate_summary(self) -> Dict:
        """Generate high-level summary"""
        summary = {
            'timestamp': datetime.now().isoformat(),
            'page_type': 'unknown',
            'actionable': False,
            'complexity': 0.0,
            'job_listings': 0,
            'primary_action': None,
            'has_data': bool(self.dom_data or self.ax_data),
            'files_used': self.files_found
        }
        
        # Get from context
        context = self.results.get('context', {})
        if context:
            summary['page_type'] = context.get('page_type', 'unknown')
            summary['job_listings'] = context.get('job_listings_count', 0)
            summary['primary_action'] = context.get('main_action')
            summary['actionable'] = context.get('confidence', 0) > 0.5
        
        # Get from DOM
        dom = self.results.get('dom', {})
        if dom:
            summary['complexity'] = dom.get('complexity', 0)
            summary['interactive_count'] = dom.get('interactive_count', 0)
        
        return summary
    
    def print_report(self):
        """Print human-readable report"""
        print("\n" + "="*70)
        print("📊 PAGE ANALYSIS REPORT")
        print("="*70)
        
        # Files used
        if self.files_found:
            print("\n📁 DATA SOURCES:")
            for data_type, filename in self.files_found.items():
                print(f"  {data_type}: {filename}")
        
        # Check if we have data
        if not self.results.get('summary', {}).get('has_data', False):
            print("\n⚠️ No data loaded. Run a session capture first.")
            return
        
        # Summary
        summary = self.results.get('summary', {})
        print(f"\n📌 OVERVIEW:")
        print(f"  Page Type: {summary.get('page_type', 'unknown')}")
        print(f"  Complexity Score: {summary.get('complexity', 0):.2f}")
        print(f"  Actionable: {'✅' if summary.get('actionable') else '❌'}")
        print(f"  Job Listings Found: {summary.get('job_listings', 0)}")
        
        # DOM Analysis
        dom = self.results.get('dom', {})
        if dom:
            print(f"\n📄 DOM STRUCTURE:")
            print(f"  Total Nodes: {dom.get('node_count', 0)}")
            print(f"  Interactive Elements: {dom.get('interactive_count', 0)}")
            print(f"  Forms: {'✅' if dom.get('has_forms') else '❌'}")
            print(f"  Search: {'✅' if dom.get('has_search') else '❌'}")
            print(f"  Navigation: {'✅' if dom.get('has_navigation') else '❌'}")
            
            # Decision
            decision = self.results.get('dom_decision', 'unknown')
            print(f"\n🎯 RECOMMENDED ACTION: {decision}")
        
        # Accessibility
        ax = self.results.get('accessibility', {})
        if ax:
            print(f"\n♿ ACCESSIBILITY:")
            print(f"  Semantic Nodes: {ax.get('total_nodes', 0)}")
            print(f"  Buttons: {ax.get('buttons', 0)}")
            print(f"  Headings: {ax.get('headings', 0)}")
            print(f"  Links: {ax.get('links', 0)}")
            print(f"  Form Fields: {ax.get('form_fields', 0)}")
            if ax.get('top_roles'):
                print(f"  Top Roles: {dict(list(ax.get('top_roles', {}).items())[:5])}")
        
        # Context
        context = self.results.get('context', {})
        if context:
            print(f"\n🧠 CONTEXT:")
            print(f"  Purpose: {context.get('purpose', 'Unknown')}")
            print(f"  Main Action: {context.get('main_action', 'Unknown')}")
            print(f"  Confidence: {context.get('confidence', 0):.2f}")
        
        # Job Listings
        jobs = context.get('job_listings', []) if context else []
        if jobs:
            print(f"\n💼 JOB LISTINGS (first {min(3, len(jobs))}):")
            for i, job in enumerate(jobs[:3], 1):
                print(f"  {i}. {job.get('title', 'Untitled')}")
                if job.get('company'):
                    print(f"     Company: {job.get('company')}")
                if job.get('location'):
                    print(f"     Location: {job.get('location')}")
                if job.get('salary'):
                    print(f"     Salary: {job.get('salary')}")
                if job.get('experience'):
                    print(f"     Experience: {job.get('experience')}")
        
        # Companies
        companies = context.get('key_companies', []) if context else []
        if companies:
            print(f"\n🏢 KEY COMPANIES:")
            for company in companies[:5]:
                print(f"  • {company}")
        
        # Primary Actions
        actions = context.get('primary_actions', []) if context else []
        if actions:
            print(f"\n⚡ PRIMARY ACTIONS:")
            for action in actions[:5]:
                print(f"  • {action}")
        
        print("\n" + "="*70)
    
    def save_results(self):
        """Save results to JSON"""
        if not self.results:
            print("⚠️ No results to save")
            return
        
        output_file = self.session_path / 'analysis_results.json'
        try:
            with open(output_file, 'w') as f:
                json.dump(self.results, f, indent=2, default=str)
            print(f"\n✅ Results saved to: {output_file}")
        except Exception as e:
            print(f"❌ Could not save results: {e}")
    
    def save_report(self):
        """Save report to text file"""
        if not self.results:
            print("⚠️ No results to save")
            return
        
        report_file = self.session_path / 'report.txt'
        try:
            with open(report_file, 'w') as f:
                # Redirect print to file
                import contextlib
                with contextlib.redirect_stdout(f):
                    self.print_report()
            print(f"✅ Report saved to: {report_file}")
        except Exception as e:
            print(f"❌ Could not save report: {e}")


def find_sessions(memory_dir: Path = None) -> list:
    """Find recent sessions in the memory directory"""
    if memory_dir is None:
        memory_dir = Path('memory')
    
    if not memory_dir.exists():
        # Try parent directory
        memory_dir = Path('/data/data/com.termux/files/home/automation/chrome-launcher/memory')
        if not memory_dir.exists():
            return []
    
    sessions = sorted(memory_dir.glob('session_*'), key=lambda x: x.stat().st_mtime, reverse=True)
    return sessions


def main():
    print("🚀 Session Analysis Pipeline")
    print("="*50)
    print("📂 Supports organized directories:")
    print("   - dom_trees/      → DOM data")
    print("   - accessibility/  → Accessibility tree")
    print("   - snapshots/      → Snapshot data")
    print("   - computed_styles/→ Computed styles")
    print("="*50)
    
    # Find recent sessions
    sessions = find_sessions()
    
    if sessions:
        print("\n📂 Recent sessions:")
        for i, session in enumerate(sessions[:5]):
            # Check if analysis already exists
            has_analysis = (session / 'analysis_results.json').exists()
            status = "✅" if has_analysis else "📄"
            # Check what data is available
            dom_files = list(session.glob('dom_trees/dom_*.json')) + list(session.glob('dom_*.json'))
            ax_files = list(session.glob('accessibility/a11y_*.json')) + list(session.glob('a11y_*.json'))
            data_info = f"DOM:{len(dom_files)} AX:{len(ax_files)}"
            print(f"  [{i}] {status} {session.name} ({data_info})")
        
        print("\nOptions:")
        print("  - Enter number [0-4] to select a session")
        print("  - Enter full path to a session")
        print("  - Press Enter to use the most recent session")
        
        choice = input("\nSelect option: ").strip()
        
        if choice == "":
            # Use most recent
            session_path = sessions[0]
        elif choice.isdigit():
            idx = int(choice)
            if 0 <= idx < len(sessions):
                session_path = sessions[idx]
            else:
                print("❌ Invalid selection")
                return
        else:
            session_path = Path(choice)
    else:
        print("\n📂 No sessions found")
        session_path = Path(input("📁 Enter full session path: ").strip())
    
    if not session_path.exists():
        print(f"❌ Session not found: {session_path}")
        return
    
    # Run analysis
    print(f"\n🔬 Analyzing: {session_path}")
    analyzer = SessionAnalyzer(str(session_path))
    analyzer.analyze()
    analyzer.print_report()
    analyzer.save_results()
    analyzer.save_report()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Interrupted. Goodbye!")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
