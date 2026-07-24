#!/usr/bin/env python3
"""
Universal Page Understanding Engine v5 - FINAL
----------------------------------------------
Enhanced with:
- Hybrid entity extraction (regex + rules + NLP)
- Better opportunity detection with context
- Improved text processing
- More robust error handling
- Cleaner output format
"""

import json
import websocket
import requests
import sys
import time
import re
from typing import Optional, Dict, List, Any, Set, Tuple
from collections import Counter, defaultdict
from dataclasses import dataclass, field, asdict
from urllib.parse import urlparse, urljoin
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
import rich.box as box
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.text import Text
from datetime import datetime
import hashlib

try:
    import spacy
    SPACY_AVAILABLE = True
    nlp = spacy.load("en_core_web_sm")
except:
    SPACY_AVAILABLE = False
    nlp = None

console = Console()

# ============================================================================
# TEXT CLEANER - Removes noise from extracted text
# ============================================================================

class TextCleaner:
    """Clean and normalize extracted text"""

    @staticmethod
    def clean(text: str) -> str:
        """Clean text by removing noise"""
        if not text:
            return ""
        
        # Remove excessive whitespace
        text = re.sub(r'\s+', ' ', text)

        # Remove common noise patterns
        noise_patterns = [
            r'[•·●○◆◇■□▪▫►▸▹►▻◄◀▶]',  # Bullet points
            r'[★☆✩✪✫✬✭✮✯]',  # Stars
            r'[♥♡❤]',  # Hearts
            r'[✔✓✅☑]',  # Checkmarks
            r'[✖✗✘❌❎]',  # Crosses
            r'[\[\]\(\)\{\}]',  # Brackets
        ]

        for pattern in noise_patterns:
            text = re.sub(pattern, '', text)

        # Remove multiple spaces
        text = re.sub(r'\s{2,}', ' ', text)

        # Remove leading/trailing whitespace
        text = text.strip()

        return text

    @staticmethod
    def clean_opportunity(text: str) -> str:
        """Clean opportunity text specifically"""
        if not text:
            return ""
            
        # Remove common prefixes
        prefixes = [
            r'^(?:job|position|role|opening|internship|hackathon|event)\s*[:.]?\s*',
            r'^(?:apply for|register for|participate in)\s*',
            r'^(?:now!|hurry!|limited!)\s*',
        ]

        for prefix in prefixes:
            text = re.sub(prefix, '', text, flags=re.IGNORECASE)

        # Remove trailing noise
        text = re.sub(r'\s*[|/\\]\s*.*$', '', text)

        return text.strip()

# ============================================================================
# ENHANCED ENTITY EXTRACTOR - Hybrid Approach
# ============================================================================

