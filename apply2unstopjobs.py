import json
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Initialize the browser with CDP
options = webdriver.ChromeOptions()
options.add_argument("--remote-debugging-port=9247")
driver = webdriver.Chrome(options=options)

# Get the CDP connection
cdp = driver.execute_cdp_cmd("Target.getTargets", {})
cdp_ws = driver.w3c_handles[0]

# Enable CDP events
driver.execute_cdp_cmd("Page.enable", {})
driver.execute_cdp_cmd("DOM.enable", {})

def monitor_cdp_events():
    """Monitor CDP events for page changes"""
    print("🚀 Starting CDP event monitoring...")
    
    while True:
        try:
            # Get messages from CDP
            msg = driver.execute_cdp_cmd("Runtime.evaluate", {
                "expression": """
                    (() => {
                        // Check for any pending CDP messages
                        return window.__cdp_messages || [];
                    })()
                """
            })
            
            # Alternative: Use selenium's built-in CDP message handling
            # This is a simplified approach - you may need to implement proper WebSocket handling
            
            # For demonstration, we'll use a polling approach with CDP
            state = driver.execute_cdp_cmd("Runtime.evaluate", {
                "expression": """
                    (() => ({
                        url: location.href,
                        readyState: document.readyState,
                        title: document.title,
                        applyText: document.getElementById("un-register-btn")?.innerText || null,
                        applyClass: document.getElementById("un-register-btn")?.className || null,
                        modal: !!document.querySelector(".modal, .cdk-overlay-container"),
                        bodyLength: document.body?.innerHTML?.length || 0,
                        timestamp: new Date().toISOString()
                    }))()
                """
            })
            
            current_state = state["result"]["result"]["value"]
            
            # Store and check for changes
            if not hasattr(monitor_cdp_events, "last_state"):
                monitor_cdp_events.last_state = current_state
                print(f"\n📊 Initial state:")
                print(json.dumps(current_state, indent=2))
                continue
            
            if current_state != monitor_cdp_events.last_state:
                print("\n" + "="*80)
                print(f"🔄 Change detected at {current_state['timestamp']}")
                print("="*80)
                
                # Show what changed
                old = monitor_cdp_events.last_state
                changes = []
                
                if current_state['url'] != old['url']:
                    changes.append(f"🌐 URL: {old['url']} → {current_state['url']}")
                
                if current_state['readyState'] != old['readyState']:
                    changes.append(f"📄 Ready State: {old['readyState']} → {current_state['readyState']}")
                
                if current_state['applyText'] != old['applyText']:
                    changes.append(f"🔄 Apply Button: {old['applyText']} → {current_state['applyText']}")
                
                if current_state['modal'] != old['modal']:
                    changes.append(f"💬 Modal: {old['modal']} → {current_state['modal']}")
                
                if current_state['title'] != old['title']:
                    changes.append(f"📌 Title: {old['title']} → {current_state['title']}")
                
                for change in changes:
                    print(f"  • {change}")
                
                print("\n📊 Current state:")
                print(json.dumps(current_state, indent=2))
                
                monitor_cdp_events.last_state = current_state
            
            time.sleep(0.5)  # Poll every 500ms
            
        except Exception as e:
            print(f"❌ Error in monitoring: {e}")
            time.sleep(1)

def check_for_login_redirect():
    """Check if we've been redirected to login"""
    current_url = driver.current_url
    if "login" in current_url.lower():
        print("\n🔐 Redirected to login page!")
        return True
    return False

def handle_application_process():
    """Main application flow"""
    try:
        # Start monitoring in background
        print("🔍 Starting CDP monitoring...")
        
        # Navigate to the page
        driver.get("https://unstop.com/jobs/analyst-mobile-front-ads-operations-nby2iE9?utm_medium=email&utm_source=newsletter")
        
        # Wait for page to load
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        
        print("📄 Page loaded, looking for apply button...")
        
        # Try multiple selectors for the apply button
        selectors = [
            "#un-register-btn",
            ".register_btn",
            "button:contains('Apply')",
            "[class*='register']",
            "[class*='apply']"
        ]
        
        apply_button = None
        for selector in selectors:
            try:
                if selector.startswith("button:"):
                    apply_button = WebDriverWait(driver, 3).until(
                        EC.element_to_be_clickable((By.XPATH, f"//button[contains(text(), 'Apply')]"))
                    )
                else:
                    apply_button = WebDriverWait(driver, 3).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                    )
                if apply_button:
                    print(f"✅ Found apply button with selector: {selector}")
                    break
            except:
                continue
        
        if not apply_button:
            print("❌ Could not find apply button")
            return
        
        # Get initial state
        initial_state = driver.execute_cdp_cmd("Runtime.evaluate", {
            "expression": """
                (() => ({
                    url: location.href,
                    applyText: document.getElementById("un-register-btn")?.innerText || null,
                    buttonClass: document.getElementById("un-register-btn")?.className || null
                }))()
            """
        })
        print(f"\n📋 Initial state: {initial_state['result']['result']['value']}")
        
        # Click the apply button
        print("\n🖱️ Clicking apply button...")
        apply_button.click()
        
        # Monitor for changes
        print("\n⏳ Monitoring for changes...")
        start_time = time.time()
        timeout = 30
        
        while time.time() - start_time < timeout:
            # Check for login redirect
            if check_for_login_redirect():
                print("🔐 Login required!")
                break
            
            # Check current state
            current_state = driver.execute_cdp_cmd("Runtime.evaluate", {
                "expression": """
                    (() => ({
                        url: location.href,
                        readyState: document.readyState,
                        applyText: document.getElementById("un-register-btn")?.innerText || null,
                        modal: !!document.querySelector(".modal, .cdk-overlay-container"),
                        loginForm: !!document.querySelector("form, .login-form, .signin-form")
                    }))()
                """
            })
            
            state_data = current_state['result']['result']['value']
            
            # Check if application was successful
            if state_data['applyText'] and "applied" in state_data['applyText'].lower():
                print(f"\n✅ Successfully applied! Button text: {state_data['applyText']}")
                break
            
            # Check if modal appeared
            if state_data['modal']:
                print("\n💬 Modal appeared - checking for application form...")
                
                # Try to find and fill application form if needed
                try:
                    # Look for submit button in modal
                    submit_btn = driver.find_element(By.CSS_SELECTOR, 
                        ".modal .submit-btn, .modal button[type='submit']")
                    if submit_btn:
                        print("📝 Submitting application form...")
                        submit_btn.click()
                except:
                    print("ℹ️ No form submission needed")
            
            time.sleep(1)
            
        print("\n🏁 Monitoring complete!")
        
    except Exception as e:
        print(f"❌ Error in application process: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    try:
        handle_application_process()
        
        # Keep monitoring for additional changes
        print("\n" + "="*80)
        print("📡 Starting continuous monitoring (press Ctrl+C to stop)")
        print("="*80)
        
        # Start continuous monitoring
        monitor_cdp_events()
        
    except KeyboardInterrupt:
        print("\n\n⏹️ Monitoring stopped by user")
    finally:
        driver.quit()
        print("👋 Browser closed")
