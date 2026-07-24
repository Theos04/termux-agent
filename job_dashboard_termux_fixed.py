# job_dashboard_termux_fixed.py - Fixed interactive dashboard
import json
import sys
import os
from pathlib import Path
from datetime import datetime
from job_intelligence_termux_fixed import TermuxJobIntelligence

class TermuxJobDashboard:
    """Interactive dashboard optimized for Termux"""
    
    def __init__(self):
        self.intelligence = TermuxJobIntelligence()
        self.intelligence.load_jobs()
        self.intelligence.embed_all_jobs()
        self.running = True
        
    def clear_screen(self):
        """Clear the terminal screen"""
        os.system('clear' if os.name == 'posix' else 'cls')
    
    def show_header(self):
        """Show dashboard header"""
        print("\n" + "=" * 70)
        print("🧠 JOB INTELLIGENCE DASHBOARD (Termux)")
        print("=" * 70)
        print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"📂 Jobs: {len(self.intelligence.jobs)}")
        print(f"🔢 Embeddings: {len(self.intelligence.job_embeddings)}")
        print("-" * 70)
    
    def show_commands(self):
        """Show available commands"""
        print("\n📋 Commands:")
        print("  1. trends   - Show market trends")
        print("  2. match    - Match skills to jobs")
        print("  3. search   - Search similar jobs")
        print("  4. skills   - Show top skills in demand")
        print("  5. report   - Generate full report")
        print("  6. analyze  - Analyze specific job")
        print("  7. list     - List all jobs")
        print("  8. help     - Show this help")
        print("  9. clear    - Clear screen")
        print("  0. quit     - Exit dashboard")
        print("-" * 70)
    
    def show_trends(self):
        """Show market trends"""
        self.clear_screen()
        self.show_header()
        print("\n📊 MARKET TRENDS")
        print("-" * 60)
        
        analysis = self.intelligence.analyze_market()
        
        print(f"\n📈 Total Jobs: {analysis['total_jobs']}")
        
        if analysis['companies']:
            print("\n🏢 Top Companies:")
            for company, count in analysis['companies'].most_common(10):
                print(f"   {company}: {count}")
        else:
            print("\n🏢 No company data available")
        
        if analysis['locations']:
            print("\n📍 Top Locations:")
            for location, count in analysis['locations'].most_common(10):
                print(f"   {location}: {count}")
        
        if analysis['salary_stats']['jobs_with_salary'] > 0:
            print(f"\n💰 Salary Stats:")
            print(f"   Jobs with salary: {analysis['salary_stats']['jobs_with_salary']}")
            print(f"   Average: ₹{analysis['salary_stats']['avg']:,.0f}")
            print(f"   Range: ₹{analysis['salary_stats']['min']:,.0f} - ₹{analysis['salary_stats']['max']:,.0f}")
        
        input("\nPress Enter to continue...")
    
    def show_skills(self):
        """Show top skills in demand"""
        self.clear_screen()
        self.show_header()
        print("\n🔧 TOP SKILLS IN DEMAND")
        print("-" * 60)
        
        analysis = self.intelligence.analyze_market()
        
        if analysis['top_skills']:
            for i, (skill, count) in enumerate(analysis['top_skills'][:20], 1):
                print(f"  {i:2}. {skill}: {count} jobs")
        else:
            print("No skills data available")
        
        input("\nPress Enter to continue...")
    
    def show_match(self):
        """Match skills to jobs"""
        self.clear_screen()
        self.show_header()
        print("\n🤝 SKILL MATCHING")
        print("-" * 60)
        
        print("\n💡 Example skills: Python, SQL, React, Customer Support, Business Development")
        skills_input = input("\nEnter your skills (comma separated): ")
        skills = [s.strip() for s in skills_input.split(',') if s.strip()]
        
        if not skills:
            print("No skills entered")
            input("Press Enter to continue...")
            return
        
        print(f"\n🔍 Matching for: {', '.join(skills[:5])}")
        matches = self.intelligence.match_skills_to_jobs(skills, n_results=10)
        
        if not matches:
            print("No matches found")
            input("Press Enter to continue...")
            return
        
        print(f"\n📊 Top Matches:")
        for i, match in enumerate(matches[:10], 1):
            print(f"\n{i}. {match['title']}")
            print(f"   Company: {match['company']}")
            print(f"   Location: {match['location']}")
            print(f"   Match: {match['percentage']}%")
            if match['matched_skills']:
                print(f"   ✅ Matched: {', '.join(match['matched_skills'][:3])}")
            if match['missing_skills']:
                print(f"   ⚠️  Missing: {', '.join(match['missing_skills'][:3])}")
        
        input("\nPress Enter to continue...")
    
    def show_search(self):
        """Search similar jobs"""
        self.clear_screen()
        self.show_header()
        print("\n🔍 JOB SEARCH")
        print("-" * 60)
        
        print("\n💡 Example: Python Developer, Data Scientist, Customer Support Executive")
        query = input("\nEnter search query: ")
        if not query:
            return
        
        print(f"\n🔍 Searching for: {query}")
        results = self.intelligence.find_similar_jobs(query, n_results=10)
        
        if not results:
            print("No results found")
            input("Press Enter to continue...")
            return
        
        print(f"\n📊 Results:")
        for i, result in enumerate(results[:10], 1):
            print(f"\n{i}. {result['title']}")
            print(f"   Company: {result['company']}")
            print(f"   Location: {result['location']}")
            if result['similarity'] > 0:
                print(f"   Similarity: {result['similarity']:.3f}")
        
        input("\nPress Enter to continue...")
    
    def show_list(self):
        """List all jobs"""
        self.clear_screen()
        self.show_header()
        print("\n📋 ALL JOBS")
        print("-" * 60)
        
        if not self.intelligence.jobs:
            print("No jobs available")
            input("Press Enter to continue...")
            return
        
        for i, job in enumerate(self.intelligence.jobs, 1):
            title = job.get('title', 'Unknown')
            company = job.get('company', 'Unknown')
            location = job.get('location', 'Unknown')
            print(f"  {i:2}. {title[:50]}")
            print(f"      Company: {company}")
            print(f"      Location: {location}")
            print()
        
        input("Press Enter to continue...")
    
    def show_analyze(self):
        """Analyze a specific job"""
        self.clear_screen()
        self.show_header()
        print("\n🔬 JOB ANALYSIS")
        print("-" * 60)
        
        if not self.intelligence.jobs:
            print("No jobs available")
            input("Press Enter to continue...")
            return
        
        print(f"\n📋 Available jobs: {len(self.intelligence.jobs)}")
        print("Enter job number (1-{0})".format(len(self.intelligence.jobs)))
        print("Or enter 'random' for a random job")
        
        choice = input("\nChoice: ").strip()
        
        if choice.lower() == 'random':
            import random
            idx = random.randint(0, len(self.intelligence.jobs) - 1)
        else:
            try:
                idx = int(choice) - 1
                if idx < 0 or idx >= len(self.intelligence.jobs):
                    print("Invalid index")
                    input("Press Enter to continue...")
                    return
            except:
                print("Invalid input")
                input("Press Enter to continue...")
                return
        
        job = self.intelligence.jobs[idx]
        
        print(f"\n📋 Job Details")
        print("-" * 60)
        print(f"Title: {job.get('title', 'N/A')}")
        print(f"Company: {job.get('company', 'N/A')}")
        print(f"Location: {job.get('location', 'N/A')}")
        print(f"Type: {job.get('job_type', 'N/A')}")
        print(f"URL: {job.get('url', job.get('detail_url', 'N/A'))}")
        
        skills = job.get('skills', [])
        if isinstance(skills, str):
            skills = [s.strip() for s in skills.split(',')] if skills else []
        if skills:
            print(f"\n🔧 Skills: {', '.join(skills[:10])}")
        
        salary = job.get('salary_range')
        if salary:
            print(f"💰 Salary: {salary}")
        
        deadline = job.get('deadline')
        if deadline:
            print(f"⏰ Deadline: {deadline}")
        
        description = job.get('full_description', '')
        if description:
            print(f"\n📝 Description (first 500 chars):")
            print(f"{description[:500]}...")
        
        input("\nPress Enter to continue...")
    
    def show_report(self):
        """Generate and show full report"""
        self.clear_screen()
        self.show_header()
        print("\n📊 GENERATING REPORT...")
        
        report = self.intelligence.generate_report()
        
        # Save report
        report_dir = Path("job_details")
        report_dir.mkdir(exist_ok=True)
        report_file = report_dir / f"dashboard_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(report_file, 'w') as f:
            f.write(report)
        
        print("\n" + report)
        print(f"\n✅ Report saved to: {report_file}")
        
        input("\nPress Enter to continue...")
    
    def run(self):
        """Run the dashboard"""
        while self.running:
            self.clear_screen()
            self.show_header()
            self.show_commands()
            
            cmd = input("\nEnter command: ").strip().lower()
            
            if cmd == 'quit' or cmd == 'exit' or cmd == '0':
                self.running = False
                print("\nGoodbye! 👋")
                break
            elif cmd == 'trends' or cmd == '1':
                self.show_trends()
            elif cmd == 'match' or cmd == '2':
                self.show_match()
            elif cmd == 'search' or cmd == '3':
                self.show_search()
            elif cmd == 'skills' or cmd == '4':
                self.show_skills()
            elif cmd == 'report' or cmd == '5':
                self.show_report()
            elif cmd == 'analyze' or cmd == '6':
                self.show_analyze()
            elif cmd == 'list' or cmd == '7':
                self.show_list()
            elif cmd == 'help' or cmd == '8':
                self.clear_screen()
                self.show_header()
                self.show_commands()
                input("\nPress Enter to continue...")
            elif cmd == 'clear' or cmd == '9':
                continue
            else:
                print(f"❌ Unknown command: {cmd}")
                print("Type 'help' for available commands")
                input("Press Enter to continue...")

def main():
    try:
        dashboard = TermuxJobDashboard()
        dashboard.run()
    except KeyboardInterrupt:
        print("\n\nGoodbye! 👋")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
