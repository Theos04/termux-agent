// WhatsApp Web - Enter phone number (FINAL WORKING VERSION)
(function() {
    console.log('📱 WhatsApp Web - Enter Phone Number');
    const phoneNumber = '+917888139676'; // Just the number, no +91
    
    // Find the phone input - look for the one with value containing "+91"
    let phoneInput = null;
    const allInputs = document.querySelectorAll('input');
    
    for (let input of allInputs) {
        // Check by value (contains +91 country code)
        if (input.value && input.value.includes('+91')) {
            phoneInput = input;
            console.log('✅ Found input with country code:', input.value);
            break;
        }
        
        // Check if it's visible and likely the phone input
        const rect = input.getBoundingClientRect();
        if (rect.top > 0 && rect.top < 300 && input.offsetParent !== null) {
            const parentText = input.parentElement?.textContent || '';
            if (parentText.includes('phone') || parentText.includes('number') || parentText.includes('Enter')) {
                phoneInput = input;
                console.log('✅ Found input by position');
                break;
            }
        }
    }
    
    if (!phoneInput) {
        console.log('❌ Phone input not found');
        return {
            success: false,
            message: 'Phone input not found'
        };
    }
    
    console.log('📱 Found phone input:', {
        type: phoneInput.type,
        value: phoneInput.value,
        placeholder: phoneInput.placeholder
    });
    
    // Method to set phone number with proper events
    function setPhoneNumber(input, number) {
        // Focus and click to activate
        input.focus();
        input.click();
        
        // Clear the input (remove "+91 " or any existing value)
        input.value = '';
        input.dispatchEvent(new Event('input', { bubbles: true }));
        input.dispatchEvent(new Event('change', { bubbles: true }));
        
        // Set the phone number (just the number part)
        input.value = number;
        input.dispatchEvent(new Event('input', { bubbles: true }));
        input.dispatchEvent(new Event('change', { bubbles: true }));
        
        // Simulate typing for React detection
        for (let char of number) {
            input.dispatchEvent(new KeyboardEvent('keydown', { key: char, bubbles: true }));
            input.dispatchEvent(new KeyboardEvent('keypress', { key: char, bubbles: true }));
            input.dispatchEvent(new KeyboardEvent('keyup', { key: char, bubbles: true }));
        }
        
        // Trigger blur and refocus for validation
        input.blur();
        input.dispatchEvent(new Event('blur', { bubbles: true }));
        input.focus();
        input.dispatchEvent(new Event('focus', { bubbles: true }));
        
        return input.value === number;
    }
    
    // Set the phone number
    const valueSet = setPhoneNumber(phoneInput, phoneNumber);
    
    console.log('📱 Current input value:', phoneInput.value);
    console.log('✅ Value matches:', phoneInput.value === phoneNumber);
    
    // Wait for validation
    const waitTime = Date.now();
    while (Date.now() - waitTime < 1000) {}
    
    // Find the Next button
    let nextButton = null;
    const allButtons = document.querySelectorAll('button, [role="button"]');
    
    for (let btn of allButtons) {
        const text = btn.textContent?.trim();
        if (text === 'Next') {
            nextButton = btn;
            console.log('✅ Found Next button');
            break;
        }
    }
    
    if (!nextButton) {
        console.log('❌ Next button not found');
        return {
            success: valueSet,
            message: valueSet ? 'Phone number entered but Next button not found' : 'Failed to enter phone number',
            phoneNumber: phoneNumber,
            inputValue: phoneInput.value,
            valueMatches: phoneInput.value === phoneNumber
        };
    }
    
    // Click Next
    let nextClicked = false;
    try {
        // Try multiple click methods
        nextButton.click();
        nextClicked = true;
        console.log('✅ Clicked Next button');
    } catch (e) {
        try {
            const event = new MouseEvent('click', { view: window, bubbles: true, cancelable: true });
            nextButton.dispatchEvent(event);
            nextClicked = true;
            console.log('✅ Clicked Next with MouseEvent');
        } catch (e2) {
            console.log('❌ Failed to click Next:', e2.message);
        }
    }
    
    // Wait for page update
    const waitTime2 = Date.now();
    while (Date.now() - waitTime2 < 1000) {}
    
    // Check if validation error is gone
    const hasError = !!document.querySelector('[class*="error"], [class*="Error"]') || 
                     document.body?.innerText?.includes('Valid phone number is required');
    
    return {
        success: valueSet && nextClicked && !hasError,
        message: valueSet && nextClicked ? 
            (hasError ? 'Phone number entered but validation error - number may be invalid' : '✅ Phone number entered and Next button clicked successfully!') : 
            'Failed to complete',
        phoneNumber: phoneNumber,
        inputValue: phoneInput.value,
        valueMatches: phoneInput.value === phoneNumber,
        nextButtonClicked: nextClicked,
        hasValidationError: hasError,
        currentUrl: window.location.href,
        pageTitle: document.title
    };
})();
