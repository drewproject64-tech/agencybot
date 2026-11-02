"""Run once with bot stopped: DATABASE_URL=... python migrate_to_neon.py /path/leads.db"""
import argparse
import os
import sqlite3
from pathlib import Path
from database import connect, initialize


def migrate(path):
    if not os.environ.get('DATABASE_URL', '').strip():
        raise RuntimeError('Set DATABASE_URL to the Neon connection string first')
    if not Path(path).is_file():
        raise ValueError('Existing SQLite file not found')
    source = sqlite3.connect(f'{Path(path).resolve().as_uri()}?mode=ro', uri=True)
    target = connect(path)
    try:
        initialize(target)
        # Require an empty destination: avoid merging unrelated lead IDs or opt-outs.
        target.execute('LOCK TABLE leads, users IN ACCESS EXCLUSIVE MODE')
        if target.execute('SELECT COUNT(*) FROM leads').fetchone()[0] or target.execute('SELECT COUNT(*) FROM users').fetchone()[0]:
            raise RuntimeError('Destination must be empty; migration cancelled without importing records')
        leads = source.execute('SELECT id,user_id,name,username,created_at,status FROM leads').fetchall()
        for row in leads:
            target.execute('INSERT INTO leads(id,user_id,name,username,created_at,status) VALUES (?,?,?,?,?,?)', row)
        has_users = source.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='users'").fetchone()
        if has_users:
            for row in source.execute('SELECT user_id,name,username,first_seen,last_seen,subscribed,blocked FROM users'):
                target.execute('INSERT INTO users(user_id,name,username,first_seen,last_seen,subscribed,blocked) VALUES (?,?,?,?,?,?,?)', row)
        target.execute("SELECT setval(pg_get_serial_sequence('leads','id'), COALESCE(MAX(id),1), COUNT(*) > 0) FROM leads")
        target.commit()
        initialize(target)  # Fill users present only in historical leads.
        count = target.execute('SELECT COUNT(*) FROM users').fetchone()[0]
        print(f'Migration complete: {len(leads)} leads, {count} users. Source unchanged.')
    finally:
        source.close()
        target.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sqlite_path')
    migrate(parser.parse_args().sqlite_path)
