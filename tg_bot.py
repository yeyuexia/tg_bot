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
from datetime import time as dt_time
from functools import wraps
from contextlib import redirect_stdout

import pytz

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


@auth
async def cmd_portfolio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Checking portfolio...")
    try:
        from watchdog import load_portfolio, check_portfolio_status
        portfolio = load_portfolio()
        if not portfolio["positions"]:
            await update.message.reply_text("No portfolio found.")
            return

        rows, total_value, total_pnl, total_pnl_pct, cash = check_portfolio_status(portfolio)
        lines = []
        for r in rows:
            icon = "+" if r["pnl"] >= 0 else "-"
            lines.append(
                f"{icon} {r['ticker']:6s} {r['shares']:3d}x ${r['current']:>8.2f} = ${r['value']:>9.2f} "
                f"P&L: ${r['pnl']:>+8.2f} ({r['pnl_pct']:>+.1f}%)"
            )
        lines.append(f"\nCash:      ${cash:>10,.2f}")
        lines.append(f"Portfolio: ${total_value:>10,.2f}")
        icon = "+" if total_pnl >= 0 else "-"
        lines.append(f"Total P&L: {icon} ${abs(total_pnl):>10,.2f} ({total_pnl_pct:>+.1f}%)")
        await send_long_message(update, "\n".join(lines))
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")


@auth
async def cmd_watchdog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Running watchdog...")
    try:
        from watchdog import run_watchdog
        loop = asyncio.get_event_loop()
        output, _ = await loop.run_in_executor(None, capture_stdout, run_watchdog, False)
        await send_long_message(update, output or "Watchdog completed (no output).")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")


@auth
async def cmd_run(update: Update, context: ContextTypes.DEFAULT_TYPE):
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


@auth
async def cmd_screen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Running stock screener...")
    try:
        from screener import screen_stocks
        loop = asyncio.get_event_loop()
        output, df = await loop.run_in_executor(None, capture_stdout, screen_stocks)
        if df is not None and not df.empty:
            lines = ["Top Screened Stocks:\n"]
            for _, row in df.head(10).iterrows():
                lines.append(
                    f"#{row['rank']:2d} {row['ticker']:6s} "
                    f"${row['price']:>8.2f}  "
                    f"P/E:{row['pe'] or 0:>5.1f}  "
                    f"Score:{row['composite']:.3f}"
                )
            await send_long_message(update, "\n".join(lines))
        else:
            await update.message.reply_text("No screening results.")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")


@auth
async def cmd_macro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Running macro analysis...")
    try:
        from macro import macro_regime_score, macro_risk_adjustment
        loop = asyncio.get_event_loop()

        def _run_macro():
            result = macro_regime_score()
            adj = macro_risk_adjustment(1.0)
            return result, adj

        output, (result, adj) = await loop.run_in_executor(None, capture_stdout, _run_macro)

        score = result["score"]
        regime = result["regime"]
        lines = [
            f"Macro Regime: {regime.upper()}",
            f"Score: {score:+.3f}",
            f"Risk Adjustment: {adj*100:.0f}%\n",
        ]
        for name, ind in result["indicators"].items():
            lines.append(f"  {name:18s} {ind['signal']:+.1f}  {ind['label']}")
        await send_long_message(update, "\n".join(lines))
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")


@auth
async def cmd_sentiment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Fetching sentiment...")
    try:
        from sentiment import get_market_hotspots
        loop = asyncio.get_event_loop()

        def _run():
            return get_market_hotspots()

        _, hotspots = await loop.run_in_executor(None, capture_stdout, _run)

        mood = hotspots["market_mood"]
        label = hotspots["mood_label"]
        lines = [
            f"Market Mood: {label} ({mood:+.2f})",
            f"Sources: {hotspots['news_count']} news, {hotspots['reddit_count']} Reddit\n",
        ]

        alerts = hotspots.get("portfolio_alerts", [])
        if alerts:
            lines.append(f"Portfolio Alerts ({len(alerts)}):")
            for a in alerts[:8]:
                icon = "+" if a["sentiment"] == "bullish" else "-" if a["sentiment"] == "bearish" else "~"
                lines.append(f"  {icon} [{a['ticker']}] {a['headline'][:60]}")
            lines.append("")

        buzz = hotspots.get("ticker_buzz")
        if buzz is not None and not buzz.empty:
            lines.append("Top Buzz:")
            for _, row in buzz.head(8).iterrows():
                lines.append(f"  {row['ticker']:6s} {row['mentions']}x  sent:{row['avg_sentiment']:+.2f}")

        await send_long_message(update, "\n".join(lines))
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")


