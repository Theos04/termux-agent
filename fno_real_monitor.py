#!/usr/bin/env python3
"""
Fixed Real F&O Monitor - Properly tracks OI changes
"""

import requests
import json
import time
import os
from datetime import datetime
from typing import Dict, List, Optional, Any
from collections import defaultdict, deque
from colorama import Fore, Style, init
import signal

init(autoreset=True)

class FnODataFetcher:
    """Fetches F&O data from MoneyControl"""
    
    def __init__(self):
        self.session = requests.Session()
        self.base_url = "https://priceapi.moneycontrol.com"
        
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
            "Accept-Encoding": "gzip, deflate, br",
            "Accept-Language": "en-US,en;q=0.9",
            "Connection": "keep-alive",
            "Host": "priceapi.moneycontrol.com",
            "Origin": "https://www.moneycontrol.com",
            "Referer": "https://www.moneycontrol.com/markets/fno-market-snapshot",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site"
        }
        self.session.headers.update(self.headers)
        
    def get_fno_oi_trends(self, category: str) -> Dict:
        """Get F&O OI trends for a category"""
        url = f"{self.base_url}/technicalCompanyData/oiData/getFnoOiTrends"
        params = {
            "category": category,
            "expiry": "ALL",
            "type": "ALL",
            "deviceType": "W",
            "limit": "100"
        }
        
        try:
            response = self.session.get(url, params=params, timeout=10)
            if response.status_code == 200:
                return response.json()
            return {}
        except Exception as e:
            return {"error": str(e)}
    
    def get_fno_ban_list(self) -> List[str]:
        """Get F&O ban list"""
        url = f"{self.base_url}/technicalCompanyData/oiData/getFnoBan"
        try:
            response = self.session.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if "data" in data:
                    return [s.get("name") for s in data["data"] if s.get("name")]
            return []
        except:
            return []

