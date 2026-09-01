#!/usr/bin/env python3
"""
Manual token input helper
"""

import json
from pathlib import Path

def main():
    print("""
╔═══════════════════════════════════════════════╗
║    🔑 Manual Token Entry                     ║
║    Enter your Naukri authentication token    ║
╚═══════════════════════════════════════════════╝
    """)
    
    print("📋 How to get your token:")
    print("-" * 40)
    print("1. Open Naukri.com in Chrome")
    print("2. Press F12 to open Developer Tools")
    print("3. Go to 'Network' tab")
    print("4. Refresh the page (F5)")
    print("5. In the 'Filter' box, type: 'naukimg' or 'cloudgateway'")
    print("6. Click on any API request (they have a blue or purple icon)")
    print("7. Scroll down in the right panel to 'Request Headers'")
    print("8. Find: 'Authorization: Bearer <your_token>'")
    print("9. Copy the token (long string after 'Bearer ')")
    print("-" * 40)
    print()
    
    # Check if we have a token file
    if Path('naukri_token.txt').exists():
        with open('naukri_token.txt', 'r') as f:
            existing = f.read().strip()
        if existing:
            print(f"📂 Existing token found: {existing[:30]}...")
            use_existing = input("\nUse existing token? (y/n): ").lower()
            if use_existing == 'y':
                print("✅ Using existing token")
                return
            else:
                print("Enter new token:")
    
    token = input("\n🔑 Enter your token: ").strip()
    
    if not token:
        print("❌ Token is required!")
        return
        
    if len(token) < 20:
        print("⚠️ Token seems short. Please verify it's correct.")
        confirm = input("Continue anyway? (y/n): ").lower()
        if confirm != 'y':
            return
            
    # Save token
    with open('naukri_token.txt', 'w') as f:
        f.write(token)
        
    print("\n✅ Token saved to: naukri_token.txt")
    print(f"🔑 Token: {token[:30]}...")
    print("\n🚀 You can now run: ./run_job_bot.sh")

if __name__ == "__main__":
    main()
