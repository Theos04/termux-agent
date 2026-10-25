#!/usr/bin/env python3
"""
Standalone WhatsApp CDP Agent Daemon.

Runs on dedicated port (default 9223), polling unread chats and routing messages
through the READ -> WRITE -> ACTION -> ResponseComposer specialist trio.
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent.config import AgentConfig
from agent.database import Database
from agent.whatsapp import WhatsAppCDPClient, WhatsAppWorker
from agent.whatsapp.google_sheet_sync import GoogleSheetPharmacySync

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("whatsapp_agent")


def main():
    parser = argparse.ArgumentParser(description="WhatsApp CDP Agent Daemon")
    parser.add_argument("--port", type=int, default=None, help="WhatsApp CDP port (default 9223)")
    parser.add_argument("--poll-interval", type=float, default=5.0, help="Polling interval in seconds")
    parser.add_argument("--sync-sheets", action="store_true", help="Sync data from Google Sheets on start")
    parser.add_argument("--mock", action="store_true", help="Run with mock CDP client (no browser required)")
    args = parser.parse_args()

    cfg = AgentConfig()
    port = args.port or cfg.whatsapp_cdp_port
    db = Database(cfg.db_path)

    print("=" * 64)
    print("🤖 WhatsApp Pharmacy Trading Agent Daemon")
    print("=" * 64)
    print(f"🔌 Target CDP Port : {port} (Dedicated isolated port)")
    print(f"📁 Database        : {cfg.db_path}")
    print(f"⏱️  Poll Interval   : {args.poll_interval}s")
    print(f"🎭 Mode            : {'MOCK' if args.mock else 'LIVE CDP'}")
    print("=" * 64)

    if args.sync_sheets:
        print("\n📥 Synchronizing data from Google Sheets (gid: 1112889530)...")
        try:
            sync = GoogleSheetPharmacySync(db)
            res = sync.sync_all(product_limit=1000, party_limit=500)
            print(f"✓ Products synced  : {res.get('products_synced')}")
            print(f"✓ Retailers synced : {res.get('retailers_synced')}")
            print(f"✓ Suppliers synced : {res.get('suppliers_synced')}")
            print(f"✓ Batches synced   : {res.get('inventory_batches_synced')}")
        except Exception as exc:
            print(f"⚠️ Google Sheets sync warning: {exc}")

    cdp = WhatsAppCDPClient(port=port, mock_mode=args.mock)
    status = cdp.get_status()
    print(f"\nBrowser Status: {status.get('message', 'Active')}")
    if not status.get("browser_running") and not args.mock:
        print(f"💡 Note: Start WhatsApp Chrome with: python launch-whatsapp-chrome.py")

    worker = WhatsAppWorker(db=db, cdp_client=cdp, poll_interval=args.poll_interval)
    worker.start()

    stop_event = False

    def handle_sig(sig, frame):
        nonlocal stop_event
        print("\nGracefully stopping WhatsApp Agent...")
        stop_event = True
        worker.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_sig)
    signal.signal(signal.SIGTERM, handle_sig)

    print("\n🟢 WhatsApp Agent running. Press Ctrl+C to stop.")
    while not stop_event:
        time.sleep(1.0)


if __name__ == "__main__":
    main()
