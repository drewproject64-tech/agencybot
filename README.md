# Emmanuel Digitals & CO Agency Bot

Telegram client-intake and lead-management bot for **Emmanuel Digitals & CO**.

## Features

- Branded home menu
- About Agency and Services sections
- Portfolio button
- Direct client request intake
- Forwards original client messages to the admin chat
- Captures client name, username, Telegram ID and timestamp
- SQLite lead storage
- Lead statuses: New, Contacted, In Progress, Closed
- Admin reply-to-client workflow
- Admin-only `/leads` command
- `/help` and `/cancel`
- Environment-based configuration

## Environment

```env
BOT_TOKEN=your_telegram_bot_token
ADMIN_CHAT_ID=your_admin_chat_id
PORTFOLIO_URL=https://t.me/Emmanuel_DigitalsCO
CONTACT_URL=https://t.me/EmmanuelDigitals_CO
DB_PATH=leads.db
```

Never commit real secrets to GitHub.

## Run

```bash
pip install -r requirements.txt
python bot.py
```

For production hosting, use persistent storage for `leads.db`.
