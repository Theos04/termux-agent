import json
import re
from collections import Counter

# Load hackathons
with open('scraped_data/hackathons_20260716_222102.json', 'r') as f:
    data = json.load(f)

hackathons = data.get('hackathons', [])

# Categorize by type
categories = {
    'AI/ML': [],
    'Web3/Blockchain': [],
    'Sustainability': [],
    'Healthcare': [],
    'Fintech': [],
    'Open Innovation': []
}

for h in hackathons:
    title = h.get('title', '').lower()
    desc = h.get('description', '').lower()
    tags = h.get('tags', [])
    
    if any(k in title or k in desc for k in ['ai', 'machine learning', 'deep learning', 'ml']):
        categories['AI/ML'].append(h)
    elif any(k in title or k in desc for k in ['blockchain', 'web3', 'crypto', 'nft']):
        categories['Web3/Blockchain'].append(h)
    elif any(k in title or k in desc for k in ['sustain', 'climate', 'green', 'environment']):
        categories['Sustainability'].append(h)
    # ... add more categories

# Find high-value opportunities
print("\n📊 Hackathon Analysis")
print("=" * 60)
for cat, items in categories.items():
    if items:
        print(f"\n{cat}: {len(items)} hackathons")
        for h in items[:3]:
            print(f"  • {h.get('title')}")
