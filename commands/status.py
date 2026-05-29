"""/status — bot health snapshot.

Aggregates lightweight counters from core.chat, core.memory, and
schedulers.watchdog plus on-disk metadata (log size, session DB, memory file
count, qmd reachability) and renders a single Telegram message.
"""
import datetime as dt
import os
import shutil
import time
from pathlib import Path

import psutil

from core import chat as chat_mod
from core import memory as memory_mod
from core.auth import auth
from core.utils import send_long_message
from schedulers import watchdog as watchdog_mod

COMMAND = "status"
DESCRIPTION = "Bot health snapshot"

_BOT_DIR = Path(__file__).parent.parent
_LOG_PATH = _BOT_DIR / "bot.log"
_MEMORY_DIR = _BOT_DIR / "memory"
_SESSIONS_DB = _BOT_DIR / "sessions.db"


def _fmt_ago(ts: float) -> str:
    if not ts:
        return "never"
    elapsed = time.time() - ts
    if elapsed < 60:
        return f"{int(elapsed)}s ago"
    if elapsed < 3600:
        return f"{int(elapsed / 60)}m ago"
    if elapsed < 86400:
        return f"{int(elapsed / 3600)}h ago"
    return f"{int(elapsed / 86400)}d ago"


def _fmt_bytes(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


def _fmt_uptime(seconds: float) -> str:
    s = int(seconds)
    d, s = divmod(s, 86400)
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    parts = []
    if d:
        parts.append(f"{d}d")
    if h or d:
        parts.append(f"{h}h")
    parts.append(f"{m}m")
    return " ".join(parts)


def _gather() -> dict:
    proc = psutil.Process(os.getpid())
    started = dt.datetime.fromtimestamp(proc.create_time())

    log_size = _LOG_PATH.stat().st_size if _LOG_PATH.exists() else 0
    log_backups = sorted(_BOT_DIR.glob("bot.log.20*"))
    mem_files = list(_MEMORY_DIR.glob("*.md")) if _MEMORY_DIR.exists() else []
    sessions_db_size = _SESSIONS_DB.stat().st_size if _SESSIONS_DB.exists() else 0

    return {
        "pid": proc.pid,
        "started": started,
        "uptime_s": time.time() - proc.create_time(),
        "rss_mb": proc.memory_info().rss / 1024 / 1024,
        "log_size": log_size,
        "log_backups": len(log_backups),
        "mem_file_count": len(mem_files),
        "sessions_db_size": sessions_db_size,
        "qmd_available": shutil.which("qmd") is not None,
        "last_chat_call": chat_mod.last_claude_call,
        "total_chat_calls": chat_mod.total_claude_calls,
        "last_chat_error": chat_mod.last_claude_error,
        "last_memory_save": memory_mod.last_save,
        "total_memory_saves": memory_mod.total_saves,
        "total_memory_skipped": memory_mod.total_save_skipped,
        "last_memory_error": memory_mod.last_save_error,
        "last_watchdog_run": watchdog_mod.last_run,
        "last_watchdog_alerts": watchdog_mod.last_alert_count,
        "last_watchdog_error": watchdog_mod.last_error,
    }


def _format(d: dict) -> str:
    lines = [
        "Bot Status",
        "",
        f"PID            {d['pid']}",
        f"Started        {d['started'].strftime('%Y-%m-%d %H:%M:%S')}",
        f"Uptime         {_fmt_uptime(d['uptime_s'])}",
        f"Memory (RSS)   {d['rss_mb']:.1f} MB",
        "",
        f"Chat calls     {d['total_chat_calls']} total, last {_fmt_ago(d['last_chat_call'])}",
    ]
    if d["last_chat_error"]:
        lines.append(f"  last error   {d['last_chat_error'][:80]}")
    lines.append(
        f"Memory saves   {d['total_memory_saves']} kept, "
        f"{d['total_memory_skipped']} skipped (NOTHING), last {_fmt_ago(d['last_memory_save'])}"
    )
    if d["last_memory_error"]:
        lines.append(f"  last error   {d['last_memory_error'][:80]}")
    lines.append(
        f"Watchdog       last {_fmt_ago(d['last_watchdog_run'])}"
        f" ({d['last_watchdog_alerts']} alerts)"
    )
    if d["last_watchdog_error"]:
        lines.append(f"  last error   {d['last_watchdog_error'][:80]}")
    lines += [
        "",
        f"qmd CLI        {'available' if d['qmd_available'] else 'MISSING'}",
        f"Memory files   {d['mem_file_count']} markdown files",
        f"Sessions DB    {_fmt_bytes(d['sessions_db_size'])}",
        f"Log            {_fmt_bytes(d['log_size'])} current, {d['log_backups']} backups",
    ]
    return "\n".join(lines)


@auth
async def handler(update, context):
    info = _gather()
    await send_long_message(update, _format(info))
