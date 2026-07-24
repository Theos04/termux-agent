import json

with open("/data/data/com.termux/files/home/chrome-sessions/session_info.json") as f:
    data = json.load(f)

unstop = data["sessions"]["6"]      # or search by name

port = unstop["port"]
ws = unstop["current_ws_id"]

ws_url = f"ws://127.0.0.1:{port}/devtools/page/{ws}"
