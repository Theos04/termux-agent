#!/usr/bin/env python3
"""
gdork - Professional Google Dorking CLI Tool for Bug Bounty
Organized dorking categories for efficient reconnaissance
"""

import argparse
import json
import sys
import webbrowser
from urllib.parse import quote_plus
import requests
from bs4 import BeautifulSoup
import time
from datetime import datetime
from typing import List, Dict, Optional
import os
from tabulate import tabulate

class DorkGenerator:
    """Generate organized dork queries by category"""
    
    def __init__(self, domain: str, verbose: bool = False):
        self.domain = domain
        self.verbose = verbose
        self.queries = {
            'domain': [],
            'files': [],
            'urls': [],
            'titles': [],
            'text': [],
            'dates': [],
            'technology': [],
            'documents': [],
            'cloud': [],
            'subdomains': [],
            'exposures': [],
            'custom': []
        }
    
    def generate_all(self):
        """Generate all dork categories"""
        self.generate_domain_queries()
        self.generate_file_queries()
        self.generate_url_queries()
        self.generate_title_queries()
        self.generate_text_queries()
        self.generate_date_queries()
        self.generate_technology_queries()
        self.generate_document_queries()
        self.generate_cloud_queries()
        self.generate_subdomain_queries()
        self.generate_exposure_queries()
        return self.queries
    
    def generate_domain_queries(self):
        """Generate domain-specific queries"""
        self.queries['domain'] = [
            f"site:{self.domain}",
            f"site:{self.domain} -www",
            f"site:*.{self.domain}",
            f"site:{self.domain} inurl:https",
        ]
    
    def generate_file_queries(self):
        """Generate file-type discovery queries"""
        files = {
            'Documents': ['pdf', 'doc', 'docx', 'txt', 'rtf', 'odt'],
            'Spreadsheets': ['xls', 'xlsx', 'csv', 'ods'],
            'Presentations': ['ppt', 'pptx', 'odp'],
            'Configurations': ['conf', 'config', 'ini', 'cfg', 'env', 'yaml', 'yml', 'json', 'xml'],
            'Code': ['js', 'css', 'html', 'htm', 'php', 'asp', 'aspx', 'jsp', 'do', 'py', 'rb', 'go'],
            'Backups': ['bak', 'backup', 'old', 'orig', 'swp'],
            'Logs': ['log', 'logs'],
            'Database': ['sql', 'db', 'sqlite', 'mdb'],
            'Archives': ['zip', 'rar', '7z', 'tar', 'gz'],
            'Certificates': ['pem', 'crt', 'cer', 'key', 'p12'],
        }
        
        for category, extensions in files.items():
            for ext in extensions:
                self.queries['files'].append(f"site:{self.domain} filetype:{ext}")
    
    def generate_url_queries(self):
        """Generate URL-based discovery queries"""
        url_patterns = [
            'admin', 'login', 'signin', 'auth', 'authenticate',
            'api', 'api/v1', 'api/v2', 'v1', 'v2', 'v3',
            'dashboard', 'panel', 'console', 'adminpanel',
            'upload', 'download', 'file', 'files',
            'backup', 'backups', 'export', 'import',
            'config', 'configuration', 'settings',
            'test', 'tests', 'debug', 'dev', 'staging',
            'internal', 'private', 'secret', 'hidden',
            'status', 'health', 'metrics', 'monitoring',
            'docs', 'documentation', 'help', 'support',
            'register', 'signup', 'reset', 'forgot',
            'profile', 'user', 'users', 'account',
            'order', 'payment', 'checkout', 'cart',
            'search', 'query', 'filter', 'sort',
            'reports', 'analytics', 'statistics',
            'upload', 'media', 'images', 'assets',
            'cgi-bin', 'scripts', 'includes',
            'wp-admin', 'wp-login', 'wp-content',
            'sql', 'database', 'db', 'mysql', 'postgres',
        ]
        
        for pattern in url_patterns:
            self.queries['urls'].append(f"site:{self.domain} inurl:{pattern}")
        
        # Advanced URL patterns
        self.queries['urls'].extend([
            f'site:{self.domain} inurl:"id="',
            f'site:{self.domain} inurl:"page="',
            f'site:{self.domain} inurl:"view="',
            f'site:{self.domain} inurl:"lang="',
            f'site:{self.domain} inurl:"q="',
            f'site:{self.domain} inurl:"s="',
            f'site:{self.domain} inurl:"cmd="',
            f'site:{self.domain} inurl:"exec="',
            f'site:{self.domain} inurl:"query="',
        ])
    
    def generate_title_queries(self):
        """Generate title-based discovery queries"""
        title_patterns = [
            'login', 'admin', 'dashboard', 'home', 'index',
            'welcome', 'sign in', 'sign up', 'register',
            'error', 'not found', '404', '500',
            'internal server error', 'database error',
            'phpmyadmin', 'phpinfo', 'mysql', 'postgresql',
            'aws', 'azure', 'gcp', 'cloud',
            'gitlab', 'github', 'bitbucket', 'jenkins',
            'confluence', 'jira', 'wiki', 'docs',
            'test', 'testing', 'staging', 'dev',
            'api documentation', 'swagger', 'openapi',
            'grafana', 'kibana', 'elasticsearch',
            'kibana', 'prometheus', 'alertmanager',
            'control panel', 'webmail', 'mail',
            'ftp', 'sftp', 'ssh', 'telnet',
        ]
        
        for pattern in title_patterns:
            self.queries['titles'].append(f'site:{self.domain} intitle:"{pattern}"')
        
        # Advanced title patterns
        self.queries['titles'].extend([
            f'site:{self.domain} intitle:"index of"',
            f'site:{self.domain} intitle:"parent directory"',
            f'site:{self.domain} intitle:"dashboard" "admin"',
            f'site:{self.domain} intitle:"login" "password"',
        ])
    
    def generate_text_queries(self):
        """Generate content-based discovery queries"""
        text_patterns = [
            'password', 'username', 'email', 'phone',
            'database', 'mysql', 'postgresql', 'mongodb',
            'secret', 'key', 'api_key', 'api-key',
            'token', 'bearer', 'authorization',
            'config', 'configuration', 'settings',
            'internal', 'confidential', 'private',
            'bug', 'issue', 'todo', 'fixme',
            'test', 'testing', 'staging', 'dev',
            'admin', 'root', 'superuser',
            'aws_access_key', 'aws_secret_key',
            'azure', 'gcp', 'cloud',
            'db_host', 'db_user', 'db_pass',
            'ftp', 'sftp', 'ssh', 'telnet',
            'crypto', 'encrypt', 'decrypt',
            'ssl', 'tls', 'certificate',
            'oauth', 'openid', 'saml',
            'jwt', 'session', 'cookie',
            'error', 'exception', 'warning',
            'debug', 'verbose', 'trace',
            'http', 'https', 'api', 'rest',
        ]
        
        for pattern in text_patterns:
            self.queries['text'].append(f'site:{self.domain} intext:"{pattern}"')
        
        # Advanced text patterns
        self.queries['text'].extend([
            f'site:{self.domain} intext:"sql syntax"',
            f'site:{self.domain} intext:"mysql_fetch"',
            f'site:{self.domain} intext:"postgresql" "error"',
            f'site:{self.domain} intext:"Warning: mysql"',
            f'site:{self.domain} intext:"PHP error"',
            f'site:{self.domain} intext:"Stack trace"',
        ])
    
    def generate_date_queries(self):
        """Generate date-based queries"""
        import datetime
        current_year = datetime.datetime.now().year
        
        self.queries['dates'] = [
            f'site:{self.domain} daterange:1-1-2020-1-1-2021',
            f'site:{self.domain} daterange:1-1-2021-1-1-2022',
            f'site:{self.domain} daterange:1-1-2022-1-1-2023',
            f'site:{self.domain} daterange:1-1-2023-1-1-2024',
            f'site:{self.domain} daterange:1-1-2024-1-1-2025',
            f'site:{self.domain} before:2020-01-01',
            f'site:{self.domain} after:2024-01-01',
        ]
    
    def generate_technology_queries(self):
        """Generate technology fingerprinting queries"""
        technologies = {
            'WordPress': [
                'wp-content', 'wp-includes', 'wp-admin',
                'wp-json', 'wp-login', 'wp-config'
            ],
            'Drupal': [
                'sites/all', 'sites/default', 'drupal',
                'user/register', 'user/login'
            ],
            'Joomla': [
                'administrator', 'components/com_',
                'modules/mod_', 'plugins/'
            ],
            'Magento': [
                'skin/frontend', 'app/code', 'magento'
            ],
            'Laravel': [
                'laravel', 'laravel-admin', 'laravel-login'
            ],
            'Django': [
                'django', 'admin', 'static/admin'
            ],
            'Ruby on Rails': [
                'rails', 'assets', 'rails_admin'
            ],
            'Node.js': [
                'node_modules', 'package.json', 'npm'
            ],
            'Express.js': [
                'express', 'routes', 'controllers'
            ],
            'Flask': [
                'flask', 'static/flask', 'flask-admin'
            ],
            'Spring Boot': [
                'spring', 'actuator', 'swagger-ui'
            ],
            'Angular': [
                'angular', 'angular.json', 'ngx-'
            ],
            'React': [
                'react', 'bundle.js', 'react-dom'
            ],
            'Vue.js': [
                'vue', 'vue.js', 'app.js'
            ],
            'AWS S3': [
                's3.amazonaws.com', 's3-website', 'bucket'
            ],
            'CloudFront': [
                'cloudfront.net', 'distribution'
            ],
            'Firebase': [
                'firebase', 'firebaseio.com', 'firebaseapp.com'
            ],
        }
        
        for tech, patterns in technologies.items():
            for pattern in patterns:
                self.queries['technology'].append(f'site:{self.domain} {pattern}')
    
    def generate_document_queries(self):
        """Generate document discovery queries"""
        document_types = {
            'Policies': ['policy', 'security', 'privacy', 'terms', 'legal'],
            'Manuals': ['manual', 'guide', 'tutorial', 'documentation'],
            'Reports': ['report', 'analysis', 'summary', 'review'],
            'Presentations': ['presentation', 'slide', 'deck', 'slides'],
            'Financial': ['invoice', 'receipt', 'payment', 'purchase'],
            'Employee': ['employee', 'staff', 'hr', 'human_resources'],
            'Technical': ['specification', 'design', 'architecture', 'diagram'],
            'Contracts': ['contract', 'agreement', 'nda', 'moa'],
            'Procedures': ['procedure', 'process', 'workflow', 'sop'],
            'Knowledge': ['wiki', 'knowledge', 'faq', 'help'],
        }
        
        for category, keywords in document_types.items():
            for keyword in keywords:
                self.queries['documents'].append(f'site:{self.domain} {keyword}')
                # Also try with file types
                for ext in ['pdf', 'docx', 'xlsx', 'txt']:
                    self.queries['documents'].append(f'site:{self.domain} {keyword} filetype:{ext}')
    
    def generate_cloud_queries(self):
        """Generate cloud service discovery queries"""
        cloud_patterns = {
            'AWS': [
                's3.amazonaws.com', 'aws.amazon.com', 'ec2.amazonaws.com',
                'elasticbeanstalk.com', 'cloudfront.net', 'amazonaws.com'
            ],
            'Azure': [
                'azure.com', 'azurewebsites.net', 'cloudapp.azure.com',
                'azureedge.net', 'blob.core.windows.net'
            ],
            'GCP': [
                'googleapis.com', 'appspot.com', 'googlecloud.com',
                'cloudfunctions.net', 'run.app'
            ],
            'DigitalOcean': [
                'digitalocean.com', 'digitaloceanspaces.com'
            ],
            'Heroku': [
                'herokuapp.com', 'heroku.com'
            ],
            'Netlify': [
                'netlify.app', 'netlify.com'
            ],
            'Vercel': [
                'vercel.app', 'now.sh'
            ],
            'Cloudflare': [
                'cloudflare.com', 'cloudflare.net', 'workers.dev'
            ],
            'Alibaba': [
                'alibabacloud.com', 'aliyuncs.com'
            ],
        }
        
        for provider, patterns in cloud_patterns.items():
            for pattern in patterns:
                self.queries['cloud'].append(f'site:{self.domain} {pattern}')
    
    def generate_subdomain_queries(self):
        """Generate subdomain discovery queries"""
        subdomain_patterns = [
            'admin', 'api', 'app', 'blog', 'cdn', 'cloud',
            'dashboard', 'dev', 'docs', 'git', 'github',
            'internal', 'mail', 'portal', 'staging', 'test',
            'web', 'www', 'ftp', 'sftp', 'ssh', 'vpn',
            'monitoring', 'stats', 'status', 'health',
            'chat', 'forum', 'community', 'support',
            'help', 'kb', 'wiki', 'confluence', 'jira',
            'jenkins', 'cicd', 'build', 'deploy',
            'backup', 'data', 'db', 'mysql', 'redis',
            'elastic', 'kibana', 'grafana', 'prometheus',
            'aws', 'azure', 'gcp', 'cloud',
            'analytics', 'reports', 'metrics',
            'test', 'dev', 'stage', 'staging', 'qa'
        ]
        
        for sub in subdomain_patterns:
            self.queries['subdomains'].append(f'site:{sub}.{self.domain}')
    
    def generate_exposure_queries(self):
        """Generate exposure discovery queries"""
        self.queries['exposures'] = [
            # Directory listing
            f'site:{self.domain} intitle:"index of"',
            f'site:{self.domain} intitle:"parent directory"',
            f'site:{self.domain} "Directory listing"',
            f'site:{self.domain} "Index of /"',
            
            # Configuration files
            f'site:{self.domain} filetype:env',
            f'site:{self.domain} filetype:config',
            f'site:{self.domain} filetype:conf',
            f'site:{self.domain} filetype:ini',
            f'site:{self.domain} filetype:yaml',
            f'site:{self.domain} filetype:yml',
            
            # Backup files
            f'site:{self.domain} filetype:bak',
            f'site:{self.domain} filetype:backup',
            f'site:{self.domain} filetype:old',
            f'site:{self.domain} "backup" filetype:sql',
            
            # Database dumps
            f'site:{self.domain} filetype:sql',
            f'site:{self.domain} "CREATE TABLE" filetype:sql',
            f'site:{self.domain} "INSERT INTO" filetype:sql',
            
            # Exposed logs
            f'site:{self.domain} filetype:log',
            f'site:{self.domain} "error.log"',
            f'site:{self.domain} "access.log"',
            
            # PHP Info
            f'site:{self.domain} "phpinfo()"',
            f'site:{self.domain} "PHP Version"',
            
            # Git exposure
            f'site:{self.domain} ".git/config"',
            f'site:{self.domain} ".git/HEAD"',
            
            # AWS Keys
            f'site:{self.domain} "AKIA"',
            f'site:{self.domain} "AWS_SECRET_ACCESS_KEY"',
            f'site:{self.domain} "aws_access_key_id"',
            
            # API Keys
            f'site:{self.domain} "api_key"',
            f'site:{self.domain} "API_KEY"',
            f'site:{self.domain} "Authorization: Bearer"',
            
            # Database credentials
            f'site:{self.domain} "DB_PASSWORD"',
            f'site:{self.domain} "DB_USERNAME"',
            f'site:{self.domain} "MYSQL_PASSWORD"',
            f'site:{self.domain} "POSTGRES_PASSWORD"',
            
            # SSH keys
            f'site:{self.domain} "BEGIN RSA PRIVATE KEY"',
            f'site:{self.domain} "BEGIN DSA PRIVATE KEY"',
            
            # Certificates
            f'site:{self.domain} filetype:pem',
            f'site:{self.domain} filetype:crt',
            f'site:{self.domain} filetype:key',
            
            # Admin panels
            f'site:{self.domain} intitle:"admin login"',
            f'site:{self.domain} intitle:"dashboard" inurl:admin',
            f'site:{self.domain} inurl:admin intext:"login"',
            
            # Error messages
            f'site:{self.domain} "SQL syntax"',
            f'site:{self.domain} "mysql_fetch"',
            f'site:{self.domain} "PostgreSQL" "ERROR"',
            f'site:{self.domain} "ORA-"',
            
            # Debug information
            f'site:{self.domain} "Stack trace"',
            f'site:{self.domain} "Warning:"',
            f'site:{self.domain} "Notice:"',
            
            # Exposed dashboards
            f'site:{self.domain} intitle:"Grafana"',
            f'site:{self.domain} intitle:"Kibana"',
            f'site:{self.domain} intitle:"ELK"',
            
            # Version control
            f'site:{self.domain} "version" filetype:xml',
            f'site:{self.domain} "build" filetype:properties',
            
            # Jenkins
            f'site:{self.domain} intitle:"jenkins"',
            f'site:{self.domain} "jenkins" inurl:job',
            
            # Jira/Confluence
            f'site:{self.domain} intitle:"Jira"',
            f'site:{self.domain} intitle:"Confluence"',
            f'site:{self.domain} "dashboard" "jira"',
        ]

