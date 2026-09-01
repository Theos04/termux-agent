#!/usr/bin/env python3
"""
Top gainers and losers from MoneyControl
"""

from stock_price_fetcher import MoneyControlStockFetcher

def main():
    fetcher = MoneyControlStockFetcher()
    
    # Get all categories
    categories = {
        "Active Buying": "📈 Top Gainers",
        "Active Selling": "📉 Top Losers",
        "Strong Buying": "💪 Strong Buying",
        "Strong Selling": "🔻 Strong Selling",
    }
    
    print("🚀 Market Movers")
    print("="*60)
    
    for category, title in categories.items():
        data = fetcher.get_fno_trends(category=category, limit=10)
        
        if "data" in data and data["data"]:
            print(f"\n{title} ({category}):")
            stocks = data["data"]
            
            for i, stock in enumerate(stocks[:5], 1):
                name = stock.get("name", "N/A")
                price = stock.get("price", 0)
                change = stock.get("pricePerChange", 0)
                trend = stock.get("trend", "")
                
                change_str = f"+{change}%" if change >= 0 else f"{change}%"
                emoji = "🟢" if change >= 0 else "🔴"
                
                print(f"  {i}. {emoji} {name}: ₹{price} ({change_str})")

if __name__ == "__main__":
    main()
