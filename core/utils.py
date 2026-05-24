import io
from contextlib import redirect_stdout

from telegram import Update

_MAX_LEN = 4000


async def send_long_message(update: Update, text: str) -> list:
    sent = []
    if not text:
        return sent
    if len(text) <= _MAX_LEN:
        sent.append(await update.message.reply_text(text))
        return sent

    chunk = ""
    for line in text.split("\n"):
        # Hard-split lines that exceed the cap on their own.
        while len(line) > _MAX_LEN:
            if chunk:
                sent.append(await update.message.reply_text(chunk))
                chunk = ""
            sent.append(await update.message.reply_text(line[:_MAX_LEN]))
            line = line[_MAX_LEN:]

        if len(chunk) + len(line) + 1 > _MAX_LEN:
            if chunk:
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
