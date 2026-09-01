#!/data/data/com.termux/files/usr/bin/env python3
"""
Fetch detailed structured data from hackathon pages - V2
Based on actual Unstop page structure
"""

import sys
import json
import time
import os
import re
from typing import List, Dict, Optional
from datetime import datetime
import random

sys.path.insert(0, '/data/data/com.termux/files/home/automation/chrome-launcher')

try:
    from geturl import ChromePage
    print("✅ Loaded ChromePage from geturl.py")
except ImportError as e:
    print(f"❌ Could not import ChromePage: {e}")
    sys.exit(1)

def load_urls(filename="hackathon_urls_open.txt"):
    """Load hackathon URLs from file"""
    if not os.path.exists(filename):
        print(f"❌ File not found: {filename}")
        return []
    
    with open(filename, 'r') as f:
        urls = [line.strip() for line in f if line.strip()]
    return urls

def extract_hackathon_details_v2(page, url):
    """Extract detailed structured data from hackathon page - V2"""
    
    print(f"   📄 Navigating to: {url[:80]}...")
    page.js(f"window.location.href = '{url}'")
    
    # Wait for page to load
    print("   ⏳ Waiting for page to load...")
    time.sleep(8)
    
    # Wait for content
    for i in range(10):
        ready = page.js("return document.readyState")
        if ready == "complete":
            break
        time.sleep(1)
    
    time.sleep(3)
    
    # Get page text for debugging
    page_text = page.js("return document.body ? document.body.innerText : ''")
    
    script = """
    (function() {
        const data = {
            url: window.location.href,
            scraped_at: new Date().toISOString()
        };
        
        // Helper to get text from element
        function getText(selector) {
            const el = document.querySelector(selector);
            return el ? el.textContent.trim() : null;
        }
        
        // Helper to get all text from elements
        function getTexts(selector) {
            const els = document.querySelectorAll(selector);
            return Array.from(els).map(el => el.textContent.trim()).filter(Boolean);
        }
        
        // Helper to find text in page
        function findInPage(pattern) {
            const body = document.body ? document.body.innerText : '';
            const match = body.match(pattern);
            return match ? match[1] || match[0] : null;
        }
        
        // 1. Title - from h1 or page title
        const titleEl = document.querySelector('h1');
        if (titleEl) {
            data.title = titleEl.textContent.trim();
        }
        if (!data.title) {
            data.title = document.title || 'Unknown';
        }
        // Clean up title - remove "Unstop - " prefix if present
        if (data.title && data.title.startsWith('Unstop - ')) {
            data.title = data.title.replace('Unstop - ', '');
        }
        
        // 2. Description - from various sources
        const descSelectors = [
            '.description',
            '.event-description',
            '.hackathon-description',
            '[class*="description"]',
            '.about-section',
            '#description'
        ];
        for (const sel of descSelectors) {
            const desc = getText(sel);
            if (desc && desc.length > 20) {
                data.description = desc;
                break;
            }
        }
        if (!data.description) {
            // Try meta description
            const metaDesc = document.querySelector('meta[name="description"]');
            if (metaDesc) {
                data.description = metaDesc.getAttribute('content');
            }
        }
        
        // 3. Organizer/Host
        const orgSelectors = [
            '.organizer',
            '.host',
            '.organised-by',
            '.hosted-by',
            '[class*="organizer"]',
            '[class*="host"]',
            '.company-name'
        ];
        for (const sel of orgSelectors) {
            const org = getText(sel);
            if (org && org.length > 2) {
                data.organizer = org;
                break;
            }
        }
        if (!data.organizer) {
            // Try to find from page text
            const orgMatch = document.body ? document.body.innerText.match(/Organized by[:\s]+([^\n]+)/i) : null;
            if (orgMatch) {
                data.organizer = orgMatch[1].trim();
            }
        }
        
        // 4. Team Size
        const teamMatch = document.body ? document.body.innerText.match(/Team Size[:\s]+([^\n]+)/i) : null;
        if (teamMatch) {
            data.team_size = teamMatch[1].trim();
        }
        if (!data.team_size) {
            const teamSelectors = [
                '.team-size',
                '.team',
                '[class*="team-size"]',
                '[class*="team"]'
            ];
            for (const sel of teamSelectors) {
                const team = getText(sel);
                if (team && team.length > 2) {
                    data.team_size = team;
                    break;
                }
            }
        }
        
        // 5. Dates
        const dateSelectors = [
            '.dates',
            '.event-dates',
            '.hackathon-dates',
            '[class*="date"]',
            '.timeline'
        ];
        const dates = [];
        for (const sel of dateSelectors) {
            const els = document.querySelectorAll(sel);
            for (const el of els) {
                const text = el.textContent.trim();
                if (text && text.length > 5) {
                    dates.push(text);
                }
            }
        }
        // Also look for date patterns in page text
        if (dates.length === 0) {
            const body = document.body ? document.body.innerText : '';
            const dateMatches = body.match(/\\d{1,2}\\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\\s+\\d{4}/g);
            if (dateMatches) {
                dates.push(...dateMatches);
            }
        }
        data.dates = dates;
        
        // 6. Prizes
        const prizeSelectors = [
            '.prizes',
            '.prize',
            '.rewards',
            '.awards',
            '[class*="prize"]',
            '[class*="reward"]'
        ];
        const prizes = [];
        for (const sel of prizeSelectors) {
            const els = document.querySelectorAll(sel);
            for (const el of els) {
                const text = el.textContent.trim();
                if (text && text.length > 5) {
                    prizes.push(text);
                }
            }
        }
        // Look for Prize Pool in page text
        if (prizes.length === 0) {
            const body = document.body ? document.body.innerText : '';
            const prizeMatch = body.match(/Prize Pool[:\s]+([^\\n]+)/i);
            if (prizeMatch) {
                prizes.push(prizeMatch[1].trim());
            }
        }
        data.prizes = prizes;
        
        // 7. Status (open/closed/upcoming) - from URL or page
        const url = window.location.href;
        if (url.includes('oppstatus=open')) {
            data.status = 'open';
        } else if (url.includes('oppstatus=closed')) {
            data.status = 'closed';
        } else if (url.includes('oppstatus=upcoming')) {
            data.status = 'upcoming';
        } else {
            // Try to find status in page
            const statusSelectors = [
                '.status',
                '.oppstatus',
                '[class*="status"]',
                '[class*="open"]',
                '[class*="closed"]',
                '[class*="upcoming"]'
            ];
            for (const sel of statusSelectors) {
                const status = getText(sel);
                if (status) {
                    data.status = status;
                    break;
                }
            }
        }
        
        // 8. Eligibility
        const eligMatch = document.body ? document.body.innerText.match(/Eligibility[:\s]+([^\\n]+)/i) : null;
        if (eligMatch) {
            data.eligibility = eligMatch[1].trim();
        }
        
        // 9. Registration Deadline
        const deadlineMatch = document.body ? document.body.innerText.match(/Registration Deadline[:\s]+([^\\n]+)/i) : null;
        if (deadlineMatch) {
            data.registration_deadline = deadlineMatch[1].trim();
        }
        if (!data.registration_deadline) {
            const regSelectors = [
                '.registration-deadline',
                '.deadline',
                '.reg-deadline',
                '[class*="deadline"]'
            ];
            for (const sel of regSelectors) {
                const deadline = getText(sel);
                if (deadline) {
                    data.registration_deadline = deadline;
                    break;
                }
            }
        }
        
        // 10. Location/Venue
        const locMatch = document.body ? document.body.innerText.match(/Location[:\s]+([^\\n]+)/i) : null;
        if (locMatch) {
            data.location = locMatch[1].trim();
        }
        if (!data.location) {
            const locationSelectors = [
                '.location',
                '.venue',
                '.address',
                '[class*="location"]',
                '[class*="venue"]'
            ];
            for (const sel of locationSelectors) {
                const loc = getText(sel);
                if (loc) {
                    data.location = loc;
                    break;
                }
            }
        }
        
        // 11. Registration button
        const regBtn = document.querySelector(
            'a[href*="register"], button:contains("Register"), ' +
            'a:contains("Register"), button:contains("Apply"), ' +
            'a:contains("Apply"), .register-btn, .apply-btn, ' +
            'a[href*="registerNow"]'
        );
        data.has_register_button = !!regBtn;
        data.register_url = regBtn ? regBtn.href || null : null;
        
        // 12. Hackathon ID
        const idMatch = window.location.href.match(/\\/hackathons\\/(\\d+)/);
        data.hackathon_id = idMatch ? idMatch[1] : null;
        
        // 13. Category/Tags
        const categoryMatch = document.body ? document.body.innerText.match(/Category[:\s]+([^\\n]+)/i) : null;
        if (categoryMatch) {
            data.category = categoryMatch[1].trim();
        }
        
        // 14. Word count
        data.word_count = document.body ? document.body.innerText.split(/\\s+/).length : 0;
        
        // 15. Page text sample (for debugging)
        data.page_text_sample = document.body ? document.body.innerText.slice(0, 500) : null;
        
        return data;
    })();
    """
    
    result = page.js(script)
    
    if result and isinstance(result, dict):
        result['url'] = url
        result['scraped_at'] = datetime.now().isoformat()
        return result
    
    return {'url': url, 'error': 'Failed to extract details'}

