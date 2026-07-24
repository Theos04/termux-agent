#!/usr/bin/env python3
"""
DeepSeek Chat History Extractor - Production Version
Extracts complete chat history with proper formatting
"""

import json
import subprocess
import sys
import time
import re
from typing import Optional, Dict, List, Any
from datetime import datetime

try:
    import requests
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests"])
    import requests

try:
    import websocket
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "websocket-client"])
    import websocket

class DeepSeekChatExtractor:
    def __init__(self, port: int = 9227):
        self.port = port
        self.base_url = f"http://127.0.0.1:{port}"
        self.ws_url = None
        self.tabs = []
        self._command_counter = 0

    def get_tabs(self) -> List[Dict]:
        try:
            response = requests.get(f"{self.base_url}/json", timeout=5)
            if response.status_code == 200:
                tabs = response.json()
                self.tabs = [t for t in tabs if t.get('type') == 'page']
                return self.tabs
            return []
        except Exception as e:
            print(f"❌ Error fetching tabs: {e}")
            return []

    def get_websocket_url(self, tab_index: int = 0) -> Optional[str]:
        self.get_tabs()
        if not self.tabs or tab_index >= len(self.tabs):
            return None
        ws_url = self.tabs[tab_index].get('webSocketDebuggerUrl')
        if ws_url:
            self.ws_url = ws_url
            return ws_url
        return None

    def _connect_websocket(self) -> Optional[websocket.WebSocket]:
        if not self.ws_url:
            return None
        try:
            ws = websocket.create_connection(
                self.ws_url,
                timeout=10,
                header={"Origin": f"http://127.0.0.1:{self.port}"}
            )
            return ws
        except Exception as e:
            print(f"❌ WebSocket connection error: {e}")
            return None

    def _send_cdp_command(self, ws: websocket.WebSocket, method: str, params: Dict = None) -> Dict:
        self._command_counter += 1
        cmd = {
            "id": self._command_counter,
            "method": method,
            "params": params or {}
        }
        ws.send(json.dumps(cmd))
        while True:
            try:
                response = ws.recv()
                data = json.loads(response)
                if 'id' in data and data['id'] == self._command_counter:
                    return data
            except:
                continue

    def extract_all_messages(self, tab_index: int = 0, max_scrolls: int = 50) -> List[Dict]:
        """
        Extract all messages from DeepSeek chat with proper role detection
        """
        print("🎯 Extracting DeepSeek chat messages...")
        
        ws_url = self.get_websocket_url(tab_index)
        if not ws_url:
            return []
        
        ws = self._connect_websocket()
        if not ws:
            return []
        
        try:
            self._send_cdp_command(ws, "Runtime.enable")
            
            script = f"""
            (async function() {{
                const maxScrolls = {max_scrolls};
                const allMessages = [];
                const seenHashes = new Set();
                let scrollCount = 0;
                let noNewCount = 0;
                
                // DeepSeek specific selectors
                function findMessages() {{
                    const messages = [];
                    
                    // Try data attributes first (most reliable)
                    const userSelectors = [
                        '[data-role="user"]',
                        '[data-message-role="user"]',
                        '.chat-message-user',
                        '.message-user',
                        '.user-message'
                    ];
                    
                    const assistantSelectors = [
                        '[data-role="assistant"]',
                        '[data-message-role="assistant"]',
                        '.chat-message-assistant',
                        '.message-assistant',
                        '.assistant-message'
                    ];
                    
                    // Get user messages
                    for (const selector of userSelectors) {{
                        const elements = document.querySelectorAll(selector);
                        if (elements.length > 0) {{
                            elements.forEach(el => {{
                                const text = el.textContent?.trim() || '';
                                if (text.length > 10) {{
                                    messages.push({{
                                        text: text,
                                        role: 'user',
                                        selector: selector
                                    }});
                                }}
                            }});
                            break;
                        }}
                    }}
                    
                    // Get assistant messages
                    for (const selector of assistantSelectors) {{
                        const elements = document.querySelectorAll(selector);
                        if (elements.length > 0) {{
                            elements.forEach(el => {{
                                const text = el.textContent?.trim() || '';
                                if (text.length > 10) {{
                                    messages.push({{
                                        text: text,
                                        role: 'assistant',
                                        selector: selector
                                    }});
                                }}
                            }});
                            break;
                        }}
                    }}
                    
                    // If nothing found, try generic selectors
                    if (messages.length === 0) {{
                        const genericSelectors = [
                            '[data-testid="message"]',
                            '[role="article"]',
                            '.prose',
                            '.markdown-body'
                        ];
                        
                        for (const selector of genericSelectors) {{
                            const elements = document.querySelectorAll(selector);
                            if (elements.length > 0) {{
                                elements.forEach(el => {{
                                    const text = el.textContent?.trim() || '';
                                    const classes = el.className || '';
                                    let role = 'unknown';
                                    
                                    if (classes.includes('user')) role = 'user';
                                    else if (classes.includes('assistant')) role = 'assistant';
                                    
                                    if (text.length > 10) {{
                                        messages.push({{
                                            text: text,
                                            role: role,
                                            selector: selector
                                        }});
                                    }}
                                }});
                                break;
                            }}
                        }}
                    }}
                    
                    return messages;
                }}
                
                // Get initial messages
                let initialMessages = findMessages();
                initialMessages.forEach(msg => {{
                    const hash = msg.text.substring(0, 100);
                    if (!seenHashes.has(hash)) {{
                        seenHashes.add(hash);
                        allMessages.push(msg);
                    }}
                }});
                
                console.log(`Initial messages: ${{allMessages.length}}`);
                
                // Scroll to load more
                while (scrollCount < maxScrolls) {{
                    // Find scrollable container
                    const containers = document.querySelectorAll(
                        '.scroll-container, .chat-container, .message-list, ' +
                        '.overflow-y-auto, .flex-1.overflow-y-auto'
                    );
                    
                    if (containers.length > 0) {{
                        const container = containers[0];
                        const oldHeight = container.scrollHeight;
                        container.scrollTop = container.scrollHeight;
                        
                        // Wait for content to load
                        await new Promise(resolve => setTimeout(resolve, 1000));
                        
                        // Check if we loaded new content
                        const newHeight = container.scrollHeight;
                        if (newHeight === oldHeight && scrollCount > 3) {{
                            noNewCount++;
                        }}
                    }} else {{
                        // Fallback: scroll window
                        const oldHeight = document.documentElement.scrollHeight;
                        window.scrollTo(0, document.documentElement.scrollHeight);
                        await new Promise(resolve => setTimeout(resolve, 1000));
                        
                        const newHeight = document.documentElement.scrollHeight;
                        if (newHeight === oldHeight && scrollCount > 3) {{
                            noNewCount++;
                        }}
                    }}
                    
                    scrollCount++;
                    
                    // Extract messages after scroll
                    const currentMessages = findMessages();
                    let newCount = 0;
                    
                    currentMessages.forEach(msg => {{
                        const hash = msg.text.substring(0, 100);
                        if (!seenHashes.has(hash)) {{
                            seenHashes.add(hash);
                            allMessages.push(msg);
                            newCount++;
                        }}
                    }});
                    
                    if (newCount === 0) {{
                        noNewCount++;
                    }} else {{
                        noNewCount = 0;
                        console.log(`Found ${{newCount}} new messages. Total: ${{allMessages.length}}`);
                    }}
                    
                    if (noNewCount >= 3 && scrollCount > 5) {{
                        console.log('No new messages found, stopping scroll');
                        break;
                    }}
                }}
                
                // Deduplicate and order messages
                const uniqueMessages = [];
                const seenTexts = new Set();
                
                // Reverse to get chronological order (oldest first)
                for (let i = allMessages.length - 1; i >= 0; i--) {{
                    const msg = allMessages[i];
                    const key = msg.text.substring(0, 50);
                    if (!seenTexts.has(key)) {{
                        seenTexts.add(key);
                        uniqueMessages.push(msg);
                    }}
                }}
                
                console.log(`Total unique messages: ${{uniqueMessages.length}}`);
                
                return {{
                    messages: uniqueMessages,
                    total: uniqueMessages.length,
                    scrolls: scrollCount
                }};
            }})()
            """
            
            cmd = {
                "method": "Runtime.evaluate",
                "params": {
                    "expression": script,
                    "returnByValue": True,
                    "awaitPromise": True
                }
            }
            
            print("⏳ Scrolling and extracting messages...")
            result = self._send_cdp_command(ws, "Runtime.evaluate", cmd["params"])
            ws.close()
            
            if result and 'result' in result and 'result' in result['result']:
                data = result['result']['result'].get('value', {})
                messages = data.get('messages', [])
                total = data.get('total', 0)
                scrolls = data.get('scrolls', 0)
                
                print(f"✅ Extracted {total} messages after {scrolls} scrolls")
                return messages
            
            return []
            
        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()
            if ws:
                ws.close()
            return []

    def save_formatted_output(self, messages: List[Dict], base_filename: str = None):
        """Save messages in multiple formats"""
        if not messages:
            print("❌ No messages to save")
            return
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        if not base_filename:
            base_filename = f"deepseek_chat_{timestamp}"
        
        # Separate messages by role
        user_msgs = [m for m in messages if m.get('role') == 'user']
        assistant_msgs = [m for m in messages if m.get('role') == 'assistant']
        unknown_msgs = [m for m in messages if m.get('role') == 'unknown']
        
        # 1. Save as JSON
        json_file = f"{base_filename}.json"
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump({
                'timestamp': datetime.now().isoformat(),
                'total_messages': len(messages),
                'user_messages': len(user_msgs),
                'assistant_messages': len(assistant_msgs),
                'unknown_messages': len(unknown_msgs),
                'messages': messages
            }, f, indent=2, ensure_ascii=False)
        print(f"✅ Saved JSON: {json_file}")
        
        # 2. Save as formatted text
        txt_file = f"{base_filename}.txt"
        with open(txt_file, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write("DEEPSEEK CHAT EXPORT\n")
            f.write(f"Exported: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Total Messages: {len(messages)}\n")
            f.write(f"User Messages: {len(user_msgs)}\n")
            f.write(f"Assistant Messages: {len(assistant_msgs)}\n")
            f.write("=" * 80 + "\n\n")
            
            for i, msg in enumerate(messages, 1):
                role = msg.get('role', 'UNKNOWN').upper()
                text = msg.get('text', '')
                
                f.write(f"[{i}] {role}:\n")
                f.write(text + "\n\n")
                f.write("-" * 60 + "\n\n")
        print(f"✅ Saved Text: {txt_file}")
        
        # 3. Save as Markdown (for readability)
        md_file = f"{base_filename}.md"
        with open(md_file, 'w', encoding='utf-8') as f:
            f.write("# DeepSeek Chat Export\n\n")
            f.write(f"**Exported:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write(f"**Total Messages:** {len(messages)}\n\n")
            f.write("---\n\n")
            
            for i, msg in enumerate(messages, 1):
                role = msg.get('role', 'unknown').capitalize()
                text = msg.get('text', '')
                
                if role.lower() == 'user':
                    f.write(f"## 👤 User Message {i}\n\n")
                else:
                    f.write(f"## 🤖 Assistant Response {i}\n\n")
                
                f.write(text + "\n\n")
                f.write("---\n\n")
        print(f"✅ Saved Markdown: {md_file}")

def main():
    print("🎯 DeepSeek Chat Extractor - Production")
    print("=" * 80)
    print("Extracts complete chat history with proper formatting")
    print("=" * 80)
    
    port_input = input("🔌 Chrome debug port (default 9227): ").strip()
    port = int(port_input) if port_input else 9227
    
    extractor = DeepSeekChatExtractor(port)
    
    print(f"\n📡 Connecting to Chrome on port {port}...")
    tabs = extractor.get_tabs()
    
    if not tabs:
        print("❌ No tabs found. Make sure Chrome is running with:")
        print(f"   chromium-browser --remote-debugging-port={port}")
        return
    
    print(f"\n✅ Found {len(tabs)} tabs:")
    for i, tab in enumerate(tabs):
        title = tab.get('title', 'Untitled')[:70]
        url = tab.get('url', '')[:70]
        print(f"  [{i}] {title}")
        print(f"      URL: {url}")
        print()
    
    tab_input = input(f"📑 Select tab (0-{len(tabs)-1}, default 0): ").strip()
    tab_index = int(tab_input) if tab_input else 0
    
    scroll_input = input("📜 Max scrolls (default 30): ").strip()
    max_scrolls = int(scroll_input) if scroll_input else 30
    
    print("\n" + "=" * 80)
    messages = extractor.extract_all_messages(tab_index, max_scrolls)
    
    if not messages:
        print("\n❌ No messages extracted.")
        print("\n💡 Troubleshooting tips:")
        print("  1. Make sure you're on a DeepSeek chat page")
        print("  2. Wait for messages to fully load")
        print("  3. Try scrolling down manually first")
        print("  4. Check that Chrome debugging is enabled")
        return
    
    print("\n" + "=" * 80)
    print("📊 EXTRACTION SUMMARY")
    print("=" * 80)
    
    user_msgs = [m for m in messages if m.get('role') == 'user']
    assistant_msgs = [m for m in messages if m.get('role') == 'assistant']
    unknown_msgs = [m for m in messages if m.get('role') == 'unknown']
    
    print(f"Total Messages:  {len(messages)}")
    print(f"User Messages:   {len(user_msgs)}")
    print(f"Assistant Msgs:  {len(assistant_msgs)}")
    print(f"Unknown:         {len(unknown_msgs)}")
    
    print("\n📝 PREVIEW (first 3 messages):")
    print("-" * 80)
    for i, msg in enumerate(messages[:3], 1):
        role = msg.get('role', 'unknown').upper()
        text = msg.get('text', '')[:200]
        print(f"[{i}] {role}: {text}...")
        print()
    
    if len(messages) > 3:
        print(f"... and {len(messages)-3} more messages")
    
    print("\n" + "=" * 80)
    save = input("💾 Save messages to file? (y/n): ").strip().lower()
    
    if save == 'y':
        name_input = input("📁 Filename prefix (default: deepseek_chat): ").strip()
        prefix = name_input if name_input else "deepseek_chat"
        
        extractor.save_formatted_output(messages, prefix)
        print("\n✅ All files saved successfully!")
    
    print("\n👋 Done!")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Interrupted. Goodbye!")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
