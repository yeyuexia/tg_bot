import asyncio

from core.alpaca import sync as alpaca_sync
from core.auth import auth
from core.scheduler import build_watchdog_message
from core.utils import send_long_message

COMMAND = "watchdog"
DESCRIPTION = "Run daily watchdog check"


@auth
async def handler(update, context):
    await update.message.reply_text("Running watchdog (syncing Alpaca)...")
    try:
        from watchdog import (
            check_price_moves, check_volume,
            check_macro_shift, check_news, check_rebalance,
        )
        import config
        loop = asyncio.get_event_loop()

        def _run():
            snap = alpaca_sync()
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
                "initial_capital": config.INITIAL_CAPITAL,
            }

            if not portfolio["positions"]:
                return None, None, None, None, None, None, None, None

            all_alerts = []
            all_alerts.extend(check_price_moves(portfolio))
            all_alerts.extend(check_volume(portfolio))
            macro_alerts, macro_result = check_macro_shift()
            all_alerts.extend(macro_alerts)
            all_alerts.extend(check_news(portfolio))
            all_alerts.extend(check_rebalance(portfolio))

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
            total_pnl     = snap.equity - config.INITIAL_CAPITAL
            total_pnl_pct = total_pnl / config.INITIAL_CAPITAL * 100
            cash          = snap.cash
            return portfolio, all_alerts, pos_by_ticker, macro_result, total_value, total_pnl, total_pnl_pct, cash

        result = await loop.run_in_executor(None, _run)
        portfolio, all_alerts, pos_by_ticker, macro_result, total_value, total_pnl, total_pnl_pct, cash = result

        if portfolio is None:
            await update.message.reply_text("No open positions yet.")
            return
        if not all_alerts:
            await update.message.reply_text("All clear. No actionable alerts.")
            return

        text = build_watchdog_message(
            portfolio, all_alerts, pos_by_ticker,
            macro_result, total_value, total_pnl, total_pnl_pct, cash,
        )
        await send_long_message(update, text)
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")
