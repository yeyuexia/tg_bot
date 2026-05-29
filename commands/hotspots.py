import datetime as dt

from core.auth import auth
from core.runner import run_and_send

COMMAND = "hotspots"
DESCRIPTION = "Recent severity-3 alerts (24h)"


def _work():
    from news_store import init_db, _get_conn
    init_db()
    cutoff = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=24)).isoformat()
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM llm_analyses WHERE trigger='hotspot' AND created_at > ? "
            "ORDER BY created_at DESC",
            (cutoff,),
        ).fetchall()
    return [dict(r) for r in rows]


def _format(rows):
    if not rows:
        return "No hotspot alerts in the last 24h."
    lines = ["Hotspot Alerts (last 24h):\n"]
    for r in rows:
        lines.append(
            f"[{r['created_at']}] {r['category'].upper()} "
            f"risk:{r['political_risk_score']:+.2f}"
        )
        lines.append(f"  {r['briefing'][:100]}\n")
    return "\n".join(lines)


@auth
async def handler(update, context):
    await run_and_send(update, "Checking recent hotspot alerts...", _work, _format, capture=True)
