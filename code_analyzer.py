#!/usr/bin/env python3
# code_analyzer.py - Python version of the code analyzer

import os
import sys
import subprocess
import json
import argparse
from datetime import datetime
from pathlib import Path
from collections import defaultdict
import re

class CodeAnalyzer:
    def __init__(self, target='.', output_dir=None, json_output=False, 
                 verbose=False, quiet=False, depth=5, include_tests=False):
        self.target = Path(target)
        self.output_dir = Path(output_dir or f"./analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        self.json_output = json_output
        self.verbose = verbose
        self.quiet = quiet
        self.depth = depth
        self.include_tests = include_tests
        self.has_rg = self.check_tool('rg')
        self.has_sg = self.check_tool('sg')
        self.has_jq = self.check_tool('jq')
        self.has_tree = self.check_tool('tree')
        
    def check_tool(self, tool):
        """Check if a tool is installed"""
        try:
            subprocess.run([tool, '--version'], 
                          capture_output=True, 
                          check=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False
    
    def run_command(self, cmd):
        """Run a command and return output"""
        try:
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            return result.stdout.strip()
        except Exception as e:
            if self.verbose:
                print(f"Error running command: {e}")
            return ""
    
    def get_statistics(self):
        """Collect project statistics"""
        stats = {
            'target': str(self.target),
            'analyzed': datetime.now().isoformat(),
            'total_files': 0,
            'total_lines': 0,
            'total_classes': 0,
            'total_functions': 0,
            'total_methods': 0,
            'total_imports': 0,
            'total_tests': 0
        }
        
        if self.target.is_file():
            # Single file
            stats['total_files'] = 1
            stats['total_lines'] = int(self.run_command(f"wc -l < {self.target}") or 0)
            
            if self.has_rg:
                stats['total_classes'] = int(self.run_command(f"rg '^class ' {self.target} | wc -l") or 0)
                stats['total_functions'] = int(self.run_command(f"rg '^def ' {self.target} | wc -l") or 0)
                stats['total_methods'] = int(self.run_command(f"rg '^    def ' {self.target} | wc -l") or 0)
                stats['total_imports'] = int(self.run_command(f"rg '^(import|from)' {self.target} | wc -l") or 0)
                
                if self.include_tests:
                    stats['total_tests'] = int(self.run_command(f"rg 'def test_' {self.target} | wc -l") or 0)
        else:
            # Directory
            py_files = list(self.target.rglob("*.py"))
            stats['total_files'] = len(py_files)
            
            if py_files:
                total_lines = 0
                for py_file in py_files:
                    try:
                        with open(py_file) as f:
                            total_lines += len(f.readlines())
                    except:
                        pass
                stats['total_lines'] = total_lines
            
            if self.has_rg:
                stats['total_classes'] = int(self.run_command(f"rg '^class ' {self.target} | wc -l") or 0)
                stats['total_functions'] = int(self.run_command(f"rg '^def ' {self.target} | wc -l") or 0)
                stats['total_methods'] = int(self.run_command(f"rg '^    def ' {self.target} | wc -l") or 0)
                stats['total_imports'] = int(self.run_command(f"rg '^(import|from)' {self.target} | wc -l") or 0)
                
                if self.include_tests:
                    stats['total_tests'] = int(self.run_command(f"rg 'def test_' {self.target} | wc -l") or 0)
        
        # Calculate derived metrics
        if stats['total_functions'] > 0:
            stats['avg_function_complexity'] = stats['total_lines'] // stats['total_functions']
        else:
            stats['avg_function_complexity'] = 0
            
        if stats['total_functions'] > 0 and stats['total_tests'] > 0:
            stats['test_coverage'] = (stats['total_tests'] * 100) // stats['total_functions']
        else:
            stats['test_coverage'] = 0
            
        return stats
    
    def analyze_structure(self):
        """Analyze code structure"""
        structure = {
            'classes': [],
            'functions': [],
            'methods': [],
            'inheritance': []
        }
        
        if self.has_rg:
            # Get classes
            classes = self.run_command(f"rg '^class ' {self.target}")
            if classes:
                structure['classes'] = [line.strip() for line in classes.split('\n') if line.strip()]
            
            # Get functions
            functions = self.run_command(f"rg '^def ' {self.target}")
            if functions:
                structure['functions'] = [line.strip() for line in functions.split('\n') if line.strip()]
            
            # Get methods
            methods = self.run_command(f"rg '^    def ' {self.target}")
            if methods:
                structure['methods'] = [line.strip() for line in methods.split('\n') if line.strip()]
        
        if self.has_sg:
            # Get inheritance
            inheritance = self.run_command(f"sg -p 'class $NAME($PARENT): {{ ... }}' {self.target} 2>/dev/null")
            if inheritance:
                structure['inheritance'] = [line.strip() for line in inheritance.split('\n') if line.strip()]
        
        return structure
    
    def analyze_dependencies(self):
        """Analyze imports and dependencies"""
        deps = {
            'standard_lib': [],
            'third_party': [],
            'package_frequency': {}
        }
        
        if self.has_rg:
            # Get all imports
            imports = self.run_command(f"rg '^(import|from) ' {self.target}")
            if imports:
                for line in imports.split('\n'):
                    if not line.strip():
                        continue
                    # Extract package name
                    match = re.search(r'^(?:import|from)\s+([a-zA-Z_][a-zA-Z0-9_]*)', line)
                    if match:
                        pkg = match.group(1)
                        deps['package_frequency'][pkg] = deps['package_frequency'].get(pkg, 0) + 1
            
            # Sort by frequency
            deps['package_frequency'] = dict(sorted(deps['package_frequency'].items(), 
                                                   key=lambda x: x[1], reverse=True))
            
            # Simple classification (can be improved)
            std_lib = {'sys', 'os', 'time', 'json', 're', 'subprocess', 'shutil', 
                      'signal', 'threading', 'queue', 'socket', 'hashlib', 'tempfile',
                      'pathlib', 'datetime', 'enum', 'dataclasses', 'typing', 'logging',
                      'atexit', 'collections', 'itertools', 'functools'}
            
            for pkg in deps['package_frequency']:
                if pkg in std_lib:
                    deps['standard_lib'].append(pkg)
                else:
                    deps['third_party'].append(pkg)
        
        return deps
    
    def analyze_complexity(self):
        """Analyze code complexity"""
        complexity = {
            'long_functions': [],
            'deep_nesting': [],
            'metrics': {}
        }
        
        if self.has_rg:
            # Find long functions
            if self.target.is_file():
                result = self.run_command(f"rg -n '^def ' {self.target}")
                for line in result.split('\n'):
                    if not line.strip():
                        continue
                    parts = line.split(':')
                    if len(parts) >= 2:
                        try:
                            line_num = int(parts[0])
                            func_name = parts[1].replace('def ', '').split('(')[0].strip()
                            
                            # Rough estimate of function length
                            with open(self.target) as f:
                                lines = f.readlines()
                                start = line_num - 1
                                end = start
                                while end < len(lines) and (not lines[end].strip() or 
                                      not lines[end].startswith('def ') or end == start):
                                    if lines[end].strip().startswith(('class ', 'def ')) and end != start:
                                        break
                                    end += 1
                                func_len = end - start
                                
                                if func_len > 50:
                                    complexity['long_functions'].append({
                                        'name': func_name,
                                        'lines': func_len,
                                        'start_line': line_num
                                    })
                        except (ValueError, IndexError):
                            pass
            
            # Count decision points
            decision_points = 0
            for keyword in ['if', 'elif', 'else', 'for', 'while', 'try']:
                count = int(self.run_command(f"rg '^\\s*{keyword}\\s' {self.target} | wc -l") or 0)
                complexity['metrics'][keyword] = count
                decision_points += count
            
            complexity['metrics']['total_decisions'] = decision_points
            
            # Find deep nesting
            nesting = self.run_command(f"rg -n '(if|for|while|with|try)\\s+.*(\\n\\s+.*){{4,}}' {self.target}")
            if nesting:
                complexity['deep_nesting'] = [line.strip() for line in nesting.split('\n') if line.strip()][:10]
        
        return complexity
    
    def analyze_error_handling(self):
        """Analyze error handling patterns"""
        errors = {
            'exception_types': {},
            'error_logging': [],
            'resource_management': {}
        }
        
        if self.has_rg:
            # Exception types
            exceptions = self.run_command(f"rg 'except\\s+\\(?([A-Za-z]+)' {self.target}")
            if exceptions:
                for line in exceptions.split('\n'):
                    match = re.search(r'except\s+\(?([A-Za-z]+)', line)
                    if match:
                        exc_type = match.group(1)
                        errors['exception_types'][exc_type] = errors['exception_types'].get(exc_type, 0) + 1
            
            # Error logging
            logging = self.run_command(f"rg '(logger\\.error|console\\.print.*red|print.*error|logging\\.error)' {self.target}")
            if logging:
                errors['error_logging'] = [line.strip() for line in logging.split('\n') if line.strip()][:20]
            
            # Resource management
            errors['resource_management'] = {
                'with_statements': int(self.run_command(f"rg '^with ' {self.target} | wc -l") or 0),
                'try_blocks': int(self.run_command(f"rg '^try:' {self.target} | wc -l") or 0),
                'finally_blocks': int(self.run_command(f"rg '^finally:' {self.target} | wc -l") or 0),
                'except_blocks': len(errors['exception_types'])
            }
        
        return errors
    
    def analyze_patterns(self):
        """Analyze code patterns"""
        patterns = {
            'design_patterns': [],
            'anti_patterns': []
        }
        
        if self.has_rg:
            # Design patterns
            if self.run_command(f"rg 'def __new__|_instance = None' {self.target}"):
                patterns['design_patterns'].append('Singleton')
            
            if self.run_command(f"rg 'def create_' {self.target}"):
                patterns['design_patterns'].append('Factory')
            
            if self.run_command(f"rg 'def build_|def configure_' {self.target}"):
                patterns['design_patterns'].append('Builder')
            
            if self.run_command(f"rg 'def notify|def subscribe|def register' {self.target}"):
                patterns['design_patterns'].append('Observer')
            
            # Anti-patterns
            if self.run_command(f"rg 'except:' {self.target}"):
                patterns['anti_patterns'].append('Bare exceptions')
            
            if self.run_command(f"rg 'def [a-zA-Z_]+\\([^)]*,[^)]*,[^)]*,[^)]*,[^)]*,[^)]*' {self.target}"):
                patterns['anti_patterns'].append('Functions with >5 parameters')
            
            if self.run_command(f"rg '^[A-Z_]+ = ' {self.target}"):
                patterns['anti_patterns'].append('Global variables')
        
        return patterns
    
    def generate_report(self):
        """Generate the complete analysis report"""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Collect all data
        stats = self.get_statistics()
        structure = self.analyze_structure()
        deps = self.analyze_dependencies()
        complexity = self.analyze_complexity()
        errors = self.analyze_error_handling()
        patterns = self.analyze_patterns()
        
        # Generate Markdown report
        report_file = self.output_dir / f"analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        
        with open(report_file, 'w') as f:
            f.write(f"# Python Code Analysis Report\n\n")
            f.write(f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"**Target**: {self.target}\n")
            f.write(f"**Tools**: rg{', sg' if self.has_sg else ''}{', jq' if self.has_jq else ''}\n\n")
            
            # Statistics
            f.write("## Statistics\n\n")
            f.write("```\n")
            for key, value in stats.items():
                f.write(f"{key.replace('_', ' ').title()}: {value}\n")
            f.write("```\n\n")
            
            # Structure
            f.write("## Code Structure\n\n")
            f.write("### Classes\n```\n")
            f.write("\n".join(structure.get('classes', ['No classes found']))[:500])
            f.write("\n```\n\n")
            
            f.write("### Functions\n```\n")
            f.write("\n".join(structure.get('functions', ['No functions found']))[:500])
            f.write("\n```\n\n")
            
            # Dependencies
            f.write("## Dependencies\n\n")
            f.write("### Package Usage Frequency\n```\n")
            for pkg, count in list(deps.get('package_frequency', {}).items())[:20]:
                f.write(f"{count:5} {pkg}\n")
            f.write("```\n\n")
            
            f.write("### Third-Party Packages\n```\n")
            f.write("\n".join(deps.get('third_party', ['No third-party packages found']))[:200])
            f.write("\n```\n\n")
            
            # Complexity
            f.write("## Complexity Analysis\n\n")
            f.write("### Long Functions (>50 lines)\n```\n")
            if complexity.get('long_functions'):
                for func in complexity['long_functions']:
                    f.write(f"{func['name']} ({func['lines']} lines, line {func['start_line']})\n")
            else:
                f.write("No long functions found\n")
            f.write("```\n\n")
            
            f.write("### Complexity Metrics\n```\n")
            for key, value in complexity.get('metrics', {}).items():
                f.write(f"{key}: {value}\n")
            f.write("```\n\n")
            
            # Error Handling
            f.write("## Error Handling\n\n")
            f.write("### Exception Types\n```\n")
            for exc, count in errors.get('exception_types', {}).items():
                f.write(f"{count:5} {exc}\n")
            f.write("```\n\n")
            
            # Patterns
            f.write("## Code Patterns\n\n")
            f.write("### Design Patterns\n```\n")
            if patterns.get('design_patterns'):
                for p in patterns['design_patterns']:
                    f.write(f"✓ {p}\n")
            else:
                f.write("No design patterns detected\n")
            f.write("```\n\n")
            
            f.write("### Anti-Patterns\n```\n")
            if patterns.get('anti_patterns'):
                for p in patterns['anti_patterns']:
                    f.write(f"✗ {p}\n")
            else:
                f.write("No anti-patterns detected\n")
            f.write("```\n\n")
            
            # Recommendations
            f.write("## Recommendations\n\n")
            f.write("### High Priority Issues\n```\n")
            if self.has_rg:
                issues = self.run_command(f"rg 'WARNING|CRITICAL|FIXME|BUG|HACK' {self.target} | head -10")
                f.write(issues or "No high priority issues found\n")
            f.write("```\n\n")
            
            f.write("### Suggested Improvements\n")
            if errors.get('exception_types', {}).get('Exception', 0) > 0:
                f.write("- Replace bare exceptions with specific exception types\n")
            if len(complexity.get('long_functions', [])) > 0:
                f.write("- Consider refactoring long functions\n")
            if patterns.get('anti_patterns'):
                f.write("- Address identified anti-patterns\n")
        
        # Generate JSON if requested
        if self.json_output:
            json_file = self.output_dir / f"analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(json_file, 'w') as f:
                json.dump({
                    'metadata': {
                        'generated': datetime.now().isoformat(),
                        'target': str(self.target)
                    },
                    'statistics': stats,
                    'structure': structure,
                    'dependencies': deps,
                    'complexity': complexity,
                    'error_handling': errors,
                    'patterns': patterns
                }, f, indent=2)
            print(f"✅ JSON report: {json_file}")
        
        print(f"✅ Analysis complete! Report: {report_file}")
        return report_file

def main():
    parser = argparse.ArgumentParser(description='Python Code Analyzer')
    parser.add_argument('target', nargs='?', default='.', help='Target file or directory')
    parser.add_argument('--output-dir', help='Output directory')
    parser.add_argument('--json', action='store_true', help='Generate JSON output')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    parser.add_argument('--quiet', '-q', action='store_true', help='Quiet mode')
    parser.add_argument('--depth', type=int, default=5, help='Maximum depth')
    parser.add_argument('--include-tests', action='store_true', help='Include test files')
    
    args = parser.parse_args()
    
    analyzer = CodeAnalyzer(
        target=args.target,
        output_dir=args.output_dir,
        json_output=args.json,
        verbose=args.verbose,
        quiet=args.quiet,
        depth=args.depth,
        include_tests=args.include_tests
    )
    
    report = analyzer.generate_report()
    print(f"\n📊 Report generated at: {report}")

if __name__ == '__main__':
    main()
