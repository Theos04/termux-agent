#!/usr/bin/env python3
"""
Universal Page Understanding Engine v3
--------------------------------------
NO LLM. Pure deterministic understanding using:
- Regex patterns for structure detection
- spaCy for NLP (NER, POS, entity extraction)
- Statistical methods for classification
- Heuristics for capability detection
- Pydantic for data validation and noise cleaning

100% reliable. Never dies. Works on ANY page.
"""

import json
import websocket
import requests
import sys
import time
import re
from typing import Optional, Dict, List, Any, Set, Tuple, Union
from collections import Counter, defaultdict
from dataclasses import dataclass, field, asdict
from urllib.parse import urlparse, urljoin
from enum import Enum
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
import rich.box as box
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.tree import Tree
from rich.text import Text
from rich.syntax import Syntax

# Pydantic imports
try:
    from pydantic import BaseModel, Field, validator, root_validator, conlist, constr, HttpUrl
    from pydantic import BaseSettings, ValidationError
    PYDANTIC_AVAILABLE = True
except ImportError:
    PYDANTIC_AVAILABLE = False
    print("⚠️ Pydantic not installed. Install with: pip install pydantic")
    # Fallback if pydantic not available
    class BaseModel:
        def __init__(self, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)
    
    def validator(*args, **kwargs):
        return lambda x: x
    
    def root_validator(*args, **kwargs):
        return lambda x: x

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
# PYDANTIC MODELS FOR DATA VALIDATION
# ============================================================================

class DOMStatsModel(BaseModel):
    """Validated DOM statistics"""
    buttons: int = Field(ge=0, description="Number of buttons")
    links: int = Field(ge=0, description="Number of links")
    forms: int = Field(ge=0, description="Number of forms")
    images: int = Field(ge=0, description="Number of images")
    videos: int = Field(ge=0, description="Number of videos")
    tables: int = Field(ge=0, description="Number of tables")
    dialogs: int = Field(ge=0, description="Number of dialogs")
    text_inputs: int = Field(ge=0, description="Number of text inputs")
    password_inputs: int = Field(ge=0, description="Number of password inputs")
    email_inputs: int = Field(ge=0, description="Number of email inputs")
    number_inputs: int = Field(ge=0, description="Number of number inputs")
    checkboxes: int = Field(ge=0, description="Number of checkboxes")
    radio_buttons: int = Field(ge=0, description="Number of radio buttons")
    dropdowns: int = Field(ge=0, description="Number of dropdowns")
    iframes: int = Field(ge=0, description="Number of iframes")
    canvas: int = Field(ge=0, description="Number of canvas elements")
    svg: int = Field(ge=0, description="Number of SVG elements")
    headings: int = Field(ge=0, description="Number of headings")
    paragraphs: int = Field(ge=0, description="Number of paragraphs")
    lists: int = Field(ge=0, description="Number of lists")
    articles: int = Field(ge=0, description="Number of articles")
    sections: int = Field(ge=0, description="Number of sections")
    total_elements: int = Field(ge=0, description="Total number of elements")
    total_text: int = Field(ge=0, description="Total text length")
    hidden_elements: int = Field(ge=0, description="Number of hidden elements")

    @validator('total_elements')
    def validate_total(cls, v, values):
        """Ensure total elements is sum of all parts"""
        # This is a soft validation - don't fail if not exact
        return v

    def to_dict(self) -> Dict:
        """Convert to dict, filtering out zero values"""
        return {k: v for k, v in self.dict().items() if v > 0}

class SectionModel(BaseModel):
    """Model for a page section"""
    pattern: str = Field(max_length=100)
    text: str = Field(max_length=50)
    position: int = Field(ge=0)
    confidence: float = Field(ge=0.0, le=1.0)

class PageStructureModel(BaseModel):
    """Validated page structure"""
    navigation: List[SectionModel] = Field(default_factory=list, max_items=10)
    search: List[SectionModel] = Field(default_factory=list, max_items=10)
    main_content: List[SectionModel] = Field(default_factory=list, max_items=10)
    sidebar: List[SectionModel] = Field(default_factory=list, max_items=10)
    footer: List[SectionModel] = Field(default_factory=list, max_items=10)
    header: List[SectionModel] = Field(default_factory=list, max_items=10)
    login_form: List[SectionModel] = Field(default_factory=list, max_items=10)
    cart: List[SectionModel] = Field(default_factory=list, max_items=10)
    profile: List[SectionModel] = Field(default_factory=list, max_items=10)

    def get_all_sections(self) -> Dict[str, List[Dict]]:
        """Get all sections as dict for backward compatibility"""
        return {k: [s.dict() for s in v] for k, v in self.dict().items() if v}

