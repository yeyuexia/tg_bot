import asyncio
import logging

from core.alpaca import sync as alpaca_sync
from core.auth import auth
from core.utils import send_long_message
from schedulers.watchdog import _build_portfolio_and_alerts, _build_message

COMMAND = "watchdog"
DESCRIPTION = "Run daily watchdog check"

logger = logging.getLogger(__name__)


@auth
async def handler(update, context):
    await update.message.reply_text("Running watchdog (syncing Alpaca)...")
    try:
        loop = asyncio.get_event_loop()
        snap = await loop.run_in_executor(None, alpaca_sync)
        result = await loop.run_in_executor(None, _build_portfolio_and_alerts, snap)

        if result is None:
            await update.message.reply_text("No open positions yet.")
            return

        portfolio, all_alerts, pos_by_ticker, macro_result, total_value, total_pnl, total_pnl_pct, cash = result
        if not all_alerts:
            await update.message.reply_text("All clear. No actionable alerts.")
            return

        text = _build_message(
            portfolio, all_alerts, pos_by_ticker,
            macro_result, total_value, total_pnl, total_pnl_pct, cash,
        )
        await send_long_message(update, text)
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")
