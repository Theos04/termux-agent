"""Enhanced CDP browser client — navigate, interact, extract page content."""

import json
import time
from typing import Any, Optional

import requests

from fetch_page2 import ChromePage, SmartExtractor


class CDPBrowser:
    """MCP-style Chrome CDP client built on fetch_page2.ChromePage."""

    def __init__(self, port: int = 9226):
        self.port = port
        self._page = ChromePage(port)
        self._msg_id = 0
        self._extractor = SmartExtractor()

    @property
    def connected(self) -> bool:
        return self._page.connected

    def connect(self) -> bool:
        return self._page.connect()

    def close(self) -> None:
        self._page.close()

    def _next_id(self) -> int:
        self._msg_id += 1
        return self._msg_id

    def _send(self, method: str, params: Optional[dict] = None, timeout: float = 30) -> Any:
        if not self._page.connected:
            raise RuntimeError("Not connected to Chrome")
        cmd_id = self._next_id()
        self._page.ws.send(json.dumps({"id": cmd_id, "method": method, "params": params or {}}))
        start = time.time()
        while time.time() - start < timeout:
            resp = self._page.ws.recv()
            data = json.loads(resp)
            if data.get("id") == cmd_id:
                if "error" in data:
                    raise RuntimeError(data["error"].get("message", str(data["error"])))
                return data.get("result")
        raise TimeoutError(f"CDP command timed out: {method}")

    def _enable_domains(self) -> None:
        for domain in ("Page", "Runtime", "DOM"):
            try:
                self._send(f"{domain}.enable", timeout=5)
            except Exception:
                pass

    def navigate(self, url: str, wait: float = 3.0) -> dict[str, Any]:
        self._enable_domains()
        self._send("Page.navigate", {"url": url})
        time.sleep(wait)
        return self.page_info()

    def page_info(self) -> dict[str, Any]:
        return {
            "url": self._page.js("location.href") or self._page.page_url,
            "title": self._page.title(),
            "port": self.port,
        }

    def get_content(self, fmt: str = "text", max_chars: int = 50000) -> dict[str, Any]:
        info = self.page_info()
        if fmt == "html":
            content = (self._page.html() or "")[:max_chars]
        elif fmt == "links":
            links = self._page.js("""
                Array.from(document.querySelectorAll('a[href]')).slice(0, 200).map(a => ({
                    text: (a.innerText || '').trim().slice(0, 120),
                    href: a.href
                }))
            """) or []
            return {**info, "links": links, "count": len(links)}
        else:
            content = (self._page.text() or "")[:max_chars]

        return {**info, "format": fmt, "content": content, "length": len(content)}

    def execute_js(self, script: str, await_promise: bool = False) -> Any:
        return self._page.js(script, await_promise=await_promise)

    def click(self, selector: str) -> dict[str, Any]:
        result = self.execute_js(
            f"""
            (() => {{
                const el = document.querySelector({json.dumps(selector)});
                if (!el) return {{ok: false, error: 'Element not found'}};
                el.click();
                return {{ok: true, tag: el.tagName}};
            }})()
            """
        )
        time.sleep(0.5)
        return {"selector": selector, "result": result}

    def fill(self, selector: str, value: str) -> dict[str, Any]:
        result = self.execute_js(
            f"""
            (() => {{
                const el = document.querySelector({json.dumps(selector)});
                if (!el) return {{ok: false, error: 'Element not found'}};
                el.focus();
                el.value = {json.dumps(value)};
                el.dispatchEvent(new Event('input', {{bubbles: true}}));
                el.dispatchEvent(new Event('change', {{bubbles: true}}));
                return {{ok: true}};
            }})()
            """
        )
        return {"selector": selector, "result": result}

    def wait_for(self, selector: str, timeout: float = 15.0) -> dict[str, Any]:
        start = time.time()
        while time.time() - start < timeout:
            found = self.execute_js(f"!!document.querySelector({json.dumps(selector)})")
            if found:
                return {"selector": selector, "found": True}
            time.sleep(0.5)
        return {"selector": selector, "found": False}

    def extract(self) -> dict[str, Any]:
        text = self._page.text() or ""
        data = self._extractor.extract(text)
        return {**self.page_info(), "extracted": data}

    @staticmethod
    def list_tabs(port: int) -> list[dict]:
        try:
            resp = requests.get(f"http://127.0.0.1:{port}/json", timeout=5)
            return [t for t in resp.json() if t.get("type") == "page"]
        except Exception:
            return []
