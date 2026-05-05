import asyncio

from core.auth import auth
from core.utils import capture_stdout, send_long_message

COMMAND = "sentiment"
DESCRIPTION = "News & social sentiment"


@auth
async def handler(update, context):
    await update.message.reply_text("Fetching sentiment...")
    try:
        from sentiment import get_market_hotspots
        loop = asyncio.get_event_loop()
        _, hotspots = await loop.run_in_executor(None, capture_stdout, get_market_hotspots)
        mood = hotspots["market_mood"]
        label = hotspots["mood_label"]
        lines = [
            f"Market Mood: {label} ({mood:+.2f})",
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

        await send_long_message(update, "\n".join(lines))
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")
