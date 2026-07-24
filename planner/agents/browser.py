"""Browser agent for Chrome automation"""
import asyncio
import time
import base64
from typing import List, Any, Optional
from .base import Agent
from ..task import Task
from ..context import Context

class BrowserAgent(Agent):
    def __init__(self, daemon=None):
        self.daemon = daemon
        self._session = None
    
    def capabilities(self) -> List[str]:
        return [
            "browser.navigate",
            "browser.extract",
            "browser.click",
            "browser.fill",
            "browser.screenshot",
            "browser.execute_js",
            "browser.get_html",
            "browser.get_text",
            "browser.wait_for"
        ]
    
    def can_execute(self, action: str) -> bool:
        return action in self.capabilities()
    
    def execute(self, task: Task, context: Context) -> Any:
        action = task.action
        params = task.parameters
        
        session_name = params.get("session", "unstop")
        self._ensure_session(session_name, context)
        
        if action == "browser.navigate":
            return self._navigate(params.get("url"), params.get("wait", 5))
        elif action == "browser.extract":
            return self._extract(params.get("selector"), params.get("multiple", False))
        elif action == "browser.click":
            return self._click(params.get("selector"))
        elif action == "browser.fill":
            return self._fill(params.get("selector"), params.get("value"))
        elif action == "browser.screenshot":
            return self._screenshot(params.get("path"))
        elif action == "browser.execute_js":
            return self._execute_js(params.get("script"), params.get("await_promise", False))
        elif action == "browser.get_html":
            return self._get_html()
        elif action == "browser.get_text":
            return self._get_text()
        elif action == "browser.wait_for":
            return self._wait_for(params.get("selector"), params.get("timeout", 30))
        else:
            raise ValueError(f"Unknown action: {action}")
    
    def _ensure_session(self, name: str, context: Context):
        if self.daemon:
            session = self.daemon.get_session(name)
            if not session:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                url = context.get("browser_url", "https://unstop.com/")
                result = loop.run_until_complete(
                    self.daemon.start_session(name, url)
                )
                if not result.get("success"):
                    raise RuntimeError(f"Failed to start session: {result}")
            self._session = name
    
    def _navigate(self, url: str, wait: int = 5):
        if not self.daemon:
            return {"success": False, "error": "No daemon available"}
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(
            self.daemon.navigate(self._session, url)
        )
        time.sleep(wait)
        return result
    
    def _extract(self, selector: str, multiple: bool = False):
        if multiple:
            script = f"""
            const els = document.querySelectorAll('{selector}');
            return Array.from(els).map(el => el.innerText || el.textContent || '');
            """
        else:
            script = f"""
            const el = document.querySelector('{selector}');
            if (!el) return null;
            return el.innerText || el.textContent || '';
            """
        return self._execute_js(script)
    
    def _click(self, selector: str):
        script = f"""
        const el = document.querySelector('{selector}');
        if (!el) {{ return {{success: false, error: 'Element not found'}}; }}
        el.click();
        return {{success: true}};
        """
        return self._execute_js(script)
    
    def _fill(self, selector: str, value: str):
        script = f"""
        const el = document.querySelector('{selector}');
        if (!el) {{ return {{success: false, error: 'Element not found'}}; }}
        el.value = '{value}';
        el.dispatchEvent(new Event('input', {{bubbles: true}}));
        return {{success: true}};
        """
        return self._execute_js(script)
    
    def _screenshot(self, path: Optional[str] = None):
        if not self.daemon:
            return {"success": False, "error": "No daemon available"}
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(
            self.daemon.screenshot(self._session)
        )
        if path and result.get("screenshot"):
            with open(path, "wb") as f:
                f.write(base64.b64decode(result["screenshot"]))
            result["file"] = path
        return result
    
    def _execute_js(self, script: str, await_promise: bool = False):
        if not self.daemon:
            return {"success": False, "error": "No daemon available"}
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(
            self.daemon.evaluate(self._session, script)
        )
    
    def _get_html(self):
        return self._execute_js("document.documentElement.outerHTML")
    
    def _get_text(self):
        return self._execute_js("document.body.innerText")
    
    def _wait_for(self, selector: str, timeout: int = 30):
        start = time.time()
        while time.time() - start < timeout:
            result = self._execute_js(f"document.querySelector('{selector}')")
            if result and not result.get("error"):
                return {"success": True, "found": True}
            time.sleep(1)
        return {"success": False, "found": False, "timeout": True}
