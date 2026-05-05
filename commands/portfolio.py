import asyncio

from core.alpaca import sync as alpaca_sync
from core.auth import auth
from core.utils import send_long_message

COMMAND = "portfolio"
DESCRIPTION = "Current portfolio status (live from Alpaca)"


@auth
async def handler(update, context):
    await update.message.reply_text("Syncing from Alpaca...")
    try:
        import config
        loop = asyncio.get_event_loop()
        snap = await loop.run_in_executor(None, alpaca_sync)

        initial = config.INITIAL_CAPITAL
        total_pnl = snap.equity - initial
        total_pnl_pct = total_pnl / initial * 100

        lines = []
        if not snap.positions:
            lines.append("No open positions — fully in cash.")
        else:
            by_tranche = {}
            for p in snap.positions:
                t = p.get("tranche", "unknown")
                by_tranche.setdefault(t, []).append(p)

            for tranche, positions in by_tranche.items():
                label = {
                    "core": "── Core ──────────────────────────────",
                    "aggressive": "── Aggressive ────────────────────────",
                }.get(tranche, f"── {tranche.title()} ─────────────────────────────")
                lines.append(label)
                for p in positions:
                    pl = p["unrealized_pl"]
                    cost = p["market_value"] - pl
                    pl_pct = pl / cost * 100 if cost != 0 else 0
                    cur_price = p["market_value"] / p["shares"] if p["shares"] else 0
                    icon = "+" if pl >= 0 else "-"
                    lines.append(
                        f"  {icon} {p['symbol']:6s}  {p['shares']:.0f}sh"
                        f"  avg ${p['avg_entry']:.2f} → ${cur_price:.2f}"
                    )
                    lines.append(
                        f"           val ${p['market_value']:>9,.2f}"
                        f"  P&L ${pl:>+8,.2f} ({pl_pct:>+.1f}%)"
                    )

        lines.append(f"\nCash:      ${snap.cash:>12,.2f}")
        lines.append(f"Equity:    ${snap.equity:>12,.2f}")
        pnl_icon = "+" if total_pnl >= 0 else "-"
        lines.append(f"Total P&L: {pnl_icon} ${abs(total_pnl):>10,.2f} ({total_pnl_pct:>+.1f}%)")
        lines.append(f"\n[{config.ALPACA_ENV.upper()}]  synced {snap.synced_at[:19]} UTC")
        await send_long_message(update, "\n".join(lines))
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")
