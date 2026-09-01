(function() {
    console.log('🔍 Searching for "Log in with phone number" in WhatsApp Web...');
    
    // Function to find the element by traversing the DOM tree
    function findElementByText(root, targetText) {
        // Use TreeWalker for more efficient text node searching
        const walker = document.createTreeWalker(
            root,
            NodeFilter.SHOW_TEXT,
            {
                acceptNode: function(node) {
                    const text = node.textContent.trim();
                    if (text === targetText) {
                        return NodeFilter.FILTER_ACCEPT;
                    }
                    return NodeFilter.FILTER_SKIP;
                }
            }
        );
        
        let node = walker.nextNode();
        if (node) {
            // Return the parent element that contains this text
            let parent = node.parentElement;
            // Try to find the actual clickable element (might be several levels up)
            while (parent) {
                // Check if it's a button, link, or has click handler
                if (parent.tagName === 'BUTTON' || 
                    parent.tagName === 'A' || 
                    parent.getAttribute('role') === 'button' ||
                    parent.onclick ||
                    parent.style.cursor === 'pointer') {
                    return parent;
                }
                // If parent has child with the text, and parent is likely clickable
                if (parent.children.length === 1 && parent.children[0] === node.parentElement) {
                    // Check if parent itself is the clickable element
                    if (parent.tagName === 'DIV' && parent.getAttribute('role') === 'button') {
                        return parent;
                    }
                }
                parent = parent.parentElement;
                // Don't go too far up
                if (parent === document.body || parent === document.documentElement) {
                    break;
                }
            }
            // If no clickable parent found, return the immediate parent
            return node.parentElement;
        }
        return null;
    }
    
    // Try to find the element
    let element = findElementByText(document, 'Log in with phone number');
    
    if (!element) {
        // Try with partial match
        const walker = document.createTreeWalker(
            document,
            NodeFilter.SHOW_TEXT,
            {
                acceptNode: function(node) {
                    const text = node.textContent.trim();
                    if (text.includes('Log in with phone number')) {
                        return NodeFilter.FILTER_ACCEPT;
                    }
                    return NodeFilter.FILTER_SKIP;
                }
            }
        );
        
        let node = walker.nextNode();
        if (node) {
            element = node.parentElement;
            // Find clickable ancestor
            let parent = element;
            while (parent && parent !== document.body) {
                if (parent.tagName === 'BUTTON' || 
                    parent.tagName === 'A' || 
                    parent.getAttribute('role') === 'button') {
                    element = parent;
                    break;
                }
                parent = parent.parentElement;
            }
        }
    }
    
    if (element) {
        console.log('✅ Found element:', element);
        console.log('📝 Element details:', {
            tagName: element.tagName,
            className: element.className,
            id: element.id,
            role: element.getAttribute('role'),
            text: element.textContent.trim(),
            innerHTML: element.innerHTML.substring(0, 200)
        });
        
        // Find all ancestors to understand structure
        let ancestors = [];
        let current = element;
        while (current && current !== document.body) {
            ancestors.push({
                tag: current.tagName,
                class: current.className,
                role: current.getAttribute('role')
            });
            current = current.parentElement;
        }
        console.log('📊 Ancestors:', ancestors);
        
        // Try to click with multiple methods
        function clickElement(el) {
            try {
                // Method 1: Standard click
                el.click();
                console.log('✅ Clicked with method 1');
                return true;
            } catch (e) {
                console.log('⚠️ Method 1 failed:', e.message);
            }
            
            try {
                // Method 2: Simulated click event
                const event = new MouseEvent('click', {
                    view: window,
                    bubbles: true,
                    cancelable: true,
                    clientX: 100,
                    clientY: 100
                });
                el.dispatchEvent(event);
                console.log('✅ Clicked with method 2');
                return true;
            } catch (e) {
                console.log('⚠️ Method 2 failed:', e.message);
            }
            
            try {
                // Method 3: Focus and enter
                el.focus();
                const enterEvent = new KeyboardEvent('keydown', {
                    key: 'Enter',
                    code: 'Enter',
                    keyCode: 13,
                    which: 13,
                    bubbles: true
                });
                el.dispatchEvent(enterEvent);
                console.log('✅ Clicked with method 3 (Enter key)');
                return true;
            } catch (e) {
                console.log('⚠️ Method 3 failed:', e.message);
            }
            
            return false;
        }
        
        // Try clicking the element
        const clicked = clickElement(element);
        
        // If that didn't work, try clicking ancestors
        if (!clicked) {
            console.log('🔄 Trying to click ancestors...');
            let parent = element.parentElement;
            let level = 0;
            while (parent && parent !== document.body && level < 5) {
                console.log(`📌 Trying parent level ${level + 1}:`, parent.tagName);
                if (clickElement(parent)) {
                    console.log(`✅ Clicked parent at level ${level + 1}`);
                    break;
                }
                parent = parent.parentElement;
                level++;
            }
        }
        
        // If still not clicked, try to find button by data attributes
        if (!clicked) {
            console.log('🔄 Trying alternative selectors...');
            const selectors = [
                'button[data-testid*="login"]',
                'div[data-testid*="login"]',
                '[data-testid="login"]',
                'button[aria-label*="login"]',
                '[role="button"] span',
                '.login-button'
            ];
            
            for (let selector of selectors) {
                try {
                    const altElement = document.querySelector(selector);
                    if (altElement && altElement.textContent.includes('phone')) {
                        console.log(`📌 Found alternative with selector: ${selector}`);
                        if (clickElement(altElement)) {
                            console.log(`✅ Clicked alternative element`);
                            break;
                        }
                    }
                } catch (e) {
                    // Skip invalid selectors
                }
            }
        }
        
    } else {
        console.log('❌ Could not find "Log in with phone number"');
        console.log('🔍 Searching for any "Login" or "Phone" related elements...');
        
        // Search for any login-related text
        const allElements = document.querySelectorAll('*');
        const relevant = [];
        for (let el of allElements) {
            const text = el.textContent?.trim()?.toLowerCase();
            if (text && (text.includes('login') || text.includes('phone') || text.includes('sign in'))) {
                if (text.length < 100) { // Only short text to avoid huge blocks
                    relevant.push({
                        tag: el.tagName,
                        text: el.textContent.trim().substring(0, 50),
                        class: el.className,
                        id: el.id,
                        role: el.getAttribute('role'),
                        visible: el.offsetParent !== null
                    });
                }
            }
        }
        
        console.log('📊 Found relevant elements:', relevant.slice(0, 20));
        
        // If there's exactly one with "phone number", try clicking it
        if (relevant.length === 1 && relevant[0].text.includes('phone')) {
            const el = document.querySelector(`[class="${relevant[0].class}"]`);
            if (el) {
                console.log('🔄 Trying to click the only phone-related element');
                el.click();
            }
        }
    }
    
    // Check if WhatsApp Web is already logged in
    console.log('🔍 Checking login status...');
    const chatElements = document.querySelectorAll('[data-testid="chat-list"], [data-testid="conversation"]');
    if (chatElements.length > 0) {
        console.log('✅ Already logged in - chat elements found!');
    } else {
        console.log('❌ Not logged in or chat list not loaded yet');
    }
})();
