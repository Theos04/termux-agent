#!/usr/bin/env python3
"""
NotebookLM Content Extractor - Robust Extraction for NotebookLM
Specifically designed for extracting AI-generated content from NotebookLM
"""

import json
import subprocess
import sys
import time
import re
from typing import Optional, Dict, List, Any
from datetime import datetime
from dataclasses import dataclass, asdict

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

@dataclass
class ContentSection:
    """Represents a content section with its type and content"""
    heading: str
    content: List[str]
    section_type: str  # 'script', 'outline', 'titles', 'thumbnail', 'notes', 'cta', 'other'

@dataclass
class ExtractedContent:
    """Complete extracted content structure"""
    full_text: str
    sections: List[ContentSection]
    raw_messages: List[Dict]
    metadata: Dict

class NotebookLMContentExtractor:
    def __init__(self, port: int = 9227):
        self.port = port
        self.base_url = f"http://127.0.0.1:{port}"
        self.ws_url = None
        self.tabs = []
        self._command_counter = 0

    def get_tabs(self) -> List[Dict]:
        """Get all browser tabs"""
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
        """Get WebSocket URL for the specified tab"""
        self.get_tabs()
        if not self.tabs or tab_index >= len(self.tabs):
            return None
        ws_url = self.tabs[tab_index].get('webSocketDebuggerUrl')
        if ws_url:
            self.ws_url = ws_url
            return ws_url
        return None

    def _connect_websocket(self) -> Optional[websocket.WebSocket]:
        """Establish WebSocket connection"""
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
        """Send CDP command and wait for response"""
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

    def extract_notebooklm_content(self, tab_index: int = 0) -> ExtractedContent:
        """
        Extract all content from NotebookLM with proper structure
        """
        print("🎯 Extracting NotebookLM content...")

        ws_url = self.get_websocket_url(tab_index)
        if not ws_url:
            return ExtractedContent(
                full_text="",
                sections=[],
                raw_messages=[],
                metadata={"error": "No WebSocket connection"}
            )

        ws = self._connect_websocket()
        if not ws:
            return ExtractedContent(
                full_text="",
                sections=[],
                raw_messages=[],
                metadata={"error": "Failed to connect"}
            )

        try:
            self._send_cdp_command(ws, "Runtime.enable")

            # Enhanced extraction script specifically for NotebookLM
            extraction_script = """
            (function() {
                'use strict';

                // Configuration
                const config = {
                    // NotebookLM specific selectors
                    contentSelectors: [
                        // Primary content containers
                        'labs-tailwind-doc-viewer',
                        'element-list-renderer',
                        'labs-tailwind-structural-element-view-v2',
                        'paragraph-element-view',

                        // Content elements
                        '.paragraph',
                        '[role="heading"]',
                        '.list-item',

                        // DeepSeek/chat specific
                        '[data-message-role]',
                        '.message-content',
                        '.prose',
                        '.markdown-body',

                        // Fallback containers
                        '.content',
                        '.main-content',
                        '.document-content'
                    ],
                    // Patterns to exclude (UI noise)
                    excludePatterns: [
                        'Save to note',
                        'copy_all',
                        'thumb_up',
                        'thumb_down',
                        'Loading',
                        'Recently used',
                        'No emoji found',
                        'Search results',
                        'Dismiss',
                        'Good response',
                        'Bad response',
                        'Click to open citation details',
                        '1 source',
                        'arrow_forward',
                        'landscape_2',
                        'photo_spark',
                        'keep_pin'
                    ],
                    // Pattern to identify section headings
                    headingPatterns: [
                        /^Titles$/i,
                        /^Thumbnail Ideas$/i,
                        /^Outline$/i,
                        /^Full Script$/i,
                        /^Editor Notes$/i,
                        /^CTA$/i,
                        /^Introduction$/i,
                        /^Chapter \\d+/i,
                        /^Opening Hook$/i,
                        /^Ending$/i,
                        /^Call to Action$/i
                    ]
                };

                // Helper functions
                function isExcluded(text) {
                    if (!text || text.length < 3) return true;
                    const trimmed = text.trim();
                    for (const pattern of config.excludePatterns) {
                        if (trimmed.includes(pattern)) return true;
                    }
                    return false;
                }

                function cleanText(text) {
                    if (!text) return '';
                    // Remove excessive whitespace
                    text = text.replace(/\\s+/g, ' ').trim();
                    // Remove citation markers like [1], [2] etc. if needed
                    text = text.replace(/\\[\\d+\\]/g, '');
                    return text;
                }

                function getSectionType(heading) {
                    const h = heading.toLowerCase();
                    if (h.includes('title')) return 'titles';
                    if (h.includes('thumbnail')) return 'thumbnail';
                    if (h.includes('outline')) return 'outline';
                    if (h.includes('script')) return 'script';
                    if (h.includes('editor')) return 'notes';
                    if (h.includes('cta')) return 'cta';
                    return 'other';
                }

                // Main extraction logic
                function extractContent() {
                    const result = {
                        sections: [],
                        messages: [],
                        fullText: '',
                        metadata: {
                            url: window.location.href,
                            title: document.title,
                            timestamp: new Date().toISOString()
                        }
                    };

                    // Method 1: Try NotebookLM specific structure
                    const docViewer = document.querySelector('labs-tailwind-doc-viewer');
                    if (docViewer) {
                        console.log('📄 Found NotebookLM document viewer');
                        const elements = docViewer.querySelectorAll('.paragraph');
                        let currentSection = null;
                        let currentContent = [];

                        elements.forEach((el) => {
                            const text = cleanText(el.textContent);
                            if (!text || isExcluded(text)) return;

                            const isHeading = el.getAttribute('role') === 'heading';

                            if (isHeading) {
                                // Save previous section
                                if (currentSection && currentContent.length > 0) {
                                    result.sections.push({
                                        heading: currentSection,
                                        content: currentContent,
                                        type: getSectionType(currentSection)
                                    });
                                }
                                currentSection = text;
                                currentContent = [];
                            } else {
                                // Check if it's a list item
                                if (el.classList.contains('list-item')) {
                                    currentContent.push(`• ${text}`);
                                } else {
                                    currentContent.push(text);
                                }
                            }
                        });

                        // Save last section
                        if (currentSection && currentContent.length > 0) {
                            result.sections.push({
                                heading: currentSection,
                                content: currentContent,
                                type: getSectionType(currentSection)
                            });
                        }
                    }

                    // Method 2: Try to find chat messages (for DeepSeek chat)
                    const messageSelectors = [
                        '[data-message-role="user"]',
                        '[data-message-role="assistant"]',
                        '.message-user',
                        '.message-assistant',
                        '.chat-message'
                    ];

                    for (const selector of messageSelectors) {
                        const msgElements = document.querySelectorAll(selector);
                        if (msgElements.length > 0) {
                            msgElements.forEach((el) => {
                                const text = cleanText(el.textContent);
                                if (!text || isExcluded(text) || text.length < 20) return;

                                const role = el.getAttribute('data-message-role') ||
                                           (el.classList.contains('message-user') ? 'user' :
                                            el.classList.contains('message-assistant') ? 'assistant' : 'unknown');

                                result.messages.push({
                                    role: role,
                                    content: text,
                                    length: text.length
                                });
                            });
                            break;
                        }
                    }

                    // If no structured content found, fallback to text extraction
                    if (result.sections.length === 0 && result.messages.length === 0) {
                        console.log('🔄 Falling back to text extraction');
                        const allText = document.body.textContent;
                        const lines = allText.split('\\n')
                            .map(l => l.trim())
                            .filter(l => l && !isExcluded(l));

                        // Try to identify sections from the text
                        let currentSection = 'General';
                        let currentContent = [];

                        for (const line of lines) {
                            // Check if it's a heading
                            const isHeading = config.headingPatterns.some(p => p.test(line));
                            if (isHeading) {
                                if (currentContent.length > 0) {
                                    result.sections.push({
                                        heading: currentSection,
                                        content: currentContent,
                                        type: getSectionType(currentSection)
                                    });
                                }
                                currentSection = line;
                                currentContent = [];
                            } else {
                                currentContent.push(line);
                            }
                        }

                        if (currentContent.length > 0) {
                            result.sections.push({
                                heading: currentSection,
                                content: currentContent,
                                type: getSectionType(currentSection)
                            });
                        }
                    }

                    // Build full text
                    let fullTextParts = [];
                    for (const section of result.sections) {
                        fullTextParts.push(section.heading);
                        fullTextParts.push('---');
                        fullTextParts.push(section.content.join('\\n\\n'));
                        fullTextParts.push('');
                    }
                    result.fullText = fullTextParts.join('\\n');

                    return result;
                }

                return extractContent();
            })()
            """

            cmd = {
                "method": "Runtime.evaluate",
                "params": {
                    "expression": extraction_script,
                    "returnByValue": True,
                    "awaitPromise": False
                }
            }

            result = self._send_cdp_command(ws, "Runtime.evaluate", cmd["params"])
            ws.close()

            if result and 'result' in result and 'result' in result['result']:
                data = result['result']['result'].get('value', {})
                
                # Convert to ExtractedContent
                sections = []
                for section_data in data.get('sections', []):
                    sections.append(ContentSection(
                        heading=section_data.get('heading', 'Unknown'),
                        content=section_data.get('content', []),
                        section_type=section_data.get('type', 'other')
                    ))

                extracted = ExtractedContent(
                    full_text=data.get('fullText', ''),
                    sections=sections,
                    raw_messages=data.get('messages', []),
                    metadata=data.get('metadata', {})
                )

                print(f"✅ Extracted {len(sections)} sections and {len(extracted.raw_messages)} messages")
                return extracted

            return ExtractedContent(
                full_text="",
                sections=[],
                raw_messages=[],
                metadata={"error": "Extraction failed"}
            )

        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()
            if ws:
                ws.close()
            return ExtractedContent(
                full_text="",
                sections=[],
                raw_messages=[],
                metadata={"error": str(e)}
            )

    def extract_by_section(self, content: ExtractedContent, section_type: str) -> Optional[ContentSection]:
        """Extract specific section by type"""
        for section in content.sections:
            if section.section_type == section_type:
                return section
        return None

    def get_full_script(self, content: ExtractedContent) -> str:
        """Get the full script content"""
        script_section = self.extract_by_section(content, 'script')
        if script_section:
            return '\n\n'.join(script_section.content)
        
        # Fallback: look for script section by heading
        for section in content.sections:
            if 'script' in section.heading.lower():
                return '\n\n'.join(section.content)
        return ''