class EntityExtractorV3:
    """Hybrid entity extraction with regex, rules, and NLP"""
    
    # Common organization suffixes
    ORG_SUFFIXES = [
        'Inc', 'Corp', 'LLC', 'Ltd', 'Pvt', 'Technologies', 'Solutions', 
        'Systems', 'Labs', 'Foundation', 'Institute', 'University', 
        'College', 'School', 'Academy', 'Group', 'Enterprises', 
        'Ventures', 'Capital', 'Partners', 'Associates', 'Consulting',
        'Services', 'Digital', 'Creative', 'Media', 'Studios', 'Works',
        'Factory', 'Co', 'Company', 'Corporation', 'Incorporated',
        'Limited', 'PLC', 'LLP', 'GmbH', 'SA', 'AG', 'SAS'
    ]
    
    # Common locations (cities and countries)
    LOCATIONS = {
        'cities': [
            'Mumbai', 'Delhi', 'Bangalore', 'Chennai', 'Hyderabad', 
            'Pune', 'Kolkata', 'Ahmedabad', 'Jaipur', 'Lucknow', 
            'Nagpur', 'Indore', 'Bhopal', 'Chandigarh', 'Noida',
            'Gurgaon', 'Faridabad', 'Ghaziabad', 'Coimbatore', 'Vizag',
            'Surat', 'Vadodara', 'Ludhiana', 'Agra', 'Varanasi',
            'Patna', 'Ranchi', 'Bhubaneswar', 'Guwahati', 'New York',
            'London', 'Singapore', 'Dubai', 'Tokyo', 'Paris',
            'Berlin', 'Sydney', 'Toronto', 'San Francisco', 'Austin'
        ],
        'countries': [
            'India', 'USA', 'UK', 'Canada', 'Australia', 'Germany',
            'France', 'Japan', 'China', 'Singapore', 'Dubai', 'UAE',
            'Europe', 'Asia', 'Africa', 'South Africa', 'Brazil',
            'Mexico', 'Italy', 'Spain', 'Netherlands', 'Sweden',
            'Norway', 'Denmark', 'Finland', 'Switzerland', 'Austria'
        ]
    }
    
    # Skills dictionary
    SKILLS = [
        'Python', 'Java', 'JavaScript', 'TypeScript', 'C++', 'C#', 
        'PHP', 'Ruby', 'Go', 'Rust', 'Swift', 'Kotlin', 'React',
        'Angular', 'Vue', 'Svelte', 'Next.js', 'Node.js', 'Django',
        'Flask', 'Spring', 'AWS', 'Azure', 'GCP', 'Docker',
        'Kubernetes', 'Terraform', 'SQL', 'NoSQL', 'MongoDB',
        'PostgreSQL', 'MySQL', 'Redis', 'Elasticsearch', 'Kafka',
        'RabbitMQ', 'Machine Learning', 'AI', 'Deep Learning', 'NLP',
        'Computer Vision', 'Data Science', 'Analytics', 'DevOps',
        'SRE', 'Blockchain', 'IoT', 'AR/VR', 'Game Development',
        'Cybersecurity', 'Cloud', 'Frontend', 'Backend', 'Full Stack',
        'Mobile', 'iOS', 'Android', 'Flutter', 'React Native',
        'TensorFlow', 'PyTorch', 'Scikit-learn', 'Pandas', 'NumPy',
        'Tableau', 'Power BI', 'Excel', 'SAP', 'Oracle', 'Salesforce'
    ]
    
    # Date patterns
    DATE_PATTERNS = [
        r'\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b',
        r'\b(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{4})\b',
        r'\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b',
        r'\b(\d{4})[/-](\d{1,2})[/-](\d{1,2})\b'
    ]
    
    # Prize patterns
    PRIZE_PATTERNS = [
        r'[\$₹€£](\d{1,3}(?:,\d{3})*(?:\.\d{2})?)\s*(?:USD|INR|EUR|GBP)?',
        r'(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)\s*(?:USD|INR|EUR|GBP|dollars|rupees|euros)',
        r'(?:prize|reward|cash|scholarship|grant|stipend)\s*(?:pool|amount|worth|value)?\s*(?:of\s*)?[\$₹€£]?(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)',
    ]
    
    @classmethod
    def extract(cls, text: str) -> Dict[str, List[str]]:
        """Extract entities using hybrid approach"""
        if not text:
            return {}
            
        clean_text = TextCleaner.clean(text)
        entities = defaultdict(set)  # Use set for automatic deduplication
        
        # 1. Use spaCy if available (best for NLP)
        if SPACY_AVAILABLE and nlp:
            try:
                doc = nlp(clean_text[:100000])
                for ent in doc.ents:
                    entity_text = ent.text.strip()
                    if len(entity_text) < 3 or len(entity_text) > 100:
                        continue
                    
                    # Map spaCy labels
                    if ent.label_ == 'ORG':
                        entities['organization'].add(entity_text)
                    elif ent.label_ == 'GPE':
                        entities['location'].add(entity_text)
                    elif ent.label_ == 'PERSON':
                        entities['person'].add(entity_text)
                    elif ent.label_ == 'DATE':
                        entities['date'].add(entity_text)
                    elif ent.label_ == 'MONEY':
                        entities['prize'].add(entity_text)
                    elif ent.label_ == 'PRODUCT':
                        entities['product'].add(entity_text)
                    elif ent.label_ == 'EVENT':
                        entities['event'].add(entity_text)
            except Exception as e:
                pass  # Fall back to regex
        
        # 2. Extract organizations using rules
        org_pattern = r'\b([A-Z][a-zA-Z\s&,.-]{2,30})\s+(?:' + '|'.join(cls.ORG_SUFFIXES) + r')\b'
        for match in re.finditer(org_pattern, clean_text, re.IGNORECASE):
            org = match.group(1).strip()
            if len(org) > 2:
                entities['organization'].add(org)
        
        # Also find organizations with "of" or "for"
        org_pattern2 = r'\b(?:University|Institute|College|School|Academy)\s+(?:of|for)\s+([A-Z][a-zA-Z\s&,.-]{2,30})\b'
        for match in re.finditer(org_pattern2, clean_text, re.IGNORECASE):
            org = match.group(1).strip()
            if len(org) > 2:
                entities['organization'].add(org)
        
        # 3. Extract locations
        # Cities
        city_pattern = r'\b(' + '|'.join(cls.LOCATIONS['cities']) + r')\b'
        for match in re.finditer(city_pattern, clean_text, re.IGNORECASE):
            city = match.group(1).strip()
            entities['location'].add(city)
        
        # Countries
        country_pattern = r'\b(' + '|'.join(cls.LOCATIONS['countries']) + r')\b'
        for match in re.finditer(country_pattern, clean_text, re.IGNORECASE):
            country = match.group(1).strip()
            entities['location'].add(country)
        
        # Location with comma
        location_pattern = r'\b([A-Z][a-zA-Z\s]+)\s*,\s*([A-Z][a-zA-Z\s]+)\b'
        for match in re.finditer(location_pattern, clean_text):
            place1 = match.group(1).strip()
            place2 = match.group(2).strip()
            if len(place1) > 2:
                entities['location'].add(place1)
            if len(place2) > 2:
                entities['location'].add(place2)
        
        # 4. Extract skills
        skill_pattern = r'\b(' + '|'.join(cls.SKILLS) + r')\b'
        for match in re.finditer(skill_pattern, clean_text, re.IGNORECASE):
            skill = match.group(1).strip()
            entities['skill'].add(skill)
        
        # 5. Extract dates
        for pattern in cls.DATE_PATTERNS:
            for match in re.finditer(pattern, clean_text):
                date_text = match.group(0).strip()
                if len(date_text) > 4:
                    entities['date'].add(date_text)
        
        # 6. Extract prizes/amounts
        for pattern in cls.PRIZE_PATTERNS:
            for match in re.finditer(pattern, clean_text, re.IGNORECASE):
                amount = match.group(0).strip()
                if len(amount) > 2:
                    entities['prize'].add(amount)
        
        # 7. Extract deadlines (context-aware)
        deadline_pattern = r'(?:deadline|last date|apply by|submit by|due|ends? on?)\s*(?:is\s*)?([A-Za-z]+\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4})'
        for match in re.finditer(deadline_pattern, clean_text, re.IGNORECASE):
            deadline = match.group(1).strip()
            if len(deadline) > 4:
                entities['deadline'].add(deadline)
        
        # 8. Extract emails
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        for match in re.finditer(email_pattern, clean_text):
            email = match.group(0).strip()
            entities['email'].add(email)
        
        # 9. Extract URLs
        url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
        for match in re.finditer(url_pattern, clean_text):
            url = match.group(0).strip()
            if len(url) > 10:
                entities['url'].add(url)
        
        # 10. Extract phone numbers
        phone_pattern = r'\+?\d{1,3}[-.\s]?\(?\d{1,4}\)?[-.\s]?\d{1,4}[-.\s]?\d{1,9}'
        for match in re.finditer(phone_pattern, clean_text):
            phone = match.group(0).strip()
            if len(phone) > 5:
                entities['phone'].add(phone)
        
        # Convert sets to sorted lists and limit
        result = {}
        for key, value_set in entities.items():
            # Filter by length
            filtered = [v for v in value_set if 2 < len(v) < 100]
            # Sort and limit to 10
            result[key] = sorted(filtered)[:10]
        
        return {k: v for k, v in result.items() if v}

