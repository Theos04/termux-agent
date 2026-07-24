# client.py
import requests
import json
from typing import Optional, Dict, Any

class ChromeClient:
    def __init__(self, base_url="http://127.0.0.1:5000", session_name="unstop"):
        self.base_url = base_url
        self.session = session_name
    
    def _request(self, method, endpoint, data=None):
        """Make HTTP request to the daemon"""
        url = f"{self.base_url}{endpoint}"
        headers = {'Content-Type': 'application/json'}
        
        try:
            if method.upper() == 'GET':
                resp = requests.get(url, headers=headers)
            else:
                resp = requests.post(url, json=data, headers=headers)
            
            if resp.status_code == 200:
                return resp.json()
            else:
                return {'error': f'HTTP {resp.status_code}', 'detail': resp.text}
        except requests.exceptions.ConnectionError:
            return {'error': 'Connection refused - is the daemon running?'}
        except Exception as e:
            return {'error': str(e)}
    
    # Session management
    def start_session(self, name: str = None, url: str = "https://unstop.com/"):
        """Start a new Chrome session"""
        name = name or self.session
        return self._request('POST', f'/session/{name}/start', {'name': name, 'url': url})
    
    def stop_session(self, name: str = None):
        """Stop a Chrome session"""
        name = name or self.session
        return self._request('POST', f'/session/{name}/stop')
    
    def get_status(self, name: str = None):
        """Get session status"""
        name = name or self.session
        return self._request('GET', f'/session/{name}/status')
    
    def list_sessions(self):
        """List all sessions"""
        return self._request('GET', '/sessions')
    
    # Navigation
    def navigate(self, url: str, name: str = None):
        """Navigate to URL"""
        name = name or self.session
        return self._request('POST', f'/session/{name}/navigate', {'url': url})
    
    def get_url(self, name: str = None):
        """Get current URL"""
        name = name or self.session
        return self._request('GET', f'/session/{name}/url')
    
    # DOM operations
    def get_html(self, name: str = None):
        """Get page HTML"""
        name = name or self.session
        return self._request('GET', f'/session/{name}/html')
    
    def click(self, selector: str, name: str = None):
        """Click element by CSS selector"""
        name = name or self.session
        return self._request('POST', f'/session/{name}/click', {'selector': selector})
    
    # JavaScript
    def evaluate(self, expression: str, name: str = None):
        """Execute JavaScript"""
        name = name or self.session
        return self._request('POST', f'/session/{name}/evaluate', {'expression': expression})
    
    # Screenshot
    def screenshot(self, name: str = None):
        """Take screenshot"""
        name = name or self.session
        return self._request('GET', f'/session/{name}/screenshot')
    
    # CDP
    def cdp(self, method: str, params: Dict = None, name: str = None):
        """Execute raw CDP command"""
        name = name or self.session
        return self._request('POST', f'/session/{name}/cdp', {'method': method, 'params': params or {}})
    
    # Health check
    def health(self):
        """Check if daemon is running"""
        return self._request('GET', '/health')
    
    # Convenience methods
    def wait_for_element(self, selector: str, timeout: int = 10):
        """Wait for element to appear"""
        js = f"""
        (function() {{
            return new Promise((resolve) => {{
                let attempts = 0;
                const maxAttempts = {timeout * 10};
                const check = () => {{
                    attempts++;
                    const el = document.querySelector('{selector}');
                    if (el) {{
                        resolve(true);
                    }} else if (attempts >= maxAttempts) {{
                        resolve(false);
                    }} else {{
                        setTimeout(check, 100);
                    }}
                }};
                check();
            }});
        }})()
        """
        result = self.evaluate(js)
        if 'result' in result and 'result' in result['result']:
            return result['result']['result']['value']
        return False
    
    def get_text(self, selector: str):
        """Get text content of element"""
        js = f"""
        (function() {{
            const el = document.querySelector('{selector}');
            return el ? el.textContent.trim() : null;
        }})()
        """
        result = self.evaluate(js)
        if 'result' in result and 'result' in result['result']:
            return result['result']['result']['value']
        return None
    
    def scroll_to_bottom(self):
        """Scroll to bottom of page"""
        return self.evaluate("window.scrollTo(0, document.body.scrollHeight)")

def demo():
    """Demonstrate the client"""
    print("🔧 Chrome Client Demo")
    client = ChromeClient()
    
    # Check if daemon is running
    health = client.health()
    if 'error' in health:
        print(f"❌ Daemon not running: {health['error']}")
        print("   Start it with: python api.py")
        return
    
    print("✅ Connected to daemon")
    
    # List sessions
    sessions = client.list_sessions()
    print(f"📋 Sessions: {sessions}")
    
    # Navigate
    print("🔄 Navigating to Unstop...")
    result = client.navigate("https://unstop.com/job/")
    print(f"   Result: {result}")
    
    # Get URL
    url = client.get_url()
    print(f"📍 Current URL: {url}")
    
    # Get title
    title = client.evaluate("document.title")
    print(f"📄 Page title: {title}")
    
    # Get some stats
    stats = client.evaluate("""
        ({
            links: document.querySelectorAll('a').length,
            buttons: document.querySelectorAll('button').length,
            images: document.querySelectorAll('img').length,
            jobs: document.querySelectorAll('[class*="job"]').length
        })
    """)
    print(f"📊 Page stats: {stats}")
    
    # Take screenshot
    print("📸 Taking screenshot...")
    screenshot = client.screenshot()
    if 'screenshot' in screenshot:
        print(f"   ✅ Screenshot captured ({len(screenshot['screenshot'])} chars)")
    
    print("✅ Demo complete!")

if __name__ == "__main__":
    demo()
