from core.auth import auth
from core.runner import run_and_send

COMMAND = "forecast"
DESCRIPTION = "Latest political briefing"


def _work():
    from core.quant import news_latest_analysis
    return news_latest_analysis()


def _format(latest):
    if not latest:
        return "No forecast yet. Start news_poller.py first."
    sectors = latest.get("sector_impacts", {})
    sector_lines = "\n".join(f"  {t}: {d}" for t, d in list(sectors.items())[:8])
    lines = [
        f"Political Briefing [{latest['trigger'].upper()}]",
        f"Time: {latest['created_at']} UTC",
        f"Risk Score: {latest['political_risk_score']:+.2f}\n",
        latest.get("briefing", ""),
    ]
    if sector_lines:
        lines.append("")
        lines.append(f"Sector Impacts:\n{sector_lines}")
    return "\n".join(lines)


@auth
async def handler(update, context):
    await run_and_send(update, "Fetching latest political forecast...", _work, _format, capture=True)
