// WhatsApp Web - Comprehensive code finder with page analysis
(function() {
    console.log('🔍 WhatsApp Web - Comprehensive Code Finder');
    
    // Get current page info
    const pageInfo = {
        url: window.location.href,
        title: document.title,
        tabId: window.name || 'unknown'
    };
    console.log('📄 Page Info:', pageInfo);
    
    // Search for code using multiple strategies
    function findCode() {
        let results = [];
        
        // Strategy 1: Look for data-link-code attribute
        const codeElements = document.querySelectorAll('[data-link-code]');
        codeElements.forEach(el => {
            const code = el.getAttribute('data-link-code');
            if (code) {
                results.push({
                    code: code,
                    method: 'data-link-code',
                    element: el.tagName,
                    class: el.className,
                    id: el.id
                });
            }
        });
        
        // Strategy 2: Look for aria-details
        const ariaElements = document.querySelectorAll('[aria-details]');
        ariaElements.forEach(el => {
            const details = el.getAttribute('aria-details');
            if (details && details.includes('link-device')) {
                const code = el.getAttribute('data-link-code');
                if (code) {
                    results.push({
                        code: code,
                        method: 'aria-details',
                        element: el.tagName,
                        class: el.className
                    });
                }
            }
        });
        
        // Strategy 3: Look for text patterns (8 chars with commas)
        const allText = document.querySelectorAll('*');
        const textPatterns = [];
        allText.forEach(el => {
            const text = el.textContent?.trim() || '';
            // Look for pattern like "1,L,Q,Q,C,5,D,G"
            const match = text.match(/\b([A-Z0-9],){7}[A-Z0-9]\b/);
            if (match) {
                textPatterns.push({
                    code: match[0],
                    method: 'text-pattern',
                    element: el.tagName,
                    text: text.substring(0, 50)
                });
            }
        });
        
        results = results.concat(textPatterns);
        
        // Strategy 4: Look for any 8-character alphanumeric code
        const allElements = document.querySelectorAll('*');
        allElements.forEach(el => {
            const text = el.textContent?.trim() || '';
            // Clean text: remove spaces, look for 8 char alphanumeric
            const clean = text.replace(/\s/g, '').replace(/,/g, '');
            if (clean.length === 8 && /^[A-Z0-9]{8}$/.test(clean)) {
                // Format as code with commas
                const formatted = clean.split('').join(',');
                // Check if this element is likely showing a code
                const parent = el.parentElement;
                const grandParent = parent?.parentElement;
                if (parent && (parent.className?.includes('code') || 
                              grandParent?.className?.includes('code'))) {
                    results.push({
                        code: formatted,
                        method: 'alphanumeric-8-char',
                        element: el.tagName,
                        class: el.className,
                        text: text.substring(0, 50)
                    });
                }
            }
        });
        
        return results;
    }
    
    // Get all results
    const allResults = findCode();
    
    // Get the DOM structure for debugging
    function getDOMStructure() {
        const structure = {
            dataLinkCodes: Array.from(document.querySelectorAll('[data-link-code]')).map(el => ({
                code: el.getAttribute('data-link-code'),
                tag: el.tagName,
                class: el.className,
                id: el.id
            })),
            ariaDetails: Array.from(document.querySelectorAll('[aria-details]')).map(el => ({
                aria: el.getAttribute('aria-details'),
                tag: el.tagName,
                class: el.className
            })),
            testIds: Array.from(document.querySelectorAll('[data-testid]')).map(el => ({
                testid: el.getAttribute('data-testid'),
                tag: el.tagName,
                class: el.className
            }))
        };
        return structure;
    }
    
    const domStructure = getDOMStructure();
    console.log('📊 DOM Structure:', domStructure);
    
    // Find unique codes
    const uniqueCodes = [];
    const codeSet = new Set();
    allResults.forEach(r => {
        if (!codeSet.has(r.code)) {
            codeSet.add(r.code);
            uniqueCodes.push(r);
        }
    });
    
    if (uniqueCodes.length > 0) {
        console.log('✅ Found', uniqueCodes.length, 'code(s):');
        uniqueCodes.forEach((r, i) => {
            console.log(`  ${i+1}. ${r.code} (${r.method})`);
        });
        
        // Get the most likely code (first one with 8 chars)
        const primaryCode = uniqueCodes.find(r => r.code.length >= 8);
        
        if (primaryCode) {
            console.log('📋 Primary Code:', primaryCode.code);
            console.log('📱 Formatted:', primaryCode.code.replace(/,/g, ' '));
            console.log('🔢 Characters:', primaryCode.code.split(','));
            
            return {
                success: true,
                code: primaryCode.code,
                formatted: primaryCode.code.replace(/,/g, ' '),
                characters: primaryCode.code.split(','),
                method: primaryCode.method,
                allCodes: uniqueCodes,
                pageInfo: pageInfo,
                domStructure: domStructure
            };
        }
    }
    
    // If no code found, return detailed debug info
    console.log('❌ No code found');
    console.log('🔍 Debug Info:');
    console.log('  - data-link-code elements:', domStructure.dataLinkCodes.length);
    console.log('  - aria-details elements:', domStructure.ariaDetails.length);
    console.log('  - data-testid elements:', domStructure.testIds.length);
    
    return {
        success: false,
        message: 'Code not found',
        pageInfo: pageInfo,
        domStructure: domStructure,
        suggestions: [
            'Make sure you are on the WhatsApp Web code screen',
            'The code should be 8 characters like: 1,L,Q,Q,C,5,D,G',
            'Try refreshing the page if the code expired'
        ]
    };
})();
