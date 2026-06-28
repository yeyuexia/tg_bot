# Telegram Bot

Telegram bot for the quantitative investment system. Provides slash commands for stock analysis, scheduled watchdog alerts, and natural language chat via Claude.

## Setup

1. Create a bot via [@BotFather](https://t.me/BotFather) on Telegram
2. Get your user ID from [@userinfobot](https://t.me/userinfobot)
3. Copy `.env.example` to `.env` and fill in your Telegram values:
   ```
   TELEGRAM_BOT_TOKEN=your-bot-token
   TELEGRAM_USER_ID=your-numeric-id
   ```
   Alpaca credentials are read from the sibling `../stock/.env` (loaded automatically by `core/config.py`), so put `ALPACA_API_KEY` / `ALPACA_API_SECRET` there.
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
| `/services` | List local services running on this machine |
| `/status` | Bot health snapshot (uptime, last call, qmd, log size) |
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
bot.py                  ← entry point; auto-discovers and registers commands + schedulers
core/
  config.py             ← env loading, paths
  auth.py               ← @auth decorator (whitelist by TELEGRAM_USER_ID)
  utils.py              ← send_long_message, capture_stdout
  memory.py             ← save/load/search conversation memory
  quant.py              ← SINGLE adapter to the ../stock `quant` package (see below)
  chat.py               ← Claude natural language chat (/new, /continue)
  session_store.py      ← SQLite persistence for Claude sessions + msg→response cache
commands/
  __init__.py           ← plugin auto-discovery (discover())
  watchdog.py           ← /watchdog manual trigger (shares helpers with schedulers/watchdog.py)
  portfolio.py          ← portfolio status
  run.py                ← full system run
  screen.py             ← stock screener + investor agent review
  services.py           ← list local services listening on TCP ports
  status.py             ← bot health snapshot (counters + on-disk metadata)
  macro.py              ← macro regime
  sentiment.py          ← sentiment analysis
  rebalance.py          ← rebalancing
  forecast.py           ← forecasting
  hotspots.py           ← market hotspots
  plan.py               ← investment plan
  help.py               ← help listing
  start.py              ← /start welcome
schedulers/
  __init__.py           ← plugin auto-discovery (discover())
  watchdog.py           ← scheduled watchdog job (8:10 AM / 12:30 PM / 5:00 PM ET, Mon–Fri)
```

### Quant integration (decoupled)

The bot is **decoupled** from the quant trading system (`../stock`): `core/quant.py`
is the **only** module that imports the `quant` package. Every command and scheduler
calls thin wrappers there (`sync_state`, `load_portfolio`, `check_portfolio_status`,
`run_alert_checks`, `rebalance`, `screen_stocks`, `run_investor_review`,
`get_config`, `daily_report_argv`) instead of reaching into quant internals or
re-implementing its logic. So when the quant side refactors its module layout
(e.g. the flat-scripts → `quant/` package move), **only `core/quant.py` changes** —
no command touches `quant.*` directly. Imports inside the adapter are lazy, so the
heavy quant/data stack only loads when a command actually runs.

(Note: `/forecast` and `/hotspots` couple to a *separate* news-forecast project via
`news_store`/`tg_notifier`, not to quant — out of scope for this boundary.)

### Chat session commands

In addition to the slash commands listed above, the chat handler supports:

| Command | Description |
|---------|-------------|
| `/new` | Start a fresh Claude session (clear prior conversation) |
| `/continue [message]` | Resume the last Claude session, optionally with a follow-up |

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

Create `schedulers/myjob.py` with:

```python
from datetime import time as dt_time
import pytz

et = pytz.timezone("US/Eastern")
SCHEDULE_TIMES = [dt_time(hour=9, minute=0, tzinfo=et)]
SCHEDULE_DAYS = (0, 1, 2, 3, 4)  # Mon–Fri

async def scheduled_handler(context):
    await context.bot.send_message(chat_id=..., text="...")
```

`bot.py` will register the job automatically on startup.

## Auth

Only the configured `TELEGRAM_USER_ID` can interact with the bot. All other messages are silently ignored.

## Memory

Each chat exchange is summarized by Claude Haiku and appended to `memory/YYYY-MM-DD.md`. Before the next message, the bot prepends two blocks to the system prompt: the raw last 3 days of memory, plus the top-5 semantic-search hits across the full history.

The semantic-search half uses the `qmd` CLI and is **optional** — without it, the bot logs `qmd search failed: ... No such file or directory: 'qmd'` and falls back to raw recency only. To enable it:

1. Install `qmd` and make sure its install dir is on the launchd plist's `PATH`. Example for a Bun install:
   ```xml
   <key>PATH</key>
   <string>/Users/zl/.bun/bin:/Users/zl/.local/bin:/usr/local/bin:/usr/bin:/bin</string>
   ```
2. Register the memory dir as a collection and build the index:
   ```bash
   qmd collection add /Users/zl/works/tg-bot/memory --name tg-bot-memory --mask "**/*.md"
   qmd update && qmd embed
   ```

## Running as a service (macOS / launchd)

The bot runs in production under launchd, configured at `~/Library/LaunchAgents/com.zl.tg-bot.plist`:

- `KeepAlive=true` — launchd restarts the bot automatically if it crashes or is killed
- `RunAtLoad=true` — starts on login
- `StandardOutPath` / `StandardErrorPath` are set to `/dev/null` so Python's `TimedRotatingFileHandler` is the sole writer to `bot.log` (otherwise launchd would double-write and bypass rotation)

Common operations:

```bash
# Apply plist changes (also restarts the bot)
launchctl unload ~/Library/LaunchAgents/com.zl.tg-bot.plist
launchctl load   ~/Library/LaunchAgents/com.zl.tg-bot.plist

# Restart after a code change
launchctl kickstart -k gui/$(id -u)/com.zl.tg-bot
```

## Logging

- All logs go to `bot.log` via a `TimedRotatingFileHandler` (daily rotation at midnight, 7 backups → 1-week retention).
- Rotated backups are named `bot.log.YYYY-MM-DD`.
- `httpx` is silenced to `WARNING` because it logs every request at INFO with the full URL — which includes the bot token in the path (`/bot<TOKEN>/getUpdates`).
