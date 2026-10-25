// WhatsApp Web - Click "Log in with phone number" and capture page state
(function() {
    console.log('🔍 Searching for "Log in with phone number"...');
    
    function getPageState() {
        // Get page information
        const state = {
            url: window.location.href,
            title: document.title,
            hasPhoneInput: false,
            hasCountryCode: false,
            phoneInputs: [],
            buttons: [],
            visibleElements: [],
            loginFormPresent: false,
            qrCodePresent: false,
            chatListPresent: false
        };
        
        // Check for phone inputs
        const inputs = document.querySelectorAll('input[type="tel"], input[type="text"], input[type="number"]');
        inputs.forEach(input => {
            const placeholder = input.placeholder?.toLowerCase() || '';
            const id = input.id?.toLowerCase() || '';
            const name = input.name?.toLowerCase() || '';
            
            if (placeholder.includes('phone') || 
                placeholder.includes('number') ||
                id.includes('phone') || 
                id.includes('number') ||
                name.includes('phone') || 
                name.includes('number')) {
                state.hasPhoneInput = true;
                state.phoneInputs.push({
                    type: input.type,
                    placeholder: input.placeholder,
                    id: input.id,
                    name: input.name,
                    value: input.value
                });
            }
        });
        
        // Check for country code selector
        const countrySelectors = document.querySelectorAll('select, [role="listbox"], [aria-label*="country"]');
        if (countrySelectors.length > 0) {
            state.hasCountryCode = true;
        }
        
        // Check for login form
        const loginForms = document.querySelectorAll('form, [role="form"], [data-testid*="login"]');
        if (loginForms.length > 0) {
            state.loginFormPresent = true;
        }
        
        // Check for QR code
        const qrElements = document.querySelectorAll('img[alt*="QR"], canvas, [data-testid*="qr"]');
        if (qrElements.length > 0) {
            state.qrCodePresent = true;
        }
        
        // Check if already logged in (chat list present)
        const chatElements = document.querySelectorAll('[data-testid="chat-list"], [data-testid*="conversation"]');
        if (chatElements.length > 0) {
            state.chatListPresent = true;
        }
        
        // Get visible buttons
        const allButtons = document.querySelectorAll('button, [role="button"], a');
        allButtons.forEach(btn => {
            const text = btn.textContent?.trim()?.toLowerCase() || '';
            const isVisible = btn.offsetParent !== null;
            if (isVisible && text.length > 0 && text.length < 50) {
                state.buttons.push({
                    text: btn.textContent.trim(),
                    tag: btn.tagName,
                    type: btn.type || '',
                    role: btn.getAttribute('role') || ''
                });
            }
        });
        
        // Get visible text elements (for debugging)
        const visibleTexts = [];
        const textElements = document.querySelectorAll('h1, h2, h3, h4, p, span, div');
        textElements.forEach(el => {
            const text = el.textContent?.trim() || '';
            if (text.length > 0 && text.length < 100 && el.offsetParent !== null) {
                const isVisible = el.offsetParent !== null;
                if (isVisible) {
                    visibleTexts.push(text);
                }
            }
        });
        state.visibleElements = visibleTexts.slice(0, 10); // Limit to 10
        
        return state;
    }
    
    function findAndClick() {
        // Try to find by text
        let element = null;
        const allElements = document.querySelectorAll('*');
        
        for (let el of allElements) {
            const text = el.textContent?.trim();
            if (text === 'Log in with phone number' || text?.includes('Log in with phone number')) {
                element = el;
                break;
            }
        }
        
        if (!element) {
            return {
                success: false,
                message: 'Element not found',
                pageState: getPageState()
            };
        }
        
        // Find clickable parent
        let clickable = element;
        let parent = element.parentElement;
        let foundClickable = false;
        
        for (let i = 0; i < 5 && parent && parent !== document.body; i++) {
            const role = parent.getAttribute('role');
            const style = window.getComputedStyle(parent);
            
            if (parent.tagName === 'BUTTON' || 
                parent.tagName === 'A' || 
                role === 'button' ||
                role === 'link' ||
                style.cursor === 'pointer') {
                clickable = parent;
                foundClickable = true;
                break;
            }
            parent = parent.parentElement;
        }
        
        if (!foundClickable) {
            // Try to find any button with similar text
            const buttons = document.querySelectorAll('button, [role="button"]');
            for (let btn of buttons) {
                const text = btn.textContent?.trim()?.toLowerCase();
                if (text && (text.includes('phone') || text.includes('login'))) {
                    clickable = btn;
                    foundClickable = true;
                    break;
                }
            }
        }
        
        // Click the element
        try {
            // Store page state before click
            const beforeState = getPageState();
            
            // Try all click methods
            let clicked = false;
            
            try {
                clickable.click();
                clicked = true;
            } catch (e) {
                try {
                    const event = new MouseEvent('click', { bubbles: true, cancelable: true });
                    clickable.dispatchEvent(event);
                    clicked = true;
                } catch (e2) {
                    // Method 3: Simulate full click sequence
                    ['mouseover', 'mousedown', 'mouseup', 'click'].forEach(type => {
                        const event = new MouseEvent(type, { bubbles: true });
                        clickable.dispatchEvent(event);
                    });
                    clicked = true;
                }
            }
            
            // Wait a bit for DOM updates
            const startTime = Date.now();
            while (Date.now() - startTime < 1000) {
                // Busy wait to allow DOM updates
            }
            
            // Get page state after click
            const afterState = getPageState();
            
            // Determine what changed
            const changes = {
                urlChanged: beforeState.url !== afterState.url,
                titleChanged: beforeState.title !== afterState.title,
                phoneInputAppeared: !beforeState.hasPhoneInput && afterState.hasPhoneInput,
                loginFormAppeared: !beforeState.loginFormPresent && afterState.loginFormPresent,
                qrCodeChanged: beforeState.qrCodePresent !== afterState.qrCodePresent,
                chatListAppeared: !beforeState.chatListPresent && afterState.chatListPresent
            };
            
            return {
                success: true,
                message: clicked ? 'Clicked successfully' : 'Click attempted but may have failed',
                clicked: clicked,
                beforeState: beforeState,
                afterState: afterState,
                changes: changes,
                summary: {
                    newUrl: afterState.url,
                    newTitle: afterState.title,
                    hasPhoneInput: afterState.hasPhoneInput,
                    hasLoginForm: afterState.loginFormPresent,
                    hasQRCode: afterState.qrCodePresent,
                    hasChatList: afterState.chatListPresent,
                    visibleButtons: afterState.buttons.slice(0, 5),
                    visibleTexts: afterState.visibleElements
                }
            };
            
        } catch (error) {
            return {
                success: false,
                message: 'Error during click: ' + error.message,
                pageState: getPageState()
            };
        }
    }
    
    // Execute and return result
    const result = findAndClick();
    
    // Log summary
    console.log('📊 Result Summary:');
    console.log('  Success:', result.success);
    console.log('  Message:', result.message);
    
    if (result.success && result.summary) {
        console.log('  New URL:', result.summary.newUrl);
        console.log('  New Title:', result.summary.newTitle);
        console.log('  Has Phone Input:', result.summary.hasPhoneInput);
        console.log('  Has Login Form:', result.summary.hasLoginForm);
        console.log('  Has QR Code:', result.summary.hasQRCode);
        console.log('  Has Chat List:', result.summary.hasChatList);
        console.log('  Visible Buttons:', result.summary.visibleButtons);
    }
    
    // Return the full result
    return result;
})();
