import json
from collections import Counter

with open('session_20260812_131833/accessibility/a11y_132052_021849.json') as f:
    data = json.load(f)

# Get node_details - this is where the nodes are stored
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

# Analyze roles from node_details
roles = Counter()
interactive_nodes = []

for node in node_details:
    role = node.get('role', 'unknown')
    roles[role] += 1
    
    # Check if it's interactive
    if role in ['button', 'link', 'textbox', 'checkbox', 'radio', 'menuitem', 'tab']:
        name = get_node_name(node)
        interactive_nodes.append((role, name, node.get('nodeId', 'N/A')))

print(f"\n📋 ROLE DISTRIBUTION:")
for role, count in roles.most_common(15):
    bar = '█' * (count // 5)
    print(f"  {role:15} : {count:4} {bar}")

print(f"\n🎯 INTERACTIVE ELEMENTS ({len(interactive_nodes)}):")
print("-" * 40)
for role, name, node_id in interactive_nodes[:30]:
    name_display = name[:40] + '...' if len(name) > 40 else name
    print(f"  [{role:10}] {name_display}")

# Find WhatsApp specific buttons
buttons = [node for node in node_details if node.get('role') == 'button']
button_names = []
for node in buttons:
    name = get_node_name(node)
    if name:
        button_names.append(name)

print(f"\n🔘 BUTTONS ({len(button_names)} found):")
print("-" * 40)
for name in button_names[:20]:
    print(f"  • {name}")

# Find focusable elements
focusable = []
for node in node_details:
    props = node.get('properties', [])
    for prop in props:
        if prop.get('name') == 'focusable':
            # Check if value is True
            value = prop.get('value', {})
            if isinstance(value, dict) and value.get('value') == True:
                name = get_node_name(node)
                role = node.get('role', 'unknown')
                focusable.append((role, name))
                break
            elif value == True:
                name = get_node_name(node)
                role = node.get('role', 'unknown')
                focusable.append((role, name))
                break

print(f"\n🎯 FOCUSABLE ELEMENTS ({len(focusable)}):")
for role, name in focusable[:20]:
    print(f"  [{role}] {name}")

# Save interactive elements for automation
with open('interactive_elements.json', 'w') as f:
    json.dump(interactive_nodes, f, indent=2)
print(f"\n✅ Interactive elements saved to interactive_elements.json")

# Print main navigation buttons
print(f"\n📱 MAIN NAVIGATION BUTTONS:")
nav_buttons = ['Chats', 'Status', 'Channels', 'Communities', 'Tools', 'Advertise', 'Media', 'Settings', 'Profile']
for btn in nav_buttons:
    found = False
    for node in buttons:
        name = get_node_name(node)
        if btn.lower() in name.lower():
            print(f"  ✅ {btn} (ID: {node.get('nodeId')})")
            found = True
            break
    if not found:
        print(f"  ❌ {btn}")
