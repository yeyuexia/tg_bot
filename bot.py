#!/usr/bin/env python3
"""
Telegram bot for the quantitative investment system.
Commands are auto-discovered from the commands/ package.

Usage:
  1. Copy .env.example to .env and fill in your tokens
  2. python3 bot.py
"""
import logging

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters

from core.config import TELEGRAM_BOT_TOKEN
from core.chat import handle_chat, handle_photo
from commands import discover
from schedulers import discover as discover_schedulers

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    for command, handler_fn, _, _plugin in discover():
        app.add_handler(CommandHandler(command, handler_fn))

    for name, scheduled_fn, schedule_times, schedule_days in discover_schedulers():
        for t in schedule_times:
            app.job_queue.run_daily(scheduled_fn, time=t, days=schedule_days)
        logger.info("Scheduled %s at %s", name, [str(t) for t in schedule_times])

    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_chat))

    logger.info("Bot starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
