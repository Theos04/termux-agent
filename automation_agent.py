#!/usr/bin/env python3
"""
Self-Learning Automation Agent
- Applies to jobs and hackathons
- Learns from successes/failures
- Reminds user of opportunities
- Improves over time
"""

import json
import subprocess
import sys
import os
import time
import math
import hashlib
import re
import sqlite3
import threading
from typing import Optional, Dict, List, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import defaultdict
from pathlib import Path
import pickle

try:
    from dynamic_cdp_5 import EnhancedChromeCDP
except ImportError:
    print("❌ Could not import dynamic_cdp_5.py")
    sys.exit(1)

# ==================== Database Schema ====================

class AutomationDB:
    """SQLite database for persistent memory and learning"""
    
    def __init__(self, db_path: str = "automation_memory.db"):
        self.db_path = db_path
        self.init_db()
    
    def init_db(self):
        """Initialize database schema"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Applications table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS applications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT,
                company TEXT,
                role TEXT,
                url TEXT,
                applied_date TIMESTAMP,
                status TEXT,
                notes TEXT,
                success BOOLEAN,
                workflow_id TEXT
            )
        ''')
        
        # Workflows table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS workflows (
                id TEXT PRIMARY KEY,
                name TEXT,
                description TEXT,
                platform TEXT,
                steps JSON,
                success_count INTEGER DEFAULT 0,
                failure_count INTEGER DEFAULT 0,
                last_used TIMESTAMP,
                created TIMESTAMP,
                updated TIMESTAMP
            )
        ''')
        
        # Exploit performance table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS exploit_performance (
                exploit_name TEXT,
                platform TEXT,
                attempts INTEGER DEFAULT 0,
                successes INTEGER DEFAULT 0,
                failures INTEGER DEFAULT 0,
                total_time REAL DEFAULT 0,
                last_used TIMESTAMP,
                PRIMARY KEY (exploit_name, platform)
            )
        ''')
        
        # Reminders table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                description TEXT,
                due_date TIMESTAMP,
                priority INTEGER DEFAULT 0,
                completed BOOLEAN DEFAULT 0,
                related_to TEXT,
                created TIMESTAMP
            )
        ''')
        
        # Learning patterns table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS learning_patterns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pattern_type TEXT,
                pattern_data JSON,
                confidence REAL,
                occurrences INTEGER DEFAULT 1,
                created TIMESTAMP,
                updated TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
        
        print("📊 Database initialized at", self.db_path)

# ==================== Job/Hackathon Platform Detectors ====================

class PlatformDetector:
    """Detects and handles different job/hackathon platforms"""
    
    @staticmethod
    def detect(url: str) -> str:
        """Detect platform from URL"""
        url_lower = url.lower()
        
        if 'unstop' in url_lower:
            return 'unstop'
        elif 'linkedin' in url_lower:
            return 'linkedin'
        elif 'naukri' in url_lower:
            return 'naukri'
        elif 'indeed' in url_lower:
            return 'indeed'
        elif 'angel.co' in url_lower or 'wellfound' in url_lower:
            return 'wellfound'
        elif 'hackerrank' in url_lower:
            return 'hackerrank'
        elif 'devfolio' in url_lower:
            return 'devfolio'
        elif 'hackathon' in url_lower:
            return 'hackathon'
        else:
            return 'unknown'
    
    @staticmethod
    def get_selectors(platform: str) -> Dict:
        """Get platform-specific selectors"""
        selectors = {
            'unstop': {
                'apply_button': ['button:contains("Apply")', '[data-action="apply"]'],
                'register_button': ['button:contains("Register")', '[data-action="register"]'],
                'job_title': ['.job-title', '.position', 'h1.role'],
                'company': ['.company-name', '.organization'],
                'description': ['.job-description', '.description', '.details'],
                'submit': ['button[type="submit"]', 'button:contains("Submit")'],
                'application_form': ['form.application-form', '#application-form']
            },
            'linkedin': {
                'apply_button': ['button:contains("Apply")', '.jobs-apply-button'],
                'easy_apply': ['button:contains("Easy Apply")'],
                'job_title': ['.job-title', 'h1', '.t-24'],
                'company': ['.company-name', '.t-16', '.job-detail-company'],
                'description': ['.job-description', '.show-more-less-html'],
                'submit': ['button[type="submit"]', '.artdeco-button--primary']
            },
            'naukri': {
                'apply_button': ['button:contains("Apply")', '.apply-button'],
                'job_title': ['.job-title', '.title'],
                'company': ['.company-name', '.subtitle'],
                'description': ['.job-description', '.details'],
                'submit': ['button[type="submit"]', '.applyBtn']
            },
            'wellfound': {
                'apply_button': ['button:contains("Apply")', '[data-action="apply"]'],
                'job_title': ['.job-title', 'h1'],
                'company': ['.company-name', 'a[href*="/company/"]'],
                'description': ['.job-description'],
                'submit': ['button[type="submit"]']
            }
        }
        return selectors.get(platform, {})

# ==================== Memory & Learning System ====================

class LearningMemory:
    """Self-learning system with pattern recognition"""
    
    def __init__(self, db_path: str = "automation_memory.db"):
        self.db = AutomationDB(db_path)
        self.pattern_cache = {}
        self.successful_sequences = []
        
    def record_application(self, platform: str, company: str, role: str, 
                           url: str, success: bool, workflow_id: str = None):
        """Record an application attempt"""
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO applications 
            (platform, company, role, url, applied_date, success, workflow_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (platform, company, role, url, datetime.now(), success, workflow_id))
        
        conn.commit()
        conn.close()
        
        # Update learning patterns
        self._update_patterns(platform, success)
    
    def record_workflow_result(self, workflow_id: str, success: bool):
        """Record workflow success/failure"""
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()
        
        if success:
            cursor.execute('''
                UPDATE workflows SET success_count = success_count + 1, 
                last_used = ? WHERE id = ?
            ''', (datetime.now(), workflow_id))
        else:
            cursor.execute('''
                UPDATE workflows SET failure_count = failure_count + 1,
                last_used = ? WHERE id = ?
            ''', (datetime.now(), workflow_id))
        
        conn.commit()
        conn.close()
    
    def record_exploit_performance(self, exploit_name: str, platform: str, 
                                   success: bool, time_taken: float):
        """Record exploit performance for learning"""
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO exploit_performance 
            (exploit_name, platform, attempts, successes, failures, total_time, last_used)
            VALUES (?, ?, 1, ?, ?, ?, ?)
            ON CONFLICT(exploit_name, platform) DO UPDATE SET
                attempts = attempts + 1,
                successes = successes + ?,
                failures = failures + ?,
                total_time = total_time + ?,
                last_used = ?
        ''', (exploit_name, platform, 
             1 if success else 0, 0 if success else 1,
             time_taken, datetime.now(),
             1 if success else 0, 0 if success else 1,
             time_taken, datetime.now()))
        
        conn.commit()
        conn.close()
    
    def get_best_exploits(self, platform: str, min_attempts: int = 3) -> List[Tuple[str, float]]:
        """Get best performing exploits for a platform"""
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT exploit_name, 
                   CAST(successes AS FLOAT) / attempts as success_rate,
                   attempts,
                   total_time / attempts as avg_time
            FROM exploit_performance
            WHERE platform = ? AND attempts >= ?
            ORDER BY success_rate DESC, avg_time ASC
        ''', (platform, min_attempts))
        
        results = cursor.fetchall()
        conn.close()
        
        return [(row[0], row[1]) for row in results]
    
    def _update_patterns(self, platform: str, success: bool):
        """Update learning patterns based on outcomes"""
        # Track success patterns
        pattern_key = f"{platform}_success"
        if pattern_key not in self.pattern_cache:
            self.pattern_cache[pattern_key] = {
                'total': 0,
                'successes': 0
            }
        
        self.pattern_cache[pattern_key]['total'] += 1
        if success:
            self.pattern_cache[pattern_key]['successes'] += 1
        
        # Store in database if we have enough data
        if self.pattern_cache[pattern_key]['total'] % 5 == 0:
            self._store_pattern(platform, self.pattern_cache[pattern_key])
    
    def _store_pattern(self, platform: str, data: Dict):
        """Store learning pattern in database"""
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()
        
        success_rate = data['successes'] / data['total'] if data['total'] > 0 else 0
        
        cursor.execute('''
            INSERT INTO learning_patterns 
            (pattern_type, pattern_data, confidence, occurrences)
            VALUES (?, ?, ?, ?)
            ON CONFLICT DO UPDATE SET
                confidence = ?,
                occurrences = occurrences + 1,
                updated = ?
        ''', ('platform_success', json.dumps({platform: data}),
              success_rate, data['total'],
              success_rate, datetime.now()))
        
        conn.commit()
        conn.close()
    
    def get_reminders(self, days_ahead: int = 7) -> List[Dict]:
        """Get upcoming reminders"""
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()
        
        cutoff = datetime.now() + timedelta(days=days_ahead)
        
        cursor.execute('''
            SELECT id, title, description, due_date, priority, related_to
            FROM reminders
            WHERE due_date <= ? AND completed = 0
            ORDER BY priority DESC, due_date ASC
        ''', (cutoff.isoformat(),))
        
        results = cursor.fetchall()
        conn.close()
        
        return [{
            'id': r[0],
            'title': r[1],
            'description': r[2],
            'due_date': r[3],
            'priority': r[4],
            'related_to': r[5]
        } for r in results]
    
    def add_reminder(self, title: str, description: str, 
                     days_until: int, priority: int = 0,
                     related_to: str = None):
        """Add a new reminder"""
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()
        
        due_date = datetime.now() + timedelta(days=days_until)
        
        cursor.execute('''
            INSERT INTO reminders 
            (title, description, due_date, priority, related_to, created)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (title, description, due_date.isoformat(), 
              priority, related_to, datetime.now()))
        
        conn.commit()
        conn.close()

# ==================== Self-Learning Automation Agent ====================

class SelfLearningAgent:
    """Complete self-learning automation system"""
    
    def __init__(self, cdp: EnhancedChromeCDP, 
                 exploit_library_path: str = ".",
                 db_path: str = "automation_memory.db"):
        
        self.cdp = cdp
        self.current_tab = 0
        self.platform_detector = PlatformDetector()
        self.memory = LearningMemory(db_path)
        
        # Import exploit library
        try:
            from ultimate_agent import EnhancedExploitLibrary
            self.exploit_library = EnhancedExploitLibrary(exploit_library_path)
        except ImportError:
            print("⚠️ Could not import EnhancedExploitLibrary, using basic")
            self.exploit_library = None
        
        # Workflow cache
        self.workflow_cache = {}
        
        # Statistics
        self.stats = {
            'applications': 0,
            'successful_applications': 0,
            'failed_applications': 0,
            'workflows_executed': 0,
            'exploits_used': {}
        }
        
        print("🧠 Self-Learning Automation Agent initialized")
        print(f"   Memory DB: {db_path}")
        print(f"   Exploit library: {exploit_library_path}")
    
    def analyze_opportunity(self, tab_index: int = None) -> Dict:
        """Analyze current page for job/hackathon opportunities"""
        if tab_index is None:
            tab_index = self.current_tab
        
        print("🔍 Analyzing opportunity...")
        
        # Get page context
        script = """
        (function() {
            return {
                url: window.location.href,
                title: document.title,
                bodyText: document.body ? document.body.innerText.substring(0, 2000) : '',
                hasApplyButton: !!document.querySelector('button[class*="apply"], button[class*="Apply"], a[href*="apply"]'),
                hasRegisterButton: !!document.querySelector('button[class*="register"], button[class*="Register"], a[href*="register"]'),
                hasJobTitle: !!document.querySelector('h1, h2, .job-title, .position, .role, .title')
            };
        })();
        """
        
        page_info = self.cdp.evaluate_script(script, tab_index)
        if not page_info:
            return {'error': 'Could not get page info'}
        
        # Detect platform
        platform = self.platform_detector.detect(page_info.get('url', ''))
        
        # Extract opportunity details
        opportunity = {
            'url': page_info.get('url', ''),
            'title': page_info.get('title', ''),
            'platform': platform,
            'has_apply_button': page_info.get('hasApplyButton', False),
            'has_register_button': page_info.get('hasRegisterButton', False),
            'text_sample': page_info.get('bodyText', '')[:500],
            'timestamp': datetime.now().isoformat()
        }
        
        # Try to extract company and role
        text = page_info.get('bodyText', '').lower()
        
        # Common job patterns
        job_patterns = [
            r'(?:job|position|role|hiring)\s*(?:for)?\s*:?\s*([^\n,.]+)',
            r'we\'re\s+hiring\s+([^\n,.]+)',
            r'apply\s+for\s+([^\n,.]+)',
        ]
        
        for pattern in job_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                opportunity['role'] = match.group(1).strip()
                break
        
        # Try to extract company
        company_patterns = [
            r'(?:at|with)\s+([A-Z][A-Za-z\s&.]+)',
            r'([A-Z][A-Za-z\s&.]+)\s+(?:is\s+)?(?:hiring|looking)',
        ]
        
        for pattern in company_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                opportunity['company'] = match.group(1).strip()
                break
        
        print(f"\n📋 Opportunity Analysis:")
        print(f"  Platform: {platform}")
        print(f"  Has Apply: {opportunity['has_apply_button']}")
        print(f"  Has Register: {opportunity['has_register_button']}")
        if 'role' in opportunity:
            print(f"  Role: {opportunity['role']}")
        if 'company' in opportunity:
            print(f"  Company: {opportunity['company']}")
        
        return opportunity
    
    def apply_to_opportunity(self, opportunity: Dict, 
                            resume_data: Dict = None,
                            tab_index: int = None) -> Dict:
        """Apply to a job or hackathon opportunity"""
        if tab_index is None:
            tab_index = self.current_tab
        
        platform = opportunity.get('platform', 'unknown')
        print(f"\n🎯 Applying to {platform} opportunity...")
        
        # Get platform-specific selectors
        selectors = self.platform_detector.get_selectors(platform)
        
        # Determine if this is a job or hackathon
        is_hackathon = 'hackathon' in opportunity.get('title', '').lower()
        
        if is_hackathon:
            print("🏆 Detected as hackathon opportunity")
            result = self._apply_hackathon(opportunity, selectors, tab_index)
        else:
            print("💼 Detected as job opportunity")
            result = self._apply_job(opportunity, selectors, resume_data, tab_index)
        
        # Record the application
        success = result.get('success', False)
        self.memory.record_application(
            platform=platform,
            company=opportunity.get('company', 'Unknown'),
            role=opportunity.get('role', 'Unknown'),
            url=opportunity.get('url', ''),
            success=success,
            workflow_id=result.get('workflow_id')
        )
        
        # Update statistics
        self.stats['applications'] += 1
        if success:
            self.stats['successful_applications'] += 1
        else:
            self.stats['failed_applications'] += 1
        
        return result
    
    def _apply_job(self, opportunity: Dict, selectors: Dict, 
                   resume_data: Dict, tab_index: int) -> Dict:
        """Apply to a job"""
        print("📝 Starting job application...")
        
        try:
            # 1. Find and click apply button
            apply_buttons = selectors.get('apply_button', ['button:contains("Apply")'])
            clicked = False
            
            for selector in apply_buttons:
                script = f"""
                (function() {{
                    const el = document.querySelector('{selector}');
                    if (el) {{
                        el.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                        setTimeout(() => {{
                            el.click();
                        }}, 500);
                        return true;
                    }}
                    return false;
                }})();
                """
                result = self.cdp.evaluate_script(script, tab_index)
                if result:
                    clicked = True
                    print(f"   ✅ Clicked apply button: {selector}")
                    break
            
            if not clicked:
                return {'success': False, 'error': 'Could not find apply button'}
            
            # Wait for form to load
            time.sleep(2)
            
            # 2. Fill form if resume data provided
            if resume_data:
                filled = self._fill_application_form(resume_data, selectors, tab_index)
                if not filled:
                    print("   ⚠️ Could not fill all form fields")
            
            # 3. Submit application
            submit_script = f"""
            (function() {{
                const submitBtn = document.querySelector('{selectors.get('submit', ['button[type="submit"]'])[0]}');
                if (submitBtn) {{
                    submitBtn.click();
                    return true;
                }}
                return false;
            }})();
            """
            submitted = self.cdp.evaluate_script(submit_script, tab_index)
            
            if submitted:
                print("   ✅ Application submitted!")
                return {
                    'success': True,
                    'workflow_id': f"job_{opportunity.get('company', '')}_{int(time.time())}"
                }
            else:
                return {'success': False, 'error': 'Could not submit application'}
                
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _apply_hackathon(self, opportunity: Dict, selectors: Dict, tab_index: int) -> Dict:
        """Register for a hackathon"""
        print("🏆 Starting hackathon registration...")
        
        try:
            # 1. Find register button
            register_buttons = selectors.get('register_button', ['button:contains("Register")'])
            clicked = False
            
            for selector in register_buttons:
                script = f"""
                (function() {{
                    const el = document.querySelector('{selector}');
                    if (el) {{
                        el.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                        setTimeout(() => {{
                            el.click();
                        }}, 500);
                        return true;
                    }}
                    return false;
                }})();
                """
                result = self.cdp.evaluate_script(script, tab_index)
                if result:
                    clicked = True
                    print(f"   ✅ Clicked register button: {selector}")
                    break
            
            if not clicked:
                return {'success': False, 'error': 'Could not find register button'}
            
            # Wait for registration form
            time.sleep(2)
            
            # 2. Check if team registration or individual
            is_team = self._detect_team_registration(tab_index)
            
            if is_team:
                print("   👥 Team registration detected")
                # Could add team member filling here
            
            # 3. Submit registration
            submit_script = f"""
            (function() {{
                const submitBtn = document.querySelector('button[type="submit"], button:contains("Submit"), button:contains("Register")');
                if (submitBtn) {{
                    submitBtn.click();
                    return true;
                }}
                return false;
            }})();
            """
            submitted = self.cdp.evaluate_script(submit_script, tab_index)
            
            if submitted:
                print("   ✅ Hackathon registration submitted!")
                return {
                    'success': True,
                    'workflow_id': f"hackathon_{opportunity.get('title', '')[:20]}_{int(time.time())}"
                }
            else:
                return {'success': False, 'error': 'Could not submit registration'}
                
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _fill_application_form(self, resume_data: Dict, selectors: Dict, tab_index: int) -> bool:
        """Fill application form with resume data"""
        filled = False
        
        # Common form fields mapping
        field_mapping = {
            'name': ['input[name*="name" i]', 'input[placeholder*="name" i]'],
            'email': ['input[name*="email" i]', 'input[type="email"]'],
            'phone': ['input[name*="phone" i]', 'input[name*="mobile" i]', 'input[type="tel"]'],
            'experience': ['textarea[name*="experience" i]', 'textarea[name*="exp" i]'],
            'skills': ['textarea[name*="skills" i]', 'input[name*="skills" i]'],
            'education': ['textarea[name*="education" i]', 'input[name*="education" i]'],
            'linkedin': ['input[name*="linkedin" i]', 'input[placeholder*="linkedin" i]'],
            'portfolio': ['input[name*="portfolio" i]', 'input[placeholder*="portfolio" i]'],
        }
        
        for field, value in resume_data.items():
            if field in field_mapping:
                for selector in field_mapping[field]:
                    script = f"""
                    (function() {{
                        const el = document.querySelector('{selector}');
                        if (el) {{
                            el.value = `{value}`;
                            el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                            el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                            return true;
                        }}
                        return false;
                    }})();
                    """
                    result = self.cdp.evaluate_script(script, tab_index)
                    if result:
                        print(f"   ✅ Filled {field}")
                        filled = True
                        break
        
        return filled
    
    def _detect_team_registration(self, tab_index: int) -> bool:
        """Detect if registration requires team information"""
        script = """
        (function() {
            const teamIndicators = [
                'team',
                'members',
                'teammate',
                'team_size',
                'team_name'
            ];
            
            const text = document.body ? document.body.innerText.toLowerCase() : '';
            const hasTeamIndicators = teamIndicators.some(ind => text.includes(ind));
            
            const hasTeamFields = !!document.querySelector(
                'input[name*="team" i], input[name*="member" i], input[placeholder*="team" i]'
            );
            
            return hasTeamIndicators || hasTeamFields;
        })();
        """
        result = self.cdp.evaluate_script(script, tab_index)
        return bool(result)
    
    def learn_from_application(self, application_result: Dict):
        """Learn from application outcome"""
        if application_result.get('success', False):
            print("🧠 Learning from successful application...")
            # Store successful pattern
            self.memory._store_pattern(
                application_result.get('platform', 'unknown'),
                {'successes': 1, 'total': 1, 'type': 'successful_application'}
            )
            
            # Add follow-up reminder
            if application_result.get('workflow_id'):
                self.memory.add_reminder(
                    title="Follow up on application",
                    description=f"Check status of application #{application_result['workflow_id']}",
                    days_until=7,
                    priority=2,
                    related_to=application_result['workflow_id']
                )
        else:
            print("🧠 Learning from failed application...")
            # Learn from failure
            self.memory._store_pattern(
                application_result.get('platform', 'unknown'),
                {'failures': 1, 'total': 1, 'type': 'failed_application'}
            )
    
    def discover_opportunities(self, 
                              platforms: List[str] = None,
                              max_pages: int = 5) -> List[Dict]:
        """Discover new opportunities on platforms"""
        if platforms is None:
            platforms = ['unstop', 'linkedin', 'wellfound']
        
        opportunities = []
        
        for platform in platforms:
            print(f"\n🔍 Scanning {platform}...")
            
            # Navigate to platform's opportunities page
            urls = {
                'unstop': 'https://unstop.com/opportunities',
                'linkedin': 'https://www.linkedin.com/jobs/',
                'wellfound': 'https://wellfound.com/jobs'
            }
            
            if platform in urls:
                # Navigate to URL
                script = f"window.location.href = '{urls[platform]}';"
                self.cdp.evaluate_script(script, self.current_tab)
                time.sleep(3)
                
                # Extract opportunities
                opps = self._extract_opportunities_from_page(platform)
                opportunities.extend(opps)
                print(f"   Found {len(opps)} opportunities")
        
        return opportunities
    
    def _extract_opportunities_from_page(self, platform: str) -> List[Dict]:
        """Extract opportunity listings from current page"""
        # Platform-specific extraction scripts
        extractors = {
            'unstop': """
            (function() {
                const opportunities = [];
                const cards = document.querySelectorAll('.card, .opportunity-card, .listing-item');
                cards.forEach(card => {
                    const title = card.querySelector('h3, h4, .title')?.textContent?.trim() || '';
                    const company = card.querySelector('.company, .organization')?.textContent?.trim() || '';
                    const link = card.querySelector('a[href*="/opportunity/"]')?.getAttribute('href') || '';
                    opportunities.push({ title, company, link, platform: 'unstop' });
                });
                return opportunities;
            })();
            """
        }
        
        script = extractors.get(platform, """
        (function() {
            const opportunities = [];
            const cards = document.querySelectorAll('.job-card, .listing-card, article, [class*="opportunity"]');
            cards.forEach(card => {
                const title = card.querySelector('h1, h2, h3, .title')?.textContent?.trim() || '';
                const company = card.querySelector('.company, .org, [class*="company"]')?.textContent?.trim() || '';
                const link = card.querySelector('a[href]')?.getAttribute('href') || '';
                if (title || company) {
                    opportunities.push({ title, company, link, platform: 'unknown' });
                }
            });
            return opportunities;
        })();
        """)
        
        result = self.cdp.evaluate_script(script, self.current_tab)
        return result if result else []
    
    def schedule_reminders(self):
        """Schedule intelligent reminders based on patterns"""
        print("⏰ Scheduling reminders...")
        
        # Check for pending follow-ups
        reminders = self.memory.get_reminders(days_ahead=30)
        
        if reminders:
            print(f"   Found {len(reminders)} upcoming reminders:")
            for reminder in reminders[:5]:
                days_until = (datetime.fromisoformat(reminder['due_date']) - datetime.now()).days
                print(f"   • {reminder['title']} (in {days_until} days)")
        
        return reminders
    
    def get_application_statistics(self) -> Dict:
        """Get application statistics"""
        conn = sqlite3.connect(self.memory.db.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successful,
                platform,
                COUNT(*) as platform_count
            FROM applications
            GROUP BY platform
        ''')
        
        results = cursor.fetchall()
        conn.close()
        
        stats = {
            'total_applications': sum(r[0] for r in results),
            'successful_applications': sum(r[1] for r in results),
            'platforms': {}
        }
        
        for row in results:
            stats['platforms'][row[2]] = {
                'total': row[3],
                'successful': row[1]
            }
        
        return stats

# ==================== Main Interface ====================

def main():
    from dynamic_cdp_5 import EnhancedChromeCDP
    
    print("🧠 Self-Learning Automation Agent")
    print("=" * 70)
    print("Features:")
    print("  ✅ Auto-apply to jobs and hackathons")
    print("  ✅ Learn from successes and failures")
    print("  ✅ Schedule reminders and follow-ups")
    print("  ✅ Discover new opportunities")
    print("  ✅ Platform-specific automation")
    print("=" * 70)
    
    # Connect to Chrome
    port_input = input("\n🔌 Chrome debug port (default 9227): ").strip()
    port = int(port_input) if port_input else 9227
    
    cdp = EnhancedChromeCDP(port)
    tabs = cdp.get_tabs()
    
    if not tabs:
        print(f"\n❌ No tabs found. Start Chrome with:")
        print(f"   chromium-browser --remote-debugging-port={port}")
        return
    
    print(f"\n✅ Found {len(tabs)} tabs")
    cdp.list_tabs()
    
    tab_input = input(f"\n📑 Select tab (0-{len(tabs)-1}, default 0): ").strip()
    tab_index = int(tab_input) if tab_input else 0
    
    # Initialize agent
    agent = SelfLearningAgent(
        cdp=cdp,
        exploit_library_path=".",
        db_path="automation_memory.db"
    )
    agent.current_tab = tab_index
    
    # Resume data template
    resume_data = {
        'name': "John Doe",
        'email': "john.doe@email.com",
        'phone': "+1234567890",
        'experience': "5 years of software development",
        'skills': "Python, JavaScript, React, Node.js",
        'education': "B.S. Computer Science",
        'linkedin': "linkedin.com/in/johndoe",
        'portfolio': "github.com/johndoe"
    }
    
    while True:
        print("\n" + "=" * 70)
        print("🧠 Self-Learning Agent Menu")
        print("  1. Analyze current page (opportunity)")
        print("  2. Apply to job/hackathon")
        print("  3. Discover opportunities")
        print("  4. Check reminders")
        print("  5. View statistics")
        print("  6. View application history")
        print("  7. Update resume data")
        print("  8. Learn from past applications")
        print("  9. Run automated scan")
        print("  0. Exit")
        print("=" * 70)
        
        choice = input("Select option: ").strip()
        
        if choice == "0":
            print("👋 Goodbye!")
            break
        
        elif choice == "1":
            opp = agent.analyze_opportunity(tab_index)
            if opp and 'error' not in opp:
                print("\n📋 Opportunity Details:")
                for key, value in opp.items():
                    if key != 'text_sample':
                        print(f"  {key}: {value}")
                
                # Ask if user wants to apply
                apply_now = input("\n🎯 Apply to this opportunity? (y/n): ").strip().lower()
                if apply_now == 'y':
                    result = agent.apply_to_opportunity(opp, resume_data, tab_index)
                    print(f"\n📊 Application Result: {'✅ Success' if result.get('success') else '❌ Failed'}")
                    agent.learn_from_application(result)
        
        elif choice == "2":
            opp = agent.analyze_opportunity(tab_index)
            if opp and 'error' not in opp:
                confirm = input(f"\nApply to {opp.get('platform', 'this')} opportunity? (y/n): ").strip().lower()
                if confirm == 'y':
                    result = agent.apply_to_opportunity(opp, resume_data, tab_index)
                    print(f"\n📊 Application Result: {'✅ Success' if result.get('success') else '❌ Failed'}")
                    agent.learn_from_application(result)
        
        elif choice == "3":
            platforms = input("Platforms to scan (comma-separated, default: unstop,linkedin,wellfound): ").strip()
            if platforms:
                platforms = [p.strip() for p in platforms.split(',')]
            else:
                platforms = ['unstop', 'linkedin', 'wellfound']
            
            opps = agent.discover_opportunities(platforms)
            print(f"\n📋 Found {len(opps)} opportunities:")
            for i, opp in enumerate(opps[:10], 1):
                print(f"  {i}. {opp.get('title', 'Unknown')} at {opp.get('company', 'Unknown')}")
            if len(opps) > 10:
                print(f"  ... and {len(opps)-10} more")
        
        elif choice == "4":
            reminders = agent.schedule_reminders()
            if reminders:
                print("\n⏰ Upcoming Reminders:")
                for r in reminders:
                    days = (datetime.fromisoformat(r['due_date']) - datetime.now()).days
                    priority = "🔴" if r['priority'] >= 2 else "🟡" if r['priority'] >= 1 else "🟢"
                    print(f"  {priority} {r['title']} (in {days} days)")
                    print(f"     {r['description']}")
            else:
                print("✅ No upcoming reminders")
        
        elif choice == "5":
            stats = agent.get_application_statistics()
            print("\n📊 Application Statistics:")
            print(f"  Total applications: {stats['total_applications']}")
            print(f"  Successful: {stats['successful_applications']}")
            if stats['total_applications'] > 0:
                print(f"  Success rate: {stats['successful_applications']/stats['total_applications']:.1%}")
            print("\n  By Platform:")
            for platform, data in stats['platforms'].items():
                print(f"    {platform}: {data['successful']}/{data['total']} successful")
        
        elif choice == "6":
            conn = sqlite3.connect(agent.memory.db.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, platform, company, role, applied_date, success
                FROM applications
                ORDER BY applied_date DESC
                LIMIT 20
            ''')
            results = cursor.fetchall()
            conn.close()
            
            print("\n📋 Recent Applications:")
            for row in results:
                status = "✅" if row[5] else "❌"
                date = datetime.fromisoformat(row[3]).strftime("%Y-%m-%d")
                print(f"  {status} {row[1]} - {row[2]} ({row[3][:30]}) - {date}")
        
        elif choice == "7":
            print("\n📝 Update Resume Data:")
            for key in resume_data.keys():
                current = resume_data[key]
                new = input(f"  {key} (current: {current}): ").strip()
                if new:
                    resume_data[key] = new
            print("✅ Resume data updated")
        
        elif choice == "8":
            print("\n🧠 Learning Analysis:")
            # Show success patterns
            conn = sqlite3.connect(agent.memory.db.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT platform, 
                       CAST(SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) AS FLOAT) / COUNT(*) as rate,
                       COUNT(*) as total
                FROM applications
                GROUP BY platform
                ORDER BY rate DESC
            ''')
            
            results = cursor.fetchall()
            conn.close()
            
            print("  Success rates by platform:")
            for platform, rate, total in results:
                bar = "█" * int(rate * 20) + "░" * (20 - int(rate * 20))
                print(f"    {platform:10} {bar} {rate:.1%} ({total} attempts)")
        
        elif choice == "9":
            print("\n🚀 Running Automated Scan...")
            print("This will scan for opportunities and apply automatically")
            
            # Get user preferences
            max_applications = int(input("Max applications to submit: ").strip() or "5")
            platforms = input("Platforms (comma-separated, default: unstop,linkedin): ").strip()
            if platforms:
                platforms = [p.strip() for p in platforms.split(',')]
            else:
                platforms = ['unstop', 'linkedin']
            
            applications_submitted = 0
            
            for platform in platforms:
                if applications_submitted >= max_applications:
                    break
                    
                print(f"\n🔍 Scanning {platform}...")
                opps = agent._extract_opportunities_from_page(platform)
                
                for opp in opps[:3]:  # Limit per platform
                    if applications_submitted >= max_applications:
                        break
                    
                    print(f"\n📋 Applying to: {opp.get('title', 'Unknown')}")
                    result = agent.apply_to_opportunity(
                        {'platform': platform, 'title': opp.get('title', ''), 'url': opp.get('link', '')},
                        resume_data,
                        tab_index
                    )
                    
                    if result.get('success', False):
                        applications_submitted += 1
                        print(f"✅ Application #{applications_submitted} submitted!")
                        agent.learn_from_application(result)
                    else:
                        print(f"❌ Application failed: {result.get('error', 'Unknown error')}")
                    
                    # Wait between applications
                    time.sleep(3)
            
            print(f"\n📊 Scan Complete: Submitted {applications_submitted} applications")
        
        else:
            print("❌ Invalid choice")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Interrupted. Goodbye!")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
