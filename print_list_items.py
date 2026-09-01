#!/usr/bin/env python3
"""
Print all list items from the accessibility tree
"""

import json
import sys
from dynamic_cdp_7 import EnhancedChromeCDP

def print_list_items(chrome, tab_index=0):
    """Print all list items from the accessibility tree"""
    
    # Get comprehensive accessibility tree
    print("\n♿ Getting accessibility tree...")
    ax_data = chrome.get_comprehensive_ax_tree(tab_index)
    
    if not ax_data or "error" in ax_data:
        print("❌ Failed to get accessibility tree")
        return
    
    # Find all list items and lists
    list_items = []
    lists = []
    list_item_details = []
    
    for node in ax_data.get('node_details', []):
        role = node.get('role', '')
        if role == 'listitem':
            list_items.append(node)
            list_item_details.append({
                'node_id': node.get('node_id'),
                'backend_id': node.get('backend_node_id'),
                'name': node.get('name', ''),
                'description': node.get('description', ''),
                'properties': node.get('properties', {}),
                'child_ids': node.get('child_ids', []),
                'parent_id': node.get('parent_id')
            })
        elif role == 'list':
            lists.append(node)
    
    # Print results
    print("\n" + "=" * 80)
    print("📋 LIST ITEMS FROM ACCESSIBILITY TREE")
    print("=" * 80)
    
    print(f"\n📊 Statistics:")
    print(f"   Total Lists: {len(lists)}")
    print(f"   Total List Items: {len(list_items)}")
    
    # Print each list item
    print("\n📝 LIST ITEMS DETAILS:")
    print("-" * 80)
    
    for i, item in enumerate(list_item_details, 1):
        print(f"\n{i}. List Item (Node ID: {item['node_id']})")
        print(f"   Name: {item['name'] or '(unnamed)'}")
        if item['description']:
            print(f"   Description: {item['description']}")
        
        # Print properties
        if item['properties']:
            print("   Properties:")
            for key, value in item['properties'].items():
                print(f"     • {key}: {value}")
        
        if item['child_ids']:
            print(f"   Child IDs: {item['child_ids']}")
        if item['parent_id']:
            print(f"   Parent ID: {item['parent_id']}")
        
        print(f"   Backend Node ID: {item['backend_id']}")
    
    # Save to file
    with open('list_items_export.json', 'w') as f:
        json.dump({
            'statistics': {
                'total_lists': len(lists),
                'total_list_items': len(list_items)
            },
            'lists': lists,
            'list_items': list_item_details
        }, f, indent=2)
    
    print("\n" + "=" * 80)
    print(f"💾 Results saved to: list_items_export.json")
    print(f"📊 Total list items found: {len(list_items)}")
    
    return list_items

def main():
    # Get port from user
    port_input = input("🔌 Chrome debug port (default 9227): ").strip()
    port = int(port_input) if port_input else 9227
    
    # Connect to Chrome
    chrome = EnhancedChromeCDP(port=port)
    
    # Get tabs
    tabs = chrome.get_tabs()
    if not tabs:
        print("❌ No tabs found")
        return
    
    # Select tab
    chrome.list_tabs()
    tab_input = input(f"\n📑 Select tab (0-{len(tabs)-1}, default 0): ").strip()
    tab_index = int(tab_input) if tab_input else 0
    
    # Print list items
    print_list_items(chrome, tab_index)
    
    # Close session
    chrome.close_session()

if __name__ == "__main__":
    main()
