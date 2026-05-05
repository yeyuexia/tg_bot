# Telegram Bot

Telegram bot for the quantitative investment system. Provides slash commands for stock analysis, scheduled watchdog alerts, and natural language chat via Claude.

## Setup

1. Create a bot via [@BotFather](https://t.me/BotFather) on Telegram
2. Get your user ID from [@userinfobot](https://t.me/userinfobot)
3. Copy `.env.example` to `.env` and fill in your values:
   ```
   TELEGRAM_BOT_TOKEN=your-bot-token
   TELEGRAM_USER_ID=your-numeric-id
   ALPACA_API_KEY=your-alpaca-key
   ALPACA_API_SECRET=your-alpaca-secret
   ```
4. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

```bash
python3 bot.py
```

### Commands

| Command | Description |
|---------|-------------|
| `/portfolio` | Current portfolio status and P&L |
| `/watchdog` | Run daily watchdog check |
| `/run` | Run full investment system |
| `/screen` | Value + quality stock screener |
| `/macro` | Macro regime analysis |
| `/sentiment` | News & social sentiment |
| `/rebalance` | Rebalance portfolio |
| `/forecast` | Market forecast |
| `/hotspots` | Market hotspots |
| `/plan` | Investment plan |
| `/help` | List commands |

Any non-command text is forwarded to Claude for natural language chat.

### Scheduled Alerts

The watchdog runs automatically at **8:10 AM**, **12:30 PM**, and **5:00 PM ET** on weekdays. It only sends a message when there are actionable alerts (stop-loss triggers, big price moves, macro regime shifts).

## Architecture

```
bot.py                  ← entry point; auto-discovers and registers commands
core/
  config.py             ← env loading, paths
  auth.py               ← @auth decorator (whitelist by TELEGRAM_USER_ID)
  utils.py              ← send_long_message, capture_stdout
  memory.py             ← save/load/search conversation memory
  alpaca.py             ← Alpaca broker sync
  chat.py               ← Claude natural language chat
commands/
  __init__.py           ← plugin auto-discovery (discover())
  watchdog.py           ← watchdog command + scheduled job (self-contained)
  portfolio.py          ← portfolio status
  run.py                ← full system run
  screen.py             ← stock screener
  macro.py              ← macro regime
  sentiment.py          ← sentiment analysis
  rebalance.py          ← rebalancing
  forecast.py           ← forecasting
  hotspots.py           ← market hotspots
  plan.py               ← investment plan
  help.py               ← help listing
  start.py              ← /start welcome
```

### Adding a New Command

Create `commands/mynewcmd.py` with:

```python
COMMAND = "mynewcmd"
DESCRIPTION = "What it does"

async def handler(update, context):
    await update.message.reply_text("Hello!")
```

No changes to `bot.py` needed — commands are auto-discovered on startup.

### Adding a Scheduled Job

Add these to your command plugin:

```python
from datetime import time as dt_time
import pytz

et = pytz.timezone("US/Eastern")
SCHEDULE_TIMES = [dt_time(hour=9, minute=0, tzinfo=et)]
SCHEDULE_DAYS = (0, 1, 2, 3, 4)  # Mon–Fri

async def scheduled_handler(bot):
    ...
```

`bot.py` will register the job automatically.

## Auth

Only the configured `TELEGRAM_USER_ID` can interact with the bot. All other messages are silently ignored.
