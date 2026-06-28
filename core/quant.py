"""Single adapter to the quant trading system (../stock).

This is the ONLY module in the bot that imports from the `quant` package.
Every command and scheduler calls these thin wrappers instead of reaching into
quant internals or re-implementing its logic, so the two projects stay
decoupled: when quant's module layout changes (e.g. the flat-scripts → `quant/`
package refactor), only this file needs updating — not every command.

Imports are done lazily inside each function so the heavy quant data stack
(pandas, yfinance, alpaca) is not loaded until a command actually runs, keeping
bot startup fast.
"""
import os
import sys
from pathlib import Path

# The quant repo lives next to the bot as ../stock. Put it on sys.path so the
# `quant` package is importable. Idempotent + self-contained (no env needed),
# mirroring core/config.py's STOCK_DIR.
STOCK_DIR = os.path.abspath(str(Path(__file__).resolve().parent.parent / ".." / "stock"))
if STOCK_DIR not in sys.path:
    sys.path.insert(0, STOCK_DIR)


def get_config():
    """The quant config module — constants like INITIAL_CAPITAL, ALPACA_ENV,
    REBALANCE_DAYS, AGGRESSIVE_PARAMS, …"""
    from quant import config
    return config


def _broker():
    from quant.execution.broker import Broker
    from quant import config
    return Broker(env=config.ALPACA_ENV)


def sync_state():
    """Live portfolio snapshot synced from Alpaca (a PortfolioSnapshot)."""
    from quant.execution import orders
    return orders.sync_state(_broker(), alerts=[])


def load_portfolio() -> dict:
    """The cached portfolio dict ({'positions': [...], 'cash': ...})."""
    from quant.execution import orders
    return orders._load_portfolio_cache()


def check_portfolio_status(portfolio):
    """-> (rows, total_value, total_pnl, total_pnl_pct, cash)."""
    from quant.monitor import watchdog
    return watchdog.check_portfolio_status(portfolio)


def run_alert_checks(portfolio):
    """Run quant's full intraday alert suite over `portfolio` and return
    (alerts, macro_result). Centralizes the watchdog check orchestration so the
    bot scheduler calls one function instead of duplicating which checks to run."""
    from quant.monitor import watchdog
    alerts = []
    alerts.extend(watchdog.check_price_moves(portfolio))
    alerts.extend(watchdog.check_volume(portfolio))
    macro_alerts, macro_result = watchdog.check_macro_shift()
    alerts.extend(macro_alerts)
    alerts.extend(watchdog.check_news(portfolio))
    alerts.extend(watchdog.check_rebalance(portfolio))
    return alerts, macro_result


def rebalance(tranche, *, dry_run=False, force=True):
    """Run the rebalancer for a tranche; returns quant's rebalance result
    (with .submitted / .queued / .skipped) or None."""
    from quant.execution import rebalancer
    return rebalancer.run(tranche=tranche, dry_run=dry_run, force=force, broker=_broker())


def screen_stocks():
    """Run the CANSLIM screener; returns its result DataFrame."""
    from quant.signals.screener import screen_stocks as _screen
    return _screen()


def run_investor_review(df):
    """Quant's own LLM investor-agent review of a screen DataFrame (replaces the
    bot's former duplicated copy)."""
    from quant.agent.investor import run_investor_review as _review
    return _review(df)


def daily_report_argv():
    """argv to run quant's full daily report as a subprocess (run with cwd=STOCK_DIR)."""
    return [sys.executable, "-m", "quant.app.daily_report"]
