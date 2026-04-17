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
import json
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

# Track Claude session per Telegram user for conversation continuity
_claude_sessions = {}  # user_id -> session_id

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
async def cmd_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show two-tranche portfolio plan: structure, deployment, and per-tranche stats."""
    try:
        from config import (
            INITIAL_CAPITAL, AGGRESSIVE_TRANCHE_PCT, AGGRESSIVE_PARAMS,
            ETF_ALLOCATION_PCT, STOCK_ALLOCATION_PCT,
            STOP_LOSS_PCT, TRAILING_STOP_PCT, REBALANCE_FREQUENCY_DAYS,
        )
        from watchdog import load_portfolio, check_portfolio_status

        core_capital = INITIAL_CAPITAL * (1 - AGGRESSIVE_TRANCHE_PCT)
        agg_capital  = INITIAL_CAPITAL * AGGRESSIVE_TRANCHE_PCT

        portfolio = load_portfolio()
        rows, total_value, total_pnl, total_pnl_pct, cash = check_portfolio_status(portfolio)
        pos_by_ticker = {r["ticker"]: r for r in rows}

        # Split positions by tranche
        core_pos = [p for p in portfolio["positions"] if p.get("tranche", "core") == "core"]
        agg_pos  = [p for p in portfolio["positions"] if p.get("tranche") == "aggressive"]

        core_deployed = sum(pos_by_ticker[p["ticker"]]["value"]
                            for p in core_pos if p["ticker"] in pos_by_ticker)
        agg_deployed  = sum(pos_by_ticker[p["ticker"]]["value"]
                            for p in agg_pos  if p["ticker"] in pos_by_ticker)

        lines = []
        lines.append(f"PORTFOLIO PLAN  ${INITIAL_CAPITAL:,.0f}")
        lines.append(f"Total value: ${total_value:,.0f}  P&L: {total_pnl_pct:+.1f}%")
        lines.append("")

        # ── Core tranche ─────────────────────────────────────────
        core_util = core_deployed / core_capital * 100 if core_capital else 0
        lines.append(f"CORE  ${core_capital:,.0f} (90%)")
        lines.append(f"  Strategy: ETF rotation + stock screen")
        lines.append(f"  Deployed: ${core_deployed:,.0f} ({core_util:.0f}%)")
        lines.append(f"  Buckets:  ETF {ETF_ALLOCATION_PCT*100:.0f}% | Stock {STOCK_ALLOCATION_PCT*100:.0f}%")
        lines.append(f"  Stops:    SL {STOP_LOSS_PCT*100:.0f}% | Trail {TRAILING_STOP_PCT*100:.0f}%")
        lines.append(f"  Rebal:    every {REBALANCE_FREQUENCY_DAYS}d")
        if core_pos:
            lines.append("  Positions:")
            for p in core_pos:
                t = p["ticker"]
                if t in pos_by_ticker:
                    r = pos_by_ticker[t]
                    icon = "+" if r["pnl"] >= 0 else "-"
                    lines.append(f"    {icon} {t:6s}  ${r['value']:>8,.0f}  {r['pnl_pct']:>+.1f}%")
        else:
            lines.append("  (no core positions yet)")

        lines.append("")

        # ── Aggressive tranche ───────────────────────────────────
        agg_util = agg_deployed / agg_capital * 100 if agg_capital else 0
        agg_top_n = AGGRESSIVE_PARAMS["momentum_top_n"]
        agg_rebal = AGGRESSIVE_PARAMS["rebalance_days"]
        agg_sl    = AGGRESSIVE_PARAMS["stop_loss_pct"] * 100
        agg_trail = AGGRESSIVE_PARAMS["trailing_stop_pct"] * 100
        lines.append(f"AGGRESSIVE  ${agg_capital:,.0f} (10%)")
        lines.append(f"  Strategy: Top-{agg_top_n} leveraged ETF momentum")
        lines.append(f"  Deployed: ${agg_deployed:,.0f} ({agg_util:.0f}%)")
        lines.append(f"  ETFs:     TQQQ / SOXL / UPRO / TECL")
        lines.append(f"  Stops:    SL {agg_sl:.0f}% | Trail {agg_trail:.0f}%  (tighter)")
        lines.append(f"  Rebal:    every {agg_rebal}d  (weekly)")
        if agg_pos:
            lines.append("  Positions:")
            for p in agg_pos:
                t = p["ticker"]
                if t in pos_by_ticker:
                    r = pos_by_ticker[t]
                    icon = "+" if r["pnl"] >= 0 else "-"
                    lines.append(f"    {icon} {t:6s}  ${r['value']:>8,.0f}  {r['pnl_pct']:>+.1f}%")
        else:
            lines.append("  (no aggressive positions yet — add via /run)")

        await send_long_message(update, "\n".join(lines))
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")


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
        from watchdog import (
            load_portfolio, check_price_moves, check_volume,
            check_macro_shift, check_news, check_rebalance,
            check_portfolio_status,
        )
        loop = asyncio.get_event_loop()

        def _run():
            portfolio = load_portfolio()
            if not portfolio["positions"]:
                return None, None, None, None, None, None, None
            all_alerts = []
            all_alerts.extend(check_price_moves(portfolio))
            all_alerts.extend(check_volume(portfolio))
            macro_alerts, macro_result = check_macro_shift()
            all_alerts.extend(macro_alerts)
            all_alerts.extend(check_news(portfolio))
            all_alerts.extend(check_rebalance(portfolio))
            rows, total_value, total_pnl, total_pnl_pct, cash = check_portfolio_status(portfolio)
            pos_by_ticker = {r["ticker"]: r for r in rows}
            return portfolio, all_alerts, pos_by_ticker, macro_result, total_value, total_pnl, total_pnl_pct, cash

        _, result = await loop.run_in_executor(None, capture_stdout, _run)
        portfolio, all_alerts, pos_by_ticker, macro_result, total_value, total_pnl, total_pnl_pct, cash = result

        if portfolio is None:
            await update.message.reply_text("No portfolio found.")
            return
        if not all_alerts:
            await update.message.reply_text("All clear. No actionable alerts.")
            return

        text = _build_watchdog_message(
            portfolio, all_alerts, pos_by_ticker,
            macro_result, total_value, total_pnl, total_pnl_pct, cash,
        )
        await send_long_message(update, text)
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
async def cmd_rebalance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Run the rebalancer for one or both tranches. Usage: /rebalance [core|aggressive|both]"""
    args = context.args
    tranche_arg = args[0].lower() if args else "both"
    if tranche_arg not in ("core", "aggressive", "both"):
        await update.message.reply_text("Usage: /rebalance [core|aggressive|both]")
        return

    tranches = ["core", "aggressive"] if tranche_arg == "both" else [tranche_arg]
    await update.message.reply_text(f"Running rebalancer: {', '.join(tranches)}...")

    try:
        from dotenv import load_dotenv
        load_dotenv()
        import rebalancer
        from broker import Broker, BrokerError
        import config

        loop = asyncio.get_event_loop()

        def _run():
            broker = Broker(env=config.ALPACA_ENV)
            lines = []
            for t in tranches:
                result = rebalancer.run(tranche=t, dry_run=False, force=True, broker=broker)
                if result is None:
                    lines.append(f"{t.upper()}: not due yet (use /rebalance {t} to force)")
                    continue
                submitted = len(result.submitted)
                queued    = len(result.queued)
                skipped   = [(i.symbol if i else "?", msg) for i, msg in result.skipped]
                lines.append(f"{t.upper()}: {submitted} submitted, {queued} queued")
                for sym, msg in skipped[:6]:
                    lines.append(f"  ✗ {sym}: {msg}")
                for o in result.submitted:
                    lines.append(f"  ✓ {o.symbol} {o.side} order {o.id[:8]}")
            return "\n".join(lines)

        text = await loop.run_in_executor(None, _run)
        await send_long_message(update, text)
    except Exception as e:
        await update.message.reply_text(f"Rebalance error: {e}")


