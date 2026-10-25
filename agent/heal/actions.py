"""Concrete heal actions for each HealClass."""

from __future__ import annotations

import logging
import os
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from .classifier import HealClass

logger = logging.getLogger(__name__)


@dataclass
class HealActionResult:
    ok: bool
    action: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_chrome_cdp(
    port: Optional[int] = None,
    notify: Optional[Callable[[str], None]] = None,
) -> HealActionResult:
    """Launch/attach Chrome via PageFetcher.ensure_chrome when available."""
    port = port or int(os.environ.get("CDP_PORT", "9222"))
    try:
        from agent_bridge import PageFetcher

        fetcher = PageFetcher(port=port)
        result = fetcher.ensure_chrome(notify=notify)
        ok = bool(result.get("ok"))
        return HealActionResult(
            ok=ok,
            action="ensure_chrome",
            message=str(result.get("message") or result),
            details=dict(result) if isinstance(result, dict) else {},
        )
    except Exception as exc:
        logger.warning("ensure_chrome_cdp failed: %s", exc)
        return HealActionResult(
            ok=False,
            action="ensure_chrome",
            message=str(exc),
        )


def reconnect_cdp(port: Optional[int] = None) -> HealActionResult:
    port = port or int(os.environ.get("CDP_PORT", "9222"))
    try:
        from agent_bridge import PageFetcher

        fetcher = PageFetcher(port=port)
        if fetcher.cdp_reachable():
            ok = fetcher.connect(port)
            return HealActionResult(
                ok=bool(ok),
                action="reconnect_cdp",
                message=f"CDP reconnect on {port}: {ok}",
                details={"port": port, "connected": bool(ok)},
            )
        return HealActionResult(
            ok=False,
            action="reconnect_cdp",
            message=f"CDP not reachable on {port}",
            details={"port": port},
        )
    except Exception as exc:
        return HealActionResult(
            ok=False, action="reconnect_cdp", message=str(exc)
        )


def reset_model_circuit() -> HealActionResult:
    """Clear mmcp circuit breaker state when package is present."""
    try:
        from mmcp.models.router import ModelRouter
        from mmcp.config import MMCPConfig

        cfg = MMCPConfig.from_env()
        router = ModelRouter(cfg)
        reset_n = 0
        for ep in getattr(router, "endpoints", []) or []:
            circuit = getattr(ep, "circuit", None) or getattr(ep, "state", None)
            if circuit is None:
                continue
            for attr in ("failures", "fail_count", "opened_at", "open_until"):
                if hasattr(circuit, attr):
                    try:
                        setattr(circuit, attr, 0 if "count" in attr or attr == "failures" else None)
                        reset_n += 1
                    except Exception:
                        pass
            if hasattr(circuit, "reset"):
                circuit.reset()
                reset_n += 1
            if hasattr(circuit, "state"):
                try:
                    circuit.state = "closed"
                    reset_n += 1
                except Exception:
                    pass
        return HealActionResult(
            ok=True,
            action="reset_model_circuit",
            message=f"Circuit reset attempts={reset_n}",
            details={"resets": reset_n},
        )
    except ImportError:
        return HealActionResult(
            ok=True,
            action="reset_model_circuit",
            message="mmcp not installed; skipped",
        )
    except Exception as exc:
        return HealActionResult(
            ok=False, action="reset_model_circuit", message=str(exc)
        )


def research_unknown(query: str) -> HealActionResult:
    """Optional Agent-Reach lookup — never runs arbitrary shell beyond agent-reach."""
    if not query.strip():
        return HealActionResult(
            ok=False, action="research", message="empty query"
        )
    try:
        proc = subprocess.run(
            ["agent-reach", "github", "search", query[:120]],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        out = (proc.stdout or proc.stderr or "").strip()[:2000]
        return HealActionResult(
            ok=proc.returncode == 0,
            action="research",
            message=out or f"exit={proc.returncode}",
            details={"returncode": proc.returncode},
        )
    except FileNotFoundError:
        return HealActionResult(
            ok=False,
            action="research",
            message="agent-reach not installed (see deploy/selfheal/README.md)",
        )
    except Exception as exc:
        return HealActionResult(ok=False, action="research", message=str(exc))


def run_heal_action(
    heal_class: HealClass,
    *,
    error: str = "",
    port: Optional[int] = None,
    research_after: int = 2,
    heal_attempt: int = 0,
) -> HealActionResult:
    if heal_class in (HealClass.CHROME_DEAD, HealClass.CDP_DOWN):
        ensured = ensure_chrome_cdp(port=port)
        if ensured.ok:
            return ensured
        recon = reconnect_cdp(port=port)
        if recon.ok:
            return recon
        return ensured

    if heal_class == HealClass.MODEL_CIRCUIT:
        return reset_model_circuit()

    if heal_class == HealClass.MAPS_SCRIPT:
        # Soft heal: ensure CDP then leave retry to queue
        ensured = ensure_chrome_cdp(port=port)
        if not ensured.ok:
            return ensured
        return HealActionResult(
            ok=True,
            action="maps_prepare_retry",
            message="Chrome/CDP ready for maps script retry",
            details=ensured.details,
        )

    if heal_class in (HealClass.TIMEOUT, HealClass.TASK_STUCK):
        return HealActionResult(
            ok=True,
            action="requeue",
            message=f"{heal_class.value}: will requeue via retry path",
            details={"at": _utcnow()},
        )

    if heal_class == HealClass.UNKNOWN and heal_attempt >= research_after:
        q = error or "chrome CDP automation failure"
        return research_unknown(q)

    return HealActionResult(
        ok=True,
        action="noop_retry",
        message="No specific fix; rely on task retry",
        details={"heal_class": heal_class.value},
    )
