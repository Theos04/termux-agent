import json
from collections import Counter

with open('session_20260812_131833/accessibility/a11y_132052_021849.json') as f:
    data = json.load(f)

# Get node_details
node_details = data.get('data', {}).get('node_details', [])
print(f"📊 Found {len(node_details)} nodes in node_details")
print("=" * 50)

# Helper function to safely get node name
def get_node_name(node):
    name_field = node.get('name')
    if isinstance(name_field, dict):
        return name_field.get('value', 'Unnamed')
    elif isinstance(name_field, str):
        return name_field if name_field else 'Unnamed'
    else:
        return 'Unnamed'

# Analyze roles
roles = Counter()
interactive_nodes = []

for node in node_details:
    role = node.get('role', 'unknown')
    roles[role] += 1
    
    # Check if it's interactive
    if role in ['button', 'link', 'textbox', 'checkbox', 'radio', 'menuitem', 'tab']:
        name = get_node_name(node)
        interactive_nodes.append((role, name, node.get('nodeId', 'N/A')))

print(f"\n📋 ROLE DISTRIBUTION (Top 15):")
for role, count in roles.most_common(15):
    bar = '█' * (count // 10)
    print(f"  {role:15} : {count:4} {bar}")

print(f"\n🎯 INTERACTIVE ELEMENTS ({len(interactive_nodes)}):")
print("-" * 50)
for role, name, node_id in interactive_nodes[:30]:
    name_display = name[:45] + '...' if len(name) > 45 else name
    print(f"  [{role:10}] {name_display}")

# Get all buttons with their IDs
buttons = []
for node in node_details:
    if node.get('role') == 'button':
        name = get_node_name(node)
        node_id = node.get('nodeId')
        if name and name != 'Unnamed':
            buttons.append((name, node_id))

print(f"\n🔘 ALL BUTTONS ({len(buttons)} found):")
print("-" * 50)
for name, node_id in buttons[:25]:
    print(f"  • {name[:40]} (ID: {node_id})")

# Main navigation buttons
print(f"\n📱 MAIN NAVIGATION BUTTONS:")
nav_buttons = ['Chats', 'Status', 'Channels', 'Communities', 'Tools', 'Advertise', 'Media', 'Settings', 'Profile']
nav_found = []
for btn in nav_buttons:
    for name, node_id in buttons:
        if btn.lower() == name.lower():
            nav_found.append((btn, node_id))
            break
    else:
        nav_found.append((btn, None))

for btn, node_id in nav_found:
    if node_id:
        print(f"  ✅ {btn} (ID: {node_id})")
    else:
        print(f"  ❌ {btn}")

# Find textboxes
textboxes = []
for node in node_details:
    if node.get('role') == 'textbox':
        name = get_node_name(node)
        node_id = node.get('nodeId')
        if name:
            textboxes.append((name, node_id))

print(f"\n📝 TEXTBOXES ({len(textboxes)} found):")
for name, node_id in textboxes:
    print(f"  • {name} (ID: {node_id})")

# Find links
links = []
for node in node_details:
    if node.get('role') == 'link':
        name = get_node_name(node)
        node_id = node.get('nodeId')
        if name:
            links.append((name, node_id))

print(f"\n🔗 LINKS ({len(links)} found):")
for name, node_id in links[:10]:
    print(f"  • {name} (ID: {node_id})")

# Save interactive elements with IDs for automation
with open('interactive_elements_with_ids.json', 'w') as f:
    json.dump(interactive_nodes, f, indent=2)
print(f"\n✅ Interactive elements saved to interactive_elements_with_ids.json")
print(f"✅ Total interactive elements: {len(interactive_nodes)}")
