// WhatsApp Web - Enter phone number (Fixed version)
(function() {
    console.log('📱 WhatsApp Web - Enter Phone Number');
    const phoneNumber = '7888139676';
    const fullNumber = '+917888139676';
    
    // Debug function to analyze the page
    function analyzePage() {
        const inputs = document.querySelectorAll('input');
        const inputInfo = [];
        inputs.forEach((input, i) => {
            inputInfo.push({
                index: i,
                type: input.type,
                placeholder: input.placeholder,
                id: input.id,
                name: input.name,
                className: input.className,
                inputMode: input.inputMode,
                value: input.value,
                visible: input.offsetParent !== null,
                rect: input.getBoundingClientRect()
            });
        });
        
        const buttons = document.querySelectorAll('button, [role="button"]');
        const buttonInfo = [];
        buttons.forEach((btn, i) => {
            buttonInfo.push({
                index: i,
                text: btn.textContent?.trim(),
                tag: btn.tagName,
                role: btn.getAttribute('role'),
                className: btn.className,
                visible: btn.offsetParent !== null
            });
        });
        
        return {
            inputs: inputInfo,
            buttons: buttonInfo,
            bodyText: document.body?.innerText?.substring(0, 500)
        };
    }
    
    console.log('🔍 Analyzing page...');
    const analysis = analyzePage();
    console.log('📊 Page Analysis:', JSON.stringify(analysis, null, 2));
    
    // Find the phone input - more flexible
    let phoneInput = null;
    const allInputs = document.querySelectorAll('input');
    
    for (let input of allInputs) {
        // Check by placeholder
        const placeholder = input.placeholder?.toLowerCase() || '';
        if (placeholder.includes('phone') || placeholder.includes('number') || placeholder.includes('enter')) {
            phoneInput = input;
            console.log('✅ Found by placeholder:', input.placeholder);
            break;
        }
        
        // Check by input mode
        if (input.inputMode === 'numeric' || input.inputMode === 'tel') {
            phoneInput = input;
            console.log('✅ Found by inputMode:', input.inputMode);
            break;
        }
        
        // Check by type
        if (input.type === 'tel') {
            phoneInput = input;
            console.log('✅ Found by type: tel');
            break;
        }
        
        // Check by visible position (if it's in the viewport and likely the phone input)
        const rect = input.getBoundingClientRect();
        if (rect.top > 0 && rect.top < 500 && input.offsetParent !== null) {
            // It's visible in the top half of the page
            const parentText = input.parentElement?.textContent?.toLowerCase() || '';
            if (parentText.includes('phone') || parentText.includes('number')) {
                phoneInput = input;
                console.log('✅ Found by position and context');
                break;
            }
        }
    }
    
    if (!phoneInput) {
        console.log('❌ Phone input not found');
        return {
            success: false,
            message: 'Phone input not found',
            analysis: analysis
        };
    }
    
    console.log('📱 Found phone input:', {
        type: phoneInput.type,
        placeholder: phoneInput.placeholder,
        id: phoneInput.id,
        className: phoneInput.className,
        inputMode: phoneInput.inputMode
    });
    
    // Try multiple methods to set the value
    let valueSet = false;
    const methods = [
        // Method 1: Direct value assignment with events
        function() {
            phoneInput.focus();
            phoneInput.click();
            phoneInput.value = '';
            phoneInput.dispatchEvent(new Event('input', { bubbles: true }));
            phoneInput.dispatchEvent(new Event('change', { bubbles: true }));
            
            phoneInput.value = phoneNumber;
            phoneInput.dispatchEvent(new Event('input', { bubbles: true }));
            phoneInput.dispatchEvent(new Event('change', { bubbles: true }));
            phoneInput.dispatchEvent(new Event('blur', { bubbles: true }));
            return phoneInput.value === phoneNumber;
        },
        
        // Method 2: Using setAttribute and value
        function() {
            phoneInput.setAttribute('value', phoneNumber);
            phoneInput.value = phoneNumber;
            phoneInput.dispatchEvent(new Event('input', { bubbles: true }));
            phoneInput.dispatchEvent(new Event('change', { bubbles: true }));
            return phoneInput.value === phoneNumber;
        },
        
        // Method 3: Simulate typing each character
        function() {
            phoneInput.focus();
            phoneInput.value = '';
            for (let char of phoneNumber) {
                phoneInput.value += char;
                phoneInput.dispatchEvent(new KeyboardEvent('keydown', { key: char, bubbles: true }));
                phoneInput.dispatchEvent(new KeyboardEvent('keypress', { key: char, bubbles: true }));
                phoneInput.dispatchEvent(new Event('input', { bubbles: true }));
                phoneInput.dispatchEvent(new KeyboardEvent('keyup', { key: char, bubbles: true }));
            }
            phoneInput.dispatchEvent(new Event('change', { bubbles: true }));
            return phoneInput.value === phoneNumber;
        },
        
        // Method 4: Use React/Vue setter if available
        function() {
            const descriptor = Object.getOwnPropertyDescriptor(phoneInput, 'value');
            if (descriptor && descriptor.set) {
                descriptor.set.call(phoneInput, phoneNumber);
                phoneInput.dispatchEvent(new Event('input', { bubbles: true }));
                phoneInput.dispatchEvent(new Event('change', { bubbles: true }));
                return phoneInput.value === phoneNumber;
            }
            return false;
        }
    ];
    
    for (let i = 0; i < methods.length; i++) {
        try {
            if (methods[i]()) {
                valueSet = true;
                console.log(`✅ Value set with method ${i + 1}`);
                break;
            }
        } catch (e) {
            console.log(`⚠️ Method ${i + 1} failed:`, e.message);
        }
    }
    
    console.log('📱 Current input value:', phoneInput.value);
    console.log('📱 Expected value:', phoneNumber);
    console.log('✅ Value matches:', phoneInput.value === phoneNumber);
    
    // Wait for validation
    const waitTime = Date.now();
    while (Date.now() - waitTime < 1000) {}
    
    // Find the Next button
    let nextButton = null;
    const allButtons = document.querySelectorAll('button, [role="button"]');
    
    for (let btn of allButtons) {
        const text = btn.textContent?.trim();
        if (text === 'Next' || text?.toLowerCase().includes('next')) {
            nextButton = btn;
            console.log('✅ Found Next button:', btn);
            break;
        }
    }
    
    let nextClicked = false;
    if (nextButton) {
        try {
            nextButton.click();
            nextClicked = true;
            console.log('✅ Clicked Next button');
        } catch (e) {
            console.log('❌ Failed to click Next:', e.message);
        }
    } else {
        console.log('❌ Next button not found');
    }
    
    // Final page analysis
    const finalAnalysis = analyzePage();
    
    return {
        success: valueSet,
        message: valueSet ? 
            (nextClicked ? 'Phone number entered and submitted' : 'Phone number entered but Next button not clicked') :
            'Failed to enter phone number',
        phoneNumber: phoneNumber,
        inputValue: phoneInput.value,
        valueMatches: phoneInput.value === phoneNumber,
        nextButtonClicked: nextClicked,
        inputFound: true,
        analysis: finalAnalysis
    };
})();
