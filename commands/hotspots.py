import asyncio
import datetime as dt

from core.auth import auth
from core.utils import capture_stdout, send_long_message

COMMAND = "hotspots"
DESCRIPTION = "Recent severity-3 alerts (24h)"


@auth
async def handler(update, context):
    await update.message.reply_text("Checking recent hotspot alerts...")
    try:
        from news_store import init_db, _get_conn
        loop = asyncio.get_event_loop()

        def _run():
            init_db()
            cutoff = (dt.datetime.utcnow() - dt.timedelta(hours=24)).isoformat()
            with _get_conn() as conn:
                rows = conn.execute(
                    "SELECT * FROM llm_analyses WHERE trigger='hotspot' AND created_at > ? "
                    "ORDER BY created_at DESC",
                    (cutoff,),
                ).fetchall()
            return [dict(r) for r in rows]

        _, rows = await loop.run_in_executor(None, capture_stdout, _run)
        if not rows:
            await update.message.reply_text("No hotspot alerts in the last 24h.")
            return

        lines = ["Hotspot Alerts (last 24h):\n"]
        for r in rows:
            lines.append(
                f"[{r['created_at']}] {r['category'].upper()} "
                f"risk:{r['political_risk_score']:+.2f}"
            )
            lines.append(f"  {r['briefing'][:100]}\n")
        await send_long_message(update, "\n".join(lines))
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")
