import logging

from core.auth import auth
from core.quant import sync_state as alpaca_sync
from core.runner import run_and_send
from schedulers.watchdog import _build_portfolio_and_alerts, _build_message

COMMAND = "watchdog"
DESCRIPTION = "Run daily watchdog check"

logger = logging.getLogger(__name__)


def _work():
    snap = alpaca_sync()
    result = _build_portfolio_and_alerts(snap)
    if result is None:
        return "No open positions yet."
    portfolio, all_alerts, pos_by_ticker, macro_result, total_value, total_pnl, total_pnl_pct, cash = result
    if not all_alerts:
        return "All clear. No actionable alerts."
    return _build_message(
        portfolio, all_alerts, pos_by_ticker,
        macro_result, total_value, total_pnl, total_pnl_pct, cash,
    )


@auth
async def handler(update, context):
    await run_and_send(update, "Running watchdog (syncing Alpaca)...", _work)