def fetch_all_details(urls, max_to_fetch=10, delay_min=3, delay_max=8):
    """Fetch details for multiple hackathons with rate limiting"""
    
    results = []
    successful = 0
    failed = 0
    
    print(f"\n📊 Fetching details for up to {max_to_fetch} hackathons...")
    print("=" * 70)
    print("⏳ Rate limiting: {}-{} seconds delay between requests".format(delay_min, delay_max))
    print("=" * 70)
    
    # Connect to Chrome
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
            details = extract_hackathon_details_v2(page, url)
            
            if details and not details.get('error'):
                results.append(details)
                successful += 1
                print(f"   ✅ {details.get('title', 'Unknown')[:60]}")
                print(f"      📅 Status: {details.get('status', 'N/A')}")
                print(f"      🏆 Prizes: {len(details.get('prizes', []))} found")
                print(f"      👥 Team: {details.get('team_size', 'N/A')}")
                print(f"      🔘 Register: {details.get('has_register_button', False)}")
            else:
                results.append({'url': url, 'error': 'Extraction failed'})
                failed += 1
                print(f"   ❌ Failed to extract details")
            
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
    save_results(results, successful, failed)
    return results

def save_results(results, successful, failed):
    """Save results to files"""
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'hackathon_details_full_{timestamp}.json'
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump({
            'scraped_at': datetime.now().isoformat(),
            'total': len(results),
            'successful': successful,
            'failed': failed,
            'hackathons': results
        }, f, indent=2)
    print(f"\n💾 Full details saved to: {filename}")
    
    # Save summary CSV
    csv_filename = f'hackathon_summary_{timestamp}.csv'
    with open(csv_filename, 'w', encoding='utf-8') as f:
        f.write("ID,Title,Status,Organizer,Team Size,Category,Has Register,URL\n")
        for h in results:
            if not h.get('error'):
                id_val = h.get('hackathon_id', '')
                title = h.get('title', '').replace(',', ';')
                status = h.get('status', '').replace(',', ';')
                organizer = h.get('organizer', '').replace(',', ';')
                team_size = h.get('team_size', '').replace(',', ';')
                category = h.get('category', '').replace(',', ';')
                has_register = str(h.get('has_register_button', False))
                url = h.get('url', '')
                f.write(f"{id_val},{title},{status},{organizer},{team_size},{category},{has_register},{url}\n")
    print(f"💾 Summary CSV saved to: {csv_filename}")

def main():
    print("\n" + "=" * 70)
    print("📋 UNSTOP HACKATHON DETAIL FETCHER V2")
    print("   Based on actual page structure")
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
    
    if delay_min > delay_max:
        delay_min, delay_max = delay_max, delay_min
    
    print(f"\n📊 Will fetch {max_to_fetch} hackathons with {delay_min}-{delay_max}s delays")
    confirm = input("Continue? (y/N): ").strip().lower()
    
    if confirm != 'y':
        print("❌ Cancelled")
        return
    
    results = fetch_all_details(urls, max_to_fetch, delay_min, delay_max)
    
    print("\n✅ Done!")

if __name__ == "__main__":
    main()
