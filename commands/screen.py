import asyncio

from telegram.constants import ChatAction

from core.auth import auth
from core.runner import _keep_typing
from core.quant import screen_stocks, run_investor_review
from core.utils import capture_stdout, send_long_message

COMMAND = "screen"
DESCRIPTION = "CANSLIM technical stock screener"


@auth
async def handler(update, context):
    await update.message.reply_text("Running stock screener...")
    try:
        loop = asyncio.get_running_loop()

        stop = asyncio.Event()
        typing_task = asyncio.create_task(_keep_typing(update, stop))
        try:
            output, df = await loop.run_in_executor(None, capture_stdout, screen_stocks)
        finally:
            stop.set()
            typing_task.cancel()
            try:
                await typing_task
            except asyncio.CancelledError:
                pass

        if df is not None and not df.empty:
            lines = ["Top Screened Stocks:\n"]
            for _, row in df.head(10).iterrows():
                vcp_pivot = row.get("vcp_pivot")
                pivot_str = f"  Pivot:${vcp_pivot:.2f}" if vcp_pivot else ""
                vcp_tag = " [VCP]" if row.get("in_base") else ""
                lines.append(
                    f"#{row['rank']:2d} {row['ticker']:6s} "
                    f"${row['price']:>8.2f}  "
                    f"RS:{row['rs_score']:>4.0f}  "
                    f"ADR:{row['adr'] * 100:>4.1f}%  "
                    f"Score:{row['composite']:.3f}"
                    f"{vcp_tag}{pivot_str}"
                )
            await send_long_message(update, "\n".join(lines))

            await update.message.reply_text("Analyzing with investor agent...")
            stop2 = asyncio.Event()
            typing_task2 = asyncio.create_task(_keep_typing(update, stop2))
            try:
                review = await loop.run_in_executor(None, run_investor_review, df)
            finally:
                stop2.set()
                typing_task2.cancel()
                try:
                    await typing_task2
                except asyncio.CancelledError:
                    pass

            if review:
                await send_long_message(update, f"Investor Review:\n\n{review}")
            else:
                await update.message.reply_text("(Investor agent unavailable or timed out.)")
        else:
            await update.message.reply_text("No screening results.")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")
