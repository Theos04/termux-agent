#!/usr/bin/env python3
"""
Universal Page Understanding Engine v6 - FINAL
----------------------------------------------
Enhanced with:
- Better text segmentation and cleaning
- Improved opportunity extraction with context windows
- Entity validation and filtering
- Smarter deduplication
- More accurate page type detection
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
# ENHANCED TEXT CLEANER
# ============================================================================

class TextCleanerV2:
    """Advanced text cleaning and segmentation"""

    @staticmethod
    def clean(text: str) -> str:
        """Clean text by removing noise and normalizing"""
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
            r'[→←↑↓↔↕↖↗↘↙]',  # Arrows
        ]

        for pattern in noise_patterns:
            text = re.sub(pattern, '', text)

        # Remove multiple spaces
        text = re.sub(r'\s{2,}', ' ', text)
        
        # Remove leading/trailing whitespace
        text = text.strip()

        return text
    
    @staticmethod
    def segment_text(text: str, max_length: int = 200) -> List[str]:
        """Split text into segments for better extraction"""
        if not text:
            return []
        
        # Split by sentences
        sentences = re.split(r'[.!?]+', text)
        segments = []
        current_segment = ""
        
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
                
            if len(current_segment) + len(sentence) < max_length:
                current_segment += " " + sentence if current_segment else sentence
            else:
                if current_segment:
                    segments.append(current_segment)
                current_segment = sentence
        
        if current_segment:
            segments.append(current_segment)
        
        return segments

    @staticmethod
    def extract_clean_text_from_html(html: str) -> str:
        """Extract clean text from HTML, removing script and style tags"""
        # Remove script and style tags
        html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
        
        # Remove HTML tags
        text = re.sub(r'<[^>]+>', ' ', html)
        
        # Decode HTML entities
        text = text.replace('&nbsp;', ' ')
        text = text.replace('&amp;', '&')
        text = text.replace('&lt;', '<')
        text = text.replace('&gt;', '>')
        text = text.replace('&quot;', '"')
        
        return TextCleanerV2.clean(text)

    @staticmethod
    def is_valid_opportunity(text: str) -> bool:
        """Validate if text is a legitimate opportunity"""
        if not text or len(text) < 5 or len(text) > 80:
            return False
        
        # Check for garbage text patterns
        garbage_patterns = [
            r'^[0-9]+$',  # Just numbers
            r'^[^a-zA-Z]+$',  # No letters
            r'(?:^|\s)(?:and|or|but|for|nor|on|at|to|by|in|of|with)\s*$',  # Just stopwords
            r'(?:^|\s)(?:http|https|www\.|\.com|\.org)',  # URLs
            r'(?:^|\s)(?:privacy|policy|terms|conditions|cookie)',  # Legal text
            r'(?:^|\s)(?:copyright|all rights reserved|©)',  # Copyright
            r'(?:^|\s)(?:login|sign in|sign up|register|forgot)',  # Login/register
        ]
        
        text_lower = text.lower()
        for pattern in garbage_patterns:
            if re.search(pattern, text_lower):
                return False
        
        # Check if it contains meaningful content
        meaningful_keywords = ['job', 'intern', 'hack', 'event', 'position', 'role', 
                              'opportunity', 'career', 'competition', 'challenge',
                              'workshop', 'seminar', 'conference', 'training',
                              'fellowship', 'scholarship', 'grant', 'program',
                              'course', 'certification', 'bootcamp', 'apprenticeship']
        
        has_keyword = any(keyword in text_lower for keyword in meaningful_keywords)
        
        # Check if it has good structure (capitalization, punctuation)
        has_good_structure = (
            (text[0].isupper() or any(c.isupper() for c in text)) and
            len(text.split()) >= 2
        )
        
        return has_keyword or has_good_structure

# ============================================================================
# ENHANCED ENTITY EXTRACTOR V2
# ============================================================================

class EntityExtractorV4:
    """Advanced hybrid entity extraction"""
    
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
    
    # Common locations
    LOCATIONS = {
        'cities': [
            'Mumbai', 'Delhi', 'Bangalore', 'Chennai', 'Hyderabad', 
            'Pune', 'Kolkata', 'Ahmedabad', 'Jaipur', 'Lucknow', 
            'Nagpur', 'Indore', 'Bhopal', 'Chandigarh', 'Noida',
            'Gurgaon', 'Faridabad', 'Ghaziabad', 'Coimbatore', 'Vizag',
            'Surat', 'Vadodara', 'Ludhiana', 'Agra', 'Varanasi',
            'Patna', 'Ranchi', 'Bhubaneswar', 'Guwahati', 'New York',
            'London', 'Singapore', 'Dubai', 'Tokyo', 'Paris',
            'Berlin', 'Sydney', 'Toronto', 'San Francisco', 'Austin',
            'Seattle', 'Boston', 'Chicago', 'Los Angeles', 'Miami'
        ],
        'countries': [
            'India', 'USA', 'UK', 'Canada', 'Australia', 'Germany',
            'France', 'Japan', 'China', 'Singapore', 'Dubai', 'UAE',
            'Europe', 'Asia', 'Africa', 'South Africa', 'Brazil',
            'Mexico', 'Italy', 'Spain', 'Netherlands', 'Sweden',
            'Norway', 'Denmark', 'Finland', 'Switzerland', 'Austria',
            'New Zealand', 'South Korea', 'Singapore', 'Malaysia'
        ]
    }
    
    # Skills dictionary - expanded
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
        'Tableau', 'Power BI', 'Excel', 'SAP', 'Oracle', 'Salesforce',
        'Linux', 'Unix', 'Shell', 'Git', 'Jenkins', 'Ansible',
        'Puppet', 'Chef', 'Nagios', 'Prometheus', 'Grafana',
        'Hadoop', 'Spark', 'Kafka', 'Flink', 'Airflow',
        'R', 'Matlab', 'Julia', 'Scala', 'Haskell'
    ]
    
    @classmethod
    def extract(cls, text: str) -> Dict[str, List[str]]:
        """Extract entities using hybrid approach"""
        if not text:
            return {}
            
        clean_text = TextCleanerV2.clean(text)
        entities = defaultdict(set)
        
        # 1. Use spaCy if available
        if SPACY_AVAILABLE and nlp:
            try:
                doc = nlp(clean_text[:100000])
                for ent in doc.ents:
                    entity_text = ent.text.strip()
                    if len(entity_text) < 3 or len(entity_text) > 100:
                        continue
                    
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
            except Exception:
                pass
        
        # 2. Extract organizations using multiple patterns
        # Pattern 1: Org + Suffix
        org_pattern = r'\b([A-Z][a-zA-Z\s&,.-]{2,30})\s+(?:' + '|'.join(cls.ORG_SUFFIXES) + r')\b'
        for match in re.finditer(org_pattern, clean_text, re.IGNORECASE):
            org = match.group(1).strip()
            if len(org) > 2:
                entities['organization'].add(org)
        
        # Pattern 2: University/Institute of X
        org_pattern2 = r'\b(?:University|Institute|College|School|Academy)\s+(?:of|for)\s+([A-Z][a-zA-Z\s&,.-]{2,30})\b'
        for match in re.finditer(org_pattern2, clean_text, re.IGNORECASE):
            org = match.group(1).strip()
            if len(org) > 2:
                entities['organization'].add(org)
        
        # Pattern 3: X University/Institute
        org_pattern3 = r'\b([A-Z][a-zA-Z\s&,.-]{2,30})\s+(?:University|Institute|College|School|Academy)\b'
        for match in re.finditer(org_pattern3, clean_text, re.IGNORECASE):
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
        
        # 4. Extract skills
        skill_pattern = r'\b(' + '|'.join(re.escape(skill) for skill in cls.SKILLS) + r')\b'
        for match in re.finditer(skill_pattern, clean_text, re.IGNORECASE):
            skill = match.group(1).strip()
            if len(skill) > 2:
                entities['skill'].add(skill)
        
        # 5. Extract dates
        date_patterns = [
            r'\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b',
            r'\b(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{4})\b',
            r'\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b',
            r'\b(\d{4})[/-](\d{1,2})[/-](\d{1,2})\b'
        ]
        
        for pattern in date_patterns:
            for match in re.finditer(pattern, clean_text):
                date_text = match.group(0).strip()
                if len(date_text) > 4:
                    entities['date'].add(date_text)
        
        # 6. Extract deadlines
        deadline_pattern = r'(?:deadline|last date|apply by|submit by|due|ends? on?)\s*(?:is\s*)?([A-Za-z]+\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4})'
        for match in re.finditer(deadline_pattern, clean_text, re.IGNORECASE):
            deadline = match.group(1).strip()
            if len(deadline) > 4:
                entities['deadline'].add(deadline)
        
        # 7. Extract prize amounts
        prize_patterns = [
            r'[\$₹€£](\d{1,3}(?:,\d{3})*(?:\.\d{2})?)\s*(?:USD|INR|EUR|GBP)?',
            r'(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)\s*(?:USD|INR|EUR|GBP|dollars|rupees|euros)',
            r'(?:prize|reward|cash|scholarship|grant|stipend)\s*(?:pool|amount|worth|value)?\s*(?:of\s*)?[\$₹€£]?(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)',
        ]
        
        for pattern in prize_patterns:
            for match in re.finditer(pattern, clean_text, re.IGNORECASE):
                amount = match.group(0).strip()
                if len(amount) > 2:
                    entities['prize'].add(amount)
        
        # 8. Extract emails
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        for match in re.finditer(email_pattern, clean_text):
            email = match.group(0).strip()
            entities['email'].add(email)
        
        # 9. Extract phone numbers
        phone_pattern = r'\+?\d{1,3}[-.\s]?\(?\d{1,4}\)?[-.\s]?\d{1,4}[-.\s]?\d{1,9}'
        for match in re.finditer(phone_pattern, clean_text):
            phone = match.group(0).strip()
            if len(phone) > 5 and not any(c.isalpha() for c in phone):
                entities['phone'].add(phone)
        
        # Filter and convert to sorted lists
        result = {}
        for key, value_set in entities.items():
            filtered = [v for v in value_set if 2 < len(v) < 100]
            if key == 'phone':
                filtered = [v for v in filtered if re.match(r'^[\d+\-()\s]+$', v)]
            result[key] = sorted(filtered)[:10]
        
        return {k: v for k, v in result.items() if v}

# ============================================================================
# ENHANCED OPPORTUNITY DETECTOR V2
# ============================================================================

class OpportunityDetectorV4:
    """Enhanced opportunity detection with context windows"""

    @classmethod
    def detect(cls, text: str, html: str) -> Dict:
        """Extract opportunities using context windows"""
        if not text:
            return {}

        # Get clean text from HTML (better than body.innerText)
        clean_html_text = TextCleanerV2.extract_clean_text_from_html(html)
        
        # Combine both text sources
        combined_text = f"{text}\n{clean_html_text}"
        clean_text = TextCleanerV2.clean(combined_text)
        
        opportunities = defaultdict(set)
        
        # Segment text into contexts
        segments = TextCleanerV2.segment_text(clean_text, max_length=300)
        
        # Keywords that indicate opportunities
        opp_indicators = {
            'jobs': ['job', 'career', 'position', 'role', 'opening', 'vacancy', 'hire', 'employment'],
            'internships': ['internship', 'intern', 'trainee', 'apprentice', 'stipend'],
            'hackathons': ['hackathon', 'hack', 'challenge', 'competition', 'coding contest'],
            'events': ['event', 'conference', 'workshop', 'seminar', 'webinar', 'meetup'],
            'scholarships': ['scholarship', 'fellowship', 'grant', 'bursary', 'financial aid'],
            'courses': ['course', 'program', 'certification', 'training', 'bootcamp', 'class']
        }
        
        # Process each segment
        for segment in segments:
            # Check for opportunity indicators in this segment
            for opp_type, indicators in opp_indicators.items():
                if any(indicator in segment.lower() for indicator in indicators):
                    # Extract potential opportunity titles from this segment
                    # Pattern: Title-like phrases
                    title_patterns = [
                        r'\b([A-Z][A-Za-z0-9\s&,.-]{5,50})\s+(?:' + '|'.join(indicators) + r')\b',
                        r'\b(?:' + '|'.join(indicators) + r')\s+([A-Z][A-Za-z0-9\s&,.-]{5,50})\b',
                        r'\b([A-Z][A-Za-z0-9\s&,.-]{5,50})\b(?=.*?' + '|'.join(indicators) + r')',
                    ]
                    
                    for pattern in title_patterns:
                        matches = re.finditer(pattern, segment, re.IGNORECASE)
                        for match in matches:
                            try:
                                opportunity = match.group(1).strip()
                                if TextCleanerV2.is_valid_opportunity(opportunity):
                                    opportunities[opp_type].add(opportunity)
                            except (IndexError, AttributeError):
                                continue
        
        # Extract from HTML title/heading attributes
        html_patterns = [
            (r'title="([^"]{10,60})"', 'events'),
            (r'aria-label="([^"]{10,60})"', 'events'),
            (r'data-title="([^"]{10,60})"', 'events'),
            (r'<h[1-6][^>]*>([^<]{10,60})</h[1-6]>', 'events'),
            (r'<a[^>]*>([^<]{10,60})</a>', 'events'),
        ]
        
        for pattern, default_type in html_patterns:
            matches = re.finditer(pattern, html, re.IGNORECASE)
            for match in matches:
                try:
                    text_match = match.group(1).strip()
                    if text_match and len(text_match) > 5:
                        # Check if it sounds like an opportunity
                        if any(kw in text_match.lower() for kw in ['job', 'intern', 'hack', 'event', 'position', 'role', 'opportunity']):
                            # Determine type
                            detected_type = default_type
                            for opp_type, indicators in opp_indicators.items():
                                if any(ind in text_match.lower() for ind in indicators):
                                    detected_type = opp_type
                                    break
                            if TextCleanerV2.is_valid_opportunity(text_match):
                                opportunities[detected_type].add(text_match)
                except (IndexError, AttributeError):
                    continue
        
        # Additional: Extract from lists/bullets
        bullet_patterns = [
            r'(?:^|\n)\s*[•·●○◆◇■□▪▫]\s*([^•·●○◆◇■□▪▫\n]{10,60})',
            r'(?:^|\n)\s*[\d+]\.\s*([^\n]{10,60})',
        ]
        
        for pattern in bullet_patterns:
            matches = re.finditer(pattern, clean_text, re.IGNORECASE)
            for match in matches:
                try:
                    text_match = match.group(1).strip()
                    if text_match and len(text_match) > 5:
                        # Check if it's an opportunity
                        opp_type = None
                        for opp_type_check, indicators in opp_indicators.items():
                            if any(ind in text_match.lower() for ind in indicators):
                                opp_type = opp_type_check
                                break
                        if opp_type and TextCleanerV2.is_valid_opportunity(text_match):
                            opportunities[opp_type].add(text_match)
                except (IndexError, AttributeError):
                    continue
        
        # Convert sets to sorted lists and filter
        result = {}
        for key, value_set in opportunities.items():
            filtered = [v for v in value_set if TextCleanerV2.is_valid_opportunity(v)]
            if filtered:
                result[key] = sorted(filtered)[:8]  # Limit to 8 per type
        
        return {k: v for k, v in result.items() if v}

# ============================================================================
# ENHANCED PAGE TYPE DETECTOR V2
# ============================================================================

class PageTypeDetectorV4:
    """Enhanced page type detection with multiple signals"""

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
        'gitlab.com': 'docs',
        'bitbucket.org': 'docs',
        'notion.so': 'docs',
    }

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
            'keywords': ['register', 'event', 'conference', 'workshop', 'seminar', 'webinar', 'speaker', 'expo'],
            'weight': 0.7
        },
        'ecommerce': {
            'keywords': ['buy', 'shop', 'cart', 'checkout', 'price', 'discount', 'purchase', 'shipping'],
            'weight': 0.7
        },
        'social': {
            'keywords': ['post', 'share', 'like', 'follow', 'comment', 'tweet', 'friend', 'status'],
            'weight': 0.6
        },
        'education': {
            'keywords': ['course', 'learn', 'study', 'class', 'lecture', 'tutorial', 'curriculum', 'exam'],
            'weight': 0.7
        },
        'coding': {
            'keywords': ['problem', 'solve', 'challenge', 'algorithm', 'code', 'programming', 'debug', 'syntax'],
            'weight': 0.7
        },
        'blog': {
            'keywords': ['blog', 'post', 'article', 'author', 'published', 'writing', 'read', 'comment'],
            'weight': 0.7
        },
        'forum': {
            'keywords': ['question', 'answer', 'thread', 'discussion', 'reply', 'community', 'ask'],
            'weight': 0.7
        }
    }

    @classmethod
    def detect(cls, text: str, url: str, title: str) -> Dict:
        """Detect page type with confidence scores"""
        if not text:
            return {'page_type': 'unknown', 'confidence': 0.0, 'evidence': [], 'all_scores': {}}
            
        clean_text = TextCleanerV2.clean(text[:20000].lower())
        url_lower = url.lower()
        title_lower = title.lower()

        scores = defaultdict(float)
        evidence = []

        # Domain detection
        for domain, page_type in cls.DOMAIN_MAPPING.items():
            if domain in url_lower:
                scores[page_type] += 1.0
                evidence.append(f"domain: {domain}")
                break

        # Keyword detection with frequency
        total_matches = 0
        for page_type, config in cls.PAGE_INDICATORS.items():
            match_count = 0
            for keyword in config['keywords']:
                count = len(re.findall(r'\b' + re.escape(keyword) + r'\w*\b', clean_text))
                if count > 0:
                    match_count += count
                    total_matches += count
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
        url_patterns = {
            'jobs': ['careers', 'jobs', 'career', 'employment', 'hiring'],
            'internships': ['intern', 'internship', 'trainee'],
            'hackathons': ['hackathon', 'hack', 'challenge', 'competition'],
            'events': ['event', 'conference', 'workshop', 'seminar', 'webinar']
        }
        
        for page_type, patterns in url_patterns.items():
            for pattern in patterns:
                if pattern in url_lower:
                    scores[page_type] += 0.3
                    evidence.append(f"URL contains '{pattern}'")

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
# MAIN ENGINE V6
# ============================================================================

class UniversalPageEngineV6:
    """Production-ready page understanding engine v6"""

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
        results['page_type'] = PageTypeDetectorV4.detect(self.text, self.url, self.title)

        # Layer 4: Entities
        console.print("[dim]  Layer 4: Entity Extraction...[/dim]")
        results['entities'] = EntityExtractorV4.extract(self.text)

        # Layer 5: Opportunities
        console.print("[dim]  Layer 5: Opportunity Detection...[/dim]")
        results['opportunities'] = OpportunityDetectorV4.detect(self.text, self.html)

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
            
        clean_text = TextCleanerV2.clean(self.text)

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
                    console.print(f"    • {opp[:60]}")

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
        
        priority = ['organization', 'location', 'person', 'date', 'deadline', 'prize', 'skill', 'email', 'phone']
        
        for entity_type in priority:
            if entity_type in entities and entities[entity_type]:
                display_type = entity_type.title()
                entity_list = entities[entity_type][:4]
                
                color = {
                    'organization': 'magenta',
                    'location': 'cyan',
                    'person': 'green',
                    'date': 'yellow',
                    'deadline': 'red',
                    'prize': 'green',
                    'skill': 'blue',
                    'email': 'cyan',
                    'phone': 'yellow'
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
        "[bold cyan]🌐 UNIVERSAL PAGE UNDERSTANDING ENGINE v6[/bold cyan]",
        subtitle="Production | Hybrid NLP | 10 Layers",
        border_style="green"
    ))
    console.print("[dim]DOM | Structure | Page Type | Entities | Opportunities | Actions | Forms | Links | Keywords | Summary[/dim]")
    console.print()

    if not SPACY_AVAILABLE:
        console.print("[yellow]⚠️ spaCy not available - using regex/rule fallback[/yellow]")
        console.print("[dim]  For better results: pip install spacy && python -m spacy download en_core_web_sm[/dim]")
        console.print()

    port = int(Prompt.ask("Chrome Port", default="9241"))
    engine = UniversalPageEngineV6(port)

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
