#!/usr/bin/env python3
"""
Accessibility Analysis - Understanding roles and semantics
"""

from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
from collections import Counter, defaultdict
from enum import Enum


class A11yRole(Enum):
    """Common accessibility roles"""
    BUTTON = "button"
    HEADING = "heading"
    LINK = "link"
    TEXTBOX = "textbox"
    CHECKBOX = "checkbox"
    RADIO = "radio"
    LIST = "list"
    LISTITEM = "listitem"
    MENU = "menu"
    MENUITEM = "menuitem"
    DIALOG = "dialog"
    NAVIGATION = "navigation"
    MAIN = "main"
    ARTICLE = "article"
    SECTION = "section"
    SEARCH = "search"
    FORM = "form"
    IMG = "img"
    TABLE = "table"
    GRID = "grid"


@dataclass
class A11yStats:
    """Accessibility statistics"""
    total_nodes: int = 0
    nodes_with_name: int = 0
    nodes_with_description: int = 0

    # Role counts
    role_counts: Dict[str, int] = field(default_factory=dict)

    # Key roles
    buttons: List[Dict] = field(default_factory=list)
    headings: List[Dict] = field(default_factory=list)
    links: List[Dict] = field(default_factory=list)
    form_fields: List[Dict] = field(default_factory=list)
    landmarks: List[Dict] = field(default_factory=list)

    # ARIA attributes
    aria_labels: int = 0
    aria_labelledby: int = 0
    aria_describedby: int = 0
    aria_hidden: int = 0

    # Semantic structure (computed, not a property)
    has_nav: bool = False
    has_main: bool = False
    has_search: bool = False
    has_form: bool = False
    has_meaningful_structure: bool = False  # This is now a regular field

    # Name sources
    name_sources: Dict[str, int] = field(default_factory=dict)

    @property
    def semantic_density(self) -> float:
        """Ratio of semantic nodes to total nodes"""
        if self.total_nodes == 0:
            return 0.0
        semantic_count = (
            len(self.buttons) +
            len(self.headings) +
            len(self.links) +
            len(self.form_fields) +
            len(self.landmarks)
        )
        return min(1.0, semantic_count / self.total_nodes)


class AccessibilityAnalyzer:
    """Analyzer for accessibility tree data"""

    ROLE_PRIORITY = {
        'button': 5,
        'heading': 4,
        'link': 3,
        'textbox': 4,
        'search': 5,
        'navigation': 4,
        'main': 3,
        'form': 3,
        'dialog': 4
    }

    def analyze(self, ax_data: Dict[str, Any]) -> A11yStats:
        """Analyze accessibility tree"""
        stats = A11yStats()
        nodes = ax_data.get('nodes', [])
        stats.total_nodes = len(nodes)

        for node in nodes:
            self._process_node(node, stats)

        self._derive_structure(stats)
        return stats

    def _process_node(self, node: Dict[str, Any], stats: A11yStats):
        """Process a single accessibility node"""
        role = node.get('role', {}).get('value', '').lower()
        name = node.get('name', {}).get('value', '')
        desc = node.get('description', {}).get('value', '')

        # Track name sources
        name_source = node.get('name', {}).get('sources', [])
        for source in name_source:
            source_type = source.get('type', 'unknown')
            stats.name_sources[source_type] = stats.name_sources.get(source_type, 0) + 1

        # Track names
        if name:
            stats.nodes_with_name += 1
        if desc:
            stats.nodes_with_description += 1

        # Track roles
        if role:
            stats.role_counts[role] = stats.role_counts.get(role, 0) + 1

        # Process specific roles
        if role == 'button':
            stats.buttons.append({
                'name': name,
                'node_id': node.get('nodeId'),
                'backend_id': node.get('backendDOMNodeId')
            })
        elif role == 'heading':
            stats.headings.append({
                'name': name,
                'level': self._extract_heading_level(name, node),
                'node_id': node.get('nodeId')
            })
        elif role == 'link':
            stats.links.append({
                'name': name,
                'node_id': node.get('nodeId')
            })
        elif role in ['textbox', 'searchbox', 'combobox', 'input']:
            stats.form_fields.append({
                'role': role,
                'name': name,
                'node_id': node.get('nodeId')
            })
        elif role in ['navigation', 'nav']:
            stats.landmarks.append({'role': role, 'name': name})
            stats.has_nav = True
        elif role in ['main', 'maincontent']:
            stats.landmarks.append({'role': role, 'name': name})
            stats.has_main = True
        elif role == 'search':
            stats.landmarks.append({'role': role, 'name': name})
            stats.has_search = True
        elif role == 'form':
            stats.landmarks.append({'role': role, 'name': name})
            stats.has_form = True

        # Track ARIA attributes
        properties = node.get('properties', [])
        for prop in properties:
            prop_name = prop.get('name', '')
            if 'aria-label' in prop_name:
                stats.aria_labels += 1
            elif 'aria-labelledby' in prop_name:
                stats.aria_labelledby += 1
            elif 'aria-describedby' in prop_name:
                stats.aria_describedby += 1
            elif 'aria-hidden' in prop_name:
                stats.aria_hidden += 1

    def _extract_heading_level(self, name: str, node: Dict) -> int:
        """Extract heading level from name or role properties"""
        # Try to get from role
        role_props = node.get('role', {})
        if 'level' in role_props:
            try:
                return int(role_props['level'])
            except:
                pass

        # Try to extract from name
        import re
        match = re.search(r'h(\d)', name.lower())
        if match:
            return int(match.group(1))

        # Check properties
        for prop in node.get('properties', []):
            if prop.get('name') == 'level':
                try:
                    return int(prop.get('value', 0))
                except:
                    pass

        return 1  # Default

    def _derive_structure(self, stats: A11yStats):
        """Derive structural understanding"""
        # Structure quality - assign to the regular field
        stats.has_meaningful_structure = (
            stats.semantic_density > 0.05 and
            len(stats.headings) > 0 and
            len(stats.buttons) > 0
        )

    def get_actionable_elements(self, stats: A11yStats) -> List[Dict]:
        """Get prioritized actionable elements"""
        elements = []

        # Priority 1: Forms and search
        if stats.has_search:
            elements.append({
                'type': 'search',
                'priority': 10,
                'action': 'search'
            })

        if stats.has_form:
            elements.append({
                'type': 'form',
                'priority': 9,
                'action': 'fill_form'
            })

        # Priority 2: Buttons with names
        for btn in stats.buttons[:10]:
            if btn.get('name'):
                elements.append({
                    'type': 'button',
                    'name': btn.get('name'),
                    'priority': 8,
                    'action': 'click'
                })

        # Priority 3: Links with names
        for link in stats.links[:5]:
            if link.get('name'):
                elements.append({
                    'type': 'link',
                    'name': link.get('name'),
                    'priority': 6,
                    'action': 'navigate'
                })

        return sorted(elements, key=lambda x: x.get('priority', 0), reverse=True)

    def find_job_related_elements(self, stats: A11yStats) -> List[Dict]:
        """Find elements related to jobs"""
        job_keywords = [
            'job', 'position', 'role', 'career', 'hiring',
            'apply', 'opportunity', 'vacancy', 'opening'
        ]

        results = []

        # Check all named elements
        for node in stats.buttons + stats.headings + stats.links:
            name = node.get('name', '').lower()
            if any(kw in name for kw in job_keywords):
                results.append(node)

        return results


