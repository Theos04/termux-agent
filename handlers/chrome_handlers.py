"""Chrome CDP task handlers — wraps termux-agent scripts."""

import subprocess
import sys
from pathlib import Path
from typing import Any

from agent.registry import register_handler, register_subscriber
from agent.events import Event


def _launcher_dir() -> Path:
    from agent.config import _launcher_dir as cfg_dir
    return Path(cfg_dir())


def _run_script(script: str, args: list[str], timeout: int = 300) -> dict[str, Any]:
    script_path = _launcher_dir() / script
    if not script_path.exists():
        raise FileNotFoundError(f"Script not found: {script_path}")

    result = subprocess.run(
        [sys.executable, str(script_path), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(_launcher_dir()),
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"{script} failed (exit {result.returncode}): {result.stderr or result.stdout}"
        )
    return {
        "stdout": result.stdout[-4000:] if result.stdout else "",
        "stderr": result.stderr[-2000:] if result.stderr else "",
        "returncode": result.returncode,
    }


def _url_args(payload: dict) -> list[str]:
    url = payload.get("url")
    if not url:
        raise ValueError("url is required")
    return [url]


def handle_fetch_page(payload: dict) -> dict:
    args = _url_args(payload)
    if payload.get("output"):
        args.extend(["--output", payload["output"]])
    return _run_script("fetch_page.py", args, payload.get("timeout", 300))


def handle_fetch_page2(payload: dict) -> dict:
    return _run_script("fetch_page2.py", _url_args(payload), payload.get("timeout", 300))


def handle_fetch_page_llm(payload: dict) -> dict:
    return _run_script("fetch_page_llm.py", _url_args(payload), payload.get("timeout", 300))


def handle_fetch_page_job_read_more(payload: dict) -> dict:
    return _run_script(
        "fetch_page_job_read_more.py", _url_args(payload), payload.get("timeout", 300)
    )


def handle_launch_chrome(payload: dict) -> dict:
    args = []
    if payload.get("port"):
        args.extend(["--port", str(payload["port"])])
    if payload.get("headless"):
        args.append("--headless")
    return _run_script("launch-chrome.py", args, payload.get("timeout", 60))


def handle_run_js(payload: dict) -> dict:
    js = payload.get("js") or payload.get("script")
    if not js:
        raise ValueError("js or script is required")
    args = [js]
    if payload.get("port"):
        args.extend(["--port", str(payload["port"])])
    return _run_script("run-js-any-chrome.py", args, payload.get("timeout", 120))


def handle_unstop_list(payload: dict) -> dict:
    """Fetch job/hackathon lists via get-list-unstop.py."""
    args = []
    if payload.get("port"):
        args.extend(["--port", str(payload["port"])])
    return _run_script("get-list-unstop.py", args, payload.get("timeout", 600))


def handle_web_scrape(payload: dict) -> dict:
    url = payload.get("url")
    args = [url] if url else []
    return _run_script("web_scraper_unstop.py", args, payload.get("timeout", 600))


def handle_cdp(payload: dict) -> dict:
    """Run any CDP script (cdpv116.py, cdp_01.py, etc.)."""
    script = payload.get("script", "cdpv116.py")
    args = [str(a) for a in payload.get("args", [])]
    return _run_script(script, args, payload.get("timeout", 300))


def handle_dynamic_js(payload: dict) -> dict:
    """Run JS via dynamic_chrome_executor.py."""
    js = payload.get("js") or payload.get("script")
    if not js:
        raise ValueError("js or script is required")
    args = []
    if payload.get("port"):
        args.extend(["--port", str(payload["port"])])
    args.append(js)
    return _run_script("dynamic_chrome_executor.py", args, payload.get("timeout", 120))


def handle_fix_devtools(payload: dict) -> dict:
    return _run_script("fix_devtools.py", [], payload.get("timeout", 60))


def handle_shell(payload: dict) -> dict:
    script = payload.get("script")
    if not script:
        raise ValueError("script is required")
    args = [str(a) for a in payload.get("args", [])]
    return _run_script(script, args, payload.get("timeout", 300))


def handle_echo(payload: dict) -> dict:
    return {"echo": payload, "status": "ok"}


def _log_task_events(event: Event) -> None:
    if event.event_type in ("task.failed", "task.timeout"):
        print(f"[event] {event.event_type}: {event.payload}")


register_handler("fetch_page", handle_fetch_page)
register_handler("fetch_page2", handle_fetch_page2)
register_handler("fetch_page_llm", handle_fetch_page_llm)
register_handler("fetch_page_job_read_more", handle_fetch_page_job_read_more)
register_handler("launch_chrome", handle_launch_chrome)
register_handler("run_js", handle_run_js)
register_handler("unstop_list", handle_unstop_list)
register_handler("web_scrape", handle_web_scrape)
register_handler("cdp", handle_cdp)
register_handler("dynamic_js", handle_dynamic_js)
register_handler("fix_devtools", handle_fix_devtools)
register_handler("shell", handle_shell)
register_handler("echo", handle_echo)

register_subscriber("task.failed", _log_task_events)
register_subscriber("task.timeout", _log_task_events)
