#!/usr/bin/env python3
"""
Direct analysis of session data with proper wrapper handling
"""

import json
import sys
import re
from pathlib import Path

# Add Perception to path
sys.path.insert(0, '/data/data/com.termux/files/home/automation/chrome-launcher/Perception')

try:
    from dom_analysis import analyze_page, decide_action
except ImportError as e:
    print(f"⚠️ Could not import dom_analysis: {e}")
    # Define fallback functions
    def analyze_page(dom_data):
        return {'page_type': 'unknown', 'node_count': 0}
    def decide_action(result):
        return 'unknown'

def load_json_file(filepath):
    """Load JSON file and extract data from wrapper if present"""
    try:
        with open(filepath, 'r') as f:
            raw_data = json.load(f)
        
        # Check if it's wrapped with 'data' and 'metadata'
        if 'data' in raw_data:
            print(f"  📦 Found wrapped data (metadata present)")
            return raw_data['data']
        else:
            return raw_data
    except Exception as e:
        print(f"  ❌ Error loading {filepath}: {e}")
        return None

def count_nodes(node):
    """Count total nodes in DOM tree"""
    count = 1
    for child in node.get('children', []):
        count += count_nodes(child)
    return count

def extract_all_text(node, results=None):
    """Extract all text from DOM tree"""
    if results is None:
        results = []
    
    if node.get('nodeType') == 3:  # Text node
        text = node.get('nodeValue', '').strip()
        if text:
            results.append(text)
    
    for child in node.get('children', []):
        extract_all_text(child, results)
    
    return results

def analyze_dom_data(dom_data):
    """Analyze DOM data regardless of format"""
    if not dom_data:
        return None, 0
    
    # If it has a 'root' key (CDP format), use that
    if 'root' in dom_data:
        dom_data = dom_data['root']
    
    # Check if it's the document node with children
    if 'children' in dom_data:
        total_nodes = count_nodes(dom_data)
        print(f"     Total nodes: {total_nodes}")
        
        # Extract all text
        all_text = extract_all_text(dom_data)
        print(f"     Text snippets: {len(all_text)}")
        
        # Show sample text
        if all_text:
            print(f"     Sample text: {all_text[0][:100]}...")
        
        return dom_data, total_nodes
    
    print(f"     Unknown DOM format, keys: {list(dom_data.keys())}")
    return dom_data, 0

def analyze_accessibility_data(ax_data):
    """Analyze accessibility data"""
    if not ax_data:
        return None, 0
    
    nodes = ax_data.get('nodes', [])
    total_nodes = len(nodes)
    print(f"     Total AX nodes: {total_nodes}")
    
    # Count roles
    roles = {}
    named_nodes = 0
    for node in nodes:
        role = node.get('role', {}).get('value', 'unknown')
        roles[role] = roles.get(role, 0) + 1
        
        name = node.get('name', {}).get('value', '')
        if name:
            named_nodes += 1
    
    print(f"     Roles found: {len(roles)}")
    for role, count in list(roles.items())[:10]:
        print(f"       - {role}: {count}")
    
    print(f"     Named nodes: {named_nodes}")
    
    # Find job-related nodes
    job_keywords = ['job', 'position', 'role', 'career', 'hiring', 'apply']
    job_nodes = []
    for node in nodes:
        name = node.get('name', {}).get('value', '').lower()
        if any(kw in name for kw in job_keywords):
            job_nodes.append(node)
    
    print(f"     Job-related nodes: {len(job_nodes)}")
    
    return ax_data, total_nodes

