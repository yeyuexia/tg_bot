from core.auth import auth

COMMAND = "help"
DESCRIPTION = "Show this message"


@auth
async def handler(update, context):
    from commands import discover
    lines = ["Stock Bot Commands:"]
    for cmd, _, desc, *_ in sorted(discover(), key=lambda x: x[0]):
        lines.append(f"/{cmd:<12} - {desc}")
    lines.append("\nOr just send any message to chat with Claude.")
    await update.message.reply_text("\n".join(lines))
