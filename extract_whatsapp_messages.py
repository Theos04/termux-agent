import json
import re

def extract_messages_from_dom(dom_file):
    """Extract WhatsApp messages from DOM JSON file"""
    with open(dom_file, 'r') as f:
        data = json.load(f)
    
    messages = []
    
    def traverse_node(node, current_sender=None, current_timestamp=None):
        if isinstance(node, dict):
            # Check for message container
            attrs = node.get('attributes', [])
            
            # Extract data-pre-plain-text for sender and timestamp
            for i in range(0, len(attrs)-1, 2):
                if attrs[i] == 'data-pre-plain-text':
                    text = attrs[i+1] if i+1 < len(attrs) else ''
                    match = re.search(r'\[([^\]]+)\] ([^:]+):', text)
                    if match:
                        current_timestamp = match.group(1)
                        current_sender = match.group(2).strip()
            
            # Extract message text from spans
            if node.get('nodeName') == 'span':
                for cls in node.get('attributes', []):
                    if cls == 'selectable-text' or cls == 'copyable-text':
                        if 'children' in node:
                            for child in node.get('children', []):
                                if child.get('nodeName') == '#text' and child.get('nodeValue'):
                                    text = child.get('nodeValue', '').strip()
                                    if text and len(text) > 2:
                                        messages.append({
                                            'sender': current_sender,
                                            'timestamp': current_timestamp,
                                            'text': text
                                        })
            
            # Recursively traverse children
            for child in node.get('children', []):
                traverse_node(child, current_sender, current_timestamp)
        elif isinstance(node, list):
            for item in node:
                traverse_node(item, current_sender, current_timestamp)
    
    # Start traversal from root
    root = data.get('root', {})
    traverse_node(root)
    
    return messages

# Extract messages
dom_file = 'session_20260812_131833/dom_trees/dom_132034_058751.json'
messages = extract_messages_from_dom(dom_file)

print(f"📱 WhatsApp Messages Extracted: {len(messages)}")
print("=" * 50)

for i, msg in enumerate(messages[:20], 1):
    print(f"\nMessage #{i}:")
    if msg.get('sender'):
        print(f"  👤 From: {msg['sender']}")
    if msg.get('timestamp'):
        print(f"  🕐 At: {msg['timestamp']}")
    if msg.get('text'):
        print(f"  📝 {msg['text']}")

# Save to file
with open('whatsapp_messages_extracted.json', 'w') as f:
    json.dump(messages, f, indent=2, ensure_ascii=False)

print(f"\n✅ Saved {len(messages)} messages to whatsapp_messages_extracted.json")