# ============================================================================
# ENHANCED OPPORTUNITY DETECTOR
# ============================================================================

class OpportunityDetectorV3:
    """Enhanced opportunity detection with better parsing"""

    # Comprehensive opportunity patterns
    OPPORTUNITY_PATTERNS = {
        'jobs': [
            r'(?:job|position|role|opening|vacancy)\s*(?:title|name|:)?\s*["\']?([A-Z][A-Za-z\s&,-]{5,60})["\']?',
            r'(?:hiring|recruiting|looking for)\s*["\']?([A-Z][A-Za-z\s&,-]{5,60})["\']?',
            r'([A-Z][A-Za-z\s&,-]{5,60})\s*(?:job|position|role|opening)',
            r'(?:we\'re hiring|join our team|career opportunity)\s*["\']?([A-Z][A-Za-z\s&,-]{5,60})["\']?',
            r'(?:career|employment)\s+(?:opportunity|opening)\s*[:.]?\s*([A-Z][A-Za-z\s&,-]{5,60})',
        ],
        'internships': [
            r'(?:internship|intern|trainee|apprentice)\s*(?:opportunity|position|program)?\s*[:.]?\s*["\']?([A-Z][A-Za-z\s&,-]{5,60})["\']?',
            r'(?:intern)\s*["\']?([A-Z][A-Za-z\s&,-]{5,60})["\']?\s*(?:internship|position)',
            r'(?:apply for|join as)\s*["\']?([A-Z][A-Za-z\s&,-]{5,60})["\']?\s*(?:intern|internship)',
            r'(?:summer|winter)\s+internship\s*(?:program|opportunity)?\s*[:.]?\s*([A-Z][A-Za-z\s&,-]{5,60})',
        ],
        'hackathons': [
            r'(?:hackathon|hack|challenge|competition)\s*(?:name|title|:)?\s*["\']?([A-Z][A-Za-z0-9\s&,.-]{5,60})["\']?',
            r'([A-Z][A-Za-z0-9\s&,.-]{5,60})\s*(?:hackathon|hack|challenge)',
            r'(?:register for|participate in|join)\s*["\']?([A-Z][A-Za-z0-9\s&,.-]{5,60})["\']?\s*(?:hackathon|hack)',
            r'(?:coding|programming)\s+(?:competition|challenge)\s*[:.]?\s*([A-Z][A-Za-z0-9\s&,.-]{5,60})',
        ],
        'events': [
            r'(?:event|conference|workshop|seminar|webinar)\s*(?:name|title|:)?\s*["\']?([A-Z][A-Za-z0-9\s&,.-]{5,60})["\']?',
            r'([A-Z][A-Za-z0-9\s&,.-]{5,60})\s*(?:event|conference|workshop|seminar)',
            r'(?:join|attend|register for)\s*["\']?([A-Z][A-Za-z0-9\s&,.-]{5,60})["\']?\s*(?:event|conference|workshop)',
            r'(?:upcoming|future)\s+(?:event|conference)\s*[:.]?\s*([A-Z][A-Za-z0-9\s&,.-]{5,60})',
        ],
        'scholarships': [
            r'(?:scholarship|fellowship|grant|bursary)\s*(?:opportunity|program)?\s*[:.]?\s*["\']?([A-Z][A-Za-z\s&,.-]{5,60})["\']?',
            r'(?:apply for|eligible for)\s*["\']?([A-Z][A-Za-z\s&,.-]{5,60})["\']?\s*(?:scholarship|fellowship)',
            r'(?:merit|need)-based\s+(?:scholarship|fellowship)\s*[:.]?\s*([A-Z][A-Za-z\s&,.-]{5,60})',
        ],
        'courses': [
            r'(?:course|program|certification|training)\s*(?:name|title|:)?\s*["\']?([A-Z][A-Za-z0-9\s&,.-]{5,60})["\']?',
            r'([A-Z][A-Za-z0-9\s&,.-]{5,60})\s*(?:course|program|training)',
            r'(?:learn|study|enroll in)\s*["\']?([A-Z][A-Za-z0-9\s&,.-]{5,60})["\']?\s*(?:course|program)',
        ]
    }

    @classmethod
    def detect(cls, text: str, html: str) -> Dict:
        """Extract opportunities with better parsing"""
        if not text:
            return {}

        # Clean text
        clean_text = TextCleaner.clean(text)
        opportunities = defaultdict(set)  # Use set for deduplication

        # Extract using patterns
        for opp_type, patterns in cls.OPPORTUNITY_PATTERNS.items():
            for pattern in patterns:
                matches = re.finditer(pattern, clean_text, re.IGNORECASE)
                for match in matches:
                    try:
                        opportunity = match.group(1).strip()
                        if opportunity and len(opportunity) > 3 and len(opportunity) < 80:
                            cleaned = TextCleaner.clean_opportunity(opportunity)
                            if cleaned and len(cleaned) > 3:
                                # Add to set for deduplication
                                opportunities[opp_type].add(cleaned)
                    except (IndexError, AttributeError):
                        continue

        # Also extract from HTML attributes
        html_patterns = [
            (r'title="([^"]{10,60})"', 'jobs'),
            (r'aria-label="([^"]{10,60})"', 'jobs'),
            (r'data-title="([^"]{10,60})"', 'jobs'),
        ]

        for pattern, opp_type in html_patterns:
            matches = re.finditer(pattern, html, re.IGNORECASE)
            for match in matches:
                try:
                    text_match = match.group(1).strip()
                    if text_match and len(text_match) > 5:
                        # Check if it sounds like an opportunity
                        keywords = ['job', 'intern', 'hack', 'event', 'position', 'role', 'opportunity']
                        if any(kw in text_match.lower() for kw in keywords):
                            opportunities[opp_type].add(text_match)
                except (IndexError, AttributeError):
                    continue

        # Convert sets to sorted lists and limit
        result = {}
        for key, value_set in opportunities.items():
            filtered = [v for v in value_set if len(v) > 3]
            result[key] = sorted(filtered)[:10]

        return {k: v for k, v in result.items() if v}

