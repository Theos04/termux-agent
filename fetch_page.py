#!/usr/bin/env python3
"""
Chrome Page Fetcher - Fixed
Properly handles WebSocket responses with matching IDs
"""

import json
import websocket
import requests
import sys
import time

def fetch_page(port=9236):
    # Get WebSocket URL
    resp = requests.get(f"http://127.0.0.1:{port}/json")
    tabs = resp.json()
    
    # Find the page tab
    page_tab = None
    for tab in tabs:
        if tab.get('type') == 'page':
            page_tab = tab
            break
    
    if not page_tab:
        print("No page tab found")
        return
    
    ws_url = page_tab.get('webSocketDebuggerUrl')
    print(f"WS URL: {ws_url}")
    
    # Connect
    ws = websocket.create_connection(ws_url, timeout=10)
    print("Connected")
    
    # Enable Runtime
    ws.send(json.dumps({"id": 1, "method": "Runtime.enable"}))
    # Wait for response
    while True:
        resp = ws.recv()
        data = json.loads(resp)
        if data.get('id') == 1:
            print("Runtime.enable confirmed")
            break
    
    # Get page title - send command with ID 2
    cmd_id = 2
    ws.send(json.dumps({
        "id": cmd_id,
        "method": "Runtime.evaluate",
        "params": {
            "expression": "document.title",
            "returnByValue": True
        }
    }))
    
    # Wait for response with matching ID
    print("Waiting for title...")
    while True:
        resp = ws.recv()
        data = json.loads(resp)
        # Check if this is the response to our command
        if data.get('id') == cmd_id:
            print("Got evaluation response!")
            result = data.get('result', {})
            if 'result' in result:
                value = result['result'].get('value')
                print(f"Title: {value}")
            elif 'error' in result:
                print(f"Error: {result['error']}")
            break
        else:
            # This is a console message or other event, print for debugging
            if data.get('method') == 'Runtime.consoleAPICalled':
                # Don't print all console messages, just the first line
                pass
    
    # Get page text - send command with ID 3
    cmd_id = 3
    ws.send(json.dumps({
        "id": cmd_id,
        "method": "Runtime.evaluate",
        "params": {
            "expression": "document.body ? document.body.innerText : ''",
            "returnByValue": True
        }
    }))
    
    print("Waiting for page text...")
    while True:
        resp = ws.recv()
        data = json.loads(resp)
        if data.get('id') == cmd_id:
            result = data.get('result', {})
            if 'result' in result:
                text = result['result'].get('value', '')
                print(f"Got {len(text)} characters of text")
                print("First 500 characters:")
                print(text[:500])
            break
    
    # Get all links - send command with ID 4
    cmd_id = 4
    ws.send(json.dumps({
        "id": cmd_id,
        "method": "Runtime.evaluate",
        "params": {
            "expression": "Array.from(document.querySelectorAll('a[href]')).map(a => a.href).slice(0, 10)",
            "returnByValue": True
        }
    }))
    
    print("Waiting for links...")
    while True:
        resp = ws.recv()
        data = json.loads(resp)
        if data.get('id') == cmd_id:
            result = data.get('result', {})
            if 'result' in result:
                links = result['result'].get('value', [])
                print(f"Found {len(links)} links")
                for link in links[:5]:
                    print(f"  {link[:80]}")
            break
    
    ws.close()

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 9236
    fetch_page(port)
