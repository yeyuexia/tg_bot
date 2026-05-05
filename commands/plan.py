from core.auth import auth
from core.utils import send_long_message

COMMAND = "plan"
DESCRIPTION = "Two-tranche portfolio structure & deployment"


@auth
async def handler(update, context):
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
