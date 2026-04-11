#!/usr/bin/env python3
"""
Telegram bot for the quantitative investment system.
Provides slash commands, scheduled alerts, and Claude chat.

Usage:
  1. Copy .env.example to .env and fill in your tokens
  2. python3 tg_bot.py
"""
import os
import sys
import io
import asyncio
import logging
from functools import wraps
from contextlib import redirect_stdout

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

load_dotenv()

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_USER_ID = int(os.environ["TELEGRAM_USER_ID"])
STOCK_DIR = os.path.join(os.path.dirname(__file__), "..", "stock")
WORK_DIR = os.path.join(os.path.dirname(__file__), "..")

# Add stock dir to path so we can import its modules
sys.path.insert(0, os.path.abspath(STOCK_DIR))

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def auth(func):
    """Decorator: only allow the configured user."""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id != TELEGRAM_USER_ID:
            return  # silently ignore
        return await func(update, context)
    return wrapper


async def send_long_message(update: Update, text: str):
    """Send a message, splitting into chunks if it exceeds Telegram's 4096 char limit."""
    max_len = 4000  # leave some margin
    if len(text) <= max_len:
        await update.message.reply_text(text)
        return
    # Split on newlines to avoid breaking mid-line
    lines = text.split("\n")
    chunk = ""
    for line in lines:
        if len(chunk) + len(line) + 1 > max_len:
            await update.message.reply_text(chunk)
            chunk = line + "\n"
        else:
            chunk += line + "\n"
    if chunk.strip():
        await update.message.reply_text(chunk)


def capture_stdout(func, *args, **kwargs):
    """Call a function and capture its print output as a string."""
    buf = io.StringIO()
    with redirect_stdout(buf):
        result = func(*args, **kwargs)
    return buf.getvalue(), result


# ── Command handlers (Task 3) will go here ──
# ── Chat handler (Task 4) will go here ──
# ── Scheduler (Task 5) will go here ──


@auth
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "Stock Bot Commands:\n"
        "/portfolio - Current portfolio status\n"
        "/watchdog - Run daily watchdog check\n"
        "/run - Run full investment system\n"
        "/screen - Value+quality stock screener\n"
        "/macro - Macro regime analysis\n"
        "/sentiment - News & social sentiment\n"
        "/help - Show this message\n"
        "\nOr just send any message to chat with Claude."
    )
    await update.message.reply_text(text)


@auth
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Stock assistant ready. Send /help to see commands, or just chat."
    )


def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))

    # Command handlers will be added in Task 3
    # Chat handler will be added in Task 4
    # Scheduler will be set up in Task 5

    logger.info("Bot starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
