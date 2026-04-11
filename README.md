# Stock Telegram Bot

Telegram bot for the quantitative investment system. Provides slash commands for stock analysis, scheduled watchdog alerts, and natural language chat via Claude.

## Setup

1. Create a bot via [@BotFather](https://t.me/BotFather) on Telegram
2. Get your user ID from [@userinfobot](https://t.me/userinfobot)
3. Copy `.env.example` to `.env` and fill in your values:
   ```
   TELEGRAM_BOT_TOKEN=your-bot-token
   TELEGRAM_USER_ID=your-numeric-id
   ```
4. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

```bash
python3 tg_bot.py
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
| `/help` | List commands |

Any non-command text is forwarded to Claude for natural language chat.

### Scheduled Alerts

The watchdog runs automatically at 8:30 AM ET on weekdays. It only sends a message when there are actionable alerts (stop-loss triggers, big price moves, macro regime shifts).

## Auth

Only the configured `TELEGRAM_USER_ID` can interact with the bot. All other messages are silently ignored.
