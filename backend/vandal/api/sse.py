"""A0: SSE streams for run, search, and CEGIS progress.

A Channel is an append-only list of messages that worker threads publish to and any number of
HTTP clients read from. A client can start anywhere (`from` / Last-Event-ID), so a page that
reconnects, or opens late, replays what it missed and then follows live.
"""

from __future__ import annotations

import asyncio
import json
import threading
from collections.abc import AsyncIterator
from typing import Any

POLL_SECONDS = 0.05
KEEPALIVE_SECONDS = 15.0


class Channel:
    def __init__(self) -> None:
        self._messages: list[tuple[str, Any]] = []
        self._lock = threading.Lock()
        self.closed = False

    def publish(self, kind: str, data: Any) -> None:
        with self._lock:
            self._messages.append((kind, data))

    def close(self) -> None:
        self.closed = True

    def since(self, start: int) -> list[tuple[int, str, Any]]:
        with self._lock:
            return [(i, k, d) for i, (k, d) in enumerate(self._messages[start:], start)]

    def __len__(self) -> int:
        return len(self._messages)


def format_sse(message_id: int, kind: str, data: Any) -> str:
    return f"id: {message_id}\nevent: {kind}\ndata: {json.dumps(data, default=str)}\n\n"


async def stream(channel: Channel, start: int = 0, follow: bool = True) -> AsyncIterator[str]:
    """Everything from `start` on, then live messages until the channel closes. With
    `follow=False`, stop once caught up."""
    cursor = start
    idle = 0.0
    while True:
        batch = channel.since(cursor)
        for i, kind, data in batch:
            yield format_sse(i, kind, data)
            cursor = i + 1
        if batch:
            idle = 0.0
            continue
        if channel.closed or not follow:
            return
        await asyncio.sleep(POLL_SECONDS)
        idle += POLL_SECONDS
        if idle >= KEEPALIVE_SECONDS:
            idle = 0.0
            yield ": keepalive\n\n"