# ============================================================================
# ENHANCED PAGE TYPE DETECTOR
# ============================================================================

class PageTypeDetectorV3:
    """Enhanced page type detection"""

    # Domain mapping
    DOMAIN_MAPPING = {
        'unstop.com': 'events',
        'internshala.com': 'internships',
        'linkedin.com': 'social',
        'github.com': 'docs',
        'youtube.com': 'video',
        'amazon.com': 'ecommerce',
        'reddit.com': 'forum',
        'twitter.com': 'social',
        'x.com': 'social',
        'wikipedia.org': 'wiki',
        'medium.com': 'blog',
        'indeed.com': 'jobs',
        'naukri.com': 'jobs',
        'hackerrank.com': 'coding',
        'leetcode.com': 'coding',
        'codeforces.com': 'coding',
        'stackoverflow.com': 'forum',
        'dev.to': 'blog',
        'hashnode.com': 'blog',
    }

    # Page type indicators with weights
    PAGE_INDICATORS = {
        'jobs': {
            'keywords': ['hiring', 'career', 'job', 'position', 'apply', 'vacancy', 'opening', 'employment'],
            'weight': 0.8
        },
        'internships': {
            'keywords': ['internship', 'intern', 'trainee', 'apprentice', 'stipend', 'summer intern'],
            'weight': 0.9
        },
        'hackathons': {
            'keywords': ['hackathon', 'hack', 'challenge', 'competition', 'prize', 'winner', 'coding contest'],
            'weight': 0.9
        },
        'events': {
            'keywords': ['register', 'event', 'conference', 'workshop', 'seminar', 'webinar', 'speaker'],
            'weight': 0.7
        },
        'ecommerce': {
            'keywords': ['buy', 'shop', 'cart', 'checkout', 'price', 'discount', 'purchase'],
            'weight': 0.7
        },
        'social': {
            'keywords': ['post', 'share', 'like', 'follow', 'comment', 'tweet', 'friend'],
            'weight': 0.6
        },
        'education': {
            'keywords': ['course', 'learn', 'study', 'class', 'lecture', 'tutorial', 'curriculum'],
            'weight': 0.7
        },
        'coding': {
            'keywords': ['problem', 'solve', 'challenge', 'algorithm', 'code', 'programming', 'debug'],
            'weight': 0.7
        },
        'blog': {
            'keywords': ['blog', 'post', 'article', 'author', 'published', 'writing', 'read'],
            'weight': 0.7
        },
        'forum': {
            'keywords': ['question', 'answer', 'thread', 'discussion', 'reply', 'post', 'community'],
            'weight': 0.7
        }
    }

    @classmethod
    def detect(cls, text: str, url: str, title: str) -> Dict:
        """Detect page type with confidence scores"""
        if not text:
            return {'page_type': 'unknown', 'confidence': 0.0, 'evidence': [], 'all_scores': {}}
            
        clean_text = TextCleaner.clean(text[:20000].lower())
        url_lower = url.lower()
        title_lower = title.lower()

        scores = defaultdict(float)
        evidence = []

        # Domain detection (high weight)
        for domain, page_type in cls.DOMAIN_MAPPING.items():
            if domain in url_lower:
                scores[page_type] += 1.0
                evidence.append(f"domain: {domain}")
                break

        # Keyword detection with frequency
        for page_type, config in cls.PAGE_INDICATORS.items():
            match_count = 0
            for keyword in config['keywords']:
                # Count occurrences with word boundaries
                count = len(re.findall(r'\b' + keyword + r'\w*\b', clean_text))
                if count > 0:
                    match_count += count
                    scores[page_type] += count * 0.15

            if match_count > 0:
                evidence.append(f"{match_count} '{page_type}' indicators")

        # Title detection
        for page_type, config in cls.PAGE_INDICATORS.items():
            for keyword in config['keywords']:
                if keyword in title_lower:
                    scores[page_type] += 0.2
                    evidence.append(f"title contains '{keyword}'")

        # URL path analysis
        if 'careers' in url_lower or 'jobs' in url_lower:
            scores['jobs'] += 0.3
            evidence.append("URL path contains 'careers' or 'jobs'")
        if 'intern' in url_lower:
            scores['internships'] += 0.3
            evidence.append("URL path contains 'intern'")
        if 'hackathon' in url_lower:
            scores['hackathons'] += 0.3
            evidence.append("URL path contains 'hackathon'")
        if 'event' in url_lower:
            scores['events'] += 0.3
            evidence.append("URL path contains 'event'")

        # Normalize scores
        total = sum(scores.values())
        if total > 0:
            for key in scores:
                scores[key] = min(scores[key] / total, 1.0)

        # Get best result
        if scores:
            best_type = max(scores, key=scores.get)
            best_score = scores[best_type]

            if best_score > 0.15:
                return {
                    'page_type': best_type,
                    'confidence': best_score,
                    'evidence': list(set(evidence))[:5],
                    'all_scores': {k: round(v, 2) for k, v in scores.items() if v > 0.05}
                }

        return {
            'page_type': 'unknown',
            'confidence': 0.0,
            'evidence': ['No strong indicators'],
            'all_scores': {}
        }