@auth
async def handle_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Forward natural language messages to Claude Code CLI."""
    user_msg = update.message.text
    if not user_msg:
        return

    await update.message.reply_text("Thinking...")
    try:
        proc = await asyncio.create_subprocess_exec(
            "claude", "--print", "-p", user_msg,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=os.path.abspath(WORK_DIR),
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
        response = stdout.decode().strip()
        if not response:
            response = f"(no output)\nstderr: {stderr.decode().strip()}"
        await send_long_message(update, response)
    except asyncio.TimeoutError:
        await update.message.reply_text("Claude timed out after 2 minutes.")
    except FileNotFoundError:
        await update.message.reply_text(
            "Claude CLI not found. Make sure 'claude' is in PATH."
        )
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

async def scheduled_watchdog(context: ContextTypes.DEFAULT_TYPE):
    """Run watchdog and send alerts to the user. Called by JobQueue on schedule."""
    try:
        from watchdog import (
            load_portfolio, check_price_moves, check_volume,
            check_macro_shift, check_news, check_rebalance,
            check_portfolio_status,
        )

        portfolio = load_portfolio()
        if not portfolio["positions"]:
            return  # no portfolio, nothing to alert on

        all_alerts = []
        all_alerts.extend(check_price_moves(portfolio))
        all_alerts.extend(check_volume(portfolio))

        macro_alerts, _ = check_macro_shift()
        all_alerts.extend(macro_alerts)
        all_alerts.extend(check_news(portfolio))
        all_alerts.extend(check_rebalance(portfolio))

        if not all_alerts:
            return  # no alerts, stay silent

        # Build summary
        _, total_value, total_pnl, total_pnl_pct, cash = check_portfolio_status(portfolio)

        lines = [
            "Daily Watchdog Alert\n",
            f"Portfolio: ${total_value:>,.2f} ({total_pnl_pct:>+.1f}%)\n",
        ]

        critical = [a for a in all_alerts if "CRITICAL" in a[0]]
        warnings = [a for a in all_alerts if "WARNING" in a[0]]
        infos = [a for a in all_alerts if "INFO" in a[0]]

        for a in critical + warnings + infos:
            lines.append(f"{a[0]} [{a[1]}] {a[2]}")

        if critical:
            lines.append(f"\n{len(critical)} CRITICAL alert(s) - ACTION REQUIRED!")

        await context.bot.send_message(
            chat_id=TELEGRAM_USER_ID,
            text="\n".join(lines),
        )
    except Exception as e:
        logger.error(f"Scheduled watchdog error: {e}")
        await context.bot.send_message(
            chat_id=TELEGRAM_USER_ID,
            text=f"Watchdog error: {e}",
        )


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

    app.add_handler(CommandHandler("portfolio", cmd_portfolio))
    app.add_handler(CommandHandler("watchdog", cmd_watchdog))
    app.add_handler(CommandHandler("run", cmd_run))
    app.add_handler(CommandHandler("screen", cmd_screen))
    app.add_handler(CommandHandler("macro", cmd_macro))
    app.add_handler(CommandHandler("sentiment", cmd_sentiment))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_chat))
    # Schedule watchdog at 8:30 AM ET, Monday-Friday
    et = pytz.timezone("US/Eastern")
    app.job_queue.run_daily(
        scheduled_watchdog,
        time=dt_time(hour=8, minute=30, tzinfo=et),
        days=(0, 1, 2, 3, 4),  # Monday=0 through Friday=4
        name="daily_watchdog",
    )
    logger.info("Scheduled daily watchdog at 8:30 AM ET, Mon-Fri")

    logger.info("Bot starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
