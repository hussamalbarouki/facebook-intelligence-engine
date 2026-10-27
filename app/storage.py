"""SQLite persistence: jobs, configuration, encrypted session secrets, and audit events."""
from __future__ import annotations
import json
from contextlib import contextmanager
import sqlite3
import threading
import time
import uuid

DEFAULT_SETTINGS = {
    'default_comments_limit': 100,
    'default_reactors_limit': 100,
    'max_comments_limit': 1000,
    'max_reactors_limit': 1000,
    'retention_days': 7,
    'request_cooldown_seconds': 5,
    'jobs_enabled': True,
}

class JobStore:
    def __init__(self, db_path: str):
        self.db_path = str(db_path)
        self.lock = threading.RLock()
        with self.conn() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript('''
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, url TEXT NOT NULL,
                    comment_limit INTEGER NOT NULL, reactor_limit INTEGER NOT NULL,
                    status TEXT NOT NULL, created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
                    result TEXT, error TEXT, client_job_id TEXT UNIQUE
                );
                CREATE INDEX IF NOT EXISTS jobs_status_idx ON jobs(status,created_at);
                CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS secrets (key TEXT PRIMARY KEY, encrypted_value BLOB NOT NULL, updated_at INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, created_at INTEGER NOT NULL, action TEXT NOT NULL, details TEXT NOT NULL);
            ''')
            # Recover jobs when only container restarted. A task interrupted mid-fetch is retried.
            db.execute("UPDATE jobs SET status='queued' WHERE status='running'")
            db.commit()

    @contextmanager
    def conn(self):
        con = sqlite3.connect(self.db_path, timeout=30)
        con.row_factory = sqlite3.Row
        try:
            con.execute('PRAGMA busy_timeout=30000')
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    def log(self, action, details=''):
        with self.conn() as db:
            db.execute('INSERT INTO events(created_at,action,details) VALUES(?,?,?)', (int(time.time()), action, str(details)[:180]))
            db.commit()

    def settings(self):
        with self.conn() as db:
            rows = db.execute('SELECT key,value FROM settings').fetchall()
        return {**DEFAULT_SETTINGS, **{r['key']: json.loads(r['value']) for r in rows}}

    def update_settings(self, patch: dict):
        with self.lock, self.conn() as db:
            for k,v in patch.items():
                db.execute('INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (k,json.dumps(v)))
            db.commit()
        self.log('settings_updated', ','.join(sorted(patch)))
        return self.settings()

    def store_secret(self, name: str, encrypted: bytes):
        with self.lock, self.conn() as db:
            db.execute('INSERT INTO secrets(key,encrypted_value,updated_at) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET encrypted_value=excluded.encrypted_value,updated_at=excluded.updated_at', (name, encrypted, int(time.time())))
            db.commit()
        self.log('cookies_updated', 'Session credentials updated')

    def get_secret(self, name: str):
        with self.conn() as db:
            row = db.execute('SELECT encrypted_value,updated_at FROM secrets WHERE key=?', (name,)).fetchone()
        return dict(row) if row else None

    def delete_secret(self, name: str):
        with self.lock, self.conn() as db:
            db.execute('DELETE FROM secrets WHERE key=?', (name,))
            db.commit()
        self.log('cookies_removed', 'Session credentials removed')

    def create(self, url, comment_limit, reactor_limit, client_job_id=None):
        with self.lock, self.conn() as db:
            if client_job_id:
                prior = db.execute('SELECT id,url,comment_limit,reactor_limit FROM jobs WHERE client_job_id=?', (client_job_id,)).fetchone()
                if prior:
                    if (prior['url'], prior['comment_limit'], prior['reactor_limit']) != (url,comment_limit,reactor_limit):
                        raise ValueError('client_job_id already belongs to a different request')
                    return prior['id'], True
            active = db.execute("SELECT COUNT(*) n FROM jobs WHERE status IN ('queued','running')").fetchone()['n']
            if active >= 20:
                raise OverflowError('Queue capacity reached')
            jid, now = str(uuid.uuid4()), int(time.time())
            db.execute('INSERT INTO jobs(id,url,comment_limit,reactor_limit,status,created_at,updated_at,client_job_id) VALUES(?,?,?,?,?,?,?,?)',
                       (jid,url,comment_limit,reactor_limit,'queued',now,now,client_job_id))
            db.commit()
        self.log('job_created', jid)
        return jid, False

    def get(self, jid, include_result=False):
        with self.conn() as db:
            row = db.execute('SELECT * FROM jobs WHERE id=?', (jid,)).fetchone()
        if not row:
            return None
        fields = ('id','url','comment_limit','reactor_limit','status','created_at','updated_at','attempts','error','client_job_id')
        value = {k: row[k] for k in fields}
        if include_result and row['result']:
            value['result'] = json.loads(row['result'])
        return value

    def list(self, status=None, limit=30, offset=0):
        where, args = ("WHERE status=?", [status]) if status else ('', [])
        with self.conn() as db:
            total = db.execute(f'SELECT COUNT(*) n FROM jobs {where}', args).fetchone()['n']
            data = db.execute(f'SELECT id,url,status,created_at,updated_at,attempts,error,client_job_id FROM jobs {where} ORDER BY created_at DESC,id DESC LIMIT ? OFFSET ?', args+[limit,offset]).fetchall()
        return {'total':total,'items':[dict(x) for x in data],'limit':limit,'offset':offset}

    def claim(self):
        with self.lock, self.conn() as db:
            row = db.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY created_at,id LIMIT 1").fetchone()
            if not row:
                return None
            db.execute("UPDATE jobs SET status='running',updated_at=?,attempts=attempts+1 WHERE id=?", (int(time.time()),row['id']))
            db.commit()
        return dict(row)

    def finish(self, jid, result=None, error=None):
        state = 'failed' if error else 'completed'
        with self.lock, self.conn() as db:
            # A canceled job must stay canceled, even if an in-flight request completes.
            db.execute("UPDATE jobs SET status=?,result=?,error=?,updated_at=? WHERE id=? AND status='running'", (
                state, json.dumps(result, ensure_ascii=False, default=str) if result is not None else None,
                str(error)[:220] if error else None,int(time.time()),jid))
            db.commit()
        self.log('job_'+state, jid)

    def retry(self, jid):
        with self.lock, self.conn() as db:
            result = db.execute("UPDATE jobs SET status='queued',error=NULL,result=NULL,updated_at=? WHERE id=? AND status='failed'", (int(time.time()),jid))
            db.commit()
        if result.rowcount: self.log('job_retried',jid)
        return bool(result.rowcount)

    def cancel(self, jid):
        with self.lock, self.conn() as db:
            result = db.execute("UPDATE jobs SET status='canceled',updated_at=? WHERE id=? AND status IN ('queued','running')", (int(time.time()),jid))
            db.commit()
        if result.rowcount: self.log('job_canceled',jid)
        return bool(result.rowcount)

    def metrics(self):
        with self.conn() as db:
            rows = db.execute('SELECT status,COUNT(*) n FROM jobs GROUP BY status').fetchall()
            recent = db.execute('SELECT COUNT(*) n FROM jobs WHERE created_at>=?', (int(time.time())-86400,)).fetchone()['n']
        return {'jobs_by_status':{r['status']:r['n'] for r in rows},'jobs_created_24h':recent}

    def events(self, limit=50):
        with self.conn() as db:
            rows = db.execute('SELECT id,created_at,action,details FROM events ORDER BY id DESC LIMIT ?', (limit,)).fetchall()
        return [dict(r) for r in rows]

    def cleanup(self, max_age_days=7):
        with self.lock, self.conn() as db:
            result = db.execute("DELETE FROM jobs WHERE status IN ('completed','failed','canceled') AND updated_at<?", (int(time.time())-max_age_days*86400,))
            db.execute('DELETE FROM events WHERE created_at<?', (int(time.time())-30*86400,))
            db.commit()
        return result.rowcount