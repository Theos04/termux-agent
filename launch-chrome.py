#!/usr/bin/env python3
"""
Minimal Chrome Launcher with Persistent Profile
Just starts Chrome, you login manually, keep it running
"""

import os
import time
import subprocess
import shutil

# Configuration
PROFILE_DIR = os.path.expanduser("~/chrome-persistent-profile")
DEBUG_PORT = 9222

def find_chrome():
    """Find Chrome/Chromium executable"""
    paths = [
        "chromium-browser",
        "chromium",
        "google-chrome",
        "google-chrome-stable",
        "/usr/bin/chromium-browser",
        "/usr/bin/chromium",
        "/data/data/com.termux/files/usr/bin/chromium-browser",
    ]
    
    for path in paths:
        if shutil.which(path):
            return path
    raise RuntimeError("Chrome not found. Install chromium-browser")

def main():
    print("=" * 60)
    print("🔧 Chrome Persistent Launcher")
    print("=" * 60)
    
    # Create profile directory
    os.makedirs(PROFILE_DIR, exist_ok=True)
    
    chrome_path = find_chrome()
    print(f"✓ Browser: {chrome_path}")
    print(f"📁 Profile: {PROFILE_DIR}")
    print(f"🔌 Debug port: {DEBUG_PORT}")
    print()
    
    # Build command
    cmd = [
        chrome_path,
        f"--remote-debugging-port={DEBUG_PORT}",
        f"--user-data-dir={PROFILE_DIR}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-blink-features=AutomationControlled",
        "--disable-extensions",
        "--window-size=1366,768",
    ]
    
    print("🚀 Starting Chrome...")
    print()
    print("=" * 60)
    print("🔐 LOGIN INSTRUCTIONS")
    print("=" * 60)
    print()
    print("1. Chrome window should open")
    print("2. Navigate to: https://www.semanticscholar.org")
    print("3. LOG IN to your account")
    print("4. Keep Chrome running")
    print()
    print("📌 For VNC access (Termux):")
    print("   vncserver :1 -geometry 1366x768 -depth 24")
    print()
    print("=" * 60)
    print()
    
    # Launch Chrome
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True
    )
    
    print(f"✅ Chrome started (PID: {process.pid})")
    print()
    print("💡 Chrome will stay running in the background")
    print("   Press Ctrl+C to stop this script (Chrome will keep running)")
    print("   To stop Chrome: pkill chromium-browser")
    print()
    
    try:
        # Keep script running
        while True:
            time.sleep(10)
            # Check if process is still alive
            if process.poll() is not None:
                print("⚠️ Chrome process died")
                break
    except KeyboardInterrupt:
        print()
        print("👋 Script stopped")
        print(f"   Chrome is still running (PID: {process.pid})")
        print(f"   Connect via: http://127.0.0.1:{DEBUG_PORT}")
        print()
        print("   To stop Chrome:")
        print(f"   kill {process.pid}")
        print("   or: pkill chromium-browser")

if __name__ == "__main__":
    main()