def print_extracted_content(content: ExtractedContent):
    """Pretty print extracted content"""
    print("\n" + "=" * 60)
    print("📄 EXTRACTED CONTENT SUMMARY")
    print("=" * 60)

    print(f"📊 Sections: {len(content.sections)}")
    print(f"💬 Messages: {len(content.raw_messages)}")
    print(f"📝 Full text length: {len(content.full_text)} characters")

    print("\n📑 SECTIONS:")
    for section in content.sections:
        print(f"  • {section.heading} ({section.section_type}) - {len(section.content)} items")

    # Show script preview
    script = content.sections[-1] if content.sections else None
    if script:
        print("\n📜 SCRIPT PREVIEW:")
        preview = '\n'.join(script.content[:5])
        print(preview[:500] + "..." if len(preview) > 500 else preview)

def save_extracted_content(content: ExtractedContent, filename_prefix: str = "notebooklm"):
    """Save extracted content to files"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    # Save full JSON
    json_file = f"{filename_prefix}_{timestamp}.json"
    with open(json_file, 'w', encoding='utf-8') as f:
        # Convert dataclasses to dicts
        data = {
            'timestamp': timestamp,
            'metadata': content.metadata,
            'sections': [
                {
                    'heading': s.heading,
                    'content': s.content,
                    'type': s.section_type
                }
                for s in content.sections
            ],
            'messages': content.raw_messages,
            'full_text': content.full_text
        }
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"✅ Saved to {json_file}")

    # Save formatted text
    txt_file = f"{filename_prefix}_{timestamp}.txt"
    with open(txt_file, 'w', encoding='utf-8') as f:
        f.write("NOTEBOOKLM CONTENT EXPORT\n")
        f.write("=" * 60 + "\n\n")
        f.write(f"Exported: {timestamp}\n")
        f.write(f"URL: {content.metadata.get('url', 'Unknown')}\n\n")
        f.write("=" * 60 + "\n\n")

        for section in content.sections:
            f.write(f"\n{'='*60}\n")
            f.write(f"📌 {section.heading}\n")
            f.write(f"{'='*60}\n\n")
            f.write('\n\n'.join(section.content))
            f.write('\n\n')

        if content.raw_messages:
            f.write("\n" + "=" * 60 + "\n")
            f.write("💬 CHAT MESSAGES\n")
            f.write("=" * 60 + "\n\n")
            for msg in content.raw_messages:
                role = msg.get('role', 'unknown').upper()
                f.write(f"[{role}]\n{msg.get('content', '')}\n\n")
                f.write("-" * 40 + "\n\n")

    print(f"✅ Saved text version to {txt_file}")

def main():
    print("🎯 NotebookLM Content Extractor")
    print("=" * 60)
    print("📚 Specialized for extracting AI-generated content from NotebookLM")

    # Get port
    port_input = input("\n🔌 Chrome debug port (default 9227): ").strip()
    port = int(port_input) if port_input else 9227

    extractor = NotebookLMContentExtractor(port)

    # Connect and list tabs
    print(f"\n📡 Connecting to Chrome on port {port}...")
    tabs = extractor.get_tabs()

    if not tabs:
        print("❌ No tabs found. Make sure Chrome is running with --remote-debugging-port")
        return

    print(f"\n✅ Found {len(tabs)} tabs:")
    for i, tab in enumerate(tabs):
        title = tab.get('title', 'Untitled')[:70]
        url = tab.get('url', '')[:70]
        print(f"  [{i}] {title}")
        print(f"      URL: {url}")

    # Select tab
    tab_input = input(f"\n📑 Select tab (0-{len(tabs)-1}, default 0): ").strip()
    tab_index = int(tab_input) if tab_input else 0

    # Extract content
    print("\n🔍 Extracting content from NotebookLM...")
    content = extractor.extract_notebooklm_content(tab_index)

    if not content.sections and not content.raw_messages:
        print("\n❌ No content extracted. Try:")
        print("  1. Make sure the NotebookLM page is fully loaded")
        print("  2. Try selecting a different tab")
        print("  3. Refresh the page and try again")
        return

    # Display summary
    print_extracted_content(content)

    # Offer to save
    save = input("\n💾 Save content to files? (y/n): ").strip().lower()
    if save == 'y':
        prefix = input("📝 Filename prefix (default: notebooklm): ").strip() or "notebooklm"
        save_extracted_content(content, prefix)

    # Offer to extract specific parts
    while True:
        action = input("\n🔧 Actions: [s]cript, [o]utline, [t]itles, [n]otes, [f]ull text, [q]uit: ").strip().lower()
        
        if action == 'q':
            break
        elif action == 's':
            script = extractor.get_full_script(content)
            print("\n📜 FULL SCRIPT:\n")
            print(script[:1000] + "..." if len(script) > 1000 else script)
        elif action == 'o':
            outline = extractor.extract_by_section(content, 'outline')
            if outline:
                print(f"\n📋 OUTLINE ({len(outline.content)} items):\n")
                for item in outline.content:
                    print(f"  • {item}")
            else:
                print("❌ Outline section not found")
        elif action == 't':
            titles = extractor.extract_by_section(content, 'titles')
            if titles:
                print(f"\n📌 TITLES ({len(titles.content)} items):\n")
                for item in titles.content:
                    print(f"  • {item}")
            else:
                print("❌ Titles section not found")
        elif action == 'n':
            notes = extractor.extract_by_section(content, 'notes')
            if notes:
                print(f"\n📝 EDITOR NOTES ({len(notes.content)} items):\n")
                for item in notes.content:
                    print(f"  • {item}")
            else:
                print("❌ Editor notes section not found")
        elif action == 'f':
            print("\n📄 FULL TEXT:\n")
            print(content.full_text[:2000] + "..." if len(content.full_text) > 2000 else content.full_text)

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
