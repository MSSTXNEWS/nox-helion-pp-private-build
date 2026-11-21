#!/usr/bin/env python3
"""NOX improvement/event journal. SQLite append-only receipts, no untrusted code execution.

Run: python journal.py init --db ./nox_journal.sqlite
     python journal.py record --db ... --task-id 1V14-01 --event-id event1 --kind ERROR --signature backend404 --source ...
     python journal.py repeated --db ... --minimum 2
"""
from __future__ import annotations
import argparse, json, sqlite3, datetime, re, hashlib
from pathlib import Path

def safe(s,limit=1000):
    s=str(s or '')[:limit]
    # Redact common credentials. Never record request bodies, prompts, cookies, auth headers.
    s=re.sub(r'(?i)(authorization|bearer|api[_-]?key|token|password|secret)\s*[:=]\s*[^\s,;&]+',r'\1=[REDACTED]',s)
    return s

def connect(path):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(path,timeout=20)
    db.execute('PRAGMA journal_mode=WAL');db.execute('PRAGMA busy_timeout=20000')
    db.executescript('''CREATE TABLE IF NOT EXISTS events (
        event_id TEXT PRIMARY KEY, task_id TEXT NOT NULL, kind TEXT NOT NULL,
        signature TEXT, source_sha TEXT, source_url TEXT,
        observed_utc TEXT NOT NULL, message TEXT NOT NULL,
        independently_verified INTEGER NOT NULL DEFAULT 0,
        owner_receipt TEXT, verifier_receipt TEXT);
    CREATE INDEX IF NOT EXISTS idx_events_task ON events(task_id,observed_utc);
    CREATE INDEX IF NOT EXISTS idx_events_sig ON events(signature,kind);
    CREATE TABLE IF NOT EXISTS improvements(
        improvement_id TEXT PRIMARY KEY, task_id TEXT NOT NULL, problem TEXT NOT NULL,
        plan TEXT NOT NULL, state TEXT NOT NULL, opened_utc TEXT NOT NULL,
        source_ref TEXT NOT NULL, rollback_ref TEXT, verifier_ref TEXT);
    ''')
    db.commit();return db

def record(db,task_id,event_id,kind,signature='',source_sha='',source_url='',message='',verified=False,owner_receipt='',verifier_receipt=''):
    kind=kind.upper()
    if kind not in {'OBSERVED','RUNNING','ERROR','BLOCKED','PATCH_PREPARED','PATCH_TESTED','PATCH_INTEGRATED','ACCEPTED','STOP','RETRY','RECOVERED','NO_GAIN'}:
        raise ValueError('invalid kind')
    if kind=='ACCEPTED' and not (verified and owner_receipt and verifier_receipt and source_sha):
        raise ValueError('ACCEPTED requires verified=yes, owner+independent receipts and pinned SHA')
    args=(safe(event_id,180),safe(task_id,100),kind,safe(signature,220),safe(source_sha,128),safe(source_url,300),
          datetime.datetime.now(datetime.timezone.utc).isoformat(),safe(message,1000),int(bool(verified)),safe(owner_receipt,260),safe(verifier_receipt,260))
    db.execute('INSERT OR IGNORE INTO events VALUES (?,?,?,?,?,?,?,?,?,?,?)',args)
    db.commit()

def repeated(db,minimum=2):
    rows=db.execute('SELECT task_id,signature,COUNT(*) AS n,MAX(observed_utc) AS last_seen FROM events WHERE kind="ERROR" AND signature != "" GROUP BY task_id,signature HAVING COUNT(*)>=? ORDER BY n DESC,last_seen DESC',(minimum,)).fetchall()
    return [{'task_id':a,'signature':b,'count':n,'last_seen_utc':d,'status':'PROPOSE_FIX_NOT_AUTOMATIC_CODE_CHANGE'} for a,b,n,d in rows]

def summary(db):
    rows=db.execute('SELECT kind,COUNT(*) FROM events GROUP BY kind').fetchall()
    return {'events_by_kind':dict(rows), 'accepted_in_this_journal':dict(rows).get('ACCEPTED',0), 'note':'Not a canonical native acceptance ledger; receipts require independent cross-check.'}

def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=['init','record','repeated','summary'])
    p.add_argument('--db',default='nox_improvement.sqlite');p.add_argument('--task-id',default='');p.add_argument('--event-id',default='')
    p.add_argument('--kind',default='OBSERVED');p.add_argument('--signature',default='');p.add_argument('--source-sha',default='')
    p.add_argument('--source-url',default='');p.add_argument('--message',default='');p.add_argument('--minimum',type=int,default=2)
    p.add_argument('--verified',action='store_true');p.add_argument('--owner-receipt',default='');p.add_argument('--verifier-receipt',default='')
    a=p.parse_args();db=connect(a.db)
    if a.command=='record':
        if not a.task_id or not a.event_id:p.error('--task-id and --event-id required')
        record(db,a.task_id,a.event_id,a.kind,a.signature,a.source_sha,a.source_url,a.message,a.verified,a.owner_receipt,a.verifier_receipt)
    result= summary(db) if a.command=='summary' else repeated(db,a.minimum) if a.command=='repeated' else {'status':a.command.upper()+'_OK'}
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