@auth
async def cmd_forecast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Fetching latest political forecast...")
    try:
        sys.path.insert(0, os.path.abspath(STOCK_DIR))
        from forecast import get_latest_political_score
        from news_store import init_db, get_latest_analysis
        loop = asyncio.get_event_loop()

        def _run():
            init_db()
            return get_latest_analysis()

        _, latest = await loop.run_in_executor(None, capture_stdout, _run)
        if not latest:
            await update.message.reply_text("No forecast yet. Start news_poller.py first.")
            return

        sectors = latest.get("sector_impacts", {})
        sector_lines = "\n".join(
            f"  {t}: {d}" for t, d in list(sectors.items())[:8]
        )
        lines = [
            f"Political Briefing [{latest['trigger'].upper()}]",
            f"Time: {latest['created_at']} UTC",
            f"Risk Score: {latest['political_risk_score']:+.2f}\n",
            latest.get("briefing", ""),
            "",
            f"Sector Impacts:\n{sector_lines}" if sector_lines else "",
        ]
        await send_long_message(update, "\n".join(l for l in lines if l is not None))
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")


@auth
async def cmd_hotspots(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Checking recent hotspot alerts...")
    try:
        import datetime as dt
        from news_store import init_db, _get_conn
        loop = asyncio.get_event_loop()

        def _run():
            init_db()
            cutoff = (dt.datetime.utcnow() - dt.timedelta(hours=24)).isoformat()
            with _get_conn() as conn:
                rows = conn.execute(
                    "SELECT * FROM llm_analyses WHERE trigger='hotspot' AND created_at > ? "
                    "ORDER BY created_at DESC",
                    (cutoff,),
                ).fetchall()
            return [dict(r) for r in rows]

        _, rows = await loop.run_in_executor(None, capture_stdout, _run)
        if not rows:
            await update.message.reply_text("No hotspot alerts in the last 24h.")
            return

        lines = ["Hotspot Alerts (last 24h):\n"]
        for r in rows:
            lines.append(
                f"[{r['created_at']}] {r['category'].upper()} "
                f"risk:{r['political_risk_score']:+.2f}"
            )
            lines.append(f"  {r['briefing'][:100]}\n")
        await send_long_message(update, "\n".join(lines))
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")


@auth
async def handle_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Forward natural language messages to Claude Code CLI."""
    user_msg = update.message.text
    if not user_msg:
        return

    # /new resets the conversation
    if user_msg.strip().lower() == "/new":
        _claude_sessions.pop(update.effective_user.id, None)
        await update.message.reply_text("Started a new conversation.")
        return

    thinking_msg = await update.message.reply_text("Thinking...")
    proc = None
    try:
        user_id = update.effective_user.id
        session_id = _claude_sessions.get(user_id)

        cmd = ["claude", "--print", "--max-turns", "200",
               "--output-format", "json",
               "--model", "sonnet",
               "--dangerously-skip-permissions",
               "--add-dir", os.path.expanduser("~/works"),
               "--append-system-prompt",
               "Be efficient: batch multiple independent tool calls in a single turn. "
               "For example, read multiple files at once, or make multiple edits at once. "
               "Minimize total turns used."]
        if session_id:
            cmd += ["--resume", session_id, "-p", user_msg]
        else:
            cmd += ["-p", user_msg]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=os.path.abspath(WORK_DIR),
        )
        elapsed = 0
        interval = 30
        while True:
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=interval,
                )
                break  # process finished
            except asyncio.TimeoutError:
                elapsed += interval
                if elapsed >= 1800:
                    raise  # real timeout — give up after 30 min
                mins = elapsed // 60
                secs = elapsed % 60
                dots = "." * ((elapsed // interval) % 3 + 1)
                time_str = f"{mins}m{secs:02d}s" if mins else f"{secs}s"
                await thinking_msg.edit_text(f"Still thinking{dots} ({time_str})")

        raw = stdout.decode().strip()
        # Parse JSON output to extract session_id for continuity
        response = raw
        try:
            data = json.loads(raw)
            response = data.get("result", raw)
            sid = data.get("session_id", "")
            if sid:
                _claude_sessions[user_id] = sid
        except (json.JSONDecodeError, AttributeError):
            pass  # fallback to raw text

        if not response:
            response = f"(no output)\nstderr: {stderr.decode().strip()}"
        await thinking_msg.delete()
        await send_long_message(update, response)
    except asyncio.TimeoutError:
        if proc:
            proc.kill()
            await proc.wait()
        await thinking_msg.edit_text("Claude timed out after 30 minutes.")
    except FileNotFoundError:
        await update.message.reply_text(
            "Claude CLI not found. Make sure 'claude' is in PATH."
        )
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

def _build_watchdog_message(portfolio, all_alerts, pos_by_ticker,
                             macro_result, total_value, total_pnl, total_pnl_pct, cash):
    """Build a detailed, human-readable watchdog alert message."""
    import datetime as _dt

    et = pytz.timezone("US/Eastern")
    now_et = _dt.datetime.now(tz=et)
    hour = now_et.hour
    session = (
        "Pre-Market" if hour < 10 else
        "Midday"     if hour < 15 else
        "After-Hours"
    )
    date_str = now_et.strftime("%a %b %-d")

    critical = [a for a in all_alerts if "CRITICAL" in a[0]]
    warnings  = [a for a in all_alerts if "WARNING"  in a[0]]
    infos     = [a for a in all_alerts if "INFO"     in a[0]]

    pnl_sign = "+" if total_pnl >= 0 else ""
    lines = [
        f"Watchdog | {session} | {date_str}",
        "",
        f"Portfolio  ${total_value:>9,.2f}  {pnl_sign}${total_pnl:,.2f} ({total_pnl_pct:+.1f}%)",
        f"Cash       ${cash:>9,.2f}",
    ]

    def _fmt_section(alerts, icon, label):
        if not alerts:
            return
        lines.append(f"\n{icon} {label} ({len(alerts)})")
        lines.append("─" * 32)
        for lvl, ticker, msg in alerts:
            pos = pos_by_ticker.get(ticker)
            lines.append(f"{ticker}")
            lines.append(f"  {msg}")
            # Add position context for stock/ETF tickers
            if pos:
                lines.append(
                    f"  Entry ${pos['entry']:.2f} | Now ${pos['current']:.2f} | "
                    f"P&L {pos['pnl_pct']:+.1f}% (${pos['pnl']:+,.2f})"
                )
            # Add action guidance for critical price/stop alerts
            if "CRITICAL" in lvl:
                if "STOP-LOSS" in msg or "TRAILING STOP" in msg:
                    lines.append("  >> Action: Review position — consider selling to limit loss")
                elif "Moved" in msg:
                    direction = "recovering" if "+" in msg else "falling"
                    lines.append(f"  >> Large move — monitor closely, price {direction}")
                elif "Regime change" in msg:
                    lines.append("  >> Action: Re-run system: python3 run.py")
                elif "SAHM RULE" in msg:
                    lines.append("  >> Recession signal — reduce equity exposure, increase cash/bonds")
                elif "Yield curve" in msg:
                    lines.append("  >> Defensive posture — favour TLT/BIL/SHY over growth")

    _fmt_section(critical, "🔴", "CRITICAL")
    _fmt_section(warnings,  "🟡", "WARNING")
    _fmt_section(infos,     "🟢", "INFO")

    # Macro footer
    lines.append("\n" + "─" * 32)
    if macro_result:
        score = macro_result["score"]
        regime = macro_result["regime"].upper()
        lines.append(f"Macro: {regime}  score {score:+.2f}")

    next_hour = "12:30 PM" if hour < 12 else "5:00 PM" if hour < 17 else "8:10 AM tomorrow"
    lines.append(f"Next check: {next_hour} ET")

    return "\n".join(lines)


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

        macro_alerts, macro_result = check_macro_shift()
        all_alerts.extend(macro_alerts)
        all_alerts.extend(check_news(portfolio))
        all_alerts.extend(check_rebalance(portfolio))

        if not all_alerts:
            return  # no alerts, stay silent

        rows, total_value, total_pnl, total_pnl_pct, cash = check_portfolio_status(portfolio)
        pos_by_ticker = {r["ticker"]: r for r in rows}

        text = _build_watchdog_message(
            portfolio, all_alerts, pos_by_ticker,
            macro_result, total_value, total_pnl, total_pnl_pct, cash,
        )
        await context.bot.send_message(chat_id=TELEGRAM_USER_ID, text=text)

        # Push political forecast briefing if available
        try:
            import datetime as _dt
            from news_store import init_db as _init_db, get_latest_analysis
            from tg_notifier import send_scheduled_briefing
            _init_db()
            latest = get_latest_analysis()
            if latest:
                hour = _dt.datetime.now(tz=pytz.timezone("US/Eastern")).hour
                label = (
                    "PRE-MARKET BRIEFING" if hour < 10 else
                    "MIDDAY BRIEFING"     if hour < 15 else
                    "AFTER-HOURS BRIEFING"
                )
                send_scheduled_briefing(latest, label=label)
        except Exception as _e:
            logger.error(f"Forecast push error: {_e}")
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
        "/plan      - Two-tranche portfolio structure & deployment\n"
        "/rebalance [core|aggressive|both] - Execute rebalancer now\n"
        "/portfolio - Current portfolio status\n"
        "/watchdog - Run daily watchdog check\n"
        "/run - Run full investment system\n"
        "/screen - Value+quality stock screener\n"
        "/macro - Macro regime analysis\n"
        "/sentiment - News & social sentiment\n"
        "/forecast - Latest political briefing\n"
        "/hotspots - Recent severity-3 alerts (24h)\n"
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

    app.add_handler(CommandHandler("plan",       cmd_plan))
    app.add_handler(CommandHandler("rebalance",  cmd_rebalance))
    app.add_handler(CommandHandler("portfolio",  cmd_portfolio))
    app.add_handler(CommandHandler("watchdog", cmd_watchdog))
    app.add_handler(CommandHandler("run", cmd_run))
    app.add_handler(CommandHandler("screen", cmd_screen))
    app.add_handler(CommandHandler("macro", cmd_macro))
    app.add_handler(CommandHandler("sentiment", cmd_sentiment))
    app.add_handler(CommandHandler("forecast", cmd_forecast))
    app.add_handler(CommandHandler("hotspots", cmd_hotspots))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_chat))
    et = pytz.timezone("US/Eastern")
    schedule_times = [
        dt_time(hour=8,  minute=10, tzinfo=et),   # pre-market
        dt_time(hour=12, minute=30, tzinfo=et),   # midday
        dt_time(hour=17, minute=0,  tzinfo=et),   # after-hours
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