# ============================================================================
# MAIN ENGINE V5
# ============================================================================

class UniversalPageEngineV5:
    """Production-ready page understanding engine"""

    def __init__(self, port=9236):
        self.port = port
        self.ws = None
        self.connected = False
        self.html = ""
        self.text = ""
        self.url = ""
        self.title = ""
        self.domain = ""
        self.page_hash = ""

    def connect(self):
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

            self.url = page_tab.get('url', '')
            self.title = page_tab.get('title', '')
            self.domain = urlparse(self.url).netloc
            ws_url = page_tab.get('webSocketDebuggerUrl')

            self.ws = websocket.create_connection(ws_url, timeout=10)

            self.ws.send(json.dumps({"id": 1, "method": "Runtime.enable"}))
            self._wait_for_response(1)

            self.connected = True
            return True

        except Exception as e:
            console.print(f"[red]Connection failed: {e}[/red]")
            return False

    def _wait_for_response(self, expected_id, timeout=5):
        start = time.time()
        while time.time() - start < timeout:
            try:
                resp = self.ws.recv()
                data = json.loads(resp)
                if data.get('id') == expected_id:
                    return data
            except:
                pass
        return None

    def js(self, script, return_by_value=True):
        if not self.connected:
            return None

        cmd_id = int(time.time() * 1000) % 100000

        self.ws.send(json.dumps({
            "id": cmd_id,
            "method": "Runtime.evaluate",
            "params": {
                "expression": script,
                "returnByValue": return_by_value
            }
        }))

        timeout = 10
        start = time.time()
        while time.time() - start < timeout:
            try:
                resp = self.ws.recv()
                data = json.loads(resp)
                if data.get('id') == cmd_id:
                    result = data.get('result', {})
                    if 'result' in result:
                        return result['result'].get('value')
                    return None
            except:
                pass
        return None

    def fetch_page(self):
        if not self.connected:
            return False

        self.html = self.js("document.documentElement.outerHTML") or ""
        self.text = self.js("document.body ? document.body.innerText : ''") or ""
        self.title = self.js("document.title") or "Untitled"
        self.url = self.js("window.location.href") or self.url
        self.page_hash = hashlib.md5(self.html.encode()).hexdigest()[:8]

        return True

    def analyze(self) -> Dict:
        """Complete analysis"""
        console.print("[bold cyan]🔍 Analyzing page...[/bold cyan]")

        if not self.fetch_page():
            return {'error': 'Failed to fetch page'}

        results = {
            'url': self.url,
            'title': self.title,
            'domain': self.domain,
            'hash': self.page_hash,
            'timestamp': datetime.now().isoformat()
        }

        # Layer 1: DOM Statistics
        console.print("[dim]  Layer 1: DOM Statistics...[/dim]")
        results['dom_stats'] = self._get_dom_stats()

        # Layer 2: Structure
        console.print("[dim]  Layer 2: Structure Detection...[/dim]")
        results['structure'] = self._detect_structure()

        # Layer 3: Page Type
        console.print("[dim]  Layer 3: Page Type Detection...[/dim]")
        results['page_type'] = PageTypeDetectorV3.detect(self.text, self.url, self.title)

        # Layer 4: Entities (Improved)
        console.print("[dim]  Layer 4: Entity Extraction...[/dim]")
        results['entities'] = EntityExtractorV3.extract(self.text)

        # Layer 5: Opportunities
        console.print("[dim]  Layer 5: Opportunity Detection...[/dim]")
        results['opportunities'] = OpportunityDetectorV3.detect(self.text, self.html)

        # Layer 6: Actions
        console.print("[dim]  Layer 6: Action Detection...[/dim]")
        results['actions'] = self._detect_actions()

        # Layer 7: Forms
        console.print("[dim]  Layer 7: Form Analysis...[/dim]")
        results['forms'] = self._analyze_forms()

        # Layer 8: Links
        console.print("[dim]  Layer 8: Link Analysis...[/dim]")
        results['links'] = self._analyze_links()

        # Layer 9: Keywords
        console.print("[dim]  Layer 9: Keyword Extraction...[/dim]")
        results['keywords'] = self._extract_keywords()

        # Layer 10: Summary
        console.print("[dim]  Layer 10: Generating Summary...[/dim]")
        results['summary'] = self._generate_summary(results)

        return results

    def _get_dom_stats(self) -> Dict:
        script = """
        (function() {
            const stats = {
                buttons: 0, links: 0, forms: 0, images: 0, videos: 0,
                tables: 0, dialogs: 0, text_inputs: 0, password_inputs: 0,
                email_inputs: 0, number_inputs: 0, checkboxes: 0, radio_buttons: 0,
                dropdowns: 0, iframes: 0, canvas: 0, svg: 0, headings: 0,
                paragraphs: 0, lists: 0, articles: 0, sections: 0,
                total_elements: 0, total_text: 0, hidden_elements: 0
            };

            const all = document.querySelectorAll('*');
            stats.total_elements = all.length;

            all.forEach(el => {
                const tag = el.tagName.toLowerCase();
                const rect = el.getBoundingClientRect();
                const isHidden = rect.width === 0 || rect.height === 0 ||
                               window.getComputedStyle(el).display === 'none';
                if (isHidden) stats.hidden_elements++;

                switch(tag) {
                    case 'button': stats.buttons++; break;
                    case 'a': stats.links++; break;
                    case 'form': stats.forms++; break;
                    case 'img': stats.images++; break;
                    case 'video': stats.videos++; break;
                    case 'table': stats.tables++; break;
                    case 'dialog': stats.dialogs++; break;
                    case 'iframe': stats.iframes++; break;
                    case 'canvas': stats.canvas++; break;
                    case 'svg': stats.svg++; break;
                    case 'article': stats.articles++; break;
                    case 'section': stats.sections++; break;
                    case 'h1': case 'h2': case 'h3': case 'h4': case 'h5': case 'h6':
                        stats.headings++; break;
                    case 'p': stats.paragraphs++; break;
                    case 'ul': case 'ol': stats.lists++; break;
                }

                if (tag === 'input') {
                    const type = el.getAttribute('type') || 'text';
                    switch(type) {
                        case 'text': stats.text_inputs++; break;
                        case 'password': stats.password_inputs++; break;
                        case 'email': stats.email_inputs++; break;
                        case 'number': stats.number_inputs++; break;
                        case 'checkbox': stats.checkboxes++; break;
                        case 'radio': stats.radio_buttons++; break;
                    }
                }
                if (tag === 'select') stats.dropdowns++;
            });

            stats.total_text = document.body ? document.body.innerText.length : 0;
            return stats;
        })()
        """
        return self.js(script) or {}

    def _detect_structure(self) -> Dict:
        script = """
        (function() {
            const structure = {};
            const semantic = {
                'navigation': 'nav, [role="navigation"], header nav, .nav, #nav',
                'main_content': 'main, [role="main"], article, .content, #content',
                'sidebar': 'aside, [role="complementary"], .sidebar, #sidebar',
                'footer': 'footer, [role="contentinfo"], .footer, #footer',
                'header': 'header, [role="banner"], .header, #header',
                'search': '[role="search"], form:has(input[type="search"]), input[type="search"]',
                'login': 'form:has(input[type="password"])',
                'cart': '.cart, #cart, [data-cart]',
                'profile': '.profile, #profile, [data-profile]'
            };

            for (const [key, selector] of Object.entries(semantic)) {
                const elements = document.querySelectorAll(selector);
                const items = [];
                elements.forEach(el => {
                    const rect = el.getBoundingClientRect();
                    const text = el.textContent.trim().slice(0, 100);
                    if (text) {
                        items.push({
                            text: text,
                            position: { x: Math.round(rect.x), y: Math.round(rect.y) },
                            visible: rect.width > 0 && rect.height > 0
                        });
                    }
                });
                if (items.length > 0) {
                    structure[key] = items.slice(0, 5);
                }
            }
            return structure;
        })()
        """
        return self.js(script) or {}

    def _detect_actions(self) -> Dict:
        script = """
        (function() {
            const actions = {
                submit: [],
                search: [],
                navigation: [],
                social: [],
                registration: [],
                ecommerce: []
            };

            const patterns = {
                submit: /Submit|Save|Send|Post|Upload|Create|Add|Update|Delete/i,
                search: /Search|Find|Lookup|Query/i,
                navigation: /Back|Next|Previous|Home|About|Contact|Sign In|Sign Out|Logout/i,
                social: /Like|Share|Follow|Comment|Reply|Tweet|Post/i,
                registration: /Register|Sign Up|Join|Subscribe|Enroll|Apply/i,
                ecommerce: /Add to Cart|Buy Now|Checkout|Order|Payment|Purchase/i
            };

            document.querySelectorAll('button, input[type="button"], input[type="submit"], [role="button"], a[role="button"]').forEach(el => {
                const text = el.textContent || el.value || '';
                const clean = text.trim();
                if (clean.length > 1 && clean.length < 60) {
                    for (const [type, pattern] of Object.entries(patterns)) {
                        if (pattern.test(clean)) {
                            actions[type].push(clean);
                            break;
                        }
                    }
                }
            });

            document.querySelectorAll('a').forEach(el => {
                const text = el.textContent.trim();
                if (text.length > 1 && text.length < 60) {
                    for (const [type, pattern] of Object.entries(patterns)) {
                        if (pattern.test(text)) {
                            actions[type].push(text);
                            break;
                        }
                    }
                }
            });

            for (const key in actions) {
                actions[key] = [...new Set(actions[key])].slice(0, 8);
            }
            return actions;
        })()
        """
        return self.js(script) or {}

    def _analyze_forms(self) -> List[Dict]:
        script = """
        (function() {
            const forms = [];
            document.querySelectorAll('form').forEach(form => {
                const fields = [];
                form.querySelectorAll('input, select, textarea').forEach(field => {
                    const type = field.getAttribute('type') || field.tagName.toLowerCase();
                    const name = field.getAttribute('name') || '';
                    const placeholder = field.getAttribute('placeholder') || '';
                    fields.push({
                        type: type,
                        name: name.slice(0, 20),
                        placeholder: placeholder.slice(0, 30),
                        required: field.hasAttribute('required')
                    });
                });
                if (fields.length > 0) {
                    forms.push({
                        action: form.getAttribute('action') || '',
                        method: form.getAttribute('method') || 'GET',
                        fields: fields.slice(0, 10)
                    });
                }
            });
            return forms;
        })()
        """
        return self.js(script) or []

    def _analyze_links(self) -> Dict:
        script = """
        (function() {
            const links = { total: 0, internal: [], external: [], social: [] };
            const domain = window.location.hostname;
            const socialDomains = ['facebook.com', 'twitter.com', 'x.com', 'linkedin.com',
                'instagram.com', 'youtube.com', 'tiktok.com', 'github.com', 'discord.com'];

            document.querySelectorAll('a[href]').forEach(el => {
                const href = el.getAttribute('href');
                if (!href || href.startsWith('#') || href.startsWith('javascript:')) return;
                try {
                    const url = new URL(href, window.location.href);
                    const text = el.textContent.trim().slice(0, 50) || '[No text]';
                    const linkDomain = url.hostname;
                    links.total++;

                    const data = { href: url.href, text: text, domain: linkDomain };

                    if (linkDomain === domain || linkDomain === '') {
                        links.internal.push(data);
                    } else {
                        links.external.push(data);
                        if (socialDomains.some(d => linkDomain.includes(d))) {
                            links.social.push(data);
                        }
                    }
                } catch(e) {}
            });

            links.internal = links.internal.slice(0, 30);
            links.external = links.external.slice(0, 30);
            links.social = links.social.slice(0, 15);
            return links;
        })()
        """
        return self.js(script) or {'total': 0, 'internal': [], 'external': [], 'social': []}

    def _extract_keywords(self) -> List[str]:
        if not self.text:
            return []
            
        clean_text = TextCleaner.clean(self.text)

        if SPACY_AVAILABLE and nlp:
            try:
                doc = nlp(clean_text[:50000])
                keywords = [token.text for token in doc
                           if token.pos_ in ['NOUN', 'PROPN']
                           and not token.is_stop
                           and len(token.text) > 2]
            except:
                keywords = re.findall(r'\b[A-Z][a-z]{2,}\b', clean_text)
        else:
            keywords = re.findall(r'\b[A-Z][a-z]{2,}\b', clean_text)

        stopwords = {'The', 'This', 'That', 'These', 'Those', 'And', 'Or', 'But',
                    'For', 'Nor', 'On', 'At', 'To', 'By', 'In', 'Of', 'With'}
        keywords = [w for w in keywords if w not in stopwords]
        counter = Counter(keywords)
        return [word for word, _ in counter.most_common(20)]

    def _generate_summary(self, results: Dict) -> Dict:
        summary = {
            'title': self.title,
            'url': self.url,
            'domain': self.domain,
            'page_type': results.get('page_type', {}).get('page_type', 'unknown'),
            'confidence': results.get('page_type', {}).get('confidence', 0),
            'key_findings': [],
            'opportunities_found': [],
            'actions_available': []
        }

        structure = results.get('structure', {})
        for section_type, sections in structure.items():
            if sections:
                visible = sum(1 for s in sections if s.get('visible', True))
                summary['key_findings'].append(f"{section_type}: {visible} visible sections")

        opportunities = results.get('opportunities', {})
        for opp_type, opp_list in opportunities.items():
            if opp_list:
                summary['opportunities_found'].append(f"{len(opp_list)} {opp_type}")

        actions = results.get('actions', {})
        for action_type, action_list in actions.items():
            if action_list:
                summary['actions_available'].extend(action_list[:3])

        # Add entity count
        entities = results.get('entities', {})
        if entities:
            entity_summary = []
            for entity_type, entity_list in entities.items():
                if entity_list:
                    entity_summary.append(f"{len(entity_list)} {entity_type}")
            if entity_summary:
                summary['key_findings'].append(f"Entities found: {', '.join(entity_summary[:3])}")

        return summary

    def close(self):
        if self.ws:
            try:
                self.ws.close()
            except:
                pass

