#!/usr/bin/env python3
"""
Dedicated WhatsApp Chrome Launcher with Isolated Profile.

Runs on port 9223 by default (completely isolated from CDP_PORT 9222 used by Maps scraping).
Preserves WhatsApp Web login state and IndexedDB storage.
"""

import os
import shutil
import subprocess
import sys
import time

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
PROFILE_DIR = os.environ.get(
    "WHATSAPP_PROFILE_DIR",
    os.path.join(ROOT_DIR, "data", "chrome-whatsapp-profile"),
)
DEBUG_PORT = int(os.environ.get("WHATSAPP_CDP_PORT", "9223"))


def find_chrome() -> str:
    paths = [
        "google-chrome",
        "google-chrome-stable",
        "chromium-browser",
        "chromium",
        "/usr/bin/google-chrome",
        "/usr/bin/chromium-browser",
        "/data/data/com.termux/files/usr/bin/chromium-browser",
    ]
    for p in paths:
        if shutil.which(p):
            return shutil.which(p)
    raise RuntimeError("Chrome executable not found. Please install google-chrome or chromium-browser")


def main():
    print("=" * 64)
    print("📱 WhatsApp Web Chrome Launcher (Isolated Agent Session)")
    print("=" * 64)

    os.makedirs(PROFILE_DIR, exist_ok=True)
    chrome_bin = find_chrome()

    print(f"✓ Binary      : {chrome_bin}")
    print(f"📁 Profile Dir : {PROFILE_DIR}")
    print(f"🔌 Debug Port  : {DEBUG_PORT} (Maps agent runs on 9222)")
    print(f"🌐 Target URL  : https://web.whatsapp.com")
    print()

    cmd = [
        chrome_bin,
        f"--remote-debugging-port={DEBUG_PORT}",
        "--remote-allow-origins=*",
        f"--user-data-dir={PROFILE_DIR}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-blink-features=AutomationControlled",
        "--window-size=1280,800",
        "https://web.whatsapp.com",
    ]

    print("🚀 Starting Chrome for WhatsApp Web...")
    proc = subprocess.Popen(cmd)
    print(f"✓ Chrome PID: {proc.pid}")
    print("Scan QR code once in the browser window. Session will persist automatically.")
    print("Press Ctrl+C to terminate browser.")

    try:
        proc.wait()
    except KeyboardInterrupt:
        print("\nStopping WhatsApp Chrome...")
        proc.terminate()


if __name__ == "__main__":
    main()
