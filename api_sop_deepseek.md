# Chrome Automation API Platform - Developer Guide

## Overview

This document provides a standardized approach for building automation modules on top of the Chrome Daemon API. The platform consists of three core components:

1. **Chrome Daemon API** (`api.py`) - REST API layer for Chrome automation
2. **Chrome Session Manager** (`cdpv119.py`) - Manages Chrome instances with WebSocket support
3. **Session Info Tracker** - Tracks session state including WebSocket IDs

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Your Automation Module                   │
├─────────────────────────────────────────────────────────────┤
│                     API Layer (api.py)                      │
│  - REST endpoints for session/automation control           │
├─────────────────────────────────────────────────────────────┤
│               Chrome Session Manager (cdpv119.py)           │
│  - Manages Chrome instances                                │
│  - Maintains WebSocket connections                         │
│  - Tracks session state                                    │
├─────────────────────────────────────────────────────────────┤
│              Chrome Browser (with DevTools)                │
└─────────────────────────────────────────────────────────────┘
```

## Core Components

### 1. Session Info File
Located at: `/data/data/com.termux/files/home/chrome-sessions/session_info.json`

```json
{
  "sessions": {
    "1": {
      "name": "my-session",
      "url": "https://example.com",
      "port": 9222,
      "pid": 12345,
      "status": "running",
      "current_ws_id": "ABC123...",
      "websocket_ids": ["ABC123...", "DEF456..."],
      "websocket_details": [
        {
          "tab_id": "ABC123...",
          "title": "Example Page",
          "url": "https://example.com",
          "ws_url": "ws://127.0.0.1:9222/devtools/page/ABC123..."
        }
      ]
    }
  }
}
```

### 2. API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/session/{name}/start` | Start a session |
| POST | `/session/{name}/stop` | Stop a session |
| GET | `/session/{name}/status` | Get session status |
| GET | `/sessions` | List all sessions |
| POST | `/session/{name}/navigate` | Navigate to URL |
| GET | `/session/{name}/html` | Get page HTML |
| POST | `/session/{name}/click` | Click element by selector |
| POST | `/session/{name}/evaluate` | Execute JavaScript |
| GET | `/session/{name}/screenshot` | Capture screenshot |
| POST | `/session/{name}/cdp` | Execute raw CDP command |

## Building Automation Modules

### Module Template

Create your module in: `/data/data/com.termux/files/home/automation/chrome-launcher/modules/`

