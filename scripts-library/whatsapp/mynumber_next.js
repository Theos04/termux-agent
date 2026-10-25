// WhatsApp Web - Enter phone number and click Next (targeted version)
(function() {
    console.log('📱 WhatsApp Web - Enter phone and click Next');
    const phoneNumber = '7888139676';
    
    // First, find and enter the phone number
    let phoneInput = null;
    const allInputs = document.querySelectorAll('input');
    
    for (let input of allInputs) {
        const placeholder = input.placeholder?.toLowerCase() || '';
        const inputMode = input.inputMode?.toLowerCase() || '';
        const type = input.type?.toLowerCase() || '';
        
        if (type === 'tel' || 
            inputMode === 'numeric' || 
            inputMode === 'tel' ||
            placeholder.includes('phone') || 
            placeholder.includes('number')) {
            phoneInput = input;
            break;
        }
    }
    
    if (!phoneInput) {
        // Look for input near "Enter phone number" text
        const textElements = document.querySelectorAll('*');
        for (let el of textElements) {
            if (el.textContent?.trim() === 'Enter phone number') {
                const parent = el.closest('div');
                if (parent) {
                    const input = parent.querySelector('input');
                    if (input) {
                        phoneInput = input;
                        break;
                    }
                }
            }
        }
    }
    
    if (!phoneInput) {
        return {
            success: false,
            message: 'Phone input not found'
        };
    }
    
    // Enter phone number
    phoneInput.focus();
    phoneInput.value = '';
    phoneInput.dispatchEvent(new Event('input', { bubbles: true }));
    phoneInput.dispatchEvent(new Event('change', { bubbles: true }));
    
    phoneInput.value = phoneNumber;
    phoneInput.dispatchEvent(new Event('input', { bubbles: true }));
    phoneInput.dispatchEvent(new Event('change', { bubbles: true }));
    
    // Simulate typing
    for (let char of phoneNumber) {
        phoneInput.dispatchEvent(new KeyboardEvent('keydown', { key: char, bubbles: true }));
        phoneInput.dispatchEvent(new KeyboardEvent('keypress', { key: char, bubbles: true }));
        phoneInput.dispatchEvent(new KeyboardEvent('keyup', { key: char, bubbles: true }));
    }
    
    console.log('✅ Phone number entered:', phoneInput.value);
    
    // Wait for validation
    const startTime = Date.now();
    while (Date.now() - startTime < 500) {}
    
    // Find the Next button - SPECIFICALLY from your JSON structure
    let nextButton = null;
    
    // Method 1: Look for span with "Next" text and find its clickable parent
    const allElements = document.querySelectorAll('*');
    for (let el of allElements) {
        if (el.textContent?.trim() === 'Next') {
            console.log('🔍 Found "Next" text in element:', el.tagName, el.className);
            
            // Check if this element itself is clickable
            if (el.tagName === 'BUTTON' || el.getAttribute('role') === 'button') {
                nextButton = el;
                break;
            }
            
            // Look for clickable parent
            let parent = el.parentElement;
            while (parent && parent !== document.body) {
                const role = parent.getAttribute('role');
                const style = window.getComputedStyle(parent);
                
                if (parent.tagName === 'BUTTON' || 
                    parent.tagName === 'A' ||
                    role === 'button' ||
                    role === 'link' ||
                    style.cursor === 'pointer') {
                    nextButton = parent;
                    console.log('✅ Found clickable parent:', parent.tagName, parent.className);
                    break;
                }
                parent = parent.parentElement;
            }
            
            if (nextButton) break;
        }
    }
    
    // Method 2: Look specifically for div with role="button" containing "Next"
    if (!nextButton) {
        const divButtons = document.querySelectorAll('div[role="button"]');
        for (let div of divButtons) {
            if (div.textContent?.trim() === 'Next' || div.textContent?.trim().includes('Next')) {
                nextButton = div;
                console.log('✅ Found div[role="button"] with Next:', div);
                break;
            }
        }
    }
    
    // Method 3: Look for any button with "Next"
    if (!nextButton) {
        const buttons = document.querySelectorAll('button');
        for (let btn of buttons) {
            const text = btn.textContent?.trim();
            if (text === 'Next' || text?.includes('Next')) {
                nextButton = btn;
                console.log('✅ Found button with Next:', btn);
                break;
            }
        }
    }
    
    // Method 4: Look for submit buttons
    if (!nextButton) {
        const submitButtons = document.querySelectorAll('button[type="submit"], input[type="submit"]');
        if (submitButtons.length > 0) {
            nextButton = submitButtons[0];
            console.log('✅ Found submit button:', nextButton);
        }
    }
    
    // Method 5: Look for any element with "Next" in the class
    if (!nextButton) {
        const nextElements = document.querySelectorAll('[class*="next"], [class*="Next"]');
        for (let el of nextElements) {
            if (el.textContent?.trim() === 'Next' || el.textContent?.trim().includes('Next')) {
                nextButton = el;
                console.log('✅ Found element with "next" in class:', el);
                break;
            }
        }
    }
    
    if (!nextButton) {
        // Debug: Show all elements with "Next" text
        console.log('🔍 Debug - All elements containing "Next":');
        const all = document.querySelectorAll('*');
        for (let el of all) {
            const text = el.textContent?.trim();
            if (text && text.includes('Next')) {
                console.log('  -', el.tagName, 'role:', el.getAttribute('role'), 'text:', text);
            }
        }
        
        return {
            success: true,
            message: 'Phone number entered but Next button not found',
            phoneNumber: phoneNumber,
            inputValue: phoneInput.value,
            nextButtonFound: false
        };
    }
    
    console.log('🖱️ Clicking Next button:', {
        tag: nextButton.tagName,
        role: nextButton.getAttribute('role'),
        class: nextButton.className,
        text: nextButton.textContent?.trim()
    });
    
    // Click the Next button with multiple methods
    let clicked = false;
    
    // Method 1: Standard click
    try {
        nextButton.click();
        clicked = true;
        console.log('✅ Clicked with method 1');
    } catch (e) {
        console.log('⚠️ Method 1 failed:', e.message);
    }
    
    // Method 2: MouseEvent
    if (!clicked) {
        try {
            const event = new MouseEvent('click', {
                view: window,
                bubbles: true,
                cancelable: true,
                clientX: 200,
                clientY: 200
            });
            nextButton.dispatchEvent(event);
            clicked = true;
            console.log('✅ Clicked with method 2');
        } catch (e) {
            console.log('⚠️ Method 2 failed:', e.message);
        }
    }
    
    // Method 3: Full click sequence
    if (!clicked) {
        try {
            ['mouseenter', 'mouseover', 'mousedown', 'mouseup', 'click'].forEach(type => {
                const event = new MouseEvent(type, { bubbles: true, cancelable: true });
                nextButton.dispatchEvent(event);
            });
            clicked = true;
            console.log('✅ Clicked with method 3');
        } catch (e) {
            console.log('⚠️ Method 3 failed:', e.message);
        }
    }
    
    // Method 4: Focus + Enter key
    if (!clicked) {
        try {
            nextButton.focus();
            const enterEvent = new KeyboardEvent('keydown', {
                key: 'Enter',
                code: 'Enter',
                keyCode: 13,
                which: 13,
                bubbles: true,
                cancelable: true
            });
            nextButton.dispatchEvent(enterEvent);
            
            const keyupEvent = new KeyboardEvent('keyup', {
                key: 'Enter',
                code: 'Enter',
                keyCode: 13,
                which: 13,
                bubbles: true
            });
            nextButton.dispatchEvent(keyupEvent);
            clicked = true;
            console.log('✅ Clicked with method 4 (Enter key)');
        } catch (e) {
            console.log('⚠️ Method 4 failed:', e.message);
        }
    }
    
    // Method 5: Click using JavaScript execution
    if (!clicked) {
        try {
            // Force click using onclick if available
            if (typeof nextButton.onclick === 'function') {
                nextButton.onclick();
                clicked = true;
                console.log('✅ Clicked with method 5 (onclick)');
            }
        } catch (e) {
            console.log('⚠️ Method 5 failed:', e.message);
        }
    }
    
    // Wait for page update
    const waitTime = Date.now();
    while (Date.now() - waitTime < 1000) {}
    
    // Get page state after click
    const afterState = {
        url: window.location.href,
        title: document.title,
        hasQRCode: !!document.querySelector('img[alt*="QR"], canvas, [data-testid*="qr"]'),
        hasChatList: !!document.querySelector('[data-testid="chat-list"], [data-testid*="conversation"]'),
        hasOTPInput: !!document.querySelector('input[inputmode="numeric"][maxlength*="6"], input[placeholder*="code"], input[placeholder*="OTP"]'),
        hasPhoneInput: !!document.querySelector('input[type="tel"], input[inputmode="numeric"]')
    };
    
    return {
        success: true,
        message: clicked ? 'Phone number entered and Next button clicked successfully' : 'Phone number entered but Next button click failed',
        phoneNumber: phoneNumber,
        inputValue: phoneInput.value,
        valueMatches: phoneInput.value === phoneNumber,
        nextButtonFound: true,
        nextButtonClicked: clicked,
        clickMethods: {
            standard: clicked
        },
        afterState: afterState,
        summary: {
            url: afterState.url,
            title: afterState.title,
            hasQRCode: afterState.hasQRCode,
            hasChatList: afterState.hasChatList,
            hasOTPInput: afterState.hasOTPInput,
            hasPhoneInput: afterState.hasPhoneInput
        }
    };
})();
