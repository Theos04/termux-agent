(function() {
  'use strict';
  
  const CONFIG = {
    promptText: "Hello, how are you?",
    textareaSelector: 'textarea[placeholder="Message DeepSeek"]',
    buttonSelector: 'div[role="button"].ds-button--primary',
    waitAfterTyping: 300, // ms to wait before clicking
    waitAfterClick: 1000 // ms to wait for response
  };
  
  try {
    // Step 1: Find and set text in textarea
    const textarea = document.querySelector(CONFIG.textareaSelector);
    
    if (!textarea) {
      return {
        success: false,
        step: 'find-textarea',
        error: 'Textarea not found',
        selector: CONFIG.textareaSelector
      };
    }
    
    // Set value using native setter
    const setter = Object.getOwnPropertyDescriptor(
      HTMLTextAreaElement.prototype,
      "value"
    ).set;
    
    if (!setter) {
      return {
        success: false,
        step: 'get-setter',
        error: 'Unable to get value setter'
      };
    }
    
    setter.call(textarea, CONFIG.promptText);
    
    // Dispatch events
    ['input', 'change'].forEach(eventType => {
      textarea.dispatchEvent(new Event(eventType, { bubbles: true }));
    });
    
    // Step 2: Wait a moment then click send
    // Note: This uses synchronous delay - for async version use await
    
    // Step 3: Find and click send button
    const sendBtn = document.querySelector(CONFIG.buttonSelector);
    
    if (!sendBtn) {
      return {
        success: false,
        step: 'find-button',
        error: 'Send button not found',
        selector: CONFIG.buttonSelector,
        textSet: true // Partial success
      };
    }
    
    // Click using multiple methods for compatibility
    sendBtn.click();
    
    const clickEvent = new MouseEvent('click', {
      view: window,
      bubbles: true,
      cancelable: true,
      buttons: 1
    });
    sendBtn.dispatchEvent(clickEvent);
    
    return {
      success: true,
      message: 'Message sent successfully',
      text: CONFIG.promptText,
      timestamp: new Date().toISOString()
    };
    
  } catch (error) {
    return {
      success: false,
      error: error.message,
      stack: error.stack,
      timestamp: new Date().toISOString()
    };
  }
})();
