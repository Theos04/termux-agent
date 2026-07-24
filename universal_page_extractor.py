#!/usr/bin/env python3
"""
Universal Page Understanding Engine v2
--------------------------------------
NO LLM. Pure deterministic understanding using:
- Regex patterns for structure detection
- spaCy for NLP (NER, POS, entity extraction)
- Statistical methods for classification
- Heuristics for capability detection

100% reliable. Never dies. Works on ANY page.
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
from rich.tree import Tree
from enum import Enum

# Try importing spaCy - if not available, use fallback
try:
    import spacy
    SPACY_AVAILABLE = True
    nlp = spacy.load("en_core_web_sm")
except:
    SPACY_AVAILABLE = False
    nlp = None

console = Console()

# ============================================================================
# LAYER 1: DETERMINISTIC DOM PARSER
# ============================================================================

@dataclass
class DOMStatistics:
    """Pure DOM stats - no semantics, just counting"""
    buttons: int = 0
    links: int = 0
    forms: int = 0
    images: int = 0
    videos: int = 0
    tables: int = 0
    dialogs: int = 0
    text_inputs: int = 0
    password_inputs: int = 0
    email_inputs: int = 0
    number_inputs: int = 0
    checkboxes: int = 0
    radio_buttons: int = 0
    dropdowns: int = 0
    iframes: int = 0
    canvas: int = 0
    svg: int = 0
    headings: int = 0
    paragraphs: int = 0
    lists: int = 0
    articles: int = 0
    sections: int = 0
    total_elements: int = 0
    total_text: int = 0
    hidden_elements: int = 0
    
    def to_dict(self) -> Dict:
        return {k: v for k, v in asdict(self).items() if v > 0}

# ============================================================================
# LAYER 2: PATTERN-BASED STRUCTURE DETECTION
# ============================================================================

class PageStructure:
    """Detect page structure using regex patterns"""
    
    # Common patterns for different section types
    PATTERNS = {
        'navigation': [
            r'<nav[^>]*>',
            r'class="[^"]*nav[^"]*"',
            r'class="[^"]*menu[^"]*"',
            r'role="navigation"',
            r'aria-label="[Nn]avigation"',
            r'<header[^>]*>.*?(?:nav|menu)'
        ],
        'search': [
            r'input[^>]*type="search"',
            r'input[^>]*name="q"',
            r'input[^>]*name="query"',
            r'input[^>]*placeholder="[Ss]earch"',
            r'input[^>]*placeholder="[Ff]ind"',
            r'role="search"',
            r'aria-label="[Ss]earch"'
        ],
        'main_content': [
            r'<main[^>]*>',
            r'role="main"',
            r'id="[Mm]ain"',
            r'class="[^"]*content[^"]*"',
            r'<article[^>]*>'
        ],
        'sidebar': [
            r'<aside[^>]*>',
            r'role="complementary"',
            r'class="[^"]*sidebar[^"]*"',
            r'class="[^"]*side-bar[^"]*"'
        ],
        'footer': [
            r'<footer[^>]*>',
            r'role="contentinfo"',
            r'class="[^"]*footer[^"]*"',
            r'id="[Ff]ooter"'
        ],
        'header': [
            r'<header[^>]*>',
            r'role="banner"',
            r'class="[^"]*header[^"]*"',
            r'id="[Hh]eader"'
        ],
        'login_form': [
            r'input[^>]*type="password"',
            r'form[^>]*action="[^"]*login',
            r'form[^>]*action="[^"]*signin',
            r'class="[^"]*login[^"]*"'
        ],
        'cart': [
            r'class="[^"]*cart[^"]*"',
            r'id="[Cc]art"',
            r'aria-label="[Cc]art"',
            r'href="[^"]*cart[^"]*"'
        ],
        'profile': [
            r'class="[^"]*profile[^"]*"',
            r'id="[Pp]rofile"',
            r'aria-label="[Pp]rofile"',
            r'href="[^"]*profile[^"]*"'
        ]
    }
    
    @classmethod
    def detect_sections(cls, html: str) -> Dict[str, List[Dict]]:
        """Detect sections using regex patterns"""
        sections = defaultdict(list)
        
        for section_type, patterns in cls.PATTERNS.items():
            for pattern in patterns:
                matches = re.finditer(pattern, html, re.IGNORECASE)
                for match in matches:
                    # Get context (100 chars before/after)
                    start = max(0, match.start() - 100)
                    end = min(len(html), match.end() + 100)
                    context = html[start:end]
                    
                    # Extract text
                    text_match = re.search(r'>([^<]{10,100})<', context)
                    text = text_match.group(1).strip() if text_match else ''
                    
                    sections[section_type].append({
                        'pattern': pattern,
                        'text': text[:50],
                        'position': match.start(),
                        'confidence': cls._calculate_confidence(match.group(), section_type)
                    })
                    
        # Deduplicate and sort by position
        for section_type in sections:
            unique = {}
            for item in sections[section_type]:
                key = item['text'] or item['position']
                if key not in unique:
                    unique[key] = item
            sections[section_type] = sorted(unique.values(), key=lambda x: x['position'])[:5]
            
        return dict(sections)
    
    @staticmethod
    def _calculate_confidence(match: str, section_type: str) -> float:
        """Calculate confidence based on match quality"""
        confidence = 0.5
        
        # Higher confidence for semantic HTML5 elements
        if match.startswith('<nav>') or match.startswith('<main>') or \
           match.startswith('<header>') or match.startswith('<footer>'):
            confidence = 0.9
        elif 'role=' in match:
            confidence = 0.85
        elif 'aria-label=' in match:
            confidence = 0.8
        elif 'id=' in match:
            confidence = 0.7
        elif 'class=' in match:
            confidence = 0.6
            
        return confidence

# ============================================================================
# LAYER 3: SPA CY-BASED NLP ENGINE (with fallback)
# ============================================================================

class NLPEngine:
    """NLP processing with spaCy, fallback to regex"""
    
    # Fallback patterns when spaCy not available
    ENTITY_PATTERNS = {
        'email': r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        'url': r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+',
        'date': r'\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b|\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},?\s+\d{4}\b',
        'phone': r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b',
        'price': r'\$\d+(?:\.\d{2})?',
        'number': r'\b\d+(?:,\d{3})*(?:\.\d+)?\b'
    }
    
    @classmethod
    def extract_entities(cls, text: str) -> Dict[str, List[str]]:
        """Extract entities using spaCy or fallback"""
        entities = defaultdict(list)
        
        if SPACY_AVAILABLE and nlp:
            doc = nlp(text[:100000])  # Limit for performance
            for ent in doc.ents:
                entities[ent.label_.lower()].append(ent.text)
                
            # Also extract with patterns
            for entity_type, pattern in cls.ENTITY_PATTERNS.items():
                for match in re.finditer(pattern, text):
                    entities[entity_type].append(match.group())
        else:
            # Fallback to regex only
            for entity_type, pattern in cls.ENTITY_PATTERNS.items():
                for match in re.finditer(pattern, text):
                    entities[entity_type].append(match.group())
                    
        # Deduplicate and limit
        for entity_type in entities:
            entities[entity_type] = list(set(entities[entity_type]))[:20]
            
        return dict(entities)
    
    @classmethod
    def extract_keywords(cls, text: str, top_n: int = 30) -> List[str]:
        """Extract important keywords"""
        if SPACY_AVAILABLE and nlp:
            doc = nlp(text[:50000])
            # Get nouns and proper nouns
            keywords = [token.text for token in doc 
                       if token.pos_ in ['NOUN', 'PROPN'] 
                       and not token.is_stop 
                       and len(token.text) > 2]
        else:
            # Simple fallback
            words = re.findall(r'\b[A-Za-z]{3,}\b', text)
            stopwords = {'the', 'this', 'that', 'these', 'those', 'and', 'or', 'but', 
                        'for', 'nor', 'on', 'at', 'to', 'by', 'in', 'of', 'with'}
            keywords = [w for w in words if w.lower() not in stopwords]
            
        # Count frequencies
        counter = Counter(keywords)
        return [word for word, _ in counter.most_common(top_n)]
    
    @classmethod
    def detect_page_type(cls, text: str, url: str, title: str) -> Dict:
        """Detect page type using NLP"""
        text_lower = text[:10000].lower()
        url_lower = url.lower()
        title_lower = title.lower()
        
        scores = defaultdict(float)
        
        # Domain-based detection
        domains = {
            'reddit.com': 'forum',
            'twitter.com': 'social',
            'x.com': 'social',
            'linkedin.com': 'social',
            'youtube.com': 'video',
            'amazon.com': 'ecommerce',
            'flipkart.com': 'ecommerce',
            'github.com': 'docs',
            'wikipedia.org': 'wiki',
            'medium.com': 'blog',
            'indeed.com': 'jobs',
            'unstop.com': 'events',
            'hackerrank.com': 'coding',
            'leetcode.com': 'coding'
        }
        
        for domain, page_type in domains.items():
            if domain in url_lower:
                scores[page_type] += 0.8
                
        # Text-based detection
        patterns = {
            'jobs': ['hiring', 'career', 'job', 'position', 'apply', 'work with us'],
            'blog': ['blog', 'article', 'post', 'published', 'author'],
            'ecommerce': ['buy', 'shop', 'cart', 'checkout', 'price', 'add to cart'],
            'forum': ['forum', 'thread', 'post', 'comment', 'reply', 'discuss'],
            'social': ['post', 'share', 'like', 'follow', 'connect', 'network'],
            'video': ['watch', 'video', 'subscribe', 'view', 'channel'],
            'docs': ['documentation', 'docs', 'api', 'reference', 'guide', 'tutorial'],
            'wiki': ['wiki', 'encyclopedia', 'article', 'history', 'edit'],
            'events': ['register', 'event', 'hackathon', 'conference', 'workshop', 'schedule'],
            'coding': ['problem', 'solve', 'challenge', 'code', 'algorithm', 'programming']
        }
        
        for page_type, keywords in patterns.items():
            for keyword in keywords:
                if keyword in text_lower:
                    scores[page_type] += 0.3
                    
        # Title-based detection
        for page_type, keywords in patterns.items():
            for keyword in keywords:
                if keyword in title_lower:
                    scores[page_type] += 0.2
                    
        # Get top prediction
        if scores:
            best_type = max(scores, key=scores.get)
            best_score = min(scores[best_type], 1.0)
            evidence = [f"Found {len([k for k in patterns.get(best_type, []) if k in text_lower])} indicators"]
        else:
            best_type = 'unknown'
            best_score = 0.0
            evidence = ['No strong indicators']
            
        return {
            'page_type': best_type,
            'confidence': best_score,
            'evidence': evidence,
            'all_scores': dict(scores)
        }

# ============================================================================
# LAYER 4: INTERACTION PATTERN DETECTION
# ============================================================================

class InteractionDetector:
    """Detect interactive elements using patterns"""
    
    # Patterns for different interaction types
    ACTION_PATTERNS = {
        'submit': r'Submit|Save|Send|Post|Upload|Create|Add|Update|Delete|Submit',
        'navigation': r'Back|Next|Previous|Home|About|Contact|Sign In|Sign Out|Logout',
        'search': r'Search|Find|Lookup|Query',
        'social': r'Like|Share|Follow|Comment|Reply|Tweet|Post',
        'ecommerce': r'Add to Cart|Buy Now|Checkout|Order|Payment',
        'registration': r'Register|Sign Up|Join|Subscribe|Enroll'
    }
    
    @classmethod
    def detect_actions(cls, html: str, text: str) -> Dict[str, List[str]]:
        """Detect available actions from page"""
        actions = defaultdict(list)
        
        # Check button text
        button_pattern = r'<button[^>]*>(.*?)</button>|<input[^>]*type="(?:button|submit)"[^>]*value="([^"]*)"'
        for match in re.finditer(button_pattern, html, re.IGNORECASE):
            button_text = match.group(1) or match.group(2) or ''
            for action_type, pattern in cls.ACTION_PATTERNS.items():
                if re.search(pattern, button_text, re.IGNORECASE):
                    actions[action_type].append(button_text.strip())
                    
        # Check link text
        link_pattern = r'<a[^>]*>(.*?)</a>'
        for match in re.finditer(link_pattern, html, re.IGNORECASE):
            link_text = match.group(1).strip()
            if len(link_text) < 50:  # Short links are likely actions
                for action_type, pattern in cls.ACTION_PATTERNS.items():
                    if re.search(pattern, link_text, re.IGNORECASE):
                        actions[action_type].append(link_text)
                        
        # Deduplicate and limit
        for action_type in actions:
            actions[action_type] = list(set(actions[action_type]))[:10]
            
        return dict(actions)

# ============================================================================
# LAYER 5: FORM ANALYZER
# ============================================================================

class FormAnalyzer:
    """Analyze forms and their fields"""
    
    FIELD_PATTERNS = {
        'email': r'type="email"|name="[^"]*email[^"]*"|id="[^"]*email[^"]*"',
        'password': r'type="password"|name="[^"]*password[^"]*"|id="[^"]*password[^"]*"',
        'name': r'name="[^"]*name[^"]*"|id="[^"]*name[^"]*"|placeholder="[Nn]ame"',
        'phone': r'type="tel"|name="[^"]*phone[^"]*"|placeholder="[Pp]hone"',
        'search': r'type="search"|name="q"|name="query"',
        'textarea': r'<textarea',
        'select': r'<select',
        'checkbox': r'type="checkbox"',
        'radio': r'type="radio"',
        'file': r'type="file"',
        'date': r'type="date"|type="datetime"',
        'number': r'type="number"'
    }
    
    @classmethod
    def analyze_forms(cls, html: str) -> List[Dict]:
        """Extract and analyze forms"""
        forms = []
        
        # Find all form tags
        form_pattern = r'<form[^>]*>(.*?)</form>'
        for form_match in re.finditer(form_pattern, html, re.IGNORECASE):
            form_html = form_match.group(1)
            
            # Extract form attributes
            form_start = form_match.group(0)[:200]
            action = re.search(r'action="([^"]*)"', form_start)
            method = re.search(r'method="([^"]*)"', form_start)
            
            form_data = {
                'action': action.group(1) if action else '',
                'method': method.group(1).upper() if method else 'GET',
                'fields': []
            }
            
            # Find fields
            for field_type, pattern in cls.FIELD_PATTERNS.items():
                fields = re.finditer(pattern, form_html, re.IGNORECASE)
                for field in fields:
                    # Try to get label/placeholder
                    field_start = max(0, field.start() - 100)
                    field_end = min(len(form_html), field.end() + 50)
                    context = form_html[field_start:field_end]
                    
                    label_match = re.search(r'>([^<]{1,50})<', context)
                    label = label_match.group(1).strip() if label_match else ''
                    
                    # Get value if present
                    value_match = re.search(r'value="([^"]*)"', context)
                    value = value_match.group(1) if value_match else ''
                    
                    # Get placeholder
                    placeholder_match = re.search(r'placeholder="([^"]*)"', context)
                    placeholder = placeholder_match.group(1) if placeholder_match else ''
                    
                    form_data['fields'].append({
                        'type': field_type,
                        'label': label[:30],
                        'value': value[:20] if value else '',
                        'placeholder': placeholder[:30],
                        'required': 'required' in context.lower()
                    })
                    
            if form_data['fields']:
                forms.append(form_data)
                
        return forms

# ============================================================================
# LAYER 6: LINK ANALYZER
# ============================================================================

class LinkAnalyzer:
    """Analyze links on the page"""
    
    @classmethod
    def analyze_links(cls, html: str, base_url: str) -> Dict:
        """Analyze all links"""
        links = []
        internal = []
        external = []
        social = []
        
        # Extract all links
        link_pattern = r'<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>'
        for match in re.finditer(link_pattern, html, re.IGNORECASE):
            href = match.group(1).strip()
            text = re.sub(r'<[^>]+>', '', match.group(2)).strip()[:50]
            
            if not href or href.startswith('#') or href.startswith('javascript:'):
                continue
                
            # Normalize URL
            full_url = urljoin(base_url, href)
            domain = urlparse(full_url).netloc
            
            link_data = {
                'href': full_url,
                'text': text if text else 'No text',
                'domain': domain
            }
            
            links.append(link_data)
            
            # Classify
            if domain and base_url and domain in base_url:
                internal.append(link_data)
            elif domain:
                external.append(link_data)
                
            # Check for social media
            social_domains = ['facebook.com', 'twitter.com', 'x.com', 'linkedin.com', 
                            'instagram.com', 'youtube.com', 'tiktok.com']
            for social_domain in social_domains:
                if social_domain in domain:
                    social.append(link_data)
                    break
                    
        return {
            'total': len(links),
            'internal': internal,
            'external': external,
            'social': social,
            'all': links[:100]  # Limit for display
        }

# ============================================================================
# MAIN ENGINE - COMBINES ALL LAYERS
# ============================================================================

class UniversalPageEngine:
    """Complete page understanding without AI"""
    
    def __init__(self, port=9236):
        self.port = port
        self.ws = None
        self.connected = False
        self.html = ""
        self.text = ""
        self.url = ""
        self.title = ""
        
    def connect(self):
        """Connect to Chrome"""
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
            ws_url = page_tab.get('webSocketDebuggerUrl')
            
            self.ws = websocket.create_connection(ws_url, timeout=10)
            
            # Enable Runtime
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
        """Fetch all page content"""
        if not self.connected:
            return False
            
        self.html = self.js("document.documentElement.outerHTML") or ""
        self.text = self.js("document.body ? document.body.innerText : ''") or ""
        self.title = self.js("document.title") or "Untitled"
        self.url = self.js("window.location.href") or self.url
        
        return True
        
    def analyze(self) -> Dict:
        """Complete page analysis"""
        console.print("[bold cyan]🔍 Analyzing page...[/bold cyan]")
        
        if not self.fetch_page():
            return {'error': 'Failed to fetch page'}
            
        results = {}
        
        # Layer 1: DOM Statistics
        console.print("[dim]  Layer 1: DOM Statistics...[/dim]")
        results['dom_stats'] = self._get_dom_stats()
        
        # Layer 2: Structure Detection
        console.print("[dim]  Layer 2: Structure Detection...[/dim]")
        results['structure'] = PageStructure.detect_sections(self.html)
        
        # Layer 3: NLP Analysis
        console.print("[dim]  Layer 3: NLP Analysis...[/dim]")
        results['entities'] = NLPEngine.extract_entities(self.text)
        results['keywords'] = NLPEngine.extract_keywords(self.text)
        results['page_type'] = NLPEngine.detect_page_type(self.text, self.url, self.title)
        
        # Layer 4: Interaction Detection
        console.print("[dim]  Layer 4: Interaction Detection...[/dim]")
        results['actions'] = InteractionDetector.detect_actions(self.html, self.text)
        
        # Layer 5: Form Analysis
        console.print("[dim]  Layer 5: Form Analysis...[/dim]")
        results['forms'] = FormAnalyzer.analyze_forms(self.html)
        
        # Layer 6: Link Analysis
        console.print("[dim]  Layer 6: Link Analysis...[/dim]")
        results['links'] = LinkAnalyzer.analyze_links(self.html, self.url)
        
        # Layer 7: Summary
        console.print("[dim]  Layer 7: Generating Summary...[/dim]")
        results['summary'] = self._generate_summary(results)
        
        return results
        
    def _get_dom_stats(self) -> Dict:
        """Get DOM statistics via JavaScript"""
        script = """
        (function() {
            const stats = {
                buttons: 0,
                links: 0,
                forms: 0,
                images: 0,
                videos: 0,
                tables: 0,
                dialogs: 0,
                text_inputs: 0,
                password_inputs: 0,
                email_inputs: 0,
                number_inputs: 0,
                checkboxes: 0,
                radio_buttons: 0,
                dropdowns: 0,
                iframes: 0,
                canvas: 0,
                svg: 0,
                headings: 0,
                paragraphs: 0,
                lists: 0,
                articles: 0,
                sections: 0,
                total_elements: 0,
                total_text: 0,
                hidden_elements: 0
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
        
    def _generate_summary(self, results: Dict) -> Dict:
        """Generate a structured summary"""
        summary = {
            'title': self.title,
            'url': self.url,
            'page_type': results.get('page_type', {}).get('page_type', 'unknown'),
            'confidence': results.get('page_type', {}).get('confidence', 0),
            'key_findings': [],
            'actions_available': [],
            'forms_available': [],
            'links_count': results.get('links', {}).get('total', 0),
            'keywords': results.get('keywords', [])[:10]
        }
        
        # Key findings from structure
        structure = results.get('structure', {})
        for section_type, sections in structure.items():
            if sections:
                summary['key_findings'].append(f"Found {section_type} with {len(sections)} sections")
                
        # Actions
        actions = results.get('actions', {})
        for action_type, action_list in actions.items():
            if action_list:
                summary['actions_available'].extend(action_list[:3])
                
        # Forms
        forms = results.get('forms', [])
        for form in forms[:3]:
            fields = [f['type'] for f in form['fields'][:5]]
            summary['forms_available'].append({
                'action': form['action'],
                'fields': fields
            })
            
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
    """Display analysis results beautifully"""
    
    if 'error' in results:
        console.print(f"[red]Error: {results['error']}[/red]")
        return
        
    # Page Info
    console.print()
    console.print(Panel(f"[bold cyan]🌐 {results['summary']['title']}[/bold cyan]", 
                       subtitle=results['summary']['url'], border_style="cyan"))
    
    # Page Type
    page_type = results.get('page_type', {})
    console.print(f"[bold]Page Type:[/bold] {page_type.get('page_type', 'unknown')} "
                 f"([yellow]{page_type.get('confidence', 0):.0%}[/yellow] confidence)")
    if page_type.get('evidence'):
        console.print(f"[dim]Evidence: {', '.join(page_type['evidence'])}[/dim]")
    
    # DOM Statistics
    dom_stats = results.get('dom_stats', {})
    if dom_stats:
        console.print()
        console.print("[bold cyan]📊 DOM Statistics[/bold cyan]")
        table = Table(box=box.MINIMAL)
        table.add_column("Element", style="cyan")
        table.add_column("Count", style="green")
        
        # Show only non-zero stats
        for key, value in dom_stats.items():
            if value > 0 and key not in ['total_elements', 'total_text', 'hidden_elements']:
                table.add_row(key.replace('_', ' ').title(), str(value))
        
        # Add totals
        table.add_row("━━━━━━━━━━", "━━━━━━━")
        table.add_row("Total Elements", str(dom_stats.get('total_elements', 0)))
        table.add_row("Total Text", f"{dom_stats.get('total_text', 0)} chars")
        console.print(table)
    
    # Structure
    structure = results.get('structure', {})
    if structure:
        console.print()
        console.print("[bold green]🏗️ Page Structure[/bold green]")
        for section_type, sections in structure.items():
            if sections:
                console.print(f"  [cyan]{section_type.title()}[/cyan]: {len(sections)} sections found")
                for section in sections[:2]:
                    text = section.get('text', '')[:40]
                    if text:
                        console.print(f"    [dim]• {text}[/dim]")
    
    # Keywords
    keywords = results.get('keywords', [])
    if keywords:
        console.print()
        console.print("[bold yellow]🔑 Key Topics[/bold yellow]")
        console.print("  " + "  ".join([f"[yellow]{k}[/yellow]" for k in keywords[:15]]))
    
    # Entities
    entities = results.get('entities', {})
    if entities:
        console.print()
        console.print("[bold magenta]🏷️ Entities Found[/bold magenta]")
        for entity_type, entity_list in entities.items():
            if entity_list:
                console.print(f"  [magenta]{entity_type.title()}[/magenta]: {', '.join(entity_list[:5])}")
    
    # Actions
    actions = results.get('actions', {})
    if actions:
        console.print()
        console.print("[bold blue]⚡ Available Actions[/bold blue]")
        for action_type, action_list in actions.items():
            if action_list:
                console.print(f"  [blue]{action_type.title()}[/blue]: {', '.join(action_list[:3])}")
    
    # Forms
    forms = results.get('forms', [])
    if forms:
        console.print()
        console.print("[bold red]📝 Forms Found[/bold red]")
        for i, form in enumerate(forms[:3], 1):
            console.print(f"  [red]Form {i}[/red]: {form['method']} → {form['action']}")
            for field in form['fields'][:5]:
                required = " *" if field['required'] else ""
                console.print(f"    • {field['type']}{required}: {field['label'] or field['placeholder']}")
    
    # Links
    links = results.get('links', {})
    if links:
        console.print()
        console.print("[bold cyan]🔗 Links[/bold cyan]")
        console.print(f"  Total: {links.get('total', 0)}")
        console.print(f"  Internal: {len(links.get('internal', []))}")
        console.print(f"  External: {len(links.get('external', []))}")
        if links.get('social'):
            console.print(f"  Social: {len(links.get('social', []))}")
    
    # Summary
    summary = results.get('summary', {})
    if summary.get('key_findings'):
        console.print()
        console.print("[bold white]📋 Summary[/bold white]")
        for finding in summary['key_findings'][:5]:
            console.print(f"  • {finding}")

# ============================================================================
# MAIN
# ============================================================================

def main():
    console.clear()
    console.print(Panel("[bold cyan]🌐 UNIVERSAL PAGE UNDERSTANDING ENGINE v2[/bold cyan]", 
                       subtitle="No LLM. Pure deterministic understanding.", border_style="green"))
    console.print("[dim]DOM Parser | Structure Detection | NLP (spaCy) | Interaction Detection | Form Analysis[/dim]")
    console.print()
    
    if not SPACY_AVAILABLE:
        console.print("[yellow]⚠️ spaCy not available - using fallback regex engine[/yellow]")
        console.print("[dim]  Install: pip install spacy && python -m spacy download en_core_web_sm[/dim]")
        console.print()
    
    port = int(Prompt.ask("Chrome Port", default="9241"))
    engine = UniversalPageEngine(port)
    
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
        
        # Save results
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
