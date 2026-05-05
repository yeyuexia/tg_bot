from core.auth import auth

COMMAND = "start"
DESCRIPTION = "Start the bot"


@auth
async def handler(update, context):
    await update.message.reply_text(
        "Stock assistant ready. Send /help to see commands, or just chat."
    )
