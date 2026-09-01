#!/usr/bin/env python3
"""
Direct analysis of session data with proper parsing
"""

import json
import sys
from pathlib import Path

# Add Perception to path
sys.path.insert(0, '/data/data/com.termux/files/home/automation/chrome-launcher/Perception')

from dom_analysis import analyze_page, decide_action

def load_json_file(filepath):
    """Load JSON file with error handling"""
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"  ❌ Error loading {filepath}: {e}")
        return None

def analyze_dom_data(dom_data):
    """Analyze DOM data regardless of format"""
    if not dom_data:
        return None
    
    # Check if it has a 'root' key (CDP format)
    if 'root' in dom_data:
        dom_data = dom_data['root']
    
    # Check if it has 'children' at root
    if 'children' not in dom_data:
        # Create a wrapper
        dom_data = {
            'nodeType': 9,  # Document node
            'nodeName': '#document',
            'children': [dom_data] if dom_data else []
        }
    
    # Count nodes
    def count_nodes(node):
        count = 1
        for child in node.get('children', []):
            count += count_nodes(child)
        return count
    
    node_count = count_nodes(dom_data)
    print(f"     Total nodes: {node_count}")
    
    return dom_data

def analyze_accessibility_data(ax_data):
    """Analyze accessibility data"""
    if not ax_data:
        return None
    
    nodes = ax_data.get('nodes', [])
    print(f"     Total AX nodes: {len(nodes)}")
    
    # Count roles
    roles = {}
    for node in nodes:
        role = node.get('role', {}).get('value', 'unknown')
        roles[role] = roles.get(role, 0) + 1
    
    print(f"     Roles found: {len(roles)}")
    for role, count in list(roles.items())[:10]:
        print(f"       - {role}: {count}")
    
    return ax_data

def extract_jobs_from_text(dom_data, ax_data):
    """Extract job listings from text nodes"""
    job_keywords = ['job', 'hiring', 'position', 'salary', 'experience', 'company']
    job_patterns = [
        r'(Innodata India|Randstad|Deloitte|PwC|KPMG|EY|KPIT|Sasken|Happiest Minds|Larsen|Mphasis|Persistent|Hexaware|Wipro|Accenture|Capgemini|Cognizant)',
        r'(\d+[-–]\d+|\d+\+)\s*(?:Lacs?|Lakhs?)\s*(?:P\.A\.|PA)',
        r'(\d+[-–]\d+|\d+\+)\s*(?:Yrs?|Years?)',
        r'(Pune|Mumbai|Bangalore|Bengaluru|Delhi|Noida|Gurgaon|Hyderabad|Chennai|Kolkata)'
    ]
    
    # Extract text from DOM
    all_text = []
    
    def extract_text(node):
        if node.get('nodeType') == 3:  # Text node
            text = node.get('nodeValue', '').strip()
            if text:
                all_text.append(text)
        
        for child in node.get('children', []):
            extract_text(child)
    
    if dom_data:
        extract_text(dom_data)
    
    print(f"\n  📝 Found {len(all_text)} text snippets")
    
    # Look for job-related text
    job_texts = []
    for text in all_text:
        text_lower = text.lower()
        if any(kw in text_lower for kw in job_keywords):
            job_texts.append(text)
    
    print(f"  💼 Found {len(job_texts)} job-related text snippets")
    
    # Look for "View jobs" buttons
    view_jobs_count = sum(1 for text in all_text if 'view jobs' in text.lower())
    print(f"  🔘 Found {view_jobs_count} 'View jobs' mentions")
    
    # Look for specific job listings from the DOM snippets you showed
    companies = []
    for text in all_text:
        import re
        for pattern in job_patterns:
            matches = re.findall(pattern, text)
            if matches:
                companies.extend(matches)
    
    if companies:
        print(f"  🏢 Found company mentions: {list(set(companies))[:10]}")
    
    return {
        'total_texts': len(all_text),
        'job_texts': len(job_texts),
        'view_jobs': view_jobs_count,
        'companies': list(set(companies))[:10] if companies else []
    }

def main():
    print("="*60)
    print("🔍 SESSION DATA ANALYSIS")
    print("="*60)
    
    # Load all data files
    print("\n📁 Loading data files:")
    
    dom_data = load_json_file('dom_trees/dom_191252_752541.json')
    if dom_data:
        print(f"  ✅ DOM loaded")
        dom_data = analyze_dom_data(dom_data)
    
    ax_data = load_json_file('accessibility/a11y_191256_499421.json')
    if ax_data:
        print(f"  ✅ Accessibility loaded")
        ax_data = analyze_accessibility_data(ax_data)
    
    snapshot_data = load_json_file('snapshots/snapshot_191254_828358.json')
    if snapshot_data:
        print(f"  ✅ Snapshot loaded")
    
    print("\n" + "="*60)
    print("📊 ANALYSIS RESULTS")
    print("="*60)
    
    # Run DOM analysis if we have data
    if dom_data:
        print("\n📄 DOM ANALYSIS:")
        try:
            # Try the actual analysis
            result = analyze_page(dom_data)
            print(f"  Page Type: {result.get('page_type', 'unknown')}")
            print(f"  Node Count: {result.get('node_count', 0)}")
            print(f"  Interactive Elements: {result.get('interactive_count', 0)}")
            print(f"  Has Search: {result.get('has_search', False)}")
            print(f"  Has Forms: {result.get('has_forms', False)}")
            print(f"  Has Navigation: {result.get('has_navigation', False)}")
            print(f"  Recommended Action: {decide_action(result)}")
        except Exception as e:
            print(f"  ❌ Error in DOM analysis: {e}")
    
    # Extract job listings
    if dom_data:
        print("\n💼 JOB LISTINGS:")
        jobs = extract_jobs_from_text(dom_data, ax_data)
        print(f"  Total text snippets: {jobs.get('total_texts', 0)}")
        print(f"  Job-related texts: {jobs.get('job_texts', 0)}")
        print(f"  'View jobs' mentions: {jobs.get('view_jobs', 0)}")
        if jobs.get('companies'):
            print(f"  Companies found: {', '.join(jobs['companies'][:5])}")
    
    # Summary
    print("\n" + "="*60)
    print("📌 SUMMARY")
    print("="*60)
    
    if dom_data:
        # Count nodes manually
        def count_nodes(node):
            count = 1
            for child in node.get('children', []):
                count += count_nodes(child)
            return count
        total_nodes = count_nodes(dom_data)
        print(f"  Total DOM Nodes: {total_nodes}")
    
    if ax_data:
        ax_nodes = len(ax_data.get('nodes', []))
        print(f"  Total AX Nodes: {ax_nodes}")
    
    print("\n  ✅ Analysis complete!")

if __name__ == "__main__":
    main()
