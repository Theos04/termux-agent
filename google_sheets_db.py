# google_sheets_db.py
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
from datetime import datetime
import logging
from typing import Optional, Dict, List, Any
from dataclasses import dataclass
import os
import sys
import base64
from pathlib import Path

# Rich imports for TUI
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.layout import Layout
from rich.columns import Columns
from rich.text import Text
from rich.markdown import Markdown
from rich import box
from rich.live import Live
from rich.tree import Tree
from rich.syntax import Syntax
import time

console = Console()

logger = logging.getLogger(__name__)

# ==================== Configuration Classes ====================

@dataclass
class SheetConfig:
    """Configuration for a Google Sheet"""
    sheet_id: str
    sheet_name: str
    credentials_file: str = 'client_secret_myagent.json'

    def __hash__(self):
        return hash(self.sheet_id)


@dataclass
class TabConfig:
    """Configuration for a tab (worksheet) within a sheet"""
    tab_name: str
    headers: Optional[List[str]] = None
    description: Optional[str] = None
    use_existing_headers: bool = True

    def __hash__(self):
        return hash(self.tab_name)


# ==================== Database Registry ====================

class DatabaseRegistry:
    """Registry for all sheet and tab configurations"""

    # Default sheet ID (can be overridden)
    DEFAULT_SHEET_ID = '1BYBAjhZ4Z1s02qkuHnWmM5UxfFKTeGIVdlJdHU7xgm0'
    DEFAULT_CREDENTIALS_FILE = 'client_secret_myagent.json'

    # Tab definitions with headers
    TABS = {
        # System tabs
        'tasks_log': TabConfig(
            'tasks_log',
            ['timestamp', 'task_id', 'task_name', 'status', 'result', 'error'],
            '📋 Log of all celery tasks'
        ),
        'chrome_sessions': TabConfig(
            'chrome_sessions',
            ['session_id', 'name', 'url', 'status', 'pid', 'timestamp', 'data'],
            '🌐 Chrome browser sessions'
        ),
        'task_queue': TabConfig(
            'task_queue',
            ['id', 'task_name', 'params', 'status', 'created_at', 'updated_at'],
            '📊 Pending task queue'
        ),
        'automation_results': TabConfig(
            'automation_results',
            ['timestamp', 'automation_id', 'data', 'status'],
            '🤖 Automation results'
        ),

        # New tabs for session data
        'page_data': TabConfig(
            'page_data',
            ['session_id', 'url', 'title', 'content', 'html', 'captured_at'],
            '📄 Captured page data and HTML'
        ),
        'extracted_data': TabConfig(
            'extracted_data',
            ['session_id', 'data_key', 'data_value', 'data_type', 'captured_at'],
            '🔍 Extracted data from JavaScript evaluations'
        ),
        'screenshots': TabConfig(
            'screenshots',
            ['session_id', 'filename', 'path', 'captured_at'],
            '📸 Screenshots captured during sessions'
        ),

        # Jobs database
        'naukri': TabConfig(
            'naukri',
            ['id', 'title', 'company', 'location', 'salary', 'url', 'posted_date', 'status', 'applied_date', 'notes'],
            '💼 Naukri.com job postings'
        ),
        'unstop_jobs': TabConfig(
            'unstop_jobs',
            ['id', 'title', 'company', 'location', 'type', 'url', 'deadline', 'status', 'applied_date', 'notes'],
            '💼 Unstop job opportunities'
        ),
        'indeed': TabConfig(
            'indeed',
            ['id', 'title', 'company', 'location', 'salary', 'url', 'posted_date', 'status', 'applied_date', 'notes'],
            '💼 Indeed.com job postings'
        ),
        'linkedin_jobs': TabConfig(
            'linkedin_jobs',
            ['id', 'title', 'company', 'location', 'salary', 'url', 'posted_date', 'status', 'applied_date', 'notes'],
            '💼 LinkedIn job postings'
        ),
        'internshala': TabConfig(
            'internshala',
            ['id', 'title', 'company', 'location', 'stipend', 'url', 'posted_date', 'status', 'applied_date', 'notes'],
            '💼 Internshala internships and jobs'
        ),

        # Hackathons database
        'unstop_hackathons': TabConfig(
            'unstop_hackathons',
            ['id', 'name', 'organizer', 'mode', 'prize', 'url', 'start_date', 'end_date', 'status', 'registered', 'notes'],
            '🏆 Unstop hackathons'
        ),
        'devfolio': TabConfig(
            'devfolio',
            ['id', 'name', 'organizer', 'mode', 'prize', 'url', 'start_date', 'end_date', 'status', 'registered', 'notes'],
            '🏆 Devfolio hackathons'
        ),
        'hackerearth': TabConfig(
            'hackerearth',
            ['id', 'name', 'organizer', 'mode', 'prize', 'url', 'start_date', 'end_date', 'status', 'registered', 'notes'],
            '🏆 HackerEarth hackathons'
        ),
        'hack2skill': TabConfig(
            'hack2skill',
            ['id', 'name', 'organizer', 'mode', 'prize', 'url', 'start_date', 'end_date', 'status', 'registered', 'notes'],
            '🏆 Hack2Skill hackathons'
        ),

        # Events database
        'meetups': TabConfig(
            'meetups',
            ['id', 'name', 'organizer', 'type', 'url', 'date', 'location', 'status', 'attended', 'notes'],
            '📅 Tech meetups and events'
        ),
        'webinars': TabConfig(
            'webinars',
            ['id', 'name', 'organizer', 'platform', 'url', 'date', 'time', 'status', 'attended', 'notes'],
            '💻 Webinars and online events'
        ),

        # Scholarships database
        'national_scholarships': TabConfig(
            'national_scholarships',
            ['id', 'name', 'provider', 'amount', 'url', 'deadline', 'eligibility', 'status', 'applied', 'notes'],
            '🎓 National scholarships'
        ),
        'international_scholarships': TabConfig(
            'international_scholarships',
            ['id', 'name', 'provider', 'amount', 'url', 'deadline', 'eligibility', 'status', 'applied', 'notes'],
            '🌍 International scholarships'
        ),
    }

    @classmethod
    def get_tab_config(cls, tab_name: str) -> Optional[TabConfig]:
        """Get tab configuration by name"""
        return cls.TABS.get(tab_name)

    @classmethod
    def get_all_tabs(cls) -> Dict[str, TabConfig]:
        """Get all tabs"""
        return cls.TABS

    @classmethod
    def get_headers(cls, tab_name: str) -> Optional[List[str]]:
        """Get headers for a tab"""
        config = cls.get_tab_config(tab_name)
        return config.headers if config else None

    @classmethod
    def get_tabs_by_category(cls) -> Dict[str, List[Dict]]:
        """Group tabs by category for display"""
        categories = {}
        for tab_name, config in cls.TABS.items():
            # Determine category from tab name
            if tab_name in ['tasks_log', 'chrome_sessions', 'task_queue', 'automation_results']:
                category = 'System'
            elif tab_name in ['page_data', 'extracted_data', 'screenshots']:
                category = 'Session Data'
            elif 'jobs' in tab_name or tab_name in ['naukri', 'indeed', 'linkedin_jobs', 'internshala']:
                category = 'Jobs'
            elif 'hackathon' in tab_name or tab_name in ['devfolio', 'hackerearth', 'hack2skill']:
                category = 'Hackathons'
            elif tab_name in ['meetups', 'webinars']:
                category = 'Events'
            elif 'scholarship' in tab_name:
                category = 'Scholarships'
            else:
                category = 'Other'

            if category not in categories:
                categories[category] = []
            categories[category].append({
                'name': tab_name,
                'config': config,
                'display_name': tab_name.replace('_', ' ').title()
            })

        return categories


