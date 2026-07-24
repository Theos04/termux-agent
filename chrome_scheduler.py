#!/usr/bin/env python3
"""
Enhanced Chrome Session Scheduler with Full Logging
"""

import sys
import json
import time
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.syntax import Syntax
from rich import box

from celery import Celery
from celery.result import AsyncResult

from celery_config import app
from chrome_tasks import (
    start_chrome_session,
    stop_chrome_session,
    restart_chrome_session,
    execute_js_script,
    health_check_all_sessions,
    deepseek_send_message,
    list_all_sessions,
    get_session_info,
    take_screenshot
)

console = Console()
LOG_DIR = Path("/data/data/com.termux/files/home/automation/chrome-launcher/logs/task_outputs")

def show_task_result(task_id: str):
    """Show detailed task result"""
    result = AsyncResult(task_id, app=app)
    
    console.print()
    console.print(Panel(f"[bold cyan]Task Status: {task_id}[/bold cyan]", border_style="blue"))
    
    status_table = Table(box=box.ROUNDED)
    status_table.add_column("Property", style="cyan")
    status_table.add_column("Value", style="green")
    
    status_table.add_row("State", result.state)
    status_table.add_row("Ready", str(result.ready()))
    status_table.add_row("Successful", str(result.successful()) if result.ready() else "N/A")
    
    if result.ready():
        if result.successful():
            value = result.get(propagate=False)
            status_table.add_row("Result", "✅ Task completed successfully")
            
            # Show log file if present
            if isinstance(value, dict) and value.get('log_file'):
                log_file = value['log_file']
                status_table.add_row("Log File", f"[green]{log_file}[/green]")
                
                # Show log file content preview
                console.print()
                console.print("[bold cyan]Log Preview:[/bold cyan]")
                try:
                    with open(log_file, 'r') as f:
                        content = f.read(2000)
                        if len(content) < 2000:
                            console.print(Syntax(content, "json", theme="monokai"))
                        else:
                            console.print(Syntax(content[:2000] + "\n... (truncated)", "json", theme="monokai"))
                except Exception as e:
                    console.print(f"[red]Cannot read log file: {e}[/red]")
        else:
            status_table.add_row("Result", f"❌ Failed: {result.info}")
    else:
        status_table.add_row("Result", "⏳ Task in progress...")
    
    console.print(status_table)
    console.print()

def show_sessions():
    """Show all sessions with details"""
    from cdpv119 import ChromeSessionManager
    manager = ChromeSessionManager()
    manager.list_sessions()
    
    # Also show tracked info
    console.print()
    console.print("[bold cyan]📊 Tracked Session Info:[/bold cyan]")
    sessions = manager.db.list_sessions()
    for session in sessions:
        tracked = manager.session_tracker.get_session_info(session['id'])
        if tracked:
            ws_id = tracked.get('current_ws_id', 'None')
            status = tracked.get('status', 'unknown')
            status_icon = "🟢" if status == 'running' else "🟡" if status == 'error' else "⚪"
            console.print(f"  {status_icon} Session {session['id']} ({session['name']})")
            console.print(f"     WS ID: {ws_id}")
            console.print(f"     Starts: {tracked.get('starts', 0)}, Errors: {tracked.get('errors', 0)}")
            console.print(f"     Last Start: {tracked.get('last_start', 'Never')}")

def show_scheduled_tasks():
    """Show scheduled tasks from Celery Beat"""
    console.print()
    console.print(Panel("[bold cyan]📋 Scheduled Tasks (Celery Beat)[/bold cyan]", border_style="blue"))
    
    schedule = app.conf.beat_schedule
    if not schedule:
        console.print("[yellow]No scheduled tasks configured[/yellow]")
        return
    
    table = Table(box=box.ROUNDED)
    table.add_column("Task Name", style="cyan")
    table.add_column("Schedule", style="green")
    table.add_column("Options", style="yellow")
    
    for task_name, config in schedule.items():
        schedule_str = str(config.get('schedule', 'N/A'))
        options = str(config.get('options', {}))
        table.add_row(
            task_name,
            schedule_str,
            options
        )
    
    console.print(table)
    console.print()
    console.print("[dim]Scheduled tasks are executed automatically by Celery Beat[/dim]")
    console.print("[dim]Start Beat with: celery -A celery_config beat[/dim]")

