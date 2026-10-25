#!/data/data/com.termux/files/usr/bin/env python3
"""
Fetch ALL hackathon details with complete descriptions
No truncation - saves everything
"""

import sys
import json
import time
import os
import re
from datetime import datetime
import random

sys.path.insert(0, '/data/data/com.termux/files/home/automation/chrome-launcher')
try:
    from geturl import ChromePage
    print("✅ Loaded ChromePage from geturl.py")
except ImportError as e:
    print(f"❌ Could not import ChromePage: {e}")
    sys.exit(1)

def load_urls(filename):
    if not os.path.exists(filename):
        print(f"❌ File not found: {filename}")
        return []
    with open(filename, 'r') as f:
        return [line.strip() for line in f if line.strip()]

def extract_complete_description(text):
    """Extract complete description from page text"""
    
    # Find the "All that you need to know about" section
    desc_start = re.search(r'All that you need to know about[^\n]*\n', text, re.IGNORECASE)
    
    if desc_start:
        start_pos = desc_start.end()
        
        # Find where the description ends
        end_patterns = [
            r'\nRead More\n',
            r'\nFeedback & Rating\n',
            r'\nFrequently Asked Questions\n',
            r'\nFAQs & Discussions\n',
            r'\nUnstop PRO Now',
            r'\nGo Pro Now\n',
            r'\nUpdated On:',
            r'\nReport An Issue'
        ]
        
        end_pos = None
        for pattern in end_patterns:
            match = re.search(pattern, text[start_pos:], re.IGNORECASE)
            if match:
                end_pos = start_pos + match.start()
                break
        
        if end_pos:
            desc_text = text[start_pos:end_pos].strip()
        else:
            desc_text = text[start_pos:].strip()
        
        # Clean up the description - remove extra whitespace but keep paragraphs
        desc_text = re.sub(r'\n{3,}', '\n\n', desc_text)
        desc_text = re.sub(r' +', ' ', desc_text)
        
        # Remove section headers that might be in the description
        desc_text = re.sub(r'^Overview\s*\n', '', desc_text, flags=re.MULTILINE)
        desc_text = re.sub(r'^Eligibility & Registration\s*\n', '', desc_text, flags=re.MULTILINE)
        desc_text = re.sub(r'^Competition Structure\s*\n', '', desc_text, flags=re.MULTILINE)
        desc_text = re.sub(r'^Rewards & Prizes\s*\n', '', desc_text, flags=re.MULTILINE)
        desc_text = re.sub(r'^Join the\.\.\.\s*\n', '', desc_text, flags=re.MULTILINE)
        
        if len(desc_text) > 50:
            return desc_text
    
    # Fallback: Try to get text after the title
    lines = text.split('\n')
    desc_lines = []
    found_section = False
    
    for i, line in enumerate(lines):
        if 'All that you need to know about' in line or 'About the Opportunity' in line:
            found_section = True
            continue
        if found_section:
            if 'Read More' in line or 'Feedback & Rating' in line or 'FAQs' in line or 'Unstop PRO' in line:
                break
            if line.strip() and not line.strip() in ['Overview', 'Eligibility & Registration', 'Competition Structure', 'Rewards & Prizes']:
                desc_lines.append(line.strip())
    
    if desc_lines:
        return ' '.join(desc_lines)
    
    return None

