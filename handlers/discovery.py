"""Periodic discovery tasks — enqueue URL discovery on a schedule."""

from agent.registry import register_handler


def handle_discovery(payload: dict) -> dict:
    """Discovery task: fetch new URLs from configured sources."""
    sources = payload.get("sources", ["unstop"])
    results = {}

    if "unstop" in sources:
        from handlers.chrome_handlers import handle_unstop_fetch
        limit = payload.get("limit", 50)
        results["unstop"] = handle_unstop_fetch({"limit": limit})

    return {"discovered": results, "sources": sources}


register_handler("discovery", handle_discovery)
