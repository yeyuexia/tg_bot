"""Common pattern for command handlers: send status, run blocking work in a
thread, format the result, send the response, handle errors uniformly."""
import asyncio
from typing import Any, Callable, Optional, TypeVar

from telegram import Update

from core.utils import capture_stdout, send_long_message

T = TypeVar("T")


async def run_and_send(
    update: Update,
    status: str,
    work: Callable[[], T],
    format_fn: Callable[[T], Optional[str]] = lambda x: x,  # type: ignore
    *,
    capture: bool = False,
    error_prefix: str = "Error",
) -> None:
    """Run a blocking command pipeline and deliver the result to the user.

    Args:
        update:       Telegram update.
        status:       Sent immediately, before work begins (e.g. "Running...").
        work:         Sync callable; executed in the default thread executor.
        format_fn:    Maps work()'s return value to user-facing text. May return
                      None or "" to suppress the final send (e.g. when work()
                      itself already short-circuited and produced an empty
                      result). Defaults to identity — pass a str-returning work
                      and it's sent verbatim.
        capture:      If True, run work() inside capture_stdout so any prints
                      go to a buffer instead of stdout. format_fn still
                      receives only work()'s return value.
        error_prefix: Prefix for the error reply, e.g. "Rebalance error".
    """
    await update.message.reply_text(status)
    try:
        loop = asyncio.get_running_loop()
        if capture:
            _, result = await loop.run_in_executor(None, capture_stdout, work)
        else:
            result = await loop.run_in_executor(None, work)
        text = format_fn(result)
        if text:
            await send_long_message(update, text)
    except Exception as e:
        await update.message.reply_text(f"{error_prefix}: {e}")