# ==================== Rich TUI Helpers ====================

class RichTUI:
    """Rich Text User Interface helpers"""

    @staticmethod
    def show_header():
        """Display application header"""
        header = Panel(
            "[bold cyan]Google Sheets Database Manager[/bold cyan]\n"
            "[dim]Multi-tab, multi-sheet database with Rich TUI[/dim]",
            box=box.ROUNDED,
            border_style="cyan"
        )
        console.print(header)
        console.print()

    @staticmethod
    def show_sheet_info(sheet_id: str, service_email: str):
        """Display sheet information"""
        info = Panel(
            f"[bold]Sheet ID:[/bold] {sheet_id}\n"
            f"[bold]Service Account:[/bold] {service_email}\n\n"
            f"[yellow]⚠️  IMPORTANT:[/yellow] Share your sheet with the service account email above",
            title="📊 Sheet Information",
            border_style="green",
            box=box.ROUNDED
        )
        console.print(info)
        console.print()

    @staticmethod
    def show_tabs_browser(tabs_data: Dict[str, List[Dict]]):
        """Display tabs in a browsable tree format"""
        tree = Tree("[bold cyan]📋 Available Tabs[/bold cyan]")

        for category, tabs in tabs_data.items():
            category_tree = tree.add(f"[bold yellow]{category}[/bold yellow] ({len(tabs)})")
            for tab in tabs:
                config = tab['config']
                tab_text = f"[green]{tab['display_name']}[/green]"
                if config.description:
                    tab_text += f" [dim]- {config.description}[/dim]"
                if config.headers:
                    tab_text += f"\n    [dim]Headers: {', '.join(config.headers[:5])}{'...' if len(config.headers) > 5 else ''}[/dim]"
                category_tree.add(tab_text)

        console.print(tree)
        console.print()

    @staticmethod
    def show_data_table(data: List[Dict[str, Any]], title: str = "Data", max_rows: int = 20):
        """Display data in a rich table"""
        if not data:
            console.print("[yellow]No data available[/yellow]")
            return

        # Create table
        table = Table(title=f"📊 {title} ({len(data)} rows)", box=box.ROUNDED)

        # Get headers from first row
        headers = list(data[0].keys())
        for header in headers:
            table.add_column(header, style="cyan", no_wrap=True, overflow="ellipsis")

        # Add rows (limited)
        for row in data[:max_rows]:
            row_data = []
            for header in headers:
                value = str(row.get(header, ''))
                # Truncate long values
                if len(value) > 50:
                    value = value[:47] + "..."
                row_data.append(value)
            table.add_row(*row_data)

        if len(data) > max_rows:
            table.add_row(*["..." for _ in headers], style="dim")
            table.caption = f"Showing {max_rows} of {len(data)} rows"

        console.print(table)
        console.print()

    @staticmethod
    def show_success(message: str):
        """Show success message"""
        console.print(f"[bold green]✅ {message}[/bold green]")

    @staticmethod
    def show_error(message: str):
        """Show error message"""
        console.print(f"[bold red]❌ {message}[/bold red]")

    @staticmethod
    def show_info(message: str):
        """Show info message"""
        console.print(f"[bold blue]ℹ️  {message}[/bold blue]")

    @staticmethod
    def show_warning(message: str):
        """Show warning message"""
        console.print(f"[bold yellow]⚠️  {message}[/bold yellow]")

    @staticmethod
    def show_progress(message: str, duration: float = 1.0):
        """Show progress spinner"""
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
        ) as progress:
            task = progress.add_task(f"[cyan]{message}...", total=None)
            time.sleep(duration)
            progress.update(task, completed=True)

    @staticmethod
    def show_menu():
        """Display main menu"""
        menu = Panel(
            "[bold cyan]Main Menu[/bold cyan]\n\n"
            "[1] 📊 View all tabs\n"
            "[2] 📝 View tab data\n"
            "[3] ➕ Add record\n"
            "[4] 🔍 Search records\n"
            "[5] 📈 View statistics\n"
            "[6] 🗑️  Delete record\n"
            "[7] 🔄 Refresh data\n"
            "[8] 🚪 Exit\n",
            box=box.ROUNDED,
            border_style="blue"
        )
        console.print(menu)


