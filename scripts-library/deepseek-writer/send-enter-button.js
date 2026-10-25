(function() {
  'use strict';
  
  try {
    const SELECTOR = 'div[role="button"].ds-button--primary';
    const TIMEOUT = 5000; // 5 seconds max wait
    
    const findButton = () => document.querySelector(SELECTOR);
    
    // Try to find button immediately
    let sendBtn = findButton();
    
    if (!sendBtn) {
      // If not found, wait a bit for dynamic loading
      const startTime = Date.now();
      while (!sendBtn && (Date.now() - startTime) < TIMEOUT) {
        // Synchronous wait (blocks execution but ensures we find it)
        // Use setTimeout for async version if preferred
        sendBtn = findButton();
      }
    }
    
    if (!sendBtn) {
      return {
        success: false,
        error: 'Send button not found',
        selector: SELECTOR,
        timeout: TIMEOUT
      };
    }
    
    // Check if button is disabled
    if (sendBtn.hasAttribute('disabled') || sendBtn.getAttribute('aria-disabled') === 'true') {
      return {
        success: false,
        error: 'Button is disabled',
        isDisabled: true
      };
    }
    
    // Method 1: Standard click (works for most cases)
    sendBtn.click();
    
    // Method 2: Also dispatch events for React compatibility
    const clickEvent = new MouseEvent('click', {
      view: window,
      bubbles: true,
      cancelable: true,
      buttons: 1
    });
    sendBtn.dispatchEvent(clickEvent);
    
    // Method 3: If it's a button element, also trigger mousedown/mouseup
    if (sendBtn.tagName === 'BUTTON' || sendBtn.tagName === 'DIV') {
      ['mousedown', 'mouseup'].forEach(eventType => {
        const event = new MouseEvent(eventType, {
          view: window,
          bubbles: true,
          cancelable: true,
          buttons: 1
        });
        sendBtn.dispatchEvent(event);
      });
    }
    
    return {
      success: true,
      message: 'Button clicked successfully',
      buttonText: sendBtn.textContent?.trim() || 'Send',
      timestamp: new Date().toISOString()
    };
    
  } catch (error) {
    return {
      success: false,
      error: error.message,
      stack: error.stack
    };
  }
})();
