from functools import wraps

from telegram import Update
from telegram.ext import ContextTypes

from core.config import TELEGRAM_USER_ID


def auth(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id != TELEGRAM_USER_ID:
            return
        return await func(update, context)
    return wrapper