```python
#!/usr/bin/env python3
"""
Module: {module_name}.py
Purpose: {describe what this module does}
Dependencies: requests, websocket-client
"""

import json
import time
import logging
from typing import Optional, Dict, Any, List
from pathlib import Path
import requests
import websocket

# ============================================================================
# Configuration
# ============================================================================

class ModuleConfig:
    """Configuration for this automation module"""
    API_BASE = "http://127.0.0.1:5000"
    SESSION_NAME = "default"
    TIMEOUT = 30
    RETRY_COUNT = 3
    RETRY_DELAY = 2
    SCRIPT_LIBRARY_PATH = "/data/data/com.termux/files/home/automation/chrome-launcher/scripts-library"
    SESSION_INFO_PATH = "/data/data/com.termux/files/home/chrome-sessions/session_info.json"

# ============================================================================
# Base Automation Class
# ============================================================================

class BaseAutomation:
    """
    Base class for Chrome automation modules.
    Provides core functionality for interacting with Chrome via CDP.
    """
    
    def __init__(self, session_name: str = None, config: ModuleConfig = None):
        """
        Initialize the automation module.
        
        Args:
            session_name: Name of the Chrome session to use
            config: Module configuration object
        """
        self.config = config or ModuleConfig()
        self.session_name = session_name or self.config.SESSION_NAME
        self.api_base = self.config.API_BASE
        self.session = requests.Session()
        self.session.timeout = self.config.TIMEOUT
        self.logger = self._setup_logger()
        
    def _setup_logger(self) -> logging.Logger:
        """Setup module logging"""
        logger = logging.getLogger(f"automation.{self.session_name}")
        logger.setLevel(logging.INFO)
        
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            
        return logger
    
    def _get_session_info(self) -> Optional[Dict]:
        """
        Get session information including WebSocket ID.
        
        Returns:
            Session information dict or None if not found
        """
        try:
            with open(self.config.SESSION_INFO_PATH, 'r') as f:
                data = json.load(f)
                
            for session_id, session_data in data.get('sessions', {}).items():
                if session_data.get('name') == self.session_name:
                    return {
                        'id': session_id,
                        **session_data
                    }
            return None
        except Exception as e:
            self.logger.error(f"Failed to get session info: {e}")
            return None
    
    def _ensure_session_running(self) -> bool:
        """
        Ensure the session is running. Start it if needed.
        
        Returns:
            True if session is running, False otherwise
        """
        # Check if session exists
        response = self.session.get(
            f"{self.api_base}/sessions"
        )
        if response.status_code != 200:
            self.logger.error("Failed to list sessions")
            return False
            
        sessions = response.json().get('sessions', [])
        session_exists = any(s.get('name') == self.session_name for s in sessions)
        
        if not session_exists:
            # Create session
            self.logger.info(f"Creating session: {self.session_name}")
            response = self.session.post(
                f"{self.api_base}/session/{self.session_name}/start",
                json={'url': 'https://example.com'}
            )
            if response.status_code != 200:
                self.logger.error(f"Failed to create session: {response.text}")
                return False
                
        # Check if session is running
        response = self.session.get(
            f"{self.api_base}/session/{self.session_name}/status"
        )
        if response.status_code != 200:
            return False
            
        status = response.json()
        if not status.get('connected', False):
            self.logger.info(f"Starting session: {self.session_name}")
            response = self.session.post(
                f"{self.api_base}/session/{self.session_name}/start"
            )
            if response.status_code != 200:
                self.logger.error(f"Failed to start session: {response.text}")
                return False
                
            # Wait for session to be ready
            time.sleep(5)
            
        return True
    
    def _make_request(self, method: str, endpoint: str, data: Dict = None) -> Dict:
        """
        Make an API request with retries.
        
        Args:
            method: HTTP method (GET, POST)
            endpoint: API endpoint path
            data: Request data (for POST requests)
            
        Returns:
            Response JSON
        """
        url = f"{self.api_base}{endpoint}"
        retries = self.config.RETRY_COUNT
        
        for attempt in range(retries):
            try:
                if method.upper() == 'GET':
                    response = self.session.get(url)
                else:
                    response = self.session.post(url, json=data)
                    
                if response.status_code == 200:
                    return response.json()
                    
                self.logger.warning(f"Request failed (attempt {attempt + 1}): {response.text}")
                
            except Exception as e:
                self.logger.warning(f"Request error (attempt {attempt + 1}): {e}")
                
            if attempt < retries - 1:
                time.sleep(self.config.RETRY_DELAY * (attempt + 1))
                
        return {'error': f'Request failed after {retries} attempts'}
    
    def navigate(self, url: str) -> Dict:
        """Navigate to a URL"""
        if not self._ensure_session_running():
            return {'error': 'Session not running'}
            
        return self._make_request(
            'POST',
            f'/session/{self.session_name}/navigate',
            {'url': url}
        )
    
    def evaluate(self, script: str) -> Dict:
        """
        Execute JavaScript in the page.
        
        Args:
            script: JavaScript code to execute
            
        Returns:
            Result of the evaluation
        """
        if not self._ensure_session_running():
            return {'error': 'Session not running'}
            
        return self._make_request(
            'POST',
            f'/session/{self.session_name}/evaluate',
            {'expression': script}
        )
    
    def click(self, selector: str) -> Dict:
        """Click an element by CSS selector"""
        if not self._ensure_session_running():
            return {'error': 'Session not running'}
            
        return self._make_request(
            'POST',
            f'/session/{self.session_name}/click',
            {'selector': selector}
        )
    
    def get_html(self) -> Dict:
        """Get the page HTML"""
        if not self._ensure_session_running():
            return {'error': 'Session not running'}
            
        return self._make_request(
            'GET',
            f'/session/{self.session_name}/html'
        )
    
    def get_url(self) -> Dict:
        """Get the current page URL"""
        if not self._ensure_session_running():
            return {'error': 'Session not running'}
            
        return self._make_request(
            'GET',
            f'/session/{self.session_name}/url'
        )
    
    def screenshot(self) -> Dict:
        """Take a screenshot"""
        if not self._ensure_session_running():
            return {'error': 'Session not running'}
            
        return self._make_request(
            'GET',
            f'/session/{self.session_name}/screenshot'
        )
    
    def execute_cdp(self, method: str, params: Dict = None) -> Dict:
        """
        Execute a raw CDP command.
        
        Args:
            method: CDP method name (e.g., 'Page.navigate')
            params: CDP parameters
            
        Returns:
            CDP response
        """
        if not self._ensure_session_running():
            return {'error': 'Session not running'}
            
        return self._make_request(
            'POST',
            f'/session/{self.session_name}/cdp',
            {'method': method, 'params': params or {}}
        )
    
    def get_websocket_connection(self) -> Optional[str]:
        """
        Get the WebSocket URL for the current session.
        
        Returns:
            WebSocket URL or None if not available
        """
        session_info = self._get_session_info()
        if not session_info:
            return None
            
        # Get the current WebSocket ID
        ws_id = session_info.get('current_ws_id')
        port = session_info.get('port')
        
        if ws_id and port:
            return f"ws://127.0.0.1:{port}/devtools/page/{ws_id}"
            
        # Try to get from API
        response = self.session.get(
            f"{self.api_base}/session/{self.session_name}/status"
        )
        if response.status_code == 200:
            data = response.json()
            if data.get('session'):
                ws_id = data['session'].get('current_ws_id')
                port = data['session'].get('port')
                if ws_id and port:
                    return f"ws://127.0.0.1:{port}/devtools/page/{ws_id}"
                    
        return None

# ============================================================================
# Script Library Integration
# ============================================================================

class ScriptLibrary:
    """
    Manages JavaScript scripts stored in the script library.
    """
    
    def __init__(self, library_path: str = None):
        self.library_path = Path(library_path or ModuleConfig.SCRIPT_LIBRARY_PATH)
        self.scripts = {}
        self._load_scripts()
        
    def _load_scripts(self):
        """Load all scripts from the library directory"""
        if not self.library_path.exists():
            self.library_path.mkdir(parents=True, exist_ok=True)
            return
            
        for script_file in self.library_path.glob("*.js"):
            try:
                with open(script_file, 'r') as f:
                    content = f.read()
                    name = script_file.stem
                    self.scripts[name] = content
            except Exception as e:
                print(f"Failed to load script {script_file}: {e}")
                
    def get_script(self, name: str) -> Optional[str]:
        """Get a script by name"""
        return self.scripts.get(name)
    
    def list_scripts(self) -> List[str]:
        """List all available script names"""
        return list(self.scripts.keys())
    
    def save_script(self, name: str, content: str) -> bool:
        """Save a new script to the library"""
        script_file = self.library_path / f"{name}.js"
        try:
            with open(script_file, 'w') as f:
                f.write(content)
            self.scripts[name] = content
            return True
        except Exception as e:
            print(f"Failed to save script: {e}")
            return False
    
    def delete_script(self, name: str) -> bool:
        """Delete a script from the library"""
        if name not in self.scripts:
            return False
            
        script_file = self.library_path / f"{name}.js"
        try:
            script_file.unlink()
            del self.scripts[name]
            return True
        except Exception as e:
            print(f"Failed to delete script: {e}")
            return False

# ============================================================================
# Example Module: WhatsApp Automation
# ============================================================================

class WhatsAppAutomation(BaseAutomation):
    """
    Example module for automating WhatsApp Web.
    """
    
    def __init__(self, session_name: str = None):
        super().__init__(session_name or "whatsapp")
        self.script_lib = ScriptLibrary()
        
    def wait_for_qr(self, timeout: int = 60) -> bool:
        """Wait for QR code to appear"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            result = self.evaluate(
                "document.querySelector('[data-testid=\"qrcode\"]') !== null"
            )
            if result.get('result', {}).get('value', False):
                return True
            time.sleep(2)
        return False
    
    def is_authenticated(self) -> bool:
        """Check if user is authenticated"""
        result = self.evaluate(
            "document.querySelector('[data-testid=\"chat-list\"]') !== null"
        )
        return result.get('result', {}).get('value', False)
    
    def send_message(self, contact: str, message: str) -> bool:
        """Send a message to a contact"""
        script = f"""
        (function() {{
            // Search for contact
            const searchInput = document.querySelector('[data-testid="chat-list-search"]');
            if (!searchInput) return {{error: 'Search input not found'}};
            
            searchInput.value = '{contact}';
            searchInput.dispatchEvent(new Event('input'));
            
            // Click on the contact
            const chatItem = document.querySelector('[data-testid="chat-list"] [role="row"]');
            if (!chatItem) return {{error: 'Contact not found'}};
            chatItem.click();
            
            // Type message
            const messageInput = document.querySelector('[data-testid="conversation-compose-input"]');
            if (!messageInput) return {{error: 'Message input not found'}};
            
            messageInput.innerHTML = '{message}';
            messageInput.dispatchEvent(new Event('input'));
            
            // Send message
            const sendButton = document.querySelector('[data-testid="compose-btn-send"]');
            if (!sendButton) return {{error: 'Send button not found'}};
            sendButton.click();
            
            return {{success: true}};
        }})()
        """
        result = self.evaluate(script)
        return result.get('result', {}).get('value', {}).get('success', False)
    
    def get_unread_count(self) -> int:
        """Get count of unread messages"""
        result = self.evaluate(
            "document.querySelectorAll('[data-testid=\"unread\"]').length"
        )
        return result.get('result', {}).get('value', 0)

# ============================================================================
# Example Module: E-commerce Automation
# ============================================================================

class EcommerceAutomation(BaseAutomation):
    """
    Example module for automating e-commerce sites.
    """
    
    def __init__(self, session_name: str = None, site_url: str = None):
        super().__init__(session_name or "ecommerce")
        self.site_url = site_url or "https://example.com"
        self.script_lib = ScriptLibrary()
        
    def search_product(self, query: str) -> Dict:
        """Search for a product"""
        script = f"""
        (function() {{
            const searchInput = document.querySelector('[name="q"]') || 
                               document.querySelector('[name="search"]') ||
                               document.querySelector('input[type="search"]');
            if (!searchInput) return {{error: 'Search input not found'}};
            
            searchInput.value = '{query}';
            searchInput.dispatchEvent(new Event('input'));
            
            const searchForm = searchInput.closest('form');
            if (searchForm) {{
                searchForm.submit();
                return {{success: true, method: 'form'}};
            }}
            
            const searchButton = document.querySelector('button[type="submit"]') ||
                                document.querySelector('input[type="submit"]');
            if (searchButton) {{
                searchButton.click();
                return {{success: true, method: 'button'}};
            }}
            
            return {{error: 'No submit method found'}};
        }})()
        """
        result = self.evaluate(script)
        return result.get('result', {}).get('value', {})
    
    def add_to_cart(self) -> Dict:
        """Add current product to cart"""
        script = """
        (function() {
            const addButton = document.querySelector('[data-testid="add-to-cart"]') ||
                             document.querySelector('button:contains("Add to Cart")') ||
                             document.querySelector('button:contains("Add to Basket")');
            
            if (!addButton) return {error: 'Add to cart button not found'};
            
            addButton.click();
            return {success: true};
        })()
        """
        result = self.evaluate(script)
        return result.get('result', {}).get('value', {})
    
    def checkout(self) -> Dict:
        """Proceed to checkout"""
        script = """
        (function() {
            const checkoutButton = document.querySelector('[data-testid="checkout"]') ||
                                   document.querySelector('button:contains("Checkout")') ||
                                   document.querySelector('button:contains("Proceed")');
            
            if (!checkoutButton) return {error: 'Checkout button not found'};
            
            checkoutButton.click();
            return {success: true};
        })()
        """
        result = self.evaluate(script)
        return result.get('result', {}).get('value', {})

# ============================================================================
# Script Execution Module
# ============================================================================

class ScriptExecutor:
    """
    Execute JavaScript scripts from the script library with parameters.
    """
    
    def __init__(self, automation: BaseAutomation, library: ScriptLibrary = None):
        self.automation = automation
        self.library = library or ScriptLibrary()
        
    def execute_script(self, script_name: str, params: Dict = None) -> Dict:
        """
        Execute a script from the library with parameters.
        
        Args:
            script_name: Name of the script in the library
            params: Parameters to pass to the script
            
        Returns:
            Script execution result
        """
        script = self.library.get_script(script_name)
        if not script:
            return {'error': f'Script "{script_name}" not found in library'}
            
        # Replace template variables
        if params:
            for key, value in params.items():
                script = script.replace(f'{{{{{key}}}}}', str(value))
                
        return self.automation.evaluate(script)
    
    def list_available_scripts(self) -> List[str]:
        """List all available scripts"""
        return self.library.list_scripts()

# ============================================================================
# Command Line Interface
# ============================================================================

def main():
    """Example CLI for testing automation modules"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Chrome Automation Module Runner')
    parser.add_argument('--module', choices=['whatsapp', 'ecommerce', 'script'], 
                       required=True, help='Module to run')
    parser.add_argument('--session', default='default', help='Session name')
    parser.add_argument('--action', help='Action to perform')
    parser.add_argument('--params', help='JSON parameters for the action')
    
    args = parser.parse_args()
    
    if args.module == 'whatsapp':
        wa = WhatsAppAutomation(args.session)
        if args.action == 'send_message':
            params = json.loads(args.params or '{}')
            result = wa.send_message(
                params.get('contact', ''),
                params.get('message', '')
            )
            print(json.dumps(result, indent=2))
        elif args.action == 'status':
            print(f"Authenticated: {wa.is_authenticated()}")
            print(f"Unread: {wa.get_unread_count()}")
            
    elif args.module == 'ecommerce':
        ec = EcommerceAutomation(args.session)
        if args.action == 'search':
            result = ec.search_product(args.params or 'product')
            print(json.dumps(result, indent=2))
            
    elif args.module == 'script':
        auto = BaseAutomation(args.session)
        executor = ScriptExecutor(auto)
        if args.action == 'list':
            print("Available scripts:")
            for script in executor.list_available_scripts():
                print(f"  - {script}")
        elif args.action == 'run':
            params = json.loads(args.params or '{}')
            result = executor.execute_script(params.get('script', ''), params.get('params', {}))
            print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()
```