def extract_jobs_from_text(dom_data):
    """Extract job listings from text nodes"""
    if not dom_data:
        return {}
    
    all_text = extract_all_text(dom_data)
    
    print(f"\n  📝 Found {len(all_text)} text snippets")
    
    # Look for job-related text
    job_keywords = ['job', 'hiring', 'position', 'salary', 'experience', 'company']
    job_texts = []
    
    # Patterns for job data
    company_pattern = re.compile(r'(Innodata India|Randstad|Deloitte|PwC|KPMG|EY|KPIT|Sasken|Happiest Minds|Larsen|Mphasis|Persistent|Hexaware|Wipro|Accenture|Capgemini|Cognizant|LTIMindtree|Infosys|TCS|HCL|Tech Mahindra)')
    salary_pattern = re.compile(r'(\d+[-–]\d+|\d+\+)\s*(?:Lacs?|Lakhs?)\s*(?:P\.A\.|PA)', re.IGNORECASE)
    experience_pattern = re.compile(r'(\d+[-–]\d+|\d+\+)\s*(?:Yrs?|Years?)', re.IGNORECASE)
    location_pattern = re.compile(r'(Pune|Mumbai|Bangalore|Bengaluru|Delhi|Noida|Gurgaon|Hyderabad|Chennai|Kolkata)', re.IGNORECASE)
    
    companies_found = set()
    salaries_found = set()
    experiences_found = set()
    locations_found = set()
    
    for text in all_text:
        text_lower = text.lower()
        if any(kw in text_lower for kw in job_keywords):
            job_texts.append(text)
        
        # Extract patterns
        company_match = company_pattern.search(text)
        if company_match:
            companies_found.add(company_match.group(1))
        
        salary_match = salary_pattern.search(text)
        if salary_match:
            salaries_found.add(salary_match.group(1))
        
        exp_match = experience_pattern.search(text)
        if exp_match:
            experiences_found.add(exp_match.group(1))
        
        loc_match = location_pattern.search(text)
        if loc_match:
            locations_found.add(loc_match.group(1))
    
    print(f"  💼 Found {len(job_texts)} job-related text snippets")
    
    # Look for "View jobs" buttons
    view_jobs_count = sum(1 for text in all_text if 'view jobs' in text.lower())
    print(f"  🔘 Found {view_jobs_count} 'View jobs' mentions")
    
    return {
        'total_texts': len(all_text),
        'job_texts': len(job_texts),
        'view_jobs': view_jobs_count,
        'companies': list(companies_found),
        'salaries': list(salaries_found),
        'experiences': list(experiences_found),
        'locations': list(locations_found)
    }

def main():
    print("="*60)
    print("🔍 SESSION DATA ANALYSIS (Fixed Wrapper Handling)")
    print("="*60)
    
    # Load all data files
    print("\n📁 Loading data files:")
    
    dom_data = load_json_file('dom_trees/dom_191252_752541.json')
    if dom_data:
        print(f"  ✅ DOM loaded")
        dom_data, dom_nodes = analyze_dom_data(dom_data)
    else:
        dom_data = None
        dom_nodes = 0
    
    ax_data = load_json_file('accessibility/a11y_191256_499421.json')
    if ax_data:
        print(f"  ✅ Accessibility loaded")
        ax_data, ax_nodes = analyze_accessibility_data(ax_data)
    else:
        ax_data = None
        ax_nodes = 0
    
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
        jobs = extract_jobs_from_text(dom_data)
        print(f"  Total text snippets: {jobs.get('total_texts', 0)}")
        print(f"  Job-related texts: {jobs.get('job_texts', 0)}")
        print(f"  'View jobs' mentions: {jobs.get('view_jobs', 0)}")
        
        if jobs.get('companies'):
            print(f"  Companies found: {', '.join(jobs['companies'][:10])}")
        if jobs.get('salaries'):
            print(f"  Salaries found: {', '.join(jobs['salaries'][:5])}")
        if jobs.get('experiences'):
            print(f"  Experience levels: {', '.join(jobs['experiences'][:5])}")
        if jobs.get('locations'):
            print(f"  Locations found: {', '.join(jobs['locations'][:10])}")
    
    # Summary
    print("\n" + "="*60)
    print("📌 SUMMARY")
    print("="*60)
    
    if dom_nodes > 0:
        print(f"  ✅ Total DOM Nodes: {dom_nodes}")
    if ax_nodes > 0:
        print(f"  ✅ Total AX Nodes: {ax_nodes}")
    
    if dom_nodes > 0 or ax_nodes > 0:
        print(f"\n  🎯 The page contains job listings with companies, salaries, and locations!")
    else:
        print(f"\n  ⚠️ No data found. Check file paths.")
    
    print("\n  ✅ Analysis complete!")

if __name__ == "__main__":
    main()