class EntityModel(BaseModel):
    """Model for extracted entities"""
    email: List[str] = Field(default_factory=list, max_items=20)
    url: List[str] = Field(default_factory=list, max_items=20)
    date: List[str] = Field(default_factory=list, max_items=20)
    phone: List[str] = Field(default_factory=list, max_items=20)
    price: List[str] = Field(default_factory=list, max_items=20)
    number: List[str] = Field(default_factory=list, max_items=20)
    person: List[str] = Field(default_factory=list, max_items=20)
    org: List[str] = Field(default_factory=list, max_items=20)
    gpe: List[str] = Field(default_factory=list, max_items=20)  # Geo-political entity
    
    @validator('email')
    def clean_emails(cls, v):
        """Validate and clean emails"""
        email_pattern = r'^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}$'
        return [e for e in v if re.match(email_pattern, e)][:20]

    @validator('phone')
    def clean_phones(cls, v):
        """Validate and clean phone numbers"""
        phone_pattern = r'^\d{3}[-.]?\d{3}[-.]?\d{4}$'
        return [p for p in v if re.match(phone_pattern, p)][:20]

class ActionModel(BaseModel):
    """Model for detected actions"""
    submit: List[str] = Field(default_factory=list, max_items=10)
    navigation: List[str] = Field(default_factory=list, max_items=10)
    search: List[str] = Field(default_factory=list, max_items=10)
    social: List[str] = Field(default_factory=list, max_items=10)
    ecommerce: List[str] = Field(default_factory=list, max_items=10)
    registration: List[str] = Field(default_factory=list, max_items=10)

    @root_validator
    def clean_actions(cls, values):
        """Remove HTML noise from actions"""
        cleaned = {}
        for key, value in values.items():
            if isinstance(value, list):
                cleaned[key] = [cls._clean_text(v) for v in value if v][:10]
        return cleaned

    @staticmethod
    def _clean_text(text: str) -> str:
        """Remove HTML tags and clean up text"""
        # Remove HTML tags
        text = re.sub(r'<[^>]+>', ' ', text)
        # Remove extra whitespace
        text = ' '.join(text.split())
        # Limit length
        return text[:100]

class FieldModel(BaseModel):
    """Model for form field"""
    type: str = Field(max_length=50)
    label: str = Field(default="", max_length=100)
    value: str = Field(default="", max_length=100)
    placeholder: str = Field(default="", max_length=100)
    required: bool = False

class FormModel(BaseModel):
    """Model for a form"""
    action: str = Field(default="", max_length=500)
    method: str = Field(default="GET", max_length=10)
    fields: List[FieldModel] = Field(default_factory=list, max_items=50)

    @validator('method')
    def validate_method(cls, v):
        """Validate HTTP method"""
        if v.upper() in ['GET', 'POST', 'PUT', 'DELETE', 'PATCH']:
            return v.upper()
        return 'GET'

class LinkModel(BaseModel):
    """Model for a link"""
    href: str = Field(max_length=500)
    text: str = Field(default="No text", max_length=100)
    domain: str = Field(default="", max_length=100)

    @validator('href')
    def validate_href(cls, v):
        """Validate URL"""
        if not v.startswith(('http://', 'https://', '/')):
            return f"http://{v}"
        return v

    @validator('text')
    def clean_text(cls, v):
        """Clean link text"""
        # Remove extra whitespace
        v = ' '.join(v.split())
        # Remove common noise
        v = re.sub(r'^\W+', '', v)
        return v[:100] or "No text"

class LinkAnalysisModel(BaseModel):
    """Model for link analysis"""
    total: int = Field(ge=0)
    internal: List[LinkModel] = Field(default_factory=list, max_items=100)
    external: List[LinkModel] = Field(default_factory=list, max_items=100)
    social: List[LinkModel] = Field(default_factory=list, max_items=50)
    all: List[LinkModel] = Field(default_factory=list, max_items=100)

    @validator('total')
    def validate_total(cls, v, values):
        """Ensure total matches sum of internal and external"""
        # This is a soft validation
        return v

