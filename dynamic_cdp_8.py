#!/usr/bin/env python3
"""
Enhanced Chrome CDP Controller - With Session Management & Memory
Extended with Advanced DOM/Data Extraction Modules
"""

import json
import subprocess
import sys
import os
import time
import re
from pathlib import Path
from typing import Optional, Dict, List, Any, Union, Tuple
from dataclasses import dataclass, asdict, field
from datetime import datetime
from collections import defaultdict, Counter
from urllib.parse import urlparse

try:
    import requests
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests"])
    import requests

try:
    import websocket
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "websocket-client"])
    import websocket

# Optional dependencies for new modules
try:
    from lxml import html, etree
    LXML_AVAILABLE = True
except ImportError:
    LXML_AVAILABLE = False
    print("⚠️ lxml not installed. XPath and advanced HTML parsing will be limited.")
    print("   Install with: pip install lxml")

try:
    import cssselect
    CSSSELECT_AVAILABLE = True
except ImportError:
    CSSSELECT_AVAILABLE = False
    print("⚠️ cssselect not installed. CSS selector testing will be limited.")
    print("   Install with: pip install cssselect")

# ============================================================
# EXISTING DATACLASSES - PRESERVED
# ============================================================

@dataclass
class LayoutSnapshot:
    """Complete layout and style information"""
    dom_nodes: List[Dict]
    layout_tree: List[Dict]
    computed_styles: List[Dict]

@dataclass
class CommandLog:
    """Log entry for a CDP command"""
    timestamp: str
    command: str
    params: Dict = field(default_factory=dict)
    success: bool = False
    result_summary: str = ""
    duration_ms: float = 0.0

@dataclass
class SessionMetadata:
    """Track session information"""
    session_id: str
    start_time: str
    end_time: Optional[str] = None
    chrome_port: int = 0
    tab_url: str = ""
    tab_title: str = ""
    total_commands: int = 0
    snapshots_taken: List[Dict] = field(default_factory=list)
    files_generated: Dict[str, int] = field(default_factory=dict)

# ============================================================
# NEW DATACLASSES FOR EXTRACTION MODULES
# ============================================================

@dataclass
class RegexMatch:
    """A single regex match with metadata"""
    value: str
    start: int
    end: int
    groups: Dict[str, str] = field(default_factory=dict)

@dataclass
class XPathResult:
    """Result of an XPath query"""
    expression: str
    matches: List[Dict]
    count: int
    duration_ms: float

@dataclass
class CSSSelectorResult:
    """Result of a CSS selector test"""
    selector: str
    valid: bool
    match_count: int
    matches: List[Dict]
    error: Optional[str] = None
    duration_ms: float = 0.0

@dataclass
class SemanticData:
    """Semantic web data extraction result"""
    json_ld: List[Dict]
    rdfa: List[Dict]
    microdata: List[Dict]
    triples: List[Dict]
    statistics: Dict

# ============================================================
# 1. REGEX PATTERN LIBRARY
# ============================================================

class RegexPatterns:
    """Central repository of compiled regex patterns"""
    
    # Core patterns
    EMAIL = re.compile(
        r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
        re.IGNORECASE
    )
    
    URL = re.compile(
        r'https?://[^\s<>"{}|\\^`\[\]]+',
        re.IGNORECASE
    )
    
    IP_V4 = re.compile(
        r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b'
    )
    
    IP_V6 = re.compile(
        r'\b(?:[A-F0-9]{1,4}:){7}[A-F0-9]{1,4}\b|'
        r'\b(?:[A-F0-9]{1,4}:){1,7}:[A-F0-9]{1,4}\b|'
        r'\b(?:[A-F0-9]{1,4}:){1,6}:[A-F0-9]{1,4}:?[A-F0-9]{1,4}\b|'
        r'\b(?:[A-F0-9]{1,4}:){1,5}:[A-F0-9]{1,4}(?::[A-F0-9]{1,4}){1,2}\b|'
        r'\b(?:[A-F0-9]{1,4}:){1,4}:[A-F0-9]{1,4}(?::[A-F0-9]{1,4}){1,3}\b|'
        r'\b(?:[A-F0-9]{1,4}:){1,3}:[A-F0-9]{1,4}(?::[A-F0-9]{1,4}){1,4}\b|'
        r'\b(?:[A-F0-9]{1,4}:){1,2}:[A-F0-9]{1,4}(?::[A-F0-9]{1,4}){1,5}\b|'
        r'\b(?:[A-F0-9]{1,4}:){1}:[A-F0-9]{1,4}(?::[A-F0-9]{1,4}){1,6}\b',
        re.IGNORECASE
    )
    
    PHONE = re.compile(
        r'\b(?:\+?[0-9]{1,3}[-.\s]?)?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}\b'
    )
    
    UUID = re.compile(
        r'\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b',
        re.IGNORECASE
    )
    
    DATE_ISO = re.compile(
        r'\b[0-9]{4}-[0-9]{2}-[0-9]{2}\b'
    )
    
    TIME_24H = re.compile(
        r'\b[0-2][0-9]:[0-5][0-9](?::[0-5][0-9])?\b'
    )
    
    CREDIT_CARD = re.compile(
        r'\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13}|6(?:011|5[0-9]{2})[0-9]{12})\b'
    )
    
    MAC_ADDRESS = re.compile(
        r'\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b'
    )
    
    DOMAIN = re.compile(
        r'\b(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}\b'
    )
    
    HEX_COLOR = re.compile(
        r'#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})\b'
    )
    
    # Named group patterns for extraction with groups
    EMAIL_NAMED = re.compile(
        r'(?P<username>[a-zA-Z0-9._%+-]+)@(?P<domain>[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})',
        re.IGNORECASE
    )
    
    URL_NAMED = re.compile(
        r'(?P<protocol>https?)://(?P<host>[^\s/<]+)(?P<path>/[^\s]*)?',
        re.IGNORECASE
    )
    
    @classmethod
    def get_all_patterns(cls) -> Dict[str, re.Pattern]:
        """Get all compiled patterns"""
        return {
            name: getattr(cls, name)
            for name in dir(cls)
            if not name.startswith('_') and isinstance(getattr(cls, name), re.Pattern)
        }
    
    @classmethod
    def get_pattern_names(cls) -> List[str]:
        """Get all pattern names"""
        return [
            name for name in dir(cls)
            if not name.startswith('_') and isinstance(getattr(cls, name), re.Pattern)
        ]


class RegexExtractor:
    """Extract regex matches from text with metadata"""
    
    @staticmethod
    def extract(pattern_name: str, text: str, unique: bool = True) -> List[str]:
        """Extract all matches for a named pattern"""
        pattern = getattr(RegexPatterns, pattern_name, None)
        if not pattern:
            raise ValueError(f"Unknown pattern: {pattern_name}")
        
        matches = pattern.findall(text)
        if unique:
            # Preserve order while removing duplicates
            seen = set()
            unique_matches = []
            for match in matches:
                if match not in seen:
                    seen.add(match)
                    unique_matches.append(match)
            return unique_matches
        return matches
    
    @staticmethod
    def extract_with_metadata(pattern_name: str, text: str) -> List[RegexMatch]:
        """Extract matches with position and group metadata"""
        pattern = getattr(RegexPatterns, pattern_name, None)
        if not pattern:
            raise ValueError(f"Unknown pattern: {pattern_name}")
        
        results = []
        for match in pattern.finditer(text):
            groups = {}
            if match.groupdict():
                groups = match.groupdict()
            elif match.groups():
                # For unnamed groups, use numeric indices
                for i, group in enumerate(match.groups(), 1):
                    if group is not None:
                        groups[str(i)] = group
            
            results.append(RegexMatch(
                value=match.group(0),
                start=match.start(),
                end=match.end(),
                groups=groups
            ))
        return results
    
    @staticmethod
    def extract_named(pattern_name: str, text: str) -> List[Dict[str, str]]:
        """Extract matches with named groups as dictionaries"""
        pattern = getattr(RegexPatterns, pattern_name, None)
        if not pattern:
            raise ValueError(f"Unknown pattern: {pattern_name}")
        
        results = []
        for match in pattern.finditer(text):
            if match.groupdict():
                results.append(match.groupdict())
            else:
                # If no named groups, return the match itself
                results.append({'match': match.group(0)})
        return results
    
    @staticmethod
    def validate(pattern_name: str, value: str) -> bool:
        """Validate a string against a pattern (full match required)"""
        pattern = getattr(RegexPatterns, pattern_name, None)
        if not pattern:
            raise ValueError(f"Unknown pattern: {pattern_name}")
        
        return bool(pattern.fullmatch(value.strip()))
    
    @staticmethod
    def search(pattern_name: str, text: str) -> bool:
        """Check if pattern exists in text"""
        pattern = getattr(RegexPatterns, pattern_name, None)
        if not pattern:
            raise ValueError(f"Unknown pattern: {pattern_name}")
        
        return bool(pattern.search(text))


# Convenience functions
def is_match(pattern_name: str, value: str) -> bool:
    """Validate a string against a pattern"""
    return RegexExtractor.validate(pattern_name, value)


def extract(pattern_name: str, text: str, unique: bool = True) -> List[str]:
    """Extract matches for a pattern"""
    return RegexExtractor.extract(pattern_name, text, unique)


def extract_with_metadata(pattern_name: str, text: str) -> List[RegexMatch]:
    """Extract matches with metadata"""
    return RegexExtractor.extract_with_metadata(pattern_name, text)


def extract_named(pattern_name: str, text: str) -> List[Dict[str, str]]:
    """Extract matches with named groups"""
    return RegexExtractor.extract_named(pattern_name, text)


# Emulate the requested API structure
class extract_api:
    emails = lambda text: extract('EMAIL', text)
    urls = lambda text: extract('URL', text)
    ipv4 = lambda text: extract('IP_V4', text)
    ipv6 = lambda text: extract('IP_V6', text)
    phones = lambda text: extract('PHONE', text)
    uuids = lambda text: extract('UUID', text)
    dates_iso = lambda text: extract('DATE_ISO', text)
    times_24h = lambda text: extract('TIME_24H', text)
    credit_cards = lambda text: extract('CREDIT_CARD', text)
    mac_addresses = lambda text: extract('MAC_ADDRESS', text)
    domains = lambda text: extract('DOMAIN', text)
    hex_colors = lambda text: extract('HEX_COLOR', text)


patterns = RegexPatterns
extract = extract_api
validate = is_match

# ============================================================
# 2. XPATH EXPRESSION ENGINE
# ============================================================

class DOMQuery:
    """XPath query engine for DOM exploration"""
    
    def __init__(self, xpath: str, namespace: Optional[Dict[str, str]] = None):
        """
        Initialize an XPath query
        
        Args:
            xpath: XPath expression string
            namespace: Optional namespace mapping for namespace-aware queries
        """
        self.xpath = xpath
        self.namespace = namespace or {}
        self._parser = None
        self._tree = None
    
    def evaluate(self, context_node: Any = None, html_source: str = None) -> XPathResult:
        """
        Evaluate the XPath query against a context
        
        Args:
            context_node: Existing DOM node to query against (lxml element)
            html_source: HTML string to parse if no context provided
        
        Returns:
            XPathResult with matches and metadata
        """
        start_time = time.time()
        
        if not LXML_AVAILABLE:
            return XPathResult(
                expression=self.xpath,
                matches=[],
                count=0,
                duration_ms=(time.time() - start_time) * 1000
            )
        
        try:
            # Get the tree to query
            tree = None
            if context_node is not None:
                # If context is an lxml element, use it directly
                if hasattr(context_node, 'xpath'):
                    tree = context_node
                else:
                    # Try to parse it if it's a dict representation
                    tree = self._dict_to_lxml(context_node)
            elif html_source is not None:
                tree = html.fromstring(html_source)
            else:
                # No context provided
                return XPathResult(
                    expression=self.xpath,
                    matches=[],
                    count=0,
                    duration_ms=(time.time() - start_time) * 1000,
                    error="No context provided for XPath query"
                )
            
            if tree is None:
                return XPathResult(
                    expression=self.xpath,
                    matches=[],
                    count=0,
                    duration_ms=(time.time() - start_time) * 1000,
                    error="Failed to parse context"
                )
            
            # Execute the query
            if self.namespace:
                results = tree.xpath(self.xpath, namespaces=self.namespace)
            else:
                results = tree.xpath(self.xpath)
            
            # Convert results to structured format
            matches = self._process_results(results)
            
            return XPathResult(
                expression=self.xpath,
                matches=matches,
                count=len(matches),
                duration_ms=(time.time() - start_time) * 1000
            )
            
        except Exception as e:
            return XPathResult(
                expression=self.xpath,
                matches=[],
                count=0,
                duration_ms=(time.time() - start_time) * 1000,
                error=str(e)
            )
    
    def _dict_to_lxml(self, node_dict: Dict) -> Any:
        """Convert dictionary representation to lxml element"""
        if not LXML_AVAILABLE:
            return None
        
        # Simple conversion for common structures
        # This handles the basic DOM tree from CDP
        try:
            # Create a root element
            tag = node_dict.get('nodeName', 'div').lower()
            root = html.Element(tag)
            
            # Add attributes
            attributes = node_dict.get('attributes', {})
            if isinstance(attributes, list):
                # Handle list format: ['key1', 'value1', 'key2', 'value2']
                for i in range(0, len(attributes), 2):
                    if i + 1 < len(attributes):
                        root.set(attributes[i], attributes[i+1])
            elif isinstance(attributes, dict):
                for key, value in attributes.items():
                    root.set(key, str(value))
            
            # Add children
            for child in node_dict.get('children', []):
                child_elem = self._dict_to_lxml(child)
                if child_elem is not None:
                    root.append(child_elem)
            
            return root
        except Exception:
            return None
    
    def _process_results(self, results: List) -> List[Dict]:
        """Process XPath results into structured format"""
        matches = []
        
        for result in results:
            if isinstance(result, etree._Element):
                # Element node
                match = {
                    'type': 'element',
                    'tag': result.tag,
                    'text': result.text or '',
                    'attributes': dict(result.attrib),
                    'html': html.tostring(result, encoding='unicode') if LXML_AVAILABLE else '',
                }
                matches.append(match)
            elif isinstance(result, str):
                # Text node
                matches.append({
                    'type': 'text',
                    'value': result
                })
            elif isinstance(result, (int, float, bool)):
                # Number or boolean result
                matches.append({
                    'type': 'value',
                    'value': result
                })
            else:
                # Other types
                matches.append({
                    'type': 'unknown',
                    'value': str(result)
                })
        
        return matches
    
    @staticmethod
    def from_element(element: Any) -> 'DOMQuery':
        """Create a query from an existing element"""
        # This would be used to query relative to a specific element
        # Implementation depends on the element representation
        return DOMQuery('.')
    
    @staticmethod
    def find_all_by_xpath(html_source: str, xpath: str, 
                         namespace: Optional[Dict[str, str]] = None) -> List[Dict]:
        """Convenience method to find all elements matching XPath"""
        query = DOMQuery(xpath, namespace)
        result = query.evaluate(html_source=html_source)
        return result.matches


# ============================================================
# 3. CSS SELECTOR TESTING ENGINE
# ============================================================