# ==================== Main Database Class ====================

class GoogleSheetsDB:
    """Main database interface with multi-sheet and multi-tab support"""

    def __init__(self,
                 sheet_id: Optional[str] = None,
                 credentials_file: Optional[str] = None,
                 interactive: bool = True,
                 data_dir: Optional[str] = None):
        """
        Initialize database connection

        Args:
            sheet_id: Google Sheet ID (will prompt if not provided and interactive=True)
            credentials_file: Path to Google service account credentials
            interactive: If True, prompt for missing information
            data_dir: Directory to store screenshots and other data
        """
        self.tui = RichTUI()
        self.credentials_file = credentials_file or DatabaseRegistry.DEFAULT_CREDENTIALS_FILE
        self.interactive = interactive

        # Setup data directories
        if data_dir:
            self.data_dir = Path(data_dir)
        else:
            self.data_dir = Path.cwd() / 'data'
        
        self.screenshots_dir = self.data_dir / 'screenshots'
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"📁 Screenshots directory: {self.screenshots_dir}")

        # Check if credentials file exists
        if not os.path.exists(self.credentials_file):
            console.print(f"\n[red]❌ Credentials file not found: {self.credentials_file}[/red]")
            console.print("[yellow]Please ensure you have the service account credentials file.[/yellow]")
            if interactive:
                if Confirm.ask("Do you want to specify a different credentials file?"):
                    new_file = Prompt.ask("Enter credentials file path")
                    if os.path.exists(new_file):
                        self.credentials_file = new_file
                    else:
                        console.print(f"[red]❌ File not found: {new_file}[/red]")
                        sys.exit(1)
                else:
                    console.print("\n[yellow]Please download the credentials file from Google Cloud Console.[/yellow]")
                    console.print("Save it as 'client_secret_myagent.json' in the current directory.")
                    sys.exit(1)

        # Get sheet ID
        if sheet_id:
            self.sheet_id = sheet_id
        elif interactive:
            self.sheet_id = self._prompt_sheet_id()
        else:
            self.sheet_id = DatabaseRegistry.DEFAULT_SHEET_ID

        self.client = None
        self._sheet_cache = None
        self._worksheet_cache = {}
        self._header_cache = {}
        self._connect()

    def _prompt_sheet_id(self) -> str:
        """Prompt user for sheet ID with rich UI"""
        console.print("\n[bold cyan]Google Sheets Database Configuration[/bold cyan]")
        console.print("[dim]You can find your Google Sheet ID in the URL:[/dim]")
        console.print("[dim]https://docs.google.com/spreadsheets/d/YOUR_SHEET_ID/edit[/dim]")
        console.print(f"\n[dim]Example: {DatabaseRegistry.DEFAULT_SHEET_ID}[/dim]")

        # Show current sheet ID if already shared
        console.print(f"\n[cyan]Default sheet ID:[/cyan] {DatabaseRegistry.DEFAULT_SHEET_ID}")

        sheet_id = Prompt.ask("\nEnter Google Sheet ID", default=DatabaseRegistry.DEFAULT_SHEET_ID)

        console.print(f"\n[green]✅ Using sheet ID:[/green] {sheet_id}")
        return sheet_id

    def _prompt_tab_headers(self, tab_name: str) -> List[str]:
        """Prompt user for tab headers with rich UI"""
        console.print(f"\n[cyan]📋 Tab '{tab_name}' not found in configuration.[/cyan]")

        choice = Prompt.ask(
            "Would you like to",
            choices=["1", "2", "3"],
            default="1"
        )

        if choice == '1':
            return None  # Will read from sheet
        elif choice == '2':
            headers_input = Prompt.ask("\nEnter headers separated by commas")
            return [h.strip() for h in headers_input.split(',') if h.strip()]
        else:
            return []

    def _connect(self):
        """Connect to Google Sheets API"""
        try:
            # Check if credentials file exists
            if not os.path.exists(self.credentials_file):
                console.print(f"\n[red]❌ Credentials file not found: {self.credentials_file}[/red]")
                raise FileNotFoundError(f"Credentials file not found: {self.credentials_file}")

            # Load credentials with progress
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                transient=True,
            ) as progress:
                task = progress.add_task("[cyan]Connecting to Google Sheets...", total=None)

                scope = [
                    'https://spreadsheets.google.com/feeds',
                    'https://www.googleapis.com/auth/drive',
                    'https://www.googleapis.com/auth/spreadsheets'
                ]
                creds = ServiceAccountCredentials.from_json_keyfile_name(
                    self.credentials_file, scope
                )
                self.client = gspread.authorize(creds)
                progress.update(task, completed=True)

            console.print("[green]✅ Connected to Google Sheets API[/green]")

            # Test connection
            self.get_sheet()
            console.print(f"[green]✅ Successfully opened sheet:[/green] {self.sheet_id}")

            # Get the service account email for sharing
            with open(self.credentials_file, 'r') as f:
                creds_data = json.load(f)
                service_email = creds_data.get('client_email', '')

            # Show sheet info with sharing instructions
            self.tui.show_sheet_info(self.sheet_id, service_email)

        except Exception as e:
            console.print(f"[red]❌ Failed to connect to Google Sheets: {e}[/red]")
            raise

    def get_sheet(self) -> gspread.Spreadsheet:
        """Get the spreadsheet (with caching)"""
        if self._sheet_cache is None:
            try:
                self._sheet_cache = self.client.open_by_key(self.sheet_id)
                logger.info(f"📊 Opened sheet: {self.sheet_id}")
            except Exception as e:
                console.print(f"[red]❌ Failed to open sheet. Make sure:[/red]")
                console.print("   1. The sheet ID is correct")
                console.print("   2. The sheet is shared with your service account")
                console.print("   3. You have internet connection")
                raise
        return self._sheet_cache

    def get_worksheet(self,
                      tab_name: str,
                      headers: Optional[List[str]] = None,
                      auto_create: bool = True) -> gspread.Worksheet:
        """
        Get or create a worksheet by name with caching
        """
        # Check cache
        cache_key = tab_name
        if cache_key in self._worksheet_cache:
            return self._worksheet_cache[cache_key]

        sheet = self.get_sheet()

        try:
            # Try to get existing worksheet
            ws = sheet.worksheet(tab_name)
            logger.info(f"📋 Found worksheet: {tab_name}")

            # Get headers from the sheet
            if headers is None:
                headers = self._get_headers_from_sheet(ws)

            self._worksheet_cache[cache_key] = ws
            return ws

        except gspread.exceptions.WorksheetNotFound:
            if not auto_create:
                raise ValueError(f"Worksheet '{tab_name}' not found and auto_create is disabled")

            console.print(f"\n[yellow]⚠️  Worksheet '{tab_name}' not found. Creating new worksheet...[/yellow]")

            # Get headers
            if headers is None:
                # Try to get headers from config
                config_headers = DatabaseRegistry.get_headers(tab_name)
                if config_headers:
                    headers = config_headers
                    console.print(f"[dim]📋 Using configured headers: {', '.join(headers)}[/dim]")
                elif self.interactive:
                    headers = self._prompt_tab_headers(tab_name)
                else:
                    headers = ['id', 'data', 'timestamp']

            # Create worksheet
            try:
                ws = sheet.add_worksheet(title=tab_name, rows=1000, cols=max(len(headers or []), 20))
                if headers:
                    ws.append_row(headers)
                    logger.info(f"✅ Created worksheet: {tab_name} with {len(headers)} headers")
                    console.print(f"[green]✅ Created worksheet: {tab_name} with {len(headers)} headers[/green]")
                else:
                    logger.info(f"✅ Created worksheet: {tab_name}")
                    console.print(f"[green]✅ Created worksheet: {tab_name}[/green]")

                self._worksheet_cache[cache_key] = ws
                return ws

            except Exception as e:
                console.print(f"[red]❌ Failed to create worksheet {tab_name}: {e}[/red]")
                raise

    def _get_headers_from_sheet(self, ws: Optional[gspread.Worksheet] = None) -> List[str]:
        """Get headers from existing sheet or prompt user"""
        if ws:
            try:
                # Get first row as headers
                headers_row = ws.row_values(1)
                if headers_row:
                    logger.info(f"📋 Found headers in sheet: {headers_row}")
                    return headers_row
            except:
                pass

        if self.interactive:
            headers_input = Prompt.ask("Enter headers separated by commas", default="id,title,company,timestamp")
            return [h.strip() for h in headers_input.split(',') if h.strip()]

        # Default headers
        return ['id', 'data', 'timestamp']

    def get_headers(self, tab_name: str) -> List[str]:
        """Get headers for a tab"""
        if tab_name in self._header_cache:
            return self._header_cache[tab_name]

        try:
            ws = self.get_worksheet(tab_name, auto_create=False)
            headers = ws.row_values(1)
            self._header_cache[tab_name] = headers
            return headers
        except:
            # If tab doesn't exist, get from config
            headers = DatabaseRegistry.get_headers(tab_name) or ['id', 'data', 'timestamp']
            self._header_cache[tab_name] = headers
            return headers

    # ==================== Generic CRUD Operations ====================

    def insert_row(self,
                   tab_name: str,
                   data: Dict[str, Any]) -> Dict[str, Any]:
        """Insert a row into any tab"""
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
        ) as progress:
            task = progress.add_task(f"[cyan]Inserting into {tab_name}...", total=None)

            ws = self.get_worksheet(tab_name)

            # Get headers to ensure correct order
            headers = self.get_headers(tab_name)

            # Prepare row data in header order
            row_data = []
            for header in headers:
                row_data.append(str(data.get(header, '')))

            ws.append_row(row_data)
            progress.update(task, completed=True)

        logger.info(f"✅ Inserted row into {tab_name}")
        return {'success': True, 'tab': tab_name, 'data': data}

    def get_all_rows(self,
                     tab_name: str) -> List[Dict[str, Any]]:
        """Get all rows from a tab"""
        ws = self.get_worksheet(tab_name)
        try:
            records = ws.get_all_records()
            return records
        except Exception as e:
            logger.error(f"Error fetching rows from {tab_name}: {e}")
            return []

    def find_rows(self,
                  tab_name: str,
                  column: str,
                  value: Any) -> List[Dict[str, Any]]:
        """Find rows by column value"""
        records = self.get_all_rows(tab_name)
        return [r for r in records if r.get(column) == value]

    def update_row(self,
                   tab_name: str,
                   row_index: int,
                   data: Dict[str, Any]) -> Dict[str, Any]:
        """Update a specific row by index"""
        ws = self.get_worksheet(tab_name)
        headers = self.get_headers(tab_name)

        # Prepare row data in header order
        row_data = []
        for header in headers:
            row_data.append(str(data.get(header, '')))

        # Update the row (row_index is 0-based, +2 for header)
        actual_row = row_index + 2
        col_letter = chr(65 + len(headers) - 1)
        ws.update(f'A{actual_row}:{col_letter}{actual_row}', [row_data])

        logger.info(f"✅ Updated row {row_index} in {tab_name}")
        return {'success': True, 'row': row_index, 'data': data}

    def delete_row(self, tab_name: str, row_index: int) -> Dict[str, Any]:
        """Delete a row by index"""
        ws = self.get_worksheet(tab_name)
        actual_row = row_index + 2  # +2 for header
        ws.delete_rows(actual_row)
        logger.info(f"✅ Deleted row {row_index} from {tab_name}")
        return {'success': True, 'row': row_index}

    def get_record_count(self, tab_name: str) -> int:
        """Get number of records in a tab"""
        try:
            ws = self.get_worksheet(tab_name, auto_create=False)
            records = ws.get_all_records()
            return len(records)
        except:
            return 0

    def get_all_tabs_info(self) -> Dict[str, Dict]:
        """Get information about all tabs"""
        info = {}
        for tab_name in DatabaseRegistry.get_all_tabs().keys():
            try:
                count = self.get_record_count(tab_name)
                headers = self.get_headers(tab_name)
                info[tab_name] = {
                    'count': count,
                    'headers': headers,
                    'exists': True
                }
            except:
                info[tab_name] = {
                    'count': 0,
                    'headers': DatabaseRegistry.get_headers(tab_name) or [],
                    'exists': False
                }
        return info

    # ==================== Session Data Methods ====================

    def get_session_data(self, session_name: str) -> Dict:
        """
        Get all data for a specific session across all tabs
        This is a convenience method that aggregates data from multiple tabs
        """
        session_data = {
            'pages': [],
            'extracted': [],
            'screenshots': [],
            'automation': [],
            'tasks': []
        }
        
        try:
            # Get data from page_data tab
            try:
                records = self.get_all_rows('page_data')
                session_data['pages'] = [r for r in records if r.get('session_id') == session_name]
            except:
                pass
            
            # Get data from extracted_data tab
            try:
                records = self.get_all_rows('extracted_data')
                session_data['extracted'] = [r for r in records if r.get('session_id') == session_name]
            except:
                pass
            
            # Get data from screenshots tab
            try:
                records = self.get_all_rows('screenshots')
                session_data['screenshots'] = [r for r in records if r.get('session_id') == session_name]
            except:
                pass
            
            # Get data from automation_results tab
            try:
                records = self.get_all_rows('automation_results')
                session_data['automation'] = [r for r in records if r.get('automation_id', '').startswith(session_name)]
            except:
                pass
            
            # Get data from tasks_log tab
            try:
                records = self.get_all_rows('tasks_log')
                session_data['tasks'] = [r for r in records if session_name in r.get('task_name', '')]
            except:
                pass
            
            return session_data
            
        except Exception as e:
            logger.error(f"Error getting session data: {e}")
            return session_data

    def get_extracted_data_by_key(self, session_name: str, key: str) -> Optional[Dict]:
        """
        Get specific extracted data by key
        """
        try:
            records = self.get_all_rows('extracted_data')
            for record in records:
                if record.get('session_id') == session_name and record.get('data_key') == key:
                    return {
                        'value': record.get('data_value'),
                        'type': record.get('data_type', 'string'),
                        'captured_at': record.get('captured_at')
                    }
            return None
        except Exception as e:
            logger.error(f"Error getting extracted data: {e}")
            return None

    def save_extracted_data(self, session_name: str, key: str, value: Any, data_type: str = 'json') -> Dict:
        """
        Save extracted data from JavaScript evaluations
        """
        try:
            # Convert value to string if needed
            if isinstance(value, (dict, list)):
                value_str = json.dumps(value)
                data_type = 'json'
            elif isinstance(value, str):
                value_str = value
                data_type = 'string'
            else:
                value_str = str(value)
                data_type = 'string'
            
            data = {
                'session_id': session_name,
                'data_key': key,
                'data_value': value_str,
                'data_type': data_type,
                'captured_at': datetime.now().isoformat()
            }
            
            return self.insert_row('extracted_data', data)
            
        except Exception as e:
            logger.error(f"Error saving extracted data: {e}")
            return {'success': False, 'error': str(e)}

    def save_screenshot(self, session_name: str, screenshot_data: str, filename: Optional[str] = None) -> Dict:
        """
        Save screenshot and record metadata
        """
        try:
            if not filename:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f"{session_name}_{timestamp}.png"
            
            # Save the screenshot (assuming base64 data)
            if screenshot_data.startswith('data:image/png;base64,'):
                screenshot_data = screenshot_data.split(',')[1]
            
            filepath = self.screenshots_dir / filename
            with open(filepath, 'wb') as f:
                f.write(base64.b64decode(screenshot_data))
            
            data = {
                'session_id': session_name,
                'filename': filename,
                'path': str(filepath),
                'captured_at': datetime.now().isoformat()
            }
            
            return self.insert_row('screenshots', data)
            
        except Exception as e:
            logger.error(f"Error saving screenshot: {e}")
            return {'success': False, 'error': str(e)}

    def save_page_data(self, session_name: str, url: str, title: str, html_content: str, raw_data: Any = None) -> Dict:
        """
        Save page HTML and extracted content
        """
        try:
            data = {
                'session_id': session_name,
                'url': url,
                'title': title,
                'content': json.dumps(raw_data) if raw_data else '',
                'html': html_content,
                'captured_at': datetime.now().isoformat()
            }
            
            return self.insert_row('page_data', data)
            
        except Exception as e:
            logger.error(f"Error saving page data: {e}")
            return {'success': False, 'error': str(e)}

    # ==================== Convenience Methods ====================

    def add_job(self, platform: str, job_data: Dict[str, Any]) -> Dict[str, Any]:
        """Add a job to the specified platform"""
        tab_name = f"{platform}_jobs" if platform not in ['naukri', 'unstop'] else platform if platform == 'naukri' else 'unstop_jobs'
        return self.insert_row(tab_name, job_data)

    def get_jobs(self, platform: str) -> List[Dict[str, Any]]:
        """Get all jobs from a platform"""
        tab_name = f"{platform}_jobs" if platform not in ['naukri', 'unstop'] else platform if platform == 'naukri' else 'unstop_jobs'
        return self.get_all_rows(tab_name)

    def add_hackathon(self, platform: str, hackathon_data: Dict[str, Any]) -> Dict[str, Any]:
        """Add a hackathon to the specified platform"""
        tab_name = f"{platform}_hackathons" if platform != 'unstop' else 'unstop_hackathons'
        return self.insert_row(tab_name, hackathon_data)

    def get_hackathons(self, platform: str) -> List[Dict[str, Any]]:
        """Get all hackathons from a platform"""
        tab_name = f"{platform}_hackathons" if platform != 'unstop' else 'unstop_hackathons'
        return self.get_all_rows(tab_name)

    def log_task(self, task_id: str, task_name: str, status: str,
                 result: Any = None, error: str = None) -> None:
        """Log task result to tasks_log"""
        data = {
            'timestamp': datetime.now().isoformat(),
            'task_id': task_id,
            'task_name': task_name,
            'status': status,
            'result': json.dumps(result) if result else '',
            'error': str(error) if error else ''
        }
        self.insert_row('tasks_log', data)


