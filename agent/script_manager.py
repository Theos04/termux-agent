"""Load and execute JS from scripts-library."""

import json
import os
from pathlib import Path
from typing import Any, Optional

from agent.cdp_browser import CDPBrowser


class ScriptManager:
    def __init__(self, base_dir: Optional[str] = None):
        if base_dir:
            self.script_dir = Path(base_dir)
        else:
            from agent.config import _LAUNCHER_ROOT
            self.script_dir = _LAUNCHER_ROOT / "scripts-library"
        self.scripts: dict[str, str] = {}
        self.load_all()

    def load_all(self) -> None:
        self.scripts.clear()
        if not self.script_dir.exists():
            return
        for path in self.script_dir.rglob("*.js"):
            if path.stat().st_size == 0:
                continue
            rel = path.relative_to(self.script_dir).with_suffix("")
            key = str(rel).replace("\\", "/")
            self.scripts[key] = path.read_text(encoding="utf-8")

    def list_scripts(self) -> list[str]:
        return sorted(self.scripts.keys())

    def get(self, name: str) -> Optional[str]:
        if name in self.scripts:
            return self.scripts[name]
        # allow unstop/get-job-list or get-job-list
        for key, content in self.scripts.items():
            if key.endswith(name) or key.replace("/", "") == name.replace("/", ""):
                return content
        return None

    def execute(
        self, name: str, browser: CDPBrowser, params: Optional[dict] = None
    ) -> Any:
        script = self.get(name)
        if not script:
            raise FileNotFoundError(f"Script not found: {name}")
        if params:
            browser.execute_js(f"const params = {json.dumps(params)};")
        return browser.execute_js(script, await_promise=True)


_manager: Optional[ScriptManager] = None


def get_script_manager() -> ScriptManager:
    global _manager
    if _manager is None:
        _manager = ScriptManager()
    return _manager
