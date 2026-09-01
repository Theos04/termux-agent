#!/data/data/com.termux/files/usr/bin/env python3
"""
Fetch hackathon details using geturl.py's ChromePage class
Extracts: title, description, organizer, dates, prizes, team size, status, etc.
"""

import sys
import json
import time
import os
import re
from datetime import datetime
import random

# Import ChromePage from geturl.py
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
    """Extract complete hackathon details using geturl.py's methods"""
    
    print(f"   📄 Navigating to: {url[:80]}...")
    
    # Use navigate_to from geturl.py
    page.navigate_to(url)
    
    # Wait for page to load
    print("   ⏳ Waiting for page to load...")
    time.sleep(5)
    
    # Get page text using geturl.py's get_text() method
    text = page.get_text()
    
    if not text or len(text) < 100:
        print("   ⚠️ Page text is empty or too short")
        return {'url': url, 'error': 'No text content', 'title': 'Unknown'}
    
    # Get page title
    title = page.get_title()
    
    # Initialize details dictionary with all fields
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
        'tags': [],
        'page_text_sample': text[:1000] if text else None
    }
    
    # Extract hackathon ID from URL
    id_match = re.search(r'/hackathons/(\d+)', url)
    if id_match:
        details['hackathon_id'] = id_match.group(1)
    
    # Clean title - remove " - 2026" suffix if present
    if details['title'] and details['title'].endswith(' - 2026'):
        details['title'] = details['title'].replace(' - 2026', '')
    
    # Extract title from page if page title is generic
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
            # Clean up organizer (remove extra text like "scheduled for...")
            org = re.sub(r',\s+scheduled\s+for.*$', '', org)
            org = re.sub(r',\s+\d{1,2}–\d{1,2}\s+[A-Za-z]+\s+\d{4}.*$', '', org)
            details['organizer'] = org
            break
    
    # If organizer not found, try to find it in text
    if details['organizer'] == 'Unknown':
        org_match = re.search(r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+(?:presents|organizes|hosts|brings)', text)
        if org_match:
            details['organizer'] = org_match.group(1).strip()
    
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
    
    # If not in URL, try to find in text
    if details['status'] == 'Unknown':
        status_match = re.search(r'Status[:\s]+([^\n]+)', text, re.IGNORECASE)
        if status_match:
            details['status'] = status_match.group(1).strip()
    
    # ========================================================================
    # EXTRACT COMPLETE DESCRIPTION - FIXED VERSION
    # ========================================================================
    
    # Find the "All that you need to know about" section
    desc_start = re.search(r'All that you need to know about[^\n]*\n', text, re.IGNORECASE)
    
    if desc_start:
        start_pos = desc_start.end()
        
        # Find where the description ends (look for "Read More" or "Feedback & Rating" or "Frequently Asked Questions")
        end_patterns = [
            r'\nRead More\n',
            r'\nFeedback & Rating\n',
            r'\nFrequently Asked Questions\n',
            r'\nFAQs & Discussions\n',
            r'\nUnstop PRO Now',
            r'\nGo Pro Now\n',
            r'\nUpdated On:'
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
        
        # Clean up the description
        desc_text = re.sub(r'\s+', ' ', desc_text)
        desc_text = re.sub(r'\n+', '\n', desc_text)
        
        # Remove any remaining navigation items
        desc_text = re.sub(r'^Overview\s*', '', desc_text)
        desc_text = re.sub(r'^Eligibility & Registration\s*', '', desc_text)
        desc_text = re.sub(r'^Competition Structure\s*', '', desc_text)
        desc_text = re.sub(r'^Rewards & Prizes\s*', '', desc_text)
        
        if len(desc_text) > 50:
            details['description'] = desc_text[:3000]  # Limit to 3000 chars
    
    # If no description found, try to get the full text after the title
    if not details['description']:
        lines = text.split('\n')
        desc_lines = []
        found_section = False
        
        for i, line in enumerate(lines):
            if 'All that you need to know about' in line:
                found_section = True
                continue
            if found_section:
                # Stop at "Read More" or "Feedback"
                if 'Read More' in line or 'Feedback & Rating' in line or 'FAQs' in line:
                    break
                if line.strip() and not line.strip() in ['Overview', 'Eligibility & Registration', 'Competition Structure', 'Rewards & Prizes']:
                    desc_lines.append(line.strip())
                if len(' '.join(desc_lines)) > 1000:
                    break
        
        if desc_lines:
            details['description'] = ' '.join(desc_lines)[:3000]
    
    # Extract dates - look for dates in the text
    date_patterns = [
        r'(\d{1,2}\s+[A-Za-z]+\s+\d{4})',
        r'(\d{4}-\d{2}-\d{2})',
        r'(\d{1,2}/\d{1,2}/\d{4})',
        r'(\d{1,2}\s+[A-Za-z]{3,}\s+\d{4})',
        r'(\d{1,2}\s+[A-Za-z]+\s+\d{4},\s+\d{1,2}:\d{2}\s+[AP]M)'
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
    
    # If no prizes found, try to find prize amounts
    if not details['prizes']:
        amount_patterns = [
            r'₹\s*([\d,]+)',
            r'\$\s*([\d,]+)',
            r'([\d,]+)\s*INR'
        ]
        amounts = []
        for pattern in amount_patterns:
            matches = re.findall(pattern, text)
            if matches:
                amounts.extend(matches)
        if amounts:
            details['prizes'] = [f"₹{a}" for a in amounts[:5]]
            details['prize_amount'] = ', '.join(amounts[:3])
    
    # Extract sponsors
    sponsor_match = re.search(r'Sponsors?[:\s]+([^\n]+(?:\n[^\n]+)*?)(?:\n\s*\n|\n(?:Categories|Team|Eligibility))', text, re.IGNORECASE)
    if sponsor_match:
        sponsors = [s.strip() for s in sponsor_match.group(1).split('\n') if s.strip() and len(s.strip()) > 2]
        details['sponsors'] = sponsors[:10]
    
    # Extract categories/tags
    category_patterns = [
        r'Categories?[:\s]+([^\n]+)',
        r'Tags?[:\s]+([^\n]+)',
        r'Competition Categories?[:\s]+([^\n]+)'
    ]
    for pattern in category_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            cats = [c.strip() for c in match.group(1).split('\n') if c.strip()]
            details['tags'] = cats[:10]
            if cats:
                details['category'] = cats[0]
            break
    
    # Extract eligibility
    elig_match = re.search(r'Eligibility[:\s]+([^\n]+(?:\n[^\n]+)*?)(?:\n\s*\n|\n(?:Team|Dates|Prizes))', text, re.IGNORECASE)
    if elig_match:
        details['eligibility'] = elig_match.group(1).strip()
    
    # Extract registration deadline
    deadline_patterns = [
        r'Registration Deadline[:\s]+([^\n]+)',
        r'Deadline[:\s]+([^\n]+)',
        r'Register by[:\s]+([^\n]+)'
    ]
    for pattern in deadline_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            details['registration_deadline'] = match.group(1).strip()
            break
    
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
    registered_keywords = ['already registered', 'you are registered', 'registered successfully']
    for keyword in registered_keywords:
        if keyword.lower() in text.lower():
            details['already_registered'] = True
            break
    
    # Word count
    details['word_count'] = len(text.split())
    
    # Fix organizer if it contains extra text
    if 'scheduled for' in details.get('organizer', ''):
        org = details['organizer']
        org = re.sub(r',\s+scheduled\s+for.*$', '', org)
        org = re.sub(r',\s+\d{1,2}–\d{1,2}\s+[A-Za-z]+\s+\d{4}.*$', '', org)
        details['organizer'] = org
    
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
                print(f"   ✅ {details.get('title', 'Unknown')[:60]}")
                print(f"      📅 Status: {details.get('status', 'N/A')}")
                print(f"      👥 Team: {details.get('team_size', 'N/A')}")
                print(f"      🏆 Prizes: {len(details.get('prizes', []))} found")
                desc_preview = details.get('description', '')
                if desc_preview:
                    print(f"      📝 Desc: {desc_preview[:80]}..." if len(desc_preview) > 80 else f"      📝 Desc: {desc_preview}")
                else:
                    print(f"      📝 Desc: None")
                print(f"      🔘 Register: {details.get('has_register_button', False)}")
                if details.get('already_registered'):
                    print(f"      ⚠️ Already registered!")
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
    
    print(f"\n💾 Full details saved to: {filename}")
    
    # Also save as CSV with more fields
    csv_filename = f'hackathon_summary_{timestamp}.csv'
    with open(csv_filename, 'w', encoding='utf-8') as f:
        f.write("ID,Title,Status,Organizer,Team Size,Register Button,Already Registered,"
                "Prizes Count,Description Preview,URL\n")
        for h in results:
            if not h.get('error'):
                desc_preview = h.get('description', '')[:200].replace(',', ';') if h.get('description') else ''
                f.write(f"{h.get('hackathon_id', '')},"
                       f"{h.get('title', '').replace(',', ';')},"
                       f"{h.get('status', '')},"
                       f"{h.get('organizer', '').replace(',', ';')},"
                       f"{h.get('team_size', '')},"
                       f"{h.get('has_register_button', False)},"
                       f"{h.get('already_registered', False)},"
                       f"{len(h.get('prizes', []))},"
                       f"{desc_preview},"
                       f"{h.get('url', '')}\n")
    
    print(f"💾 Summary CSV saved to: {csv_filename}")
    
    return results

def main():
    print("\n" + "=" * 70)
    print("📋 UNSTOP HACKATHON DETAIL FETCHER")
    print("   Extracts: Title, Description, Organizer, Dates, Prizes, etc.")
    print("=" * 70)
    
    # Check for URL files
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
    
    if successful > 0:
        print("\n📋 Sample fetched data:")
        for r in results[:3]:
            if not r.get('error'):
                print(f"\n   📌 Title: {r.get('title', 'Unknown')}")
                print(f"   🏢 Organizer: {r.get('organizer', 'N/A')}")
                print(f"   📅 Status: {r.get('status', 'N/A')}")
                print(f"   👥 Team Size: {r.get('team_size', 'N/A')}")
                desc = r.get('description', '')
                if desc:
                    print(f"   📝 Description: {desc[:300]}..." if len(desc) > 300 else f"   📝 Description: {desc}")
                else:
                    print(f"   📝 Description: None")
                print(f"   🏆 Prizes: {len(r.get('prizes', []))} found")
                if r.get('prizes'):
                    for prize in r.get('prizes', [])[:3]:
                        print(f"      • {prize}")
                if r.get('dates'):
                    print(f"   📅 Dates: {', '.join(r.get('dates', []))}")
                print(f"   🔘 Register: {r.get('has_register_button', False)}")
    
    print("\n✅ Done!")

if __name__ == "__main__":
    main()
