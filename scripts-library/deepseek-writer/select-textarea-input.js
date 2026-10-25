(function() {
  'use strict';
  
  try {
    const PROMPT_TEXT = "Hello, how are you?";
    const SELECTOR = 'textarea[placeholder="Message DeepSeek"]';
    
    const textarea = document.querySelector(SELECTOR);
    
    if (!textarea) {
      return {
        success: false,
        error: 'Textarea element not found',
        selector: SELECTOR
      };
    }
    
    // Focus the textarea
    textarea.focus();
    
    // Set value using native setter (works with React)
    const setter = Object.getOwnPropertyDescriptor(
      HTMLTextAreaElement.prototype,
      "value"
    ).set;
    
    if (!setter) {
      return {
        success: false,
        error: 'Unable to get value setter'
      };
    }
    
    setter.call(textarea, PROMPT_TEXT);
    
    // Dispatch events to notify React/Vue/Angular
    const events = ['input', 'change', 'blur'];
    events.forEach(eventType => {
      textarea.dispatchEvent(new Event(eventType, { bubbles: true }));
    });
    
    return {
      success: true,
      message: 'Text set successfully',
      text: PROMPT_TEXT,
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
