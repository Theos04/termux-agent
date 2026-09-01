#!/data/data/com.termux/files/usr/bin/env python3
"""
Fetch detailed structured data from hackathon pages
Extracts: title, description, dates, prizes, organizers, eligibility, etc.
"""

import sys
import json
import time
import os
import re
from typing import List, Dict, Optional
from datetime import datetime
import random

# Fix: Add current directory to path for imports
sys.path.insert(0, '/data/data/com.termux/files/home/automation/chrome-launcher')

# Import ChromePage from geturl.py
try:
    from geturl import ChromePage
    print("✅ Loaded ChromePage from geturl.py")
except ImportError as e:
    print(f"❌ Could not import ChromePage: {e}")
    print("   Trying direct import...")
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("geturl", "geturl.py")
        geturl = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(geturl)
        ChromePage = geturl.ChromePage
        print("✅ Loaded ChromePage via direct import")
    except Exception as e2:
        print(f"❌ Failed to import ChromePage: {e2}")
        sys.exit(1)

def load_urls(filename="hackathon_urls_open.txt"):
    """Load hackathon URLs from file"""
    if not os.path.exists(filename):
        print(f"❌ File not found: {filename}")
        return []
    
    with open(filename, 'r') as f:
        urls = [line.strip() for line in f if line.strip()]
    return urls

