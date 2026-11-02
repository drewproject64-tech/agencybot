"""SQLite fallback and Neon/PostgreSQL connections."""
import os
import sqlite3


class PostgresConnection:
    def __init__(self, url):
        import psycopg
        self.raw = psycopg.connect(url, connect_timeout=15, sslmode='require')

    def execute(self, sql, params=()):
        return self.raw.execute(sql.replace('?', '%s'), params)

    def commit(self):
        self.raw.commit()

    def close(self):
        self.raw.close()


def connect(path):
    url = os.environ.get('DATABASE_URL', '').strip()
    if url:
        if not url.startswith(('postgres://', 'postgresql://')):
            raise ValueError('DATABASE_URL must be a PostgreSQL connection URL')
        return PostgresConnection(url)
    return sqlite3.connect(path)


def initialize(conn):
    pg = isinstance(conn, PostgresConnection)
    key = 'BIGSERIAL PRIMARY KEY' if pg else 'INTEGER PRIMARY KEY AUTOINCREMENT'
    conn.execute(f'''CREATE TABLE IF NOT EXISTS leads (
        id {key}, user_id BIGINT NOT NULL, name TEXT NOT NULL,
        username TEXT, created_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'new')''')
    conn.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id BIGINT PRIMARY KEY, name TEXT NOT NULL, username TEXT,
        first_seen TEXT NOT NULL, last_seen TEXT NOT NULL,
        subscribed INTEGER NOT NULL DEFAULT 1, blocked INTEGER NOT NULL DEFAULT 0)''')
    conn.execute('''INSERT INTO users (user_id,name,username,first_seen,last_seen)
        SELECT user_id, MAX(name), MAX(username), MIN(created_at), MAX(created_at)
        FROM leads WHERE user_id > 0 GROUP BY user_id
        ON CONFLICT(user_id) DO NOTHING''')
    conn.commit()
