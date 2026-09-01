#!/usr/bin/env python3
"""
Discover actual content from text snippets (filter out technical jargon)
"""

import json
import re
from collections import Counter
from pathlib import Path

def load_data(filepath):
    with open(filepath, 'r') as f:
        raw = json.load(f)
        return raw.get('data', raw)

def extract_all_text(data, results=None):
    if results is None:
        results = []
    
    if isinstance(data, dict):
        for key, value in data.items():
            if key in ['children', 'nodes', 'childNodes']:
                continue
            if isinstance(value, str) and value.strip():
                results.append(value.strip())
            else:
                extract_all_text(value, results)
        
        for key in ['children', 'nodes', 'childNodes']:
            if key in data and isinstance(data[key], list):
                for item in data[key]:
                    extract_all_text(item, results)
    
    elif isinstance(data, list):
        for item in data:
            extract_all_text(item, results)
    
    return results

def is_technical_text(text):
    """Check if text is likely technical/HTML vs actual content"""
    technical_patterns = [
        r'^[a-zA-Z-]+$',  # Single word
        r'^[{}\[\]]',  # JSON-like
        r'^[0-9]+$',  # Just numbers
        r'^[A-Z]{2,}$',  # All caps acronym
        r'(webkit|moz|ms|o)[A-Z]',  # Browser prefixes
        r'(aria|role|class|id|style|data-)',  # HTML attributes
        r'^[a-f0-9]{8,}$',  # Hex strings
        r'\.(js|css|png|jpg|gif|svg|woff|ttf|eot)',  # File extensions
    ]
    
    # Check length
    if len(text) < 3 or len(text) > 500:
        return True
    
    # Check if it's a URL
    if re.match(r'^https?://', text):
        return True
    
    # Check technical patterns
    for pattern in technical_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    
    # Check for too many special characters
    special_chars = sum(1 for c in text if not c.isalnum() and not c.isspace())
    if special_chars / len(text) > 0.3:  # More than 30% special characters
        return True
    
    return False

def main():
    print("🔍 Discovering Actual Content")
    print("="*60)
    
    # Load all data
    all_texts = []
    
    # Load DOM
    dom_data = load_data('dom_trees/dom_191252_752541.json')
    if dom_data:
        texts = extract_all_text(dom_data)
        all_texts.extend(texts)
        print(f"📄 DOM texts: {len(texts)}")
    
    # Load AX
    ax_data = load_data('accessibility/a11y_191256_499421.json')
    if ax_data:
        texts = extract_all_text(ax_data)
        all_texts.extend(texts)
        print(f"♿ AX texts: {len(texts)}")
    
    # Load Snapshot
    snap_data = load_data('snapshots/snapshot_191254_828358.json')
    if snap_data:
        texts = extract_all_text(snap_data)
        all_texts.extend(texts)
        print(f"📸 Snapshot texts: {len(texts)}")
    
    print(f"\n📝 Total texts: {len(all_texts)}")
    
    # Filter out technical text
    content_texts = []
    for text in all_texts:
        if not is_technical_text(text):
            content_texts.append(text)
    
    print(f"📖 Content texts (non-technical): {len(content_texts)}")
    print(f"🔧 Technical texts filtered: {len(all_texts) - len(content_texts)}")
    
    # Find actual content
    print("\n" + "="*60)
    print("📊 DISCOVERED CONTENT")
    print("="*60)
    
    # Common words in content
    words = []
    for text in content_texts:
        # Split into words (keep multi-word phrases with spaces)
        if len(text.split()) > 1:
            # This is a phrase
            words.append(text)
        else:
            # Single word
            words.append(text)
    
    # Count word frequencies
    word_freq = Counter()
    for word in words:
        word_lower = word.lower()
        if len(word_lower) > 2:
            word_freq[word_lower] += 1
    
    print(f"\n📖 Most Common Content Phrases/Texts (Top 30):")
    print("-"*40)
    for i, (text, count) in enumerate(word_freq.most_common(30), 1):
        if len(text) > 80:
            display = text[:80] + "..."
        else:
            display = text
        print(f"  {i:2d}. [{count:3d}] {display}")
    
    # Look for specific content types
    print("\n" + "="*60)
    print("🎯 CONTENT CATEGORIES")
    print("="*60)
    
    # Job-related content
    job_keywords = ['job', 'position', 'role', 'career', 'hiring', 'apply', 'salary', 'experience']
    job_texts = [t for t in content_texts if any(kw in t.lower() for kw in job_keywords)]
    print(f"\n💼 Job-related content: {len(job_texts)} snippets")
    
    if job_texts:
        print("   Sample job texts:")
        for text in job_texts[:5]:
            print(f"   • {text[:100]}")
    
    # Company names
    company_patterns = [
        r'\b(Innodata India|Randstad|Deloitte|PwC|KPMG|EY|KPIT|Sasken|Happiest Minds|Mphasis|Persistent|Hexaware|Wipro|Accenture|Capgemini|Cognizant|LTIMindtree|Infosys|TCS|HCL)\b'
    ]
    companies = set()
    for text in content_texts:
        for pattern in company_patterns:
            matches = re.findall(pattern, text)
            companies.update(matches)
    
    if companies:
        print(f"\n🏢 Companies found: {', '.join(sorted(companies))}")
    
    # Locations
    location_patterns = [
        r'\b(Pune|Mumbai|Bangalore|Bengaluru|Delhi|Noida|Gurgaon|Hyderabad|Chennai|Kolkata|Thane|Navi Mumbai)\b'
    ]
    locations = set()
    for text in content_texts:
        for pattern in location_patterns:
            matches = re.findall(pattern, text)
            locations.update(matches)
    
    if locations:
        print(f"\n📍 Locations found: {', '.join(sorted(locations))}")
    
    # Salary patterns
    salary_pattern = r'(\d+[-–]\d+|\d+\+)\s*(?:Lacs?|Lakhs?)\s*(?:P\.A\.|PA)'
    salaries = set()
    for text in content_texts:
        matches = re.findall(salary_pattern, text, re.IGNORECASE)
        salaries.update(matches)
    
    if salaries:
        print(f"\n💰 Salaries found: {', '.join(sorted(salaries))}")
    
    # Experience patterns
    exp_pattern = r'(\d+[-–]\d+|\d+\+)\s*(?:Yrs?|Years?)'
    experiences = set()
    for text in content_texts:
        matches = re.findall(exp_pattern, text, re.IGNORECASE)
        experiences.update(matches)
    
    if experiences:
        print(f"\n📅 Experience levels: {', '.join(sorted(experiences))}")
    
    # Blog/News content
    blog_keywords = ['blog', 'article', 'news', 'read more', 'learn more']
    blog_texts = [t for t in content_texts if any(kw in t.lower() for kw in blog_keywords)]
    if blog_texts:
        print(f"\n📰 Blog/News content: {len(blog_texts)} snippets")
        print("   Sample blog titles:")
        for text in blog_texts[:3]:
            print(f"   • {text[:100]}")
    
    print("\n" + "="*60)
    print("📌 SUMMARY")
    print("="*60)
    
    print(f"  Total content discovered: {len(content_texts)} snippets")
    print(f"  Job listings found: {len(job_texts)}")
    print(f"  Companies: {len(companies)}")
    print(f"  Locations: {len(locations)}")
    print(f"  Salaries: {len(salaries)}")
    print(f"  Experience levels: {len(experiences)}")
    print(f"  Blog/News: {len(blog_texts)}")

if __name__ == "__main__":
    main()