class CSSSelectorTester:
    """CSS selector testing and diagnostic engine"""
    
    def __init__(self, html: str = None):
        self.html = html
        self._tree = None
        if html and LXML_AVAILABLE:
            try:
                self._tree = html.fromstring(html)
            except Exception:
                self._tree = None
    
    def test(self, html: str = None, selector: str = None,
            attributes: List[str] = None) -> CSSSelectorResult:
        """
        Test a CSS selector against HTML
        
        Args:
            html: HTML string to test against
            selector: CSS selector string
            attributes: List of attributes to extract from matches
        
        Returns:
            CSSSelectorResult with match data
        """
        start_time = time.time()
        
        if selector is None:
            return CSSSelectorResult(
                selector='',
                valid=False,
                match_count=0,
                matches=[],
                error="No selector provided",
                duration_ms=(time.time() - start_time) * 1000
            )
        
        # Use provided HTML or stored HTML
        test_html = html or self.html
        if not test_html:
            return CSSSelectorResult(
                selector=selector,
                valid=False,
                match_count=0,
                matches=[],
                error="No HTML provided for testing",
                duration_ms=(time.time() - start_time) * 1000
            )
        
        if not LXML_AVAILABLE:
            return CSSSelectorResult(
                selector=selector,
                valid=False,
                match_count=0,
                matches=[],
                error="lxml not available for CSS selector testing",
                duration_ms=(time.time() - start_time) * 1000
            )
        
        try:
            # Parse HTML
            tree = html.fromstring(test_html)
            
            # Try to use cssselect if available, otherwise use lxml's built-in
            if CSSSELECT_AVAILABLE:
                try:
                    # Validate selector
                    cssselect.parse(selector)
                except Exception as e:
                    return CSSSelectorResult(
                        selector=selector,
                        valid=False,
                        match_count=0,
                        matches=[],
                        error=f"Invalid CSS selector: {str(e)}",
                        duration_ms=(time.time() - start_time) * 1000
                    )
            
            # Find matches
            try:
                # lxml's CSS selector support
                matches = tree.cssselect(selector)
            except Exception as e:
                return CSSSelectorResult(
                    selector=selector,
                    valid=False,
                    match_count=0,
                    matches=[],
                    error=f"CSS selector error: {str(e)}",
                    duration_ms=(time.time() - start_time) * 1000
                )
            
            # Extract data from matches
            result_matches = []
            attributes = attributes or ['id', 'class', 'href', 'src', 'data-*']
            
            for element in matches:
                match_data = {
                    'tag': element.tag,
                    'text': element.text_content().strip()[:200] if hasattr(element, 'text_content') else '',
                    'id': element.get('id', ''),
                    'class': element.get('class', ''),
                    'attributes': dict(element.attrib),
                    'outer_html': html.tostring(element, encoding='unicode') if LXML_AVAILABLE else '',
                    'inner_html': html.tostring(element, encoding='unicode') if LXML_AVAILABLE else '',
                }
                
                # Extract requested attributes
                for attr in attributes:
                    if attr == 'data-*':
                        # Extract all data attributes
                        data_attrs = {}
                        for key, value in element.attrib.items():
                            if key.startswith('data-'):
                                data_attrs[key] = value
                        match_data['data_attributes'] = data_attrs
                    else:
                        if attr in element.attrib:
                            match_data[attr] = element.attrib[attr]
                
                result_matches.append(match_data)
            
            return CSSSelectorResult(
                selector=selector,
                valid=True,
                match_count=len(result_matches),
                matches=result_matches,
                duration_ms=(time.time() - start_time) * 1000
            )
            
        except Exception as e:
            return CSSSelectorResult(
                selector=selector,
                valid=False,
                match_count=0,
                matches=[],
                error=str(e),
                duration_ms=(time.time() - start_time) * 1000
            )
    
    def test_from_page(self, html_source: str, selector: str,
                       attributes: List[str] = None) -> CSSSelectorResult:
        """Test a selector against HTML from a page"""
        return self.test(html_source, selector, attributes)
    
    @staticmethod
    def validate_selector(selector: str) -> bool:
        """Validate a CSS selector syntax"""
        if not CSSSELECT_AVAILABLE:
            # Basic validation without cssselect
            try:
                # Simple check: try to parse with lxml's CSS selector
                from lxml.cssselect import CSSSelector
                CSSSelector(selector)
                return True
            except Exception:
                return False
        
        try:
            cssselect.parse(selector)
            return True
        except Exception:
            return False
    
    @staticmethod
    def get_selector_stats(html: str, selector: str) -> Dict:
        """Get statistics about a selector match"""
        tester = CSSSelectorTester(html)
        result = tester.test(selector=selector)
        
        if not result.valid:
            return {
                'valid': False,
                'error': result.error
            }
        
        # Calculate additional stats
        stats = {
            'valid': True,
            'match_count': result.match_count,
            'tag_distribution': Counter(m['tag'] for m in result.matches),
            'id_present': sum(1 for m in result.matches if m.get('id')),
            'class_present': sum(1 for m in result.matches if m.get('class')),
            'unique_attributes': set(),
        }
        
        for match in result.matches:
            stats['unique_attributes'].update(match.get('attributes', {}).keys())
        
        stats['unique_attributes'] = list(stats['unique_attributes'])
        
        return stats


# ============================================================
# 4. JSON-LD / RDFa EXTRACTION
# ============================================================

class SemanticExtractor:
    """Extract JSON-LD, RDFa, Microdata, and semantic triples"""
    
    def __init__(self):
        self.json_ld_blocks = []
        self.rdfa_triples = []
        self.microdata_items = []
    
    def extract_from_html(self, html_source: str) -> SemanticData:
        """Extract all semantic data from HTML"""
        start_time = time.time()
        
        result = SemanticData(
            json_ld=[],
            rdfa=[],
            microdata=[],
            triples=[],
            statistics={
                'json_ld_blocks': 0,
                'rdfa_triples': 0,
                'microdata_items': 0,
                'total_triples': 0,
                'extraction_time_ms': 0
            }
        )
        
        if not html_source:
            return result
        
        # 1. Extract JSON-LD
        json_ld_data = self._extract_json_ld(html_source)
        result.json_ld = json_ld_data
        result.statistics['json_ld_blocks'] = len(json_ld_data)
        
        # 2. Extract RDFa
        rdfa_data = self._extract_rdfa(html_source)
        result.rdfa = rdfa_data
        result.statistics['rdfa_triples'] = len(rdfa_data)
        
        # 3. Extract Microdata (basic)
        microdata_data = self._extract_microdata(html_source)
        result.microdata = microdata_data
        result.statistics['microdata_items'] = len(microdata_data)
        
        # 4. Generate triples from all sources
        triples = self._generate_triples(result)
        result.triples = triples
        result.statistics['total_triples'] = len(triples)
        result.statistics['extraction_time_ms'] = (time.time() - start_time) * 1000
        
        return result
    
    def _extract_json_ld(self, html_source: str) -> List[Dict]:
        """Extract JSON-LD from HTML"""
        json_ld_blocks = []
        
        # Find all script tags with type application/ld+json
        # Use regex to find them (simple but effective)
        script_pattern = r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>'
        
        for match in re.finditer(script_pattern, html_source, re.DOTALL | re.IGNORECASE):
            try:
                script_content = match.group(1).strip()
                if not script_content:
                    continue
                
                data = json.loads(script_content)
                
                # Handle both single objects and arrays
                if isinstance(data, list):
                    json_ld_blocks.extend(data)
                else:
                    json_ld_blocks.append(data)
            except json.JSONDecodeError:
                # Malformed JSON-LD, skip
                continue
            except Exception:
                # Other errors, skip
                continue
        
        return json_ld_blocks
    
    def _extract_rdfa(self, html_source: str) -> List[Dict]:
        """Extract RDFa triples from HTML"""
        rdfa_triples = []
        
        if not LXML_AVAILABLE:
            return rdfa_triples
        
        try:
            tree = html.fromstring(html_source)
            
            # Find all elements with RDFa attributes
            # RDFa attributes: about, property, typeof, resource, vocab, prefix, content, rel, rev, datatype
            rdfa_attrs = ['about', 'property', 'typeof', 'resource', 
                         'vocab', 'prefix', 'content', 'rel', 'rev', 'datatype']
            
            # XPath to find elements with any RDFa attribute
            xpath_expr = '//*[' + ' or '.join(f'@{attr}' for attr in rdfa_attrs) + ']'
            elements = tree.xpath(xpath_expr)
            
            for element in elements:
                # Extract RDFa attributes
                attrs = {}
                for attr in rdfa_attrs:
                    if attr in element.attrib:
                        attrs[attr] = element.attrib[attr]
                
                if attrs:
                    # Build a triple
                    triple = {
                        'subject': attrs.get('about', ''),
                        'predicate': attrs.get('property', attrs.get('rel', '')),
                        'object': attrs.get('content', element.text_content().strip() if element.text_content() else ''),
                        'type': attrs.get('typeof', ''),
                        'resource': attrs.get('resource', ''),
                        'vocab': attrs.get('vocab', ''),
                        'prefix': attrs.get('prefix', ''),
                        'datatype': attrs.get('datatype', ''),
                    }
                    
                    # Clean up empty values
                    triple = {k: v for k, v in triple.items() if v}
                    
                    if triple.get('subject') and triple.get('predicate') and triple.get('object'):
                        rdfa_triples.append(triple)
                    
                    # Also add as a simpler triple
                    if triple.get('property') or triple.get('rel'):
                        simple_triple = {
                            'subject': triple.get('subject', ''),
                            'predicate': triple.get('property', triple.get('rel', '')),
                            'object': triple.get('object', ''),
                            'type': triple.get('type', '')
                        }
                        # Store both formats
                        triple['_simple_triple'] = simple_triple
            
        except Exception as e:
            # Silently fail for RDFa extraction
            pass
        
        return rdfa_triples
    
    def _extract_microdata(self, html_source: str) -> List[Dict]:
        """Extract HTML5 Microdata (basic implementation)"""
        microdata_items = []
        
        if not LXML_AVAILABLE:
            return microdata_items
        
        try:
            tree = html.fromstring(html_source)
            
            # Find elements with itemscope attribute
            items = tree.xpath('//*[@itemscope]')
            
            for item in items:
                item_data = {
                    'itemtype': item.get('itemtype', ''),
                    'itemid': item.get('itemid', ''),
                    'properties': {}
                }
                
                # Find properties within the item
                props = item.xpath('.//*[@itemprop]')
                for prop in props:
                    prop_name = prop.get('itemprop', '')
                    prop_value = prop.get('content', prop.text_content().strip())
                    if prop_name and prop_value:
                        if prop_name not in item_data['properties']:
                            item_data['properties'][prop_name] = []
                        item_data['properties'][prop_name].append(prop_value)
                
                # Clean up empty properties
                if item_data['properties']:
                    microdata_items.append(item_data)
            
        except Exception:
            pass
        
        return microdata_items
    
    def _generate_triples(self, semantic_data: SemanticData) -> List[Dict]:
        """Generate RDF-style triples from all semantic data"""
        triples = []
        
        # Generate triples from JSON-LD
        for json_ld in semantic_data.json_ld:
            triples.extend(self._json_ld_to_triples(json_ld))
        
        # Convert RDFa to triples
        for rdfa in semantic_data.rdfa:
            if '_simple_triple' in rdfa:
                triples.append(rdfa['_simple_triple'])
            else:
                # Try to create a triple from available data
                triple = {
                    'subject': rdfa.get('subject', ''),
                    'predicate': rdfa.get('property', rdfa.get('rel', '')),
                    'object': rdfa.get('object', '')
                }
                if triple['subject'] and triple['predicate'] and triple['object']:
                    triples.append(triple)
        
        return triples
    
    def _json_ld_to_triples(self, json_ld: Dict, base_subject: str = None) -> List[Dict]:
        """Convert JSON-LD to RDF triples (simplified)"""
        triples = []
        
        if not isinstance(json_ld, dict):
            return triples
        
        # Extract @id for subject
        subject = json_ld.get('@id', base_subject or '_:b0')
        subject = subject or '_:b0'
        
        # Handle @type
        if '@type' in json_ld:
            triples.append({
                'subject': subject,
                'predicate': 'rdf:type',
                'object': json_ld['@type'] if isinstance(json_ld['@type'], str) else json_ld['@type'][0]
            })
        
        # Process all other properties
        for key, value in json_ld.items():
            if key.startswith('@'):
                continue
            
            # Handle nested objects and arrays
            if isinstance(value, dict):
                # Create a blank node for nested object
                nested_subject = f'_:b{len(triples)}'
                triples.append({
                    'subject': subject,
                    'predicate': key,
                    'object': nested_subject
                })
                triples.extend(self._json_ld_to_triples(value, nested_subject))
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        nested_subject = f'_:b{len(triples)}'
                        triples.append({
                            'subject': subject,
                            'predicate': key,
                            'object': nested_subject
                        })
                        triples.extend(self._json_ld_to_triples(item, nested_subject))
                    else:
                        triples.append({
                            'subject': subject,
                            'predicate': key,
                            'object': str(item)
                        })
            else:
                triples.append({
                    'subject': subject,
                    'predicate': key,
                    'object': str(value)
                })
        
        return triples


# ============================================================
# EXISTING SESSION MANAGER - EXTENDED
# ============================================================

