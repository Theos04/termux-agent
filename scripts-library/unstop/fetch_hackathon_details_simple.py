#!/data/data/com.termux/files/usr/bin/env python3
"""
Simple hackathon detail fetcher - uses geturl.py's working approach
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

def extract_hackathon_details(page, url):
    """Extract hackathon details using simple text extraction"""
    
    print(f"   📄 Navigating to: {url[:80]}...")
    page.js(f"window.location.href = '{url}'")
    time.sleep(8)
    
    # Get page text (this works!)
    text = page.js("return document.body ? document.body.innerText : ''")
    
    if not text:
        return {'url': url, 'error': 'No text content', 'title': 'Unknown'}
    
    # Parse text using regex patterns
    details = {
        'url': url,
        'title': 'Unknown',
        'organizer': 'Unknown',
        'team_size': 'Unknown',
        'status': 'Unknown',
        'prizes': [],
        'dates': [],
        'eligibility': 'Unknown',
        'has_register_button': False,
        'hackathon_id': None
    }
    
    # Extract hackathon ID from URL
    id_match = re.search(r'/hackathons/(\d+)', url)
    if id_match:
        details['hackathon_id'] = id_match.group(1)
    
    # Extract title (first few lines)
    lines = text.split('\n')
    for line in lines[:10]:
        line = line.strip()
        if line and len(line) > 10 and not line.startswith('Home') and not line.startswith('Internships'):
            # Skip navigation items
            if line not in ['Home', 'Internships', 'Jobs', 'Competitions', 'Mentorship', 
                           'Mock Tests', 'Mock Interview', '100 Days to Code', 'Courses', 
                           'Practice', 'Scholarships', 'Cultural Events', 'Workshops', 
                           'Conferences', 'Articles', 'Your Dashboards', 'My Activity']:
                details['title'] = line
                break
    
    # Extract organizer
    org_patterns = [
        r'Organized by[:\s]+([^\n]+)',
        r'Hosted by[:\s]+([^\n]+)',
        r'Organiser[:\s]+([^\n]+)'
    ]
    for pattern in org_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            details['organizer'] = match.group(1).strip()
            break
    
    # Extract team size
    team_match = re.search(r'Team Size[:\s]+([^\n]+)', text, re.IGNORECASE)
    if team_match:
        details['team_size'] = team_match.group(1).strip()
    
    # Extract status from URL or page
    if 'oppstatus=open' in url:
        details['status'] = 'Open'
    elif 'oppstatus=closed' in url:
        details['status'] = 'Closed'
    elif 'oppstatus=upcoming' in url:
        details['status'] = 'Upcoming'
    
    # Extract dates
    date_patterns = [
        r'(\d{1,2}\s+[A-Za-z]+\s+\d{4})',
        r'(\d{4}-\d{2}-\d{2})',
        r'(\d{1,2}/\d{1,2}/\d{4})'
    ]
    for pattern in date_patterns:
        matches = re.findall(pattern, text)
        if matches:
            details['dates'] = matches[:5]
            break
    
    # Extract prizes
    prize_section = re.search(r'Prize[:\s]+([^\n]+(?:\n[^\n]+)*?)(?:\n\n|\n[A-Z])', text, re.IGNORECASE)
    if prize_section:
        prize_text = prize_section.group(1).strip()
        details['prizes'] = [p.strip() for p in prize_text.split('\n') if p.strip()]
    
    # Check for register button
    register_indicators = ['Register', 'Apply', 'Enroll', 'Join Now']
    for indicator in register_indicators:
        if indicator.lower() in text.lower():
            details['has_register_button'] = True
            break
    
    # Check for "Already Registered" or "Registered"
    if 'already registered' in text.lower() or 'you are registered' in text.lower():
        details['already_registered'] = True
    else:
        details['already_registered'] = False
    
    # Extract eligibility
    elig_match = re.search(r'Eligibility[:\s]+([^\n]+)', text, re.IGNORECASE)
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
    
    # Extract word count
    details['word_count'] = len(text.split())
    
    return details

def fetch_all_details(urls, max_to_fetch=10, delay_min=3, delay_max=8):
    results = []
    successful = 0
    failed = 0
    
    print(f"\n📊 Fetching details for up to {max_to_fetch} hackathons...")
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
                print(f"   ✅ {details.get('title', 'Unknown')[:60]}")
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
    filename = f'hackathon_details_{timestamp}.json'
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump({
            'scraped_at': datetime.now().isoformat(),
            'total': len(results),
            'successful': successful,
            'failed': failed,
            'hackathons': results
        }, f, indent=2)
    
    print(f"\n💾 Saved to: {filename}")
    
    # Also save as CSV
    csv_filename = f'hackathon_summary_{timestamp}.csv'
    with open(csv_filename, 'w', encoding='utf-8') as f:
        f.write("ID,Title,Status,Organizer,Team Size,Register Button,URL\n")
        for h in results:
            if not h.get('error'):
                f.write(f"{h.get('hackathon_id', '')},{h.get('title', '').replace(',', ';')},"
                       f"{h.get('status', '')},{h.get('organizer', '').replace(',', ';')},"
                       f"{h.get('team_size', '')},{h.get('has_register_button', False)},{h.get('url', '')}\n")
    
    print(f"💾 Summary CSV saved to: {csv_filename}")
    
    return results

def main():
    print("\n" + "=" * 70)
    print("📋 UNSTOP HACKATHON DETAIL FETCHER (SIMPLE)")
    print("   Uses text extraction like geturl.py")
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
