"""Map task/runtime errors to heal classes."""

from __future__ import annotations

from enum import Enum
from typing import Optional


class HealClass(str, Enum):
    CDP_DOWN = "cdp_down"
    CHROME_DEAD = "chrome_dead"
    TASK_STUCK = "task_stuck"
    TIMEOUT = "timeout"
    MODEL_CIRCUIT = "model_circuit"
    MAPS_SCRIPT = "maps_script"
    UNKNOWN = "unknown"


_PATTERNS: list[tuple[HealClass, tuple[str, ...]]] = [
    (
        HealClass.CHROME_DEAD,
        (
            "chrome crashed",
            "chrome not running",
            "browser process",
            "no chrome",
            "failed to launch chrome",
            "launch-chrome",
        ),
    ),
    (
        HealClass.CDP_DOWN,
        (
            "cdp",
            "devtools",
            "websocket",
            "9222",
            "not connected",
            "connection refused",
            "econnrefused",
            "target closed",
            "session closed",
            "inspectable",
        ),
    ),
    (
        HealClass.MODEL_CIRCUIT,
        (
            "circuit open",
            "circuit_breaker",
            "model unavailable",
            "all models failed",
            "llama-cli",
            "gguf",
        ),
    ),
    (
        HealClass.MAPS_SCRIPT,
        (
            "maps",
            "hfpxzc",
            "role=feed",
            "google-maps",
            "scroll scrape",
            "consent",
            "no feed",
        ),
    ),
    (
        HealClass.TIMEOUT,
        ("timed out", "timeout", "task timed out"),
    ),
    (
        HealClass.TASK_STUCK,
        ("orphan", "stuck", "worker dead", "no heartbeat"),
    ),
]


def classify_error(
    error: Optional[str] = None,
    *,
    status: Optional[str] = None,
    task_type: Optional[str] = None,
) -> HealClass:
    if status == "timeout":
        return HealClass.TIMEOUT
    if status == "running":
        return HealClass.TASK_STUCK

    text = (error or "").lower()
    if not text:
        return HealClass.UNKNOWN

    for heal_class, needles in _PATTERNS:
        if any(n in text for n in needles):
            # Prefer chrome_dead over generic cdp when both match
            if heal_class == HealClass.CDP_DOWN and any(
                n in text for n in _PATTERNS[0][1]
            ):
                return HealClass.CHROME_DEAD
            return heal_class

    if task_type and "maps" in task_type.lower() and (
        "script" in text or "js" in text or "evaluate" in text
    ):
        return HealClass.MAPS_SCRIPT

    return HealClass.UNKNOWN
