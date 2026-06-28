from core.auth import auth
from core.runner import run_and_send

COMMAND = "rebalance"
DESCRIPTION = "Execute rebalancer [core|aggressive|both]"


@auth
async def handler(update, context):
    """Usage: /rebalance [core|aggressive|both]"""
    args = context.args
    tranche_arg = args[0].lower() if args else "both"
    if tranche_arg not in ("core", "aggressive", "both"):
        await update.message.reply_text("Usage: /rebalance [core|aggressive|both]")
        return
    tranches = ["core", "aggressive"] if tranche_arg == "both" else [tranche_arg]

    def _work():
        from core.quant import rebalance

        lines = []
        for t in tranches:
            result = rebalance(t)
            if result is None:
                lines.append(f"{t.upper()}: no orders generated")
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

    await run_and_send(
        update,
        f"Running rebalancer: {', '.join(tranches)}...",
        _work,
        error_prefix="Rebalance error",
    )
