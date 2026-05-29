from core.auth import auth
from core.runner import run_and_send

COMMAND = "sentiment"
DESCRIPTION = "News & social sentiment"


def _work():
    from sentiment import get_market_hotspots
    return get_market_hotspots()


def _format(hotspots):
    lines = [
        f"Market Mood: {hotspots['mood_label']} ({hotspots['market_mood']:+.2f})",
        f"Sources: {hotspots['news_count']} news, {hotspots['reddit_count']} Reddit\n",
    ]
    alerts = hotspots.get("portfolio_alerts", [])
    if alerts:
        lines.append(f"Portfolio Alerts ({len(alerts)}):")
        for a in alerts[:8]:
            icon = "+" if a["sentiment"] == "bullish" else "-" if a["sentiment"] == "bearish" else "~"
            lines.append(f"  {icon} [{a['ticker']}] {a['headline'][:60]}")
        lines.append("")

    buzz = hotspots.get("ticker_buzz")
    if buzz is not None and not buzz.empty:
        lines.append("Top Buzz:")
        for _, row in buzz.head(8).iterrows():
            lines.append(f"  {row['ticker']:6s} {row['mentions']}x  sent:{row['avg_sentiment']:+.2f}")

    return "\n".join(lines)


@auth
async def handler(update, context):
    await run_and_send(update, "Fetching sentiment...", _work, _format, capture=True)