class GoogleDorker:
    """Execute Google dork queries and manage results"""
    
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        self.results = {}
    
    def build_url(self, query: str) -> str:
        """Build Google search URL"""
        return f"https://www.google.com/search?q={quote_plus(query)}"
    
    def search(self, query: str, delay: float = 1.0) -> List[Dict]:
        """Perform a single Google search"""
        if self.verbose:
            print(f"[*] Searching: {query}")
        
        try:
            time.sleep(delay)
            url = self.build_url(query)
            response = self.session.get(url)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            results = []
            
            for result in soup.find_all('div', class_='g'):
                try:
                    title_elem = result.find('h3')
                    if not title_elem:
                        continue
                    
                    title = title_elem.get_text()
                    link_elem = result.find('a')
                    link = link_elem.get('href') if link_elem else None
                    desc_elem = result.find('div', class_='VwiC3b')
                    description = desc_elem.get_text() if desc_elem else "No description"
                    
                    results.append({
                        'title': title,
                        'link': link,
                        'description': description,
                        'query': query
                    })
                except Exception:
                    continue
            
            return results
            
        except Exception as e:
            if self.verbose:
                print(f"[!] Error searching '{query}': {e}")
            return []
    
    def execute_dorks(self, queries: List[str], max_results: int = 3, delay: float = 1.0) -> Dict:
        """Execute multiple dork queries"""
        results = {}
        total_queries = len(queries)
        
        for idx, query in enumerate(queries, 1):
            if self.verbose:
                print(f"[*] Processing query {idx}/{total_queries}")
            
            results[query] = self.search(query, delay)
            
            # Break if we've reached max results
            total_found = sum(len(r) for r in results.values())
            if total_found >= max_results:
                break
        
        return results

