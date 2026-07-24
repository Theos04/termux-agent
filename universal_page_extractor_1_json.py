#!/usr/bin/env python3
"""
Universal Page Understanding Engine v4 - PATCHED
----------------------------------------------
Production-ready with:
- Cleaner text extraction
- Better opportunity parsing
- Improved entity extraction
- Smart deduplication
- Rich output formatting
- FIXED: EntityExtractorV2 safe group extraction
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
            r'[🔥💡⭐🏆🎯🎖️]',  # Emojis
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
# ENHANCED OPPORTUNITY DETECTOR
# ============================================================================

class OpportunityDetectorV2:
    """Enhanced opportunity detection with better parsing"""

    # More specific patterns
    JOB_PATTERNS = [
        r'(?:job|position|role|opening|vacancy)\s*(?:title|name|:)?\s*["\']?([A-Z][A-Za-z\s&,-]{5,50})["\']?',
        r'(?:hiring|recruiting|looking for)\s*["\']?([A-Z][A-Za-z\s&,-]{5,50})["\']?',
        r'([A-Z][A-Za-z\s&,-]{5,50})\s*(?:job|position|role|opening)',
        r'(?:we\'re hiring|join our team|career opportunity)\s*["\']?([A-Z][A-Za-z\s&,-]{5,50})["\']?',
    ]

    INTERNSHIP_PATTERNS = [
        r'(?:internship|intern|trainee|apprentice)\s*(?:opportunity|position|program)?\s*[:.]?\s*["\']?([A-Z][A-Za-z\s&,-]{5,50})["\']?',
        r'(?:intern)\s*["\']?([A-Z][A-Za-z\s&,-]{5,50})["\']?\s*(?:internship|position)',
        r'(?:apply for|join as)\s*["\']?([A-Z][A-Za-z\s&,-]{5,50})["\']?\s*(?:intern|internship)',
    ]

    HACKATHON_PATTERNS = [
        r'(?:hackathon|hack|challenge|competition)\s*(?:name|title|:)?\s*["\']?([A-Z][A-Za-z0-9\s&,.-]{5,50})["\']?',
        r'([A-Z][A-Za-z0-9\s&,.-]{5,50})\s*(?:hackathon|hack|challenge)',
        r'(?:register for|participate in|join)\s*["\']?([A-Z][A-Za-z0-9\s&,.-]{5,50})["\']?\s*(?:hackathon|hack)',
    ]

    EVENT_PATTERNS = [
        r'(?:event|conference|workshop|seminar|webinar)\s*(?:name|title|:)?\s*["\']?([A-Z][A-Za-z0-9\s&,.-]{5,50})["\']?',
        r'([A-Z][A-Za-z0-9\s&,.-]{5,50})\s*(?:event|conference|workshop)',
        r'(?:join|attend|register for)\s*["\']?([A-Z][A-Za-z0-9\s&,.-]{5,50})["\']?\s*(?:event|conference|workshop)',
    ]

    @classmethod
    def detect(cls, text: str, html: str) -> Dict:
        """Extract opportunities with better parsing"""
        if not text:
            return {}

        # Clean text first
        clean_text = TextCleaner.clean(text)

        opportunities = {
            'jobs': [],
            'internships': [],
            'hackathons': [],
            'events': [],
            'scholarships': [],
            'courses': []
        }

        # Extract using patterns
        for opp_type, patterns in [
            ('jobs', cls.JOB_PATTERNS),
            ('internships', cls.INTERNSHIP_PATTERNS),
            ('hackathons', cls.HACKATHON_PATTERNS),
            ('events', cls.EVENT_PATTERNS)
        ]:
            for pattern in patterns:
                try:
                    matches = re.finditer(pattern, clean_text, re.IGNORECASE)
                    for match in matches:
                        try:
                            # Safely extract group 1
                            if match.groups() and len(match.groups()) >= 1:
                                opportunity = match.group(1)
                                if opportunity is not None:
                                    opportunity = opportunity.strip()
                                    if opportunity and len(opportunity) > 3 and len(opportunity) < 80:
                                        # Clean the opportunity text
                                        cleaned = TextCleaner.clean_opportunity(opportunity)
                                        if cleaned and len(cleaned) > 3:
                                            opportunities[opp_type].append(cleaned)
                        except (IndexError, AttributeError):
                            continue
                except Exception:
                    continue

        # Also extract from HTML attributes (often have cleaner text)
        html_patterns = [
            (r'title="([^"]{10,60})"', 'jobs'),
            (r'aria-label="([^"]{10,60})"', 'jobs'),
            (r'data-title="([^"]{10,60})"', 'jobs'),
        ]

        for pattern, opp_type in html_patterns:
            try:
                matches = re.finditer(pattern, html, re.IGNORECASE)
                for match in matches:
                    try:
                        if match.groups() and len(match.groups()) >= 1:
                            text_match = match.group(1)
                            if text_match is not None:
                                text_match = text_match.strip()
                                if text_match and len(text_match) > 5:
                                    # Check if it sounds like an opportunity
                                    keywords = ['job', 'intern', 'hack', 'event', 'position', 'role', 'opportunity']
                                    if any(kw in text_match.lower() for kw in keywords):
                                        opportunities[opp_type].append(text_match)
                    except (IndexError, AttributeError):
                        continue
            except Exception:
                continue

        # Deduplicate and clean
        for key in opportunities:
            # Remove duplicates while preserving order
            seen = set()
            unique = []
            for item in opportunities[key]:
                # Normalize for deduplication
                normalized = item.lower().strip()
                if normalized not in seen and len(item) > 3:
                    seen.add(normalized)
                    unique.append(item)
            opportunities[key] = unique[:10]  # Limit to 10 per type

        # Remove empty lists
        return {k: v for k, v in opportunities.items() if v}

# ============================================================================
# ENHANCED PAGE TYPE DETECTOR WITH CLEANER OUTPUT
# ============================================================================

class PageTypeDetectorV2:
    """Enhanced page type detection with cleaner output"""

    # Cleaner domain mapping
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
    }

    # Cleaner patterns with weights
    PATTERNS = {
        'jobs': {
            'keywords': ['hiring', 'career', 'job', 'position', 'apply', 'vacancy', 'opening'],
            'weight': 0.8
        },
        'internships': {
            'keywords': ['internship', 'intern', 'trainee', 'apprentice', 'stipend'],
            'weight': 0.9
        },
        'hackathons': {
            'keywords': ['hackathon', 'hack', 'challenge', 'competition', 'prize', 'winner'],
            'weight': 0.9
        },
        'events': {
            'keywords': ['register', 'event', 'conference', 'workshop', 'seminar', 'webinar'],
            'weight': 0.7
        },
        'ecommerce': {
            'keywords': ['buy', 'shop', 'cart', 'checkout', 'price', 'discount'],
            'weight': 0.7
        },
        'social': {
            'keywords': ['post', 'share', 'like', 'follow', 'comment', 'tweet'],
            'weight': 0.6
        },
        'education': {
            'keywords': ['course', 'learn', 'study', 'class', 'lecture', 'tutorial'],
            'weight': 0.7
        },
        'coding': {
            'keywords': ['problem', 'solve', 'challenge', 'algorithm', 'code', 'programming'],
            'weight': 0.7
        }
    }

    @classmethod
    def detect(cls, text: str, url: str, title: str) -> Dict:
        """Enhanced page type detection"""
        if not text:
            return {'page_type': 'unknown', 'confidence': 0.0, 'evidence': ['No text'], 'all_scores': {}}
            
        clean_text = TextCleaner.clean(text[:20000].lower())
        url_lower = url.lower()
        title_lower = title.lower()

        scores = defaultdict(float)
        evidence = []

        # Domain detection
        for domain, page_type in cls.DOMAIN_MAPPING.items():
            if domain in url_lower:
                scores[page_type] += 0.9
                evidence.append(f"domain: {domain}")
                break

        # Keyword detection
        for page_type, config in cls.PATTERNS.items():
            match_count = 0
            for keyword in config['keywords']:
                # Count occurrences
                count = len(re.findall(r'\b' + keyword + r'\w*\b', clean_text))
                if count > 0:
                    match_count += count
                    scores[page_type] += count * 0.1

            if match_count > 0:
                evidence.append(f"{match_count} {page_type} indicators")

        # Title detection
        for page_type, config in cls.PATTERNS.items():
            for keyword in config['keywords']:
                if keyword in title_lower:
                    scores[page_type] += 0.1
                    evidence.append(f"title contains '{keyword}'")

        # Normalize scores
        total = sum(scores.values())
        if total > 0:
            for key in scores:
                scores[key] = min(scores[key] / total, 1.0)

        # Get best
        if scores:
            best_type = max(scores, key=scores.get)
            best_score = scores[best_type]

            if best_score > 0.2:
                return {
                    'page_type': best_type,
                    'confidence': best_score,
                    'evidence': list(set(evidence))[:5],
                    'all_scores': {k: round(v, 2) for k, v in scores.items() if v > 0.1}
                }

        return {
            'page_type': 'unknown',
            'confidence': 0.0,
            'evidence': ['No strong indicators'],
            'all_scores': {}
        }

# ============================================================================
# ENHANCED ENTITY EXTRACTOR - PATCHED VERSION
# ============================================================================

class EntityExtractorV2:
    """Enhanced entity extraction with better patterns and safe group extraction"""

    PATTERNS = {
        'organization': r'\b([A-Z][A-Za-z\s&,.-]{2,30})\s+(?:Inc|Corp|LLC|Ltd|Pvt|Technologies|Solutions|Systems|Labs|Foundation|Institute|University|College|School|Academy|Group|Enterprises|Ventures|Capital|Partners|Associates|Consulting|Services|Digital|Creative|Media|Studios|Works|Factory|Labs?|Co\.|Company)\b',
        'location': r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s*[,.]?\s*(?:India|USA|UK|Canada|Australia|Germany|France|Japan|China|Singapore|Dubai|UAE|Europe|Asia|Africa)\b|\b(?:Mumbai|Delhi|Bangalore|Chennai|Hyderabad|Pune|Kolkata|Ahmedabad|Jaipur|Lucknow|Nagpur|Indore|Bhopal|Chandigarh|Noida|Gurgaon|Faridabad|Ghaziabad|Coimbatore|Vizag|Surat|Vadodara|Ludhiana|Agra|Varanasi|Patna|Ranchi|Bhubaneswar|Guwahati)\b',
        'deadline': r'\b(?:deadline|last date|apply by|submit by|due|ends? on?)\s*(?:is\s*)?([A-Za-z]+\s+\d{1,2},?\s+\d{4}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
        'date': r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},?\s+\d{4}\b|\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b',
        'prize': r'\b(?:prize|reward|cash|scholarship|grant)\s*(?:pool|amount|worth|value)?\s*(?:of\s*)?[\$₹]?\d+(?:,\d{3})*(?:\.\d{2})?\s*(?:USD|INR|EUR)?',
        'skill': r'\b(Python|Java|JavaScript|TypeScript|C\+\+|C#|PHP|Ruby|Go|Rust|Swift|Kotlin|React|Angular|Vue|Svelte|Next\.js|Node\.js|Django|Flask|Spring|AWS|Azure|GCP|Docker|Kubernetes|Terraform|SQL|NoSQL|MongoDB|PostgreSQL|MySQL|Redis|Elasticsearch|Kafka|RabbitMQ|Machine Learning|AI|Deep Learning|NLP|Computer Vision|Data Science|Analytics|DevOps|SRE|Blockchain|IoT|AR/VR|Game Development|Cybersecurity|Cloud|Frontend|Backend|Full Stack|Mobile|iOS|Android|Flutter|React Native)\b',
    }

    @classmethod
    def extract(cls, text: str) -> Dict[str, List[str]]:
        """Extract entities with better cleaning and safe group extraction"""
        entities = defaultdict(list)
        
        if not text:
            return {}
            
        clean_text = TextCleaner.clean(text)

        # Use spaCy if available
        if SPACY_AVAILABLE and nlp:
            try:
                doc = nlp(clean_text[:100000])
                for ent in doc.ents:
                    if ent.label_ in ['ORG', 'GPE', 'PERSON', 'DATE', 'MONEY']:
                        if len(ent.text) > 2:
                            entities[ent.label_.lower()].append(ent.text)
            except Exception:
                pass

        # Always use regex patterns - FIXED with safe group extraction
        for entity_type, pattern in cls.PATTERNS.items():
            try:
                matches = re.finditer(pattern, clean_text, re.IGNORECASE)
                for match in matches:
                    # SAFE: Check if group 1 exists before accessing it
                    try:
                        # Check if the match has group 1
                        if match.groups() and len(match.groups()) >= 1:
                            entity = match.group(1)
                            if entity is not None:
                                entity = entity.strip()
                                if entity and len(entity) > 2:
                                    # For date/deadline, avoid adding common words
                                    if entity_type in ['date', 'deadline']:
                                        if entity.lower() not in ['date', 'deadline', 'last date']:
                                            entities[entity_type].append(entity)
                                    else:
                                        entities[entity_type].append(entity)
                    except (IndexError, AttributeError):
                        # If no group 1, try using the full match
                        try:
                            entity = match.group(0).strip()
                            if entity and len(entity) > 2:
                                # Only add if it's not just a pattern like "deadline"
                                if not any(keyword in entity.lower() for keyword in ['deadline', 'date', 'prize']):
                                    entities[entity_type].append(entity)
                        except Exception:
                            continue
            except Exception:
                # Skip this pattern if it causes issues
                continue

        # Deduplicate and filter
        filtered = {}
        for entity_type, entity_list in entities.items():
            # Remove very short or very long
            filtered_list = [e for e in entity_list if 2 < len(e) < 100]
            # Deduplicate while preserving order
            seen = set()
            unique_list = []
            for e in filtered_list:
                if e not in seen:
                    seen.add(e)
                    unique_list.append(e)
            filtered[entity_type] = unique_list[:10]

        # Map spaCy labels to our types
        type_mapping = {
            'org': 'organization',
            'gpe': 'location',
            'person': 'person',
            'date': 'date',
            'money': 'prize'
        }

        result = {}
        for key, value in filtered.items():
            mapped_key = type_mapping.get(key, key)
            if mapped_key not in result:
                result[mapped_key] = []
            # Only add if not already present
            for item in value:
                if item not in result[mapped_key]:
                    result[mapped_key].append(item)

        # Limit each type to 10 items
        for key in result:
            result[key] = result[key][:10]

        return {k: v for k, v in result.items() if v}

# ============================================================================
# MAIN ENGINE V4
# ============================================================================

class UniversalPageEngineV4:
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
        results['page_type'] = PageTypeDetectorV2.detect(self.text, self.url, self.title)

        # Layer 4: Entities
        console.print("[dim]  Layer 4: Entity Extraction...[/dim]")
        results['entities'] = EntityExtractorV2.extract(self.text)

        # Layer 5: Opportunities
        console.print("[dim]  Layer 5: Opportunity Detection...[/dim]")
        results['opportunities'] = OpportunityDetectorV2.detect(self.text, self.html)

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

    # Entities
    entities = results.get('entities', {})
    if entities:
        console.print()
        console.print("[bold magenta]🏷️ Key Entities[/bold magenta]")
        for entity_type in ['organization', 'location', 'date', 'deadline', 'prize', 'skill']:
            if entity_type in entities and entities[entity_type]:
                console.print(f"  [magenta]{entity_type.title()}:[/magenta] {', '.join(entities[entity_type][:3])}")

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
        "[bold cyan]🌐 UNIVERSAL PAGE UNDERSTANDING ENGINE v4 - PATCHED[/bold cyan]",
        subtitle="Production | No LLM | 10 Layers | Fixed Entity Extraction",
        border_style="green"
    ))
    console.print("[dim]DOM | Structure | Page Type | Entities | Opportunities | Actions | Forms | Links | Keywords | Summary[/dim]")
    console.print()

    if not SPACY_AVAILABLE:
        console.print("[yellow]⚠️ spaCy not available - using regex fallback[/yellow]")
        console.print("[dim]  Install: pip install spacy && python -m spacy download en_core_web_sm[/dim]")
        console.print()

    port = int(Prompt.ask("Chrome Port", default="9241"))
    engine = UniversalPageEngineV4(port)

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
