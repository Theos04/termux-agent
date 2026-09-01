# The messages from your console output
messages_data = [
    {"sender": "Unknown", "text": "Karr diya", "timestamp": "Sun Feb 08 2026 21:28:00 GMT+0530"},
    {"sender": "Unknown", "text": "Papa k samne hy na tu", "timestamp": "Sun Feb 08 2026 21:28:00 GMT+0530"},
    {"sender": "Unknown", "text": "Umm", "timestamp": "Sun Feb 08 2026 21:29:00 GMT+0530"},
    {"sender": "Unknown", "text": "Safe", "timestamp": "Sun Feb 08 2026 21:29:00 GMT+0530"},
    {"sender": "Unknown", "text": "Aaya gharpe", "timestamp": "Sun Feb 08 2026 21:55:00 GMT+0530"},
    {"sender": "Unknown", "text": "Bapree", "timestamp": "Sun Feb 08 2026 21:56:00 GMT+0530"},
    {"sender": "Unknown", "text": "Good morning Daddy", "timestamp": "Sun Mar 08 2026 08:50:00 GMT+0530"},
    {"sender": "Unknown", "text": "Wahhhhh", "timestamp": "Sun Mar 08 2026 08:51:00 GMT+0530"},
    {"sender": "Unknown", "text": "What a timing", "timestamp": "Sun Mar 08 2026 08:52:00 GMT+0530"},
    {"sender": "Unknown", "text": "Dono saath mey soye", "timestamp": "Sun Mar 08 2026 08:52:00 GMT+0530"},
    {"sender": "Unknown", "text": "Saath mey uthe", "timestamp": "Sun Mar 08 2026 08:52:00 GMT+0530"},
    {"sender": "Unknown", "text": "Nahane jaara", "timestamp": "Sun Mar 08 2026 08:52:00 GMT+0530"},
    {"sender": "Unknown", "text": "Kk baby", "timestamp": "Sun Mar 08 2026 08:52:00 GMT+0530"},
    {"sender": "Unknown", "text": "We are also goin yeshua", "timestamp": "Sun Mar 08 2026 08:53:00 GMT+0530"},
    {"sender": "Unknown", "text": "Nikla ghar se???", "timestamp": "Sun Mar 08 2026 10:57:00 GMT+0530"},
    {"sender": "Unknown", "text": "mailto.harshmehta04@gmail.com", "timestamp": "Sat Aug 08 2026 11:41:00 GMT+0530"},
    {"sender": "Unknown", "text": "Where are you??", "timestamp": "Sun Nov 08 2026 16:10:00 GMT+0530"},
    {"sender": "Unknown", "text": "Where are you??", "timestamp": "Sun Nov 08 2026 16:41:00 GMT+0530"},
    {"sender": "Unknown", "text": "Abhi bhi", "timestamp": "Sun Nov 08 2026 16:41:00 GMT+0530"},
    {"sender": "Unknown", "text": "Nhi hoga", "timestamp": "Sun Nov 08 2026 16:45:00 GMT+0530"},
    {"sender": "Unknown", "text": "Pura amount", "timestamp": "Sun Nov 08 2026 16:45:00 GMT+0530"},
    {"sender": "Unknown", "text": "Ugh", "timestamp": "Sun Nov 08 2026 16:46:00 GMT+0530"},
    {"sender": "Unknown", "text": "Abhiraj ko bola tha last time karne", "timestamp": "Sun Nov 08 2026 16:46:00 GMT+0530"},
    {"sender": "Unknown", "text": "But u might be busy na there", "timestamp": "Sun Nov 08 2026 16:46:00 GMT+0530"},
    {"sender": "Unknown", "text": "Is it urgent", "timestamp": "Sun Nov 08 2026 16:46:00 GMT+0530"},
    {"sender": "Unknown", "text": "I will be done with my last round in som time", "timestamp": "Sun Nov 08 2026 16:46:00 GMT+0530"},
    {"sender": "Unknown", "text": "Tu kabhi free hongi?", "timestamp": "Sun Nov 08 2026 16:47:00 GMT+0530"},
    {"sender": "Unknown", "text": "I will be done with my last round in som time", "timestamp": "Sun Nov 08 2026 16:47:00 GMT+0530"},
    {"sender": "Unknown", "text": "Tu kabhi free hongi?", "timestamp": "Sun Nov 08 2026 16:47:00 GMT+0530"},
    {"sender": "Unknown", "text": "Okay no problem", "timestamp": "Sun Nov 08 2026 16:47:00 GMT+0530"},
    {"sender": "Unknown", "text": "Thanks", "timestamp": "Sun Nov 08 2026 16:47:00 GMT+0530"},
    {"sender": "Unknown", "text": "Okay call me when u are done", "timestamp": "Sun Nov 08 2026 16:47:00 GMT+0530"},
    {"sender": "Unknown", "text": "Alright", "timestamp": "Sun Nov 08 2026 16:47:00 GMT+0530"},
    {"sender": "Unknown", "text": "Sort kr", "timestamp": "Tue Dec 08 2026 11:55:00 GMT+0530"},
    {"sender": "Unknown", "text": "Konse frm k liye eligible h", "timestamp": "Tue Dec 08 2026 11:55:00 GMT+0530"},
    {"sender": "Unknown", "text": "Okay", "timestamp": "Tue Dec 08 2026 12:07:00 GMT+0530"},
    {"sender": "Unknown", "text": "Hm", "timestamp": "Tue Dec 08 2026 12:11:00 GMT+0530"},
]

import json
import re
from datetime import datetime

# Try to extract sender from the data-pre-plain-text in the DOM
with open('session_20260812_131833/dom_trees/dom_132034_058751.json', 'r') as f:
    content = f.read()

# Find sender names from data-pre-plain-text
senders = re.findall(r'"data-pre-plain-text":"\[[^\]]+\] ([^:]+):', content)
unique_senders = list(set(senders))
print(f"Found senders: {unique_senders}")

# Since we have the messages already, let's save them
with open('whatsapp_messages_from_console.json', 'w') as f:
    json.dump(messages_data, f, indent=2, ensure_ascii=False)

print(f"\n✅ Saved {len(messages_data)} messages to whatsapp_messages_from_console.json")
print("\n📊 Messages:")
for i, msg in enumerate(messages_data[:20], 1):
    print(f"{i:2}. {msg['text']}")