class SessionManager:
    """Manages session data, logging, and file organization - EXTENDED with new capabilities"""

    def __init__(self, base_dir: str = "."):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.session_dir = self.base_dir / f"session_{self.session_id}"

        # Create session directory structure - EXTENDED with new directories
        self.dirs = {
            'dom_trees': self.session_dir / 'dom_trees',
            'snapshots': self.session_dir / 'snapshots',
            'accessibility': self.session_dir / 'accessibility',
            'computed_styles': self.session_dir / 'computed_styles',
            'scripts': self.session_dir / 'scripts',
            'interactions': self.session_dir / 'interactions',
            'logs': self.session_dir / 'logs',
            'exports': self.session_dir / 'exports',
            'memory': self.session_dir / 'memory',  # For state persistence
            # NEW DIRECTORY STRUCTURE
            'regex': self.session_dir / 'regex',
            'xpath': self.session_dir / 'xpath',
            'selectors': self.session_dir / 'selectors',
            'semantic': self.session_dir / 'semantic',
        }

        for dir_path in self.dirs.values():
            dir_path.mkdir(parents=True, exist_ok=True)

        # Initialize metadata - PRESERVED
        self.metadata = SessionMetadata(
            session_id=self.session_id,
            start_time=datetime.now().isoformat(),
        )

        # Command history - PRESERVED
        self.command_history: List[CommandLog] = []

        # Memory/state tracking - EXTENDED
        self.state = {
            'last_dom_tree': None,
            'last_snapshot': None,
            'last_accessibility': None,
            'last_styles': None,
            'last_interaction': None,
            'interaction_count': 0,
            'errors': [],
            # NEW STATE KEYS
            'last_regex_extraction': None,
            'last_xpath_query': None,
            'last_css_test': None,
            'last_semantic_extraction': None,
            'last_json_ld': None,
            'last_rdfa': None,
        }

        # Initialize session log
        self._log_event('session_start', {
            'session_id': self.session_id,
            'base_dir': str(self.base_dir)
        })

        # Save initial state
        self._save_state()

    # ============================================================
    # EXISTING METHODS - PRESERVED COMPLETELY
    # ============================================================

    def _log_event(self, event_type: str, data: Dict = None):
        """Log an event to the session log - PRESERVED"""
        log_file = self.dirs['logs'] / "session.jsonl"
        entry = {
            'timestamp': datetime.now().isoformat(),
            'event': event_type,
            'data': data or {}
        }
        with open(log_file, 'a') as f:
            f.write(json.dumps(entry) + '\n')

    def log_command(self, command: str, params: Dict = None,
                    success: bool = False, result_summary: str = "",
                    duration_ms: float = 0.0):
        """Log a command execution - PRESERVED"""
        cmd_log = CommandLog(
            timestamp=datetime.now().isoformat(),
            command=command,
            params=params or {},
            success=success,
            result_summary=result_summary,
            duration_ms=duration_ms
        )

        self.command_history.append(cmd_log)
        self.metadata.total_commands += 1

        # Log to file
        self._log_event('command', asdict(cmd_log))

        # Save state after each command
        self._save_state()

    def save_dom_tree(self, dom_data: Dict, context: Dict = None):
        """Save DOM tree with full metadata - PRESERVED"""
        timestamp = datetime.now().strftime("%H%M%S_%f")
        filename = self.dirs['dom_trees'] / f"dom_{timestamp}.json"

        metadata = {
            'session_id': self.session_id,
            'timestamp': datetime.now().isoformat(),
            'tab_url': self.metadata.tab_url,
            'tab_title': self.metadata.tab_title,
            'context': context or {},
            'node_count': self._count_nodes(dom_data) if dom_data else 0,
            'command_index': len(self.command_history)
        }

        payload = {
            'metadata': metadata,
            'data': dom_data
        }

        with open(filename, 'w') as f:
            json.dump(payload, f, indent=2)

        # Update state
        self.state['last_dom_tree'] = {
            'file': str(filename),
            'metadata': metadata
        }

        # Update session index
        self._update_index('dom_trees', filename.name, metadata)
        self._increment_file_count('dom_trees')

        print(f"💾 DOM tree saved: {filename.name}")
        return filename

    def save_snapshot(self, snapshot: LayoutSnapshot, context: Dict = None):
        """Save DOM snapshot with full metadata - PRESERVED"""
        timestamp = datetime.now().strftime("%H%M%S_%f")
        filename = self.dirs['snapshots'] / f"snapshot_{timestamp}.json"

        metadata = {
            'session_id': self.session_id,
            'timestamp': datetime.now().isoformat(),
            'tab_url': self.metadata.tab_url,
            'tab_title': self.metadata.tab_title,
            'context': context or {},
            'dom_node_count': len(snapshot.dom_nodes),
            'layout_tree_count': len(snapshot.layout_tree),
            'computed_styles_count': len(snapshot.computed_styles),
            'command_index': len(self.command_history)
        }

        payload = {
            'metadata': metadata,
            'data': {
                'dom_nodes': snapshot.dom_nodes,
                'layout_tree': snapshot.layout_tree,
                'computed_styles': snapshot.computed_styles
            }
        }

        with open(filename, 'w') as f:
            json.dump(payload, f, indent=2)

        self.state['last_snapshot'] = {
            'file': str(filename),
            'metadata': metadata
        }

        self._update_index('snapshots', filename.name, metadata)
        self._increment_file_count('snapshots')

        print(f"💾 Snapshot saved: {filename.name}")
        return filename

    def save_accessibility_tree(self, ax_data: Dict, context: Dict = None):
        """Save accessibility tree with full metadata - PRESERVED"""
        timestamp = datetime.now().strftime("%H%M%S_%f")
        filename = self.dirs['accessibility'] / f"a11y_{timestamp}.json"

        metadata = {
            'session_id': self.session_id,
            'timestamp': datetime.now().isoformat(),
            'tab_url': self.metadata.tab_url,
            'tab_title': self.metadata.tab_title,
            'context': context or {},
            'node_count': len(ax_data.get('nodes', [])),
            'command_index': len(self.command_history)
        }

        payload = {
            'metadata': metadata,
            'data': ax_data
        }

        with open(filename, 'w') as f:
            json.dump(payload, f, indent=2)

        self.state['last_accessibility'] = {
            'file': str(filename),
            'metadata': metadata
        }

        self._update_index('accessibility', filename.name, metadata)
        self._increment_file_count('accessibility')

        print(f"💾 Accessibility tree saved: {filename.name}")
        return filename

    def save_computed_styles(self, styles: List[Dict], context: Dict = None):
        """Save computed styles with full metadata - PRESERVED"""
        timestamp = datetime.now().strftime("%H%M%S_%f")
        filename = self.dirs['computed_styles'] / f"styles_{timestamp}.json"

        metadata = {
            'session_id': self.session_id,
            'timestamp': datetime.now().isoformat(),
            'tab_url': self.metadata.tab_url,
            'tab_title': self.metadata.tab_title,
            'context': context or {},
            'style_count': len(styles),
            'command_index': len(self.command_history)
        }

        payload = {
            'metadata': metadata,
            'data': styles
        }

        with open(filename, 'w') as f:
            json.dump(payload, f, indent=2)

        self.state['last_styles'] = {
            'file': str(filename),
            'metadata': metadata
        }

        self._update_index('computed_styles', filename.name, metadata)
        self._increment_file_count('computed_styles')

        print(f"💾 Computed styles saved: {filename.name}")
        return filename

    def save_interaction(self, interaction_data: Dict, context: Dict = None):
        """Save interaction results - PRESERVED"""
        timestamp = datetime.now().strftime("%H%M%S_%f")
        filename = self.dirs['interactions'] / f"interaction_{timestamp}.json"

        metadata = {
            'session_id': self.session_id,
            'timestamp': datetime.now().isoformat(),
            'tab_url': self.metadata.tab_url,
            'tab_title': self.metadata.tab_title,
            'context': context or {},
            'interaction_number': self.state['interaction_count'] + 1,
            'command_index': len(self.command_history)
        }

        payload = {
            'metadata': metadata,
            'data': interaction_data
        }

        with open(filename, 'w') as f:
            json.dump(payload, f, indent=2)

        self.state['last_interaction'] = {
            'file': str(filename),
            'metadata': metadata
        }
        self.state['interaction_count'] += 1

        self._update_index('interactions', filename.name, metadata)
        self._increment_file_count('interactions')

        print(f"💾 Interaction saved: {filename.name}")
        return filename

    def save_script(self, script_content: str, script_type: str = "javascript", context: Dict = None):
        """Save generated scripts - PRESERVED"""
        timestamp = datetime.now().strftime("%H%M%S_%f")
        ext = '.js' if script_type == 'javascript' else '.txt'
        filename = self.dirs['scripts'] / f"script_{timestamp}{ext}"

        metadata = {
            'session_id': self.session_id,
            'timestamp': datetime.now().isoformat(),
            'tab_url': self.metadata.tab_url,
            'tab_title': self.metadata.tab_title,
            'context': context or {},
            'script_type': script_type,
            'command_index': len(self.command_history)
        }

        # Save script with metadata header
        with open(filename, 'w') as f:
            f.write(f"// Session: {self.session_id}\n")
            f.write(f"// Timestamp: {metadata['timestamp']}\n")
            f.write(f"// Tab: {self.metadata.tab_url}\n")
            f.write(f"// Type: {script_type}\n")
            f.write("// " + "="*50 + "\n\n")
            f.write(script_content)

        self._update_index('scripts', filename.name, metadata)
        self._increment_file_count('scripts')

        print(f"💾 Script saved: {filename.name}")
        return filename

    def log_error(self, error_msg: str, context: Dict = None):
        """Log an error - PRESERVED"""
        error_entry = {
            'timestamp': datetime.now().isoformat(),
            'error': error_msg,
            'context': context or {}
        }
        self.state['errors'].append(error_entry)
        self._log_event('error', error_entry)

    # ============================================================
    # NEW SAVE METHODS FOR EXTRACTION MODULES
    # ============================================================

    def save_regex_results(self, results: Dict, context: Dict = None):
        """Save regex extraction results"""
        timestamp = datetime.now().strftime("%H%M%S_%f")
        filename = self.dirs['regex'] / f"regex_{timestamp}.json"

        metadata = {
            'session_id': self.session_id,
            'timestamp': datetime.now().isoformat(),
            'tab_url': self.metadata.tab_url,
            'tab_title': self.metadata.tab_title,
            'context': context or {},
            'pattern_count': len(results.get('patterns', {})),
            'total_matches': sum(len(matches) for matches in results.get('patterns', {}).values()),
            'command_index': len(self.command_history)
        }

        payload = {
            'metadata': metadata,
            'data': results
        }

        with open(filename, 'w') as f:
            json.dump(payload, f, indent=2)

        self.state['last_regex_extraction'] = {
            'file': str(filename),
            'metadata': metadata
        }

        self._update_index('regex', filename.name, metadata)
        self._increment_file_count('regex')

        print(f"💾 Regex results saved: {filename.name}")
        return filename

    def save_xpath_results(self, results: Dict, context: Dict = None):
        """Save XPath query results"""
        timestamp = datetime.now().strftime("%H%M%S_%f")
        filename = self.dirs['xpath'] / f"xpath_{timestamp}.json"

        metadata = {
            'session_id': self.session_id,
            'timestamp': datetime.now().isoformat(),
            'tab_url': self.metadata.tab_url,
            'tab_title': self.metadata.tab_title,
            'context': context or {},
            'expression': context.get('xpath', '') if context else '',
            'match_count': len(results.get('matches', [])),
            'command_index': len(self.command_history)
        }

        payload = {
            'metadata': metadata,
            'data': results
        }

        with open(filename, 'w') as f:
            json.dump(payload, f, indent=2)

        self.state['last_xpath_query'] = {
            'file': str(filename),
            'metadata': metadata
        }

        self._update_index('xpath', filename.name, metadata)
        self._increment_file_count('xpath')

        print(f"💾 XPath results saved: {filename.name}")
        return filename

    def save_css_results(self, results: Dict, context: Dict = None):
        """Save CSS selector test results"""
        timestamp = datetime.now().strftime("%H%M%S_%f")
        filename = self.dirs['selectors'] / f"css_{timestamp}.json"

        metadata = {
            'session_id': self.session_id,
            'timestamp': datetime.now().isoformat(),
            'tab_url': self.metadata.tab_url,
            'tab_title': self.metadata.tab_title,
            'context': context or {},
            'selector': context.get('selector', '') if context else '',
            'match_count': results.get('match_count', 0),
            'valid': results.get('valid', False),
            'command_index': len(self.command_history)
        }

        payload = {
            'metadata': metadata,
            'data': results
        }

        with open(filename, 'w') as f:
            json.dump(payload, f, indent=2)

        self.state['last_css_test'] = {
            'file': str(filename),
            'metadata': metadata
        }

        self._update_index('selectors', filename.name, metadata)
        self._increment_file_count('selectors')

        print(f"💾 CSS selector results saved: {filename.name}")
        return filename

    def save_semantic_results(self, results: Dict, context: Dict = None):
        """Save semantic extraction results"""
        timestamp = datetime.now().strftime("%H%M%S_%f")
        filename = self.dirs['semantic'] / f"semantic_{timestamp}.json"

        metadata = {
            'session_id': self.session_id,
            'timestamp': datetime.now().isoformat(),
            'tab_url': self.metadata.tab_url,
            'tab_title': self.metadata.tab_title,
            'context': context or {},
            'json_ld_blocks': results.get('statistics', {}).get('json_ld_blocks', 0),
            'rdfa_triples': results.get('statistics', {}).get('rdfa_triples', 0),
            'microdata_items': results.get('statistics', {}).get('microdata_items', 0),
            'total_triples': results.get('statistics', {}).get('total_triples', 0),
            'command_index': len(self.command_history)
        }

        payload = {
            'metadata': metadata,
            'data': results
        }

        with open(filename, 'w') as f:
            json.dump(payload, f, indent=2)

        self.state['last_semantic_extraction'] = {
            'file': str(filename),
            'metadata': metadata
        }

        self._update_index('semantic', filename.name, metadata)
        self._increment_file_count('semantic')

        print(f"💾 Semantic data saved: {filename.name}")
        return filename

    def save_json_ld_results(self, json_ld_data: List[Dict], context: Dict = None):
        """Save JSON-LD extraction results specifically"""
        timestamp = datetime.now().strftime("%H%M%S_%f")
        filename = self.dirs['semantic'] / f"jsonld_{timestamp}.json"

        metadata = {
            'session_id': self.session_id,
            'timestamp': datetime.now().isoformat(),
            'tab_url': self.metadata.tab_url,
            'tab_title': self.metadata.tab_title,
            'context': context or {},
            'block_count': len(json_ld_data),
            'command_index': len(self.command_history)
        }

        payload = {
            'metadata': metadata,
            'data': json_ld_data
        }

        with open(filename, 'w') as f:
            json.dump(payload, f, indent=2)

        self.state['last_json_ld'] = {
            'file': str(filename),
            'metadata': metadata
        }

        self._update_index('semantic', filename.name, metadata)
        self._increment_file_count('semantic')

        print(f"💾 JSON-LD data saved: {filename.name}")
        return filename

    def save_rdfa_results(self, rdfa_data: List[Dict], context: Dict = None):
        """Save RDFa extraction results specifically"""
        timestamp = datetime.now().strftime("%H%M%S_%f")
        filename = self.dirs['semantic'] / f"rdfa_{timestamp}.json"

        metadata = {
            'session_id': self.session_id,
            'timestamp': datetime.now().isoformat(),
            'tab_url': self.metadata.tab_url,
            'tab_title': self.metadata.tab_title,
            'context': context or {},
            'triple_count': len(rdfa_data),
            'command_index': len(self.command_history)
        }

        payload = {
            'metadata': metadata,
            'data': rdfa_data
        }

        with open(filename, 'w') as f:
            json.dump(payload, f, indent=2)

        self.state['last_rdfa'] = {
            'file': str(filename),
            'metadata': metadata
        }

        self._update_index('semantic', filename.name, metadata)
        self._increment_file_count('semantic')

        print(f"💾 RDFa data saved: {filename.name}")
        return filename

    # ============================================================
    # EXISTING HELPER METHODS - PRESERVED
    # ============================================================

    def _update_index(self, category: str, filename: str, metadata: Dict):
        """Update the session index file - PRESERVED"""
        index_file = self.session_dir / "index.json"

        index = {}
        if index_file.exists():
            with open(index_file, 'r') as f:
                index = json.load(f)

        if category not in index:
            index[category] = []

        index[category].append({
            'filename': filename,
            'timestamp': metadata.get('timestamp'),
            'context': metadata.get('context', {})
        })

        with open(index_file, 'w') as f:
            json.dump(index, f, indent=2, default=str)

    def _increment_file_count(self, category: str):
        """Track file counts - PRESERVED"""
        if category not in self.metadata.files_generated:
            self.metadata.files_generated[category] = 0
        self.metadata.files_generated[category] += 1

    def _count_nodes(self, node: Dict) -> int:
        """Count total nodes in DOM tree - PRESERVED"""
        if not node:
            return 0
        count = 1
        for child in node.get('children', []):
            count += self._count_nodes(child)
        return count

    def _save_state(self):
        """Save current session state to memory - PRESERVED AND EXTENDED"""
        state_file = self.dirs['memory'] / "state.json"
        state_data = {
            'metadata': asdict(self.metadata),
            'state': self.state,
            'command_count': len(self.command_history),
            'last_updated': datetime.now().isoformat()
        }
        with open(state_file, 'w') as f:
            json.dump(state_data, f, indent=2, default=str)

    def get_latest(self, category: str) -> Optional[Path]:
        """Get the latest file in a category - PRESERVED"""
        dir_path = self.dirs.get(category)
        if not dir_path or not dir_path.exists():
            return None

        files = list(dir_path.glob('*'))
        if not files:
            return None

        return max(files, key=lambda p: p.stat().st_mtime)

    def export_session(self, format: str = 'json'):
        """Export entire session data - PRESERVED"""
        export_file = self.dirs['exports'] / f"session_export_{self.session_id}.{format}"

        # Collect all data
        session_data = {
            'metadata': asdict(self.metadata),
            'state': self.state,
            'command_history': [asdict(cmd) for cmd in self.command_history],
            'files': {}
        }

        # List all files
        for category, dir_path in self.dirs.items():
            if category != 'exports' and dir_path.exists():
                files = list(dir_path.glob('*'))
                session_data['files'][category] = [f.name for f in files]

        with open(export_file, 'w') as f:
            json.dump(session_data, f, indent=2, default=str)

        print(f"📦 Session exported to: {export_file}")
        return export_file

    def generate_report(self) -> str:
        """Generate a comprehensive session report - PRESERVED"""
        report = []
        report.append("=" * 70)
        report.append(f"📊 SESSION REPORT: {self.session_id}")
        report.append("=" * 70)
        report.append(f"Start Time: {self.metadata.start_time}")
        report.append(f"End Time: {self.metadata.end_time or 'In progress'}")
        report.append(f"Chrome Port: {self.metadata.chrome_port}")
        report.append(f"Tab URL: {self.metadata.tab_url}")
        report.append(f"Tab Title: {self.metadata.tab_title}")
        report.append(f"\n📈 Statistics:")
        report.append(f"  Total Commands: {self.metadata.total_commands}")
        report.append(f"  Interactions: {self.state['interaction_count']}")
        report.append(f"  Errors: {len(self.state['errors'])}")

        # Command type breakdown
        cmd_types = defaultdict(int)
        for cmd in self.command_history:
            cmd_type = cmd.command.split('.')[0] if '.' in cmd.command else cmd.command
            cmd_types[cmd_type] += 1

        report.append(f"\n📋 Command Types:")
        for cmd_type, count in sorted(cmd_types.items()):
            report.append(f"  {cmd_type}: {count}")

        # Files generated
        report.append(f"\n📁 Files Generated:")
        for category, count in self.metadata.files_generated.items():
            report.append(f"  {category}: {count} files")

        # Latest snapshots
        report.append(f"\n🔍 Latest Snapshots:")
        for category in ['dom_trees', 'snapshots', 'accessibility', 'computed_styles']:
            latest = self.state.get(f'last_{category.rstrip("s")}')
            if latest:
                report.append(f"  {category}: {latest['file']}")

        # Errors summary
        if self.state['errors']:
            report.append(f"\n⚠️ Recent Errors:")
            for error in self.state['errors'][-5:]:  # Last 5 errors
                report.append(f"  [{error['timestamp']}] {error['error'][:100]}")

        report.append(f"\n📂 Session Directory: {self.session_dir}")
        report.append("=" * 70)

        # Save report
        report_file = self.dirs['logs'] / "report.txt"
        report_text = "\n".join(report)
        with open(report_file, 'w') as f:
            f.write(report_text)

        return report_text

    def close(self):
        """Close the session - PRESERVED"""
        self.metadata.end_time = datetime.now().isoformat()
        self._log_event('session_end', {
            'total_commands': self.metadata.total_commands,
            'duration': str(datetime.now() - datetime.fromisoformat(self.metadata.start_time))
        })
        self._save_state()

        # Generate final report
        self.generate_report()

        print(f"\n✅ Session {self.session_id} closed")
        print(f"📂 Data saved to: {self.session_dir}")