def extract_hackathon_details(page, url):
    """Extract detailed structured data from hackathon page"""
    
    # Navigate to the page
    print(f"   📄 Navigating to: {url[:60]}...")
    page.js(f"window.location.href = '{url}'")
    time.sleep(5)  # Initial load
    
    # Wait for page to fully load
    max_wait = 15
    for i in range(max_wait):
        ready = page.js("return document.readyState")
        if ready == "complete":
            break
        time.sleep(1)
    
    # Extra wait for dynamic content
    time.sleep(3)
    
    script = """
    (function() {
        const data = {
            url: window.location.href,
            scraped_at: new Date().toISOString()
        };
        
        // Helper function to get text content
        function getText(selector) {
            const el = document.querySelector(selector);
            return el ? el.textContent.trim() : null;
        }
        
        // Helper to get all text from elements matching selector
        function getTexts(selector) {
            const els = document.querySelectorAll(selector);
            return Array.from(els).map(el => el.textContent.trim()).filter(Boolean);
        }
        
        // 1. Title
        const titleSelectors = [
            'h1',
            '.hackathon-title',
            '.event-title',
            '.competition-title',
            '[class*="title"]',
            'h1[class*="title"]'
        ];
        for (const sel of titleSelectors) {
            const title = getText(sel);
            if (title && title.length > 5) {
                data.title = title;
                break;
            }
        }
        if (!data.title) {
            data.title = document.title || 'Unknown';
        }
        
        // 2. Description
        const descSelectors = [
            '.description',
            '.event-description',
            '.hackathon-description',
            '[class*="desc"]',
            '.about',
            '.about-event',
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
            // Try to get from meta description
            const metaDesc = document.querySelector('meta[name="description"]');
            if (metaDesc) {
                data.description = metaDesc.getAttribute('content');
            }
        }
        
        // 3. Dates and Times
        const dateSelectors = [
            '.dates',
            '.event-dates',
            '.hackathon-dates',
            '[class*="date"]',
            '[class*="time"]',
            '.timeline',
            '.schedule'
        ];
        const dates = [];
        for (const sel of dateSelectors) {
            const elements = document.querySelectorAll(sel);
            for (const el of elements) {
                const text = el.textContent.trim();
                if (text && (text.includes('Date') || text.includes('Time') || 
                            text.includes('from') || text.includes('to') ||
                            text.match(/\\d{1,2}\\s+[A-Za-z]+\\s+\\d{4}/) ||
                            text.match(/\\d{4}-\\d{2}-\\d{2}/))) {
                    dates.push(text);
                }
            }
        }
        data.dates = dates;
        
        // 4. Location/Venue
        const locationSelectors = [
            '.location',
            '.venue',
            '.address',
            '[class*="location"]',
            '[class*="venue"]',
            '.place'
        ];
        data.location = getText(locationSelectors.join(',')) || null;
        
        // 5. Organizer/Host
        const orgSelectors = [
            '.organizer',
            '.host',
            '.organised-by',
            '.hosted-by',
            '[class*="organizer"]',
            '[class*="host"]',
            '.company-name',
            '.sponsor'
        ];
        data.organizer = getText(orgSelectors.join(',')) || null;
        
        // 6. Prizes
        const prizeSelectors = [
            '.prizes',
            '.prize',
            '.rewards',
            '.awards',
            '[class*="prize"]',
            '[class*="reward"]',
            '[class*="award"]'
        ];
        data.prizes = getTexts(prizeSelectors.join(','));
        
        // 7. Status/Type
        const statusSelectors = [
            '.status',
            '.oppstatus',
            '.competition-status',
            '[class*="status"]',
            '[class*="open"]',
            '[class*="closed"]',
            '[class*="upcoming"]'
        ];
        data.status = getText(statusSelectors.join(',')) || null;
        
        // 8. Team size
        const teamSelectors = [
            '.team-size',
            '.team',
            '[class*="team"]',
            '.members',
            '.participants'
        ];
        data.team_size = getText(teamSelectors.join(',')) || null;
        
        // 9. Registration deadline
        const regSelectors = [
            '.registration-deadline',
            '.deadline',
            '.reg-deadline',
            '[class*="deadline"]',
            '[class*="register-before"]'
        ];
        data.registration_deadline = getText(regSelectors.join(',')) || null;
        
        // 10. Registration button
        const regBtn = document.querySelector(
            'a[href*="register"], button:contains("Register"), ' +
            'a:contains("Register"), button:contains("Apply"), ' +
            'a:contains("Apply"), .register-btn, .apply-btn'
        );
        data.has_register_button = !!regBtn;
        data.register_url = regBtn ? regBtn.href || null : null;
        
        // 11. Tags/Categories
        const tagSelectors = [
            '.tags',
            '.categories',
            '.skills',
            '[class*="tag"]',
            '[class*="category"]'
        ];
        data.tags = getTexts(tagSelectors.join(','));
        
        // 12. Prize amount (numeric)
        const prizeTexts = data.prizes.join(' ');
        const prizeMatches = prizeTexts.match(/₹\\s*([\\d,]+)/g) || 
                           prizeTexts.match(/\\$\\s*([\\d,]+)/g) ||
                           prizeTexts.match(/([\\d,]+)\\s*INR/g);
        data.prize_amount = prizeMatches ? prizeMatches.join(', ') : null;
        
        // 13. Extract hackathon ID from URL
        const idMatch = window.location.href.match(/\\/hackathons\\/(\\d+)/);
        data.hackathon_id = idMatch ? idMatch[1] : null;
        
        // 14. Page stats
        data.word_count = document.body ? document.body.innerText.split(/\\s+/).length : 0;
        data.has_forms = document.querySelectorAll('form').length > 0;
        data.link_count = document.querySelectorAll('a[href]').length;
        
        return data;
    })();
    """
    
    result = page.js(script)
    
    # Add the URL if not already present
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
    
    # Take a subset if needed
    urls_to_fetch = urls[:max_to_fetch]
    total = len(urls_to_fetch)
    
    for i, url in enumerate(urls_to_fetch, 1):
        print(f"\n[{i}/{total}] Processing: {url[:80]}...")
        
        try:
            # Extract details
            details = extract_hackathon_details(page, url)
            
            if details and not details.get('error'):
                results.append(details)
                successful += 1
                print(f"   ✅ {details.get('title', 'Unknown')[:60]}")
                print(f"      📅 Status: {details.get('status', 'N/A')}")
                print(f"      🏆 Prizes: {len(details.get('prizes', []))} found")
                print(f"      🔘 Register button: {details.get('has_register_button', False)}")
            else:
                results.append({'url': url, 'error': 'Extraction failed'})
                failed += 1
                print(f"   ❌ Failed to extract details")
            
            # Rate limiting - random delay between requests
            if i < total:
                delay = random.uniform(delay_min, delay_max)
                print(f"   ⏳ Waiting {delay:.1f}s before next request...")
                time.sleep(delay)
                
        except Exception as e:
            print(f"   ❌ Error: {e}")
            results.append({'url': url, 'error': str(e)})
            failed += 1
            # Extra delay after error
            time.sleep(5)
    
    page.close()
    
    # Save results incrementally
    save_results(results, successful, failed)
    
    return results

