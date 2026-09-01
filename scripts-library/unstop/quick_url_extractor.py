#!/data/data/com.termux/files/usr/bin/env python3
# quick_url_extractor.py - Quick URL extraction with proper waiting

import requests
import json
import time
import re
import sys

API = "http://127.0.0.1:5000"
WAIT_TIME = 15  # Wait 15 seconds for DOM to stabilize

def wait_for_page_load(wait_time=WAIT_TIME):
    """Wait for page to load"""
    print(f"⏳ Waiting {wait_time}s for page to load...")
    time.sleep(wait_time)
    
    # Check if page has content
    try:
        script = "return document.body && document.body.children.length > 0"
        response = requests.post(
            f"{API}/session/unstop/execute",
            json={"script": script}
        )
        if response.status_code == 200:
            data = response.json()
            has_content = data.get('result', False)
            if has_content:
                print("✅ Page has content loaded")
            else:
                print("⚠️ Page may not be fully loaded")
        else:
            print(f"⚠️ Could not check page state: {response.status_code}")
    except Exception as e:
        print(f"⚠️ Error checking page state: {e}")

def extract_hackathon_urls():
    """Extract hackathon URLs from the current page"""
    
    # Check session
    print("🔍 Checking session...")
    try:
        status = requests.get(f"{API}/session/unstop/status").json()
        print(f"📊 Session status: {status.get('connected', False)}")
        if not status.get('connected', False):
            print("⚠️ Session not connected. Starting new session...")
            requests.post(
                f"{API}/session/unstop/start",
                json={"url": "https://unstop.com/hackathons?oppstatus=open"}
            )
            print(f"⏳ Waiting {WAIT_TIME}s for initial page load...")
            time.sleep(WAIT_TIME)
    except Exception as e:
        print(f"❌ Error checking session: {e}")
        print("Starting new session...")
        try:
            requests.post(
                f"{API}/session/unstop/start",
                json={"url": "https://unstop.com/hackathons?oppstatus=open"}
            )
            print(f"⏳ Waiting {WAIT_TIME}s for initial page load...")
            time.sleep(WAIT_TIME)
        except:
            print("❌ Failed to start session")
            return []
    
    # Execute JavaScript to extract hackathon URLs
    script = """
    function extractHackathonUrls() {
        const urls = new Set();
        const patterns = [
            /\\/hackathons\\//,
            /\\/hackathon\\//,
            /\\/hack\\//,
            /hackathon/i,
            /oppstatus=open/,
            /oppstatus=closed/,
            /oppstatus=upcoming/
        ];
        
        // Get all links
        const allLinks = document.querySelectorAll('a[href]');
        console.log('Found ' + allLinks.length + ' total links');
        
        allLinks.forEach(a => {
            const href = a.href;
            const text = a.textContent.trim();
            
            // Check if it's a hackathon link
            const isHackathon = patterns.some(pattern => 
                pattern.test(href) || pattern.test(text)
            );
            
            if (isHackathon && href.includes('unstop.com')) {
                urls.add(href);
            }
        });
        
        // Also check for hackathon cards that might not have links
        const cards = document.querySelectorAll('.hackathon-card, .event-card, .card, [class*="hackathon"], [class*="event"]');
        console.log('Found ' + cards.length + ' hackathon cards');
        
        cards.forEach(card => {
            const link = card.querySelector('a');
            if (link && link.href && link.href.includes('unstop.com')) {
                urls.add(link.href);
            }
        });
        
        return Array.from(urls);
    }
    
    return extractHackathonUrls();
    """
    
    print("⏳ Extracting hackathon URLs...")
    try:
        response = requests.post(
            f"{API}/session/unstop/execute",
            json={"script": script}
        )
        
        if response.status_code == 200:
            data = response.json()
            urls = data.get('result', [])
            return urls
        else:
            print(f"❌ Error: {response.status_code} - {response.text}")
            return []
    except Exception as e:
        print(f"❌ Error executing script: {e}")
        return []

def navigate_to_page(url):
    """Navigate to a specific page and wait"""
    print(f"📄 Navigating to: {url}")
    try:
        response = requests.post(
            f"{API}/session/unstop/navigate",
            json={"url": url}
        )
        if response.status_code == 200:
            print(f"⏳ Waiting {WAIT_TIME}s for page to load...")
            time.sleep(WAIT_TIME)
            return True
        else:
            print(f"❌ Failed to navigate: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Error navigating: {e}")
        return False

def main():
    print("\n" + "=" * 60)
    print("🔍 UNSTOP HACKATHON URL EXTRACTOR")
    print(f"⏳ Using wait time: {WAIT_TIME}s")
    print("=" * 60)
    
    # Pages to extract from
    pages = [
        "https://unstop.com/hackathons?oppstatus=open",
        "https://unstop.com/hackathons?oppstatus=closed",
        "https://unstop.com/hackathons?oppstatus=upcoming"
    ]
    
    all_urls = []
    
    for page_url in pages:
        print(f"\n📄 Processing: {page_url}")
        
        # Navigate to page
        if not navigate_to_page(page_url):
            print(f"⚠️ Skipping {page_url}")
            continue
        
        # Extract URLs
        urls = extract_hackathon_urls()
        
        if urls:
            print(f"✅ Found {len(urls)} hackathon URLs")
            all_urls.extend(urls)
            
            # Show sample
            print(f"  Sample URLs:")
            for url in urls[:3]:
                print(f"    • {url}")
        else:
            print("⚠️ No hackathon URLs found")
            
        # Wait between pages
        if page_url != pages[-1]:
            print(f"⏳ Waiting {WAIT_TIME}s before next page...")
            time.sleep(WAIT_TIME)
    
    # Deduplicate URLs
    all_urls = list(dict.fromkeys(all_urls))
    
    if all_urls:
        print(f"\n📊 Total unique hackathon URLs found: {len(all_urls)}")
        
        # Save to file
        with open('quick_hackathon_urls.txt', 'w', encoding='utf-8') as f:
            f.write('\n'.join(all_urls))
        
        print("💾 Saved to: quick_hackathon_urls.txt")
        
        # Count by status
        open_count = sum(1 for u in all_urls if 'oppstatus=open' in u)
        closed_count = sum(1 for u in all_urls if 'oppstatus=closed' in u)
        upcoming_count = sum(1 for u in all_urls if 'oppstatus=upcoming' in u)
        
        print(f"\n📊 Summary by status:")
        print(f"   Open: {open_count}")
        print(f"   Closed: {closed_count}")
        print(f"   Upcoming: {upcoming_count}")
        
        # Show all URLs
        print(f"\n📋 All URLs:")
        for i, url in enumerate(all_urls, 1):
            print(f"  {i}. {url}")
    else:
        print("\n❌ No hackathon URLs found")
        print("   Possible reasons:")
        print("   1. Page might need more time to load")
        print("   2. Page might require scrolling")
        print("   3. Page structure might have changed")
        print("   4. Need to handle dynamic content differently")
        
        print("\n💡 Try:")
        print("   - Increase WAIT_TIME to 20-30 seconds")
        print("   - Check if you're on the correct page")
        print("   - Try extracting all links first")

if __name__ == "__main__":
    main()