class GDorkCLI:
    """Main CLI interface for gdork tool"""
    
    def __init__(self):
        self.dorker = None
        self.generator = None
    
    def print_banner(self):
        """Print tool banner"""
        banner = """
╔══════════════════════════════════════════════════════════╗
║                    🎯 GDORK - v1.0                       ║
║         Professional Google Dorking CLI Tool            ║
║              Bug Bounty Recon & Discovery               ║
╚══════════════════════════════════════════════════════════╝
        """
        print(banner)
    
    def display_category_results(self, category: str, queries: List[str], results: Dict = None):
        """Display organized results for a category"""
        print(f"\n[{category.upper()}]")
        print("-" * 80)
        
        for query in queries:
            print(f"  {query}")
        
        if results and category in results:
            print(f"\n  Results found: {len(results[category])}")
            for res in results[category][:5]:  # Show first 5 results
                print(f"    → {res['title'][:60]}...")
                print(f"      {res['link']}")
    
    def generate_and_display(self, domain: str, categories: List[str], 
                            max_results: int = 10, delay: float = 1.0,
                            execute: bool = False, no_open: bool = False):
        """Generate and optionally execute dork queries"""
        self.generator = DorkGenerator(domain)
        
        if not categories or 'all' in categories:
            self.generator.generate_all()
            categories = list(self.generator.queries.keys())
        
        print(f"\n[+] Target: {domain}")
        print(f"[+] Categories: {', '.join(categories)}\n")
        
        all_queries = []
        for category in categories:
            if category in self.generator.queries:
                queries = self.generator.queries[category]
                all_queries.extend(queries)
                self.display_category_results(category, queries)
        
        # Execute searches if requested
        if execute:
            self.dorker = GoogleDorker(verbose=True)
            print(f"\n[+] Executing {len(all_queries)} searches...")
            
            # Limit queries to avoid overwhelming
            limited_queries = all_queries[:max_results * 2]  # Search more, but limit results
            
            results = self.dorker.execute_dorks(
                limited_queries, 
                max_results=max_results,
                delay=delay
            )
            
            # Display results summary
            total_results = sum(len(r) for r in results.values())
            print(f"\n[+] Total results found: {total_results}")
            
            # Open in browser if requested
            if not no_open and results:
                first_query = list(results.keys())[0]
                if results[first_query]:
                    print(f"\n[+] Opening first result in browser...")
                    webbrowser.open(self.dorker.build_url(first_query))
        else:
            # Just generate and show dorks, open in browser
            if not no_open and all_queries:
                print(f"\n[+] Opening first query in browser...")
                webbrowser.open(self.dorker.build_url(all_queries[0]) if self.dorker else 
                               f"https://www.google.com/search?q={quote_plus(all_queries[0])}")
        
        # Save results if requested
        return all_queries