class FnORealMonitor:
    """Real F&O Monitor with proper OI tracking"""
    
    def __init__(self, interval: float = 3.0):
        self.fetcher = FnODataFetcher()
        self.interval = interval
        self.running = True
        
        # Store historical data with proper deques
        self.history = defaultdict(lambda: {
            "oi": deque(maxlen=10),
            "price": deque(maxlen=10),
            "volume": deque(maxlen=10)
        })
        
        self.stock_data = {}
        self.ban_list = []
        self.iteration = 0
        
        signal.signal(signal.SIGINT, self.signal_handler)
    
    def signal_handler(self, sig, frame):
        print(f"\n{Fore.YELLOW}⏹️ Stopping monitor...{Style.RESET_ALL}")
        self.running = False
    
    def fetch_all_categories(self) -> Dict:
        """Fetch data from all categories"""
        categories = [
            "Active Buying", "Strong Buying", "Short Covering",
            "Active Selling", "Strong Selling", "Profit Booking"
        ]
        
        all_stocks = {}
        
        for category in categories:
            data = self.fetcher.get_fno_oi_trends(category)
            
            if "data" in data and data["data"]:
                for stock in data["data"]:
                    name = stock.get("name", "")
                    if not name:
                        continue
                    
                    if name not in all_stocks:
                        all_stocks[name] = {
                            "name": name,
                            "price": stock.get("price", 0),
                            "openInt": stock.get("openInt", 0),
                            "volume": stock.get("volume", 0),
                            "pricePerChange": stock.get("pricePerChange", 0),
                            "categories": [category],
                            "oiChange": 0  # Will be calculated
                        }
                    else:
                        # Update with latest data
                        for key in ["price", "openInt", "volume", "pricePerChange"]:
                            if key in stock:
                                all_stocks[name][key] = stock[key]
                        all_stocks[name]["categories"].append(category)
        
        # Update history and calculate OI changes
        for name, stock in all_stocks.items():
            current_oi = stock["openInt"]
            current_price = stock["price"]
            current_volume = stock["volume"]
            
            # Store in history
            if current_oi > 0:
                self.history[name]["oi"].append(current_oi)
            if current_price > 0:
                self.history[name]["price"].append(current_price)
            if current_volume > 0:
                self.history[name]["volume"].append(current_volume)
            
            # Calculate OI change from history
            oi_history = list(self.history[name]["oi"])
            if len(oi_history) >= 2:
                prev_oi = oi_history[-2]
                if prev_oi > 0:
                    oi_change = ((current_oi - prev_oi) / prev_oi) * 100
                    stock["oiChange"] = oi_change
        
        # Get ban list
        self.ban_list = self.fetcher.get_fno_ban_list()
        
        return {
            "stocks": list(all_stocks.values()),
            "ban_list": self.ban_list,
            "total": len(all_stocks)
        }
    
    def classify_pattern(self, stock: Dict) -> Dict:
        """Classify F&O pattern"""
        price_change = stock.get("pricePerChange", 0)
        oi_change = stock.get("oiChange", 0)
        
        # Only classify if we have OI data
        if abs(oi_change) < 0.5:
            return {
                "signal": "WAITING_FOR_DATA",
                "emoji": "⏳",
                "description": "Collecting data...",
                "color": Fore.WHITE
            }
        
        # Determine pattern
        if price_change > 1.5 and oi_change > 2:
            return {
                "signal": "LONG_BUILDUP",
                "emoji": "🔵",
                "description": "Long Build-up",
                "color": Fore.GREEN
            }
        elif price_change > 1.5 and oi_change < -2:
            return {
                "signal": "SHORT_COVERING",
                "emoji": "🟡",
                "description": "Short Covering",
                "color": Fore.YELLOW
            }
        elif price_change < -1.5 and oi_change > 2:
            return {
                "signal": "SHORT_BUILDUP",
                "emoji": "🔴",
                "description": "Short Build-up",
                "color": Fore.RED
            }
        elif price_change < -1.5 and oi_change < -2:
            return {
                "signal": "LONG_UNWINDING",
                "emoji": "📉",
                "description": "Long Unwinding",
                "color": Fore.BLUE
            }
        elif abs(price_change) <= 1.5 and oi_change > 3:
            return {
                "signal": "OI_ADDITION",
                "emoji": "➕",
                "description": "OI Addition",
                "color": Fore.CYAN
            }
        elif abs(price_change) <= 1.5 and oi_change < -3:
            return {
                "signal": "OI_REDUCTION",
                "emoji": "➖",
                "description": "OI Reduction",
                "color": Fore.MAGENTA
            }
        else:
            return {
                "signal": "NEUTRAL",
                "emoji": "⚪",
                "description": "Neutral",
                "color": Fore.WHITE
            }
    
    def display_data(self, data: Dict):
        """Display F&O data"""
        os.system('clear' if os.name == 'posix' else 'cls')
        
        stocks = data.get("stocks", [])
        ban_list = data.get("ban_list", [])
        
        print(f"{Fore.CYAN}{'='*120}{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}📊 REAL F&O MONITOR - {datetime.now().strftime('%H:%M:%S')}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'='*120}{Style.RESET_ALL}")
        
        # Show number of stocks with OI data
        stocks_with_oi = [s for s in stocks if s.get("openInt", 0) > 0]
        stocks_with_history = [s for s in stocks if len(self.history[s["name"]]["oi"]) >= 2]
        
        print(f"\n{Fore.CYAN}📊 DATA STATUS:{Style.RESET_ALL}")
        print(f"  Total Stocks: {len(stocks)}")
        print(f"  Stocks with OI: {len(stocks_with_oi)}")
        print(f"  Stocks with OI History: {len(stocks_with_history)} (showing patterns)")
        
        # Ban List
        if ban_list:
            print(f"\n{Fore.RED}🚫 F&O BAN LIST ({len(ban_list)} stocks):{Style.RESET_ALL}")
            for stock in ban_list[:10]:
                print(f"  • {stock}")
            if len(ban_list) > 10:
                print(f"  • ... and {len(ban_list) - 10} more")
        
        # Top F&O Patterns
        print(f"\n{Fore.GREEN}🔍 TOP F&O PATTERNS:{Style.RESET_ALL}")
        
        patterns = []
        for stock in stocks:
            if stock.get("openInt", 0) > 0 and len(self.history[stock["name"]]["oi"]) >= 2:
                pattern = self.classify_pattern(stock)
                if pattern["signal"] != "NEUTRAL" and pattern["signal"] != "WAITING_FOR_DATA":
                    patterns.append({
                        "stock": stock,
                        "pattern": pattern
                    })
        
        # Sort by absolute OI change
        patterns.sort(key=lambda x: abs(x["stock"].get("oiChange", 0)), reverse=True)
        
        if patterns:
            for i, item in enumerate(patterns[:20], 1):
                stock = item["stock"]
                pattern = item["pattern"]
                name = stock["name"][:25]
                price = stock["price"]
                change = stock.get("pricePerChange", 0)
                oi_change = stock.get("oiChange", 0)
                volume = stock.get("volume", 0)
                
                color = Fore.GREEN if change > 0 else Fore.RED if change < 0 else Fore.WHITE
                vol_color = Fore.YELLOW if volume > 10_000_000 else Fore.WHITE
                
                print(f"  {i:2}. {pattern['emoji']} {name:25} ₹{price:>8.2f}  {color}{change:>+6.2f}%{Style.RESET_ALL}  OI: {oi_change:>+6.2f}%  {pattern['color']}{pattern['description']:15}{Style.RESET_ALL}  {vol_color}📊 {volume:>10,}{Style.RESET_ALL}")
        else:
            print(f"  {Fore.YELLOW}⏳ Waiting for OI data to accumulate... (need 2 readings){Style.RESET_ALL}")
            print(f"  {Fore.YELLOW}   This will happen in the next update cycle{Style.RESET_ALL}")
        
        # OI Gainers
        print(f"\n{Fore.GREEN}📈 TOP OI GAINERS:{Style.RESET_ALL}")
        oi_gainers = [s for s in stocks if s.get("oiChange", 0) > 2 and s.get("openInt", 0) > 0]
        oi_gainers.sort(key=lambda x: x.get("oiChange", 0), reverse=True)
        
        if oi_gainers:
            for i, stock in enumerate(oi_gainers[:10], 1):
                name = stock["name"][:25]
                price = stock["price"]
                change = stock.get("pricePerChange", 0)
                oi_change = stock.get("oiChange", 0)
                color = Fore.GREEN if change > 0 else Fore.RED
                print(f"  {i:2}. {name:25} ₹{price:>8.2f}  {color}{change:>+6.2f}%{Style.RESET_ALL}  OI: {Fore.GREEN}+{oi_change:>5.1f}%{Style.RESET_ALL}")
        else:
            print(f"  {Fore.YELLOW}No OI gainers yet (need 2 readings){Style.RESET_ALL}")
        
        # OI Losers
        print(f"\n{Fore.RED}📉 TOP OI LOSERS:{Style.RESET_ALL}")
        oi_losers = [s for s in stocks if s.get("oiChange", 0) < -2 and s.get("openInt", 0) > 0]
        oi_losers.sort(key=lambda x: x.get("oiChange", 0))
        
        if oi_losers:
            for i, stock in enumerate(oi_losers[:10], 1):
                name = stock["name"][:25]
                price = stock["price"]
                change = stock.get("pricePerChange", 0)
                oi_change = stock.get("oiChange", 0)
                color = Fore.RED if change < 0 else Fore.GREEN
                print(f"  {i:2}. {name:25} ₹{price:>8.2f}  {color}{change:>+6.2f}%{Style.RESET_ALL}  OI: {Fore.RED}{oi_change:>6.1f}%{Style.RESET_ALL}")
        else:
            print(f"  {Fore.YELLOW}No OI losers yet (need 2 readings){Style.RESET_ALL}")
        
        # Market Stats
        total_volume = sum(s.get("volume", 0) for s in stocks)
        
        print(f"\n{Fore.CYAN}📊 MARKET STATS:{Style.RESET_ALL}")
        print(f"  Total F&O Stocks: {len(stocks)}")
        print(f"  Total Volume: {total_volume:,.0f}")
        print(f"  Stocks in Ban: {len(ban_list)}")
        print(f"  Iteration: {self.iteration}")
        print(f"{Fore.CYAN}{'='*120}{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}⏱️ Updating every {self.interval}s | Press Ctrl+C to stop{Style.RESET_ALL}")
        
        # Show progress for first few iterations
        if self.iteration <= 3:
            print(f"\n{Fore.CYAN}📝 NOTE: Pattern data will appear after 2 updates{Style.RESET_ALL}")
    
    def run(self):
        """Main loop"""
        print(f"{Fore.GREEN}🚀 Starting Real F&O Monitor...{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}   Pattern data will appear after 2 updates (6 seconds){Style.RESET_ALL}\n")
        
        while self.running:
            try:
                self.iteration += 1
                
                # Fetch data
                data = self.fetch_all_categories()
                
                if data and data.get("stocks"):
                    self.display_data(data)
                else:
                    print(f"{Fore.RED}⚠️ No data received. Retrying...{Style.RESET_ALL}")
                
                time.sleep(self.interval)
                
            except KeyboardInterrupt:
                print(f"\n{Fore.YELLOW}⏹️ Stopped by user{Style.RESET_ALL}")
                break
            except Exception as e:
                print(f"{Fore.RED}❌ Error: {e}{Style.RESET_ALL}")
                time.sleep(self.interval)

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Real F&O Monitor')
    parser.add_argument('-i', '--interval', type=float, default=3.0,
                       help='Update interval in seconds (default: 3.0)')
    
    args = parser.parse_args()
    
    monitor = FnORealMonitor(interval=args.interval)
    monitor.run()

if __name__ == "__main__":
    main()