# === Usage ===

def analyze_accessibility(ax_data: Dict[str, Any]) -> Dict[str, Any]:
    """Quick analysis function"""
    analyzer = AccessibilityAnalyzer()
    stats = analyzer.analyze(ax_data)

    return {
        'total_nodes': stats.total_nodes,
        'semantic_density': stats.semantic_density,
        'has_meaningful_structure': stats.has_meaningful_structure,
        'buttons': len(stats.buttons),
        'headings': len(stats.headings),
        'links': len(stats.links),
        'form_fields': len(stats.form_fields),
        'has_nav': stats.has_nav,
        'has_main': stats.has_main,
        'has_search': stats.has_search,
        'has_form': stats.has_form,
        'top_roles': dict(list(stats.role_counts.items())[:10]),
        'actionable_elements': analyzer.get_actionable_elements(stats)[:5],
        'job_elements': len(analyzer.find_job_related_elements(stats))
    }


if __name__ == "__main__":
    # Sample AX data (simplified)
    sample_ax = {
        "nodes": [
            {
                "nodeId": "1",
                "role": {"value": "button"},
                "name": {"value": "Submit Application"},
                "properties": [{"name": "aria-label", "value": "Submit job application"}]
            },
            {
                "nodeId": "2",
                "role": {"value": "heading", "level": 1},
                "name": {"value": "Job Listings"}
            },
            {
                "nodeId": "3",
                "role": {"value": "link"},
                "name": {"value": "View Jobs at Google"}
            },
            {
                "nodeId": "4",
                "role": {"value": "navigation"},
                "name": {"value": "Main Navigation"}
            },
            {
                "nodeId": "5",
                "role": {"value": "search"},
                "name": {"value": "Search jobs"}
            },
            {
                "nodeId": "6",
                "role": {"value": "textbox"},
                "name": {"value": "Enter job title"}
            },
            {
                "nodeId": "7",
                "role": {"value": "button"},
                "name": {"value": "Search"}
            }
        ]
    }

    print("=" * 50)
    print("ACCESSIBILITY ANALYSIS")
    print("=" * 50)

    result = analyze_accessibility(sample_ax)

    print("\n📊 STATISTICS:")
    for key, value in result.items():
        if key == 'actionable_elements':
            print(f"  {key}:")
            for elem in value:
                print(f"    - {elem}")
        elif key == 'top_roles':
            print(f"  {key}: {value}")
        else:
            print(f"  {key}: {value}")
