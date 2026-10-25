"""WebSocket fan-out hub — bridges the synchronous EventBus to async WS clients.

Architecture
────────────
EventBus.emit() runs in a worker thread (sync).
WSHub.broadcast() must be called from async context.

The bridge is a thread-safe asyncio.Queue per task_id plus a global "all-events"
channel.  A background coroutine drains each queue and pushes to connected sockets.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

# Maximum events buffered per channel before dropping oldest
_QUEUE_MAXSIZE = 256


class WSHub:
    """Central fan-out hub for real-time WebSocket streaming.

    Usage
    -----
    hub = WSHub()
    await hub.start()                    # call once at app startup

    # In EventBus subscriber (sync thread):
    hub.publish_threadsafe(loop, task_id, event_dict)

    # In FastAPI route:
    await hub.connect(task_id, websocket)   # blocks until disconnect
    """

    def __init__(self) -> None:
        # task_id → set of connected WebSocket objects
        self._clients: dict[int | str, set[WebSocket]] = defaultdict(set)
        # task_id → asyncio.Queue feeding those clients
        self._queues: dict[int | str, asyncio.Queue] = {}
        self._lock = asyncio.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Capture the running event loop for threadsafe publishing."""
        self._loop = asyncio.get_running_loop()
        logger.info("WSHub started")

    # ------------------------------------------------------------------
    # Publishing (from sync worker threads)
    # ------------------------------------------------------------------

    def publish_threadsafe(
        self,
        loop: asyncio.AbstractEventLoop,
        channel: int | str,
        event: dict[str, Any],
    ) -> None:
        """Thread-safe: schedule broadcast from a sync thread."""
        asyncio.run_coroutine_threadsafe(self.broadcast(channel, event), loop)
        # Also push to wildcard channel "all"
        if channel != "all":
            asyncio.run_coroutine_threadsafe(self.broadcast("all", event), loop)

    async def broadcast(self, channel: int | str, event: dict[str, Any]) -> None:
        """Async: deliver event to all subscribers on this channel."""
        async with self._lock:
            sockets = list(self._clients.get(channel, set()))

        if not sockets:
            return

        payload = json.dumps(event, default=str)
        dead: list[WebSocket] = []
        for ws in sockets:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)

        if dead:
            async with self._lock:
                for ws in dead:
                    self._clients[channel].discard(ws)

    # ------------------------------------------------------------------
    # Subscription (from FastAPI WS routes)
    # ------------------------------------------------------------------

    async def connect(
        self,
        channel: int | str,
        ws: WebSocket,
        *,
        send_hello: bool = True,
    ) -> None:
        """Accept a WS connection and hold it until disconnect.

        The coroutine blocks until the client disconnects or an error occurs.
        """
        await ws.accept()
        async with self._lock:
            self._clients[channel].add(ws)

        if send_hello:
            await ws.send_text(
                json.dumps({"type": "connected", "channel": str(channel)})
            )

        logger.debug("WSHub: client connected channel=%s", channel)

        try:
            # Keep alive — read and discard pings / client messages
            while True:
                data = await ws.receive_text()
                # Allow clients to send {"ping": true}
                try:
                    msg = json.loads(data)
                    if msg.get("ping"):
                        await ws.send_text(json.dumps({"pong": True}))
                except Exception:
                    pass
        except WebSocketDisconnect:
            pass
        except Exception as exc:
            logger.debug("WSHub: ws error channel=%s: %s", channel, exc)
        finally:
            async with self._lock:
                self._clients[channel].discard(ws)
            logger.debug("WSHub: client disconnected channel=%s", channel)

    def client_count(self, channel: int | str) -> int:
        return len(self._clients.get(channel, set()))

    def all_channels(self) -> list[str]:
        return [str(k) for k, v in self._clients.items() if v]


# Module-level singleton — imported by both server.py and the EventBus bridge
hub = WSHub()
