import asyncio

from core.auth import auth
from core.utils import capture_stdout, send_long_message

COMMAND = "macro"
DESCRIPTION = "Macro regime analysis"


@auth
async def handler(update, context):
    await update.message.reply_text("Running macro analysis...")
    try:
        from macro import macro_regime_score, macro_risk_adjustment
        loop = asyncio.get_event_loop()

        def _run():
            result = macro_regime_score()
            adj = macro_risk_adjustment(1.0)
            return result, adj

        _, (result, adj) = await loop.run_in_executor(None, capture_stdout, _run)
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
