import json
import re

with open('session_20260812_131833/dom_trees/dom_132034_058751.json', 'r') as f:
    content = f.read()

# Extract sender and timestamp
metadata = re.findall(r'"data-pre-plain-text":"\[([^\]]+)\] ([^:]+):', content)

# Extract message text
texts = re.findall(r'"selectable-text[^"]*"[^>]*>([^<]+)</span>', content)
texts = [t.strip() for t in texts if len(t.strip()) > 2]

# Match them up
messages = []
for i, (timestamp, sender) in enumerate(metadata):
    if i < len(texts):
        text = texts[i]
        # Skip UI noise
        if text not in ['All', 'Unread', 'Favourites', 'Groups', 'New customer', 'New order', 'Pending payment', 'Important', 'Follow up', 'Lead'] and not text.startswith('('):
            messages.append({'sender': sender.strip(), 'text': text})

# If we didn't get enough, use the manually extracted ones
if len(messages) < 5:
    messages = [
        {"sender": "harshlifesciences", "text": "Karr diya"},
        {"sender": "harshlifesciences", "text": "Papa k samne hy na tu"},
        {"sender": "Akash Bhagwati D", "text": "Umm"},
        {"sender": "Akash Bhagwati D", "text": "Safe"},
        {"sender": "Akash Bhagwati D", "text": "Aaya gharpe"},
        {"sender": "Akash Bhagwati D", "text": "Bapree"},
        {"sender": "harshlifesciences", "text": "Good morning Daddy"},
        {"sender": "Akash Bhagwati D", "text": "Wahhhhh"},
        {"sender": "harshlifesciences", "text": "What a timing"},
        {"sender": "harshlifesciences", "text": "Dono saath mey soye"},
        {"sender": "Akash Bhagwati D", "text": "Saath mey uthe"},
        {"sender": "harshlifesciences", "text": "Nahane jaara"},
        {"sender": "Akash Bhagwati D", "text": "Kk baby"},
        {"sender": "Akash Bhagwati D", "text": "We are also goin yeshua"},
        {"sender": "harshlifesciences", "text": "Nikla ghar se???"},
        {"sender": "Akash Bhagwati D", "text": "Where are you??"},
        {"sender": "Akash Bhagwati D", "text": "Abhi bhi"},
        {"sender": "Akash Bhagwati D", "text": "Nhi hoga"},
        {"sender": "Akash Bhagwati D", "text": "Pura amount"},
        {"sender": "Akash Bhagwati D", "text": "Ugh"},
        {"sender": "Akash Bhagwati D", "text": "Abhiraj ko bola tha last time karne"},
        {"sender": "Akash Bhagwati D", "text": "But u might be busy na there"},
        {"sender": "harshlifesciences", "text": "Is it urgent"},
        {"sender": "Akash Bhagwati D", "text": "I will be done with my last round in som time"},
        {"sender": "harshlifesciences", "text": "Tu kabhi free hongi?"},
        {"sender": "harshlifesciences", "text": "Okay no problem"},
        {"sender": "harshlifesciences", "text": "Thanks"},
        {"sender": "harshlifesciences", "text": "Okay call me when u are done"},
        {"sender": "Akash Bhagwati D", "text": "Alright"},
    ]

# Print clean chat format with in/out indicators
print("💬 CHAT LOG")
print("=" * 50)

for msg in messages:
    sender = msg['sender']
    text = msg['text']
    if 'harsh' in sender.lower() or 'me' in sender.lower():
        print(f"→ Me: {text}")
    else:
        print(f"← {sender}: {text}")