# ============================================================================
# DISPLAY FUNCTIONS
# ============================================================================

def display_results(results: Dict):
    """Display results with better formatting"""

    if 'error' in results:
        console.print(f"[red]Error: {results['error']}[/red]")
        return

    console.print()
    console.print(Panel(
        f"[bold cyan]🌐 {results['summary']['title'][:80]}[/bold cyan]",
        subtitle=f"{results['url']}",
        border_style="cyan"
    ))

    # Page Type
    page_type = results.get('page_type', {})
    console.print(f"[bold]Page Type:[/bold] {page_type.get('page_type', 'unknown')} "
                 f"([yellow]{page_type.get('confidence', 0):.0%}[/yellow] confidence)")
    if page_type.get('evidence'):
        console.print(f"[dim]Evidence: {', '.join(page_type['evidence'][:3])}[/dim]")

    # DOM Stats
    dom_stats = results.get('dom_stats', {})
    if dom_stats:
        console.print()
        console.print("[bold cyan]📊 Page Stats[/bold cyan]")
        stats_text = []
        important = ['buttons', 'links', 'forms', 'images', 'text_inputs', 'dropdowns']
        for key in important:
            if dom_stats.get(key, 0) > 0:
                stats_text.append(f"[cyan]{key.replace('_', ' ').title()}[/cyan]: {dom_stats[key]}")
        console.print("  " + " | ".join(stats_text))
        console.print(f"  [dim]Total Elements: {dom_stats.get('total_elements', 0)} | Text: {dom_stats.get('total_text', 0)} chars[/dim]")

    # Opportunities
    opportunities = results.get('opportunities', {})
    if opportunities:
        console.print()
        console.print("[bold green]💼 Opportunities[/bold green]")
        for opp_type, opp_list in opportunities.items():
            if opp_list:
                console.print(f"  [green]{opp_type.title()}:[/green]")
                for opp in opp_list[:5]:
                    console.print(f"    • {opp}")

    # Actions
    actions = results.get('actions', {})
    if actions:
        console.print()
        console.print("[bold blue]⚡ Actions[/bold blue]")
        for action_type, action_list in actions.items():
            if action_list:
                console.print(f"  [blue]{action_type.title()}:[/blue] {', '.join(action_list[:4])}")

    # Entities (Enhanced display)
    entities = results.get('entities', {})
    if entities:
        console.print()
        console.print("[bold magenta]🏷️ Key Entities[/bold magenta]")
        
        # Priority display order
        priority = ['organization', 'location', 'person', 'date', 'deadline', 'prize', 'skill', 'email', 'phone', 'url']
        
        for entity_type in priority:
            if entity_type in entities and entities[entity_type]:
                display_type = entity_type.title()
                entity_list = entities[entity_type][:4]  # Show up to 4
                
                # Color code different types
                color = {
                    'organization': 'magenta',
                    'location': 'cyan',
                    'person': 'green',
                    'date': 'yellow',
                    'deadline': 'red',
                    'prize': 'green',
                    'skill': 'blue',
                    'email': 'cyan',
                    'phone': 'yellow',
                    'url': 'blue'
                }.get(entity_type, 'white')
                
                console.print(f"  [{color}]{display_type}:[/{color}] {', '.join(entity_list)}")

    # Links
    links = results.get('links', {})
    if links:
        console.print()
        console.print("[bold cyan]🔗 Links[/bold cyan]")
        console.print(f"  Total: {links.get('total', 0)} | Internal: {len(links.get('internal', []))} | "
                     f"External: {len(links.get('external', []))} | Social: {len(links.get('social', []))}")

    # Keywords
    keywords = results.get('keywords', [])
    if keywords:
        console.print()
        console.print("[bold yellow]🔑 Topics[/bold yellow]")
        console.print("  " + " ".join([f"[yellow]{k}[/yellow]" for k in keywords[:12]]))

    # Summary
    summary = results.get('summary', {})
    if summary.get('key_findings') or summary.get('opportunities_found'):
        console.print()
        console.print("[bold white]📋 Summary[/bold white]")
        for finding in summary.get('key_findings', [])[:5]:
            console.print(f"  • {finding}")
        for opp in summary.get('opportunities_found', [])[:3]:
            console.print(f"  • Found {opp}")

