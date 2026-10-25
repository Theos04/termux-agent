#!/data/data/com.termux/files/usr/bin/env python3
"""
Unstop Hackathon Extractor with Pagination
Uses pagination_on.js to navigate through all pages
"""

import sys
import json
import time
import os
import subprocess
from typing import List, Dict

# Import ChromePage from geturl.py
try:
    import importlib.util
    spec = importlib.util.spec_from_file_location("geturl", "../../geturl.py")
    geturl = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(geturl)
    ChromePage = geturl.ChromePage
except Exception as e:
    print(f"❌ Could not import from geturl.py: {e}")
    sys.exit(1)

def load_pagination_script():
    """Load pagination_on.js script content"""
    script_path = "pagination_on.js"
    
    # Try multiple locations
    possible_paths = [
        "pagination_on.js",
        "scripts-library/unstop/pagination_on.js",
        "../scripts-library/unstop/pagination_on.js"
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            with open(path, 'r') as f:
                content = f.read()
                # Extract the pagination function
                return content
    return None

def extract_hackathon_urls_from_page(page):
    """Extract hackathon URLs from current page"""
    script = """
    (function() {
        const patterns = [
            /\\/hackathons\\//,
            /\\/hackathon\\//,
            /hackathon/i
        ];
        
        const results = [];
        const allLinks = document.querySelectorAll('a[href]');
        
        allLinks.forEach(a => {
            const href = a.href;
            const text = a.textContent.trim();
            
            if (href && href.includes('unstop.com')) {
                const isHackathon = patterns.some(pattern => 
                    pattern.test(href) || pattern.test(text)
                );
                
                if (isHackathon) {
                    const idMatch = href.match(/\\/hackathons\\/(\\d+)/);
                    const id = idMatch ? idMatch[1] : null;
                    
                    let status = 'unknown';
                    if (href.includes('oppstatus=open')) status = 'open';
                    else if (href.includes('oppstatus=closed')) status = 'closed';
                    else if (href.includes('oppstatus=upcoming')) status = 'upcoming';
                    
                    if (!results.some(r => r.url === href)) {
                        results.push({
                            url: href,
                            text: text.slice(0, 100),
                            id: id,
                            status: status
                        });
                    }
                }
            }
        });
        
        return results;
    })();
    """
    
    result = page.js(script)
    return result if result else []

def click_next_page(page):
    """Use pagination_on.js logic to go to next page"""
    
    # JavaScript to find and click next page
    script = """
    (function() {
        const delay = ms => new Promise(r => setTimeout(r, ms));
        
        function currentPage() {
            const active = document.querySelector(
                ".pagination-number li.active .number"
            );
            return active ? parseInt(active.textContent.trim(), 10) : null;
        }
        
        function pageButtons() {
            return [...document.querySelectorAll(".pagination-number .number")];
        }
        
        async function waitForPageChange(oldPage) {
            for (let i = 0; i < 50; i++) {
                await delay(200);
                const now = currentPage();
                if (now !== oldPage) return true;
            }
            return false;
        }
        
        const current = currentPage();
        if (current == null) {
            return { success: false, reason: "no_page_indicator" };
        }
        
        const target = current + 1;
        
        // Look for page n+1
        const targetButton = pageButtons().find(btn =>
            parseInt(btn.textContent.trim(), 10) === target
        );
        
        if (targetButton) {
            targetButton.click();
            waitForPageChange(current);
            return { success: true, page: target, method: "direct" };
        }
        
        // Try advancing pagination
        const nextGroup = document.querySelector(
            ".pagination-number .right-arrow.arrow:not(.disabled)"
        );
        
        if (!nextGroup) {
            return { success: false, reason: "last_page" };
        }
        
        nextGroup.click();
        
        // Wait for pagination to update
        return new Promise(resolve => {
            setTimeout(() => {
                const retry = pageButtons().find(btn =>
                    parseInt(btn.textContent.trim(), 10) === target
                );
                
                if (!retry) {
                    resolve({ success: false, reason: "page_not_found" });
                    return;
                }
                
                retry.click();
                waitForPageChange(current);
                resolve({ success: true, page: target, method: "group_advance" });
            }, 1500);
        });
    })();
    """
    
    result = page.js(script, await_promise=True)
    return result if result else {"success": False, "reason": "unknown"}

def get_all_hackathon_urls_with_pagination(page, max_pages=10):
    """Get all hackathon URLs by navigating through pagination"""
    
    all_hackathons = []
    page_num = 1
    
    print(f"📄 Starting pagination (max {max_pages} pages)...")
    
    while page_num <= max_pages:
        print(f"\n📄 Page {page_num}:")
        
        # Wait for page to load
        time.sleep(5)
        
        # Extract URLs from current page
        hackathons = extract_hackathon_urls_from_page(page)
        
        if hackathons:
            print(f"   ✅ Found {len(hackathons)} hackathon URLs")
            all_hackathons.extend(hackathons)
            
            # Show sample
            for h in hackathons[:3]:
                print(f"      • {h.get('text', '')[:40]}")
        else:
            print(f"   ⚠️ No hackathon URLs found on page {page_num}")
            break
        
        # Try to go to next page
        if page_num < max_pages:
            print(f"   🔄 Going to next page...")
            result = click_next_page(page)
            
            if result and result.get('success'):
                page_num += 1
                print(f"   ✅ Navigated to page {page_num}")
                # Wait for page load
                time.sleep(5)
            else:
                reason = result.get('reason', 'unknown') if result else 'unknown'
                print(f"   ⏹️ No more pages: {reason}")
                break
        else:
            break
    
    return all_hackathons

def main():
    print("\n" + "=" * 70)
    print("🏆 UNSTOP HACKATHON EXTRACTOR WITH PAGINATION")
    print("   Uses pagination_on.js logic")
    print("=" * 70)
    
    # Check if pagination script exists
    pagination_script = load_pagination_script()
    if pagination_script:
        print("✅ Found pagination_on.js")
    else:
        print("⚠️ pagination_on.js not found, using built-in pagination")
    
    # Connect to Chrome
    port = 9258
    page = ChromePage(port)
    
    if not page.connect():
        print("❌ Failed to connect to Chrome")
        return
    
    print(f"✅ Connected to Chrome")
    
    # Status pages to process
    status_pages = {
        'open': 'https://unstop.com/hackathons?oppstatus=open',
        'closed': 'https://unstop.com/hackathons?oppstatus=closed',
        'upcoming': 'https://unstop.com/hackathons?oppstatus=upcoming'
    }
    
    all_hackathons = []
    results_by_status = {}
    
    for status_name, url in status_pages.items():
        print(f"\n" + "=" * 70)
        print(f"📊 Processing {status_name.upper()} hackathons (with pagination)")
        print(f"   URL: {url}")
        print("=" * 70)
        
        # Navigate to page
        page.js(f"window.location.href = '{url}'")
        print("⏳ Waiting for page to load...")
        time.sleep(10)
        
        # Get all URLs with pagination
        hackathons = get_all_hackathon_urls_with_pagination(page, max_pages=5)
        
        if hackathons:
            # Add status
            for h in hackathons:
                if h.get('status') == 'unknown':
                    h['status'] = status_name
            
            results_by_status[status_name] = hackathons
            all_hackathons.extend(hackathons)
            print(f"\n✅ Found {len(hackathons)} total URLs for {status_name}")
        else:
            print(f"\n⚠️ No URLs found for {status_name}")
    
    # Deduplicate
    seen = set()
    unique_hackathons = []
    for h in all_hackathons:
        if h['url'] not in seen:
            seen.add(h['url'])
            unique_hackathons.append(h)
    
    print("\n" + "=" * 70)
    print(f"📊 SUMMARY: Total unique hackathon URLs: {len(unique_hackathons)}")
    print("=" * 70)
    
    if unique_hackathons:
        # Save all URLs
        all_urls = [h['url'] for h in unique_hackathons]
        with open('hackathon_urls_all.txt', 'w', encoding='utf-8') as f:
            f.write('\n'.join(all_urls))
        print(f"✅ Saved {len(all_urls)} URLs to hackathon_urls_all.txt")
        
        # Save by status
        for status in ['open', 'closed', 'upcoming']:
            status_urls = [h['url'] for h in unique_hackathons if h.get('status') == status]
            if status_urls:
                filename = f'hackathon_urls_{status}.txt'
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(status_urls))
                print(f"✅ Saved {len(status_urls)} {status} URLs to {filename}")
        
        # Save JSON
        with open('hackathon_details_pagination.json', 'w', encoding='utf-8') as f:
            json.dump({
                'timestamp': time.time(),
                'total': len(unique_hackathons),
                'hackathons': unique_hackathons,
                'by_status': {k: len(v) for k, v in results_by_status.items()}
            }, f, indent=2)
        print(f"✅ Saved details to hackathon_details_pagination.json")
        
        # Count by status
        status_counts = {}
        for h in unique_hackathons:
            status = h.get('status', 'unknown')
            status_counts[status] = status_counts.get(status, 0) + 1
        
        print(f"\n📊 Status breakdown:")
        for status, count in sorted(status_counts.items()):
            print(f"   {status}: {count}")
        
        # Show sample URLs
        print(f"\n📋 Sample URLs (first 10):")
        for i, h in enumerate(unique_hackathons[:10], 1):
            status = h.get('status', 'unknown')
            print(f"  {i:2d}. [{status:7}] {h.get('url', '')}")
        if len(unique_hackathons) > 10:
            print(f"  ... and {len(unique_hackathons) - 10} more")
    
    page.close()
    print("\n✅ Done!")

if __name__ == "__main__":
    main()