### Script Library Structure

Create scripts in: `/data/data/com.termux/files/home/automation/chrome-launcher/scripts-library/`

Example script: `login.js`
```javascript
(function() {
    // Login automation script
    // Usage: {{username}}, {{password}} are replaced with parameters
    
    const usernameField = document.querySelector('[name="username"]') || 
                         document.querySelector('[name="email"]') ||
                         document.querySelector('[type="email"]');
    const passwordField = document.querySelector('[name="password"]') || 
                         document.querySelector('[type="password"]');
    const submitButton = document.querySelector('[type="submit"]') ||
                        document.querySelector('button:contains("Login")');
    
    if (!usernameField || !passwordField) {
        return {error: 'Login form fields not found'};
    }
    
    usernameField.value = '{{username}}';
    usernameField.dispatchEvent(new Event('input'));
    
    passwordField.value = '{{password}}';
    passwordField.dispatchEvent(new Event('input'));
    
    if (submitButton) {
        submitButton.click();
        return {success: true, method: 'click'};
    }
    
    // Try to submit form
    const form = usernameField.closest('form');
    if (form) {
        form.submit();
        return {success: true, method: 'submit'};
    }
    
    return {error: 'No submit method found'};
})()
```

Example script: `extract_data.js`
```javascript
(function() {
    // Extract data from page
    // Returns structured data from the page
    
    const data = {
        title: document.title,
        url: window.location.href,
        headings: Array.from(document.querySelectorAll('h1, h2, h3')).map(el => el.textContent.trim()),
        links: Array.from(document.querySelectorAll('a')).map(el => ({
            text: el.textContent.trim(),
            href: el.href
        })),
        images: Array.from(document.querySelectorAll('img')).map(el => ({
            alt: el.alt || '',
            src: el.src
        })),
        text: document.body.innerText.substring(0, 5000)
    };
    
    return data;
})()
```

