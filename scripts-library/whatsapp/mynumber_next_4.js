// WhatsApp Web - Enter phone number (Properly handles country code)
(function() {
    console.log('📱 WhatsApp Web - Enter Phone Number');
    const phoneNumber = '7888139676'; // Just the digits without +91
    
    // Find the phone input
    let phoneInput = null;
    const allInputs = document.querySelectorAll('input');
    
    for (let input of allInputs) {
        // Check if it has the country code in value
        if (input.value && input.value.includes('+91')) {
            phoneInput = input;
            console.log('✅ Found input with country code:', input.value);
            break;
        }
        
        // Check by placeholder
        if (input.placeholder && input.placeholder.toLowerCase().includes('phone')) {
            phoneInput = input;
            console.log('✅ Found input by placeholder');
            break;
        }
        
        // Check by input mode
        if (input.inputMode === 'numeric' || input.inputMode === 'tel') {
            phoneInput = input;
            console.log('✅ Found input by inputMode');
            break;
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
        inputMode: phoneInput.inputMode
    });
    
    // Method to set the phone number
    function setPhoneNumber(input, number) {
        // Focus the input
        input.focus();
        input.click();
        
        // CRITICAL: Select all text in the input
        input.select();
        input.setSelectionRange(0, input.value.length);
        
        // Clear the input completely
        input.value = '';
        input.dispatchEvent(new Event('input', { bubbles: true }));
        input.dispatchEvent(new Event('change', { bubbles: true }));
        
        // Now set just the number (without +91)
        input.value = number;
        input.dispatchEvent(new Event('input', { bubbles: true }));
        input.dispatchEvent(new Event('change', { bubbles: true }));
        
        // Simulate typing each character
        for (let char of number) {
            const keydown = new KeyboardEvent('keydown', { key: char, bubbles: true });
            const keypress = new KeyboardEvent('keypress', { key: char, bubbles: true });
            const keyup = new KeyboardEvent('keyup', { key: char, bubbles: true });
            input.dispatchEvent(keydown);
            input.dispatchEvent(keypress);
            input.dispatchEvent(keyup);
        }
        
        // Trigger blur and refocus for validation
        input.blur();
        input.dispatchEvent(new Event('blur', { bubbles: true }));
        input.focus();
        input.dispatchEvent(new Event('focus', { bubbles: true }));
        
        return input.value === number;
    }
    
    // Set the phone number (just the digits)
    const valueSet = setPhoneNumber(phoneInput, phoneNumber);
    
    console.log('📱 Expected number:', phoneNumber);
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
    
    // Check the current state
    const hasError = document.body?.innerText?.includes('Valid phone number is required');
    const hasCodeScreen = !!document.querySelector('[data-testid="link-with-phone-number-code-cells"]');
    const hasQRCode = !!document.querySelector('img[alt*="QR"], canvas, [data-testid*="qr"]');
    const hasChatList = !!document.querySelector('[data-testid="chat-list"]');
    
    // Get current input value after all operations
    const finalValue = phoneInput.value;
    
    console.log('📊 Final state:');
    console.log('  - Input value:', finalValue);
    console.log('  - Has error:', hasError);
    console.log('  - Has code screen:', hasCodeScreen);
    console.log('  - Has QR code:', hasQRCode);
    console.log('  - Has chat list:', hasChatList);
    
    // Determine if successful
    let success = valueSet && nextClicked;
    let message = '';
    
    if (hasChatList) {
        message = '🎉 Already logged in!';
        success = true;
    } else if (hasCodeScreen) {
        message = '✅ Phone number entered and moved to code screen! Enter the code on your phone.';
        success = true;
    } else if (hasError) {
        message = '❌ Phone number entered but validation error - number may be invalid';
        success = false;
    } else if (valueSet && nextClicked) {
        message = '✅ Phone number entered and Next button clicked! Waiting for response...';
        success = true;
    } else {
        message = '⚠️ Partial success - check the page manually';
        success = false;
    }
    
    return {
        success: success,
        message: message,
        phoneNumber: phoneNumber,
        inputValue: finalValue,
        valueMatches: finalValue === phoneNumber,
        nextButtonClicked: nextClicked,
        hasValidationError: hasError,
        hasCodeScreen: hasCodeScreen,
        hasQRCode: hasQRCode,
        hasChatList: hasChatList,
        currentUrl: window.location.href,
        pageTitle: document.title
    };
})();
