import json
import re
from collections import defaultdict

# Load the DOM data
with open('session_20260812_131833/dom_trees/dom_132034_058751.json') as f:
    dom_data = json.load(f)

print("📱 WHATSAPP CHAT EXTRACTOR")
print("=" * 60)

# Function to recursively find message containers
def find_messages(node, messages=None, depth=0):
    if messages is None:
        messages = []
    
    # Look for message containers - they have data-testid="msg-container"
    if isinstance(node, dict):
        # Check attributes for message containers
        attrs = node.get('attributes', [])
        for i in range(0, len(attrs), 2):
            if i+1 < len(attrs):
                if attrs[i] == 'data-testid' and attrs[i+1] == 'msg-container':
                    messages.append(node)
                    break
        
        # Also check for quoted messages
        for i in range(0, len(attrs), 2):
            if i+1 < len(attrs):
                if attrs[i] == 'role' and attrs[i+1] == 'button':
                    if attrs[i-2:i+2] and 'quoted-message' in str(attrs):
                        messages.append(node)
                        break
        
        # Recursively search children
        for child in node.get('children', []):
            find_messages(child, messages, depth+1)
    
    return messages

# Get root node
root = dom_data.get('root', {})
print(f"📄 Searching for messages in DOM...")

# Find all message containers
messages = find_messages(root)
print(f"✅ Found {len(messages)} message containers")

# Extract message details
chat_data = []

def extract_text_from_node(node):
    """Extract text from a node and its children"""
    texts = []
    
    # Check for direct text content
    if isinstance(node, dict):
        # Check for text content in attributes
        attrs = node.get('attributes', [])
        for i in range(0, len(attrs), 2):
            if i+1 < len(attrs):
                if attrs[i] == 'data-pre-plain-text':
                    texts.append(attrs[i+1])
        
        # Check for child text nodes
        if 'children' in node:
            for child in node['children']:
                if isinstance(child, dict):
                    # If child has nodeName '#text', get its value
                    if child.get('nodeName') == '#text':
                        if child.get('nodeValue'):
                            texts.append(child['nodeValue'])
                    else:
                        texts.extend(extract_text_from_node(child))
    
    return texts

def extract_message(node):
    """Extract full message details from a message container"""
    msg = {
        'sender': None,
        'message': None,
        'timestamp': None,
        'quoted': None,
        'is_reply': False,
        'type': 'text'
    }
    
    # Convert node to string for regex patterns
    node_str = json.dumps(node)
    
    # Extract sender from data-pre-plain-text
    sender_match = re.search(r'data-pre-plain-text="\[([^\]]+)\] ([^:]+):', node_str)
    if sender_match:
        msg['timestamp'] = sender_match.group(1)
        msg['sender'] = sender_match.group(2).strip()
    
    # Extract quoted message
    quoted_match = re.search(r'quoted-message.*?selectable-text[^>]*>([^<]+)</span>', node_str)
    if quoted_match:
        msg['quoted'] = quoted_match.group(1).strip()
        msg['is_reply'] = True
    
    # Extract main message text
    # Look for selectable-text spans that contain the message
    msg_patterns = [
        r'selectable-text copyable-text[^>]*>([^<]+)</span>',
        r'selectable-text[^>]*>([^<]+)</span>',
    ]
    
    for pattern in msg_patterns:
        matches = re.findall(pattern, node_str)
        # Filter out quotes and metadata
        for match in matches:
            if match.strip() and not match.strip().startswith('['):
                # Skip if it looks like a quoted message
                if msg['quoted'] and match.strip() == msg['quoted']:
                    continue
                if msg['timestamp'] and match.strip() == msg['timestamp']:
                    continue
                if len(match.strip()) > 2:  # Avoid single character matches
                    msg['message'] = match.strip()
                    break
        if msg['message']:
            break
    
    return msg

# Extract messages from found containers
for idx, msg_node in enumerate(messages[:50]):  # Limit to first 50 messages
    msg_data = extract_message(msg_node)
    if msg_data['message'] or msg_data['sender']:
        chat_data.append(msg_data)

print(f"\n💬 EXTRACTED MESSAGES ({len(chat_data)}):")
print("=" * 60)

for i, msg in enumerate(chat_data, 1):
    print(f"\n📨 Message #{i}:")
    if msg['sender']:
        print(f"  👤 From: {msg['sender']}")
    if msg['timestamp']:
        print(f"  🕐 At: {msg['timestamp']}")
    if msg['quoted']:
        print(f"  💬 Replying to: {msg['quoted'][:50]}...")
    if msg['message']:
        print(f"  📝 Text: {msg['message']}")
    if not msg['sender'] and not msg['message']:
        print("  ⚠️  [Partial message data]")

# Save extracted messages to file
with open('extracted_chat_messages.json', 'w') as f:
    json.dump(chat_data, f, indent=2, ensure_ascii=False)

print(f"\n✅ Extracted {len(chat_data)} messages saved to extracted_chat_messages.json")
print(f"📊 Statistics:")
print(f"  • Messages with sender: {sum(1 for m in chat_data if m['sender'])}")
print(f"  • Messages with text: {sum(1 for m in chat_data if m['message'])}")
print(f"  • Replies: {sum(1 for m in chat_data if m['is_reply'])}")
