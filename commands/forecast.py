import asyncio

from core.auth import auth
from core.utils import capture_stdout, send_long_message

COMMAND = "forecast"
DESCRIPTION = "Latest political briefing"


@auth
async def handler(update, context):
    await update.message.reply_text("Fetching latest political forecast...")
    try:
        from news_store import init_db, get_latest_analysis
        loop = asyncio.get_event_loop()

        def _run():
            init_db()
            return get_latest_analysis()

        _, latest = await loop.run_in_executor(None, capture_stdout, _run)
        if not latest:
            await update.message.reply_text("No forecast yet. Start news_poller.py first.")
            return

        sectors = latest.get("sector_impacts", {})
        sector_lines = "\n".join(
            f"  {t}: {d}" for t, d in list(sectors.items())[:8]
        )
        lines = [
            f"Political Briefing [{latest['trigger'].upper()}]",
            f"Time: {latest['created_at']} UTC",
            f"Risk Score: {latest['political_risk_score']:+.2f}\n",
            latest.get("briefing", ""),
            "",
            f"Sector Impacts:\n{sector_lines}" if sector_lines else "",
        ]
        await send_long_message(update, "\n".join(l for l in lines if l is not None))
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")
