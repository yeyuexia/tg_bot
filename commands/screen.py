import asyncio

from core.auth import auth
from core.utils import capture_stdout, send_long_message

COMMAND = "screen"
DESCRIPTION = "Value+quality stock screener"


@auth
async def handler(update, context):
    await update.message.reply_text("Running stock screener...")
    try:
        from screener import screen_stocks
        loop = asyncio.get_event_loop()
        output, df = await loop.run_in_executor(None, capture_stdout, screen_stocks)
        if df is not None and not df.empty:
            lines = ["Top Screened Stocks:\n"]
            for _, row in df.head(10).iterrows():
                lines.append(
                    f"#{row['rank']:2d} {row['ticker']:6s} "
                    f"${row['price']:>8.2f}  "
                    f"P/E:{row['pe'] or 0:>5.1f}  "
                    f"Score:{row['composite']:.3f}"
                )
            await send_long_message(update, "\n".join(lines))
        else:
            await update.message.reply_text("No screening results.")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")
