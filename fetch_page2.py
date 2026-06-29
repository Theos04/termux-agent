#!/usr/bin/env python3
"""
Chrome Page Client - Enhanced version for API
"""

import json
import websocket
import requests
import time
import re
from typing import Optional, Dict, List, Any

class ChromePage:
    def __init__(self, port=9226):
        self.port = port
        self.ws = None
        self.connected = False
        self.page_title = ""
        self.page_url = ""

    def connect(self):
        try:
            resp = requests.get(f"http://127.0.0.1:{self.port}/json", timeout=5)
            tabs = resp.json()

            page_tab = None
            for tab in tabs:
                if tab.get('type') == 'page':
                    page_tab = tab
                    break

            if not page_tab:
                return False

            self.page_title = page_tab.get('title', 'Untitled')
            self.page_url = page_tab.get('url', '')
            ws_url = page_tab.get('webSocketDebuggerUrl')

            self.ws = websocket.create_connection(ws_url, timeout=10)
            self.ws.send(json.dumps({"id": 1, "method": "Runtime.enable"}))
            
            while True:
                resp = self.ws.recv()
                data = json.loads(resp)
                if data.get('id') == 1:
                    break

            self.connected = True
            return True

        except Exception as e:
            return False

    def js(self, script, await_promise=False):
        if not self.connected:
            return None

        cmd_id = int(time.time() * 1000) % 100000

        self.ws.send(json.dumps({
            "id": cmd_id,
            "method": "Runtime.evaluate",
            "params": {
                "expression": script,
                "returnByValue": True,
                "awaitPromise": await_promise
            }
        }))

        timeout = 30
        start = time.time()
        while time.time() - start < timeout:
            try:
                resp = self.ws.recv()
                data = json.loads(resp)
                if data.get('id') == cmd_id:
                    result = data.get('result', {})
                    if 'result' in result:
                        return result['result'].get('value')
                    return None
            except:
                pass

        return None

    def text(self):
        return self.js("document.body ? document.body.innerText : ''") or ""

    def title(self):
        return self.js("document.title") or "No title"

    def html(self):
        return self.js("document.documentElement.outerHTML") or ""

    def close(self):
        if self.ws:
            try:
                self.ws.close()
            except:
                pass