## Best Practices

### 1. Session Management
- Always call `_ensure_session_running()` before any operation
- Use the session info file to get WebSocket IDs
- Implement retry logic for network operations

### 2. Script Design
- Use IIFE (Immediately Invoked Function Expression) for scripts
- Return structured data from scripts
- Use template variables with `{{variable}}` syntax for parameters
- Include error handling in scripts

### 3. Error Handling
```python
try:
    result = automation.evaluate(script)
    if 'error' in result:
        self.logger.error(f"Script error: {result['error']}")
        return None
    return result.get('result', {}).get('value')
except Exception as e:
    self.logger.error(f"Execution error: {e}")
    return None
```

### 4. Logging
```python
import logging

logger = logging.getLogger(__name__)
logger.info("Action performed")
logger.warning("Warning condition")
logger.error("Error condition")
```

### 5. Resource Management
- Close WebSocket connections when done
- Use context managers where appropriate
- Implement proper cleanup in `__del__` or context manager

## Common CDP Commands

| Command | Method | Parameters |
|---------|--------|------------|
| Navigate | `Page.navigate` | `{"url": "https://..."}` |
| Get HTML | `Runtime.evaluate` | `{"expression": "document.documentElement.outerHTML"}` |
| Click | `Runtime.evaluate` | `{"expression": "document.querySelector('selector').click()"}` |
| Screenshot | `Page.captureScreenshot` | `{"format": "png"}` |
| Evaluate | `Runtime.evaluate` | `{"expression": "JS code", "returnByValue": true}` |

