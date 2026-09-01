#!/usr/bin/env python3
"""
Enhanced Real-time Stock Monitor with Live Graphs
Fixed bugs + Visual charts for better analysis
"""

import requests
import json
import time
import os
import sys
from datetime import datetime
from typing import Dict, List, Any, Optional
from collections import defaultdict, deque
import signal
from colorama import Fore, Style, init
import threading

# For terminal graphs
try:
    import plotext as plt
    HAS_PLOTEXT = True
except ImportError:
    HAS_PLOTEXT = False
    print(f"{Fore.YELLOW}⚠️ Install plotext for graphs: pip install plotext{Style.RESET_ALL}")

init(autoreset=True)

class EnhancedStockMonitor:
    """Enhanced real-time stock monitor with live graphs"""

    def __init__(self, check_interval: float = 2.0):
        self.session = requests.Session()
        self.base_url = "https://priceapi.moneycontrol.com"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
            "Accept": "application/json",
            "Referer": "https://www.moneycontrol.com/"
        }
        self.check_interval = check_interval
        self.running = True
        
        # Historical data storage
        self.price_history = defaultdict(lambda: deque(maxlen=100))
        self.volume_history = defaultdict(lambda: deque(maxlen=100))
        self.volume_delta_history = defaultdict(lambda: deque(maxlen=60))
        self.oi_history = defaultdict(lambda: deque(maxlen=100))
        self.timestamps = defaultdict(lambda: deque(maxlen=100))
        
        # Day's high/low tracking
        self.day_high = {}
        self.day_low = {}
        self.prev_day_close = {}
        
        # Alert thresholds
        self.price_change_threshold = 0.5
        self.volume_spike_threshold = 2.0
        self.penny_stock_threshold = 50.0
        self.min_volume_threshold = 1_000_000
        
        # Watchlist (expandable)
        self.watchlist = {"LTM", "Suzlon Energy", "APL Apollo", "Ashok Leyland", 
                         "Reliance", "TCS", "HDFC Bank", "Infosys", "ICICI Bank"}
        
        # Alert log
        self.alert_log = []
        self.display_mode = "full"  # "full", "compact", "graph"
        
        signal.signal(signal.SIGINT, self.signal_handler)

    def signal_handler(self, sig, frame):
        print(f"\n{Fore.YELLOW}⏹️ Stopping monitor...{Style.RESET_ALL}")
        self.running = False

    def get_fno_data(self, category: str = "Active Buying", limit: int = 30) -> Dict:
        """Fetch F&O data for a specific category"""
        url = f"{self.base_url}/technicalCompanyData/oiData/getFnoOiTrends"
        params = {
            "category": category,
            "expiry": "ALL",
            "type": "ALL",
            "deviceType": "W",
            "limit": limit
        }

        try:
            response = self.session.get(url, headers=self.headers, params=params, timeout=5)
            if response.status_code == 200:
                return response.json()
            return {}
        except Exception as e:
            return {"error": str(e)}

    def fetch_all_stocks(self) -> List[Dict]:
        """Fetch stocks with F&O categorization"""
        categories = ["Active Buying", "Strong Buying", "Short Covering",
                     "Active Selling", "Strong Selling", "Profit Booking"]

        stock_map = {}

        for category in categories:
            data = self.get_fno_data(category=category, limit=40)  # Increased limit
            if "data" in data:
                for stock in data["data"]:
                    name = stock.get("name", "")
                    if not name:
                        continue
                    
                    if name not in stock_map:
                        stock_map[name] = stock.copy()
                        stock_map[name]["categories"] = [category]
                    else:
                        stock_map[name]["categories"].append(category)
                        for key in ["price", "volume", "openInt", "pricePerChange"]:
                            if key in stock:
                                stock_map[name][key] = stock[key]

        return list(stock_map.values())

    def calculate_volume_spike(self, stock_name: str, current_volume: float) -> Optional[float]:
        """Calculate volume spike using deltas"""
        if stock_name not in self.volume_history or len(self.volume_history[stock_name]) == 0:
            self.volume_history[stock_name].append(current_volume)
            return None
            
        previous_volume = self.volume_history[stock_name][-1]
        delta = current_volume - previous_volume
        
        self.volume_delta_history[stock_name].append(delta)
        
        deltas = list(self.volume_delta_history[stock_name])
        if len(deltas) < 10:
            return None
            
        avg_delta = sum(deltas[:-1]) / (len(deltas) - 1)
        if avg_delta > 0 and delta > avg_delta * self.volume_spike_threshold:
            return delta / avg_delta
        
        return None

    def check_price_movement(self, stock_name: str, current_price: float) -> Dict:
        """Check for significant price movements"""
        history = self.price_history[stock_name]
        
        if len(history) < 1:
            return {}
            
        old_price = history[-1]
        change_pct = ((current_price - old_price) / old_price) * 100
        
        # Update day's high/low
        if stock_name not in self.day_high or current_price > self.day_high[stock_name]:
            self.day_high[stock_name] = current_price
        if stock_name not in self.day_low or current_price < self.day_low[stock_name]:
            self.day_low[stock_name] = current_price

        if abs(change_pct) >= self.price_change_threshold:
            direction = f"{Fore.GREEN}🚀 UP{Style.RESET_ALL}" if change_pct > 0 else f"{Fore.RED}🔻 DOWN{Style.RESET_ALL}"
            return {
                "change_pct": change_pct,
                "direction": direction,
                "old_price": old_price,
                "new_price": current_price
            }
        return {}

    def analyze_oi_pattern(self, stock_name: str, price: float, oi: float) -> Dict:
        """FIXED: OI-based pattern analysis"""
        if stock_name not in self.oi_history or len(self.oi_history[stock_name]) < 1:
            self.oi_history[stock_name].append(oi)
            return {}
            
        prev_oi = self.oi_history[stock_name][-1]
        
        # Get previous price safely
        if stock_name in self.price_history and len(self.price_history[stock_name]) > 0:
            prev_price = self.price_history[stock_name][-1]
        else:
            prev_price = price
            
        price_change = price - prev_price if prev_price != price else 0
        oi_change = oi - prev_oi
        
        # Classify pattern
        pattern = ""
        if price_change > 0 and oi_change > 0:
            pattern = f"{Fore.GREEN}Long Build-up{Style.RESET_ALL}"
        elif price_change > 0 and oi_change < 0:
            pattern = f"{Fore.YELLOW}Short Covering{Style.RESET_ALL}"
        elif price_change < 0 and oi_change > 0:
            pattern = f"{Fore.RED}Short Build-up{Style.RESET_ALL}"
        elif price_change < 0 and oi_change < 0:
            pattern = f"{Fore.BLUE}Long Unwinding{Style.RESET_ALL}"
            
        return {"pattern": pattern, "price_change": price_change, "oi_change": oi_change}

    def calculate_momentum_score(self, stock: Dict) -> float:
        """FIXED: Composite momentum score"""
        name = stock.get("name", "")
        price_change = stock.get("pricePerChange", 0)
        volume = stock.get("volume", 0)
        oi = stock.get("openInt", 0)
        price = stock.get("price", 0)
        
        # Price score
        price_score = max(-1, min(1, price_change / 10))
        
        # Volume score
        volume_score = min(1, volume / 50_000_000)
        
        # OI score
        oi_score = 0
        if name in self.oi_history:
            oi_hist = list(self.oi_history[name])
            if len(oi_hist) > 1:
                oi_change_pct = ((oi_hist[-1] - oi_hist[-2]) / oi_hist[-2] * 100) if oi_hist[-2] > 0 else 0
                oi_score = max(-1, min(1, oi_change_pct / 20))
        
        # Category weight
        category_weights = {
            "Strong Buying": 0.3,
            "Active Buying": 0.2,
            "Short Covering": 0.25,
            "Active Selling": -0.2,
            "Strong Selling": -0.3,
            "Profit Booking": -0.15
        }
        categories = stock.get("categories", [])
        cat_score = sum(category_weights.get(cat, 0) for cat in categories) / max(1, len(categories))
        
        # Composite score
        score = (
            0.35 * price_score +
            0.25 * volume_score +
            0.20 * oi_score +
            0.10 * min(1, volume * price / 1_000_000_000) +
            0.10 * cat_score
        )
        
        return score

    def plot_price_chart(self, stock_name: str):
        """Generate terminal price chart"""
        if not HAS_PLOTEXT:
            return
            
        prices = list(self.price_history.get(stock_name, []))
        if len(prices) < 10:
            return
            
        plt.clear_figure()
        plt.plot(prices, marker="●", color="cyan")
        plt.title(f"{stock_name} Price Movement")
        plt.xlabel("Time (samples)")
        plt.ylabel("Price (₹)")
        plt.grid(True)
        plt.show()
        print("\n")

    def plot_volume_chart(self, stock_name: str):
        """Generate terminal volume chart"""
        if not HAS_PLOTEXT:
            return
            
        volumes = list(self.volume_history.get(stock_name, []))
        if len(volumes) < 10:
            return
            
        plt.clear_figure()
        plt.bar(volumes, color="yellow")
        plt.title(f"{stock_name} Volume")
        plt.xlabel("Time (samples)")
        plt.ylabel("Volume")
        plt.grid(True)
        plt.show()
        print("\n")

    def identify_penny_stocks(self, stocks: List[Dict]) -> List[Dict]:
        """Identify penny stocks with sufficient liquidity"""
        penny_stocks = []
        for stock in stocks:
            price = stock.get("price", 0)
            volume = stock.get("volume", 0)
            
            if price <= self.penny_stock_threshold and volume > self.min_volume_threshold:
                penny_stocks.append({
                    "name": stock.get("name"),
                    "price": price,
                    "volume": volume,
                    "oi": stock.get("openInt", 0),
                    "change": stock.get("pricePerChange", 0),
                    "categories": stock.get("categories", [])
                })
        return sorted(penny_stocks, key=lambda x: x["volume"], reverse=True)

    def display_watchlist(self, stocks: List[Dict]):
        """Display watchlist stocks"""
        watchlist_stocks = [s for s in stocks if s.get("name") in self.watchlist]
        if not watchlist_stocks:
            return
            
        print(f"\n{Fore.CYAN}⭐ WATCHLIST:{Style.RESET_ALL}")
        for stock in sorted(watchlist_stocks, key=lambda x: x.get("pricePerChange", 0), reverse=True):
            name = stock.get("name", "N/A")
            price = stock.get("price", 0)
            change = stock.get("pricePerChange", 0)
            vol = stock.get("volume", 0)
            color = Fore.GREEN if change > 0 else Fore.RED if change < 0 else Fore.WHITE
            print(f"  {name:20} ₹{price:>8.2f}  {color}{change:>+6.2f}%{Style.RESET_ALL}  📊 {vol:>12,.0f}")

    def display_status(self, current_time: str, stocks: List[Dict],
                      alerts: List[Dict], penny_stocks: List[Dict]):
        """Enhanced display with more stocks and graph options"""
        os.system('clear' if os.name == 'posix' else 'cls')

        print(f"{Fore.CYAN}{'='*100}{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}📊 ENHANCED STOCK MONITOR - {current_time}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'='*100}{Style.RESET_ALL}")

        # Show watchlist
        self.display_watchlist(stocks)

        # Show alerts
        if alerts:
            print(f"\n{Fore.MAGENTA}🚨 ALERTS:{Style.RESET_ALL}")
            for alert in alerts[:10]:  # Show top 10 alerts
                print(f"  • {alert['stock']}: {alert['message']}")
            print(f"{Fore.CYAN}{'-'*100}{Style.RESET_ALL}")

        # Sort by change
        sorted_by_change = sorted(stocks, key=lambda x: x.get("pricePerChange", 0), reverse=True)
        
        # Show TOP 10 gainers (increased from 5)
        print(f"\n{Fore.GREEN}📈 TOP 10 GAINERS:{Style.RESET_ALL}")
        for i, stock in enumerate(sorted_by_change[:10], 1):
            name = stock.get("name", "N/A")[:25]
            price = stock.get("price", 0)
            change = stock.get("pricePerChange", 0)
            vol = stock.get("volume", 0)
            oi = stock.get("openInt", 0)
            oi_pattern = self.analyze_oi_pattern(name, price, oi)
            pattern_emoji = "🔵" if "Long Build" in str(oi_pattern) else "🟡" if "Short Cover" in str(oi_pattern) else "🔴" if "Short Build" in str(oi_pattern) else "⚪"
            color = Fore.GREEN if change > 0 else Fore.RED
            print(f"  {i:2}. {name:25} ₹{price:>8.2f}  {color}{change:>+6.2f}%{Style.RESET_ALL}  {pattern_emoji}  📊 {vol:>12,.0f}")

        # Show TOP 10 losers (increased from 5)
        print(f"\n{Fore.RED}📉 TOP 10 LOSERS:{Style.RESET_ALL}")
        for i, stock in enumerate(sorted_by_change[-10:], 1):
            name = stock.get("name", "N/A")[:25]
            price = stock.get("price", 0)
            change = stock.get("pricePerChange", 0)
            vol = stock.get("volume", 0)
            color = Fore.RED if change < 0 else Fore.GREEN
            print(f"  {i:2}. {name:25} ₹{price:>8.2f}  {color}{change:>+6.2f}%{Style.RESET_ALL}  📊 {vol:>12,.0f}")

        # Momentum leaders - TOP 10
        print(f"\n{Fore.CYAN}🚀 MOMENTUM LEADERS (Top 10):{Style.RESET_ALL}")
        scored_stocks = []
        for stock in stocks[:50]:  # Check top 50 for performance
            try:
                score = self.calculate_momentum_score(stock)
                if score > 0.2:
                    scored_stocks.append((stock, score))
            except Exception as e:
                continue
        
        for idx, (stock, score) in enumerate(sorted(scored_stocks, key=lambda x: x[1], reverse=True)[:10], 1):
            name = stock.get("name", "N/A")[:25]
            price = stock.get("price", 0)
            change = stock.get("pricePerChange", 0)
            vol = stock.get("volume", 0)
            color = Fore.GREEN if change > 0 else Fore.RED
            print(f"  {idx:2}. {name:25} ₹{price:>8.2f}  {color}{change:>+6.2f}%{Style.RESET_ALL}  ⭐ {score:>5.2f}  📊 {vol:>12,.0f}")

        # Penny stocks
        if penny_stocks:
            print(f"\n{Fore.YELLOW}🪙 PENNY STOCKS (Under ₹50, Vol > 1M):{Style.RESET_ALL}")
            for i, stock in enumerate(penny_stocks[:10], 1):
                change_color = Fore.GREEN if stock['change'] > 0 else Fore.RED if stock['change'] < 0 else Fore.WHITE
                print(f"  {i:2}. {stock['name']:25} ₹{stock['price']:>6.2f}  {change_color}{stock['change']:>+5.2f}%{Style.RESET_ALL}  📊 {stock['volume']:>12,.0f}")

        # Market stats
        total_volume = sum(s.get("volume", 0) for s in stocks)
        avg_price = sum(s.get("price", 0) for s in stocks) / len(stocks) if stocks else 0
        total_stocks = len(stocks)
        advancing = sum(1 for s in stocks if s.get("pricePerChange", 0) > 0)
        declining = sum(1 for s in stocks if s.get("pricePerChange", 0) < 0)
        
        print(f"\n{Fore.CYAN}📊 MARKET STATS:{Style.RESET_ALL}")
        print(f"  Total Stocks: {total_stocks}  |  Advancing: {Fore.GREEN}{advancing}{Style.RESET_ALL}  |  Declining: {Fore.RED}{declining}{Style.RESET_ALL}")
        print(f"  Total Volume: {total_volume:,.0f}  |  Avg Price: ₹{avg_price:.2f}")
        print(f"  Penny Stocks: {len(penny_stocks)}")
        print(f"{Fore.CYAN}{'='*100}{Style.RESET_ALL}")
        
        # Interactive options
        print(f"{Fore.YELLOW}⏱️ Monitoring every {self.check_interval}s | Press Ctrl+C to stop{Style.RESET_ALL}")
        print(f"{Fore.CYAN}📈 To see graphs: Type 'graph STOCK_NAME' in another terminal{Style.RESET_ALL}")

    def monitor_loop(self):
        """Main monitoring loop"""
        print(f"{Fore.GREEN}🔄 Monitoring every {self.check_interval} second(s)...{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}Press Ctrl+C to stop | Shows TOP 10 gainers/losers{Style.RESET_ALL}\n")

        iteration = 0

        while self.running:
            try:
                iteration += 1
                current_time = datetime.now().strftime("%H:%M:%S")

                stocks = self.fetch_all_stocks()

                if not stocks:
                    print(f"[{current_time}] {Fore.RED}⚠️ No data received{Style.RESET_ALL}")
                    time.sleep(self.check_interval)
                    continue

                alerts_found = []
                penny_stocks = self.identify_penny_stocks(stocks)

                for stock in stocks:
                    name = stock.get("name", "")
                    price = stock.get("price", 0)
                    volume = stock.get("volume", 0)
                    oi = stock.get("openInt", 0)

                    if price == 0:
                        continue

                    # Store timestamp
                    self.timestamps[name].append(time.time())

                    # Price check
                    price_alert = self.check_price_movement(name, price)
                    
                    # Store current values
                    self.price_history[name].append(price)
                    if volume > 0:
                        self.volume_history[name].append(volume)
                    if oi > 0:
                        self.oi_history[name].append(oi)

                    if price_alert:
                        alerts_found.append({
                            "type": "price_movement",
                            "stock": name,
                            "message": f"{price_alert['direction']} {price_alert['change_pct']:.2f}% (₹{price_alert['old_price']:.2f} → ₹{price:.2f})",
                            "price": price,
                            "change": price_alert['change_pct']
                        })

                    # Volume spike
                    spike_multiplier = self.calculate_volume_spike(name, volume)
                    if spike_multiplier and spike_multiplier > self.volume_spike_threshold:
                        alerts_found.append({
                            "type": "volume_spike",
                            "stock": name,
                            "message": f"{Fore.YELLOW}📊 Volume spike: {spike_multiplier:.1f}x normal{Style.RESET_ALL}",
                            "volume": volume
                        })
                    
                    # OI pattern
                    oi_pattern = self.analyze_oi_pattern(name, price, oi)
                    if oi_pattern and "pattern" in oi_pattern and oi_pattern["pattern"]:
                        if "Long Build" in oi_pattern["pattern"] or "Short Cover" in oi_pattern["pattern"]:
                            alerts_found.append({
                                "type": "oi_pattern",
                                "stock": name,
                                "message": f"{oi_pattern['pattern']}",
                                "price": price
                            })

                # Update display every 3 iterations
                if iteration % 3 == 0 or alerts_found or penny_stocks:
                    self.display_status(current_time, stocks, alerts_found, penny_stocks)

                time.sleep(self.check_interval)

            except Exception as e:
                print(f"{Fore.RED}❌ Error in monitor loop: {e}{Style.RESET_ALL}")
                time.sleep(self.check_interval)

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Enhanced Real-time Stock Monitor with Graphs')
    parser.add_argument('-i', '--interval', type=float, default=2.0,
                       help='Check interval in seconds (default: 2.0)')
    parser.add_argument('-p', '--penny', type=float, default=50.0,
                       help='Penny stock price threshold (default: 50)')
    parser.add_argument('-c', '--change', type=float, default=0.5,
                       help='Price change alert threshold (default: 0.5%%)')
    parser.add_argument('-v', '--volume', type=float, default=2.0,
                       help='Volume spike multiplier (default: 2.0x)')

    args = parser.parse_args()

    monitor = EnhancedStockMonitor(check_interval=args.interval)
    monitor.penny_stock_threshold = args.penny
    monitor.price_change_threshold = args.change
    monitor.volume_spike_threshold = args.volume

    print(f"{Fore.CYAN}{'='*100}{Style.RESET_ALL}")
    print(f"{Fore.GREEN}🚀 ENHANCED REAL-TIME STOCK MONITOR WITH GRAPHS{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'='*100}{Style.RESET_ALL}")
    print(f"⏱️ Interval: {args.interval}s")
    print(f"🪙 Penny Stock Threshold: ₹{args.penny}")
    print(f"📊 Price Change Alert: {args.change}%")
    print(f"📈 Volume Spike Alert: {args.volume}x average")
    print(f"{Fore.CYAN}{'='*100}{Style.RESET_ALL}")

    try:
        monitor.monitor_loop()
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}⏹️ Monitor stopped by user{Style.RESET_ALL}")

if __name__ == "__main__":
    main()
