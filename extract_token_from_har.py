#!/usr/bin/env python3
"""
Extract authentication token from your HAR file
"""

import json
import re
from pathlib import Path

def extract_token_from_har(har_file: str) -> str:
    """Extract Bearer token from HAR file"""
    try:
        with open(har_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Handle different HAR structures
        entries = []
        if 'log' in data:
            entries = data['log'].get('entries', [])
        elif 'entries' in data:
            entries = data['entries']
        else:
            # Try to find entries anywhere
            for key in data:
                if isinstance(data[key], dict) and 'entries' in data[key]:
                    entries = data[key]['entries']
                    break
        
        print(f"📊 Found {len(entries)} entries to scan...")
        
        # Look through all requests
        for entry in entries:
            request = entry.get('request', {})
            headers = request.get('headers', [])
            url = request.get('url', '')
            
            # Skip if not naukri
            if 'naukri' not in url and 'naukimg' not in url:
                continue
                
            for header in headers:
                if header.get('name', '').lower() == 'authorization':
                    auth_value = header.get('value', '')
                    # Extract Bearer token
                    match = re.search(r'Bearer\s+([^\s]+)', auth_value)
                    if match:
                        token = match.group(1)
                        print(f"✅ Found token in: {url[:80]}...")
                        return token
                        
        # Try cookies as well
        for entry in entries:
            request = entry.get('request', {})
            headers = request.get('headers', [])
            url = request.get('url', '')
            
            if 'naukri' not in url and 'naukimg' not in url:
                continue
                
            for header in headers:
                if header.get('name', '').lower() == 'cookie':
                    cookies = header.get('value', '')
                    # Look for session or auth cookies
                    if 'session' in cookies or 'auth' in cookies:
                        print(f"🍪 Found authentication cookies in: {url[:80]}...")
                        # Extract session ID
                        match = re.search(r'session[_\w]*=([^;]+)', cookies)
                        if match:
                            return match.group(1)
                        
        return None
        
    except Exception as e:
        print(f"Error reading HAR file: {e}")
        import traceback
        traceback.print_exc()
        return None

def get_token_from_har_entries(har_file: str) -> list:
    """Get all possible tokens from HAR entries"""
    tokens = []
    try:
        with open(har_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        entries = data.get('log', {}).get('entries', [])
        
        for entry in entries:
            request = entry.get('request', {})
            headers = request.get('headers', [])
            
            for header in headers:
                if header.get('name', '').lower() == 'authorization':
                    auth_value = header.get('value', '')
                    if 'Bearer' in auth_value:
                        token = auth_value.replace('Bearer ', '').strip()
                        if token and len(token) > 20:
                            tokens.append(token)
    except:
        pass
    
    return list(set(tokens))  # Remove duplicates

def main():
    """Main function"""
    print("""
╔═══════════════════════════════════════════════╗
║    🔑 HAR Token Extractor                    ║
║    Extract authentication token from HAR     ║
╚═══════════════════════════════════════════════╝
    """)
    
    # Check for HAR files
    har_files = list(Path('.').glob('*.har'))
    
    if not har_files:
        print("❌ No HAR files found.")
        print("Please run: python quick_capture_har.py to capture traffic first.")
        return
        
    print("📂 Available HAR files:")
    for i, file in enumerate(har_files, 1):
        size = file.stat().st_size / 1024
        print(f"  {i}. {file.name} ({size:.1f} KB)")
        
    choice = input(f"\nSelect file (1-{len(har_files)}): ").strip()
    
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(har_files):
            har_file = har_files[idx]
            
            # Try to get tokens
            tokens = get_token_from_har_entries(str(har_file))
            
            if tokens:
                # Use the first token
                token = tokens[0]
                print(f"\n✅ Token extracted successfully!")
                print(f"🔑 Token: {token[:30]}...{token[-10:]}")
                print(f"📊 Found {len(tokens)} tokens total")
                
                # Save token
                with open('naukri_token.txt', 'w') as f:
                    f.write(token)
                print("\n💾 Token saved to: naukri_token.txt")
                print("\n📋 You can now run: ./run_job_bot.sh")
            else:
                print("❌ No Bearer token found in HAR file.")
                print("\n💡 Manual token extraction:")
                print("  1. Open Chrome Developer Tools (F12)")
                print("  2. Go to 'Network' tab")
                print("  3. Refresh Naukri.com page")
                print("  4. Find any API request (filter by 'naukri' or 'naukimg')")
                print("  5. Click on the request")
                print("  6. Under 'Request Headers', find 'Authorization: Bearer <token>'")
                print("  7. Copy the token (the part after 'Bearer ')")
                print("\n   Then run: echo 'your_token' > naukri_token.txt")
        else:
            print("Invalid selection.")
            
    except ValueError:
        print("Invalid input.")

if __name__ == "__main__":
    main()
