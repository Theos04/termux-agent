import json
import re

with open('session_20260812_131833/snapshots/snapshot_132040_947183.json', 'r') as f:
    data = json.load(f)

messages = []
dom_nodes = data.get('data', {}).get('dom_nodes', [])

print(f"Found {len(dom_nodes)} DOM nodes")

# Look for text nodes that might be messages
for i, node in enumerate(dom_nodes):
    node_value = node.get('nodeValue', '')
    if node_value and len(node_value) > 2 and node_value not in ['\n', ' ', '']:
        # Check if it looks like a message (not CSS, not JSON, not URLs)
        if not node_value.startswith('{') and not node_value.startswith('@') and not node_value.startswith('.'):
            # Try to find context - look for data-pre-plain-text nearby
            # For now, just collect all text nodes
            messages.append({
                'index': i,
                'text': node_value.strip()
            })

print(f"Found {len(messages)} potential message nodes")
print("\nFirst 30 messages:")
for msg in messages[:30]:
    if len(msg['text']) > 3:
        print(f"  {msg['text'][:100]}")

# Now extract using the pattern you found with rg
print("\n" + "="*60)
print("Searching for specific messages...")

# Use regex to find messages with context
content = json.dumps(data)
# Find patterns like "Is it urgent"
patterns = [
    r'"Is it urgent"',
    r'"Tu kabhi free hongi\?"',
    r'"Karr diya"',
    r'"Papa k samne hy na tu"',
]

for pattern in patterns:
    matches = re.findall(pattern, content)
    if matches:
        print(f"Found {len(matches)} matches for {pattern}")

# Extract all message-like text from the snapshot
print("\n" + "="*60)
print("All message-like text from snapshot:")
text_nodes = re.findall(r'"nodeValue":\s*"([^"]{3,100})"', content)
for text in text_nodes[:30]:
    if text and not text.startswith('{') and not text.startswith('@') and not text.startswith('.'):
        print(f"  {text}")
