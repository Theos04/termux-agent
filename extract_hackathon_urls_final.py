#!/data/data/com.termux/files/usr/bin/env python3
"""
Extract hackathon URLs using geturl.py's ChromePage class with custom extraction
"""

import sys
import json
import time

# Import ChromePage from geturl.py
try:
    import importlib.util
    spec = importlib.util.spec_from_file_location("geturl", "geturl.py")
    geturl = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(geturl)
    ChromePage = geturl.ChromePage
    print("✅ Loaded ChromePage from geturl.py")
except Exception as e:
    print(f"❌ Could not import from geturl.py: {e}")
    sys.exit(1)

def extract_hackathon_urls(page):
    """Extract hackathon URLs using JavaScript in the page"""
    
    script = """
    (function() {
        const patterns = [
            /\\/hackathons\\//,
            /\\/hackathon\\//,
            /hackathon/i,
            /oppstatus=open/,
            /oppstatus=closed/,
            /oppstatus=upcoming/
        ];
        
        const results = [];
        const allLinks = document.querySelectorAll('a[href]');
        console.log('Total links found:', allLinks.length);
        
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
                    
                    results.push({
                        url: href,
                        text: text.slice(0, 100),
                        id: id,
                        status: status
                    });
                }
            }
        });
        
        return results;
    })();
    """
    
    return page.js(script) or []

def main():
    print("\n" + "=" * 60)
    print("🔍 EXTRACT HACKATHON URLs (FINAL)")
    print("   Using geturl.py's ChromePage class")
    print("=" * 60)
    
    # Use port 9258
    port = 9258
    page = ChromePage(port)
    
    if not page.connect():
        print("❌ Failed to connect to Chrome")
        print("   Make sure Chrome is running with remote debugging")
        return
    
    print(f"✅ Connected to: {page.page_title}")
    print(f"   URL: {page.page_url}")
    
    # Wait for dynamic content
    print("\n⏳ Waiting 15s for dynamic content to load...")
    time.sleep(15)
    
    # Get all links first
    print("\n🔍 Getting all links...")
    all_links = page.get_all_links()
    print(f"   Found {len(all_links)} total links")
    
    if all_links:
        print("\n📋 Sample links:")
        for link in all_links[:10]:
            print(f"   • {link.get('text', '')[:40]} → {link.get('href', '')[:80]}")
    
    # Extract hackathon URLs using custom method
    print("\n🔍 Extracting hackathon URLs...")
    hackathons = extract_hackathon_urls(page)
    
    if hackathons:
        print(f"✅ Found {len(hackathons)} hackathon URLs!")
        
        # Save to files
        urls = [h['url'] for h in hackathons]
        
        with open('hackathon_urls.txt', 'w', encoding='utf-8') as f:
            f.write('\n'.join(urls))
        print(f"💾 Saved {len(urls)} URLs to hackathon_urls.txt")
        
        with open('hackathon_details.json', 'w', encoding='utf-8') as f:
            json.dump(hackathons, f, indent=2)
        print("💾 Saved details to hackathon_details.json")
        
        # Show URLs
        print(f"\n📋 Hackathon URLs:")
        for i, h in enumerate(hackathons, 1):
            print(f"  {i}. {h.get('text', '')[:50]} → {h.get('url', '')}")
    else:
        print("❌ No hackathon URLs found")
        
        # Try to manually find hackathon links
        print("\n🔍 Manual search for hackathon links...")
        hackathon_links = []
        for link in all_links:
            href = link.get('href', '')
            if 'hackathon' in href.lower():
                hackathon_links.append(href)
        
        if hackathon_links:
            print(f"✅ Found {len(hackathon_links)} hackathon URLs manually!")
            for url in hackathon_links[:10]:
                print(f"  • {url}")
            
            with open('hackathon_urls_manual.txt', 'w', encoding='utf-8') as f:
                f.write('\n'.join(hackathon_links))
            print("\n💾 Saved to hackathon_urls_manual.txt")
    
    page.close()
    print("\n✅ Done!")

if __name__ == "__main__":
    main()
