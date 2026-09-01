#!/data/data/com.termux/files/usr/bin/env python3
"""
Complete Unstop Hackathon URL Extractor
Extracts hackathon URLs from all status pages
"""

import sys
import json
import time
import os

# Import ChromePage from geturl.py
try:
    import importlib.util
    spec = importlib.util.spec_from_file_location("geturl", "geturl.py")
    geturl = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(geturl)
    ChromePage = geturl.ChromePage
except Exception as e:
    print(f"❌ Could not import from geturl.py: {e}")
    sys.exit(1)

def extract_hackathon_urls(page, status_filter=None):
    """Extract hackathon URLs from the current page"""
    
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
                    
                    // Skip duplicates
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
    if not result:
        return []
    
    # Filter by status if specified
    if status_filter:
        return [h for h in result if h.get('status') == status_filter]
    
    return result

def main():
    print("\n" + "=" * 60)
    print("🏆 UNSTOP HACKATHON URL EXTRACTOR")
    print("   Extracts hackathon URLs from all status pages")
    print("=" * 60)
    
    # Connect to Chrome
    port = 9258
    page = ChromePage(port)
    
    if not page.connect():
        print("❌ Failed to connect to Chrome")
        print("   Make sure Chrome is running with remote debugging")
        return
    
    print(f"✅ Connected to Chrome")
    print(f"   Current page: {page.page_url}")
    
    # Status pages to check
    status_pages = {
        'open': 'https://unstop.com/hackathons?oppstatus=open',
        'closed': 'https://unstop.com/hackathons?oppstatus=closed',
        'upcoming': 'https://unstop.com/hackathons?oppstatus=upcoming',
        'all': 'https://unstop.com/hackathons'
    }
    
    all_hackathons = []
    results_by_status = {}
    
    for status_name, url in status_pages.items():
        print(f"\n📄 Processing: {status_name.upper()} hackathons")
        print(f"   URL: {url}")
        
        # Navigate to the page
        page.js(f"window.location.href = '{url}'")
        
        # Wait for page to load
        print("   ⏳ Waiting for page to load...")
        time.sleep(15)
        
        # Wait for content
        retries = 3
        for i in range(retries):
            link_count = page.js("return document.querySelectorAll('a[href]').length")
            if link_count and link_count > 0:
                print(f"   ✅ Found {link_count} links on page")
                break
            print(f"   ⏳ Waiting for content... (attempt {i+1}/{retries})")
            time.sleep(5)
        
        # Extract hackathon URLs
        hackathons = extract_hackathon_urls(page)
        
        if hackathons:
            print(f"   ✅ Found {len(hackathons)} hackathon URLs")
            results_by_status[status_name] = hackathons
            all_hackathons.extend(hackathons)
            
            # Show sample
            for h in hackathons[:3]:
                print(f"      • {h.get('text', '')[:40]} → {h.get('url', '')}")
        else:
            print(f"   ⚠️ No hackathon URLs found on {status_name} page")
            
            # Debug: show all links
            all_links = page.get_all_links()
            print(f"   Debug: {len(all_links)} total links on page")
            
            # Manual search for hackathon links
            hackathon_links = []
            for link in all_links:
                href = link.get('href', '')
                if 'hackathon' in href.lower():
                    hackathon_links.append(href)
            
            if hackathon_links:
                print(f"   Found {len(hackathon_links)} hackathon links manually!")
                for link in hackathon_links[:3]:
                    print(f"      • {link}")
    
    # Close connection
    page.close()
    
    # Save results
    if all_hackathons:
        # Deduplicate by URL
        seen = set()
        unique_hackathons = []
        for h in all_hackathons:
            if h['url'] not in seen:
                seen.add(h['url'])
                unique_hackathons.append(h)
        
        print(f"\n" + "=" * 60)
        print(f"📊 SUMMARY")
        print(f"   Total unique hackathon URLs: {len(unique_hackathons)}")
        print("=" * 60)
        
        # Save all URLs
        all_urls = [h['url'] for h in unique_hackathons]
        with open('hackathon_urls_all.txt', 'w', encoding='utf-8') as f:
            f.write('\n'.join(all_urls))
        print(f"💾 Saved {len(all_urls)} URLs to hackathon_urls_all.txt")
        
        # Save by status
        for status_name, hackathons in results_by_status.items():
            if hackathons:
                filename = f'hackathon_urls_{status_name}.txt'
                urls = [h['url'] for h in hackathons]
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(urls))
                print(f"💾 Saved {len(urls)} {status_name} URLs to {filename}")
        
        # Save detailed JSON
        with open('hackathon_details_all.json', 'w', encoding='utf-8') as f:
            json.dump({
                'timestamp': time.time(),
                'total': len(unique_hackathons),
                'hackathons': unique_hackathons
            }, f, indent=2)
        print(f"💾 Saved details to hackathon_details_all.json")
        
        # Count by status
        status_counts = {}
        for h in unique_hackathons:
            status = h.get('status', 'unknown')
            status_counts[status] = status_counts.get(status, 0) + 1
        
        print(f"\n📊 Status breakdown:")
        for status, count in sorted(status_counts.items()):
            print(f"   {status}: {count}")
        
        # Show all URLs
        print(f"\n📋 All hackathon URLs:")
        for i, url in enumerate(all_urls, 1):
            print(f"  {i:2d}. {url}")
        
        # Find hackathon IDs
        ids = [h['id'] for h in unique_hackathons if h['id']]
        if ids:
            print(f"\n📊 Hackathon IDs found: {len(ids)}")
            print(f"   Sample IDs: {', '.join(ids[:5])}")
    else:
        print("\n❌ No hackathon URLs found")
        print("\n💡 Suggestions:")
        print("   1. Make sure you're logged into Unstop")
        print("   2. Try increasing wait times")
        print("   3. Navigate to the page manually in Chrome first")
    
    print("\n✅ Done!")

if __name__ == "__main__":
    main()
