import json
import re

with open('session_20260812_131833/dom_trees/dom_132034_058751.json', 'r') as f:
    data = json.load(f)

def extract_messages(node, messages=None):
    if messages is None:
        messages = []
    
    if isinstance(node, dict):
        # Check for data-pre-plain-text attribute
        attrs = node.get('attributes', [])
        for i in range(0, len(attrs)-1, 2):
            if attrs[i] == 'data-pre-plain-text':
                meta = attrs[i+1]
                # Extract timestamp and sender
                match = re.search(r'\[([^\]]+)\] ([^:]+):', meta)
                if match:
                    timestamp = match.group(1)
                    sender = match.group(2).strip()
                    
                    # Find message text - look for selectable-text spans
                    text = ""
                    
                    def find_text(n):
                        nonlocal text
                        if isinstance(n, dict):
                            # Check if this is a selectable-text span
                            attrs = n.get('attributes', [])
                            if 'selectable-text' in attrs or 'copyable-text' in attrs:
                                for child in n.get('children', []):
                                    if child.get('nodeName') == '#text':
                                        text += child.get('nodeValue', '')
                            # Recurse
                            for child in n.get('children', []):
                                find_text(child)
                    
                    find_text(node)
                    if text.strip():
                        messages.append({
                            'timestamp': timestamp,
                            'sender': sender,
                            'text': text.strip()
                        })
        
        # Recurse into children
        for child in node.get('children', []):
            extract_messages(child, messages)
    
    return messages

messages = extract_messages(data)

print(f"📱 Found {len(messages)} messages")
print("=" * 60)

for i, msg in enumerate(messages[:20], 1):
    print(f"{i:2}. [{msg['timestamp']}] {msg['sender']}:")
    print(f"    {msg['text'][:80]}...")

# Save to file
with open('whatsapp_messages_complete.json', 'w') as f:
    json.dump(messages, f, indent=2, ensure_ascii=False)

print(f"\n✅ Saved {len(messages)} messages to whatsapp_messages_complete.json")

# Statistics
senders = {}
for msg in messages:
    senders[msg['sender']] = senders.get(msg['sender'], 0) + 1

print("\n📊 Message Statistics:")
print("  Total messages:", len(messages))
print("  Unique senders:", len(senders))
print("\n  Messages per sender:")
for sender, count in sorted(senders.items(), key=lambda x: x[1], reverse=True):
    print(f"    {sender}: {count} messages")