# ============================================================
# ENHANCED CHROME CDP CONTROLLER - EXTENDED
# ============================================================

class EnhancedChromeCDP:
    """Enhanced Chrome CDP Controller with comprehensive accessibility and script execution - EXTENDED"""

    def __init__(self, port: int = 9227, session_dir: str = None):
        self.port = port
        self.base_url = f"http://127.0.0.1:{port}"
        self.ws_url = None
        self.tabs = []
        self.connection_timeout = 10
        self._command_counter = 0
        self._dom_enabled = False
        self._css_enabled = False
        self._ax_enabled = False

        # Initialize session manager
        if session_dir is None:
            session_dir = os.getcwd()
        self.session = SessionManager(session_dir)
        self.session.metadata.chrome_port = port

        # Auto-save feature
        self.auto_save = True

        # Initialize new extractors
        self._semantic_extractor = SemanticExtractor()
        self._css_tester = CSSSelectorTester()

    # ============================================================
    # EXISTING METHODS - PRESERVED COMPLETELY
    # ============================================================

    def get_tabs(self) -> List[Dict]:
        """Get all tabs from Chrome with enhanced info - PRESERVED"""
        try:
            response = requests.get(f"{self.base_url}/json", timeout=5)
            if response.status_code == 200:
                tabs = response.json()
                self.tabs = [t for t in tabs if t.get('type') == 'page']

                # Update session metadata
                if self.tabs:
                    self.session.metadata.tab_url = self.tabs[0].get('url', '')
                    self.session.metadata.tab_title = self.tabs[0].get('title', '')

                print(f"🔍 Found {len(self.tabs)} tabs")
                return self.tabs
            return []
        except Exception as e:
            error_msg = f"Error fetching tabs: {e}"
            print(f"❌ {error_msg}")
            self.session.log_error(error_msg)
            return []

    def get_websocket_url(self, tab_index: int = 0) -> Optional[str]:
        """Get WebSocket URL for a specific tab - PRESERVED"""
        self.get_tabs()

        if not self.tabs:
            print("❌ No tabs found")
            return None

        if tab_index >= len(self.tabs):
            print(f"❌ Tab index {tab_index} out of range")
            return None

        ws_url = self.tabs[tab_index].get('webSocketDebuggerUrl')
        if ws_url:
            self.ws_url = ws_url
            # Update session metadata
            self.session.metadata.tab_url = self.tabs[tab_index].get('url', '')
            self.session.metadata.tab_title = self.tabs[tab_index].get('title', '')
            print(f"🔗 WebSocket URL: {ws_url[:50]}...")
            return ws_url
        print("❌ No WebSocket URL found for tab")
        return None

    def _connect_websocket(self) -> Optional[websocket.WebSocket]:
        """Establish WebSocket connection with proper headers - PRESERVED"""
        ws_url = self.ws_url
        if not ws_url:
            print("❌ No WebSocket URL available")
            return None

        try:
            print(f"🔌 Connecting to WebSocket...")
            ws = websocket.create_connection(
                ws_url,
                timeout=self.connection_timeout,
                header={"Origin": f"http://127.0.0.1:{self.port}"}
            )
            print("✅ WebSocket connected")
            self._dom_enabled = False
            self._css_enabled = False
            self._ax_enabled = False
            return ws
        except Exception as e:
            error_msg = f"WebSocket connection error: {e}"
            print(f"❌ {error_msg}")
            self.session.log_error(error_msg)
            return None

    def _send_cdp_command(self, ws: websocket.WebSocket, method: str, params: Dict = None) -> Dict:
        """Send CDP command and get response - PRESERVED"""
        self._command_counter += 1
        cmd_id = self._command_counter
        start_time = time.time()

        cmd = {
            "id": cmd_id,
            "method": method,
            "params": params or {}
        }

        print(f"📤 Sending: {method}")
        if params:
            print(f"   Params: {json.dumps(params)[:200]}")

        try:
            ws.send(json.dumps(cmd))
        except Exception as e:
            error_msg = f"Failed to send command: {e}"
            print(f"❌ {error_msg}")
            self.session.log_error(error_msg, {'command': method, 'params': params})
            self.session.log_command(method, params, False, error_msg, (time.time() - start_time) * 1000)
            return None

        while time.time() - start_time < 30:
            try:
                response = ws.recv()
                data = json.loads(response)

                if 'id' in data and data['id'] == cmd_id:
                    duration_ms = (time.time() - start_time) * 1000

                    if 'error' in data:
                        error_msg = json.dumps(data['error'])
                        print(f"❌ CDP Error: {error_msg}")
                        self.session.log_error(error_msg, {'command': method})
                        self.session.log_command(method, params, False, error_msg, duration_ms)
                    elif 'result' in data:
                        print(f"✅ Received response for {method}")
                        result_summary = f"Success - Type: {type(data['result']).__name__}"
                        self.session.log_command(method, params, True, result_summary, duration_ms)

                    return data
                else:
                    # Handle events/notifications
                    if 'method' in data:
                        print(f"ℹ️ Notification: {data['method']}")
                        if data['method'] in ['Runtime.executionContextCreated',
                                             'Runtime.executionContextDestroyed']:
                            self.session._log_event('cdp_notification', data)
                    continue

            except websocket.WebSocketTimeoutException:
                print("⏳ Waiting for response...")
                continue
            except Exception as e:
                error_msg = f"Response parsing error: {e}"
                print(f"⚠️ {error_msg}")
                self.session.log_error(error_msg)
                continue

        error_msg = f"Timeout waiting for response to {method}"
        print(f"❌ {error_msg}")
        self.session.log_error(error_msg, {'command': method})
        self.session.log_command(method, params, False, error_msg, 30000)
        return None

    def _enable_domain(self, ws: websocket.WebSocket, domain: str) -> bool:
        """Enable a CDP domain - PRESERVED"""
        if domain == "DOM" and self._dom_enabled:
            return True
        if domain == "CSS" and self._css_enabled:
            return True
        if domain == "Accessibility" and self._ax_enabled:
            return True

        print(f"🔧 Enabling domain: {domain}")
        try:
            result = self._send_cdp_command(ws, f"{domain}.enable")
            if result and 'error' not in result:
                print(f"✅ {domain} enabled")
                if domain == "DOM":
                    self._dom_enabled = True
                elif domain == "CSS":
                    self._css_enabled = True
                elif domain == "Accessibility":
                    self._ax_enabled = True
                return True
            else:
                print(f"❌ Failed to enable {domain}")
                return False
        except Exception as e:
            error_msg = f"Exception enabling {domain}: {e}"
            print(f"❌ {error_msg}")
            self.session.log_error(error_msg)
            return False

    def get_document(self, tab_index: int = 0, depth: int = -1,
                     pierce: bool = True, auto_save: bool = None) -> Optional[Dict]:
        """Get full DOM tree with auto-save - PRESERVED"""
        print("\n📄 DOM.getDocument - Fetching DOM tree...")

        ws_url = self.get_websocket_url(tab_index)
        if not ws_url:
            return None

        ws = self._connect_websocket()
        if not ws:
            return None

        try:
            if not self._enable_domain(ws, "DOM"):
                ws.close()
                return None

            params = {"depth": depth, "pierce": pierce}
            result = self._send_cdp_command(ws, "DOM.getDocument", params)
            ws.close()

            if result and 'result' in result:
                root = result['result']['root']
                print(f"✅ DOM tree retrieved! Root: {root.get('nodeName')} (ID: {root.get('nodeId')})")

                save = auto_save if auto_save is not None else self.auto_save
                if save:
                    context = {
                        'depth': depth,
                        'pierce': pierce,
                        'method': 'DOM.getDocument'
                    }
                    self.session.save_dom_tree(root, context)

                return root
            return None
        except Exception as e:
            error_msg = f"DOM.getDocument error: {e}"
            print(f"❌ {error_msg}")
            self.session.log_error(error_msg)
            if ws:
                ws.close()
            return None

    def get_dom_snapshot(self, tab_index: int = 0, auto_save: bool = None) -> Optional[LayoutSnapshot]:
        """Capture complete DOM snapshot with auto-save - PRESERVED"""
        print("\n📸 DOMSnapshot.getSnapshot - Capturing snapshot...")

        ws_url = self.get_websocket_url(tab_index)
        if not ws_url:
            return None

        ws = self._connect_websocket()
        if not ws:
            return None

        try:
            print("🔧 Enabling required domains...")
            self._enable_domain(ws, "DOM")
            self._enable_domain(ws, "CSS")

            params = {
                "computedStyleWhitelist": [],
                "includeEventListeners": False,
                "includePaintOrder": False,
                "includeUserAgentShadowTree": True
            }
            result = self._send_cdp_command(ws, "DOMSnapshot.getSnapshot", params)
            ws.close()

            if result and 'result' in result:
                snapshot_data = result['result']
                snapshot = LayoutSnapshot(
                    dom_nodes=snapshot_data.get('domNodes', []),
                    layout_tree=snapshot_data.get('layoutTree', []),
                    computed_styles=snapshot_data.get('computedStyles', [])
                )
                print(f"✅ Snapshot captured!")
                print(f"   DOM nodes: {len(snapshot.dom_nodes)}")
                print(f"   Layout tree: {len(snapshot.layout_tree)}")

                save = auto_save if auto_save is not None else self.auto_save
                if save:
                    context = {
                        'method': 'DOMSnapshot.getSnapshot',
                        'params': params
                    }
                    self.session.save_snapshot(snapshot, context)

                return snapshot
            return None
        except Exception as e:
            error_msg = f"DOMSnapshot.getSnapshot error: {e}"
            print(f"❌ {error_msg}")
            self.session.log_error(error_msg)
            if ws:
                ws.close()
            return None

    def get_accessibility_tree(self, tab_index: int = 0, auto_save: bool = None) -> Optional[Dict]:
        """Get accessibility tree with auto-save - PRESERVED"""
        print("\n♿ Accessibility.getFullAXTree - Getting accessibility tree...")

        ws_url = self.get_websocket_url(tab_index)
        if not ws_url:
            return None

        ws = self._connect_websocket()
        if not ws:
            return None

        try:
            if not self._enable_domain(ws, "Accessibility"):
                ws.close()
                return None

            result = self._send_cdp_command(ws, "Accessibility.getFullAXTree")
            ws.close()

            if result and 'result' in result:
                nodes = result['result'].get('nodes', [])
                print(f"✅ Accessibility tree retrieved! Found {len(nodes)} nodes")

                save = auto_save if auto_save is not None else self.auto_save
                if save:
                    context = {'method': 'Accessibility.getFullAXTree'}
                    self.session.save_accessibility_tree(result['result'], context)

                return result['result']
            return None
        except Exception as e:
            error_msg = f"Accessibility.getFullAXTree error: {e}"
            print(f"❌ {error_msg}")
            self.session.log_error(error_msg)
            if ws:
                ws.close()
            return None

    def get_comprehensive_ax_tree(self, tab_index: int = 0) -> Dict:
        """Get comprehensive accessibility tree - PRESERVED"""
        print("\n♿ Getting Comprehensive Accessibility Tree...")

        ax_data = self.get_accessibility_tree(tab_index, auto_save=False)
        if not ax_data:
            return {"error": "Failed to get accessibility tree"}

        nodes = ax_data.get('nodes', [])

        # Build a structured tree with detailed node information
        comprehensive = {
            "total_nodes": len(nodes),
            "nodes_by_role": Counter(),
            "nodes_by_property": Counter(),
            "tree_structure": [],
            "node_details": [],
            "relationships": [],
            "statistics": {
                "total_roles": 0,
                "total_properties": 0,
                "deepest_depth": 0,
                "nodes_with_name": 0,
                "nodes_with_description": 0,
                "nodes_interactive": 0,
                "nodes_visible": 0
            }
        }

        # Process each node
        for node in nodes:
            # Count roles
            role = node.get('role', {}).get('value', 'unknown')
            comprehensive["nodes_by_role"][role] += 1

            # Count properties
            properties = node.get('properties', [])
            for prop in properties:
                prop_name = prop.get('name', 'unknown')
                comprehensive["nodes_by_property"][prop_name] += 1

            # Build node details
            node_detail = {
                "node_id": node.get('nodeId'),
                "backend_node_id": node.get('backendDOMNodeId'),
                "role": role,
                "name": node.get('name', {}).get('value', ''),
                "description": node.get('description', {}).get('value', ''),
                "properties": {p.get('name'): p.get('value', {}).get('value', '') for p in properties},
                "child_ids": node.get('childIds', []),
                "parent_id": node.get('parentId'),
                "is_interactive": self._is_interactive_node(node),
                "has_name": bool(node.get('name', {}).get('value')),
                "has_description": bool(node.get('description', {}).get('value'))
            }
            comprehensive["node_details"].append(node_detail)

            # Update statistics
            if node_detail["has_name"]:
                comprehensive["statistics"]["nodes_with_name"] += 1
            if node_detail["has_description"]:
                comprehensive["statistics"]["nodes_with_description"] += 1
            if node_detail["is_interactive"]:
                comprehensive["statistics"]["nodes_interactive"] += 1

        comprehensive["statistics"]["total_roles"] = len(comprehensive["nodes_by_role"])
        comprehensive["statistics"]["total_properties"] = len(comprehensive["nodes_by_property"])

        # Build tree structure
        comprehensive["tree_structure"] = self._build_ax_tree_structure(nodes)

        # Save comprehensive data
        if self.auto_save:
            context = {'method': 'Comprehensive_AX_Tree'}
            self.session.save_accessibility_tree(comprehensive, context)

        return comprehensive

    def _is_interactive_node(self, node: Dict) -> bool:
        """Determine if a node is interactive - PRESERVED"""
        interactive_roles = {'button', 'link', 'checkbox', 'radio', 'textbox', 'combobox',
                           'slider', 'spinbutton', 'menu', 'menuitem', 'tab', 'treeitem',
                           'gridcell', 'listitem', 'option', 'switch', 'tabpanel'}

        role = node.get('role', {}).get('value', '').lower()
        if role in interactive_roles:
            return True

        # Check for interactive properties
        properties = node.get('properties', [])
        for prop in properties:
            if prop.get('name') in {'click', 'focus', 'keydown', 'keyup'}:
                return True
            if prop.get('name') == 'aria-expanded':
                return True

        return False

    def _build_ax_tree_structure(self, nodes: List[Dict], parent_id: int = None, depth: int = 0) -> List[Dict]:
        """Build a hierarchical tree structure from AX nodes - PRESERVED"""
        tree = []

        for node in nodes:
            node_id = node.get('nodeId')
            if node.get('parentId') == parent_id:
                # Create node entry
                node_entry = {
                    "node_id": node_id,
                    "role": node.get('role', {}).get('value', 'unknown'),
                    "name": node.get('name', {}).get('value', ''),
                    "depth": depth,
                    "children": self._build_ax_tree_structure(nodes, node_id, depth + 1)
                }
                tree.append(node_entry)

        return tree

    def display_ax_tree_chart(self, ax_data: Dict):
        """Display comprehensive accessibility tree chart - PRESERVED"""
        if not ax_data or "error" in ax_data:
            print("❌ No accessibility data available")
            return

        print("\n" + "=" * 80)
        print("♿ COMPREHENSIVE ACCESSIBILITY TREE ANALYSIS")
        print("=" * 80)

        # Statistics section
        stats = ax_data.get("statistics", {})
        print("\n📊 STATISTICS:")
        print(f"   Total AX Nodes: {ax_data.get('total_nodes', 0)}")
        print(f"   Total Roles: {stats.get('total_roles', 0)}")
        print(f"   Total Properties: {stats.get('total_properties', 0)}")
        print(f"   Deepest Depth: {stats.get('deepest_depth', 0)}")
        print(f"   Nodes with Name: {stats.get('nodes_with_name', 0)}")
        print(f"   Nodes with Description: {stats.get('nodes_with_description', 0)}")
        print(f"   Interactive Nodes: {stats.get('nodes_interactive', 0)}")

        # Role distribution
        print("\n📋 ROLE DISTRIBUTION:")
        roles = ax_data.get("nodes_by_role", {})
        sorted_roles = sorted(roles.items(), key=lambda x: x[1], reverse=True)
        for role, count in sorted_roles[:15]:  # Show top 15
            bar = "█" * (count * 2 if count < 30 else 60)
            print(f"   {role:20s}: {count:4d} {bar}")

        # Property distribution
        print("\n📋 TOP PROPERTIES:")
        properties = ax_data.get("nodes_by_property", {})
        sorted_props = sorted(properties.items(), key=lambda x: x[1], reverse=True)
        for prop, count in sorted_props[:10]:
            bar = "█" * (count * 2 if count < 30 else 60)
            print(f"   {prop:20s}: {count:4d} {bar}")

        # Tree structure visualization
        print("\n🌳 TREE STRUCTURE (Top levels):")
        tree = ax_data.get("tree_structure", [])
        self._display_tree_structure(tree, max_depth=3)

        # Interactive nodes summary
        print("\n🎯 INTERACTIVE NODES SUMMARY:")
        interactive_nodes = [n for n in ax_data.get("node_details", []) if n.get("is_interactive")]
        for node in interactive_nodes[:10]:
            print(f"   [{node.get('role', 'unknown')}] {node.get('name', 'unnamed')}")

    def _display_tree_structure(self, tree: List[Dict], prefix: str = "", max_depth: int = 3, current_depth: int = 0):
        """Display tree structure recursively - PRESERVED"""
        if current_depth > max_depth:
            return

        for i, node in enumerate(tree):
            is_last = i == len(tree) - 1
            connector = "└── " if is_last else "├── "

            role = node.get('role', 'unknown')
            name = node.get('name', '')[:30]
            node_info = f"[{role}] {name}" if name else f"[{role}]"

            print(f"{prefix}{connector}{node_info}")

            if node.get('children'):
                new_prefix = prefix + ("    " if is_last else "│   ")
                self._display_tree_structure(
                    node.get('children', []),
                    new_prefix,
                    max_depth,
                    current_depth + 1
                )

    def get_computed_styles(self, tab_index: int = 0,
                           node_id: int = None, auto_save: bool = None) -> Optional[List[Dict]]:
        """Get computed styles with auto-save - PRESERVED"""
        print("\n🎨 CSS.getComputedStyleForNode - Getting computed styles...")

        ws_url = self.get_websocket_url(tab_index)
        if not ws_url:
            return None

        ws = self._connect_websocket()
        if not ws:
            return None

        try:
            self._enable_domain(ws, "DOM")
            self._enable_domain(ws, "CSS")

            if node_id is None:
                root = self.get_document(tab_index, auto_save=False)
                if root:
                    node_id = self._find_first_element(root)
                    if node_id:
                        print(f"   Using first element node ID: {node_id}")
                    else:
                        print("❌ Could not find any element nodes")
                        ws.close()
                        return None
                else:
                    ws.close()
                    return None

            params = {"nodeId": node_id}
            result = self._send_cdp_command(ws, "CSS.getComputedStyleForNode", params)
            ws.close()

            if result and 'result' in result:
                styles = result['result'].get('computedStyle', [])
                print(f"✅ Retrieved {len(styles)} computed styles")

                save = auto_save if auto_save is not None else self.auto_save
                if save:
                    context = {
                        'method': 'CSS.getComputedStyleForNode',
                        'node_id': node_id
                    }
                    self.session.save_computed_styles(styles, context)

                return styles
            return None
        except Exception as e:
            error_msg = f"CSS.getComputedStyleForNode error: {e}"
            print(f"❌ {error_msg}")
            self.session.log_error(error_msg)
            if ws:
                ws.close()
            return None

    def _find_first_element(self, node: Dict) -> Optional[int]:
        """Find the first element node - PRESERVED"""
        if node.get('nodeType') == 1:
            return node.get('nodeId')

        for child in node.get('children', []):
            result = self._find_first_element(child)
            if result:
                return result
        return None

    def _count_nodes(self, node: Dict) -> int:
        """Count total nodes in DOM tree - PRESERVED"""
        count = 1
        for child in node.get('children', []):
            count += self._count_nodes(child)
        return count

    def analyze_page_structure(self, tab_index: int = 0, auto_save: bool = None,
                               include_regex: bool = False,
                               include_xpath: bool = False,
                               include_selectors: bool = False,
                               include_semantic: bool = False) -> Dict:
        """Comprehensive page analysis with full session logging - EXTENDED"""
        print("\n🔬 Performing complete page analysis...")
        result = {
            "timestamp": datetime.now().isoformat(),
            "dom_tree": None,
            "snapshot": None,
            "accessibility": None,
            "metadata": {}
        }

        dom_root = self.get_document(tab_index, auto_save=auto_save)
        if dom_root:
            result["dom_tree"] = dom_root
            result["metadata"]["node_count"] = self._count_nodes(dom_root)

        snapshot = self.get_dom_snapshot(tab_index, auto_save=auto_save)
        if snapshot:
            result["snapshot"] = snapshot
            result["metadata"]["layout_count"] = len(snapshot.layout_tree)

        ax_tree = self.get_comprehensive_ax_tree(tab_index)
        if ax_tree and "error" not in ax_tree:
            result["accessibility"] = ax_tree
            result["metadata"]["ax_nodes"] = ax_tree.get('total_nodes', 0)
            result["metadata"]["ax_roles"] = len(ax_tree.get('nodes_by_role', {}))

            # Display the AX tree chart
            self.display_ax_tree_chart(ax_tree)

        # NEW: Optional regex extraction
        if include_regex:
            try:
                html_source = self._get_page_html(tab_index)
                if html_source:
                    regex_results = self.extract_regex_from_page(tab_index, auto_save=auto_save)
                    result["regex"] = regex_results
                    result["metadata"]["regex_matches"] = sum(len(matches) for matches in regex_results.get('patterns', {}).values())
            except Exception as e:
                print(f"⚠️ Regex extraction failed: {e}")

        # NEW: Optional XPath analysis
        if include_xpath:
            try:
                # Run some common XPath queries
                html_source = self._get_page_html(tab_index)
                if html_source:
                    xpath_results = []
                    common_xpaths = [
                        "//*[@id]",  # Elements with IDs
                        "//button",  # All buttons
                        "//a[@href]",  # All links
                        "//*[@class]",  # Elements with classes
                        "//*[@role='button']",  # Role buttons
                        "//input[@type='text']",  # Text inputs
                    ]
                    for xpath in common_xpaths:
                        result_xpath = self.query_xpath(tab_index, xpath, auto_save=auto_save)
                        if result_xpath:
                            xpath_results.append({
                                'expression': xpath,
                                'count': result_xpath.get('count', 0)
                            })
                    result["xpath_analysis"] = xpath_results
            except Exception as e:
                print(f"⚠️ XPath analysis failed: {e}")

        # NEW: Optional semantic extraction
        if include_semantic:
            try:
                semantic_data = self.extract_semantic_data(tab_index, auto_save=auto_save)
                if semantic_data:
                    result["semantic"] = semantic_data
                    stats = semantic_data.get('statistics', {})
                    result["metadata"]["json_ld_blocks"] = stats.get('json_ld_blocks', 0)
                    result["metadata"]["rdfa_triples"] = stats.get('rdfa_triples', 0)
                    result["metadata"]["total_triples"] = stats.get('total_triples', 0)
            except Exception as e:
                print(f"⚠️ Semantic extraction failed: {e}")

        print(f"\n✅ Analysis complete!")

        self.session.log_command('analyze_page_structure',
                                {'tab_index': tab_index},
                                True,
                                f"Analysis complete: {result['metadata']}")

        return result

    def _get_page_html(self, tab_index: int = 0) -> Optional[str]:
        """Get the full HTML of the current page using Runtime.evaluate"""
        script = "document.documentElement.outerHTML"
        result = self.evaluate_script(script, tab_index)
        if isinstance(result, str):
            return result
        return None

    # ============================================================
    # NEW: REGEX EXTRACTION METHODS
    # ============================================================

    def extract_regex_from_page(self, tab_index: int = 0,
                               patterns: List[str] = None,
                               auto_save: bool = None) -> Dict:
        """
        Extract regex patterns from the current page
        
        Args:
            tab_index: Index of the tab to use
            patterns: List of pattern names to extract (default: all)
            auto_save: Whether to auto-save results
        """
        start_time = time.time()
        print("\n🔍 Extracting regex patterns from page...")

        # Get page HTML
        html_source = self._get_page_html(tab_index)
        if not html_source:
            print("❌ Failed to get page HTML")
            return {'error': 'Failed to get page HTML'}

        # Determine which patterns to use
        if patterns is None:
            patterns = RegexPatterns.get_pattern_names()
        elif isinstance(patterns, str):
            patterns = [patterns]

        # Extract patterns
        results = {}
        for pattern_name in patterns:
            try:
                matches = extract(pattern_name, html_source)
                if matches:
                    results[pattern_name] = matches
                    print(f"  {pattern_name}: {len(matches)} matches")
            except Exception as e:
                print(f"  ⚠️ {pattern_name}: {e}")
                results[pattern_name] = []

        # Also extract with metadata for detailed results
        detailed_results = {}
        for pattern_name in patterns:
            try:
                matches = extract_with_metadata(pattern_name, html_source)
                if matches:
                    detailed_results[pattern_name] = [asdict(m) for m in matches]
            except Exception:
                pass

        output = {
            'patterns': results,
            'detailed': detailed_results,
            'total_matches': sum(len(m) for m in results.values()),
            'pattern_count': len(results),
            'timestamp': datetime.now().isoformat(),
            'tab_url': self.session.metadata.tab_url
        }

        # Log the command
        duration_ms = (time.time() - start_time) * 1000
        self.session.log_command(
            'regex.extract',
            {'patterns': patterns},
            True,
            f"Extracted {output['total_matches']} matches from {output['pattern_count']} patterns",
            duration_ms
        )

        # Save results
        save = auto_save if auto_save is not None else self.auto_save
        if save:
            self.session.save_regex_results(output, {'patterns': patterns})

        return output

    def extract_regex(self, text: str, patterns: List[str] = None) -> Dict:
        """
        Extract regex patterns from arbitrary text
        
        Args:
            text: The text to search
            patterns: List of pattern names to extract (default: all)
        """
        if patterns is None:
            patterns = RegexPatterns.get_pattern_names()

        results = {}
        for pattern_name in patterns:
            try:
                matches = extract(pattern_name, text)
                if matches:
                    results[pattern_name] = matches
            except Exception:
                results[pattern_name] = []

        return {
            'patterns': results,
            'total_matches': sum(len(m) for m in results.values()),
            'pattern_count': len(results)
        }

    def validate_regex(self, pattern_name: str, value: str) -> bool:
        """Validate a string against a regex pattern"""
        return validate(pattern_name, value)

    def extract_regex_named(self, pattern_name: str, text: str) -> List[Dict[str, str]]:
        """Extract with named groups"""
        return extract_named(pattern_name, text)

    # ============================================================
    # NEW: XPATH QUERY METHODS
    # ============================================================

    def query_xpath(self, tab_index: int = 0,
                   xpath: str = None,
                   context_node: Dict = None,
                   auto_save: bool = None) -> Dict:
        """
        Query the page using XPath
        
        Args:
            tab_index: Index of the tab to use
            xpath: XPath expression
            context_node: Optional context node (dictionary representation)
            auto_save: Whether to auto-save results
        """
        start_time = time.time()
        print(f"\n🌳 XPath Query: {xpath}")

        if not xpath:
            return {'error': 'No XPath expression provided'}

        # Get page HTML
        html_source = self._get_page_html(tab_index)
        if not html_source:
            print("❌ Failed to get page HTML")
            return {'error': 'Failed to get page HTML'}

        # Execute the query
        query = DOMQuery(xpath)
        result = query.evaluate(html_source=html_source)

        # Build output
        output = {
            'expression': xpath,
            'count': result.count,
            'matches': result.matches,
            'duration_ms': result.duration_ms,
            'timestamp': datetime.now().isoformat(),
            'tab_url': self.session.metadata.tab_url
        }

        if result.error:
            output['error'] = result.error
            print(f"❌ XPath error: {result.error}")
        else:
            print(f"✅ Found {result.count} matches")

        # Log the command
        self.session.log_command(
            'xpath.query',
            {'xpath': xpath},
            not bool(result.error),
            f"Found {result.count} matches" if not result.error else f"Error: {result.error}",
            result.duration_ms
        )

        # Save results
        save = auto_save if auto_save is not None else self.auto_save
        if save:
            self.session.save_xpath_results(output, {'xpath': xpath})

        return output

    def query_xpath_simple(self, tab_index: int = 0, xpath: str = None) -> List[Dict]:
        """Simplified XPath query that returns matches only"""
        result = self.query_xpath(tab_index, xpath, auto_save=False)
        return result.get('matches', [])

    # ============================================================
    # NEW: CSS SELECTOR METHODS
    # ============================================================

    def test_css_selector(self, tab_index: int = 0,
                         selector: str = None,
                         attributes: List[str] = None,
                         auto_save: bool = None) -> Dict:
        """
        Test a CSS selector against the current page
        
        Args:
            tab_index: Index of the tab to use
            selector: CSS selector string
            attributes: List of attributes to extract
            auto_save: Whether to auto-save results
        """
        start_time = time.time()
        print(f"\n🎯 CSS Selector Test: {selector}")

        if not selector:
            return {'error': 'No CSS selector provided'}

        # Get page HTML
        html_source = self._get_page_html(tab_index)
        if not html_source:
            print("❌ Failed to get page HTML")
            return {'error': 'Failed to get page HTML'}

        # Test the selector
        result = self._css_tester.test(html_source, selector, attributes)

        # Build output
        output = {
            'selector': selector,
            'valid': result.valid,
            'match_count': result.match_count,
            'matches': result.matches,
            'duration_ms': result.duration_ms,
            'timestamp': datetime.now().isoformat(),
            'tab_url': self.session.metadata.tab_url
        }

        if result.error:
            output['error'] = result.error
            print(f"❌ CSS error: {result.error}")
        else:
            print(f"✅ Valid selector: Found {result.match_count} matches")

            # Show sample matches
            if result.matches:
                print(f"\n📋 Sample matches:")
                for i, match in enumerate(result.matches[:5]):
                    tag = match.get('tag', 'unknown')
                    text = match.get('text', '')[:50]
                    print(f"  [{i}] {tag}: {text}")

        # Log the command
        self.session.log_command(
            'css.test',
            {'selector': selector},
            result.valid,
            f"Found {result.match_count} matches" if result.valid else f"Error: {result.error}",
            result.duration_ms
        )

        # Save results
        save = auto_save if auto_save is not None else self.auto_save
        if save:
            self.session.save_css_results(output, {'selector': selector})

        return output

    def test_css_selector_simple(self, tab_index: int = 0, selector: str = None) -> List[Dict]:
        """Simplified CSS selector test that returns matches only"""
        result = self.test_css_selector(tab_index, selector, auto_save=False)
        return result.get('matches', [])

    def get_selector_stats(self, tab_index: int = 0, selector: str = None) -> Dict:
        """Get statistics about a CSS selector match on the page"""
        html_source = self._get_page_html(tab_index)
        if not html_source:
            return {'error': 'Failed to get page HTML'}

        return CSSSelectorTester.get_selector_stats(html_source, selector)

    def validate_css_selector(self, selector: str) -> bool:
        """Validate a CSS selector syntax"""
        return CSSSelectorTester.validate_selector(selector)

    # ============================================================
    # NEW: SEMANTIC EXTRACTION METHODS
    # ============================================================

    def extract_semantic_data(self, tab_index: int = 0,
                             auto_save: bool = None) -> Dict:
        """
        Extract all semantic data from the current page (JSON-LD, RDFa, Microdata)
        
        Args:
            tab_index: Index of the tab to use
            auto_save: Whether to auto-save results
        """
        start_time = time.time()
        print("\n🧠 Extracting semantic data...")

        # Get page HTML
        html_source = self._get_page_html(tab_index)
        if not html_source:
            print("❌ Failed to get page HTML")
            return {'error': 'Failed to get page HTML'}

        # Extract semantic data
        semantic_data = self._semantic_extractor.extract_from_html(html_source)

        # Build output
        output = {
            'json_ld': semantic_data.json_ld,
            'rdfa': semantic_data.rdfa,
            'microdata': semantic_data.microdata,
            'triples': semantic_data.triples,
            'statistics': semantic_data.statistics,
            'timestamp': datetime.now().isoformat(),
            'tab_url': self.session.metadata.tab_url
        }

        stats = semantic_data.statistics
        print(f"✅ Semantic data extracted:")
        print(f"   JSON-LD blocks: {stats.get('json_ld_blocks', 0)}")
        print(f"   RDFa triples: {stats.get('rdfa_triples', 0)}")
        print(f"   Microdata items: {stats.get('microdata_items', 0)}")
        print(f"   Total RDF triples: {stats.get('total_triples', 0)}")

        # Log the command
        duration_ms = (time.time() - start_time) * 1000
        self.session.log_command(
            'semantic.extract',
            {},
            True,
            f"Extracted {stats.get('total_triples', 0)} triples",
            duration_ms
        )

        # Save results
        save = auto_save if auto_save is not None else self.auto_save
        if save:
            self.session.save_semantic_results(output)

        return output

    def extract_json_ld(self, tab_index: int = 0, auto_save: bool = None) -> List[Dict]:
        """Extract JSON-LD from the current page"""
        start_time = time.time()
        print("\n🧠 Extracting JSON-LD...")

        html_source = self._get_page_html(tab_index)
        if not html_source:
            print("❌ Failed to get page HTML")
            return []

        json_ld_data = self._semantic_extractor._extract_json_ld(html_source)
        print(f"✅ Found {len(json_ld_data)} JSON-LD blocks")

        # Log the command
        duration_ms = (time.time() - start_time) * 1000
        self.session.log_command(
            'semantic.json_ld',
            {},
            True,
            f"Found {len(json_ld_data)} JSON-LD blocks",
            duration_ms
        )

        # Save results
        save = auto_save if auto_save is not None else self.auto_save
        if save:
            self.session.save_json_ld_results(json_ld_data)

        return json_ld_data

    def extract_rdfa(self, tab_index: int = 0, auto_save: bool = None) -> List[Dict]:
        """Extract RDFa from the current page"""
        start_time = time.time()
        print("\n🧠 Extracting RDFa...")

        html_source = self._get_page_html(tab_index)
        if not html_source:
            print("❌ Failed to get page HTML")
            return []

        rdfa_data = self._semantic_extractor._extract_rdfa(html_source)
        print(f"✅ Found {len(rdfa_data)} RDFa triples")

        # Log the command
        duration_ms = (time.time() - start_time) * 1000
        self.session.log_command(
            'semantic.rdfa',
            {},
            True,
            f"Found {len(rdfa_data)} RDFa triples",
            duration_ms
        )

        # Save results
        save = auto_save if auto_save is not None else self.auto_save
        if save:
            self.session.save_rdfa_results(rdfa_data)

        return rdfa_data

    # ============================================================
    # EXISTING METHODS - PRESERVED (continued)
    # ============================================================

    def evaluate_script(self, script: str, tab_index: int = 0,
                       return_by_value: bool = True,
                       await_promise: bool = True) -> Optional[Any]:
        """Execute JavaScript with session logging - PRESERVED"""
        print("\n⚡ Runtime.evaluate - Executing script...")

        ws_url = self.get_websocket_url(tab_index)
        if not ws_url:
            return None

        ws = self._connect_websocket()
        if not ws:
            return None

        try:
            self._enable_domain(ws, "Runtime")

            params = {
                "expression": script,
                "returnByValue": return_by_value,
                "awaitPromise": await_promise
            }
            result = self._send_cdp_command(ws, "Runtime.evaluate", params)
            ws.close()

            if result and 'result' in result:
                if 'result' in result['result']:
                    value = result['result']['result'].get('value')
                    print(f"✅ Script executed successfully")
                    return value
                elif 'error' in result['result']:
                    error_msg = f"Script error: {result['result']['error']}"
                    print(f"⚠️ {error_msg}")
                    self.session.log_error(error_msg, {'script': script[:100]})
            return None
        except Exception as e:
            error_msg = f"Runtime.evaluate error: {e}"
            print(f"❌ {error_msg}")
            self.session.log_error(error_msg, {'script': script[:100]})
            if ws:
                ws.close()
            return None

    def execute_script_from_file(self, script_path: str, tab_index: int = 0,
                                save_results: bool = True) -> Optional[Any]:
        """Execute a JavaScript file with proper handling - PRESERVED"""
        try:
            script_path = Path(script_path)
            if not script_path.exists():
                print(f"❌ Script file not found: {script_path}")
                return None

            with open(script_path, 'r') as f:
                script_content = f.read()

            print(f"📝 Executing script from: {script_path.name}")
            result = self.evaluate_script(script_content, tab_index)

            if save_results and result is not None:
                # Save execution results
                execution_data = {
                    'script_file': str(script_path),
                    'script_content': script_content[:500] + '...' if len(script_content) > 500 else script_content,
                    'result': result,
                    'execution_time': datetime.now().isoformat()
                }
                self.session.save_interaction(execution_data, {'type': 'script_execution'})

            return result

        except Exception as e:
            error_msg = f"Script execution error: {e}"
            print(f"❌ {error_msg}")
            self.session.log_error(error_msg, {'script_path': script_path})
            return None

    def find_interactive_elements(self, tab_index: int = 0) -> List[Dict]:
        """Find all interactive elements on the page using IIFE - PRESERVED"""
        print("\n🔍 Finding interactive elements...")

        js_script = """
        (function() {
            const results = [];
            const selectors = [
                'button', 'input[type="button"]', 'input[type="submit"]',
                'input[type="reset"]', 'a[href]', '[role="button"]',
                '[role="link"]', '[onclick]', '[data-action]', '.btn',
                '[class*="button"]', '[class*="btn"]', '[data-testid*="button"]',
                '[role="tab"]', '[role="menu"]', '[role="menuitem"]'
            ];

            const elements = document.querySelectorAll(selectors.join(','));

            elements.forEach((el, index) => {
                const rect = el.getBoundingClientRect();
                const isVisible = rect.width > 0 && rect.height > 0;
                const style = window.getComputedStyle(el);

                const attrs = {};
                ['id', 'class', 'data-action', 'data-testid', 'aria-label',
                 'title', 'type', 'value', 'href', 'name', 'role',
                 'aria-expanded', 'aria-haspopup', 'data-index'].forEach(attr => {
                    if (el.hasAttribute(attr)) {
                        attrs[attr] = el.getAttribute(attr);
                    }
                });

                let text = el.textContent.trim();
                if (!text && el.tagName === 'INPUT') {
                    text = el.value || el.getAttribute('placeholder') || '';
                }

                let type = el.tagName.toLowerCase();
                if (type === 'input') {
                    type = `input[${el.type || 'text'}]`;
                }

                let hasClickHandler = false;
                try {
                    hasClickHandler = typeof el.onclick === 'function' ||
                                     el.getAttribute('onclick') !== null;
                } catch(e) {}

                // Generate robust selector
                let selector = '';
                if (el.id) {
                    selector = '#' + el.id;
                } else if (el.hasAttribute('data-testid')) {
                    selector = `[data-testid="${el.getAttribute('data-testid')}"]`;
                } else if (el.hasAttribute('data-action')) {
                    selector = `[data-action="${el.getAttribute('data-action')}"]`;
                } else {
                    // Build a selector from attributes
                    const parts = [];
                    if (el.tagName) parts.push(el.tagName.toLowerCase());
                    if (el.className) {
                        const classes = el.className.split(' ').filter(c => c);
                        if (classes.length > 0) {
                            parts.push('.' + classes.join('.'));
                        }
                    }
                    selector = parts.join('');
                    if (!selector) {
                        selector = el.tagName.toLowerCase();
                    }
                }

                results.push({
                    index: index,
                    tag: el.tagName.toLowerCase(),
                    type: type,
                    text: text.substring(0, 100),
                    visible: isVisible,
                    hasClickHandler: hasClickHandler,
                    attributes: attrs,
                    selector: selector,
                    canClick: true,
                    xpath: el.getAttribute('xpath') || null
                });
            });

            return results;
        })();
        """

        result = self.evaluate_script(js_script, tab_index)
        if result and isinstance(result, list):
            print(f"✅ Found {len(result)} interactive elements")
            return result
        return []

    def interact_with_element(self, tab_index: int = 0, element_index: int = 0,
                             action: str = 'click', value: str = None,
                             delay: float = 0.5) -> Optional[Any]:
        """Interact with a specific element with session logging - PRESERVED"""
        print(f"\n🎯 Interacting with element #{element_index}...")

        verify_script = f"""
        (function() {{
            const selectors = [
                'button', 'input[type="button"]', 'input[type="submit"]',
                'input[type="reset"]', 'a[href]', '[role="button"]',
                '[role="link"]', '[onclick]', '[data-action]', '.btn',
                '[class*="button"]', '[class*="btn"]'
            ];

            const elements = document.querySelectorAll(selectors.join(','));
            if ({element_index} >= elements.length) {{
                return {{ error: 'Element index out of range' }};
            }}

            const el = elements[{element_index}];
            el.scrollIntoView({{ behavior: 'smooth', block: 'center' }});

            return {{
                tag: el.tagName.toLowerCase(),
                text: el.textContent.trim().substring(0, 100),
                visible: el.offsetParent !== null,
                canInteract: true
            }};
        }})();
        """

        verify_result = self.evaluate_script(verify_script, tab_index)
        if verify_result and 'error' in verify_result:
            print(f"❌ {verify_result['error']}")
            return None

        print(f"   Element: {verify_result.get('tag', 'unknown')}")
        print(f"   Text: {verify_result.get('text', '')}")
        print(f"   Visible: {verify_result.get('visible', False)}")

        time.sleep(delay)

        # Perform the action
        result = None
        if action == 'click':
            click_script = f"""
            (function() {{
                const selectors = [
                    'button', 'input[type="button"]', 'input[type="submit"]',
                    'input[type="reset"]', 'a[href]', '[role="button"]',
                    '[role="link"]', '[onclick]', '[data-action]', '.btn',
                    '[class*="button"]', '[class*="btn"]'
                ];

                const elements = document.querySelectorAll(selectors.join(','));
                const el = elements[{element_index}];
                if (!el) return {{ error: 'Element not found' }};

                const event = new MouseEvent('click', {{
                    view: window, bubbles: true, cancelable: true
                }});
                el.dispatchEvent(event);
                if (typeof el.click === 'function') el.click();

                return {{ success: true, tag: el.tagName.toLowerCase() }};
            }})();
            """
            result = self.evaluate_script(click_script, tab_index)
            if result and result.get('success'):
                print(f"✅ Clicked element successfully")
            else:
                print(f"❌ Failed to click element")

        elif action == 'type' and value is not None:
            type_script = f"""
            (function() {{
                const selectors = [
                    'input[type="text"]', 'input[type="email"]',
                    'input[type="password"]', 'input[type="number"]',
                    'input[type="tel"]', 'textarea', '[contenteditable="true"]'
                ];

                const elements = document.querySelectorAll(selectors.join(','));
                const el = elements[{element_index}];
                if (!el) return {{ error: 'Element not found' }};

                el.focus();
                el.value = `{value}`;
                el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                el.dispatchEvent(new Event('change', {{ bubbles: true }}));

                return {{ success: true, value: `{value}` }};
            }})();
            """
            result = self.evaluate_script(type_script, tab_index)
            if result and result.get('success'):
                print(f"✅ Typed '{value}' into element")
            else:
                print(f"❌ Failed to type into element")

        elif action == 'hover':
            hover_script = f"""
            (function() {{
                const selectors = [
                    'button', 'input[type="button"]', 'input[type="submit"]',
                    'input[type="reset"]', 'a[href]', '[role="button"]',
                    '[role="link"]', '[onclick]', '[data-action]', '.btn',
                    '[class*="button"]', '[class*="btn"]'
                ];

                const elements = document.querySelectorAll(selectors.join(','));
                const el = elements[{element_index}];
                if (!el) return {{ error: 'Element not found' }};

                const event = new MouseEvent('mouseover', {{
                    view: window, bubbles: true, cancelable: true
                }});
                el.dispatchEvent(event);

                return {{ success: true }};
            }})();
            """
            result = self.evaluate_script(hover_script, tab_index)
            if result and result.get('success'):
                print(f"✅ Hovered over element")
            else:
                print(f"❌ Failed to hover over element")

        # Save interaction to session
        if result:
            interaction_data = {
                'element_index': element_index,
                'action': action,
                'value': value,
                'result': result,
                'verification': verify_result
            }
            context = {
                'action': action,
                'element_info': verify_result
            }
            self.session.save_interaction(interaction_data, context)

        return result

    def generate_interaction_iife(self, tab_index: int = 0, indices: List[int] = None,
                                 output_file: str = None) -> str:
        """Generate a safe IIFE script for specified elements - PRESERVED"""
        if not indices:
            # If no indices, find all interactive elements
            elements = self.find_interactive_elements(tab_index)
            if not elements:
                print("❌ No interactive elements found")
                return ""
            indices = list(range(len(elements)))

        print(f"\n📜 Generating IIFE Script for {len(indices)} elements...")

        # Get element details for better script generation
        elements = self.find_interactive_elements(tab_index)

        script_lines = [
            "// Generated IIFE Script for Element Interaction",
            "// =============================================",
            f"// Session: {self.session.session_id}",
            f"// Timestamp: {datetime.now().isoformat()}",
            f"// Tab: {self.session.metadata.tab_url}",
            f"// Port: {self.port}",
            "// =============================================",
            "",
            "(function() {",
            "    const results = [];",
            "    const selectors = [",
            "        'button', 'input[type=\"button\"]', 'input[type=\"submit\"]',",
            "        'input[type=\"reset\"]', 'a[href]', '[role=\"button\"]',",
            "        '[role=\"link\"]', '[onclick]', '[data-action]', '.btn',",
            "        '[class*=\"button\"]', '[class*=\"btn\"]', '[data-testid*=\"button\"]'",
            "    ];",
            "",
            "    const elements = document.querySelectorAll(selectors.join(','));",
            "    const delay = ms => new Promise(resolve => setTimeout(resolve, ms));",
            "",
            "    async function clickElement(el, index) {",
            "        try {",
            "            if (!el) return { success: false, index, error: 'Element not found' };",
            "            el.scrollIntoView({ behavior: 'smooth', block: 'center' });",
            "            await delay(100);",
            "            try {",
            "                const clickEvent = new MouseEvent('click', {",
            "                    view: window, bubbles: true, cancelable: true",
            "                });",
            "                el.dispatchEvent(clickEvent);",
            "            } catch(e) {}",
            "            try {",
            "                if (typeof el.click === 'function') el.click();",
            "            } catch(e) {}",
            "            return { success: true, index, tag: el.tagName.toLowerCase() };",
            "        } catch(e) {",
            "            return { success: false, index, error: e.message };",
            "        }",
            "    }",
            "",
            "    async function execute() {",
        ]

        for idx in indices:
            elem = elements[idx] if idx < len(elements) else None
            elem_text = elem.get('text', '')[:30] if elem else 'unknown'
            script_lines.append(f"        // Element {idx}: {elem_text}")
            script_lines.append(f"        const result_{idx} = await clickElement(elements[{idx}], {idx});")
            script_lines.append(f"        results.push(result_{idx});")
            script_lines.append(f"        await delay(300);")
            script_lines.append("")

        script_lines.extend([
            "        return results;",
            "    }",
            "",
            "    return execute();",
            "})();"
        ])

        full_script = "\n".join(script_lines)

        # Save the generated script
        context = {
            'element_indices': indices,
            'script_type': 'interaction_iife',
            'element_count': len(indices)
        }
        self.session.save_script(full_script, "javascript", context)

        # Save to specified output file if provided
        if output_file:
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w') as f:
                f.write(full_script)
            print(f"💾 Script saved to: {output_path}")

        return full_script

    # ============================================================
    # EXISTING INTERACTIVE ELEMENT EXPLORER - PRESERVED
    # ============================================================

    def interactive_element_explorer(self, tab_index: int = 0):
        """Interactive element explorer with better control - PRESERVED"""
        print("\n🎯 Interactive Elements Explorer")
        print("-" * 60)

        elements = self.find_interactive_elements(tab_index)
        if not elements:
            print("❌ No interactive elements found")
            return

        page_size = 10
        total_pages = (len(elements) + page_size - 1) // page_size
        current_page = 0
        selected_indices = []

        while True:
            start = current_page * page_size
            end = min(start + page_size, len(elements))

            print(f"\n📋 Elements (Page {current_page+1}/{total_pages}):")
            print("=" * 70)
            for i in range(start, end):
                elem = elements[i]
                text = elem.get('text', '')[:40]
                tag = elem.get('tag', 'unknown')
                visible = "👁️" if elem.get('visible') else "🚫"
                handler = "⚡" if elem.get('hasClickHandler') else "  "
                print(f"  [{i:2d}] {handler} {visible} {tag:10s}: {text}")
                if elem.get('attributes'):
                    attrs = elem.get('attributes', {})
                    if 'id' in attrs:
                        print(f"        ID: {attrs['id']}")
                    if 'class' in attrs:
                        print(f"        Class: {attrs['class'][:40]}")
                    if 'data-testid' in attrs:
                        print(f"        Data-testid: {attrs['data-testid']}")

            print("\n📌 Commands:")
            print("  [n] Next page  [p] Previous page  [q] Quit")
            print("  [index] Interact with element")
            print("  [index1,index2] Multiple indices (comma-separated)")
            print("  [range] e.g., 5-10 for a range")
            print("  [all] All elements in current page")
            print("  [s] Session report")
            print("  [g] Generate IIFE script")
            print("  [a] Accessibility Analysis")
            print("  [r] Regex extraction")
            print("  [x] XPath query")
            print("  [c] CSS selector test")
            print("  [sem] Semantic extraction")
            cmd = input("\nEnter command: ").strip()

            if cmd.lower() == 'q':
                break
            elif cmd.lower() == 's':
                report = self.session.generate_report()
                print("\n" + report)
            elif cmd.lower() == 'a':
                ax_data = self.get_comprehensive_ax_tree(tab_index)
                if ax_data and "error" not in ax_data:
                    self.display_ax_tree_chart(ax_data)
            elif cmd.lower() == 'r':
                # NEW: Regex extraction
                patterns_input = input("Patterns (comma-separated, or 'all' for all): ").strip()
                if patterns_input.lower() == 'all':
                    patterns = None
                else:
                    patterns = [p.strip() for p in patterns_input.split(',') if p.strip()]
                result = self.extract_regex_from_page(tab_index, patterns)
                if result and 'patterns' in result:
                    print(f"\n🔍 Regex Results:")
                    for pattern, matches in result['patterns'].items():
                        print(f"  {pattern}: {len(matches)} matches")
                        if matches:
                            print(f"    Sample: {matches[:3]}")
            elif cmd.lower() == 'x':
                # NEW: XPath query
                xpath = input("XPath expression: ").strip()
                if xpath:
                    result = self.query_xpath(tab_index, xpath)
                    if result and result.get('count', 0) > 0:
                        print(f"\n🌳 XPath Results ({result['count']} matches):")
                        for i, match in enumerate(result['matches'][:10]):
                            if match.get('type') == 'element':
                                tag = match.get('tag', 'unknown')
                                text = match.get('text', '')[:50]
                                print(f"  [{i}] {tag}: {text}")
                    elif result and 'error' in result:
                        print(f"❌ {result['error']}")
            elif cmd.lower() == 'c':
                # NEW: CSS selector test
                selector = input("CSS selector: ").strip()
                if selector:
                    result = self.test_css_selector(tab_index, selector)
                    if result and result.get('valid'):
                        print(f"\n🎯 CSS Results ({result['match_count']} matches):")
                        for i, match in enumerate(result['matches'][:10]):
                            tag = match.get('tag', 'unknown')
                            text = match.get('text', '')[:50]
                            print(f"  [{i}] {tag}: {text}")
                    elif result and 'error' in result:
                        print(f"❌ {result['error']}")
            elif cmd.lower() == 'sem':
                # NEW: Semantic extraction
                result = self.extract_semantic_data(tab_index)
                if result and 'statistics' in result:
                    stats = result['statistics']
                    print(f"\n🧠 Semantic Data Extracted:")
                    print(f"  JSON-LD blocks: {stats.get('json_ld_blocks', 0)}")
                    print(f"  RDFa triples: {stats.get('rdfa_triples', 0)}")
                    print(f"  Microdata items: {stats.get('microdata_items', 0)}")
                    print(f"  Total triples: {stats.get('total_triples', 0)}")
            elif cmd.lower() == 'g':
                print("\n🎯 Generate IIFE Script")
                print("Options:")
                print("  [all] All elements")
                print("  [visible] Visible elements only")
                print("  [interactive] Elements with click handlers")
                print("  [current] Elements on current page")
                choice = input("Select option: ").strip().lower()

                if choice == 'all':
                    indices = list(range(len(elements)))
                elif choice == 'visible':
                    indices = [i for i, e in enumerate(elements) if e.get('visible')]
                elif choice == 'interactive':
                    indices = [i for i, e in enumerate(elements) if e.get('hasClickHandler')]
                elif choice == 'current':
                    indices = list(range(start, end))
                else:
                    print("Invalid option, using current page")
                    indices = list(range(start, end))

                if indices:
                    script = self.generate_interaction_iife(tab_index, indices)
                    print("\n✅ IIFE Script Generated!")
                    print("=" * 60)
                    print(script[:500] + "..." if len(script) > 500 else script)
                    print("=" * 60)

                    execute = input("\n🔧 Execute this script? (y/n): ").strip().lower()
                    if execute == 'y':
                        print("\n⚡ Executing script...")
                        result = self.evaluate_script(script, tab_index, await_promise=True)
                        if result:
                            print(f"\n📊 Execution Results:")
                            if isinstance(result, list):
                                for res in result:
                                    if res.get('success'):
                                        print(f"  ✅ Element {res.get('index')}: Clicked ({res.get('tag')})")
                                    else:
                                        print(f"  ❌ Element {res.get('index')}: {res.get('error')}")
                            else:
                                print(f"Result: {result}")
                        else:
                            print("❌ Script execution failed")
            elif cmd.lower() == 'n' and current_page < total_pages - 1:
                current_page += 1
            elif cmd.lower() == 'p' and current_page > 0:
                current_page -= 1
            elif cmd.lower() == 'all':
                selected_indices = list(range(start, end))
                print(f"✅ Selected {len(selected_indices)} elements on this page")
                self._handle_batch_actions(tab_index, selected_indices)
            elif '-' in cmd:
                try:
                    parts = cmd.split('-')
                    if len(parts) == 2:
                        start_idx = int(parts[0].strip())
                        end_idx = int(parts[1].strip())
                        if 0 <= start_idx < len(elements) and 0 <= end_idx < len(elements):
                            selected_indices = list(range(start_idx, end_idx + 1))
                            print(f"✅ Selected elements {start_idx}-{end_idx} ({len(selected_indices)} elements)")
                            self._handle_batch_actions(tab_index, selected_indices)
                except Exception as e:
                    print(f"❌ Invalid range: {e}")
            elif ',' in cmd:
                try:
                    indices = [int(x.strip()) for x in cmd.split(',')]
                    selected_indices = [i for i in indices if 0 <= i < len(elements)]
                    if selected_indices:
                        print(f"✅ Selected {len(selected_indices)} elements: {selected_indices}")
                        self._handle_batch_actions(tab_index, selected_indices)
                except Exception as e:
                    print(f"❌ Invalid indices: {e}")
            elif cmd.isdigit():
                elem_index = int(cmd)
                if 0 <= elem_index < len(elements):
                    self.interactive_element_menu(tab_index, elem_index)
                else:
                    print("❌ Invalid index")
            else:
                print("❌ Invalid command")

    def _handle_batch_actions(self, tab_index: int, indices: List[int]):
        """Handle batch actions on multiple elements - PRESERVED"""
        print("\n🎮 What to do with selected elements?")
        print("  1. Click all (with delay)")
        print("  2. Get info for all")
        print("  3. Generate IIFE script")
        print("  4. Generate and execute script")
        print("  5. Cancel")
        action = input("Select action: ").strip()

        if action == '1':
            delay = float(input("Delay between clicks (seconds, default 0.5): ").strip() or "0.5")
            for idx in indices:
                print(f"\n--- Clicking element {idx} ---")
                self.interact_with_element(tab_index, idx, 'click', delay=delay)
                time.sleep(delay)
        elif action == '2':
            for idx in indices:
                print(f"\n--- Info for element {idx} ---")
                self.get_element_info(tab_index, idx)
        elif action == '3':
            self.generate_interaction_iife(tab_index, indices)
        elif action == '4':
            script = self.generate_interaction_iife(tab_index, indices)
            if script:
                print("\n⚡ Executing script...")
                result = self.evaluate_script(script, tab_index, await_promise=True)
                if result:
                    print(f"\n📊 Execution Results:")
                    if isinstance(result, list):
                        for res in result:
                            if res.get('success'):
                                print(f"  ✅ Element {res.get('index')}: Clicked ({res.get('tag')})")
                            else:
                                print(f"  ❌ Element {res.get('index')}: {res.get('error')}")
                    else:
                        print(f"Result: {result}")
                else:
                    print("❌ Script execution failed")

    def interactive_element_menu(self, tab_index: int = 0, element_index: int = 0):
        """Interactive menu for a single element - PRESERVED"""
        while True:
            print(f"\n🎮 Interacting with element {element_index}")
            print("  1. Click")
            print("  2. Type text")
            print("  3. Hover")
            print("  4. Get detailed info")
            print("  5. Generate script for this element")
            print("  6. Back to explorer")

            action = input("Select action: ").strip()

            if action == '1':
                self.interact_with_element(tab_index, element_index, 'click')
                print("\nPress Enter to continue...")
                input()
            elif action == '2':
                text = input("📝 Enter text to type: ")
                self.interact_with_element(tab_index, element_index, 'type', text)
                print("\nPress Enter to continue...")
                input()
            elif action == '3':
                self.interact_with_element(tab_index, element_index, 'hover')
                print("\nPress Enter to continue...")
                input()
            elif action == '4':
                self.get_element_info(tab_index, element_index)
                print("\nPress Enter to continue...")
                input()
            elif action == '5':
                self.generate_interaction_iife(tab_index, [element_index])
                print("\nPress Enter to continue...")
                input()
            elif action == '6':
                break
            else:
                print("❌ Invalid choice")

    def get_element_info(self, tab_index: int = 0, element_index: int = 0) -> Optional[Dict]:
        """Get detailed information about an element - PRESERVED"""
        print(f"\n📋 Getting detailed info for element {element_index}...")

        info_script = f"""
        (function() {{
            const selectors = [
                'button', 'input[type="button"]', 'input[type="submit"]',
                'input[type="reset"]', 'a[href]', '[role="button"]',
                '[role="link"]', '[onclick]', '[data-action]', '.btn',
                '[class*="button"]', '[class*="btn"]'
            ];

            const elements = document.querySelectorAll(selectors.join(','));
            const el = elements[{element_index}];
            if (!el) return {{ error: 'Element not found' }};

            const rect = el.getBoundingClientRect();
            const style = window.getComputedStyle(el);

            return {{
                tag: el.tagName.toLowerCase(),
                text: el.textContent.trim().substring(0, 200),
                innerHTML: el.innerHTML.substring(0, 200),
                visible: rect.width > 0 && rect.height > 0,
                rect: {{
                    x: Math.round(rect.x), y: Math.round(rect.y),
                    width: Math.round(rect.width), height: Math.round(rect.height)
                }},
                style: {{
                    color: style.color, backgroundColor: style.backgroundColor,
                    fontSize: style.fontSize, fontFamily: style.fontFamily,
                    display: style.display, visibility: style.visibility,
                    opacity: style.opacity, cursor: style.cursor,
                    pointerEvents: style.pointerEvents
                }},
                attributes: {{
                    id: el.id || null, class: el.className || null,
                    role: el.getAttribute('role'),
                    'aria-label': el.getAttribute('aria-label'),
                    type: el.getAttribute('type'), value: el.value || null,
                    href: el.getAttribute('href'), target: el.getAttribute('target'),
                    disabled: el.disabled || false, readonly: el.readOnly || false
                }},
                onClickHandler: typeof el.onclick === 'function',
                isFormElement: ['input', 'textarea', 'select', 'button'].includes(el.tagName.toLowerCase()),
                isLink: el.tagName.toLowerCase() === 'a' && el.hasAttribute('href')
            }};
        }})();
        """

        result = self.evaluate_script(info_script, tab_index)
        if result and 'error' not in result:
            print("\n📋 Element Details:")
            print("=" * 60)
            for key, value in result.items():
                if isinstance(value, dict):
                    print(f"{key}:")
                    for subkey, subvalue in value.items():
                        print(f"  {subkey}: {subvalue}")
                else:
                    print(f"{key}: {value}")
            print("=" * 60)
            return result
        else:
            print(f"❌ Failed to get info: {result.get('error', 'Unknown error')}")
            return None

    def extract_semantic_elements(self, tab_index: int = 0) -> List[Dict]:
        """Extract semantic elements with role, name, and properties - PRESERVED"""
        print("\n🔍 Extracting semantic elements...")

        js_script = """
        (function() {
            const elements = [];

            // Get all elements with ARIA roles or semantic tags
            const allElements = document.querySelectorAll('*');
            const semanticTags = ['header', 'nav', 'main', 'article', 'section',
                                 'aside', 'footer', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
                                 'button', 'a', 'input', 'select', 'textarea', 'form',
                                 'table', 'ul', 'ol', 'dl', 'figure', 'figcaption'];

            allElements.forEach(el => {
                let role = el.getAttribute('role');
                let tag = el.tagName.toLowerCase();

                // Determine role
                if (!role && semanticTags.includes(tag)) {
                    role = tag;
                }
                if (!role) return;

                // Get name
                let name = '';
                if (el.hasAttribute('aria-label')) {
                    name = el.getAttribute('aria-label');
                } else if (el.hasAttribute('aria-labelledby')) {
                    const labelId = el.getAttribute('aria-labelledby');
                    const labelEl = document.getElementById(labelId);
                    if (labelEl) name = labelEl.textContent.trim();
                } else if (el.hasAttribute('title')) {
                    name = el.getAttribute('title');
                } else if (tag === 'button' || tag === 'a') {
                    name = el.textContent.trim();
                } else if (tag === 'input') {
                    name = el.getAttribute('placeholder') || el.getAttribute('value') || '';
                }

                // Check visibility
                const rect = el.getBoundingClientRect();
                const visible = rect.width > 0 && rect.height > 0 &&
                               window.getComputedStyle(el).display !== 'none' &&
                               window.getComputedStyle(el).visibility !== 'hidden';

                elements.push({
                    role: role,
                    name: name.substring(0, 200),
                    tag: tag,
                    visible: visible,
                    id: el.id || '',
                    className: el.className || '',
                    selector: el.id ? '#' + el.id : null,
                    hasChildren: el.children.length > 0,
                    isInteractive: ['button', 'a', 'input', 'select', 'textarea'].includes(tag)
                });
            });

            return elements;
        })();
        """

        result = self.evaluate_script(js_script, tab_index)
        if result and isinstance(result, list):
            print(f"✅ Extracted {len(result)} semantic elements")
            return result
        return []

    def list_tabs(self):
        """Display all available tabs - PRESERVED"""
        self.get_tabs()

        if not self.tabs:
            print("❌ No tabs found")
            return

        print("\n📑 Available Tabs:")
        print("=" * 60)
        for i, tab in enumerate(self.tabs):
            title = tab.get('title', 'Untitled')[:50]
            url = tab.get('url', '')[:50]
            ws_url = tab.get('webSocketDebuggerUrl', 'No WebSocket')
            print(f"  [{i}] {title}")
            print(f"      URL: {url}")
            print(f"      WS: {ws_url[:60] if ws_url else 'None'}...")
            print()

    def close_session(self):
        """Close the current session properly - PRESERVED"""
        self.session.close()


