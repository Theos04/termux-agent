#!/usr/bin/env python3
"""
Naukri Job Applier v2 - Fixed form handling with better field detection
"""

import json
import time
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from dynamic_cdp_7 import EnhancedChromeCDP
except ImportError:
    print("❌ Could not import from dynamic_cdp_7.py")
    sys.exit(1)

class NaukriJobApplier:
    def __init__(self, port=9260):
        self.port = port
        self.chrome = None
        self.tab_index = 0
        
    def connect(self):
        print(f"🔌 Connecting to Chrome on port {self.port}...")
        self.chrome = EnhancedChromeCDP(port=self.port, session_dir=".")
        
        tabs = self.chrome.get_tabs()
        if not tabs:
            print(f"❌ No tabs found. Make sure Chrome is running with:")
            print(f"   chromium-browser --remote-debugging-port={self.port}")
            return False
        
        # Find Naukri tab
        naukri_tab = None
        for i, tab in enumerate(tabs):
            if 'naukri.com' in tab.get('url', ''):
                naukri_tab = i
                break
        
        self.tab_index = naukri_tab if naukri_tab is not None else 0
        print(f"✅ Using tab: {tabs[self.tab_index].get('title', 'Unknown')}")
        
        ws_url = self.chrome.get_websocket_url(self.tab_index)
        return ws_url is not None
    
    def get_dom_analysis(self):
        """Get detailed DOM analysis with full field metadata"""
        print("   📄 Getting DOM analysis...")
        
        js_script = """
        (function() {
            const result = {
                apply_buttons: [],
                forms: [],
                input_fields: [],
                submit_candidates: [],
                modals: [],
                application_status: null,
                page_title: document.title || ''
            };
            
            // Check if already applied
            const body = document.body?.innerText || '';
            if (body.includes('Already Applied') || 
                body.includes('You have already applied') ||
                body.includes('Applied Successfully')) {
                result.application_status = 'already_applied';
                return result;
            }
            
            // Helper to get element visibility
            function isVisible(el) {
                if (!el) return false;
                const rect = el.getBoundingClientRect();
                const style = window.getComputedStyle(el);
                return rect.width > 0 && rect.height > 0 &&
                       style.display !== 'none' &&
                       style.visibility !== 'hidden' &&
                       style.opacity !== '0';
            }
            
            // Helper to get label text
            function getLabel(el) {
                // Check for aria-label
                if (el.hasAttribute('aria-label')) {
                    return el.getAttribute('aria-label');
                }
                // Check for associated label
                if (el.id) {
                    const label = document.querySelector(`label[for="${el.id}"]`);
                    if (label) return label.textContent.trim();
                }
                // Check parent label
                const parentLabel = el.closest('label');
                if (parentLabel) return parentLabel.textContent.trim();
                // Check nearby text
                const parent = el.closest('div, fieldset, li');
                if (parent) {
                    const text = parent.textContent.trim();
                    const words = text.split(/\s+/).slice(0, 10).join(' ');
                    if (words.length > 5) return words;
                }
                return '';
            }
            
            // Find Apply buttons
            const allButtons = document.querySelectorAll('button, a, input[type="button"], input[type="submit"], [role="button"]');
            allButtons.forEach(el => {
                const text = (el.textContent || el.value || el.getAttribute('aria-label') || '').toLowerCase();
                const class_ = (el.className || '').toLowerCase();
                const id = (el.id || '').toLowerCase();
                const data_cy = (el.getAttribute('data-cy') || '').toLowerCase();
                
                const applyTerms = ['apply', 'submit application', 'apply now', 'job apply', 'apply for job'];
                const is_apply = applyTerms.some(term => text.includes(term) || class_.includes(term) || id.includes(term) || data_cy.includes(term));
                
                if (is_apply && isVisible(el)) {
                    result.apply_buttons.push({
                        tag: el.tagName.toLowerCase(),
                        text: (el.textContent || el.value || '').trim(),
                        id: el.id || '',
                        class: el.className || '',
                        data_cy: el.getAttribute('data-cy') || '',
                        data_apply_url: el.getAttribute('data-apply-url') || '',
                        visible: true
                    });
                }
            });
            
            // Find forms with all fields
            const forms = document.querySelectorAll('form');
            forms.forEach(form => {
                const form_data = {
                    id: form.id || '',
                    class: form.className || '',
                    action: form.action || '',
                    method: form.method || '',
                    fields: [],
                    has_visible_fields: false
                };
                
                // Get all interactive elements in form
                const inputs = form.querySelectorAll('input, select, textarea, [role="combobox"], [role="textbox"], [contenteditable="true"]');
                inputs.forEach(input => {
                    const type = input.type || input.tagName.toLowerCase() || 'text';
                    const is_hidden = type === 'hidden' || !isVisible(input);
                    
                    // Skip hidden but collect them for logging
                    const field = {
                        type: type,
                        name: input.name || '',
                        id: input.id || '',
                        class: input.className || '',
                        placeholder: input.placeholder || '',
                        value: input.value || '',
                        required: input.required || false,
                        visible: isVisible(input),
                        hidden: is_hidden,
                        aria_label: input.getAttribute('aria-label') || '',
                        autocomplete: input.getAttribute('autocomplete') || '',
                        role: input.getAttribute('role') || '',
                        label: getLabel(input),
                        tag: input.tagName.toLowerCase()
                    };
                    
                    // Try to determine field purpose from all metadata
                    const metadata = [
                        field.name,
                        field.id,
                        field.placeholder,
                        field.aria_label,
                        field.label,
                        field.autocomplete
                    ].filter(Boolean).join(' ').toLowerCase();
                    
                    field.metadata = metadata;
                    
                    form_data.fields.push(field);
                    if (field.visible) {
                        form_data.has_visible_fields = true;
                        result.input_fields.push(field);
                    }
                });
                
                // Find submit buttons in form
                const submitBtns = form.querySelectorAll('button, input[type="submit"], [role="button"]');
                submitBtns.forEach(btn => {
                    const text = (btn.textContent || btn.value || btn.getAttribute('aria-label') || '').toLowerCase();
                    const is_submit = text.includes('submit') || text.includes('apply') || 
                                    text.includes('continue') || text.includes('next') ||
                                    text.includes('send') || btn.type === 'submit';
                    
                    if (is_submit && isVisible(btn)) {
                        const submit_info = {
                            tag: btn.tagName.toLowerCase(),
                            text: (btn.textContent || btn.value || '').trim(),
                            id: btn.id || '',
                            class: btn.className || '',
                            type: btn.getAttribute('type') || '',
                            visible: true
                        };
                        form_data.submit_button = submit_info;
                        result.submit_candidates.push(submit_info);
                    }
                });
                
                result.forms.push(form_data);
            });
            
            // If no forms found, check for standalone submit buttons
            if (result.forms.length === 0) {
                const standaloneButtons = document.querySelectorAll('button, input[type="submit"], [role="button"]');
                standaloneButtons.forEach(btn => {
                    const text = (btn.textContent || btn.value || btn.getAttribute('aria-label') || '').toLowerCase();
                    const is_submit = text.includes('submit') || text.includes('apply') || 
                                    text.includes('continue') || text.includes('next') ||
                                    text.includes('send');
                    if (is_submit && isVisible(btn)) {
                        result.submit_candidates.push({
                            tag: btn.tagName.toLowerCase(),
                            text: (btn.textContent || btn.value || '').trim(),
                            id: btn.id || '',
                            class: btn.className || '',
                            type: btn.getAttribute('type') || '',
                            visible: true
                        });
                    }
                });
            }
            
            // Find modals
            const modals = document.querySelectorAll('[class*="modal"], [class*="dialog"], [role="dialog"], [class*="popup"]');
            modals.forEach(modal => {
                if (isVisible(modal)) {
                    result.modals.push({
                        id: modal.id || '',
                        class: modal.className || '',
                        visible: true
                    });
                }
            });
            
            return result;
        })();
        """
        
        analysis = self.chrome.evaluate_script(js_script, self.tab_index)
        if analysis:
            print(f"   ✅ DOM analysis complete")
            print(f"      Apply buttons: {len(analysis.get('apply_buttons', []))}")
            print(f"      Forms: {len(analysis.get('forms', []))}")
            print(f"      Input fields: {len(analysis.get('input_fields', []))}")
            print(f"      Submit candidates: {len(analysis.get('submit_candidates', []))}")
            print(f"      Modals: {len(analysis.get('modals', []))}")
            
            # Print field details for debugging
            if analysis.get('input_fields'):
                print(f"\n   📋 INPUT FIELDS FOUND:")
                for i, field in enumerate(analysis['input_fields'][:5], 1):
                    print(f"      [{i}] type={field.get('type', 'unknown')!r}")
                    print(f"          name={field.get('name', '')!r}")
                    print(f"          id={field.get('id', '')!r}")
                    print(f"          placeholder={field.get('placeholder', '')!r}")
                    print(f"          aria_label={field.get('aria_label', '')!r}")
                    print(f"          label={field.get('label', '')!r}")
                    print(f"          required={field.get('required', False)}")
                    print(f"          visible={field.get('visible', False)}")
            
            if analysis.get('submit_candidates'):
                print(f"\n   📋 SUBMIT CANDIDATES:")
                for i, btn in enumerate(analysis['submit_candidates'][:3], 1):
                    print(f"      [{i}] {btn.get('tag', 'unknown')}: {btn.get('text', '')[:50]}")
            
            if analysis.get('application_status') == 'already_applied':
                print("   ⏭️ Already applied to this job")
            
            return analysis
        return None
    
    def click_apply_button(self, analysis):
        """Click apply button with multiple strategies"""
        apply_buttons = analysis.get('apply_buttons', [])
        
        # Try each apply button
        for btn in apply_buttons:
            if not btn.get('visible', False):
                continue
                
            selector = None
            if btn.get('id'):
                selector = f"#{btn['id']}"
            elif btn.get('data_cy'):
                selector = f"[data-cy='{btn['data_cy']}']"
            elif btn.get('class'):
                selector = f".{btn['class'].split()[0]}"
            
            if selector:
                print(f"   🖱️ Clicking apply button: {btn.get('text', '')[:30]}")
                js_script = f"""
                (function() {{
                    const el = document.querySelector("{selector}");
                    if (el) {{
                        el.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                        setTimeout(() => {{
                            // Try different click methods
                            try {{ el.click(); }} catch(e) {{}}
                            try {{
                                const event = new MouseEvent('click', {{
                                    view: window, bubbles: true, cancelable: true
                                }});
                                el.dispatchEvent(event);
                            }} catch(e) {{}}
                        }}, 300);
                        return {{ success: true }};
                    }}
                    return {{ success: false }};
                }})()
                """
                result = self.chrome.evaluate_script(js_script, self.tab_index)
                if result and result.get('success'):
                    print("   ✅ Clicked apply button")
                    return True
        
        # Fallback: find by text
        js_script = """
        (function() {
            const buttons = document.querySelectorAll('button, a, input[type="button"], input[type="submit"], [role="button"]');
            const applyTerms = ['apply', 'submit application', 'apply now'];
            for (let el of buttons) {
                const text = (el.textContent || el.value || el.getAttribute('aria-label') || '').toLowerCase();
                if (applyTerms.some(term => text.includes(term)) && el.offsetParent !== null) {
                    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    setTimeout(() => {
                        try { el.click(); } catch(e) {}
                        try {
                            const event = new MouseEvent('click', {
                                view: window, bubbles: true, cancelable: true
                            });
                            el.dispatchEvent(event);
                        } catch(e) {}
                    }, 300);
                    return { success: true, text: text };
                }
            }
            return { success: false };
        })()
        """
        result = self.chrome.evaluate_script(js_script, self.tab_index)
        if result and result.get('success'):
            print(f"   ✅ Clicked apply button (fallback)")
            return True
        
        print("   ⚠️ Could not find apply button")
        return False
    
    def fill_form_fields(self, analysis):
        """Fill form fields with smart field detection"""
        input_fields = analysis.get('input_fields', [])
        if not input_fields:
            print("   ⚠️ No input fields found")
            return False
        
        # Profile data with common variations
        profile = {
            'name': 'John Doe',
            'full_name': 'John Doe',
            'email': 'john.doe@example.com',
            'phone': '9876543210',
            'mobile': '9876543210',
            'phone_number': '9876543210',
            'experience': '5',
            'total_experience': '5',
            'current_ctc': '2000000',
            'expected_ctc': '2500000',
            'notice_period': '30',
            'location': 'Pune',
            'current_location': 'Pune',
            'preferred_location': 'Pune',
            'salary_expectation': '2500000',
            'current_company': 'ABC Corp',
            'current_designation': 'Senior Engineer',
            'skills': 'Python, Machine Learning, AI',
            'summary': 'Experienced professional with 5+ years in AI/ML',
            'website': 'https://example.com',
            'linkedin': 'https://linkedin.com/in/johndoe',
            'portfolio': 'https://example.com/portfolio'
        }
        
        # Keywords to field mapping
        field_keywords = {
            'name': ['name', 'full name', 'full_name', 'candidate name', 'applicant name'],
            'email': ['email', 'e-mail', 'mail'],
            'phone': ['phone', 'mobile', 'contact', 'telephone', 'phone number', 'mobile number'],
            'experience': ['experience', 'exp', 'years', 'work exp', 'total experience'],
            'current_ctc': ['current ctc', 'ctc', 'current salary', 'current package'],
            'expected_ctc': ['expected ctc', 'expected salary', 'expected package', 'salary expectation'],
            'notice_period': ['notice period', 'notice', 'joining', 'availability'],
            'location': ['location', 'city', 'current location', 'preferred location'],
            'current_company': ['current company', 'company name', 'organisation'],
            'current_designation': ['designation', 'title', 'current role', 'job title'],
            'skills': ['skills', 'technical skills', 'key skills', 'skill set'],
            'summary': ['summary', 'about', 'description', 'profile summary']
        }
        
        filled_count = 0
        print(f"   📝 Filling {len(input_fields)} fields...")
        
        for field in input_fields:
            if not field.get('visible', False):
                continue
            
            # Skip file uploads - can't automate
            if field.get('type') == 'file':
                print(f"      ⚠️ File input - manual upload needed")
                continue
            
            # Skip hidden fields
            if field.get('hidden', False):
                continue
            
            # Determine field purpose
            metadata = field.get('metadata', '').lower()
            field_name = field.get('name', '').lower()
            field_placeholder = field.get('placeholder', '').lower()
            field_label = field.get('label', '').lower()
            field_aria = field.get('aria_label', '').lower()
            
            # Combine all text for matching
            all_text = f"{metadata} {field_name} {field_placeholder} {field_label} {field_aria}"
            
            # Find matching field
            matched_key = None
            for key, keywords in field_keywords.items():
                if any(kw in all_text for kw in keywords):
                    matched_key = key
                    break
            
            # If no match, try autocomplete
            if not matched_key and field.get('autocomplete'):
                autocomplete = field['autocomplete'].lower()
                for key in field_keywords.keys():
                    if key in autocomplete:
                        matched_key = key
                        break
            
            # Build selector
            selector = None
            if field.get('id'):
                selector = f"#{field['id']}"
            elif field.get('name'):
                selector = f"[name='{field['name']}']"
            elif field.get('class'):
                selector = f".{field['class'].split()[0]}"
            
            if not selector:
                continue
            
            # Get value based on field type
            value = None
            field_type = field.get('type', '')
            
            if field_type in ['checkbox', 'radio']:
                # For checkbox/radio, we want to check/select
                if matched_key or field.get('required', False):
                    js_script = f"""
                    (function() {{
                        const el = document.querySelector("{selector}");
                        if (el) {{
                            el.checked = true;
                            el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                            return {{ success: true }};
                        }}
                        return {{ success: false }};
                    }})()
                    """
                    result = self.chrome.evaluate_script(js_script, self.tab_index)
                    if result and result.get('success'):
                        filled_count += 1
                        print(f"      ✅ Checked: {field.get('name', 'unknown')}")
                continue
                
            elif field_type in ['select-one', 'select-multiple']:
                # For selects, try to match value or select first option
                if matched_key and profile.get(matched_key):
                    value = profile[matched_key]
                elif matched_key:
                    # Try to select first option
                    value = None
                
                if value or field.get('required', False):
                    js_script = f"""
                    (function() {{
                        const el = document.querySelector("{selector}");
                        if (el) {{
                            // Try to match value
                            const options = el.options;
                            let matched = false;
                            for (let opt of options) {{
                                if (opt.text.toLowerCase().includes("{value.lower() if value else ''}")) {{
                                    el.value = opt.value;
                                    matched = true;
                                    break;
                                }}
                            }}
                            // If no match, select first non-empty option
                            if (!matched && options.length > 0) {{
                                for (let opt of options) {{
                                    if (opt.value && opt.value !== '') {{
                                        el.value = opt.value;
                                        matched = true;
                                        break;
                                    }}
                                }}
                            }}
                            if (matched) {{
                                el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                                return {{ success: true }};
                            }}
                            return {{ success: false }};
                        }}
                        return {{ success: false }};
                    }})()
                    """
                    result = self.chrome.evaluate_script(js_script, self.tab_index)
                    if result and result.get('success'):
                        filled_count += 1
                        print(f"      ✅ Selected: {field.get('name', 'unknown')}")
                continue
            
            # For text/textarea inputs
            if matched_key and profile.get(matched_key):
                value = profile[matched_key]
            elif 'years' in all_text or 'experience' in all_text:
                value = '5'
            elif 'email' in all_text:
                value = 'john.doe@example.com'
            elif 'phone' in all_text or 'mobile' in all_text:
                value = '9876543210'
            elif 'name' in all_text:
                value = 'John Doe'
            elif 'company' in all_text:
                value = 'ABC Corp'
            elif 'role' in all_text or 'designation' in all_text:
                value = 'Senior Engineer'
            elif 'skills' in all_text:
                value = 'Python, Machine Learning, AI'
            
            if not value:
                print(f"      ⚠️ Unknown field: {field.get('name', 'unknown')}")
                continue
            
            # Fill the field
            js_script = f"""
            (function() {{
                const el = document.querySelector("{selector}");
                if (el) {{
                    el.focus();
                    el.value = "{value}";
                    el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    // For React, also trigger focus/blur
                    el.dispatchEvent(new Event('focus', {{ bubbles: true }}));
                    el.dispatchEvent(new Event('blur', {{ bubbles: true }}));
                    return {{ success: true, value: "{value}" }};
                }}
                return {{ success: false }};
            }})()
            """
            result = self.chrome.evaluate_script(js_script, self.tab_index)
            if result and result.get('success'):
                filled_count += 1
                print(f"      ✅ Filled: {field.get('name', 'unknown')} = {value}")
        
        print(f"   ✅ Filled {filled_count} fields")
        return filled_count > 0
    
    def submit_form(self, analysis):
        """Submit the form with smart submit button detection"""
        submit_candidates = analysis.get('submit_candidates', [])
        
        # Try candidates in order
        for btn in submit_candidates:
            if not btn.get('visible', False):
                continue
            
            selector = None
            if btn.get('id'):
                selector = f"#{btn['id']}"
            elif btn.get('class'):
                selector = f".{btn['class'].split()[0]}"
            
            if selector:
                print(f"   🖱️ Clicking submit: {btn.get('text', '')[:30]}")
                js_script = f"""
                (function() {{
                    const el = document.querySelector("{selector}");
                    if (el) {{
                        el.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                        setTimeout(() => {{
                            try {{ el.click(); }} catch(e) {{}}
                            try {{
                                const event = new MouseEvent('click', {{
                                    view: window, bubbles: true, cancelable: true
                                }});
                                el.dispatchEvent(event);
                            }} catch(e) {{}}
                        }}, 300);
                        return {{ success: true }};
                    }}
                    return {{ success: false }};
                }})()
                """
                result = self.chrome.evaluate_script(js_script, self.tab_index)
                if result and result.get('success'):
                    print("   ✅ Form submitted!")
                    return True
        
        # Fallback: find any submit-like button
        js_script = """
        (function() {
            const buttons = document.querySelectorAll('button, input[type="submit"], [role="button"]');
            const submitTerms = ['submit', 'apply', 'continue', 'next', 'send', 'finish', 'save'];
            for (let el of buttons) {
                const text = (el.textContent || el.value || el.getAttribute('aria-label') || '').toLowerCase();
                if (submitTerms.some(term => text.includes(term)) && el.offsetParent !== null) {
                    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    setTimeout(() => {
                        try { el.click(); } catch(e) {}
                        try {
                            const event = new MouseEvent('click', {
                                view: window, bubbles: true, cancelable: true
                            });
                            el.dispatchEvent(event);
                        } catch(e) {}
                    }, 300);
                    return { success: true, text: text };
                }
            }
            return { success: false };
        })()
        """
        result = self.chrome.evaluate_script(js_script, self.tab_index)
        if result and result.get('success'):
            print(f"   ✅ Form submitted (fallback)")
            return True
        
        print("   ⚠️ Could not find submit button")
        return False
    
    def wait_for_form(self, timeout=10):
        """Wait for form to appear after clicking apply"""
        print("   ⏳ Waiting for form to load...")
        start = time.time()
        while time.time() - start < timeout:
            analysis = self.get_dom_analysis()
            if analysis:
                forms = analysis.get('forms', [])
                if forms and any(f.get('has_visible_fields', False) for f in forms):
                    print("   ✅ Form detected")
                    return analysis
                if analysis.get('modals'):
                    print("   ✅ Modal detected")
                    return analysis
            time.sleep(1)
        print("   ⚠️ Form not detected within timeout")
        return self.get_dom_analysis()
    
    def apply_to_job(self, job):
        """Apply to a single job with improved flow"""
        title = job.get('title', 'Unknown')
        company = job.get('companyName', 'Unknown')
        job_id = job.get('jobId', '')
        
        print(f"\n📤 Applying to: {title} - {company}")
        print(f"   Job ID: {job_id}")
        
        # Get URL
        url = job.get('applyRedirectUrl') or job.get('companyApplyUrl')
        if not url and job.get('jdURL'):
            url = f"https://www.naukri.com{job['jdURL']}"
        
        if not url:
            print("   ⚠️ No URL found")
            return False
        
        # Navigate
        print(f"   🚀 Navigating to job page...")
        ws_url = self.chrome.get_websocket_url(self.tab_index)
        if not ws_url:
            print("   ❌ Failed to get WebSocket URL")
            return False
        
        try:
            import websocket
            ws = websocket.create_connection(ws_url, timeout=30)
            nav_cmd = json.dumps({
                "id": 1,
                "method": "Page.navigate",
                "params": {"url": url}
            })
            ws.send(nav_cmd)
            time.sleep(4)
            ws.close()
        except Exception as e:
            print(f"   ❌ Navigation error: {e}")
            return False
        
        # Get initial DOM analysis
        analysis = self.get_dom_analysis()
        if not analysis:
            print("   ❌ Failed to analyze DOM")
            return False
        
        # Check if already applied
        if analysis.get('application_status') == 'already_applied':
            print("   ⏭️ Already applied to this job")
            return True
        
        # Click apply button
        if not self.click_apply_button(analysis):
            print("   ⚠️ Could not click apply button")
            return False
        
        # Wait for form/modal to appear
        time.sleep(2)
        analysis = self.wait_for_form(timeout=8)
        if not analysis:
            print("   ⚠️ No form detected after click")
            return False
        
        # Fill form fields
        if analysis.get('input_fields'):
            self.fill_form_fields(analysis)
        
        # Try to submit
        if self.submit_form(analysis):
            print("   ✅ Application submitted!")
            time.sleep(2)
            
            # Verify submission
            final_analysis = self.get_dom_analysis()
            if final_analysis and final_analysis.get('application_status') == 'already_applied':
                print("   ✅ Application confirmed!")
            return True
        else:
            print("   ⚠️ Could not submit - manual intervention needed")
            return False
    
    def run(self, jobs_file, max_jobs=5):
        """Main execution"""
        print("="*80)
        print("🚀 NAUKRI JOB APPLIER v2")
        print("="*80)
        
        if not self.connect():
            return
        
        try:
            with open(jobs_file, 'r') as f:
                data = json.load(f)
                jobs = data.get('jobDetails', [])[:max_jobs]
                print(f"📁 Loaded {len(jobs)} jobs from {jobs_file}")
        except Exception as e:
            print(f"❌ Error loading jobs: {e}")
            return
        
        print("\n⚠️  The script will analyze and fill forms")
        print("⚠️  Watch the Chrome tab for interactions")
        print("⚠️  Press Ctrl+C to stop\n")
        
        applied = 0
        for i, job in enumerate(jobs, 1):
            print(f"\n[{i}/{len(jobs)}] Processing...")
            
            try:
                if self.apply_to_job(job):
                    applied += 1
            except Exception as e:
                print(f"   ❌ Error: {e}")
            
            if i < len(jobs):
                print("\n⏳ Waiting 3 seconds...")
                time.sleep(3)
        
        print("\n" + "="*80)
        print(f"📊 Summary: Applied to {applied} out of {len(jobs)} jobs")
        print("="*80)

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Naukri Job Applier v2')
    parser.add_argument('jobs_file', nargs='?', default='recommended_jobs_20260810_233033.json',
                       help='Jobs JSON file path')
    parser.add_argument('--max', type=int, default=5,
                       help='Maximum number of jobs to apply to')
    parser.add_argument('--port', type=int, default=9260,
                       help='Chrome debug port (default: 9260)')
    args = parser.parse_args()
    
    applier = NaukriJobApplier(port=args.port)
    applier.run(args.jobs_file, args.max)

if __name__ == "__main__":
    main()
