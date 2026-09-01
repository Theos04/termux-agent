#!/usr/bin/env python3
"""
F&O Data Fetcher for MoneyControl
Uses the correct F&O API endpoints for Futures & Options data
"""

import os
import requests
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from colorama import Fore, Style, init

init(autoreset=True)

class FnODataFetcher:
    """Fetches Futures & Options data from MoneyControl"""
    
    def __init__(self):
        self.session = requests.Session()
        self.base_url = "https://priceapi.moneycontrol.com"
        
        # Headers from your HAR analysis
        self.headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Encoding": "gzip, deflate, br",
            "Accept-Language": "en-US,en;q=0.9",
            "Connection": "keep-alive",
            "Host": "priceapi.moneycontrol.com",
            "Origin": "https://www.moneycontrol.com",
            "Referer": "https://www.moneycontrol.com/",
            "Sec-Ch-Ua": '"Chromium";v="149", "Not)A;Brand";v="24"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Linux"',
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site"
        }
        self.session.headers.update(self.headers)
        
    def get_fno_oi_trends(self, category: str = "Active Buying", limit: int = 50) -> Dict:
        """
        Fetch F&O Open Interest trends
        Categories: Active Buying, Strong Buying, Short Covering, 
                    Active Selling, Strong Selling, Profit Booking
        """
        url = f"{self.base_url}/technicalCompanyData/oiData/getFnoOiTrends"
        params = {
            "category": category,
            "expiry": "ALL",
            "type": "ALL",
            "deviceType": "W",
            "limit": limit
        }
        
        try:
            response = self.session.get(url, params=params, timeout=10)
            if response.status_code == 200:
                return response.json()
            else:
                return {"error": f"HTTP {response.status_code}"}
        except Exception as e:
            return {"error": str(e)}
    
    def get_fno_ban_list(self) -> List[str]:
        """Get stocks in F&O ban period"""
        url = f"{self.base_url}/technicalCompanyData/oiData/getFnoBan"
        
        try:
            response = self.session.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if "data" in data:
                    return [stock.get("name") for stock in data["data"] if stock.get("name")]
            return []
        except Exception as e:
            print(f"{Fore.RED}Error fetching ban list: {e}{Style.RESET_ALL}")
            return []
    
    def get_index_option_chain(self, index: str = "NIFTY", expiry_type: str = "current") -> Dict:
        """Get index option chain data for PCR calculation"""
        url = f"{self.base_url}/technicalCompanyData/oiData/getIndexOptionChain"
        params = {
            "index": index,
            "expiryType": expiry_type
        }
        
        try:
            response = self.session.get(url, params=params, timeout=10)
            if response.status_code == 200:
                return response.json()
            return {"error": f"HTTP {response.status_code}"}
        except Exception as e:
            return {"error": str(e)}
    
    def get_individual_stock_fno(self, symbol: str) -> Dict:
        """Get F&O data for individual stock"""
        url = f"{self.base_url}/technicalCompanyData/oiData/getStockFnoData"
        params = {
            "symbol": symbol,
            "expiry": "ALL"
        }
        
        try:
            response = self.session.get(url, params=params, timeout=10)
            if response.status_code == 200:
                return response.json()
            return {"error": f"HTTP {response.status_code}"}
        except Exception as e:
            return {"error": str(e)}
    
    def get_fno_expiry_dates(self) -> Dict:
        """Get F&O expiry dates"""
        url = f"{self.base_url}/technicalCompanyData/oiData/getFnoExpiryDates"
        
        try:
            response = self.session.get(url, timeout=10)
            if response.status_code == 200:
                return response.json()
            return {"error": f"HTTP {response.status_code}"}
        except Exception as e:
            return {"error": str(e)}
    
    def get_fno_volume_data(self, symbol: str) -> Dict:
        """Get F&O volume data for a stock"""
        url = f"{self.base_url}/technicalCompanyData/oiData/getFnoVolumeData"
        params = {"symbol": symbol}
        
        try:
            response = self.session.get(url, params=params, timeout=10)
            if response.status_code == 200:
                return response.json()
            return {"error": f"HTTP {response.status_code}"}
        except Exception as e:
            return {"error": str(e)}
    
    def analyze_fno_pattern(self, stock_data: Dict) -> Dict:
        """Analyze F&O pattern for a stock"""
        name = stock_data.get("name", "")
        price = stock_data.get("price", 0)
        oi = stock_data.get("openInt", 0)
        oi_change = stock_data.get("oiChange", 0)
        price_change = stock_data.get("pricePerChange", 0)
        volume = stock_data.get("volume", 0)
        
        pattern = {
            "name": name,
            "price": price,
            "price_change": price_change,
            "oi": oi,
            "oi_change": oi_change,
            "volume": volume,
            "signal": "NEUTRAL",
            "strength": "LOW"
        }
        
        # Determine pattern based on price and OI movement
        if price_change > 1 and oi_change > 2:
            pattern["signal"] = "LONG_BUILDUP"
            pattern["strength"] = "STRONG"
        elif price_change > 1 and oi_change < -2:
            pattern["signal"] = "SHORT_COVERING"
            pattern["strength"] = "STRONG"
        elif price_change < -1 and oi_change > 2:
            pattern["signal"] = "SHORT_BUILDUP"
            pattern["strength"] = "STRONG"
        elif price_change < -1 and oi_change < -2:
            pattern["signal"] = "LONG_UNWINDING"
            pattern["strength"] = "STRONG"
        elif abs(price_change) <= 1 and oi_change > 2:
            pattern["signal"] = "OI_ADDITION"
            pattern["strength"] = "MEDIUM"
        elif abs(price_change) <= 1 and oi_change < -2:
            pattern["signal"] = "OI_REDUCTION"
            pattern["strength"] = "MEDIUM"
        else:
            pattern["signal"] = "NEUTRAL"
            pattern["strength"] = "LOW"
        
        return pattern

