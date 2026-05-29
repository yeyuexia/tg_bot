from core.auth import auth
from core.runner import run_and_send

COMMAND = "macro"
DESCRIPTION = "Macro regime analysis"


def _work():
    from macro import macro_regime_score, macro_risk_adjustment
    return macro_regime_score(), macro_risk_adjustment(1.0)


def _format(data):
    result, adj = data
    lines = [
        f"Macro Regime: {result['regime'].upper()}",
        f"Score: {result['score']:+.3f}",
        f"Risk Adjustment: {adj*100:.0f}%\n",
    ]
    for name, ind in result["indicators"].items():
        lines.append(f"  {name:18s} {ind['signal']:+.1f}  {ind['label']}")
    return "\n".join(lines)


@auth
async def handler(update, context):
    await run_and_send(update, "Running macro analysis...", _work, _format, capture=True)