# ==================== Interactive Menu System ====================

class InteractiveMenu:
    """Interactive menu system with Rich TUI"""

    def __init__(self, db: GoogleSheetsDB):
        self.db = db
        self.tui = RichTUI()
        self.running = True

    def run(self):
        """Run the interactive menu"""
        self.tui.show_header()

        while self.running:
            self.tui.show_menu()
            choice = Prompt.ask(
                "Select an option",
                choices=["1", "2", "3", "4", "5", "6", "7", "8"],
                default="1"
            )

            if choice == "1":
                self.view_all_tabs()
            elif choice == "2":
                self.view_tab_data()
            elif choice == "3":
                self.add_record()
            elif choice == "4":
                self.search_records()
            elif choice == "5":
                self.view_statistics()
            elif choice == "6":
                self.delete_record()
            elif choice == "7":
                self.refresh_data()
            elif choice == "8":
                self.exit_app()

            if self.running:
                console.print("\n[dim]Press Enter to continue...[/dim]")
                input()

    def view_all_tabs(self):
        """View all tabs in the database"""
        console.clear()
        self.tui.show_header()

        tabs_data = DatabaseRegistry.get_tabs_by_category()
        self.tui.show_tabs_browser(tabs_data)

        # Show tab statistics
        console.print("\n[bold cyan]📊 Tab Statistics[/bold cyan]")
        info = self.db.get_all_tabs_info()
        table = Table(box=box.MINIMAL)
        table.add_column("Tab", style="cyan")
        table.add_column("Records", style="green", justify="right")
        table.add_column("Headers", style="dim")
        table.add_column("Status", style="yellow")

        for tab_name, data in info.items():
            status = "✅" if data['exists'] else "❌ Not created"
            headers_str = ', '.join(data['headers'][:3])
            if len(data['headers']) > 3:
                headers_str += "..."
            table.add_row(
                tab_name.replace('_', ' ').title(),
                str(data['count']),
                headers_str,
                status
            )

        console.print(table)

    def view_tab_data(self):
        """View data from a specific tab"""
        console.clear()
        self.tui.show_header()

        # Get all tab names
        tabs = list(DatabaseRegistry.get_all_tabs().keys())

        console.print("[bold cyan]📋 Select a tab to view[/bold cyan]")
        for i, tab in enumerate(tabs, 1):
            config = DatabaseRegistry.get_tab_config(tab)
            desc = f" - {config.description}" if config and config.description else ""
            console.print(f"  [cyan]{i}.[/cyan] {tab.replace('_', ' ').title()}{desc}")
        console.print("  [dim]0. Back to menu[/dim]")

        choice = Prompt.ask("Select tab", default="0")

        if choice == "0":
            return

        try:
            idx = int(choice) - 1
            if 0 <= idx < len(tabs):
                tab_name = tabs[idx]
                console.print(f"\n[bold cyan]📊 {tab_name.replace('_', ' ').title()}[/bold cyan]")

                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    transient=True,
                ) as progress:
                    task = progress.add_task(f"[cyan]Loading data from {tab_name}...", total=None)
                    records = self.db.get_all_rows(tab_name)
                    progress.update(task, completed=True)

                if records:
                    self.tui.show_data_table(records, tab_name.replace('_', ' ').title())
                else:
                    console.print("[yellow]No records found in this tab[/yellow]")
        except ValueError:
            console.print("[red]Invalid selection[/red]")

    def add_record(self):
        """Add a new record to a tab"""
        console.clear()
        self.tui.show_header()

        # Get all tab names
        tabs = list(DatabaseRegistry.get_all_tabs().keys())

        console.print("[bold cyan]➕ Add Record[/bold cyan]")
        for i, tab in enumerate(tabs, 1):
            config = DatabaseRegistry.get_tab_config(tab)
            desc = f" - {config.description}" if config and config.description else ""
            console.print(f"  [cyan]{i}.[/cyan] {tab.replace('_', ' ').title()}{desc}")
        console.print("  [dim]0. Back to menu[/dim]")

        choice = Prompt.ask("Select tab to add to", default="0")

        if choice == "0":
            return

        try:
            idx = int(choice) - 1
            if 0 <= idx < len(tabs):
                tab_name = tabs[idx]

                # Get headers
                headers = self.db.get_headers(tab_name)

                console.print(f"\n[bold cyan]Adding record to {tab_name.replace('_', ' ').title()}[/bold cyan]")
                console.print("[dim]Enter values for each field (press Enter to skip)[/dim]")

                data = {}
                for header in headers:
                    value = Prompt.ask(f"  {header}", default="")
                    if value:
                        data[header] = value

                if data:
                    with Progress(
                        SpinnerColumn(),
                        TextColumn("[progress.description]{task.description}"),
                        transient=True,
                    ) as progress:
                        task = progress.add_task(f"[cyan]Adding record to {tab_name}...", total=None)
                        result = self.db.insert_row(tab_name, data)
                        progress.update(task, completed=True)

                    self.tui.show_success(f"Record added to {tab_name}")
                    self.tui.show_data_table([data], "Added Record")
                else:
                    console.print("[yellow]No data provided, skipping...[/yellow]")
        except ValueError:
            console.print("[red]Invalid selection[/red]")

    def search_records(self):
        """Search for records in a tab"""
        console.clear()
        self.tui.show_header()

        # Get all tab names
        tabs = list(DatabaseRegistry.get_all_tabs().keys())

        console.print("[bold cyan]🔍 Search Records[/bold cyan]")
        for i, tab in enumerate(tabs, 1):
            config = DatabaseRegistry.get_tab_config(tab)
            desc = f" - {config.description}" if config and config.description else ""
            console.print(f"  [cyan]{i}.[/cyan] {tab.replace('_', ' ').title()}{desc}")
        console.print("  [dim]0. Back to menu[/dim]")

        choice = Prompt.ask("Select tab to search", default="0")

        if choice == "0":
            return

        try:
            idx = int(choice) - 1
            if 0 <= idx < len(tabs):
                tab_name = tabs[idx]

                headers = self.db.get_headers(tab_name)

                console.print(f"\n[bold cyan]Searching in {tab_name.replace('_', ' ').title()}[/bold cyan]")

                # Select column to search
                console.print("\n[dim]Select column to search:[/dim]")
                for i, header in enumerate(headers, 1):
                    console.print(f"  [cyan]{i}.[/cyan] {header}")

                col_choice = Prompt.ask("Select column", default="1")
                try:
                    col_idx = int(col_choice) - 1
                    if 0 <= col_idx < len(headers):
                        column = headers[col_idx]
                        value = Prompt.ask(f"Enter value to search for in '{column}'")

                        if value:
                            with Progress(
                                SpinnerColumn(),
                                TextColumn("[progress.description]{task.description}"),
                                transient=True,
                            ) as progress:
                                task = progress.add_task(f"[cyan]Searching in {tab_name}...", total=None)
                                results = self.db.find_rows(tab_name, column, value)
                                progress.update(task, completed=True)

                            if results:
                                self.tui.show_data_table(results, f"Search Results: {column}={value}")
                            else:
                                console.print("[yellow]No matching records found[/yellow]")
                except ValueError:
                    console.print("[red]Invalid selection[/red]")
        except ValueError:
            console.print("[red]Invalid selection[/red]")

    def view_statistics(self):
        """View database statistics"""
        console.clear()
        self.tui.show_header()

        console.print("[bold cyan]📈 Database Statistics[/bold cyan]")

        info = self.db.get_all_tabs_info()

        total_records = 0
        active_tabs = 0

        table = Table(title="Tab Statistics", box=box.ROUNDED)
        table.add_column("Category", style="cyan")
        table.add_column("Tab", style="green")
        table.add_column("Records", style="yellow", justify="right")
        table.add_column("Headers", style="dim")

        categories = DatabaseRegistry.get_tabs_by_category()

        for category, tabs in categories.items():
            category_rows = 0
            for tab in tabs:
                tab_name = tab['name']
                data = info.get(tab_name, {'count': 0, 'headers': []})
                count = data['count']
                total_records += count
                if count > 0:
                    active_tabs += 1
                category_rows += count

                headers_str = ', '.join(data['headers'][:3])
                if len(data['headers']) > 3:
                    headers_str += "..."

                table.add_row(
                    category if category_rows == count else "",
                    tab['display_name'],
                    str(count),
                    headers_str
                )
            # Add category total
            if category_rows > 0:
                table.add_row(
                    "[bold]" + category + " Total[/bold]",
                    "",
                    f"[bold]{category_rows}[/bold]",
                    "",
                    style="bold"
                )
                table.add_row("", "", "", "", style="dim")

        console.print(table)

        # Summary panel
        summary = Panel(
            f"[bold]Summary:[/bold]\n"
            f"  • Total Records: [cyan]{total_records}[/cyan]\n"
            f"  • Active Tabs: [green]{active_tabs}[/green]\n"
            f"  • Total Tabs: [yellow]{len(info)}[/yellow]\n"
            f"  • Sheet ID: [dim]{self.db.sheet_id}[/dim]",
            title="📊 Summary",
            border_style="cyan"
        )
        console.print(summary)

    def delete_record(self):
        """Delete a record from a tab"""
        console.clear()
        self.tui.show_header()

        # Get all tab names
        tabs = list(DatabaseRegistry.get_all_tabs().keys())

        console.print("[bold red]🗑️  Delete Record[/bold red]")
        console.print("[yellow]⚠️  This action cannot be undone![/yellow]")

        for i, tab in enumerate(tabs, 1):
            config = DatabaseRegistry.get_tab_config(tab)
            desc = f" - {config.description}" if config and config.description else ""
            console.print(f"  [cyan]{i}.[/cyan] {tab.replace('_', ' ').title()}{desc}")
        console.print("  [dim]0. Back to menu[/dim]")

        choice = Prompt.ask("Select tab", default="0")

        if choice == "0":
            return

        try:
            idx = int(choice) - 1
            if 0 <= idx < len(tabs):
                tab_name = tabs[idx]

                records = self.db.get_all_rows(tab_name)
                if not records:
                    console.print("[yellow]No records to delete[/yellow]")
                    return

                # Show records with indices
                self.tui.show_data_table(records, f"{tab_name} - Select row to delete")

                row_idx = Prompt.ask(
                    "Enter row number to delete (1-based)",
                    default="0"
                )

                if row_idx == "0":
                    return

                try:
                    row_num = int(row_idx) - 1
                    if 0 <= row_num < len(records):
                        # Confirm deletion
                        if Confirm.ask(f"[red]Are you sure you want to delete row {row_idx}?[/red]"):
                            with Progress(
                                SpinnerColumn(),
                                TextColumn("[progress.description]{task.description}"),
                                transient=True,
                            ) as progress:
                                task = progress.add_task(f"[cyan]Deleting row from {tab_name}...", total=None)
                                result = self.db.delete_row(tab_name, row_num)
                                progress.update(task, completed=True)

                            self.tui.show_success(f"Deleted row {row_idx} from {tab_name}")
                except ValueError:
                    console.print("[red]Invalid row number[/red]")
        except ValueError:
            console.print("[red]Invalid selection[/red]")

    def refresh_data(self):
        """Refresh all cached data"""
        console.clear()
        self.tui.show_header()

        console.print("[bold cyan]🔄 Refreshing Data[/bold cyan]")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
        ) as progress:
            # Clear caches
            self.db._worksheet_cache = {}
            self.db._header_cache = {}

            task = progress.add_task("[cyan]Refreshing cache...", total=None)
            time.sleep(0.5)
            progress.update(task, completed=True)

        self.tui.show_success("Data refreshed successfully")

    def exit_app(self):
        """Exit the application"""
        if Confirm.ask("[yellow]Are you sure you want to exit?[/yellow]"):
            console.print("[green]Goodbye! 👋[/green]")
            self.running = False


# ==================== Singleton Instance ====================

_db_instance = None

def get_db(sheet_id: Optional[str] = None,
           credentials_file: Optional[str] = None,
           interactive: bool = True,
           data_dir: Optional[str] = None) -> GoogleSheetsDB:
    """Get singleton database instance"""
    global _db_instance
    if _db_instance is None:
        _db_instance = GoogleSheetsDB(
            sheet_id=sheet_id,
            credentials_file=credentials_file,
            interactive=interactive,
            data_dir=data_dir
        )
    return _db_instance


# ==================== Main Application ====================

def main():
    """Main application entry point"""
    try:
        # Initialize database
        db = get_db(interactive=True)

        # Start interactive menu
        menu = InteractiveMenu(db)
        menu.run()

    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")
        sys.exit(0)
    except Exception as e:
        console.print(f"[red]❌ Error: {e}[/red]")
        sys.exit(1)


if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    main()
