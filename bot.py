#!/usr/bin/env python3
"""
Telegram bot for the quantitative investment system.
Commands are auto-discovered from the commands/ package.

Usage:
  1. Copy .env.example to .env and fill in your tokens
  2. python3 bot.py
"""
import logging
from datetime import time as dt_time

import pytz
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters

from core.config import TELEGRAM_BOT_TOKEN
from core.chat import handle_chat, handle_photo
from core.scheduler import scheduled_watchdog
from commands import discover

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    for command, handler_fn, _ in discover():
        app.add_handler(CommandHandler(command, handler_fn))

    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_chat))

    et = pytz.timezone("US/Eastern")
    schedule_times = [
        dt_time(hour=8,  minute=10, tzinfo=et),
        dt_time(hour=12, minute=30, tzinfo=et),
        dt_time(hour=17, minute=0,  tzinfo=et),
    ]
    for t in schedule_times:
        app.job_queue.run_daily(
            scheduled_watchdog,
            time=t,
            days=(0, 1, 2, 3, 4),
        )
    logger.info("Scheduled watchdog at 8:10, 12:30, 17:00 ET Mon-Fri")
    logger.info("Bot starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
