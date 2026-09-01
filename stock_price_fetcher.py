#!/usr/bin/env python3
"""
Stock Price Fetcher for MoneyControl
Fetches real-time stock prices and F&O data
"""

import requests
import json
from datetime import datetime
from typing import List, Dict, Any, Optional

class MoneyControlStockFetcher:
    """Fetch stock prices and F&O data from MoneyControl"""
    
    def __init__(self):
        self.base_url = "https://priceapi.moneycontrol.com"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
            "Accept": "application/json",
            "Referer": "https://www.moneycontrol.com/"
        }
    
    def get_fno_trends(self, category: str = "Active Buying", expiry: str = "ALL", 
                       stock_type: str = "ALL", limit: int = 20) -> Dict[str, Any]:
        """
        Get F&O trends data
        
        Categories:
            - Active Buying
            - Strong Buying
            - Short Covering
            - Active Selling
            - Strong Selling
            - Profit Booking
        """
        url = f"{self.base_url}/technicalCompanyData/oiData/getFnoOiTrends"
        params = {
            "category": category,
            "expiry": expiry,
            "type": stock_type,
            "deviceType": "W",
            "limit": limit
        }
        
        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=10)
            if response.status_code == 200:
                return response.json()
            else:
                return {"error": f"HTTP {response.status_code}", "data": []}
        except Exception as e:
            return {"error": str(e), "data": []}
    
    def get_trending_stocks(self, limit: int = 10) -> List[Dict]:
        """Get trending stocks from MoneyControl"""
        url = f"https://www.moneycontrol.com/techmvc/mc_widgets/trending_stocks"
        params = {"limit": limit, "classic": "true"}
        
        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=10)
            if response.status_code == 200:
                # This returns HTML, not JSON - we need to parse it
                return {"html": response.text}
            return []
        except Exception as e:
            return {"error": str(e)}
    
    def get_stock_quote(self, symbol: str) -> Optional[Dict]:
        """Get stock quote for a specific symbol"""
        # Search through F&O data for the symbol
        data = self.get_fno_trends(category="Active Buying", limit=50)
        
        if "data" in data:
            for item in data["data"]:
                if item.get("name", "").lower() == symbol.lower():
                    return {
                        "symbol": item.get("name"),
                        "price": item.get("price"),
                        "change": item.get("pricePerChange"),
                        "open_interest": item.get("openInt"),
                        "oi_change": item.get("oiPerChange"),
                        "trend": item.get("trend"),
                        "category": item.get("category"),
                        "volume": item.get("volume"),
                        "timestamp": item.get("timestamp")
                    }
        return None
    
    def print_stock_data(self, data: Dict):
        """Pretty print stock data"""
        if "error" in data:
            print(f"❌ Error: {data['error']}")
            return
        
        if "data" not in data:
            print("❌ No data found")
            return
        
        stocks = data["data"]
        if not stocks:
            print("No stocks found")
            return
        
        print(f"\n📊 Stock Data ({len(stocks)} stocks)")
        print("="*60)
        
        # Print summary stats
        bullish = data.get("bullishPercentage", "0")
        bearish = data.get("bearishPercentage", "0")
        print(f"📈 Bullish: {bullish}% | 📉 Bearish: {bearish}%")
        print("-"*60)
        
        # Print each stock
        for i, stock in enumerate(stocks[:20], 1):
            name = stock.get("name", "N/A")
            price = stock.get("price", 0)
            change = stock.get("pricePerChange", 0)
            trend = stock.get("trend", "N/A")
            category = stock.get("category", "N/A")
            oi = stock.get("openInt", 0)
            
            # Emoji for trend
            trend_emoji = "🟢" if trend == "Bullish" else "🔴" if trend == "Bearish" else "⚪"
            
            # Change indicator
            change_str = f"+{change}%" if change >= 0 else f"{change}%"
            change_emoji = "▲" if change >= 0 else "▼"
            
            print(f"{i:2}. {trend_emoji} {name[:25]:25} ₹{price:>8.2f} {change_emoji} {change_str:>7} | {category[:15]:15} | OI: {oi:,.0f}")

def main():
    fetcher = MoneyControlStockFetcher()
    
    print("🚀 MoneyControl Stock Price Fetcher")
    print("="*60)
    print(f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Get F&O trends
    print("📈 Fetching Active Buying trends...")
    data = fetcher.get_fno_trends(category="Active Buying", limit=20)
    fetcher.print_stock_data(data)
    
    # Search for a specific stock
    print("\n" + "="*60)
    print("🔍 Search for a stock (e.g., RELIANCE, TCS, INFY)")
    symbol = input("Enter stock symbol (or press Enter to skip): ").strip()
    
    if symbol:
        stock = fetcher.get_stock_quote(symbol)
        if stock:
            print(f"\n✅ Found {symbol}:")
            print(f"   Price: ₹{stock['price']}")
            print(f"   Change: {stock['change']}%")
            print(f"   Trend: {stock['trend']}")
            print(f"   Category: {stock['category']}")
            print(f"   Open Interest: {stock['open_interest']:,.0f}")
        else:
            print(f"\n❌ Stock '{symbol}' not found in current data")
    
    # Get other categories
    print("\n" + "="*60)
    print("📊 Other Categories:")
    categories = ["Strong Buying", "Short Covering", "Active Selling", "Strong Selling", "Profit Booking"]
    
    for category in categories:
        data = fetcher.get_fno_trends(category=category, limit=5)
        if "data" in data and data["data"]:
            stocks = data["data"]
            print(f"\n{category} ({len(stocks)} stocks):")
            for stock in stocks[:3]:
                name = stock.get("name", "N/A")
                price = stock.get("price", 0)
                change = stock.get("pricePerChange", 0)
                print(f"  • {name}: ₹{price} ({'+' if change >= 0 else ''}{change}%)")

if __name__ == "__main__":
    main()