def extract_hackathon_details(page, url):
    """Extract complete hackathon details with full description"""
    
    print(f"   📄 Navigating to: {url[:80]}...")
    
    page.navigate_to(url)
    print("   ⏳ Waiting for page to load...")
    time.sleep(5)
    
    # Get page text
    text = page.get_text()
    
    if not text or len(text) < 100:
        return {'url': url, 'error': 'No text content', 'title': 'Unknown'}
    
    title = page.get_title()
    
    # Initialize details
    details = {
        'url': url,
        'title': title or 'Unknown',
        'organizer': 'Unknown',
        'team_size': 'Unknown',
        'status': 'Unknown',
        'prizes': [],
        'dates': [],
        'eligibility': 'Unknown',
        'has_register_button': False,
        'already_registered': False,
        'hackathon_id': None,
        'word_count': 0,
        'registration_deadline': None,
        'location': None,
        'description': None,
        'category': None,
        'prize_amount': None,
        'sponsors': [],
        'tags': []
    }
    
    # Extract hackathon ID
    id_match = re.search(r'/hackathons/(\d+)', url)
    if id_match:
        details['hackathon_id'] = id_match.group(1)
    
    # Clean title
    if details['title'] and details['title'].endswith(' - 2026'):
        details['title'] = details['title'].replace(' - 2026', '')
    
    # Extract title from page if needed
    if 'Hackathons in India' in details['title']:
        lines = text.split('\n')
        for line in lines[:20]:
            line = line.strip()
            if line and len(line) > 20 and len(line) < 100:
                skip_words = ['Home', 'Internships', 'Jobs', 'Competitions', 'Mentorship', 
                             'Mock Tests', 'Mock Interview', '100 Days to Code', 'Courses', 
                             'Practice', 'Scholarships', 'Cultural Events', 'Workshops', 
                             'Conferences', 'Articles', 'Your Dashboards', 'My Activity',
                             'Recruiter', 'Organizer', 'Details', 'Dates', 'Deadlines',
                             'Prizes', 'Reviews', 'FAQs', 'Discussions', 'Online']
                if line not in skip_words and not line.startswith('Prizes') and not line.startswith('Team Size'):
                    details['title'] = line
                    break
    
    # Extract organizer
    org_patterns = [
        r'Organized by[:\s]+([^\n]+)',
        r'Hosted by[:\s]+([^\n]+)',
        r'Organiser[:\s]+([^\n]+)',
        r'Organizer[:\s]+([^\n]+)'
    ]
    for pattern in org_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            org = match.group(1).strip()
            org = re.sub(r',\s+scheduled\s+for.*$', '', org)
            org = re.sub(r',\s+\d{1,2}–\d{1,2}\s+[A-Za-z]+\s+\d{4}.*$', '', org)
            details['organizer'] = org
            break
    
    # Extract team size
    team_match = re.search(r'Team Size[:\s]+([^\n]+)', text, re.IGNORECASE)
    if team_match:
        details['team_size'] = team_match.group(1).strip()
    
    # Extract status from URL
    if 'oppstatus=open' in url:
        details['status'] = 'Open'
    elif 'oppstatus=closed' in url:
        details['status'] = 'Closed'
    elif 'oppstatus=upcoming' in url:
        details['status'] = 'Upcoming'
    
    # Extract COMPLETE DESCRIPTION - no truncation
    desc = extract_complete_description(text)
    if desc:
        details['description'] = desc
    
    # Extract dates
    date_patterns = [
        r'(\d{1,2}\s+[A-Za-z]+\s+\d{4})',
        r'(\d{4}-\d{2}-\d{2})',
        r'(\d{1,2}/\d{1,2}/\d{4})'
    ]
    all_dates = []
    for pattern in date_patterns:
        matches = re.findall(pattern, text)
        if matches:
            all_dates.extend(matches)
    if all_dates:
        unique_dates = []
        for d in all_dates:
            if d not in unique_dates:
                unique_dates.append(d)
        details['dates'] = unique_dates[:5]
    
    # Extract prizes
    prize_patterns = [
        r'Prizes?[:\s]*([^\n]+(?:\n[^\n]+)*?)(?:\n\s*\n|\n(?:Sponsors|Categories|Team|Eligibility|Reviews))',
        r'Rewards[:\s]*([^\n]+(?:\n[^\n]+)*?)(?:\n\s*\n|\n(?:Sponsors|Categories|Team|Eligibility|Reviews))'
    ]
    for pattern in prize_patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            prize_text = match.group(1).strip()
            prizes = [p.strip() for p in prize_text.split('\n') if p.strip() and len(p.strip()) > 3]
            if prizes:
                details['prizes'] = prizes[:10]
                break
    
    # Extract eligibility
    elig_match = re.search(r'Eligibility[:\s]+([^\n]+(?:\n[^\n]+)*?)(?:\n\s*\n|\n(?:Team|Dates|Prizes))', text, re.IGNORECASE)
    if elig_match:
        details['eligibility'] = elig_match.group(1).strip()
    
    # Extract registration deadline
    deadline_match = re.search(r'Registration Deadline[:\s]+([^\n]+)', text, re.IGNORECASE)
    if deadline_match:
        details['registration_deadline'] = deadline_match.group(1).strip()
    
    # Extract location
    loc_match = re.search(r'Location[:\s]+([^\n]+)', text, re.IGNORECASE)
    if loc_match:
        details['location'] = loc_match.group(1).strip()
    
    # Check for register button
    register_keywords = ['Register', 'Apply', 'Enroll', 'Join Now', 'Register Now']
    for keyword in register_keywords:
        if keyword.lower() in text.lower():
            details['has_register_button'] = True
            break
    
    # Check if already registered
    if 'already registered' in text.lower() or 'you are registered' in text.lower():
        details['already_registered'] = True
    
    details['word_count'] = len(text.split())
    
    return details

