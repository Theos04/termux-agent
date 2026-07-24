#!/usr/bin/env python3
# scheduler_cli.py
from simple_scheduler import ChromeScheduler
from cdpv117 import ChromeSessionManager
from datetime import datetime
import sys
import time

def main():
    print("\n" + "="*60)
    print("🔄 Chrome Session Scheduler (APScheduler)")
    print("="*60 + "\n")
    
    while True:
        print("\nOptions:")
        print("  1. Start session now")
        print("  2. Stop session now")
        print("  3. List all sessions")
        print("  4. Schedule session start")
        print("  5. Show scheduled jobs")
        print("  6. Start scheduler daemon")
        print("  0. Exit")
        
        choice = input("\nSelect option: ").strip()
        
        if choice == "0":
            print("Goodbye! 👋")
            break
            
        elif choice == "1":
            session_id = int(input("Enter session ID: "))
            manager = ChromeSessionManager()
            manager.start_session(session_id)
            
        elif choice == "2":
            session_id = int(input("Enter session ID: "))
            manager = ChromeSessionManager()
            manager.stop_session(session_id)
            
        elif choice == "3":
            manager = ChromeSessionManager()
            manager.list_sessions()
            
        elif choice == "4":
            session_id = int(input("Enter session ID: "))
            print("Schedule time (24-hour format):")
            hour = int(input("  Hour (0-23): "))
            minute = int(input("  Minute (0-59): "))
            
            scheduler = ChromeScheduler()
            scheduler.add_schedule(session_id, hour, minute)
            print(f"✅ Scheduled session {session_id} at {hour:02d}:{minute:02d}")
            
        elif choice == "5":
            scheduler = ChromeScheduler()
            scheduler.print_jobs()
            
        elif choice == "6":
            print("Starting scheduler daemon (Ctrl+C to stop)...")
            scheduler = ChromeScheduler()
            scheduler.start()

if __name__ == "__main__":
    main()