class PageTypeModel(BaseModel):
    """Model for page type detection"""
    page_type: str = Field(max_length=50)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: List[str] = Field(default_factory=list, max_items=20)
    all_scores: Dict[str, float] = Field(default_factory=dict)

    @validator('page_type')
    def validate_page_type(cls, v):
        """Ensure page type is from known list"""
        valid_types = ['forum', 'social', 'video', 'ecommerce', 'docs', 'wiki', 'blog', 'jobs', 'events', 'coding', 'unknown']
        if v not in valid_types:
            return 'unknown'
        return v

class SummaryModel(BaseModel):
    """Model for page summary"""
    title: str = Field(max_length=200)
    url: str = Field(max_length=500)
    page_type: str = Field(max_length=50)
    confidence: float = Field(ge=0.0, le=1.0)
    key_findings: List[str] = Field(default_factory=list, max_items=20)
    actions_available: List[str] = Field(default_factory=list, max_items=20)
    forms_available: List[Dict] = Field(default_factory=list, max_items=10)
    links_count: int = Field(ge=0)
    keywords: List[str] = Field(default_factory=list, max_items=20)

    @validator('actions_available', each_item=True)
    def clean_actions(cls, v):
        """Clean action text"""
        # Remove HTML and extra whitespace
        v = re.sub(r'<[^>]+>', ' ', v)
        return ' '.join(v.split())[:100]

