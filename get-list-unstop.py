#!/usr/bin/env python3
"""
Chrome Page Tool - Unstop Job Extractor (Enhanced)
Improved version with better data parsing and extraction
"""

import json
import websocket
import requests
import sys
import time
import re
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich import box
from rich.text import Text
from rich.syntax import Syntax
from rich.columns import Columns
from rich.console import Group
from datetime import datetime
from collections import Counter

console = Console()

class UnstopJobExtractor:
    def __init__(self, port=9236):
        self.port = port
        self.ws = None
        self.connected = False
        self.page_title = ""
        self.page_url = ""
        self.jobs = []

    def connect(self):
        """Connect to Chrome DevTools"""
        try:
            resp = requests.get(f"http://127.0.0.1:{self.port}/json", timeout=5)
            tabs = resp.json()

            page_tab = None
            for tab in tabs:
                if tab.get('type') == 'page':
                    page_tab = tab
                    break

            if not page_tab:
                console.print("[red]No page found[/red]")
                return False

            self.page_title = page_tab.get('title', 'Untitled')
            self.page_url = page_tab.get('url', '')
            ws_url = page_tab.get('webSocketDebuggerUrl')

            self.ws = websocket.create_connection(ws_url, timeout=10)

            self.ws.send(json.dumps({"id": 1, "method": "Runtime.enable"}))
            while True:
                resp = self.ws.recv()
                data = json.loads(resp)
                if data.get('id') == 1:
                    break

            self.connected = True
            console.print(f"[green]✅ Connected to: {self.page_title}[/green]")
            console.print(f"[dim]   URL: {self.page_url}[/dim]")
            return True

        except Exception as e:
            console.print(f"[red]Connection failed: {e}[/red]")
            return False

    def js(self, script, await_promise=False):
        """Execute JavaScript and return result"""
        if not self.connected:
            return None

        cmd_id = int(time.time() * 1000) % 100000

        self.ws.send(json.dumps({
            "id": cmd_id,
            "method": "Runtime.evaluate",
            "params": {
                "expression": script,
                "returnByValue": True,
                "awaitPromise": await_promise
            }
        }))

        timeout = 30
        start = time.time()
        while time.time() - start < timeout:
            try:
                resp = self.ws.recv()
                data = json.loads(resp)
                if data.get('id') == cmd_id:
                    result = data.get('result', {})
                    if 'result' in result:
                        return result['result'].get('value')
                    elif 'error' in result:
                        console.print(f"[red]Error: {result['error']}[/red]")
                        return None
                    return None
            except Exception as e:
                console.print(f"[red]WS read error: {e}[/red]")
                return None

        console.print("[yellow]Timeout waiting for response[/yellow]")
        return None

    def extract_jobs(self):
        """Extract job listings with improved parsing"""
        script = """
        (function() {
            const jobs = [];
            
            // Find all job listing containers
            const jobContainers = document.querySelectorAll('a[class*="opp_"], a[id*="i_"]');
            
            jobContainers.forEach(container => {
                try {
                    // Extract title - look for h3 or itemprop name
                    const titleEl = container.querySelector('h3, [itemprop="name"]');
                    let title = titleEl ? titleEl.textContent.trim() : '';
                    
                    // Extract company - look for paragraph that's not the title
                    const companyEl = container.querySelector('p');
                    let company = companyEl ? companyEl.textContent.trim() : '';
                    
                    // If company is same as title, try to find differently
                    if (company === title) {
                        const altCompany = container.querySelector('[itemprop="name"]:not(h3)');
                        company = altCompany ? altCompany.textContent.trim() : '';
                    }
                    
                    // Extract job URL
                    const jobUrl = container.href || '';
                    
                    // Extract location - look for location classes or itemprop
                    const locationEl = container.querySelector('[class*="location"], [itemprop="location"]');
                    let location = locationEl ? locationEl.textContent.trim() : '';
                    // Clean up location
                    location = location.replace(/\\s+/g, ' ').trim();
                    
                    // Extract experience
                    const expEl = container.querySelector('[class*="exp"], [class*="years"]');
                    let experience = expEl ? expEl.textContent.trim() : '';
                    experience = experience.replace(/\\s+/g, ' ').trim();
                    
                    // Extract job type
                    const typeEl = container.querySelector('[class*="schedule"]');
                    let jobType = typeEl ? typeEl.textContent.trim() : '';
                    jobType = jobType.replace(/\\s+/g, ' ').trim();
                    
                    // Extract salary
                    const salaryEl = container.querySelector('[class*="cash"], [class*="salary"], [class*="LPA"]');
                    let salary = salaryEl ? salaryEl.textContent.trim() : '';
                    salary = salary.replace(/\\s+/g, ' ').trim();
                    
                    // Extract skills - get from chip elements
                    const skillEls = container.querySelectorAll('[class*="chip"] span, [class*="skill"]');
                    const skills = Array.from(skillEls)
                        .map(el => el.textContent.trim())
                        .filter(s => s && !s.includes('Posted') && !s.includes('days left'))
                        .slice(0, 10); // Limit to 10 skills
                    
                    // Extract posted date
                    const dateEl = container.querySelector('[class*="Posted"]');
                    let postedDate = dateEl ? dateEl.textContent.trim() : '';
                    postedDate = postedDate.replace(/\\s+/g, ' ').trim();
                    
                    // Extract deadline
                    const deadlineEl = container.querySelector('[class*="days left"], [class*="left"]');
                    let deadline = deadlineEl ? deadlineEl.textContent.trim() : '';
                    deadline = deadline.replace(/\\s+/g, ' ').trim();
                    
                    // Extract tags (like Fresher, Experienced, etc.)
                    const tagEls = container.querySelectorAll('[class*="chip"]');
                    const tags = Array.from(tagEls)
                        .map(el => el.textContent.trim())
                        .filter(s => s && s.length < 30)
                        .slice(0, 5);
                    
                    // Only add if we have at least a title
                    if (title) {
                        jobs.push({
                            title: title,
                            company: company || 'Not specified',
                            url: jobUrl,
                            location: location || 'Not specified',
                            experience: experience || 'Not specified',
                            jobType: jobType || 'Not specified',
                            salary: salary || 'Not specified',
                            skills: skills,
                            postedDate: postedDate || 'Not specified',
                            deadline: deadline || 'Not specified',
                            tags: tags
                        });
                    }
                } catch(e) {
                    // Skip this container if there's an error
                }
            });
            
            return jobs;
        })()
        """
        
        console.print("[yellow]🔍 Extracting job listings...[/yellow]")
        self.jobs = self.js(script) or []
        
        # Post-process to clean up data
        for job in self.jobs:
            # Clean location - remove extra spaces and normalize
            if job.get('location'):
                job['location'] = ' '.join(job['location'].split())
                # Remove duplicate "In Office" if it appears
                if 'In Office' in job['location']:
                    parts = job['location'].split('|')
                    if len(parts) > 1:
                        cities = parts[1].strip()
                        job['location'] = f"In Office | {cities}"
            
            # Clean salary - remove extra spaces
            if job.get('salary'):
                job['salary'] = ' '.join(job['salary'].split())
            
            # Clean skills - remove duplicates
            if job.get('skills'):
                job['skills'] = list(dict.fromkeys(job['skills']))  # Remove duplicates
            
            # Clean tags - remove duplicates
            if job.get('tags'):
                job['tags'] = list(dict.fromkeys(job['tags']))  # Remove duplicates
        
        console.print(f"[green]✅ Found {len(self.jobs)} jobs[/green]")
        return self.jobs

    def display_jobs_table(self, jobs=None, show_all=False):
        """Display jobs in a formatted table with better formatting"""
        if jobs is None:
            jobs = self.jobs
        
        if not jobs:
            console.print("[yellow]No jobs found[/yellow]")
            return
        
        # Create main table
        table = Table(
            title=f"📋 Job Listings ({len(jobs)})", 
            box=box.ROUNDED,
            show_header=True,
            header_style="bold cyan"
        )
        table.add_column("#", style="cyan", width=4)
        table.add_column("Title", style="green", max_width=35)
        table.add_column("Company", style="yellow", max_width=25)
        table.add_column("Location", style="blue", max_width=25)
        table.add_column("Type", style="magenta", max_width=12)
        table.add_column("Salary", style="red", max_width=15)
        
        display_count = len(jobs) if show_all else min(30, len(jobs))
        
        for i, job in enumerate(jobs[:display_count], 1):
            title = job.get('title', 'N/A')[:33]
            company = job.get('company', 'N/A')[:23]
            location = job.get('location', 'N/A')[:23]
            job_type = job.get('jobType', 'N/A')[:10]
            salary = job.get('salary', 'N/A')[:13]
            
            table.add_row(str(i), title, company, location, job_type, salary)
        
        console.print(table)
        
        if len(jobs) > display_count:
            console.print(f"[dim]... and {len(jobs)-display_count} more[/dim]")
    
    def display_job_details(self, job):
        """Display detailed information for a single job with better formatting"""
        content = []
        content.append(f"[bold cyan]📌 {job.get('title', 'Untitled')}[/bold cyan]")
        content.append("")
        content.append(f"[bold]🏢 Company:[/bold] {job.get('company', 'N/A')}")
        content.append(f"[bold]📍 Location:[/bold] {job.get('location', 'N/A')}")
        content.append(f"[bold]💼 Job Type:[/bold] {job.get('jobType', 'N/A')}")
        content.append(f"[bold]⏰ Experience:[/bold] {job.get('experience', 'N/A')}")
        content.append(f"[bold]💰 Salary:[/bold] {job.get('salary', 'N/A')}")
        content.append(f"[bold]📅 Posted:[/bold] {job.get('postedDate', 'N/A')}")
        content.append(f"[bold]⏳ Deadline:[/bold] {job.get('deadline', 'N/A')}")
        content.append("")
        
        if job.get('skills'):
            content.append("[bold]🛠️ Skills:[/bold]")
            for skill in job.get('skills', []):
                if skill and skill not in ['Fresher', 'Experienced']:
                    content.append(f"  • {skill}")
        
        if job.get('tags'):
            content.append("[bold]🏷️ Tags:[/bold]")
            for tag in job.get('tags', []):
                if tag:
                    content.append(f"  • {tag}")
        
        content.append("")
        content.append(f"[bold]🔗 URL:[/bold] {job.get('url', 'N/A')}")
        
        console.print(Panel("\n".join(content), title="Job Details", border_style="cyan"))
    
    def filter_jobs(self, keyword):
        """Filter jobs by keyword with better matching"""
        filtered = []
        keyword_lower = keyword.lower()
        
        for job in self.jobs:
            searchable = f"{job.get('title', '')} {job.get('company', '')} {job.get('location', '')} {' '.join(job.get('skills', []))} {job.get('jobType', '')}".lower()
            if keyword_lower in searchable:
                filtered.append(job)
        
        return filtered
    
    def search_by_city(self, city):
        """Search jobs by city name"""
        filtered = []
        city_lower = city.lower()
        
        for job in self.jobs:
            location = job.get('location', '').lower()
            if city_lower in location:
                filtered.append(job)
        
        return filtered
    
    def get_stats(self):
        """Get statistics about extracted jobs"""
        if not self.jobs:
            return None
        
        stats = {
            'total': len(self.jobs),
            'companies': Counter(),
            'locations': Counter(),
            'job_types': Counter(),
            'skills': Counter(),
            'cities': Counter()
        }
        
        for job in self.jobs:
            # Count companies
            company = job.get('company', 'Unknown')
            if company != 'Not specified':
                stats['companies'][company] += 1
            
            # Count job types
            job_type = job.get('jobType', 'Unknown')
            if job_type != 'Not specified':
                stats['job_types'][job_type] += 1
            
            # Count skills
            for skill in job.get('skills', []):
                if skill and skill not in ['Fresher', 'Experienced']:
                    stats['skills'][skill] += 1
            
            # Extract and count cities from location
            location = job.get('location', '')
            if location and location != 'Not specified':
                # Extract city names after "|" or commas
                parts = location.split('|')
                if len(parts) > 1:
                    cities = parts[1].split(',')
                    for city in cities:
                        city = city.strip()
                        if city:
                            stats['cities'][city] += 1
                else:
                    # Try to find city names
                    cities = location.split(',')
                    for city in cities:
                        city = city.strip()
                        if city and not city.startswith('In Office') and not city.startswith('Work from'):
                            stats['cities'][city] += 1
        
        return stats
    
    def export_json(self, filename=None):
        """Export jobs to JSON file"""
        if not self.jobs:
            console.print("[yellow]No jobs to export[/yellow]")
            return
        
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"unstop_jobs_{timestamp}.json"
        
        try:
            export_data = {
                'source_url': self.page_url,
                'extracted_at': datetime.now().isoformat(),
                'total_jobs': len(self.jobs),
                'jobs': self.jobs
            }
            
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)
            console.print(f"[green]✅ Exported {len(self.jobs)} jobs to {filename}[/green]")
        except Exception as e:
            console.print(f"[red]Export failed: {e}[/red]")
    
    def export_markdown(self, filename=None):
        """Export jobs to Markdown file"""
        if not self.jobs:
            console.print("[yellow]No jobs to export[/yellow]")
            return
        
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"unstop_jobs_{timestamp}.md"
        
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(f"# 🏢 Job Listings from Unstop\n\n")
                f.write(f"**Source:** {self.page_url}\n\n")
                f.write(f"**Total Jobs:** {len(self.jobs)}\n\n")
                f.write(f"**Extracted At:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                f.write("---\n\n")
                
                for i, job in enumerate(self.jobs, 1):
                    f.write(f"## {i}. {job.get('title', 'Untitled')}\n\n")
                    f.write(f"**Company:** {job.get('company', 'N/A')}\n\n")
                    f.write(f"**Location:** {job.get('location', 'N/A')}\n\n")
                    f.write(f"**Job Type:** {job.get('jobType', 'N/A')}\n\n")
                    f.write(f"**Experience:** {job.get('experience', 'N/A')}\n\n")
                    f.write(f"**Salary:** {job.get('salary', 'N/A')}\n\n")
                    f.write(f"**Posted:** {job.get('postedDate', 'N/A')}\n\n")
                    f.write(f"**Deadline:** {job.get('deadline', 'N/A')}\n\n")
                    
                    if job.get('skills'):
                        f.write("**Skills:**\n")
                        for skill in job.get('skills', []):
                            if skill and skill not in ['Fresher', 'Experienced']:
                                f.write(f"- {skill}\n")
                        f.write("\n")
                    
                    f.write(f"**URL:** [{job.get('url', 'N/A')}]({job.get('url', '#')})\n\n")
                    f.write("---\n\n")
            
            console.print(f"[green]✅ Exported to {filename}[/green]")
        except Exception as e:
            console.print(f"[red]Export failed: {e}[/red]")

    def close(self):
        if self.ws:
            try:
                self.ws.close()
            except:
                pass

def main():
    console.clear()
    console.print(Panel("[bold cyan]🏢 Unstop Job Extractor (Enhanced)[/bold cyan]", border_style="green"))
    console.print("[dim]Specialized tool for extracting job listings from Unstop with improved parsing[/dim]\n")

    port = int(Prompt.ask("Port", default="9236"))
    extractor = UnstopJobExtractor(port)

    if not extractor.connect():
        return

    while True:
        console.print()
        console.print(Panel(f"[bold]Page: {extractor.page_title[:60]}...[/bold]", border_style="blue"))

        console.print("[cyan]📌 Options:[/cyan]")
        console.print("  1. Extract All Jobs")
        console.print("  2. Show Jobs Table")
        console.print("  3. View Job Details")
        console.print("  4. Filter Jobs by Keyword")
        console.print("  5. Filter Jobs by City")
        console.print("  6. Show Statistics")
        console.print("  7. Export to JSON")
        console.print("  8. Export to Markdown")
        console.print("  9. Refresh Page")
        console.print("  10. Navigate to URL")
        console.print("  0. Exit")

        choice = Prompt.ask("Select", choices=["0","1","2","3","4","5","6","7","8","9","10"])

        if choice == "0":
            break

        elif choice == "1":  # Extract Jobs
            extractor.extract_jobs()
            if extractor.jobs:
                extractor.display_jobs_table()
                console.print(f"\n[green]✅ Ready to work with {len(extractor.jobs)} jobs[/green]")

        elif choice == "2":  # Show Jobs Table
            if not extractor.jobs:
                console.print("[yellow]No jobs extracted yet. Use option 1 first.[/yellow]")
            else:
                show_all = Confirm.ask("Show all jobs?", default=False)
                extractor.display_jobs_table(show_all=show_all)

        elif choice == "3":  # View Job Details
            if not extractor.jobs:
                console.print("[yellow]No jobs extracted yet. Use option 1 first.[/yellow]")
            else:
                extractor.display_jobs_table()
                idx = int(Prompt.ask("Enter job number", default="1")) - 1
                if 0 <= idx < len(extractor.jobs):
                    extractor.display_job_details(extractor.jobs[idx])
                else:
                    console.print("[red]Invalid job number[/red]")

        elif choice == "4":  # Filter Jobs by Keyword
            if not extractor.jobs:
                console.print("[yellow]No jobs extracted yet. Use option 1 first.[/yellow]")
            else:
                keyword = Prompt.ask("Enter keyword (e.g., 'developer', 'mumbai', 'sales')")
                filtered = extractor.filter_jobs(keyword)
                if filtered:
                    console.print(f"[green]✅ Found {len(filtered)} jobs matching '{keyword}'[/green]")
                    extractor.display_jobs_table(filtered)
                    
                    if Confirm.ask("View details of a filtered job?"):
                        idx = int(Prompt.ask("Enter job number")) - 1
                        if 0 <= idx < len(filtered):
                            extractor.display_job_details(filtered[idx])
                else:
                    console.print(f"[yellow]No jobs found matching '{keyword}'[/yellow]")

        elif choice == "5":  # Filter Jobs by City
            if not extractor.jobs:
                console.print("[yellow]No jobs extracted yet. Use option 1 first.[/yellow]")
            else:
                city = Prompt.ask("Enter city name (e.g., 'Mumbai', 'Chennai')")
                filtered = extractor.search_by_city(city)
                if filtered:
                    console.print(f"[green]✅ Found {len(filtered)} jobs in {city}[/green]")
                    extractor.display_jobs_table(filtered)
                    
                    if Confirm.ask("View details of a job?"):
                        idx = int(Prompt.ask("Enter job number")) - 1
                        if 0 <= idx < len(filtered):
                            extractor.display_job_details(filtered[idx])
                else:
                    console.print(f"[yellow]No jobs found in {city}[/yellow]")

        elif choice == "6":  # Show Statistics
            if not extractor.jobs:
                console.print("[yellow]No jobs extracted yet. Use option 1 first.[/yellow]")
            else:
                stats = extractor.get_stats()
                if stats:
                    console.print(Panel("[bold]📊 Job Statistics[/bold]", border_style="green"))
                    
                    console.print(f"\n[bold]Total Jobs:[/bold] {stats['total']}")
                    
                    console.print(f"\n[bold cyan]🏢 Top Companies:[/bold cyan]")
                    for company, count in stats['companies'].most_common(10):
                        console.print(f"  • {company}: {count}")
                    
                    console.print(f"\n[bold cyan]📍 Top Cities:[/bold cyan]")
                    for city, count in stats['cities'].most_common(10):
                        if city:
                            console.print(f"  • {city}: {count}")
                    
                    console.print(f"\n[bold cyan]💼 Job Types:[/bold cyan]")
                    for job_type, count in stats['job_types'].most_common():
                        if job_type != 'Not specified':
                            console.print(f"  • {job_type}: {count}")
                    
                    console.print(f"\n[bold cyan]🛠️ Top Skills:[/bold cyan]")
                    for skill, count in stats['skills'].most_common(15):
                        if skill and skill not in ['Fresher', 'Experienced']:
                            console.print(f"  • {skill}: {count}")

        elif choice == "7":  # Export to JSON
            if not extractor.jobs:
                console.print("[yellow]No jobs to export[/yellow]")
            else:
                extractor.export_json()

        elif choice == "8":  # Export to Markdown
            if not extractor.jobs:
                console.print("[yellow]No jobs to export[/yellow]")
            else:
                extractor.export_markdown()

        elif choice == "9":  # Refresh Page
            extractor.js("location.reload()")
            console.print("[yellow]⏳ Page reloading...[/yellow]")
            time.sleep(3)
            console.print(f"[dim]New title: {extractor.page_title}[/dim]")
            extractor.jobs = []  # Clear cached jobs

        elif choice == "10":  # Navigate to URL
            url = Prompt.ask("URL")
            if not url.startswith(("http://", "https://")):
                url = f"https://{url}"
            extractor.js(f"window.location.href = '{url}'")
            console.print(f"[yellow]⏳ Navigating to {url}...[/yellow]")
            time.sleep(3)
            console.print(f"[dim]New title: {extractor.page_title}[/dim]")
            extractor.jobs = []  # Clear cached jobs

        if choice != "0":
            console.print()
            input("Press Enter to continue...")

    extractor.close()
    console.print("[green]Goodbye! 👋[/green]")

if __name__ == "__main__":
    main()
