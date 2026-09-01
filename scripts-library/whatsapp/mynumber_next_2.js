// WhatsApp Web - Enter phone number (Fixed for current page)
(function() {
    console.log('📱 WhatsApp Web - Enter Phone Number');
    const phoneNumber = '+917888139676';
    
    // Find the phone input - look for the input with value containing "+91"
    let phoneInput = null;
    const allInputs = document.querySelectorAll('input');
    
    for (let input of allInputs) {
        // Check by value (contains +91 country code)
        if (input.value && input.value.includes('+91')) {
            phoneInput = input;
            console.log('✅ Found input with country code:', input.value);
            break;
        }
        
        // Check by placeholder (if it has phone-related text)
        if (input.placeholder && input.placeholder.toLowerCase().includes('phone')) {
            phoneInput = input;
            console.log('✅ Found input by placeholder:', input.placeholder);
            break;
        }
        
        // Check if it's visible and in the right position
        const rect = input.getBoundingClientRect();
        if (rect.top > 0 && rect.top < 300 && input.offsetParent !== null) {
            // It's visible in the top area
            const parentText = input.parentElement?.textContent || '';
            if (parentText.includes('phone') || parentText.includes('number')) {
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
        placeholder: phoneInput.placeholder,
        id: phoneInput.id,
        className: phoneInput.className
    });
    
    // Clear the existing value and enter the phone number
    function setPhoneNumber(input, number) {
        // Focus the input
        input.focus();
        input.click();
        
        // Clear any existing value
        input.value = '';
        input.dispatchEvent(new Event('input', { bubbles: true }));
        input.dispatchEvent(new Event('change', { bubbles: true }));
        
        // Enter the phone number (without +91 since it's already there)
        input.value = number;
        input.dispatchEvent(new Event('input', { bubbles: true }));
        input.dispatchEvent(new Event('change', { bubbles: true }));
        
        // Also simulate typing for better React detection
        for (let char of number) {
            const keydown = new KeyboardEvent('keydown', { key: char, bubbles: true });
            const keypress = new KeyboardEvent('keypress', { key: char, bubbles: true });
            const keyup = new KeyboardEvent('keyup', { key: char, bubbles: true });
            input.dispatchEvent(keydown);
            input.dispatchEvent(keypress);
            input.dispatchEvent(keyup);
        }
        
        // Trigger blur to validate
        input.blur();
        input.dispatchEvent(new Event('blur', { bubbles: true }));
        
        // Refocus
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
    while (Date.now() - waitTime < 500) {}
    
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
            valueMatches: phoneInput.value === phoneNumber,
            nextButtonFound: false
        };
    }
    
    // Click Next
    let nextClicked = false;
    try {
        nextButton.click();
        nextClicked = true;
        console.log('✅ Clicked Next button');
    } catch (e) {
        console.log('❌ Failed to click Next:', e.message);
    }
    
    // Wait for page update
    const waitTime2 = Date.now();
    while (Date.now() - waitTime2 < 1000) {}
    
    return {
        success: valueSet && nextClicked,
        message: valueSet && nextClicked ? 
            '✅ Phone number entered and Next button clicked successfully!' : 
            valueSet ? 'Phone number entered but Next button click failed' : 'Failed to enter phone number',
        phoneNumber: phoneNumber,
        inputValue: phoneInput.value,
        valueMatches: phoneInput.value === phoneNumber,
        nextButtonClicked: nextClicked,
        currentUrl: window.location.href,
        pageTitle: document.title
    };
})();
