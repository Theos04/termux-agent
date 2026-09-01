#!/usr/bin/env python3
"""
Get fresh Naukri tokens using CDP capture
"""

from har2api.capture.cdp_capturer import CDPCapturer
import time
import json
import sys

def get_fresh_tokens(port=9260, capture_time=60):
    """Capture fresh tokens from Chrome"""
    
    print("="*80)
    print("🔄 GETTING FRESH NAUKRI TOKENS")
    print("="*80)
    
    # Initialize capturer
    capturer = CDPCapturer(port=port)
    
    # Connect to Chrome tabs
    print(f"\n📡 Connecting to Chrome on port {port}...")
    tabs = capturer.get_tabs()
    
    if not tabs:
        print("❌ No tabs found. Make sure Chrome is running with debugging enabled.")
        return None
    
    connected = False
    for tab in tabs:
        if tab.get('type') == 'page':
            print(f"   Connecting to tab: {tab.get('title', 'Unknown')[:50]}")
            if capturer.connect_to_tab(tab['id'], tab['webSocketDebuggerUrl']):
                connected = True
                break
    
    if not connected:
        print("❌ Failed to connect to any tab")
        return None
    
    # Start capture
    print("\n✅ Connected! Starting capture...")
    capturer.start_capture()
    
    print(f"\n⏳ Capturing for {capture_time} seconds...")
    print("   Make sure you're logged into Naukri.com")
    print("   Navigate around the site to generate API calls")
    
    # Wait with progress
    for i in range(capture_time):
        if i % 10 == 0:
            elapsed = i
            remaining = capture_time - i
            print(f"   ⏱️  {elapsed}s elapsed - {remaining}s remaining")
        time.sleep(1)
    
    # Stop capture
    print("\n🛑 Stopping capture...")
    entries = capturer.stop_capture()
    
    # Get tokens
    tokens = capturer.get_session_tokens()
    
    # Check if we got tokens
    if tokens.get('authorization'):
        print("\n✅ Fresh tokens captured!")
        print(f"   Bearer Token: {tokens['authorization'][:50]}...")
        print(f"   Cookies: {len(tokens.get('cookies', {}))}")
        
        # Save tokens to file
        with open('fresh_tokens.json', 'w') as f:
            json.dump(tokens, f, indent=2)
        print(f"\n💾 Tokens saved to: fresh_tokens.json")
        
        # Also export HAR for reference
        har_data = capturer.export_har('fresh_capture.har')
        print(f"📁 HAR exported to: fresh_capture.har")
        
        return tokens
    else:
        print("\n❌ No authorization token found!")
        print("   Make sure you're logged into Naukri.com")
        return None

if __name__ == "__main__":
    # Get fresh tokens with 60 second capture
    tokens = get_fresh_tokens(port=9260, capture_time=60)
    
    if tokens:
        print("\n" + "="*80)
        print("✅ SUCCESS! Use these tokens in the API client")
        print("="*80)
        print(f"\nBearer Token:\n{tokens['authorization']}\n")
        print(f"Cookies:\n{json.dumps(tokens['cookies'], indent=2)}")