def show_task_logs():
    """Show recent task logs"""
    log_files = sorted(LOG_DIR.glob("*.log"), key=lambda x: x.stat().st_mtime, reverse=True)
    
    if not log_files:
        console.print("[yellow]No task logs found[/yellow]")
        return
    
    console.print()
    console.print(Panel(f"[bold cyan]📝 Recent Task Logs ({len(log_files)} files)[/bold cyan]", border_style="blue"))
    
    table = Table(box=box.ROUNDED)
    table.add_column("#", style="cyan", width=4)
    table.add_column("File", style="green")
    table.add_column("Size", style="yellow")
    table.add_column("Modified", style="dim")
    
    for i, log_file in enumerate(log_files[:20], 1):
        size = log_file.stat().st_size
        size_str = f"{size / 1024:.1f} KB" if size > 1024 else f"{size} B"
        modified = datetime.fromtimestamp(log_file.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S')
        table.add_row(str(i), log_file.name, size_str, modified)
    
    console.print(table)
    console.print()
    
    choice = Prompt.ask("Enter log number to view (or 0 to cancel)", default="0")
    if choice and choice != "0":
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(log_files):
                log_file = log_files[idx]
                with open(log_file, 'r') as f:
                    content = f.read()
                    console.print()
                    console.print(Panel(f"[bold cyan]{log_file.name}[/bold cyan]", border_style="green"))
                    console.print(Syntax(content, "json" if log_file.suffix == '.json' else "text", theme="monokai"))
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")

def main():
    while True:
        console.clear()
        
        header = """
╔══════════════════════════════════════════════════════════════╗
║           🚀 Chrome Session Scheduler v2                    ║
║        Celery-Powered Automation with Full Logging         ║
╚══════════════════════════════════════════════════════════════╝
        """
        console.print(Panel(header, border_style="cyan"))
        
        # Show quick status
        try:
            from cdpv119 import ChromeSessionManager
            manager = ChromeSessionManager()
            sessions = manager.db.list_sessions()
            running = [s for s in sessions if s['status'] == 'running']
            console.print(f"[dim]Sessions: {len(sessions)} total, {len(running)} running[/dim]")
        except:
            pass
        
        console.print()
        
        menu = Table(show_header=False, box=box.MINIMAL_HEAVY_HEAD)
        menu.add_column("Option", style="cyan", width=10)
        menu.add_column("Action", style="green")
        menu.add_column("Description", style="dim")
        
        menu.add_row("1", "Start Session", "Start a Chrome session")
        menu.add_row("2", "Stop Session", "Stop a running Chrome session")
        menu.add_row("3", "Restart Session", "Restart a Chrome session")
        menu.add_row("4", "Execute Script", "Execute JavaScript on a session")
        menu.add_row("5", "DeepSeek Message", "Send a message on DeepSeek")
        menu.add_row("6", "Screenshot", "Take screenshot of a session")
        menu.add_row("7", "Health Check", "Check all running sessions")
        menu.add_row("8", "Task Status", "Check status of a scheduled task")
        menu.add_row("9", "List Sessions", "Show all sessions with details")
        menu.add_row("10", "Scheduled Tasks", "View scheduled tasks")
        menu.add_row("11", "Task Logs", "View recent task logs")
        menu.add_row("0", "Exit", "Exit the scheduler")
        
        console.print(menu)
        console.print()
        
        choice = Prompt.ask("Select option", choices=["0","1","2","3","4","5","6","7","8","9","10","11"])
        
        if choice == "0":
            console.print("[green]Goodbye! 👋[/green]")
            break
        
        elif choice == "1":
            session_id = int(Prompt.ask("Enter session ID to start"))
            result = start_chrome_session.delay(session_id)
            console.print(f"[green]✅ Task submitted: {result.id}[/green]")
            if Confirm.ask("Wait for result?"):
                show_task_result(result.id)
        
        elif choice == "2":
            session_id = int(Prompt.ask("Enter session ID to stop"))
            result = stop_chrome_session.delay(session_id)
            console.print(f"[green]✅ Task submitted: {result.id}[/green]")
            if Confirm.ask("Wait for result?"):
                show_task_result(result.id)
        
        elif choice == "3":
            session_id = int(Prompt.ask("Enter session ID to restart"))
            result = restart_chrome_session.delay(session_id)
            console.print(f"[green]✅ Task submitted: {result.id}[/green]")
            if Confirm.ask("Wait for result?"):
                show_task_result(result.id)
        
        elif choice == "4":
            session_id = int(Prompt.ask("Enter session ID"))
            script_id = Prompt.ask("Enter script ID (e.g., deepseek-writer/select-textarea-input.js)")
            result = execute_js_script.delay(session_id, script_id)
            console.print(f"[green]✅ Task submitted: {result.id}[/green]")
            if Confirm.ask("Wait for result?"):
                show_task_result(result.id)
        
        elif choice == "5":
            session_id = int(Prompt.ask("Enter session ID (or 0 to use first running)"))
            if session_id == 0:
                # Find first running session
                from cdpv119 import ChromeSessionManager
                manager = ChromeSessionManager()
                sessions = manager.db.list_sessions()
                running = [s for s in sessions if s['status'] == 'running']
                if running:
                    session_id = running[0]['id']
                    console.print(f"[green]Using session {session_id} ({running[0]['name']})[/green]")
                else:
                    console.print("[red]No running sessions found[/red]")
                    continue
            
            message = Prompt.ask("Enter message", default="Hello, how are you?")
            result = deepseek_send_message.delay(session_id, message)
            console.print(f"[green]✅ Task submitted: {result.id}[/green]")
            if Confirm.ask("Wait for result?"):
                show_task_result(result.id)
        
        elif choice == "6":
            session_id = int(Prompt.ask("Enter session ID"))
            result = take_screenshot.delay(session_id)
            console.print(f"[green]✅ Task submitted: {result.id}[/green]")
            if Confirm.ask("Wait for result?"):
                show_task_result(result.id)
        
        elif choice == "7":
            result = health_check_all_sessions.delay()
            console.print(f"[green]✅ Health check submitted: {result.id}[/green]")
            if Confirm.ask("Wait for result?"):
                show_task_result(result.id)
        
        elif choice == "8":
            task_id = Prompt.ask("Enter task ID")
            show_task_result(task_id)
        
        elif choice == "9":
            show_sessions()
        
        elif choice == "10":
            show_scheduled_tasks()
        
        elif choice == "11":
            show_task_logs()
        
        console.print()
        if choice not in ["0", "8", "9", "10", "11"]:
            Prompt.ask("Press Enter to continue...")

if __name__ == "__main__":
    main()
