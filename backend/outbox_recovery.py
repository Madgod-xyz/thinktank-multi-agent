"""Retry persisted host events while the backend is running."""

from __future__ import annotations

import asyncio
from typing import Callable


async def outbox_recovery_loop(
    flush: Callable[..., bool],
    *,
    interval_seconds: float = 5.0,
    max_events: int = 20,
    timeout: float = 0.35,
) -> None:
    while True:
        try:
            await asyncio.to_thread(flush, max_events=max_events, timeout=timeout)
        except Exception:
            pass
        await asyncio.sleep(interval_seconds)