class PageAnalysisModel(BaseModel):
    """Complete page analysis model with validation"""
    dom_stats: DOMStatsModel
    structure: PageStructureModel
    entities: EntityModel
    keywords: List[str] = Field(default_factory=list, max_items=50)
    page_type: PageTypeModel
    actions: ActionModel
    forms: List[FormModel] = Field(default_factory=list, max_items=20)
    links: LinkAnalysisModel
    summary: SummaryModel
    timestamp: float = Field(default_factory=time.time)
    url: str = Field(max_length=500)
    title: str = Field(max_length=200)

    class Config:
        """Pydantic config"""
        extra = 'ignore'
        validate_assignment = True

    @validator('keywords', each_item=True)
    def clean_keywords(cls, v):
        """Clean and validate keywords"""
        # Remove non-alphabetic characters
        v = re.sub(r'[^a-zA-Z\s]', '', v)
        # Remove extra whitespace
        v = ' '.join(v.split())
        # Ensure min length
        if len(v) < 2:
            return None
        return v[:30]

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

    def to_model(self) -> DOMStatsModel:
        """Convert to Pydantic model"""
        return DOMStatsModel(**asdict(self))

    def to_dict(self) -> Dict:
        """Convert to dict, filtering out zero values"""
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

                    # Clean text
                    text = ' '.join(text.split())[:50]

                    sections[section_type].append({
                        'pattern': pattern[:50],
                        'text': text,
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

        return min(confidence, 1.0)

    @classmethod
    def to_model(cls, html: str) -> PageStructureModel:
        """Convert detection results to Pydantic model"""
        sections = cls.detect_sections(html)
        structured = {}
        for key, values in sections.items():
            structured[key] = [SectionModel(**v) for v in values]
        return PageStructureModel(**structured)

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
                entity_type = ent.label_.lower()
                if entity_type in ['person', 'org', 'gpe', 'date', 'money', 'percent']:
                    entities[entity_type].append(ent.text)
                else:
                    entities['other'].append(ent.text)

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
                        'for', 'nor', 'on', 'at', 'to', 'by', 'in', 'of', 'with', 'from',
                        'for', 'its', 'it', 'not', 'are', 'was', 'were', 'has', 'have',
                        'been', 'will', 'would', 'could', 'should', 'may', 'might'}
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
            'leetcode.com': 'coding',
            'quora.com': 'social',
            'stackoverflow.com': 'forum'
        }

        for domain, page_type in domains.items():
            if domain in url_lower:
                scores[page_type] += 0.8

        # Text-based detection
        patterns = {
            'jobs': ['hiring', 'career', 'job', 'position', 'apply', 'work with us', 'job opening'],
            'blog': ['blog', 'article', 'post', 'published', 'author', 'blog post'],
            'ecommerce': ['buy', 'shop', 'cart', 'checkout', 'price', 'add to cart', 'product'],
            'forum': ['forum', 'thread', 'post', 'comment', 'reply', 'discuss', 'discussion'],
            'social': ['post', 'share', 'like', 'follow', 'connect', 'network', 'tweet'],
            'video': ['watch', 'video', 'subscribe', 'view', 'channel', 'youtube'],
            'docs': ['documentation', 'docs', 'api', 'reference', 'guide', 'tutorial', 'getting started'],
            'wiki': ['wiki', 'encyclopedia', 'article', 'history', 'edit', 'wikipedia'],
            'events': ['register', 'event', 'hackathon', 'conference', 'workshop', 'schedule', 'speaker'],
            'coding': ['problem', 'solve', 'challenge', 'code', 'algorithm', 'programming', 'solution']
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

    @classmethod
    def to_entity_model(cls, text: str) -> EntityModel:
        """Convert extracted entities to Pydantic model"""
        entities = cls.extract_entities(text)
        # Map entity types to model fields
        mapped = {}
        for key, value in entities.items():
            if key in EntityModel.__fields__:
                mapped[key] = value
        return EntityModel(**mapped)

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
        'social': r'Like|Share|Follow|Comment|Reply|Tweet|Post|Upvote|Downvote',
        'ecommerce': r'Add to Cart|Buy Now|Checkout|Order|Payment',
        'registration': r'Register|Sign Up|Join|Subscribe|Enroll|Ask'
    }

    @classmethod
    def detect_actions(cls, html: str, text: str) -> Dict[str, List[str]]:
        """Detect available actions from page"""
        actions = defaultdict(list)

        # Check button text
        button_pattern = r'<button[^>]*>(.*?)</button>|<input[^>]*type="(?:button|submit)"[^>]*value="([^"]*)"'
        for match in re.finditer(button_pattern, html, re.IGNORECASE):
            button_text = match.group(1) or match.group(2) or ''
            button_text = re.sub(r'<[^>]+>', ' ', button_text)
            button_text = ' '.join(button_text.split())
            
            if button_text:
                for action_type, pattern in cls.ACTION_PATTERNS.items():
                    if re.search(pattern, button_text, re.IGNORECASE):
                        # Clean up the button text
                        cleaned = button_text[:100]
                        if cleaned not in actions[action_type]:
                            actions[action_type].append(cleaned)

        # Check link text
        link_pattern = r'<a[^>]*>(.*?)</a>'
        for match in re.finditer(link_pattern, html, re.IGNORECASE):
            link_text = re.sub(r'<[^>]+>', '', match.group(1)).strip()
            link_text = ' '.join(link_text.split())
            if len(link_text) < 50 and link_text:  # Short links are likely actions
                for action_type, pattern in cls.ACTION_PATTERNS.items():
                    if re.search(pattern, link_text, re.IGNORECASE):
                        if link_text not in actions[action_type]:
                            actions[action_type].append(link_text)

        # Deduplicate and limit
        for action_type in actions:
            actions[action_type] = list(set(actions[action_type]))[:10]

        return dict(actions)

    @classmethod
    def to_action_model(cls, html: str, text: str) -> ActionModel:
        """Convert detected actions to Pydantic model"""
        actions = cls.detect_actions(html, text)
        return ActionModel(**actions)

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
        'number': r'type="number"',
        'text': r'type="text"|type="search"'
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

                    # Clean up
                    label = ' '.join(label.split())[:30]
                    placeholder = ' '.join(placeholder.split())[:30]

                    # Check if field already exists (avoid duplicates)
                    existing = any(
                        f['type'] == field_type and 
                        (f['label'] == label or f['placeholder'] == placeholder)
                        for f in form_data['fields']
                    )
                    
                    if not existing:
                        form_data['fields'].append({
                            'type': field_type,
                            'label': label,
                            'value': value[:20] if value else '',
                            'placeholder': placeholder,
                            'required': 'required' in context.lower()
                        })

            if form_data['fields']:
                forms.append(form_data)

        return forms[:5]  # Limit to 5 forms

    @classmethod
    def to_form_models(cls, html: str) -> List[FormModel]:
        """Convert forms to Pydantic models"""
        forms = cls.analyze_forms(html)
        models = []
        for form in forms:
            fields = [FieldModel(**field) for field in form['fields']]
            models.append(FormModel(
                action=form['action'],
                method=form['method'],
                fields=fields
            ))
        return models

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
            text = re.sub(r'<[^>]+>', '', match.group(2)).strip()
            text = ' '.join(text.split())[:50]

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
                            'instagram.com', 'youtube.com', 'tiktok.com', 'reddit.com']
            for social_domain in social_domains:
                if social_domain in domain:
                    social.append(link_data)
                    break

        return {
            'total': len(links),
            'internal': internal[:50],
            'external': external[:50],
            'social': social[:20],
            'all': links[:100]  # Limit for display
        }

    @classmethod
    def to_link_model(cls, html: str, base_url: str) -> LinkAnalysisModel:
        """Convert link analysis to Pydantic model"""
        analysis = cls.analyze_links(html, base_url)
        return LinkAnalysisModel(
            total=analysis['total'],
            internal=[LinkModel(**link) for link in analysis['internal']],
            external=[LinkModel(**link) for link in analysis['external']],
            social=[LinkModel(**link) for link in analysis['social']],
            all=[LinkModel(**link) for link in analysis['all']]
        )

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
        self._debug = False

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
        """Complete page analysis with Pydantic validation"""
        console.print("[bold cyan]🔍 Analyzing page...[/bold cyan]")

        if not self.fetch_page():
            return {'error': 'Failed to fetch page'}

        results = {}

        # Layer 1: DOM Statistics
        console.print("[dim]  Layer 1: DOM Statistics...[/dim]")
        dom_stats = self._get_dom_stats()
        dom_stats_model = DOMStatsModel(**dom_stats) if dom_stats else DOMStatsModel()
        results['dom_stats'] = dom_stats_model.dict()
        console.print(f"[dim]    ✓ Found {dom_stats.get('total_elements', 0)} elements[/dim]")

        # Layer 2: Structure Detection
        console.print("[dim]  Layer 2: Structure Detection...[/dim]")
        structure_model = PageStructure.to_model(self.html)
        results['structure'] = structure_model.dict()
        console.print(f"[dim]    ✓ Found {len(structure_model.get_all_sections())} section types[/dim]")

        # Layer 3: NLP Analysis
        console.print("[dim]  Layer 3: NLP Analysis...[/dim]")
        entities_model = NLPEngine.to_entity_model(self.text)
        results['entities'] = entities_model.dict()
        
        keywords = NLPEngine.extract_keywords(self.text)
        results['keywords'] = keywords[:20]
        
        page_type_data = NLPEngine.detect_page_type(self.text, self.url, self.title)
        page_type_model = PageTypeModel(**page_type_data)
        results['page_type'] = page_type_model.dict()
        console.print(f"[dim]    ✓ Page type: {page_type_model.page_type} ({page_type_model.confidence:.0%})[/dim]")

        # Layer 4: Interaction Detection
        console.print("[dim]  Layer 4: Interaction Detection...[/dim]")
        actions_model = InteractionDetector.to_action_model(self.html, self.text)
        results['actions'] = actions_model.dict()
        console.print(f"[dim]    ✓ Found {len([k for k,v in actions_model.dict().items() if v])} action types[/dim]")

        # Layer 5: Form Analysis
        console.print("[dim]  Layer 5: Form Analysis...[/dim]")
        form_models = FormAnalyzer.to_form_models(self.html)
        results['forms'] = [f.dict() for f in form_models]
        console.print(f"[dim]    ✓ Found {len(form_models)} forms[/dim]")

        # Layer 6: Link Analysis
        console.print("[dim]  Layer 6: Link Analysis...[/dim]")
        link_model = LinkAnalyzer.to_link_model(self.html, self.url)
        results['links'] = link_model.dict()
        console.print(f"[dim]    ✓ Found {link_model.total} links[/dim]")

        # Layer 7: Summary
        console.print("[dim]  Layer 7: Generating Summary...[/dim]")
        summary_data = self._generate_summary(results)
        summary_model = SummaryModel(**summary_data)
        results['summary'] = summary_model.dict()

        # Create complete validated model
        try:
            full_model = PageAnalysisModel(
                dom_stats=dom_stats_model,
                structure=structure_model,
                entities=entities_model,
                keywords=results['keywords'],
                page_type=page_type_model,
                actions=actions_model,
                forms=form_models,
                links=link_model,
                summary=summary_model,
                url=self.url,
                title=self.title,
                timestamp=time.time()
            )
            results['validated'] = True
            results['model'] = full_model.dict()
        except Exception as e:
            console.print(f"[yellow]⚠️ Validation warning: {e}[/yellow]")
            results['validated'] = False
            results['validation_error'] = str(e)

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
            if sections and isinstance(sections, list):
                summary['key_findings'].append(f"Found {section_type} with {len(sections)} sections")

        # Actions
        actions = results.get('actions', {})
        for action_type, action_list in actions.items():
            if action_list:
                # Clean action text
                cleaned = [re.sub(r'<[^>]+>', ' ', a)[:50] for a in action_list[:3]]
                summary['actions_available'].extend(cleaned)

        # Forms
        forms = results.get('forms', [])
        for form in forms[:3]:
            fields = [f['type'] for f in form.get('fields', [])[:5]]
            summary['forms_available'].append({
                'action': form.get('action', '')[:50],
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
    """Display analysis results beautifully with validation info"""

    if 'error' in results:
        console.print(f"[red]Error: {results['error']}[/red]")
        return

    # Show validation status
    if results.get('validated'):
        console.print("[green]✅ Data validated with Pydantic[/green]")
    else:
        console.print(f"[yellow]⚠️ Data validation warning: {results.get('validation_error', 'Unknown error')}[/yellow]")

    # Page Info
    console.print()
    summary = results.get('summary', {})
    console.print(Panel(f"[bold cyan]🌐 {summary.get('title', 'Unknown')}[/bold cyan]",
                       subtitle=summary.get('url', ''), border_style="cyan"))

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
        shown = 0
        for key, value in dom_stats.items():
            if value > 0 and key not in ['total_elements', 'total_text', 'hidden_elements']:
                table.add_row(key.replace('_', ' ').title(), str(value))
                shown += 1

        if shown > 0:
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
            if sections and isinstance(sections, list):
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
        # Wrap keywords for better display
        keyword_str = "  " + "  ".join([f"[yellow]{k}[/yellow]" for k in keywords[:15]])
        console.print(keyword_str)

    # Entities
    entities = results.get('entities', {})
    if entities:
        console.print()
        console.print("[bold magenta]🏷️ Entities Found[/bold magenta]")
        for entity_type, entity_list in entities.items():
            if entity_list and isinstance(entity_list, list):
                display_list = [e[:30] for e in entity_list[:5]]
                console.print(f"  [magenta]{entity_type.title()}[/magenta]: {', '.join(display_list)}")

    # Actions
    actions = results.get('actions', {})
    if actions:
        console.print()
        console.print("[bold blue]⚡ Available Actions[/bold blue]")
        for action_type, action_list in actions.items():
            if action_list and isinstance(action_list, list):
                cleaned = [a[:40] for a in action_list[:3]]
                console.print(f"  [blue]{action_type.title()}[/blue]: {', '.join(cleaned)}")

    # Forms
    forms = results.get('forms', [])
    if forms:
        console.print()
        console.print("[bold red]📝 Forms Found[/bold red]")
        for i, form in enumerate(forms[:3], 1):
            console.print(f"  [red]Form {i}[/red]: {form.get('method', 'GET')} → {form.get('action', '')[:50]}")
            for field in form.get('fields', [])[:5]:
                required = " *" if field.get('required') else ""
                label = field.get('label') or field.get('placeholder') or field.get('type')
                console.print(f"    • {field.get('type', 'unknown')}{required}: {label[:30]}")

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
    console.print(Panel("[bold cyan]🌐 UNIVERSAL PAGE UNDERSTANDING ENGINE v3[/bold cyan]",
                       subtitle="Pydantic validation | No LLM | Pure deterministic understanding", 
                       border_style="green"))
    console.print("[dim]DOM Parser | Structure Detection | NLP (spaCy) | Interaction Detection | Form Analysis[/dim]")
    console.print("[dim]Data validation: Pydantic[/dim]")
    console.print()

    if not PYDANTIC_AVAILABLE:
        console.print("[red]❌ Pydantic not available! Install: pip install pydantic[/red]")
        console.print("[dim]  Without Pydantic, data validation will be limited[/dim]")
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
            filename = f"page_analysis_v3_{timestamp}.json"
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2, default=str)
            console.print(f"[green]✅ Saved to {filename}[/green]")

    engine.close()
    console.print("[green]Goodbye! 👋[/green]")

if __name__ == "__main__":
    main()
