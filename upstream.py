"""Short-lived upstream state shared by this supervisor's stdio sessions."""
from contextlib import closing
from datetime import timezone
from email.utils import parsedate_to_datetime
from hashlib import sha256
import math
import os
import sqlite3
import time


def retry_seconds(header):
    try:
        delay = int(header)
    except (TypeError, ValueError, OverflowError):
        try:
            deadline = parsedate_to_datetime(header)
            if deadline.tzinfo is None:
                deadline = deadline.replace(tzinfo=timezone.utc)
            delay = math.ceil(deadline.timestamp() - time.time())
        except (TypeError, ValueError, OverflowError, IndexError, AttributeError):
            delay = 60
    return max(1, min(delay, 86400))


class UpstreamState:
    def __init__(self, token):
        self.path = os.environ.get('QBT_UPSTREAM_STATE')
        self.key = sha256(token.encode()).hexdigest()

    def _connection(self):
        db = sqlite3.connect(self.path, timeout=2)
        try:
            db.execute('CREATE TABLE IF NOT EXISTS deadlines '
                       '(token TEXT, purpose TEXT, until REAL, PRIMARY KEY(token, purpose))')
        except Exception:
            db.close()
            raise
        return db

    def remaining(self, purpose):
        if not self.path:
            return 0
        with closing(self._connection()) as db:
            row = db.execute('SELECT until FROM deadlines WHERE token=? AND purpose=?',
                             (self.key, purpose)).fetchone()
        return max(0, math.ceil(row[0] - time.time())) if row else 0

    def remember(self, purpose, seconds):
        if self.path:
            with closing(self._connection()) as db, db:
                db.execute('INSERT INTO deadlines VALUES (?, ?, ?) ON CONFLICT(token, purpose) '
                           'DO UPDATE SET until=max(until, excluded.until)',
                           (self.key, purpose, time.time() + seconds))

    def check_rate_limit(self):
        delay = self.remaining('throttled')
        if delay:
            raise ValueError(f'QuickBooks Time rate limited (429). Retry after {delay} seconds.')
