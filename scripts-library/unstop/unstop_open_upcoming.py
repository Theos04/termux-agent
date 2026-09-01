#!/data/data/com.termux/files/usr/bin/env python3
"""
Unstop Hackathon Extractor - Open & Upcoming Only
Extracts only open and upcoming hackathons with pagination
"""

import sys
import json
import time
import os
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
    print("   Trying local import...")
    try:
        sys.path.insert(0, '../..')
        from geturl import ChromePage
    except:
        print("❌ Failed to import ChromePage")
        sys.exit(1)

def extract_hackathon_urls_from_page(page):
    """Extract hackathon URLs from current page - only open and upcoming"""
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
                    // Determine status from URL
                    let status = 'unknown';
                    if (href.includes('oppstatus=open')) status = 'open';
                    else if (href.includes('oppstatus=closed')) status = 'closed';
                    else if (href.includes('oppstatus=upcoming')) status = 'upcoming';
                    
                    // ONLY include open and upcoming
                    if (status === 'open' || status === 'upcoming') {
                        const idMatch = href.match(/\\/hackathons\\/(\\d+)/);
                        const id = idMatch ? idMatch[1] : null;

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
            }
        });

        return results;
    })();
    """

    result = page.js(script)
    return result if result else []

def click_next_page(page):
    """Use pagination logic to go to next page"""
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

        const targetButton = pageButtons().find(btn =>
            parseInt(btn.textContent.trim(), 10) === target
        );

        if (targetButton) {
            targetButton.click();
            waitForPageChange(current);
            return { success: true, page: target, method: "direct" };
        }

        const nextGroup = document.querySelector(
            ".pagination-number .right-arrow.arrow:not(.disabled)"
        );

        if (!nextGroup) {
            return { success: false, reason: "last_page" };
        }

        nextGroup.click();

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
    seen_urls = set()

    print(f"📄 Starting pagination (max {max_pages} pages)...")

    while page_num <= max_pages:
        print(f"\n📄 Page {page_num}:")

        time.sleep(5)

        hackathons = extract_hackathon_urls_from_page(page)

        if hackathons:
            # Filter out duplicates
            new_hackathons = []
            for h in hackathons:
                if h['url'] not in seen_urls:
                    seen_urls.add(h['url'])
                    new_hackathons.append(h)
            
            print(f"   ✅ Found {len(new_hackathons)} new open/upcoming hackathon URLs")
            all_hackathons.extend(new_hackathons)

            for h in new_hackathons[:3]:
                print(f"      • [{h.get('status', 'unknown')}] {h.get('text', '')[:40]}")
        else:
            print(f"   ⚠️ No open/upcoming hackathon URLs found on page {page_num}")
            break

        if page_num < max_pages:
            print(f"   🔄 Going to next page...")
            result = click_next_page(page)

            if result and result.get('success'):
                page_num += 1
                print(f"   ✅ Navigated to page {page_num}")
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
    print("🏆 UNSTOP HACKATHON EXTRACTOR")
    print("   Open & Upcoming Hackathons Only")
    print("=" * 70)

    port = 9258
    page = ChromePage(port)

    if not page.connect():
        print("❌ Failed to connect to Chrome")
        return

    print(f"✅ Connected to Chrome")

    all_hackathons = []
    
    # Only process open and upcoming pages
    status_pages = {
        'open': 'https://unstop.com/hackathons?oppstatus=open',
        'upcoming': 'https://unstop.com/hackathons?oppstatus=upcoming'
    }

    for status_name, url in status_pages.items():
        print(f"\n" + "=" * 70)
        print(f"📊 Processing {status_name.upper()} hackathons")
        print(f"   URL: {url}")
        print("=" * 70)

        page.js(f"window.location.href = '{url}'")
        print("⏳ Waiting for page to load...")
        time.sleep(10)

        hackathons = get_all_hackathon_urls_with_pagination(page, max_pages=5)

        if hackathons:
            for h in hackathons:
                if h.get('status') == 'unknown':
                    h['status'] = status_name
            all_hackathons.extend(hackathons)
            print(f"\n✅ Found {len(hackathons)} {status_name} hackathon URLs")
        else:
            print(f"\n⚠️ No {status_name} hackathon URLs found")

        # Wait between processing different status pages
        if status_name != list(status_pages.keys())[-1]:
            print(f"\n⏳ Waiting 5s before processing next status...")
            time.sleep(5)

    # Deduplicate
    seen = set()
    unique_hackathons = []
    for h in all_hackathons:
        if h['url'] not in seen:
            seen.add(h['url'])
            unique_hackathons.append(h)

    print("\n" + "=" * 70)
    print(f"📊 SUMMARY: Total unique open/upcoming hackathon URLs: {len(unique_hackathons)}")
    print("=" * 70)

    if unique_hackathons:
        # Save all URLs
        all_urls = [h['url'] for h in unique_hackathons]
        with open('hackathon_urls_open_upcoming.txt', 'w', encoding='utf-8') as f:
            f.write('\n'.join(all_urls))
        print(f"✅ Saved {len(all_urls)} URLs to hackathon_urls_open_upcoming.txt")

        # Save by status
        for status in ['open', 'upcoming']:
            status_urls = [h['url'] for h in unique_hackathons if h.get('status') == status]
            if status_urls:
                filename = f'hackathon_urls_{status}.txt'
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(status_urls))
                print(f"✅ Saved {len(status_urls)} {status} URLs to {filename}")

        # Save JSON
        with open('hackathon_details_open_upcoming.json', 'w', encoding='utf-8') as f:
            json.dump({
                'timestamp': time.time(),
                'total': len(unique_hackathons),
                'hackathons': unique_hackathons
            }, f, indent=2)
        print(f"✅ Saved details to hackathon_details_open_upcoming.json")

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
