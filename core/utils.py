import io
from contextlib import redirect_stdout

from telegram import Update


async def send_long_message(update: Update, text: str) -> list:
    sent = []
    max_len = 4000
    if len(text) <= max_len:
        sent.append(await update.message.reply_text(text))
        return sent
    lines = text.split("\n")
    chunk = ""
    for line in lines:
        if len(chunk) + len(line) + 1 > max_len:
            sent.append(await update.message.reply_text(chunk))
            chunk = line + "\n"
        else:
            chunk += line + "\n"
    if chunk.strip():
        sent.append(await update.message.reply_text(chunk))
    return sent


def capture_stdout(func, *args, **kwargs):
    buf = io.StringIO()
    with redirect_stdout(buf):
        result = func(*args, **kwargs)
    return buf.getvalue(), result
