import os
import sys
from pathlib import Path

from dotenv import load_dotenv

_bot_dir = Path(__file__).parent.parent
load_dotenv(_bot_dir / ".env")
load_dotenv(_bot_dir / ".." / "stock" / ".env")

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_USER_ID = int(os.environ["TELEGRAM_USER_ID"])
STOCK_DIR = os.path.abspath(str(_bot_dir / ".." / "stock"))
WORK_DIR = os.path.abspath(str(_bot_dir / ".."))

sys.path.insert(0, STOCK_DIR)
