import asyncio
import os
import sys

from core.auth import auth
from core.config import STOCK_DIR
from core.utils import send_long_message

COMMAND = "run"
DESCRIPTION = "Run full investment system"


@auth
async def handler(update, context):
    await update.message.reply_text("Running full investment system... (this takes a minute)")
    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, os.path.join(STOCK_DIR, "run.py"),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=STOCK_DIR,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
        output = stdout.decode()
        if proc.returncode != 0:
            output += f"\n\nSTDERR:\n{stderr.decode()}"
        await send_long_message(update, output or "Run completed (no output).")
    except asyncio.TimeoutError:
        await update.message.reply_text("Timed out after 5 minutes.")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")
