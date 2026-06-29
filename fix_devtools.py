#!/usr/bin/env python3
"""
DevTools Connection Fix - Diagnostic and Repair Tool
"""

import json
import time
import requests
import socket
import subprocess
import sys
import os

def check_port(port):
    """Check if a port is open"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex(('127.0.0.1', port))
        sock.close()
        return result == 0
    except:
        return False

def check_devtools(port):
    """Check if DevTools is responding"""
    try:
        response = requests.get(f"http://127.0.0.1:{port}/json/version", timeout=5)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ DevTools responding on port {port}")
            print(f"   Browser: {data.get('Browser', 'Unknown')}")
            print(f"   Protocol: {data.get('Protocol-Version', 'Unknown')}")
            return True
        return False
    except Exception as e:
        print(f"❌ DevTools not responding: {e}")
        return False

def get_tabs(port):
    """Get list of tabs"""
    try:
        response = requests.get(f"http://127.0.0.1:{port}/json", timeout=5)
        if response.status_code == 200:
            tabs = response.json()
            return [t for t in tabs if t.get('type') == 'page']
        return []
    except Exception as e:
        print(f"❌ Failed to get tabs: {e}")
        return []

def fix_chrome_command(port, url):
    """Generate the correct Chrome command"""
    profile_dir = os.path.expanduser(f"~/chrome-sessions/fix-test")
    cmd = [
        "chromium-browser",
        f"--remote-debugging-port={port}",
        "--remote-allow-origins=*",
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-blink-features=AutomationControlled",
        "--disable-extensions",
        "--disable-gpu",
        "--window-size=1366,768",
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-dev-shm-usage",
        "--disable-in-process-stack-traces",
        "--disable-logging",
        "--log-level=3",
        "--disable-breakpad",
        "--disable-crash-reporter",
        "--disable-component-update",
        "--disable-background-networking",
        "--disable-sync",
        "--disable-default-apps",
        "--disable-translate",
        "--disable-dbus",
        "--disable-notifications",
        "--disable-prompt-on-repost",
        "--disable-hang-monitor",
        "--disable-client-side-phishing-detection",
        "--disable-component-extensions-with-background-pages",
        "--disable-field-trial-config",
        "--disable-background-timer-throttling",
        "--disable-renderer-backgrounding",
        "--disable-backgrounding-occluded-windows",
        f"--disable-features=IsolateOrigins,site-per-process,BlockInsecurePrivateNetworkRequests,TranslateUI,AudioServiceOutOfProcess,PasswordImport,PrivacySandboxSettings4,PrivacySandboxAdsAPIsOverride,EnableMsrPpqTesting,EnableMsrPpqTrial,EnableMsrPpq,VizDisplayCompositor",
        url
    ]
    return cmd

def main():
    port = 9236  # Your upwork port
    url = "https://www.upwork.com/"
    
    print("🔍 Chrome DevTools Diagnostic Tool")
    print("=" * 50)
    
    # Step 1: Check if port is open
    print(f"\n1. Checking if port {port} is open...")
    if check_port(port):
        print(f"✅ Port {port} is open")
    else:
        print(f"❌ Port {port} is not open")
        print("   Chrome may not be running or remote debugging is disabled")
        print("   Try starting Chrome manually with the correct flags")
        return
    
    # Step 2: Check DevTools
    print(f"\n2. Checking DevTools on port {port}...")
    if check_devtools(port):
        print("✅ DevTools is responding")
        
        # Step 3: Get tabs
        print("\n3. Getting tabs...")
        tabs = get_tabs(port)
        if tabs:
            print(f"✅ Found {len(tabs)} tabs:")
            for i, tab in enumerate(tabs, 1):
                print(f"   [{i}] {tab.get('title', 'Untitled')}")
                print(f"       URL: {tab.get('url', '')}")
                ws_url = tab.get('webSocketDebuggerUrl', '')
                if ws_url:
                    print(f"       WS: {ws_url}")
        else:
            print("⚠️ No tabs found")
    else:
        print("❌ DevTools is not responding")
        print("\n   Possible fixes:")
        print("   1. Chrome might be running with incorrect flags")
        print("   2. The port might be blocked")
        print("   3. Chrome might be in a broken state")
        
        print("\n   Attempting to fix by restarting Chrome...")
        
        # Kill existing Chrome
        subprocess.run(["pkill", "-f", "chromium-browser"], capture_output=True)
        time.sleep(2)
        
        # Start Chrome with correct flags
        cmd = fix_chrome_command(port, url)
        print(f"\n   Running: {' '.join(cmd[:5])} ...")
        
        # Start Chrome in background
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )
        
        # Wait for Chrome to start
        print("   Waiting for Chrome to start...")
        time.sleep(5)
        
        # Check again
        print("\n   Rechecking DevTools...")
        if check_devtools(port):
            print("✅ DevTools is now responding!")
            
            # Get tabs
            tabs = get_tabs(port)
            if tabs:
                print(f"✅ Found {len(tabs)} tabs")
                for i, tab in enumerate(tabs, 1):
                    print(f"   [{i}] {tab.get('title', 'Untitled')}")
                    ws_url = tab.get('webSocketDebuggerUrl', '')
                    if ws_url:
                        print(f"       WS: {ws_url}")
        else:
            print("❌ DevTools still not responding")
            print("\n   Manual steps to fix:")
            print("   1. Kill all Chrome processes: pkill -f chromium-browser")
            print("   2. Start Chrome manually with:")
            print(f"   chromium-browser --remote-debugging-port={port} --remote-allow-origins=* --no-sandbox --disable-web-security --user-data-dir=/tmp/chrome-test {url}")
            print("   3. Check if the port is open: netstat -tuln | grep {port}")
    
    # Step 4: Test WebSocket connection
    print("\n4. Testing WebSocket connection...")
    try:
        import websocket
        tabs = get_tabs(port)
        if tabs:
            ws_url = tabs[0].get('webSocketDebuggerUrl')
            if ws_url:
                print(f"   Connecting to: {ws_url}")
                try:
                    ws = websocket.create_connection(ws_url, timeout=5)
                    print("✅ WebSocket connection successful!")
                    
                    # Test Runtime.enable
                    ws.send(json.dumps({"id": 1, "method": "Runtime.enable"}))
                    response = ws.recv()
                    print(f"   Runtime.enable response: {response[:100]}...")
                    
                    ws.close()
                except Exception as e:
                    print(f"❌ WebSocket connection failed: {e}")
            else:
                print("❌ No WebSocket URL found")
        else:
            print("❌ No tabs to test WebSocket")
    except ImportError:
        print("⚠️ websocket module not installed, skipping WebSocket test")
        print("   Install with: pip install websocket-client")

if __name__ == "__main__":
    main()
