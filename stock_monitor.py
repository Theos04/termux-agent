#!/usr/bin/env python3
"""
Real-time Stock Price Monitor for MoneyControl
Tracks prices to the second, monitors volume spikes, and alerts on opportunities
"""

import requests
import json
import time
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from collections import defaultdict, deque
import threading
import signal

class StockMonitor:
    """Real-time stock price monitor with alerting"""
    
    def __init__(self, check_interval: float = 1.0):
        self.base_url = "https://priceapi.moneycontrol.com"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
            "Accept": "application/json",
            "Referer": "https://www.moneycontrol.com/"
        }
        self.check_interval = check_interval
        self.running = True
        self.data_history = defaultdict(lambda: deque(maxlen=100))
        self.price_history = defaultdict(lambda: deque(maxlen=60))
        self.volume_history = defaultdict(lambda: deque(maxlen=60))
        self.alerts = []
        self.lock = threading.Lock()
        
        self.price_change_threshold = 0.5
        self.volume_spike_threshold = 2.0
        self.penny_stock_threshold = 50.0
        
        signal.signal(signal.SIGINT, self.signal_handler)
        
    def signal_handler(self, sig, frame):
        print("\n⏹️ Stopping monitor...")
        self.running = False
        
    def get_fno_data(self, category: str = "Active Buying", limit: int = 50) -> Dict:
        url = f"{self.base_url}/technicalCompanyData/oiData/getFnoOiTrends"
        params = {
            "category": category,
            "expiry": "ALL",
            "type": "ALL",
            "deviceType": "W",
            "limit": limit
        }
        
        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=5)
            if response.status_code == 200:
                return response.json()
            return {}
        except Exception as e:
            return {"error": str(e)}
    
    def fetch_all_stocks(self) -> List[Dict]:
        categories = ["Active Buying", "Strong Buying", "Short Covering", 
                     "Active Selling", "Strong Selling", "Profit Booking"]
        
        all_stocks = []
        seen_symbols = set()
        
        for category in categories:
            data = self.get_fno_data(category=category, limit=30)
            if "data" in data:
                for stock in data["data"]:
                    name = stock.get("name", "")
                    if name and name not in seen_symbols:
                        seen_symbols.add(name)
                        stock["category"] = category
                        all_stocks.append(stock)
        
        return all_stocks
    
    def check_volume_spike(self, stock_name: str, current_volume: float) -> bool:
        history = self.volume_history[stock_name]
        if len(history) < 10:
            return False
        
        avg_volume = sum(history) / len(history)
        if avg_volume > 0 and current_volume > avg_volume * self.volume_spike_threshold:
            return True
        return False
    
    def check_price_movement(self, stock_name: str, current_price: float) -> Dict:
        history = self.price_history[stock_name]
        if len(history) < 2:
            return {}
        
        old_price = history[-1]
        change_pct = ((current_price - old_price) / old_price) * 100
        
        if abs(change_pct) >= self.price_change_threshold:
            direction = "🚀 UP" if change_pct > 0 else "🔻 DOWN"
            return {
                "change_pct": change_pct,
                "direction": direction,
                "old_price": old_price,
                "new_price": current_price
            }
        return {}
    
    def identify_penny_stocks(self, stocks: List[Dict]) -> List[Dict]:
        penny_stocks = []
        for stock in stocks:
            price = stock.get("price", 0)
            volume = stock.get("volume", 0)
            oi = stock.get("openInt", 0)
            
            if price <= self.penny_stock_threshold and volume > 100000:
                penny_stocks.append({
                    "name": stock.get("name"),
                    "price": price,
                    "volume": volume,
                    "oi": oi,
                    "change": stock.get("pricePerChange", 0),
                    "category": stock.get("category", "")
                })
        
        return sorted(penny_stocks, key=lambda x: x["volume"], reverse=True)
    
    def monitor_loop(self):
        print(f"🔄 Monitoring every {self.check_interval} second(s)...")
        print("Press Ctrl+C to stop\n")
        
        iteration = 0
        
        while self.running:
            try:
                iteration += 1
                current_time = datetime.now().strftime("%H:%M:%S")
                
                stocks = self.fetch_all_stocks()
                
                if not stocks:
                    print(f"[{current_time}] ⚠️ No data received")
                    time.sleep(self.check_interval)
                    continue
                
                alerts_found = []
                penny_stocks = self.identify_penny_stocks(stocks)
                
                for stock in stocks:
                    name = stock.get("name", "")
                    price = stock.get("price", 0)
                    volume = stock.get("volume", 0)
                    change = stock.get("pricePerChange", 0)
                    oi = stock.get("openInt", 0)
                    
                    if price == 0:
                        continue
                    
                    with self.lock:
                        self.price_history[name].append(price)
                        if volume > 0:
                            self.volume_history[name].append(volume)
                    
                    price_alert = self.check_price_movement(name, price)
                    if price_alert:
                        direction = price_alert["direction"]
                        change_pct = price_alert["change_pct"]
                        alerts_found.append({
                            "type": "price_movement",
                            "stock": name,
                            "message": f"{direction} {change_pct:.2f}%% (₹{price_alert['old_price']:.2f} → ₹{price:.2f})",
                            "price": price,
                            "change": change_pct
                        })
                    
                    if volume > 0 and self.check_volume_spike(name, volume):
                        alerts_found.append({
                            "type": "volume_spike",
                            "stock": name,
                            "message": f"📊 Volume spike: {volume:,.0f}",
                            "volume": volume
                        })
                
                if iteration % 5 == 0 or alerts_found or penny_stocks:
                    self.display_status(current_time, stocks, alerts_found, penny_stocks)
                
                time.sleep(self.check_interval)
                
            except Exception as e:
                print(f"❌ Error in monitor loop: {e}")
                time.sleep(self.check_interval)
    
    def display_status(self, current_time: str, stocks: List[Dict], 
                      alerts: List[Dict], penny_stocks: List[Dict]):
        os.system('clear' if os.name == 'posix' else 'cls')
        
        print("="*80)
        print(f"📊 STOCK MONITOR - {current_time}")
        print("="*80)
        
        if alerts:
            print("\n🚨 ALERTS:")
            for alert in alerts:
                print(f"  • {alert['stock']}: {alert['message']}")
            print("-"*80)
        
        sorted_by_change = sorted(stocks, key=lambda x: x.get("pricePerChange", 0), reverse=True)
        
        print("\n📈 TOP GAINERS:")
        for i, stock in enumerate(sorted_by_change[:5], 1):
            name = stock.get("name", "N/A")[:20]
            price = stock.get("price", 0)
            change = stock.get("pricePerChange", 0)
            vol = stock.get("volume", 0)
            print(f"  {i}. {name:20} ₹{price:>8.2f}  {change:>+6.2f}%  📊 {vol:>12,.0f}")
        
        print("\n📉 TOP LOSERS:")
        for i, stock in enumerate(sorted_by_change[-5:], 1):
            name = stock.get("name", "N/A")[:20]
            price = stock.get("price", 0)
            change = stock.get("pricePerChange", 0)
            vol = stock.get("volume", 0)
            print(f"  {i}. {name:20} ₹{price:>8.2f}  {change:>+6.2f}%  📊 {vol:>12,.0f}")
        
        if penny_stocks:
            print("\n🪙 PENNY STOCKS (Under ₹50):")
            for i, stock in enumerate(penny_stocks[:10], 1):
                print(f"  {i}. {stock['name']:20} ₹{stock['price']:>6.2f}  🔄 {stock['change']:>+5.2f}%  📊 {stock['volume']:>12,.0f}")
        
        total_volume = sum(s.get("volume", 0) for s in stocks)
        avg_price = sum(s.get("price", 0) for s in stocks) / len(stocks) if stocks else 0
        
        print("\n📊 MARKET STATS:")
        print(f"  Total Stocks: {len(stocks)}")
        print(f"  Total Volume: {total_volume:,.0f}")
        print(f"  Avg Price: ₹{avg_price:.2f}")
        print(f"  Penny Stocks: {len(penny_stocks)}")
        print("="*80)
        
        print(f"⏱️ Monitoring every {self.check_interval}s | Press Ctrl+C to stop")

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Real-time Stock Monitor')
    parser.add_argument('-i', '--interval', type=float, default=1.0,
                       help='Check interval in seconds (default: 1.0)')
    parser.add_argument('-p', '--penny', type=float, default=50.0,
                       help='Penny stock price threshold (default: 50)')
    parser.add_argument('-c', '--change', type=float, default=0.5,
                       help='Price change alert threshold (default: 0.5%%)')
    parser.add_argument('-v', '--volume', type=float, default=2.0,
                       help='Volume spike multiplier (default: 2.0x)')
    
    args = parser.parse_args()
    
    monitor = StockMonitor(check_interval=args.interval)
    monitor.penny_stock_threshold = args.penny
    monitor.price_change_threshold = args.change
    monitor.volume_spike_threshold = args.volume
    
    print("="*80)
    print("🚀 REAL-TIME STOCK MONITOR")
    print("="*80)
    print(f"⏱️ Interval: {args.interval}s")
    print(f"🪙 Penny Stock Threshold: ₹{args.penny}")
    print(f"📊 Price Change Alert: {args.change}%")
    print(f"📈 Volume Spike Alert: {args.volume}x average")
    print("="*80)
    
    try:
        monitor.monitor_loop()
    except KeyboardInterrupt:
        print("\n⏹️ Monitor stopped by user")

if __name__ == "__main__":
    main()
