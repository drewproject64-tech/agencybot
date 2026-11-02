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

## User database and admin panel

All private /start users are saved by Telegram ID with name, username, first-seen and last-seen timestamps. Returning private-message/callback users are also recorded. Existing leads are imported automatically without deleting or duplicating leads. Historical starters who were never stored cannot be recovered from Telegram; they must interact again.

Set ADMIN_USER_IDS to comma-separated numeric Telegram user IDs. Only these individual users can open /admin or use admin buttons, replies or /leads. A positive ADMIN_CHAT_ID is also treated as an admin user for compatibility with existing private-admin deployments. A negative group ADMIN_CHAT_ID only receives requests; group members are not automatically admins. Do not set ADMIN_CHAT_ID to a non-admin person's private ID.

/admin shows total saved users, subscriptions, blocked/unreachable users, eligible broadcast recipients and recent users. Choose Broadcast to users or Message one user, send text/media, review the preview, then confirm Send. Direct messages require a saved user ID. Broadcasts exclude admins and opted-out/blocked users, handle Telegram rate limits, and report success/failure counts. Only one delivery runs at a time. No messages are sent merely by opening the panel.

Users can use /stop to opt out of broadcasts and /subscribe to opt in. Starting again does not undo an opt-out. Service replies/direct messages remain available.

Keep DB_PATH on persistent storage (for example /var/data/leads.db on a mounted disk) and retain the existing database to recover existing leads. Back it up before deploying. Drafts and delivery jobs are in memory: an interrupted broadcast does not resume automatically. Albums are sent as individual messages. Deploy one polling instance per token.

Run checks: python -m unittest -v


## Neon PostgreSQL

1. Create/select a Neon project and copy its PostgreSQL connection string from Connect.
2. Set DATABASE_URL as a secret environment variable on your bot host. Keep the SSL and channel_binding options supplied by Neon. Never commit credentials.
3. Install requirements and redeploy. Tables are created automatically. A configured but unavailable database causes an error; the bot never silently falls back to SQLite.
4. With DATABASE_URL set, users, lead statuses and admin statistics use Neon. DB_PATH is used only when DATABASE_URL is empty. No local persistent disk is required for Neon records.

To preserve existing records: stop the bot, back up the existing SQLite file, then run `python migrate_to_neon.py /path/to/leads.db` in an environment with DATABASE_URL set. Use a fresh empty Neon database; this migration refuses a nonempty destination. It preserves IDs, lead statuses, subscriptions and blocked flags, and leaves the source unchanged. After success, restart the bot with DATABASE_URL. Do not switch back to the old SQLite file after collecting new Neon records.

The database connection needs to be configured on the host; repository changes alone do not connect your Neon account. Message drafts and broadcast progress are still in memory.
