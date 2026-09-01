// JavaScript to run in Chrome console
function extractWhatsAppMessages() {
    const messages = [];
    
    // Find all message containers
    const msgContainers = document.querySelectorAll('[data-testid="msg-container"]');
    
    msgContainers.forEach((container, index) => {
        const msg = {
            index: index,
            sender: null,
            timestamp: null,
            text: null,
            replyTo: null
        };
        
        // Get sender name
        const senderEl = container.querySelector('[data-pre-plain-text]');
        if (senderEl) {
            const plainText = senderEl.getAttribute('data-pre-plain-text');
            const match = plainText.match(/\[([^\]]+)\] ([^:]+):/);
            if (match) {
                msg.timestamp = match[1];
                msg.sender = match[2].trim();
            }
        }
        
        // Get message text
        const textEl = container.querySelector('.selectable-text.copyable-text');
        if (textEl) {
            msg.text = textEl.textContent.trim();
        }
        
        // Get quoted/reply message
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

// Execute and return
extractWhatsAppMessages();
