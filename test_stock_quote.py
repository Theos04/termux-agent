#!/usr/bin/env python3
"""
Test direct stock quote endpoints
"""

import requests
import json

def test_endpoints():
    endpoints = [
        "https://priceapi.moneycontrol.com/technicalCompanyData/oiData/getFnoOiTrends?category=Active%20Buying&expiry=ALL&type=ALL&deviceType=W&limit=10",
        "https://www.moneycontrol.com/techmvc/mc_widgets/trending_stocks?limit=5&classic=true",
        "https://www.moneycontrol.com/mccode/common/indices_chart/indices_chart.php",
    ]
    
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
        "Accept": "application/json",
        "Referer": "https://www.moneycontrol.com/"
    }
    
    for url in endpoints:
        print(f"\n🔍 Testing: {url[:80]}...")
        try:
            response = requests.get(url, headers=headers, timeout=10)
            print(f"  Status: {response.status_code}")
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    print(f"  Response type: {type(data)}")
                    if isinstance(data, dict):
                        print(f"  Keys: {list(data.keys())[:5]}")
                        # Look for stock data
                        for key, value in data.items():
                            if isinstance(value, list) and len(value) > 0:
                                print(f"  {key}: {len(value)} items")
                                if len(value) > 0 and isinstance(value[0], dict):
                                    print(f"  Sample: {list(value[0].keys())[:5]}")
                                    if 'symbol' in value[0]:
                                        print(f"  Symbol: {value[0]['symbol']}")
                                    if 'price' in value[0]:
                                        print(f"  Price: {value[0]['price']}")
                    elif isinstance(data, list) and len(data) > 0:
                        print(f"  List with {len(data)} items")
                        if isinstance(data[0], dict):
                            print(f"  Sample keys: {list(data[0].keys())[:5]}")
                except json.JSONDecodeError:
                    print(f"  Response preview: {response.text[:200]}...")
        except Exception as e:
            print(f"  Error: {e}")

if __name__ == "__main__":
    test_endpoints()
