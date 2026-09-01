#!/usr/bin/env python3
"""
Quick stock price checker
Usage: python quick_stock.py [SYMBOL]
Example: python quick_stock.py RELIANCE
"""

import sys
from stock_price_fetcher import MoneyControlStockFetcher

def main():
    fetcher = MoneyControlStockFetcher()
    
    if len(sys.argv) > 1:
        symbol = sys.argv[1].upper()
        print(f"🔍 Fetching {symbol}...")
        
        # Search through all categories
        categories = ["Active Buying", "Strong Buying", "Short Covering", 
                     "Active Selling", "Strong Selling", "Profit Booking"]
        
        found = False
        for category in categories:
            data = fetcher.get_fno_trends(category=category, limit=50)
            if "data" in data:
                for stock in data["data"]:
                    if stock.get("name", "").upper() == symbol:
                        print(f"\n✅ {stock['name']}")
                        print(f"   Price: ₹{stock['price']}")
                        print(f"   Change: {stock['pricePerChange']}%")
                        print(f"   Trend: {stock['trend']}")
                        print(f"   Category: {stock['category']}")
                        print(f"   Open Interest: {stock['openInt']:,.0f}")
                        print(f"   Volume: {stock.get('volume', 0):,.0f}")
                        found = True
                        break
            if found:
                break
        
        if not found:
            print(f"❌ Stock '{symbol}' not found")
    else:
        print("Usage: python quick_stock.py SYMBOL")
        print("Example: python quick_stock.py RELIANCE")
        print("\n📊 Try these symbols:")
        print("  RELIANCE, TCS, INFY, HDFC, ICICI, SBIN, IRFC, VODAFONE")

if __name__ == "__main__":
    main()
