#!/usr/bin/env python3
"""
DeepSeek Chat Extractor - Targeted Extraction
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

    def extract_chat_messages(self, tab_index: int = 0) -> List[Dict]:
        """
        Extract actual chat messages with proper role identification
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
            
            script = """
            (function() {
                const messages = [];
                
                // Find all message containers
                // DeepSeek uses specific class names and data attributes
                const selectors = [
                    // Try to find by data attributes first (most specific)
                    '[data-testid="message"]',
                    '[data-role="user"]',
                    '[data-role="assistant"]',
                    '[data-message-role="user"]',
                    '[data-message-role="assistant"]',
                    
                    // Try by class names
                    '.chat-message-user',
                    '.chat-message-assistant',
                    '.message-user',
                    '.message-assistant',
                    '.user-message',
                    '.assistant-message',
                    
                    // Try by role attribute
                    '[role="article"]',
                    '[role="listitem"]',
                    
                    // Last resort - find by looking at the DOM structure
                    '.prose',
                    '.markdown-body'
                ];
                
                let elements = [];
                let foundSelector = '';
                
                for (const selector of selectors) {
                    const found = document.querySelectorAll(selector);
                    if (found.length > 0) {
                        elements = found;
                        foundSelector = selector;
                        console.log(`Found ${found.length} elements with selector: ${selector}`);
                        break;
                    }
                }
                
                // If no elements found, try to find by scanning all divs
                if (elements.length === 0) {
                    console.log('Trying fallback: scanning all divs');
                    const allDivs = document.querySelectorAll('div');
                    const candidates = [];
                    
                    for (const div of allDivs) {
                        const text = div.textContent || '';
                        const classes = div.className || '';
                        
                        // Look for divs that contain chat-like content
                        if (text.length > 20 && 
                            (classes.includes('chat') || 
                             classes.includes('message') || 
                             classes.includes('conversation') ||
                             classes.includes('response') ||
                             classes.includes('answer'))) {
                            candidates.push(div);
                        }
                    }
                    
                    if (candidates.length > 0) {
                        elements = candidates;
                        foundSelector = 'div (scanned)';
                        console.log(`Found ${elements.length} candidate divs`);
                    }
                }
                
                // Process each element
                const seenTexts = new Set();
                let userCount = 0;
                let assistantCount = 0;
                let unknownCount = 0;
                
                elements.forEach((el, index) => {
                    // Get the text content
                    let text = el.textContent || '';
                    text = text.trim();
                    
                    // Skip empty or very short texts
                    if (text.length < 15) return;
                    
                    // Try to determine role
                    let role = 'unknown';
                    const classes = el.className || '';
                    const dataRole = el.getAttribute('data-role') || '';
                    const dataMessageRole = el.getAttribute('data-message-role') || '';
                    const roleAttr = el.getAttribute('role') || '';
                    
                    // Check for role indicators
                    if (classes.includes('user') || 
                        classes.includes('human') || 
                        dataRole === 'user' || 
                        dataMessageRole === 'user') {
                        role = 'user';
                        userCount++;
                    } else if (classes.includes('assistant') || 
                               classes.includes('bot') || 
                               classes.includes('response') || 
                               classes.includes('answer') ||
                               dataRole === 'assistant' || 
                               dataMessageRole === 'assistant') {
                        role = 'assistant';
                        assistantCount++;
                    } else {
                        // Try to guess by content
                        const lowerText = text.toLowerCase();
                        // User messages often start with questions or are shorter
                        if (lowerText.includes('?') && text.length < 200) {
                            role = 'user';
                            userCount++;
                        } else if (text.length > 100) {
                            role = 'assistant';
                            assistantCount++;
                        } else {
                            unknownCount++;
                        }
                    }
                    
                    // Use text hash to deduplicate
                    const hash = text.substring(0, 50);
                    if (!seenTexts.has(hash)) {
                        seenTexts.add(hash);
                        
                        // Try to find a timestamp
                        const timeMatch = text.match(/\d{1,2}:\d{2}/);
                        const time = timeMatch ? timeMatch[0] : null;
                        
                        messages.push({
                            role: role,
                            text: text,
                            length: text.length,
                            time: time,
                            index: index,
                            classes: classes.substring(0, 100),
                            selector: foundSelector
                        });
                    }
                });
                
                console.log(`User messages: ${userCount}, Assistant: ${assistantCount}, Unknown: ${unknownCount}`);
                
                return {
                    messages: messages,
                    total: messages.length,
                    userCount: userCount,
                    assistantCount: assistantCount,
                    unknownCount: unknownCount,
                    selectorUsed: foundSelector
                };
            })()
            """
            
            cmd = {
                "method": "Runtime.evaluate",
                "params": {
                    "expression": script,
                    "returnByValue": True,
                    "awaitPromise": False
                }
            }
            
            result = self._send_cdp_command(ws, "Runtime.evaluate", cmd["params"])
            ws.close()
            
            if result and 'result' in result and 'result' in result['result']:
                data = result['result']['result'].get('value', {})
                messages = data.get('messages', [])
                total = data.get('total', 0)
                selector = data.get('selectorUsed', 'unknown')
                
                print(f"✅ Extracted {total} messages using selector: {selector}")
                print(f"   User: {data.get('userCount', 0)}")
                print(f"   Assistant: {data.get('assistantCount', 0)}")
                print(f"   Unknown: {data.get('unknownCount', 0)}")
                
                return messages
            
            return []
            
        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()
            if ws:
                ws.close()
            return []

    def extract_with_scroll(self, tab_index: int = 0, max_scrolls: int = 30) -> List[Dict]:
        """
        Scroll and extract messages with improved scrolling
        """
        print(f"📜 Scrolling and extracting (max {max_scrolls} scrolls)...")
        
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
                let allMessages = [];
                let seenHashes = new Set();
                let scrollCount = 0;
                let noNewCount = 0;
                
                function getMessageTexts() {{
                    const messages = [];
                    
                    // DeepSeek specific selectors
                    const selectors = [
                        '[data-testid="message"]',
                        '[data-role="user"]',
                        '[data-role="assistant"]',
                        '.chat-message-user',
                        '.chat-message-assistant',
                        '.prose',
                        '.markdown-body'
                    ];
                    
                    let elements = [];
                    for (const selector of selectors) {{
                        const found = document.querySelectorAll(selector);
                        if (found.length > 0) {{
                            elements = found;
                            break;
                        }}
                    }}
                    
                    if (elements.length === 0) {{
                        // Fallback: find any div with chat-like content
                        const allDivs = document.querySelectorAll('div');
                        for (const div of allDivs) {{
                            const text = div.textContent || '';
                            const classes = div.className || '';
                            if (text.length > 50 && 
                                (classes.includes('chat') || 
                                 classes.includes('message') || 
                                 classes.includes('conversation'))) {{
                                elements.push(div);
                            }}
                        }}
                    }}
                    
                    // Extract text and role
                    elements.forEach(el => {{
                        let text = el.textContent || '';
                        text = text.trim();
                        
                        if (text.length < 20) return;
                        
                        let role = 'unknown';
                        const classes = el.className || '';
                        const dataRole = el.getAttribute('data-role') || '';
                        
                        if (classes.includes('user') || dataRole === 'user') {{
                            role = 'user';
                        }} else if (classes.includes('assistant') || dataRole === 'assistant') {{
                            role = 'assistant';
                        }}
                        
                        messages.push({{
                            text: text,
                            role: role,
                            length: text.length
                        }});
                    }});
                    
                    return messages;
                }}
                
                while (scrollCount < maxScrolls) {{
                    const currentMessages = getMessageTexts();
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
                        console.log(`Found {{{{newCount}}}} new messages. Total: {{{{allMessages.length}}}}`);
                    }}
                    
                    if (noNewCount >= 3 && scrollCount > 5) {{
                        console.log('No new messages found, stopping');
                        break;
                    }}
                    
                    // Scroll the main container
                    const containers = document.querySelectorAll('.scroll-container, .chat-container, .message-list');
                    if (containers.length > 0) {{
                        containers[0].scrollTop = containers[0].scrollHeight;
                    }} else {{
                        window.scrollTo(0, document.documentElement.scrollHeight);
                    }}
                    
                    scrollCount++;
                    await new Promise(resolve => setTimeout(resolve, 1200));
                }}
                
                // Final extraction
                const finalMessages = getMessageTexts();
                finalMessages.forEach(msg => {{
                    const hash = msg.text.substring(0, 100);
                    if (!seenHashes.has(hash)) {{
                        seenHashes.add(hash);
                        allMessages.push(msg);
                    }}
                }});
                
                return {{
                    messages: allMessages,
                    total: allMessages.length,
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
            
            print("⏳ Scrolling to load all messages...")
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
            if ws:
                ws.close()
            return []

def main():
    print("🎯 DeepSeek Chat Extractor - Targeted")
    print("=" * 60)
    
    port_input = input("🔌 Chrome debug port (default 9227): ").strip()
    port = int(port_input) if port_input else 9227
    
    extractor = DeepSeekChatExtractor(port)
    
    print(f"\n📡 Connecting to Chrome on port {port}...")
    tabs = extractor.get_tabs()
    
    if not tabs:
        print("❌ No tabs found.")
        return
    
    print(f"✅ Found {len(tabs)} tabs")
    for i, tab in enumerate(tabs):
        title = tab.get('title', 'Untitled')[:60]
        url = tab.get('url', '')[:60]
        print(f"  [{i}] {title}")
        print(f"      URL: {url}")
        print()
    
    tab_input = input(f"\n📑 Select tab (0-{len(tabs)-1}, default 0): ").strip()
    tab_index = int(tab_input) if tab_input else 0
    
    print("\n📝 Choose method:")
    print("  1. Direct Extraction (no scroll)")
    print("  2. Scroll & Extract (load all messages)")
    print()
    
    choice = input("Select (1 or 2, default 2): ").strip() or "2"
    
    if choice == "1":
        messages = extractor.extract_chat_messages(tab_index)
    else:
        scrolls = input("Max scrolls (default 30): ").strip()
        scrolls = int(scrolls) if scrolls else 30
        messages = extractor.extract_with_scroll(tab_index, scrolls)
    
    if not messages:
        print("❌ No messages extracted.")
        print("\n💡 Try these steps:")
        print("  1. Open your DeepSeek chat in Chrome")
        print("  2. Make sure the chat is fully loaded")
        print("  3. Try scrolling down manually first")
        print("  4. Run the script again")
        return
    
    # Process messages
    print(f"\n📊 Extracted {len(messages)} messages")
    
    # Separate by role
    user_msgs = [m for m in messages if m.get('role') == 'user']
    assistant_msgs = [m for m in messages if m.get('role') == 'assistant']
    unknown_msgs = [m for m in messages if m.get('role') == 'unknown']
    
    print(f"   User: {len(user_msgs)}")
    print(f"   Assistant: {len(assistant_msgs)}")
    print(f"   Unknown: {len(unknown_msgs)}")
    
    # Show sample messages
    print("\n📝 Sample messages:")
    for i, msg in enumerate(messages[:5], 1):
        role = msg.get('role', 'unknown').upper()
        text = msg.get('text', '')[:150]
        print(f"  [{i}] {role}: {text}...")
    
    if len(messages) > 5:
        print(f"  ... and {len(messages)-5} more")
    
    # Save
    save = input("\n💾 Save messages to file? (y/n): ").strip().lower()
    if save == 'y':
        filename = f"deepseek_chat_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump({
                'timestamp': datetime.now().isoformat(),
                'total_messages': len(messages),
                'user_messages': len(user_msgs),
                'assistant_messages': len(assistant_msgs),
                'messages': messages
            }, f, indent=2, ensure_ascii=False)
        print(f"✅ Saved to {filename}")
        
        # Also save as readable text
        txt_filename = f"deepseek_chat_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(txt_filename, 'w', encoding='utf-8') as f:
            f.write("DEEPSEEK CHAT EXPORT\n")
            f.write("=" * 60 + "\n\n")
            for i, msg in enumerate(messages, 1):
                role = msg.get('role', 'UNKNOWN').upper()
                text = msg.get('text', '')
                f.write(f"[{i}] {role}:\n{text}\n\n")
                f.write("-" * 40 + "\n\n")
        print(f"✅ Saved text version to {txt_filename}")

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