class FnO_StockMonitor:
    """Complete F&O Stock Monitor with all data"""
    
    def __init__(self, check_interval: float = 2.0):
        self.fetcher = FnODataFetcher()
        self.check_interval = check_interval
        self.running = True
        self.ban_list = []
        self.historical_oi = {}
        
    def get_complete_fno_data(self) -> Dict[str, Any]:
        """Get complete F&O data from all categories"""
        categories = ["Active Buying", "Strong Buying", "Short Covering",
                     "Active Selling", "Strong Selling", "Profit Booking"]
        
        all_stocks = {}
        category_counts = {}
        
        print(f"\n{Fore.CYAN}📊 Fetching F&O Data...{Style.RESET_ALL}")
        
        for category in categories:
            data = self.fetcher.get_fno_oi_trends(category=category, limit=50)
            if "data" in data:
                category_counts[category] = len(data["data"])
                for stock in data["data"]:
                    name = stock.get("name", "")
                    if not name:
                        continue
                    
                    if name not in all_stocks:
                        all_stocks[name] = stock.copy()
                        all_stocks[name]["categories"] = [category]
                    else:
                        all_stocks[name]["categories"].append(category)
                        # Update with latest data
                        for key in ["price", "volume", "openInt", "pricePerChange"]:
                            if key in stock:
                                all_stocks[name][key] = stock[key]
        
        # Calculate OI changes
        for name, stock in all_stocks.items():
            current_oi = stock.get("openInt", 0)
            if name in self.historical_oi:
                prev_oi = self.historical_oi[name]
                if prev_oi > 0:
                    oi_change = ((current_oi - prev_oi) / prev_oi) * 100
                    stock["oiChange"] = oi_change
                else:
                    stock["oiChange"] = 0
            else:
                stock["oiChange"] = 0
            
            # Update historical OI
            self.historical_oi[name] = current_oi
        
        # Get ban list
        self.ban_list = self.fetcher.get_fno_ban_list()
        
        # Get PCR data
        pcr_data = self.fetcher.get_index_option_chain()
        
        return {
            "stocks": list(all_stocks.values()),
            "category_counts": category_counts,
            "ban_list": self.ban_list,
            "pcr_data": pcr_data,
            "total_stocks": len(all_stocks)
        }
    
    def analyze_all_patterns(self, stocks: List[Dict]) -> List[Dict]:
        """Analyze F&O patterns for all stocks"""
        patterns = []
        for stock in stocks:
            pattern = self.fetcher.analyze_fno_pattern(stock)
            patterns.append(pattern)
        return sorted(patterns, key=lambda x: abs(x.get("oi_change", 0)), reverse=True)
    
    def display_fno_data(self, data: Dict[str, Any]):
        """Display F&O data in a nice format"""
        os.system('clear' if os.name == 'posix' else 'cls')
        
        stocks = data.get("stocks", [])
        pcr_data = data.get("pcr_data", {})
        ban_list = data.get("ban_list", [])
        
        print(f"{Fore.CYAN}{'='*120}{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}📊 F&O DATA SNAPSHOT - {datetime.now().strftime('%H:%M:%S')}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'='*120}{Style.RESET_ALL}")
        
        # PCR Info
        if pcr_data and "data" in pcr_data:
            print(f"\n{Fore.CYAN}📊 INDEX OPTIONS:{Style.RESET_ALL}")
            print(f"  NIFTY PCR: {Fore.YELLOW}{pcr_data.get('pcr', 'N/A')}{Style.RESET_ALL}")
            print(f"  Total OI: {pcr_data.get('totalOi', 0):,.0f}")
        
        # Ban List
        if ban_list:
            print(f"\n{Fore.RED}🚫 F&O BAN LIST ({len(ban_list)} stocks):{Style.RESET_ALL}")
            for stock in ban_list[:10]:
                print(f"  • {stock}")
            if len(ban_list) > 10:
                print(f"  • ... and {len(ban_list) - 10} more")
        
        # Top F&O Patterns
        print(f"\n{Fore.GREEN}🔍 TOP F&O PATTERNS:{Style.RESET_ALL}")
        patterns = self.analyze_all_patterns(stocks[:100])
        
        pattern_emoji = {
            "LONG_BUILDUP": "🔵",
            "SHORT_COVERING": "🟡",
            "SHORT_BUILDUP": "🔴",
            "LONG_UNWINDING": "📉",
            "OI_ADDITION": "➕",
            "OI_REDUCTION": "➖",
            "NEUTRAL": "⚪"
        }
        
        pattern_names = {
            "LONG_BUILDUP": "Long Build-up ↑ ↑",
            "SHORT_COVERING": "Short Covering ↑ ↓",
            "SHORT_BUILDUP": "Short Build-up ↓ ↑",
            "LONG_UNWINDING": "Long Unwinding ↓ ↓",
            "OI_ADDITION": "OI Addition",
            "OI_REDUCTION": "OI Reduction",
            "NEUTRAL": "Neutral"
        }
        
        for i, pattern in enumerate(patterns[:15], 1):
            if pattern["signal"] != "NEUTRAL":
                emoji = pattern_emoji.get(pattern["signal"], "⚪")
                pname = pattern_names.get(pattern["signal"], "Unknown")
                name = pattern["name"][:25]
                price = pattern["price"]
                change = pattern.get("price_change", 0)
                oi_change = pattern.get("oi_change", 0)
                
                color = Fore.GREEN if change > 0 else Fore.RED if change < 0 else Fore.WHITE
                print(f"  {i:2}. {emoji} {name:25} ₹{price:>8.2f}  {color}{change:>+6.2f}%{Style.RESET_ALL}  OI: {oi_change:>+6.2f}%  {Fore.CYAN}{pname}{Style.RESET_ALL}")
        
        # Category breakdown
        print(f"\n{Fore.CYAN}📊 CATEGORY BREAKDOWN:{Style.RESET_ALL}")
        for category, count in data.get("category_counts", {}).items():
            print(f"  {category}: {count} stocks")
        
        # Market Stats
        total_stocks = data.get("total_stocks", 0)
        strong_bullish = sum(1 for p in patterns if p.get("signal") in ["LONG_BUILDUP", "SHORT_COVERING"] and p.get("strength") == "STRONG")
        strong_bearish = sum(1 for p in patterns if p.get("signal") in ["SHORT_BUILDUP", "LONG_UNWINDING"] and p.get("strength") == "STRONG")
        
        print(f"\n{Fore.CYAN}📊 F&O MARKET STATS:{Style.RESET_ALL}")
        print(f"  Total F&O Stocks: {total_stocks}")
        print(f"  Strong Bullish: {Fore.GREEN}{strong_bullish}{Style.RESET_ALL}")
        print(f"  Strong Bearish: {Fore.RED}{strong_bearish}{Style.RESET_ALL}")
        print(f"  Stocks in Ban: {Fore.RED}{len(ban_list)}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'='*120}{Style.RESET_ALL}")

def main():
    """Main function to run F&O monitor"""
    print(f"{Fore.GREEN}🚀 Starting F&O Data Monitor...{Style.RESET_ALL}")
    print(f"{Fore.YELLOW}Press Ctrl+C to stop{Style.RESET_ALL}")
    
    monitor = FnO_StockMonitor()
    iteration = 0
    
    try:
        while True:
            iteration += 1
            
            # Fetch data every 3 seconds
            data = monitor.get_complete_fno_data()
            monitor.display_fno_data(data)
            
            # Next update
            time.sleep(3)
            
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}⏹️ F&O Monitor stopped{Style.RESET_ALL}")

if __name__ == "__main__":
    main()