def create_parser():
    """Create argument parser"""
    parser = argparse.ArgumentParser(
        description='GDORK - Professional Google Dorking Tool',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
EXAMPLES:
  # Generate all dorks for a domain
  gdork example.com

  # Generate specific categories
  gdork example.com -c files urls titles

  # Generate and execute searches
  gdork example.com -c files texts -e -n 20

  # Generate and open browser
  gdork example.com -c admin exposures

  # Show only a specific category
  gdork example.com -c files -s

  # Full reconnaissance
  gdork example.com -c all -e -n 50 -o results.json
        """
    )
    
    parser.add_argument('domain', help='Target domain (e.g., example.com)')
    parser.add_argument('-c', '--categories', nargs='+', 
                       choices=['domain', 'files', 'urls', 'titles', 'text', 
                               'dates', 'technology', 'documents', 'cloud', 
                               'subdomains', 'exposures', 'all'],
                       default=['all'],
                       help='Dork categories to generate')
    parser.add_argument('-e', '--execute', action='store_true',
                       help='Execute searches and fetch results')
    parser.add_argument('-n', '--max-results', type=int, default=10,
                       help='Maximum results per category (default: 10)')
    parser.add_argument('-d', '--delay', type=float, default=1.0,
                       help='Delay between requests in seconds (default: 1.0)')
    parser.add_argument('-o', '--output', help='Save results to file (JSON format)')
    parser.add_argument('-s', '--show-only', action='store_true',
                       help='Show only dorks without opening browser')
    parser.add_argument('-v', '--verbose', action='store_true',
                       help='Verbose output')
    parser.add_argument('-q', '--quiet', action='store_true',
                       help='Quiet mode (minimal output)')
    
    return parser

def main():
    parser = create_parser()
    args = parser.parse_args()
    
    # Print banner
    if not args.quiet:
        cli = GDorkCLI()
        cli.print_banner()
    
    # Initialize
    cli = GDorkCLI()
    
    # Handle categories
    categories = args.categories
    if 'all' in categories:
        categories = ['domain', 'files', 'urls', 'titles', 'text', 
                     'dates', 'technology', 'documents', 'cloud', 
                     'subdomains', 'exposures']
    
    # Generate and process
    cli.generate_and_display(
        domain=args.domain,
        categories=categories,
        max_results=args.max_results,
        delay=args.delay,
        execute=args.execute,
        no_open=args.show_only
    )
    
    print("\n[+] Done!")

if __name__ == '__main__':
    main()