## Quick Start Examples

### Example 1: Basic Navigation and Data Extraction

```python
from modules.template import BaseAutomation, ScriptLibrary

# Initialize
auto = BaseAutomation("my-session")
library = ScriptLibrary()

# Navigate
auto.navigate("https://example.com")
time.sleep(3)

# Extract data using a script
result = auto.evaluate(library.get_script("extract_data"))
data = result.get('result', {}).get('value', {})
print(data)
```

### Example 2: Form Automation

```python
from modules.template import BaseAutomation

auto = BaseAutomation("my-session")

# Fill and submit a form
script = """
(function() {
    const form = document.querySelector('form');
    if (!form) return {error: 'Form not found'};
    
    // Fill fields
    document.querySelector('[name="email"]').value = 'user@example.com';
    document.querySelector('[name="password"]').value = 'password123';
    
    // Submit
    form.submit();
    return {success: true};
})()
"""

result = auto.evaluate(script)
```

### Example 3: Running Scripts with Parameters

```python
from modules.template import ScriptExecutor, BaseAutomation

auto = BaseAutomation("my-session")
executor = ScriptExecutor(auto)

# Run login script with parameters
result = executor.execute_script('login', {
    'username': 'myuser',
    'password': 'mypass'
})

print(result.get('result', {}).get('value', {}))
```

