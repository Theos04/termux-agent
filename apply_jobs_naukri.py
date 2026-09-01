#!/usr/bin/env python3
"""
Naukri Job Applier using CDP - Fixed click functionality
"""

import json
import time
import sys
import requests
import websocket

class NaukriCDPApplier:
    def __init__(self, port=9260):
        self.port = port
        self.ws = None
        self.msg_id = 0
        
    def connect(self):
        """Connect to Chrome via CDP"""
        try:
            response = requests.get(f"http://localhost:{self.port}/json")
            tabs = response.json()
            
            page_tabs = [t for t in tabs if t.get('type') == 'page']
            if not page_tabs:
                print("❌ No page tabs found")
                return False
            
            # Try to find a Naukri tab first
            naukri_tab = None
            for tab in page_tabs:
                url = tab.get('url', '')
                if 'naukri.com' in url:
                    naukri_tab = tab
                    break
            
            tab = naukri_tab or page_tabs[0]
            ws_url = tab.get('webSocketDebuggerUrl')
            
            print(f"✅ Connected to: {tab.get('title', 'Unknown')[:50]}")
            self.ws = websocket.create_connection(ws_url, timeout=30)
            
            # Enable required domains
            self.send_command("DOM.enable")
            self.send_command("Runtime.enable")
            self.send_command("Page.enable")
            
            return True
            
        except Exception as e:
            print(f"❌ Connection error: {e}")
            return False
    
    def send_command(self, method, params=None):
        """Send CDP command and get response"""
        self.msg_id += 1
        msg = json.dumps({
            "id": self.msg_id,
            "method": method,
            "params": params or {}
        })
        self.ws.send(msg)
        
        # Wait for response
        timeout = 30
        start = time.time()
        while time.time() - start < timeout:
            try:
                response = self.ws.recv()
                data = json.loads(response)
                if data.get('id') == self.msg_id:
                    return data
            except:
                time.sleep(0.1)
        return None
    
    def navigate(self, url):
        """Navigate to URL"""
        print(f"   🚀 Navigating to: {url[:80]}...")
        result = self.send_command("Page.navigate", {"url": url})
        
        if result and 'result' in result:
            if result['result'].get('errorText'):
                print(f"   ❌ Error: {result['result']['errorText']}")
                return False
            
            # Wait for page to load
            time.sleep(4)
            return True
        return False
    
    def wait_for_page_load(self, timeout=15):
        """Wait for page to fully load"""
        print("   ⏳ Waiting for page to load...")
        start = time.time()
        while time.time() - start < timeout:
            try:
                result = self.send_command("Runtime.evaluate", {
                    "expression": "document.readyState"
                })
                if result and 'result' in result:
                    state = result['result'].get('result', {}).get('value', '')
                    if state == 'complete':
                        print("   ✅ Page loaded")
                        return True
            except:
                pass
            time.sleep(0.5)
        return False
    
    def click_apply_button_js(self):
        """Click apply button using JavaScript - more reliable"""
        js_code = """
        (function() {
            // Try multiple strategies to find and click the Apply button
            
            // Strategy 1: Find by class or ID
            const selectors = [
                '.apply-button',
                '#applyBtn',
                '[data-cy="apply-button"]',
                'button[data-apply-url]',
                '.applyBtn',
                'button.apply',
                'a.apply',
                '[class*="apply"]',
                '[class*="Apply"]'
            ];
            
            for (let selector of selectors) {
                try {
                    const el = document.querySelector(selector);
                    if (el) {
                        // Check if it's visible and clickable
                        const rect = el.getBoundingClientRect();
                        if (rect.width > 0 && rect.height > 0) {
                            el.scrollIntoView({ behavior: 'smooth', block: 'center' });
                            // Use both methods to ensure click
                            el.click();
                            // Also dispatch a click event
                            const event = new MouseEvent('click', {
                                view: window,
                                bubbles: true,
                                cancelable: true
                            });
                            el.dispatchEvent(event);
                            return { success: true, method: 'selector', selector: selector };
                        }
                    }
                } catch(e) {}
            }
            
            // Strategy 2: Find by text content
            const allElements = document.querySelectorAll('button, a, div[role="button"]');
            for (let el of allElements) {
                const text = el.textContent?.trim() || '';
                if (text.includes('Apply') || text.includes('Apply Now') || text === 'Apply') {
                    const rect = el.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0) {
                        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
                        el.click();
                        const event = new MouseEvent('click', {
                            view: window,
                            bubbles: true,
                            cancelable: true
                        });
                        el.dispatchEvent(event);
                        return { success: true, method: 'text', text: text };
                    }
                }
            }
            
            // Strategy 3: Find input with type submit
            const inputs = document.querySelectorAll('input[type="submit"]');
            for (let el of inputs) {
                const value = el.value || '';
                if (value.includes('Apply') || value.includes('Submit')) {
                    const rect = el.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0) {
                        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
                        el.click();
                        return { success: true, method: 'input', value: value };
                    }
                }
            }
            
            // Strategy 4: Look for any button with apply in data attributes
            const dataElements = document.querySelectorAll('[data-apply], [data-action="apply"]');
            for (let el of dataElements) {
                const rect = el.getBoundingClientRect();
                if (rect.width > 0 && rect.height > 0) {
                    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    el.click();
                    return { success: true, method: 'data-attribute' };
                }
            }
            
            return { success: false, message: 'No Apply button found' };
        })()
        """
        
        print("   🖱️ Clicking Apply button via JavaScript...")
        result = self.send_command("Runtime.evaluate", {"expression": js_code})
        
        if result and 'result' in result:
            value = result['result'].get('result', {}).get('value', {})
            if value.get('success'):
                print(f"   ✅ Clicked via {value.get('method', 'unknown')}")
                return True
            else:
                print(f"   ⚠️ {value.get('message', 'Failed to click')}")
                return False
        return False
    
    def check_if_applied(self):
        """Check if already applied"""
        js_code = """
        (function() {
            // Check for applied indicators
            const indicators = [
                '.applied',
                '.already-applied',
                '[class*="applied"]',
                '[class*="Applied"]',
                'button[disabled]'
            ];
            
            for (let selector of indicators) {
                const el = document.querySelector(selector);
                if (el) {
                    const text = el.textContent?.trim() || '';
                    if (text.includes('Applied') || text.includes('Already')) {
                        return true;
                    }
                }
            }
            
            // Check text content
            const body = document.body?.innerText || '';
            if (body.includes('Already Applied') || 
                body.includes('You have already applied') ||
                body.includes('Applied Successfully')) {
                return true;
            }
            
            return false;
        })()
        """
        result = self.send_command("Runtime.evaluate", {"expression": js_code})
        if result and 'result' in result:
            return result['result']['result'].get('value', False)
        return False
    
    def get_job_url(self, job):
        """Get the job URL from job data"""
        url = job.get('applyRedirectUrl') or job.get('companyApplyUrl')
        if not url and job.get('jdURL'):
            url = f"https://www.naukri.com{job['jdURL']}"
        return url
    
    def apply_to_job(self, job):
        """Apply to a single job"""
        title = job.get('title', 'Unknown')
        company = job.get('companyName', 'Unknown')
        job_id = job.get('jobId', '')
        
        print(f"\n📤 Applying to: {title} - {company}")
        print(f"   Job ID: {job_id}")
        
        # Get URL
        url = self.get_job_url(job)
        if not url:
            print("   ⚠️ No URL found")
            return False
        
        # Navigate to URL
        if not self.navigate(url):
            return False
        
        # Wait for page load
        self.wait_for_page_load()
        time.sleep(2)
        
        # Check if already applied
        if self.check_if_applied():
            print("   ⏭️ Already applied to this job")
            return True
        
        # Click apply button using JavaScript
        success = self.click_apply_button_js()
        
        if success:
            print("   ✅ Application submitted!")
            # Wait for any modal or next step
            time.sleep(2)
            
            # Check if there's a confirmation
            js_code = """
            (function() {
                // Check for success message or modal
                const body = document.body?.innerText || '';
                if (body.includes('Application submitted') || 
                    body.includes('Successfully Applied') ||
                    body.includes('Thank you for applying')) {
                    return { confirmed: true };
                }
                return { confirmed: false };
            })()
            """
            result = self.send_command("Runtime.evaluate", {"expression": js_code})
            if result and 'result' in result:
                confirmed = result['result'].get('result', {}).get('value', {}).get('confirmed', False)
                if confirmed:
                    print("   ✅ Application confirmed!")
            
            return True
        else:
            print("   ⚠️ Could not click Apply button - manual intervention needed")
            return False
    
    def run(self, jobs_file, max_jobs=5):
        """Main execution"""
        print("="*80)
        print("🚀 NAUKRI CDP APPLIER")
        print("="*80)
        
        # Connect to Chrome
        print("\n🔌 Connecting to Chrome...")
        if not self.connect():
            print("❌ Failed to connect. Make sure Chrome is running with --remote-debugging-port=9260")
            return
        
        # Load jobs
        try:
            with open(jobs_file, 'r') as f:
                data = json.load(f)
                jobs = data.get('jobDetails', [])[:max_jobs]
                print(f"📁 Loaded {len(jobs)} jobs from {jobs_file}")
        except Exception as e:
            print(f"❌ Error loading jobs: {e}")
            return
        
        print("\n⚠️  The script will try to apply automatically")
        print("⚠️  You may need to complete additional steps manually")
        print("⚠️  Press Ctrl+C to stop\n")
        
        applied = 0
        failed = 0
        for i, job in enumerate(jobs, 1):
            print(f"\n[{i}/{len(jobs)}] Processing...")
            
            try:
                if self.apply_to_job(job):
                    applied += 1
                else:
                    failed += 1
            except Exception as e:
                print(f"   ❌ Error: {e}")
                failed += 1
            
            if i < len(jobs):
                print("\n⏳ Waiting 3 seconds...")
                time.sleep(3)
        
        print("\n" + "="*80)
        print(f"📊 Summary: Applied to {applied} out of {len(jobs)} jobs")
        print(f"   Failed: {failed}")
        print("="*80)
        
        if self.ws:
            self.ws.close()

def main():
    import sys
    # Parse arguments properly
    args = sys.argv[1:]
    jobs_file = "recommended_jobs_20260810_233033.json"
    max_jobs = 5
    
    for i, arg in enumerate(args):
        if arg == '--file' and i + 1 < len(args):
            jobs_file = args[i + 1]
        elif arg == '--max' and i + 1 < len(args):
            try:
                max_jobs = int(args[i + 1])
            except:
                pass
        elif arg.startswith('--file='):
            jobs_file = arg.split('=')[1]
        elif arg.startswith('--max='):
            try:
                max_jobs = int(arg.split('=')[1])
            except:
                pass
        elif not arg.startswith('--'):
            jobs_file = arg
    
    applier = NaukriCDPApplier()
    applier.run(jobs_file, max_jobs)

if __name__ == "__main__":
    main()
