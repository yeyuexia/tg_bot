import asyncio
import logging
import time
from datetime import date
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

MEMORY_DIR = Path(__file__).parent.parent / "memory"
MEMORY_DIR.mkdir(exist_ok=True)

# Debounce qmd update/embed so rapid messages don't pile up redundant runs.
# Memory entries written during the cooldown window become searchable on the
# next save after the window expires.
_QMD_DEBOUNCE_S = 60.0
_qmd_lock = asyncio.Lock()
_last_qmd_update: float = 0.0

# Health counters consumed by commands/status.py. "save" here means a memory
# file was successfully written (even if the Haiku summarizer returned NOTHING
# we count the attempt as successful — the summarizer ran, no error occurred).
last_save: float = 0.0
last_save_error: Optional[str] = None
total_saves: int = 0
total_save_skipped: int = 0  # NOTHING-returns; included for completeness


def load_recent_memory(max_days: int = 3) -> str:
    files = sorted(MEMORY_DIR.glob("*.md"), reverse=True)[:max_days]
    if not files:
        return ""
    parts = []
    for f in reversed(files):
        parts.append(f"## {f.stem}\n{f.read_text().strip()}")
    return "\n\n".join(parts)


async def search_memory(query: str) -> str:
    """Cheap keyword (BM25) lookup for the chat hot path.

    Uses `qmd search`, NOT `qmd query`. `query` runs embedding + reranking +
    query-expansion (three local models, ~5-21s cold-start per call) and was
    adding that latency to *every* message. `search` is pure BM25 over the
    SQLite index — no models, ~0.1s — and returns the same hits on our small
    memory corpus. Deeper semantic recall is left to the Claude agent on
    demand (see _SYSTEM_PROMPT_BASE in core/chat.py).
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "qmd", "search", query, "-n", "5", "-c", "tg-bot-memory",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
        result = stdout.decode().strip()
        if not result or "No results" in result:
            return ""
        return result
    except Exception as e:
        logger.warning("qmd search failed: %s", e)
        return ""


async def load_memory(user_msg: str) -> str:
    recent = load_recent_memory()
    searched = await search_memory(user_msg)
    parts = []
    if recent:
        parts.append(f"# Recent Memory\n{recent}")
    if searched:
        parts.append(f"# Relevant Past Context\n{searched}")
    return "\n\n".join(parts)


async def update_qmd_index():
    """Run `qmd update` + `qmd embed`, debounced to at most once per 60s and
    serialized via a module-level lock so concurrent saves never race on the
    qmd SQLite index."""
    global _last_qmd_update
    if time.monotonic() - _last_qmd_update < _QMD_DEBOUNCE_S:
        return
    async with _qmd_lock:
        # Re-check under the lock: a concurrent coroutine may have just run.
        if time.monotonic() - _last_qmd_update < _QMD_DEBOUNCE_S:
            return
        try:
            proc = await asyncio.create_subprocess_exec(
                "qmd", "update",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.communicate(), timeout=30)
            proc = await asyncio.create_subprocess_exec(
                "qmd", "embed",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.communicate(), timeout=60)
            _last_qmd_update = time.monotonic()
        except Exception as e:
            logger.warning("qmd index update failed: %s", e)


async def save_memory(user_msg: str, assistant_response: str):
    global last_save, last_save_error, total_saves, total_save_skipped
    today = date.today().isoformat()
    prompt = (
        "Below is a conversation exchange between a user and an assistant. "
        "Extract ONLY facts worth remembering for future conversations — "
        "decisions made, preferences expressed, tasks completed, issues found, "
        "or important context. "
        "If nothing is worth remembering, respond with exactly: NOTHING\n"
        "Otherwise respond with concise bullet points (no headings, no preamble).\n\n"
        f"User: {user_msg}\n\n"
        f"Assistant: {assistant_response[:2000]}"
    )
    try:
        proc = await asyncio.create_subprocess_exec(
            "claude", "--print", "--max-turns", "1",
            "--model", "haiku",
            "-p", prompt,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
        result = stdout.decode().strip()
        if not result or "NOTHING" in result.upper():
            total_save_skipped += 1
            return
        mem_file = MEMORY_DIR / f"{today}.md"
        existing = mem_file.read_text().strip() if mem_file.exists() else ""
        if existing:
            mem_file.write_text(f"{existing}\n{result}\n")
        else:
            mem_file.write_text(f"{result}\n")
        logger.info("Memory saved to %s", mem_file)
        last_save = time.time()
        last_save_error = None
        total_saves += 1
        await update_qmd_index()
    except Exception as e:
        last_save_error = str(e)
        logger.warning("Memory save failed: %s", e)