# ============================================================================
# MAIN
# ============================================================================

def main():
    console.clear()
    console.print(Panel(
        "[bold cyan]🌐 UNIVERSAL PAGE UNDERSTANDING ENGINE v5[/bold cyan]",
        subtitle="Production | Hybrid NLP | 10 Layers",
        border_style="green"
    ))
    console.print("[dim]DOM | Structure | Page Type | Entities | Opportunities | Actions | Forms | Links | Keywords | Summary[/dim]")
    console.print()

    if not SPACY_AVAILABLE:
        console.print("[yellow]⚠️ spaCy not available - using regex/rule fallback[/yellow]")
        console.print("[dim]  For better results: pip install spacy && python -m spacy download en_core_web_sm[/dim]")
        console.print("[dim]  Hybrid extraction still works with rules and patterns[/dim]")
        console.print()

    port = int(Prompt.ask("Chrome Port", default="9241"))
    engine = UniversalPageEngineV5(port)

    if not engine.connect():
        console.print("[red]❌ Failed to connect to Chrome[/red]")
        return

    console.print(f"[green]✅ Connected to: {engine.title}[/green]")
    console.print(f"[dim]   {engine.url}[/dim]")
    console.print()

    if Confirm.ask("Run complete page analysis?"):
        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=True) as progress:
            task = progress.add_task("Analyzing page...", total=None)
            results = engine.analyze()

        display_results(results)

        if Confirm.ask("Save analysis results?"):
            timestamp = int(time.time())
            filename = f"page_analysis_{timestamp}.json"
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2, default=str)
            console.print(f"[green]✅ Saved to {filename}[/green]")

    engine.close()
    console.print("[green]Goodbye! 👋[/green]")

if __name__ == "__main__":
    main()
