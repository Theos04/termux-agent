import json
import re

with open('session_20260812_131833/dom_trees/dom_132034_058751.json', 'r') as f:
    content = f.read()

# Find all message entries with sender and text
messages = []

# Pattern for sender/timestamp
sender_pattern = r'"data-pre-plain-text":"\[([^\]]+)\] ([^:]+):[^"]*"'
senders = list(re.finditer(sender_pattern, content))

# Pattern for message text
text_pattern = r'"selectable-text[^"]*"[^>]*>([^<]+)</span>'
texts = list(re.finditer(text_pattern, content))

print(f"Found {len(senders)} senders and {len(texts)} text elements")

# Try to match senders with texts (they appear in order)
for i, sender_match in enumerate(senders[:20]):
    timestamp = sender_match.group(1)
    sender = sender_match.group(2).strip()
    print(f"[{timestamp}] {sender}:")
    
    # Find the next text that belongs to this message
    if i < len(texts):
        text = texts[i].group(1).strip()
        if text and len(text) > 2:
            print(f"  {text}")

print("\n" + "="*50)

# Alternative: Look for message bubbles in the HTML-like content
html_pattern = r'<span[^>]*class="[^"]*selectable-text[^"]*"[^>]*>([^<]+)</span>'
html_matches = re.findall(html_pattern, content)

print(f"Found {len(html_matches)} text spans:")
for i, text in enumerate(html_matches[:20]):
    if len(text.strip()) > 2:
        print(f"  {i+1}. {text.strip()}")
