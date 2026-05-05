import asyncio

from core.auth import auth
from core.utils import send_long_message

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
    await update.message.reply_text(f"Running rebalancer: {', '.join(tranches)}...")

    try:
        from dotenv import load_dotenv
        load_dotenv()
        import rebalancer
        from broker import Broker
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