# ============================================================
# MAIN - EXTENDED CLI
# ============================================================

def main():
    print("🚀 Enhanced Chrome CDP Controller - With Advanced Extraction Modules")
    print("=" * 60)
    print("Features: Auto-save, Session tracking, Regex, XPath, CSS, Semantic")
    print("=" * 60)

    port_input = input("🔌 Chrome debug port (default 9227): ").strip()
    port = int(port_input) if port_input else 9227

    session_dir = input("📁 Session directory (default: current): ").strip()
    if not session_dir:
        session_dir = "."

    chrome = EnhancedChromeCDP(port, session_dir)

    print(f"\n📡 Connecting to Chrome on port {port}...")
    print(f"📁 Session ID: {chrome.session.session_id}")
    print(f"📂 Session directory: {chrome.session.session_dir}")

    tabs = chrome.get_tabs()

    if not tabs:
        print("❌ No tabs found. Make sure Chrome is running with:")
        print(f"   chromium-browser --remote-debugging-port={port}")
        return

    print(f"✅ Found {len(tabs)} tabs")
    chrome.list_tabs()

    tab_input = input(f"\n📑 Select tab (0-{len(tabs)-1}, default 0): ").strip()
    tab_index = int(tab_input) if tab_input else 0

    while True:
        print("\n" + "=" * 60)
        print(f"📁 Session: {chrome.session.session_id}")
        print(f"📊 Commands: {chrome.session.metadata.total_commands}")
        print(f"🔌 Port: {port}")
        print("=" * 60)
        print("📝 CDP Commands:")
        print("  1. Execute JavaScript (Runtime.evaluate)")
        print("  2. Get DOM Tree (DOM.getDocument) - Auto-save ✅")
        print("  3. Get DOM Snapshot (DOMSnapshot.getSnapshot) - Auto-save ✅")
        print("  4. Get Accessibility Tree - Auto-save ✅")
        print("  5. Comprehensive AX Tree with Chart 📊")
        print("  6. Complete Page Analysis (All Domains)")
        print("  7. Extract Semantic Elements")
        print("  8. Get Computed Styles - Auto-save ✅")
        print("  9. List Tabs")
        print(" 10. Change Tab")
        print(" 11. Interactive Element Explorer 🎯")
        print(" 12. Generate Custom Interaction Script")
        print(" 13. Execute Script from File 📄")
        print(" 14. View Session Report 📊")
        print(" 15. Export Session Data 📦")
        print(" 16. Toggle Auto-Save 🔄")
        print(" 17. Regex Extraction 🔍")
        print(" 18. XPath Query 🌳")
        print(" 19. CSS Selector Test 🎯")
        print(" 20. Semantic Extraction 🧠")
        print("  0. Exit & Close Session")
        print("=" * 60)

        choice = input("Select option: ").strip()

        if choice == "0":
            print("👋 Closing session...")
            chrome.close_session()
            print("Goodbye!")
            break

        elif choice == "1":
            print("\n📝 Enter JavaScript (type 'END' on a new line when done):")
            lines = []
            while True:
                line = input()
                if line.strip() == "END":
                    break
                lines.append(line)
            script = "\n".join(lines)

            if script:
                result = chrome.evaluate_script(script, tab_index)
                if result is not None:
                    print(f"\n✅ Result: {json.dumps(result, indent=2, default=str)[:3000]}")
                else:
                    print("\n❌ No result returned")

        elif choice == "2":
            dom_root = chrome.get_document(tab_index)
            if dom_root:
                node_count = chrome._count_nodes(dom_root)
                print(f"\n📊 DOM Statistics:")
                print(f"   Total nodes: {node_count}")
                print(f"   Root node: {dom_root.get('nodeName')} (ID: {dom_root.get('nodeId')})")

        elif choice == "3":
            snapshot = chrome.get_dom_snapshot(tab_index)
            if snapshot:
                print(f"\n📊 Snapshot Statistics:")
                print(f"   DOM nodes: {len(snapshot.dom_nodes)}")
                print(f"   Layout tree: {len(snapshot.layout_tree)}")
                print(f"   Computed styles: {len(snapshot.computed_styles)}")

        elif choice == "4":
            ax_tree = chrome.get_accessibility_tree(tab_index)
            if ax_tree:
                nodes = ax_tree.get('nodes', [])
                print(f"\n📊 Accessibility Statistics:")
                print(f"   Total accessible nodes: {len(nodes)}")

        elif choice == "5":
            print("\n♿ Getting Comprehensive Accessibility Tree...")
            ax_data = chrome.get_comprehensive_ax_tree(tab_index)
            if ax_data and "error" not in ax_data:
                chrome.display_ax_tree_chart(ax_data)

        elif choice == "6":
            print("\n🔬 Performing complete page analysis...")
            analysis = chrome.analyze_page_structure(tab_index)
            print(f"\n📊 Analysis Summary:")
            for key, value in analysis.get('metadata', {}).items():
                print(f"   {key}: {value}")

        elif choice == "7":
            elements = chrome.extract_semantic_elements(tab_index)
            if elements:
                print(f"✅ Found {len(elements)} semantic elements:")
                for elem in elements[:20]:
                    name = elem['name'][:50] if elem['name'] else '(unnamed)'
                    print(f"   [{elem['role']}] {name}")

        elif choice == "8":
            styles = chrome.get_computed_styles(tab_index)
            if styles:
                print(f"✅ Retrieved {len(styles)} computed styles (showing first 20):")
                for style in styles[:20]:
                    name = style.get('name', '')
                    value = style.get('value', '')[:50]
                    print(f"   {name}: {value}")

        elif choice == "9":
            chrome.list_tabs()

        elif choice == "10":
            chrome.tabs = []
            chrome.ws_url = None
            chrome._dom_enabled = False
            chrome._css_enabled = False
            chrome._ax_enabled = False
            chrome.list_tabs()
            tab_input = input(f"\n📑 Select tab (0-{len(chrome.tabs)-1}): ").strip()
            if tab_input:
                tab_index = int(tab_input)
                ws_url = chrome.get_websocket_url(tab_index)
                if ws_url:
                    print(f"✅ Switched to tab {tab_index}")

        elif choice == "11":
            chrome.interactive_element_explorer(tab_index)

        elif choice == "12":
            print("\n🚀 Generate Custom Interaction Script")
            print("-" * 60)

            elements = chrome.find_interactive_elements(tab_index)
            if not elements:
                print("❌ No interactive elements found")
                continue

            print("\n📋 Available elements:")
            for i, elem in enumerate(elements[:20]):
                text = elem.get('text', '')[:40]
                tag = elem.get('tag', 'unknown')
                handler = "⚡" if elem.get('hasClickHandler') else "  "
                print(f"  [{i:2d}] {handler} {tag:10s}: {text}")

            print("\n📌 Enter element indices (comma-separated, range, or 'all'):")
            indices_input = input("Indices: ").strip()

            selected_indices = []
            if indices_input.lower() == 'all':
                selected_indices = list(range(len(elements)))
            elif '-' in indices_input:
                try:
                    parts = indices_input.split('-')
                    if len(parts) == 2:
                        start = int(parts[0].strip())
                        end = int(parts[1].strip())
                        selected_indices = list(range(start, end + 1))
                except:
                    print("❌ Invalid range format")
                    continue
            else:
                try:
                    selected_indices = [int(x.strip()) for x in indices_input.split(',') if x.strip()]
                except:
                    print("❌ Invalid indices format")
                    continue

            selected_indices = [i for i in selected_indices if 0 <= i < len(elements)]
            if selected_indices:
                print(f"\n✅ Selected {len(selected_indices)} elements")
                script = chrome.generate_interaction_iife(tab_index, selected_indices)
                if script:
                    print("\n📜 Generated Script (first 500 chars):")
                    print("=" * 60)
                    print(script[:500] + "..." if len(script) > 500 else script)
                    print("=" * 60)

                    # Offer to execute
                    execute = input("\n🔧 Execute this script? (y/n): ").strip().lower()
                    if execute == 'y':
                        print("\n⚡ Executing script...")
                        result = chrome.evaluate_script(script, tab_index, await_promise=True)
                        if result:
                            print(f"\n📊 Execution Results:")
                            if isinstance(result, list):
                                for res in result:
                                    if res.get('success'):
                                        print(f"  ✅ Element {res.get('index')}: Clicked ({res.get('tag')})")
                                    else:
                                        print(f"  ❌ Element {res.get('index')}: {res.get('error')}")
                            else:
                                print(f"Result: {result}")
                        else:
                            print("❌ Script execution failed")

        elif choice == "13":
            script_path = input("📄 Enter script file path: ").strip()
            if script_path:
                result = chrome.execute_script_from_file(script_path, tab_index)
                if result is not None:
                    print(f"\n✅ Script Result: {json.dumps(result, indent=2, default=str)[:3000]}")
                else:
                    print("\n❌ Script execution failed")

        elif choice == "14":
            report = chrome.session.generate_report()
            print("\n" + report)

        elif choice == "15":
            export_file = chrome.session.export_session()
            print(f"📦 Session exported to: {export_file}")

        elif choice == "16":
            chrome.auto_save = not chrome.auto_save
            status = "ON" if chrome.auto_save else "OFF"
            print(f"🔄 Auto-save is now {status}")

        # NEW: Regex extraction
        elif choice == "17":
            print("\n🔍 Regex Extraction")
            print("-" * 60)
            print("Available patterns: EMAIL, URL, IP_V4, IP_V6, PHONE, UUID,")
            print("  DATE_ISO, TIME_24H, CREDIT_CARD, MAC_ADDRESS, DOMAIN, HEX_COLOR")
            print("  (Enter 'all' for all patterns, comma-separated for specific)")

            patterns_input = input("Patterns: ").strip()
            if patterns_input.lower() == 'all':
                patterns = None
            else:
                patterns = [p.strip() for p in patterns_input.split(',') if p.strip()]

            if not patterns:
                patterns = ['EMAIL', 'URL', 'PHONE', 'UUID']

            result = chrome.extract_regex_from_page(tab_index, patterns)
            if result and 'patterns' in result:
                print(f"\n📊 Regex Extraction Results:")
                print(f"  Total matches: {result.get('total_matches', 0)}")
                print(f"  Patterns used: {len(result.get('patterns', {}))}")

                for pattern, matches in result['patterns'].items():
                    if matches:
                        print(f"\n  {pattern}: {len(matches)} matches")
                        for i, match in enumerate(matches[:10]):
                            print(f"    [{i}] {match}")
                        if len(matches) > 10:
                            print(f"    ... and {len(matches) - 10} more")

        # NEW: XPath query
        elif choice == "18":
            print("\n🌳 XPath Query")
            print("-" * 60)
            print("Enter XPath expression (e.g., //div[@id='main']//button)")
            xpath = input("XPath: ").strip()

            if xpath:
                result = chrome.query_xpath(tab_index, xpath)
                if result:
                    if result.get('error'):
                        print(f"❌ Error: {result['error']}")
                    else:
                        print(f"\n📊 XPath Results:")
                        print(f"  Matches: {result.get('count', 0)}")
                        print(f"  Duration: {result.get('duration_ms', 0):.2f}ms")

                        for i, match in enumerate(result.get('matches', [])[:20]):
                            if match.get('type') == 'element':
                                tag = match.get('tag', 'unknown')
                                text = match.get('text', '')[:60]
                                print(f"  [{i}] {tag}: {text}")
                            else:
                                print(f"  [{i}] {match.get('type', 'unknown')}: {match.get('value', '')[:60]}")

                        if result.get('count', 0) > 20:
                            print(f"  ... and {result['count'] - 20} more")

        # NEW: CSS selector test
        elif choice == "19":
            print("\n🎯 CSS Selector Test")
            print("-" * 60)
            print("Enter CSS selector (e.g., .product-card, #main button)")
            selector = input("Selector: ").strip()

            if selector:
                # Validate first
                is_valid = chrome.validate_css_selector(selector)
                if not is_valid:
                    print("❌ Invalid CSS selector syntax")
                    continue

                result = chrome.test_css_selector(tab_index, selector)
                if result:
                    if result.get('error'):
                        print(f"❌ Error: {result['error']}")
                    else:
                        print(f"\n📊 CSS Results:")
                        print(f"  Valid: {result.get('valid', False)}")
                        print(f"  Matches: {result.get('match_count', 0)}")
                        print(f"  Duration: {result.get('duration_ms', 0):.2f}ms")

                        for i, match in enumerate(result.get('matches', [])[:20]):
                            tag = match.get('tag', 'unknown')
                            text = match.get('text', '')[:60]
                            print(f"  [{i}] {tag}: {text}")

                        if result.get('match_count', 0) > 20:
                            print(f"  ... and {result['match_count'] - 20} more")

        # NEW: Semantic extraction
        elif choice == "20":
            print("\n🧠 Semantic Extraction")
            print("-" * 60)
            print("Extracting JSON-LD, RDFa, and Microdata...")

            semantic_data = chrome.extract_semantic_data(tab_index)

            if semantic_data and 'statistics' in semantic_data:
                stats = semantic_data['statistics']
                print(f"\n📊 Semantic Data Extracted:")
                print(f"  JSON-LD blocks: {stats.get('json_ld_blocks', 0)}")
                print(f"  RDFa triples: {stats.get('rdfa_triples', 0)}")
                print(f"  Microdata items: {stats.get('microdata_items', 0)}")
                print(f"  Total triples: {stats.get('total_triples', 0)}")
                print(f"  Extraction time: {stats.get('extraction_time_ms', 0):.2f}ms")

                # Show samples
                if semantic_data.get('json_ld'):
                    print(f"\n📋 Sample JSON-LD (first block):")
                    first = semantic_data['json_ld'][0]
                    print(f"  @type: {first.get('@type', 'N/A')}")
                    if '@id' in first:
                        print(f"  @id: {first['@id']}")
                    if 'name' in first:
                        print(f"  name: {first['name']}")

                if semantic_data.get('rdfa'):
                    print(f"\n📋 Sample RDFa (first triple):")
                    first = semantic_data['rdfa'][0]
                    print(f"  subject: {first.get('subject', 'N/A')[:60]}")
                    print(f"  predicate: {first.get('predicate', 'N/A')[:60]}")
                    print(f"  object: {first.get('object', 'N/A')[:60]}")

                if semantic_data.get('triples'):
                    print(f"\n📋 Sample RDF Triple (first):")
                    first = semantic_data['triples'][0]
                    print(f"  {first.get('subject', '')[:40]} → {first.get('predicate', '')[:40]} → {first.get('object', '')[:40]}")

                # Ask if user wants to see JSON-LD
                view_choice = input("\n🔍 View full JSON-LD? (y/n): ").strip().lower()
                if view_choice == 'y' and semantic_data.get('json_ld'):
                    print("\n📄 Full JSON-LD:")
                    print(json.dumps(semantic_data['json_ld'], indent=2)[:2000])
                    if len(json.dumps(semantic_data['json_ld'])) > 2000:
                        print("... (truncated)")

        else:
            print("❌ Invalid choice")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Interrupted. Closing session...")
        if 'chrome' in locals():
            chrome.close_session()
        print("Goodbye!")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        if 'chrome' in locals():
            chrome.close_session()
        sys.exit(1)
