import asyncio
import datetime as _dt
import logging
import time
from datetime import time as dt_time
from typing import Optional

import pytz

from core.quant import sync_state as alpaca_sync, get_config, run_alert_checks
from core.config import TELEGRAM_USER_ID

et = pytz.timezone("US/Eastern")
SCHEDULE_TIMES = [
    dt_time(hour=8,  minute=10, tzinfo=et),
    dt_time(hour=12, minute=30, tzinfo=et),
    dt_time(hour=17, minute=0,  tzinfo=et),
]
SCHEDULE_DAYS = (0, 1, 2, 3, 4)

logger = logging.getLogger(__name__)

# Health counters consumed by commands/status.py.
last_run: float = 0.0
last_alert_count: int = 0
last_error: Optional[str] = None


def _build_portfolio_and_alerts(snap):
    cfg = get_config()

    portfolio = {
        "positions": [
            {
                "ticker": p["symbol"],
                "shares": p["shares"],
                "entry_price": p["avg_entry"],
                "tranche": p.get("tranche", "core"),
            }
            for p in snap.positions
        ],
        "cash": snap.cash,
        "initial_capital": cfg.INITIAL_CAPITAL,
    }

    if not portfolio["positions"]:
        return None

    all_alerts, macro_result = run_alert_checks(portfolio)

    pos_by_ticker = {
        p["symbol"]: {
            "ticker": p["symbol"],
            "shares": p["shares"],
            "current": p["market_value"] / p["shares"] if p["shares"] else 0,
            "value": p["market_value"],
            "pnl": p["unrealized_pl"],
            "pnl_pct": p["unrealized_pl"] / (p["market_value"] - p["unrealized_pl"]) * 100
                       if (p["market_value"] - p["unrealized_pl"]) else 0,
            "entry_price": p["avg_entry"],
        }
        for p in snap.positions
    }
    total_value   = snap.equity
    total_pnl     = snap.equity - cfg.INITIAL_CAPITAL
    total_pnl_pct = total_pnl / cfg.INITIAL_CAPITAL * 100
    cash          = snap.cash
    return portfolio, all_alerts, pos_by_ticker, macro_result, total_value, total_pnl, total_pnl_pct, cash


def _build_message(portfolio, all_alerts, pos_by_ticker,
                   macro_result, total_value, total_pnl, total_pnl_pct, cash):
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
            if pos:
                lines.append(
                    f"  Entry ${pos['entry_price']:.2f} | Now ${pos['current']:.2f} | "
                    f"P&L {pos['pnl_pct']:+.1f}% (${pos['pnl']:+,.2f})"
                )
            if "CRITICAL" in lvl:
                if "STOP-LOSS" in msg or "TRAILING STOP" in msg:
                    lines.append("  >> Action: Review position — consider selling to limit loss")
                elif "Moved" in msg:
                    direction = "recovering" if "+" in msg else "falling"
                    lines.append(f"  >> Large move — monitor closely, price {direction}")
                elif "Regime change" in msg:
                    lines.append("  >> Action: Re-run system: python3 -m quant.app.daily_report")
                elif "SAHM RULE" in msg:
                    lines.append("  >> Recession signal — reduce equity exposure, increase cash/bonds")
                elif "Yield curve" in msg:
                    lines.append("  >> Defensive posture — favour TLT/BIL/SHY over growth")

    _fmt_section(critical, "🔴", "CRITICAL")
    _fmt_section(warnings,  "🟡", "WARNING")
    _fmt_section(infos,     "🟢", "INFO")

    lines.append("\n" + "─" * 32)
    if macro_result:
        score = macro_result["score"]
        regime = macro_result["regime"].upper()
        lines.append(f"Macro: {regime}  score {score:+.2f}")

    next_hour = "12:30 PM" if hour < 12 else "5:00 PM" if hour < 17 else "8:10 AM tomorrow"
    lines.append(f"Next check: {next_hour} ET")

    return "\n".join(lines)


async def scheduled_handler(context):
    global last_run, last_alert_count, last_error
    try:
        loop = asyncio.get_running_loop()
        snap = await loop.run_in_executor(None, alpaca_sync)
        result = await loop.run_in_executor(None, _build_portfolio_and_alerts, snap)

        if result is None:
            last_run = time.time()
            last_alert_count = 0
            last_error = None
            return

        portfolio, all_alerts, pos_by_ticker, macro_result, total_value, total_pnl, total_pnl_pct, cash = result
        last_run = time.time()
        last_alert_count = len(all_alerts)
        last_error = None
        if not all_alerts:
            return

        text = _build_message(
            portfolio, all_alerts, pos_by_ticker,
            macro_result, total_value, total_pnl, total_pnl_pct, cash,
        )
        await context.bot.send_message(chat_id=TELEGRAM_USER_ID, text=text)

        try:
            from news_store import init_db as _init_db, get_latest_analysis
            from tg_notifier import send_scheduled_briefing
            _init_db()
            latest = get_latest_analysis()
            if latest:
                hour = _dt.datetime.now(tz=et).hour
                label = (
                    "PRE-MARKET BRIEFING" if hour < 10 else
                    "MIDDAY BRIEFING"     if hour < 15 else
                    "AFTER-HOURS BRIEFING"
                )
                send_scheduled_briefing(latest, label=label)
        except Exception as _e:
            logger.error("Forecast push error: %s", _e)
    except Exception as e:
        last_error = str(e)
        logger.error("Scheduled watchdog error: %s", e)
        await context.bot.send_message(
            chat_id=TELEGRAM_USER_ID,
            text=f"Watchdog error: {e}",
        )
