#!/usr/bin/env python3
# scheduler_cli.py - Simple CLI for scheduler
from cdpv117 import ChromeSessionManager
import os
import sys

def main():
    print("\n" + "="*60)
    print("🔄 Chrome Session Manager - Simple CLI")
    print("="*60 + "\n")
    
    manager = None
    
    while True:
        print("\nOptions:")
        print("  1. Start session now")
        print("  2. Stop session now")
        print("  3. List all sessions")
        print("  4. Session details")
        print("  5. Dashboard")
        print("  6. Start scheduler (runs in background)")
        print("  0. Exit")
        
        choice = input("\nSelect option: ").strip()
        
        if choice == "0":
            print("Goodbye! 👋")
            break
            
        elif choice == "1":
            if not manager:
                manager = ChromeSessionManager()
            session_id = int(input("Enter session ID: "))
            manager.start_session(session_id)
            
        elif choice == "2":
            if not manager:
                manager = ChromeSessionManager()
            session_id = int(input("Enter session ID: "))
            manager.stop_session(session_id)
            
        elif choice == "3":
            if not manager:
                manager = ChromeSessionManager()
            manager.list_sessions()
            
        elif choice == "4":
            if not manager:
                manager = ChromeSessionManager()
            session_id = int(input("Enter session ID: "))
            manager.show_session_details(session_id)
            
        elif choice == "5":
            if not manager:
                manager = ChromeSessionManager()
            manager.show_dashboard()
            
        elif choice == "6":
            print("Starting scheduler (Ctrl+C to stop)...")
            os.system("python3 simple_scheduler.py")

if __name__ == "__main__":
    main()