def save_results(results, successful, failed):
    """Save results to files"""
    
    # Save full results
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
        f.write("ID,Title,Status,Organizer,Team Size,Has Register Button,URL\n")
        for h in results:
            if not h.get('error'):
                id_val = h.get('hackathon_id', '')
                title = h.get('title', '').replace(',', ';')
                status = h.get('status', '').replace(',', ';')
                organizer = h.get('organizer', '').replace(',', ';')
                team_size = h.get('team_size', '').replace(',', ';')
                has_register = str(h.get('has_register_button', False))
                url = h.get('url', '')
                f.write(f"{id_val},{title},{status},{organizer},{team_size},{has_register},{url}\n")
    print(f"💾 Summary CSV saved to: {csv_filename}")
    
    # Save list of successful URLs
    success_urls = [h['url'] for h in results if not h.get('error')]
    if success_urls:
        with open('successful_fetched.txt', 'w', encoding='utf-8') as f:
            f.write('\n'.join(success_urls))
        print(f"💾 {len(success_urls)} successful URLs saved to successful_fetched.txt")
    
    # Save failed URLs for retry
    failed_urls = [h['url'] for h in results if h.get('error')]
    if failed_urls:
        with open('failed_fetch.txt', 'w', encoding='utf-8') as f:
            f.write('\n'.join(failed_urls))
        print(f"💾 {len(failed_urls)} failed URLs saved to failed_fetch.txt")

def show_summary(results):
    """Show summary of fetched data"""
    
    if not results:
        print("❌ No results to summarize")
        return
    
    print("\n" + "=" * 70)
    print("📊 SUMMARY OF FETCHED DATA")
    print("=" * 70)
    
    total = len(results)
    successful = len([r for r in results if not r.get('error')])
    failed = total - successful
    
    print(f"\n📍 Total processed: {total}")
    print(f"   ✅ Successful: {successful}")
    print(f"   ❌ Failed: {failed}")
    
    if successful > 0:
        # Sample of successful results
        print(f"\n📋 Sample of fetched hackathons:")
        sample_count = min(5, successful)
        count = 0
        for r in results:
            if not r.get('error') and count < sample_count:
                print(f"\n   {count+1}. {r.get('title', 'Unknown')}")
                print(f"      Status: {r.get('status', 'N/A')}")
                print(f"      Organizer: {r.get('organizer', 'N/A')}")
                print(f"      Team Size: {r.get('team_size', 'N/A')}")
                print(f"      Has Register: {r.get('has_register_button', False)}")
                if r.get('prizes'):
                    print(f"      Prizes: {', '.join(r.get('prizes', [])[:3])}")
                count += 1
        
        # Statistics
        with_register = len([r for r in results if r.get('has_register_button')])
        print(f"\n📊 Statistics:")
        print(f"   Hackathons with register button: {with_register}/{successful}")
        
        # Status distribution
        statuses = {}
        for r in results:
            if not r.get('error'):
                status = r.get('status', 'unknown')
                statuses[status] = statuses.get(status, 0) + 1
        
        if statuses:
            print(f"\n📊 Status distribution:")
            for status, count in sorted(statuses.items(), key=lambda x: -x[1]):
                print(f"   {status}: {count}")

def main():
    print("\n" + "=" * 70)
    print("📋 UNSTOP HACKATHON DETAIL FETCHER")
    print("   Fetches structured data from hackathon pages")
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
        print("   Run the extractor first: python3 unstop_with_pagination.py")
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
    
    # Load URLs
    urls = load_urls(filename)
    if not urls:
        return
    
    print(f"\n✅ Loaded {len(urls)} URLs from {filename}")
    
    # Ask how many to fetch
    max_to_fetch = input(f"\nHow many to fetch? (max {len(urls)}, default 10): ").strip()
    if not max_to_fetch:
        max_to_fetch = 10
    else:
        max_to_fetch = min(int(max_to_fetch), len(urls))
    
    # Rate limit settings
    print("\n⏳ Rate limit settings (seconds between requests)")
    delay_min = input("   Min delay (default 3): ").strip()
    delay_max = input("   Max delay (default 8): ").strip()
    
    delay_min = float(delay_min) if delay_min else 3.0
    delay_max = float(delay_max) if delay_max else 8.0
    
    if delay_min > delay_max:
        delay_min, delay_max = delay_max, delay_min
    
    # Confirm
    print(f"\n📊 Will fetch {max_to_fetch} hackathons with {delay_min}-{delay_max}s delays")
    print(f"   From file: {filename}")
    confirm = input("Continue? (y/N): ").strip().lower()
    
    if confirm != 'y':
        print("❌ Cancelled")
        return
    
    # Fetch details
    results = fetch_all_details(urls, max_to_fetch, delay_min, delay_max)
    
    # Show summary
    show_summary(results)
    
    print("\n✅ Done!")

if __name__ == "__main__":
    main()
