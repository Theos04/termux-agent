#!/usr/bin/env python3
"""
Quick test of DOM accessibility analyzer
"""

from dom_analyzer_lib import DOMAccessibilityAnalyzer
import os

# Path to your session
session_dir = "/data/data/com.termux/files/home/automation/chrome-launcher/memory/session_20260731_061442"

if not os.path.exists(session_dir):
    print(f"Session not found: {session_dir}")
    print("Update the path to match your actual session directory")
    exit(1)

print("Loading data...")
analyzer = DOMAccessibilityAnalyzer(session_dir)

# Summary
print("\n" + "="*60)
print("PAGE SUMMARY")
print("="*60)
summary = analyzer.get_page_summary()
for key, value in summary.items():
    if isinstance(value, dict):
        print(f"\n{key}:")
        for k, v in value.items():
            print(f"  {k}: {v}")
    else:
        print(f"{key}: {value}")

# Find all buttons
print("\n" + "="*60)
print("BUTTONS")
print("="*60)
buttons = analyzer.find_by_role('button')
for i, btn in enumerate(buttons[:10], 1):
    name = btn.name if btn.name else '[unnamed]'
    print(f"{i}. '{name}' (id: {btn.node_id})")

# Show semantic path for first button
if buttons:
    print("\n" + "="*60)
    print("SEMANTIC PATH EXAMPLE")
    print("="*60)
    analyzer.print_semantic_path(buttons[0].node_id)

# Show DOM path for first button's DOM node
if buttons:
    dom_node = analyzer.map_ax_to_dom(buttons[0].node_id)
    if dom_node:
        print("\n" + "="*60)
        print("DOM PATH EXAMPLE")
        print("="*60)
        analyzer.print_dom_path(dom_node.node_id)

# Find duplicate names
print("\n" + "="*60)
print("DUPLICATE NAMES")
print("="*60)
duplicates = analyzer.resolve_duplicate_names()
if duplicates:
    print(f"Found {len(duplicates)} duplicate accessible names:")
    for name, nodes in list(duplicates.items())[:5]:
        print(f"\n  '{name}':")
        for node in nodes[:3]:
            print(f"    - {node.role} (id: {node.node_id})")
else:
    print("No duplicate names found")

print("\n✅ Done!")
