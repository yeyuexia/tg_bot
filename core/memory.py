import asyncio
import logging
from datetime import date
from pathlib import Path

logger = logging.getLogger(__name__)

MEMORY_DIR = Path(__file__).parent.parent / "memory"
MEMORY_DIR.mkdir(exist_ok=True)


def load_recent_memory(max_days: int = 3) -> str:
    files = sorted(MEMORY_DIR.glob("*.md"), reverse=True)[:max_days]
    if not files:
        return ""
    parts = []
    for f in reversed(files):
        parts.append(f"## {f.stem}\n{f.read_text().strip()}")
    return "\n\n".join(parts)


async def search_memory(query: str) -> str:
    try:
        proc = await asyncio.create_subprocess_exec(
            "qmd", "query", query, "-n", "5", "-c", "tg-bot-memory",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
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
    except Exception as e:
        logger.warning("qmd index update failed: %s", e)


async def save_memory(user_msg: str, assistant_response: str):
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
            return
        mem_file = MEMORY_DIR / f"{today}.md"
        existing = mem_file.read_text().strip() if mem_file.exists() else ""
        if existing:
            mem_file.write_text(f"{existing}\n{result}\n")
        else:
            mem_file.write_text(f"{result}\n")
        logger.info("Memory saved to %s", mem_file)
        await update_qmd_index()
    except Exception as e:
        logger.warning("Memory save failed: %s", e)
