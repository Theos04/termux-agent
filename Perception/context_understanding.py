#!/usr/bin/env python3
"""
Context Understanding - Extract meaning from page structure
"""

from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Set
import re
from collections import defaultdict


@dataclass
class JobListing:
    """Structured job listing data"""
    title: str = ""
    company: str = ""
    location: str = ""
    experience: str = ""
    salary: str = ""
    posted_date: str = ""
    description: str = ""
    apply_url: str = ""
    confidence: float = 0.0
    
    def to_dict(self) -> Dict:
        return {
            'title': self.title,
            'company': self.company,
            'location': self.location,
            'experience': self.experience,
            'salary': self.salary,
            'posted_date': self.posted_date,
            'description': self.description[:200],
            'apply_url': self.apply_url,
            'confidence': self.confidence
        }


@dataclass
class PageContext:
    """Overall page context"""
    page_type: str = "unknown"
    purpose: str = ""
    main_action: str = ""
    job_listings: List[Dict] = field(default_factory=list)
    key_companies: List[str] = field(default_factory=list)
    primary_actions: List[str] = field(default_factory=list)
    confidence: float = 0.0


class ContextAnalyzer:
    """Analyze context from DOM and Accessibility data"""
    
    JOB_KEYWORDS = {
        'title': ['job', 'position', 'role', 'opening', 'vacancy', 'hiring'],
        'company': ['company', 'firm', 'corporation', 'inc', 'ltd', 'llc'],
        'location': ['location', 'city', 'state', 'country', 'remote'],
        'salary': ['salary', 'compensation', 'pay', 'lacs', 'lakhs', 'pa'],
        'experience': ['experience', 'exp', 'years', 'yrs']
    }
    
    def __init__(self, dom_data: Dict, ax_data: Dict, snapshot_data: Dict = None):
        self.dom_data = dom_data
        self.ax_data = ax_data
        self.snapshot_data = snapshot_data
        
        # Import analyzers
        from dom_analysis import DomAnalyzer
        from accessibility_analysis import AccessibilityAnalyzer
        
        self.dom_analyzer = DomAnalyzer() if dom_data else None
        self.dom_stats = None
        self.ax_stats = None
        
        if dom_data:
            self.dom_stats = self.dom_analyzer.analyze(dom_data)
        
        if ax_data:
            ax_analyzer = AccessibilityAnalyzer()
            self.ax_stats = ax_analyzer.analyze(ax_data)
    
    def analyze(self) -> PageContext:
        """Complete context analysis"""
        context = PageContext()
        
        # 1. Determine page type
        context.page_type = self._determine_page_type()
        
        # 2. Extract job listings
        context.job_listings = self._extract_job_listings()
        
        # 3. Identify key companies
        context.key_companies = self._extract_companies()
        
        # 4. Find primary actions
        context.primary_actions = self._find_primary_actions()
        
        # 5. Determine purpose
        context.purpose = self._determine_purpose(context)
        
        # 6. Find main action
        context.main_action = self._find_main_action(context)
        
        # 7. Calculate confidence
        context.confidence = self._calculate_confidence(context)
        
        return context
    
    def _determine_page_type(self) -> str:
        """Determine page type from DOM stats"""
        if not self.dom_stats:
            return "unknown"
        
        # Check for job listing indicators
        if self._is_job_listing_page():
            return "job_listing"
        
        # Use DOM analyzer's page type
        return self.dom_stats.page_type.value
    
    def _is_job_listing_page(self) -> bool:
        """Check if page is a job listing"""
        if not self.ax_stats:
            return False
        
        # Look for job-related elements in AX
        for heading in self.ax_stats.headings:
            name = heading.get('name', '').lower()
            if any(kw in name for kw in ['job', 'position', 'career']):
                return True
        
        # Check for "View jobs" buttons
        for btn in self.ax_stats.buttons:
            name = btn.get('name', '').lower()
            if 'view jobs' in name or 'apply' in name:
                return True
        
        # Check form fields for job-related labels
        for field in self.ax_stats.form_fields:
            name = field.get('name', '').lower()
            if any(kw in name for kw in ['job title', 'position', 'role']):
                return True
        
        return False
    
    def _extract_job_listings(self) -> List[Dict]:
        """Extract job listings from page"""
        listings = []
        
        if not self.ax_stats:
            return listings
        
        # Look for job-related headings and their parent containers
        job_headings = []
        for heading in self.ax_stats.headings:
            name = heading.get('name', '').lower()
            if any(kw in name for kw in ['job', 'position', 'role', 'hiring']):
                job_headings.append(heading)
        
        # For each job heading, look for related buttons and fields
        for heading in job_headings:
            listing = JobListing()
            listing.title = heading.get('name', '')
            listing.confidence = 0.5
            
            # Look for "View jobs" or "Apply" buttons nearby
            for btn in self.ax_stats.buttons:
                btn_name = btn.get('name', '').lower()
                if 'view' in btn_name and ('job' in btn_name or 'detail' in btn_name):
                    listing.apply_url = btn.get('node_id', '')
                    listing.confidence += 0.2
                elif 'apply' in btn_name:
                    listing.apply_url = btn.get('node_id', '')
                    listing.confidence += 0.3
            
            # Try to extract company from context
            for link in self.ax_stats.links:
                link_name = link.get('name', '')
                # Common company patterns
                if any(indicator in link_name for indicator in ['Inc', 'Ltd', 'LLC', 'Corp']):
                    listing.company = link_name
                    listing.confidence += 0.2
                    break
            
            # Limit confidence
            listing.confidence = min(1.0, listing.confidence)
            
            if listing.title:
                listings.append(listing.to_dict())
        
        return listings[:10]  # Limit to 10 listings
    
    def _extract_companies(self) -> List[str]:
        """Extract company names from page"""
        companies = set()
        
        if not self.ax_stats:
            return []
        
        # Look for company names in links and headings
        for link in self.ax_stats.links:
            name = link.get('name', '')
            # Pattern: CompanyName (position)
            match = re.search(r'^([A-Z][a-zA-Z0-9\s&.]+)\s*(?:\(|$)', name)
            if match:
                companies.add(match.group(1).strip())
        
        # Look for company indicators
        for btn in self.ax_stats.buttons:
            name = btn.get('name', '')
            if any(indicator in name for indicator in ['Inc', 'Ltd', 'LLC', 'Corp']):
                companies.add(name)
        
        return list(companies)[:10]  # Return top 10
    
    def _find_primary_actions(self) -> List[str]:
        """Find primary actions on page"""
        actions = []
        
        if not self.ax_stats:
            return actions
        
        # Get button names
        for btn in self.ax_stats.buttons:
            name = btn.get('name', '')
            if name and len(name) < 50:  # Reasonable button text
                actions.append(name)
        
        # Prioritize certain actions
        priority_keywords = ['apply', 'submit', 'search', 'view', 'sign', 'login']
        priority_actions = []
        other_actions = []
        
        for action in actions:
            action_lower = action.lower()
            if any(kw in action_lower for kw in priority_keywords):
                priority_actions.append(action)
            else:
                other_actions.append(action)
        
        return priority_actions + other_actions[:5]  # Return priority first
    
    def _determine_purpose(self, context: PageContext) -> str:
        """Determine page purpose"""
        if context.page_type == "job_listing":
            return "Browse and apply for job opportunities"
        
        if context.primary_actions:
            first_action = context.primary_actions[0].lower()
            if 'apply' in first_action or 'submit' in first_action:
                return "Submit information"
            elif 'search' in first_action:
                return "Search for content"
            elif 'view' in first_action:
                return "View content"
            elif 'login' in first_action or 'sign' in first_action:
                return "Authenticate user"
        
        return "Generic content browsing"
    
    def _find_main_action(self, context: PageContext) -> str:
        """Find the main action for the page"""
        # Look for primary action in AX stats
        if self.ax_stats:
            for btn in self.ax_stats.buttons:
                name = btn.get('name', '').lower()
                if 'apply' in name or 'submit' in name:
                    return f"Click '{btn.get('name')}'"
        
        # Return first action if available
        if context.primary_actions:
            return f"Click '{context.primary_actions[0]}'"
        
        return "Explore page content"
    
    def _calculate_confidence(self, context: PageContext) -> float:
        """Calculate confidence in the analysis"""
        confidence = 0.3  # Base confidence
        
        # Boost for AX stats
        if self.ax_stats:
            confidence += 0.1
            if self.ax_stats.total_nodes > 50:
                confidence += 0.1
            if self.ax_stats.has_meaningful_structure:
                confidence += 0.15
        
        # Boost for job listings
        if context.job_listings:
            confidence += 0.15
            if len(context.job_listings) > 3:
                confidence += 0.1
        
        # Boost for company extraction
        if context.key_companies:
            confidence += 0.1
        
        return min(1.0, confidence)


# === Usage ===

def analyze_context(dom_data: Dict, ax_data: Dict) -> Dict:
    """Quick context analysis"""
    analyzer = ContextAnalyzer(dom_data, ax_data)
    context = analyzer.analyze()
    
    return {
        'page_type': context.page_type,
        'purpose': context.purpose,
        'main_action': context.main_action,
        'confidence': context.confidence,
        'job_listings_count': len(context.job_listings),
        'job_listings': context.job_listings[:3],
        'key_companies': context.key_companies[:5],
        'primary_actions': context.primary_actions[:5]
    }


if __name__ == "__main__":
    # This would normally use real data, but we'll show the structure
    print("=" * 50)
    print("CONTEXT UNDERSTANDING MODULE")
    print("=" * 50)
    print("\n📋 Module ready for integration with real DOM/AX data")
    print("   Usage: analyzer = ContextAnalyzer(dom_data, ax_data)")
    print("   context = analyzer.analyze()")