class SmartExtractor:
    """Extract structured data from job pages"""
    
    def __init__(self):
        self.payment_patterns = {
            'paid': [
                r'stipend.*?[₹Rs][\d,]+',
                r'salary.*?[₹Rs][\d,]+',
                r'[₹Rs][\d,]+.*?(?:per|month|monthly)',
                r'paid.*?(?:internship|job)',
                r'compensation.*?[₹Rs][\d,]+',
                r'remuneration.*?[₹Rs][\d,]+',
                r'₹[\d,]+',
                r'Rs[\d,]+',
            ],
            'unpaid': [
                r'unpaid',
                r'no stipend',
                r'without pay',
                r'volunteer',
                r'expense.*?only',
                r'not.*?paid'
            ]
        }

        self.location_patterns = {
            'remote': [r'remote', r'work from home', r'wfh', r'virtual'],
            'onsite': [r'on.?site', r'in.?office', r'office', r'hyderabad', r'bangalore', r'mumbai', r'delhi', r'gurgaon'],
            'hybrid': [r'hybrid', r'partially remote']
        }

        self.requirement_patterns = [
            r'(?:requirement|skill|qualification)s?:?\s*(.*?)(?:\n\n|\n[A-Z]|\Z)',
            r'(?:experience|knowledge).*?(?:in|with).*?(?:\n|\.)'
        ]

    def extract(self, text: str) -> Dict:
        """Extract structured data from text"""
        result = {
            'title': '',
            'company': '',
            'payment_status': 'Unknown',
            'payment_amount': '',
            'location': 'Unknown',
            'location_type': 'Unknown',
            'requirements': [],
            'deadline': '',
            'type': 'Unknown',
            'summary': ''
        }

        lines = text.split('\n')

        # Extract title (first few non-empty lines)
        title_lines = []
        for line in lines[:10]:
            if line.strip() and not line.strip().lower() in ['home', 'jobs', 'internships', 'competitions']:
                title_lines.append(line.strip())
        result['title'] = ' '.join(title_lines[:3])[:100]

        # Extract company
        for line in lines[:20]:
            if 'at' in line and len(line.strip()) < 50:
                parts = line.split('at')
                if len(parts) > 1:
                    result['company'] = parts[1].strip()
                    break

        # Payment status
        text_lower = text.lower()
        result['payment_status'] = 'Unknown'
        result['payment_amount'] = ''

        # Look for payment indicators
        for pattern in self.payment_patterns['paid']:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                result['payment_status'] = 'Paid'
                result['payment_amount'] = match.group(0)
                break

        if result['payment_status'] == 'Unknown':
            for pattern in self.payment_patterns['unpaid']:
                if re.search(pattern, text_lower):
                    result['payment_status'] = 'Unpaid'
                    break

        # Location
        for loc_type, patterns in self.location_patterns.items():
            for pattern in patterns:
                if re.search(pattern, text_lower):
                    result['location_type'] = loc_type.capitalize()
                    # Try to find specific location
                    for line in lines:
                        if any(p in line.lower() for p in patterns):
                            if ':' in line:
                                result['location'] = line.split(':')[1].strip()
                            else:
                                result['location'] = line.strip()
                            break
                    break
            if result['location_type'] != 'Unknown':
                break

        # Requirements
        for pattern in self.requirement_patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                reqs = match.group(1).strip()
                items = re.split(r'[·•\n]', reqs)
                for item in items:
                    clean = item.strip()
                    if clean and len(clean) > 5:
                        result['requirements'].append(clean[:100])
                if result['requirements']:
                    break

        # Type detection
        if 'internship' in text_lower:
            result['type'] = 'Internship'
        elif 'job' in text_lower:
            result['type'] = 'Job'
        elif 'hackathon' in text_lower or 'competition' in text_lower:
            result['type'] = 'Competition'

        # Deadline
        date_patterns = [
            r'(\d{1,2}\s+[A-Za-z]+\s+\d{2,4})',
            r'([A-Za-z]+\s+\d{1,2},\s+\d{4})',
            r'(\d{2}/\d{2}/\d{4})',
            r'(\d{4}-\d{2}-\d{2})'
        ]
        for pattern in date_patterns:
            match = re.search(pattern, text)
            if match:
                result['deadline'] = match.group(1)
                break

        return result

    def format_result(self, data: Dict) -> str:
        """Format extracted data as a nice string"""
        output = []
        output.append("📋 Extracted Information")
        output.append("")

        if data.get('title'):
            output.append(f"Position: {data['title']}")
        if data.get('company'):
            output.append(f"Company: {data['company']}")
        if data.get('type'):
            output.append(f"Type: {data['type']}")

        payment = data.get('payment_status', 'Unknown')
        if payment == 'Paid':
            payment_text = f"✅ {payment}"
        elif payment == 'Unpaid':
            payment_text = f"❌ {payment}"
        else:
            payment_text = f"⚠️ {payment}"
        output.append(f"Payment: {payment_text}")

        if data.get('payment_amount'):
            output.append(f"Amount: {data['payment_amount']}")

        if data.get('location_type') != 'Unknown':
            output.append(f"Location: {data['location_type']} - {data.get('location', 'N/A')}")
        elif data.get('location'):
            output.append(f"Location: {data['location']}")

        if data.get('deadline'):
            output.append(f"Apply By: {data['deadline']}")

        if data.get('requirements'):
            output.append("")
            output.append("Requirements:")
            for req in data['requirements'][:5]:
                output.append(f"  • {req}")

        return '\n'.join(output)

