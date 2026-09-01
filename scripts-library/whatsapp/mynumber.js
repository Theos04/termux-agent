// WhatsApp Web - Enter phone number
(function() {
    console.log('📱 Entering phone number...');
    const phoneNumber = '+917888139676';
    
    function getPageState() {
        return {
            url: window.location.href,
            title: document.title,
            hasPhoneInput: !!document.querySelector('input[type="tel"], input[type="text"][inputmode="numeric"], input[placeholder*="phone"], input[placeholder*="number"]'),
            hasCountryCode: !!document.querySelector('select, [role="listbox"], [aria-label*="country"]'),
            visibleTexts: Array.from(document.querySelectorAll('h1, h2, h3, h4, p, span, div'))
                .filter(el => el.textContent?.trim() && el.offsetParent !== null)
                .map(el => el.textContent.trim())
                .filter(text => text.length > 0 && text.length < 100)
                .slice(0, 10)
        };
    }
    
    // Get initial state
    const beforeState = getPageState();
    console.log('📊 Initial page state:', beforeState);
    
    // Find the phone input field
    let phoneInput = null;
    const inputs = document.querySelectorAll('input');
    
    for (let input of inputs) {
        const type = input.type?.toLowerCase() || '';
        const placeholder = input.placeholder?.toLowerCase() || '';
        const id = input.id?.toLowerCase() || '';
        const name = input.name?.toLowerCase() || '';
        const inputMode = input.inputMode?.toLowerCase() || '';
        
        // Check if it's a phone input
        if (type === 'tel' || 
            placeholder.includes('phone') || 
            placeholder.includes('number') ||
            id.includes('phone') || 
            id.includes('number') ||
            name.includes('phone') || 
            name.includes('number') ||
            inputMode === 'numeric' ||
            inputMode === 'tel') {
            phoneInput = input;
            console.log('✅ Found phone input:', {
                type: input.type,
                placeholder: input.placeholder,
                id: input.id,
                name: input.name,
                inputMode: input.inputMode
            });
            break;
        }
    }
    
    // If not found by attributes, try to find by visible text
    if (!phoneInput) {
        console.log('🔍 Searching by visible text...');
        const allElements = document.querySelectorAll('*');
        for (let el of allElements) {
            const text = el.textContent?.trim();
            if (text === 'Enter phone number' || text?.includes('Enter phone number')) {
                // Find input near this text
                const parent = el.closest('div, form, section');
                if (parent) {
                    const nearbyInput = parent.querySelector('input');
                    if (nearbyInput) {
                        phoneInput = nearbyInput;
                        console.log('✅ Found phone input near text:', nearbyInput);
                        break;
                    }
                }
            }
        }
    }
    
    if (!phoneInput) {
        console.log('❌ Phone input not found');
        return {
            success: false,
            message: 'Phone input not found',
            pageState: getPageState()
        };
    }
    
    // Focus on the input
    try {
        phoneInput.focus();
        console.log('✅ Focused on input');
    } catch (e) {
        console.log('⚠️ Could not focus:', e.message);
    }
    
    // Clear the input first
    try {
        phoneInput.value = '';
        // Trigger input events
        phoneInput.dispatchEvent(new Event('input', { bubbles: true }));
        phoneInput.dispatchEvent(new Event('change', { bubbles: true }));
        console.log('✅ Cleared input');
    } catch (e) {
        console.log('⚠️ Could not clear:', e.message);
    }
    
    // Enter the phone number
    try {
        // Method 1: Direct value assignment
        phoneInput.value = phoneNumber;
        phoneInput.dispatchEvent(new Event('input', { bubbles: true }));
        phoneInput.dispatchEvent(new Event('change', { bubbles: true }));
        console.log('✅ Set phone number: ' + phoneNumber);
        
        // Method 2: Simulate typing (for more realistic interaction)
        const simulateTyping = false; // Set to true if needed
        if (simulateTyping) {
            for (let char of phoneNumber) {
                const keydownEvent = new KeyboardEvent('keydown', { key: char, bubbles: true });
                const keypressEvent = new KeyboardEvent('keypress', { key: char, bubbles: true });
                const keyupEvent = new KeyboardEvent('keyup', { key: char, bubbles: true });
                phoneInput.dispatchEvent(keydownEvent);
                phoneInput.dispatchEvent(keypressEvent);
                phoneInput.dispatchEvent(keyupEvent);
            }
            phoneInput.dispatchEvent(new Event('input', { bubbles: true }));
            console.log('✅ Simulated typing');
        }
        
    } catch (e) {
        console.log('❌ Failed to set value:', e.message);
        return {
            success: false,
            message: 'Failed to set phone number: ' + e.message,
            pageState: getPageState()
        };
    }
    
    // Verify the value was set
    const currentValue = phoneInput.value;
    console.log('📱 Current input value:', currentValue);
    
    // Find and click the "Next" button
    let nextButton = null;
    const buttons = document.querySelectorAll('button, [role="button"]');
    for (let btn of buttons) {
        const text = btn.textContent?.trim();
        if (text === 'Next' || text?.includes('Next')) {
            nextButton = btn;
            console.log('✅ Found Next button');
            break;
        }
    }
    
    // If no "Next" button found, look for any submit button
    if (!nextButton) {
        const submitButtons = document.querySelectorAll('button[type="submit"], input[type="submit"]');
        if (submitButtons.length > 0) {
            nextButton = submitButtons[0];
            console.log('✅ Found submit button');
        }
    }
    
    // Get page state after entering number
    const afterState = getPageState();
    
    let clickResult = false;
    if (nextButton) {
        try {
            nextButton.click();
            console.log('✅ Clicked Next button');
            clickResult = true;
        } catch (e) {
            console.log('❌ Failed to click Next:', e.message);
        }
    } else {
        console.log('⚠️ No Next button found, number entered but not submitted');
    }
    
    // Return result
    return {
        success: true,
        message: clickResult ? 'Phone number entered and submitted' : 'Phone number entered but could not submit',
        phoneNumber: phoneNumber,
        inputValue: currentValue,
        valueMatches: currentValue === phoneNumber,
        nextButtonClicked: clickResult,
        beforeState: beforeState,
        afterState: afterState,
        summary: {
            hasPhoneInput: afterState.hasPhoneInput,
            hasCountryCode: afterState.hasCountryCode,
            visibleTexts: afterState.visibleTexts
        }
    };
})();
