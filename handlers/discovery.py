"""Periodic discovery tasks."""

from agent.registry import register_handler


def handle_discovery(payload: dict) -> dict:
    sources = payload.get("sources", ["unstop"])
    results = {}

    if "unstop" in sources:
        from handlers.chrome_handlers import handle_unstop_list
        results["unstop"] = handle_unstop_list({"port": payload.get("port", 9236)})

    return {"discovered": results, "sources": sources}


register_handler("discovery", handle_discovery)