## Testing Your Module

```bash
# Test the API is running
curl http://127.0.0.1:5000/health

# List sessions
curl http://127.0.0.1:5000/sessions

# Start a session
curl -X POST http://127.0.0.1:5000/session/test/start \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com"}'

# Navigate
curl -X POST http://127.0.0.1:5000/session/test/navigate \
  -H "Content-Type: application/json" \
  -d '{"url": "https://google.com"}'

# Execute JavaScript
curl -X POST http://127.0.0.1:5000/session/test/evaluate \
  -H "Content-Type: application/json" \
  -d '{"expression": "document.title"}'
```

## Directory Structure

```
/data/data/com.termux/files/home/automation/chrome-launcher/
├── cdpv119.py          # Chrome Session Manager
├── api.py              # API Layer
├── daemon.py           # Daemon with WebSocket support
├── modules/
│   └── template.py     # Base module template
├── scripts-library/
│   ├── login.js
│   ├── extract_data.js
│   └── ... (your scripts)
└── session_db.py       # Session database

/data/data/com.termux/files/home/chrome-sessions/
├── session_info.json   # Session info with WebSocket IDs
└── [session profiles]/

/data/data/com.termux/files/home/chrome-logs/
└── [log files]/
```

## Troubleshooting

### Session Not Found
```bash
# Check if session exists
cat /data/data/com.termux/files/home/chrome-sessions/session_info.json
```

### WebSocket Connection Issues
```python
# Verify WebSocket ID is valid
ws_url = auto.get_websocket_connection()
print(f"WebSocket URL: {ws_url}")
```

### API Connection Issues
```bash
# Check if API is running
ps aux | grep api.py
# Restart API
python api.py
```

### Script Library Issues
```bash
# Check script exists
ls /data/data/com.termux/files/home/automation/chrome-launcher/scripts-library/
```

## Contributing Modules

1. Create a new module in the `modules/` directory
2. Inherit from `BaseAutomation` class
3. Add module-specific methods
4. Use the ScriptLibrary for reusable scripts
5. Add documentation and examples
6. Test thoroughly with different session states
