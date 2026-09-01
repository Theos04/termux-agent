#!/data/data/com.termux/files/usr/bin/env python3
"""Debug script to check page content"""

import requests
import json
import time

API = "http://127.0.0.1:5000"

def get_page_info():
    """Get comprehensive page info"""
    
    # Get page status
    status = requests.get(f"{API}/session/unstop/status").json()
    print("📊 Session Status:")
    print(json.dumps(status, indent=2))
    
    # Get page title
    script = "return document.title"
    response = requests.post(f"{API}/session/unstop/execute", json={"script": script})
    if response.status_code == 200:
        print(f"\n📄 Page Title: {response.json().get('result', 'N/A')}")
    
    # Get page URL
    script = "return window.location.href"
    response = requests.post(f"{API}/session/unstop/execute", json={"script": script})
    if response.status_code == 200:
        print(f"📄 Page URL: {response.json().get('result', 'N/A')}")
    
    # Count elements
    script = """
    return {
        totalLinks: document.querySelectorAll('a').length,
        totalImages: document.querySelectorAll('img').length,
        totalDivs: document.querySelectorAll('div').length,
        totalButtons: document.querySelectorAll('button').length,
        bodyTextLength: document.body ? document.body.innerText.length : 0
    }
    """
    response = requests.post(f"{API}/session/unstop/execute", json={"script": script})
    if response.status_code == 200:
        data = response.json().get('result', {})
        print("\n📊 Page Statistics:")
        print(f"  Total Links: {data.get('totalLinks', 0)}")
        print(f"  Total Images: {data.get('totalImages', 0)}")
        print(f"  Total Divs: {data.get('totalDivs', 0)}")
        print(f"  Total Buttons: {data.get('totalButtons', 0)}")
        print(f"  Text Length: {data.get('bodyTextLength', 0)} chars")
    
    # Get all links (first 20)
    script = """
    return Array.from(document.querySelectorAll('a[href]')).slice(0, 20).map(a => ({
        href: a.href,
        text: a.textContent.trim().slice(0, 50),
        className: a.className
    }));
    """
    response = requests.post(f"{API}/session/unstop/execute", json={"script": script})
    if response.status_code == 200:
        links = response.json().get('result', [])
        print(f"\n🔗 First 20 Links:")
        for i, link in enumerate(links, 1):
            print(f"  {i}. {link.get('text', 'N/A')[:30]} → {link.get('href', 'N/A')[:60]}")

if __name__ == "__main__":
    print("=" * 60)
    print("🔍 DEBUG PAGE INFO")
    print("=" * 60)
    get_page_info()