def fetch_all_details(urls, max_to_fetch=10, delay_min=3, delay_max=8):
    results = []
    successful = 0
    failed = 0
    
    print(f"\n📊 Fetching details for up to {max_to_fetch} hackathons...")
    print("=" * 70)
    print(f"⏳ Rate limiting: {delay_min}-{delay_max}s between requests")
    print("=" * 70)
    
    port = 9258
    page = ChromePage(port)
    
    if not page.connect():
        print("❌ Failed to connect to Chrome")
        return []
    
    urls_to_fetch = urls[:max_to_fetch]
    total = len(urls_to_fetch)
    
    for i, url in enumerate(urls_to_fetch, 1):
        print(f"\n[{i}/{total}] Processing...")
        
        try:
            details = extract_hackathon_details(page, url)
            
            if details and not details.get('error'):
                results.append(details)
                successful += 1
                desc_len = len(details.get('description', ''))
                print(f"   ✅ {details.get('title', 'Unknown')[:60]}")
                print(f"      📝 Description: {desc_len} characters")
                print(f"      📅 Status: {details.get('status', 'N/A')}")
                print(f"      👥 Team: {details.get('team_size', 'N/A')}")
                print(f"      🏆 Prizes: {len(details.get('prizes', []))} found")
                print(f"      🔘 Register: {details.get('has_register_button', False)}")
            else:
                results.append({'url': url, 'error': 'Failed'})
                failed += 1
                print(f"   ❌ Failed")
            
            if i < total:
                delay = random.uniform(delay_min, delay_max)
                print(f"   ⏳ Waiting {delay:.1f}s...")
                time.sleep(delay)
                
        except Exception as e:
            print(f"   ❌ Error: {e}")
            results.append({'url': url, 'error': str(e)})
            failed += 1
            time.sleep(5)
    
    page.close()
    
    # Save results
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'hackathon_details_full_{timestamp}.json'
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump({
            'scraped_at': datetime.now().isoformat(),
            'total': len(results),
            'successful': successful,
            'failed': failed,
            'hackathons': results
        }, f, indent=2, ensure_ascii=False)
    
    print(f"\n💾 Full details saved to: {filename}")
    print(f"   File size: {os.path.getsize(filename)} bytes")
    
    # Save just the descriptions separately
    desc_filename = f'all_descriptions_{timestamp}.txt'
    with open(desc_filename, 'w', encoding='utf-8') as f:
        for i, h in enumerate(results, 1):
            if not h.get('error'):
                f.write(f"\n{'='*70}\n")
                f.write(f"📌 {i}. {h.get('title', 'Unknown')}\n")
                f.write(f"{'='*70}\n")
                f.write(f"URL: {h.get('url', 'N/A')}\n")
                f.write(f"Organizer: {h.get('organizer', 'N/A')}\n")
                f.write(f"Team Size: {h.get('team_size', 'N/A')}\n")
                f.write(f"Status: {h.get('status', 'N/A')}\n")
                f.write(f"Dates: {', '.join(h.get('dates', [])) if h.get('dates') else 'N/A'}\n")
                f.write(f"Prizes: {', '.join(h.get('prizes', [])) if h.get('prizes') else 'N/A'}\n")
                f.write(f"Register Button: {h.get('has_register_button', False)}\n")
                f.write(f"\nDESCRIPTION:\n{'-'*70}\n")
                f.write(f"{h.get('description', 'No description available')}\n")
                f.write(f"{'-'*70}\n")
    
    print(f"💾 Descriptions saved to: {desc_filename}")
    
    return results

def main():
    print("\n" + "=" * 70)
    print("📋 UNSTOP HACKATHON DETAIL FETCHER")
    print("   Complete descriptions - no truncation")
    print("=" * 70)
    
    available_files = []
    for f in ['hackathon_urls_open.txt', 'hackathon_urls_closed.txt', 
              'hackathon_urls_upcoming.txt', 'hackathon_urls_all.txt']:
        if os.path.exists(f):
            with open(f, 'r') as file:
                count = sum(1 for _ in file)
            available_files.append((f, count))
    
    if not available_files:
        print("❌ No URL files found!")
        return
    
    print("\n📂 Available URL files:")
    for i, (f, count) in enumerate(available_files, 1):
        print(f"   {i}. {f} ({count} URLs)")
    
    choice = input("\nSelect file [1-{}]: ".format(len(available_files))).strip()
    try:
        idx = int(choice) - 1
        filename = available_files[idx][0]
    except:
        filename = available_files[0][0]
    
    urls = load_urls(filename)
    if not urls:
        return
    
    print(f"\n✅ Loaded {len(urls)} URLs from {filename}")
    
    max_to_fetch = input(f"\nHow many to fetch? (max {len(urls)}, default 5): ").strip()
    if not max_to_fetch:
        max_to_fetch = 5
    else:
        max_to_fetch = min(int(max_to_fetch), len(urls))
    
    print("\n⏳ Rate limit settings (seconds between requests)")
    delay_min = input("   Min delay (default 3): ").strip()
    delay_max = input("   Max delay (default 8): ").strip()
    
    delay_min = float(delay_min) if delay_min else 3.0
    delay_max = float(delay_max) if delay_max else 8.0
    
    print(f"\n📊 Will fetch {max_to_fetch} hackathons with {delay_min}-{delay_max}s delays")
    confirm = input("Continue? (y/N): ").strip().lower()
    
    if confirm != 'y':
        print("❌ Cancelled")
        return
    
    results = fetch_all_details(urls, max_to_fetch, delay_min, delay_max)
    
    # Show summary
    successful = len([r for r in results if not r.get('error')])
    print(f"\n📊 Summary: {successful}/{len(results)} successful")
    
    print("\n✅ Done!")

if __name__ == "__main__":
    main()
