import json
import re
from collections import defaultdict

print("📱 WHATSAPP CHAT EXTRACTOR (Using Snapshot)")
print("=" * 60)

# Load the snapshot data
with open('session_20260812_131833/snapshots/snapshot_132040_947183.json') as f:
    snapshot = json.load(f)

print(f"📄 Analyzing snapshot...")

# Extract DOM nodes from snapshot
dom_nodes = snapshot.get('domNodes', [])
dom_strings = snapshot.get('domStrings', [])
layout_nodes = snapshot.get('layoutNodes', [])

print(f"  • DOM Nodes: {len(dom_nodes)}")
print(f"  • Layout Nodes: {len(layout_nodes)}")
print(f"  • Strings: {len(dom_strings)}")

# Function to decode node data
def get_node_value(node, key, default=''):
    if key in node:
        val = node[key]
        if isinstance(val, int) and val < len(dom_strings):
            return dom_strings[val]
        return val
    return default

# Find chat messages by looking for text patterns
chat_messages = []
message_patterns = [
    r'data-pre-plain-text="\[([^\]]+)\] ([^:]+):',
    r'data-testid="msg-container"',
    r'selectable-text copyable-text',
    r'quoted-message',
]

# Search through DOM nodes
for node_idx, node in enumerate(dom_nodes[:500]):  # Limit to first 500
    node_str = json.dumps(node)
    
    # Check if this node contains chat message indicators
    has_msg = False
    for pattern in message_patterns:
        if re.search(pattern, node_str):
            has_msg = True
            break
    
    if has_msg:
        # Try to extract message data
        msg = {}
        
        # Extract timestamp and sender from data-pre-plain-text
        match = re.search(r'data-pre-plain-text="\[([^\]]+)\] ([^:]+):', node_str)
        if match:
            msg['timestamp'] = match.group(1)
            msg['sender'] = match.group(2).strip()
        
        # Extract text content
        text_matches = re.findall(r'selectable-text[^>]*>([^<]+)</span>', node_str)
        if text_matches:
            # Filter out timestamps and metadata
            for text in text_matches:
                text = text.strip()
                if text and len(text) > 2:
                    # Check if it's not a timestamp or sender name
                    if not re.match(r'^\d+:\d+\s*[ap]m$', text.lower()):
                        if 'msg' not in msg:
                            msg['text'] = text
                        else:
                            msg['text'] = text
                            break
        
        # Check for quoted messages
        quoted_match = re.search(r'quoted-message[^>]*>.*?selectable-text[^>]*>([^<]+)</span>', node_str, re.DOTALL)
        if quoted_match:
            msg['reply_to'] = quoted_match.group(1).strip()
            msg['is_reply'] = True
        
        if msg:
            chat_messages.append(msg)

print(f"\n💬 FOUND {len(chat_messages)} MESSAGE ELEMENTS")
print("=" * 60)

for i, msg in enumerate(chat_messages[:20], 1):
    print(f"\n📨 Message #{i}:")
    if 'sender' in msg:
        print(f"  👤 From: {msg['sender']}")
    if 'timestamp' in msg:
        print(f"  🕐 At: {msg['timestamp']}")
    if 'reply_to' in msg:
        print(f"  💬 Replying to: {msg['reply_to'][:40]}...")
    if 'text' in msg:
        print(f"  📝 Text: {msg['text']}")
    print(f"  📊 Node: {node_idx}")

# Alternative approach: Search using the DOM from the original file
print("\n🔍 Alternative: Searching raw DOM file...")
with open('session_20260812_131833/dom_trees/dom_132034_058751.json') as f:
    dom_content = f.read()

# Use regex to find message patterns in the raw content
raw_messages = []
pattern = r'"data-pre-plain-text":\s*"\[([^\]]+)\]\s+([^:]+):[^"]*"'
matches = re.findall(pattern, dom_content)

if matches:
    print(f"\n✅ Found {len(matches)} messages using regex:")
    for i, (timestamp, sender) in enumerate(matches[:10], 1):
        print(f"  {i}. [{timestamp}] {sender}")

# Try to find message content
text_pattern = r'"selectable-text copyable-text"[^>]*>([^<]+)</span>'
texts = re.findall(text_pattern, dom_content)

if texts:
    print(f"\n📝 Found {len(texts)} text elements:")
    for i, text in enumerate(texts[:10], 1):
        if len(text.strip()) > 2:
            print(f"  {i}. {text.strip()[:50]}...")

# Save all found messages
with open('extracted_messages_raw.json', 'w') as f:
    json.dump(chat_messages, f, indent=2, ensure_ascii=False)

print(f"\n✅ Saved {len(chat_messages)} messages to extracted_messages_raw.json")
