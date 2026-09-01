import json
import asyncio
import websockets

# The JavaScript to extract messages
js_code = """
function() {
    const messages = [];
    const msgContainers = document.querySelectorAll('[data-testid="msg-container"]');
    msgContainers.forEach((container, index) => {
        const msg = {index: index};
        const senderEl = container.querySelector('[data-pre-plain-text]');
        if (senderEl) {
            const plainText = senderEl.getAttribute('data-pre-plain-text');
            const match = plainText.match(/\\[([^\\]]+)\\] ([^:]+):/);
            if (match) {
                msg.timestamp = match[1];
                msg.sender = match[2].trim();
            }
        }
        const textEl = container.querySelector('.selectable-text.copyable-text');
        if (textEl) {
            msg.text = textEl.textContent.trim();
        }
        const quotedEl = container.querySelector('[data-testid="quoted-message"]');
        if (quotedEl) {
            const replyText = quotedEl.querySelector('.selectable-text');
            if (replyText) {
                msg.replyTo = replyText.textContent.trim();
            }
        }
        if (msg.text || msg.sender) {
            messages.push(msg);
        }
    });
    return messages;
}
"""

print(f"""
📱 WHATSAPP MESSAGE EXTRACTOR (via CDP)
=====================================
Copy this code to your CDP tool:

Option 1 (Execute JavaScript)
Paste the following (without the first and last quotes):

{js_code}

This will extract all visible messages from the current chat.
""")
