#!/usr/bin/env python3
"""
Simple Chrome JavaScript Test
"""

import json
import websocket

ws_url = "ws://127.0.0.1:9227/devtools/page/5BA92ADF4592CCDB9990053022DB58A4"

# Simple test script
script = """
document.title
"""

try:
    ws = websocket.create_connection(
        ws_url,
        timeout=10,
        header={"Origin": "http://127.0.0.1:9227"}
    )
    print("✅ Connected!")
    
    # Enable Runtime
    ws.send(json.dumps({"id": 1, "method": "Runtime.enable"}))
    response = ws.recv()
    print(f"Enable: {response}")
    
    # Execute simple script
    cmd = {
        "id": 2,
        "method": "Runtime.evaluate",
        "params": {
            "expression": script,
            "returnByValue": True,
            "awaitPromise": True
        }
    }
    ws.send(json.dumps(cmd))
    response = ws.recv()
    print(f"Result: {response}")
    
    ws.close()
except Exception as e:
    print(f"Error: {e}")
