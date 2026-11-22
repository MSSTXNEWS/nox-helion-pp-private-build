"""Scope-local supervised LoRA lifecycle. No hooks read or persist ordinary chat.

Each submit is a curator's explicit selection of one operation. The only
external input is a supplied local base checkpoint. Use suggest-only routing:
a promoted model changes proposals, never grants tool permissions.
"""
import argparse
from collections import Counter
import contextlib
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
import uuid

import numpy as np

from . import corpus, features, neural, train
from .kernel import Kernel

SCHEMA = """
CREATE TABLE IF NOT EXISTS state(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS versions(
 id TEXT PRIMARY KEY, filename TEXT NOT NULL UNIQUE, parent TEXT,
 status TEXT NOT NULL, report TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events(
 seq INTEGER PRIMARY KEY, token TEXT UNIQUE NOT NULL, digest TEXT NOT NULL,
 receipt TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS examples(
 fingerprint TEXT PRIMARY KEY, label TEXT NOT NULL, grp TEXT NOT NULL,
 row_json TEXT NOT NULL, trial TEXT);
CREATE INDEX IF NOT EXISTS waiting ON examples(trial,grp);
CREATE TABLE IF NOT EXISTS used_groups(grp TEXT PRIMARY KEY, trial TEXT NOT NULL);
"""


def _compact(x):
    return json.dumps(x, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def _sha(b):
    return hashlib.sha256(b).hexdigest()


def _folder(root, scope):
    if not isinstance(scope,str) or not scope.strip() or scope.strip()=='default' or len(scope)>200:
        raise ValueError('Нужна отдельная непустая область длиной до 200 символов')
    return Path(root)/_sha(scope.encode('utf-8'))


def _active(db, folder):
    row = db.execute("SELECT id,filename FROM versions WHERE id=(SELECT value FROM state WHERE key='active')").fetchone()
    if not row:
        raise ValueError('Отсутствует активная версия')
    p = folder/row[1]
    if not p.is_file():
        raise ValueError('Файл активной версии утрачен')
    return row[0],p


def active_checkpoint(root, scope, base_checkpoint):
    """Read the committed per-scope pointer; do not create a scope on chat."""
    folder = _folder(root, scope)
    path = folder/'events.sqlite3'
    if not path.exists():
        return Path(base_checkpoint)
    with contextlib.closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True,timeout=30)) as db:
        if not _initialized(db):
            return Path(base_checkpoint)
        return _active(db,folder)[1]


def _initialized(db):
    # The db file can appear before the first writer commits its private base.
    has_state=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='state'").fetchone()
    return bool(has_state and db.execute("SELECT 1 FROM state WHERE key='active'").fetchone())


def _flushdir(path):
    if os.name=='posix':
        fd = os.open(path,os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def _install_base(db, folder, source, catalog, encoder):
    existing = db.execute("SELECT value FROM state WHERE key='base_digest'").fetchone()
    if existing:
        return
    raw = Path(source).read_bytes()
    digest = _sha(raw)
    name = 'base-'+digest+'.npz'
    with tempfile.NamedTemporaryFile(dir=folder, delete=False) as f:
        stage=Path(f.name)
        try:
            f.write(raw); f.flush(); os.fsync(f.fileno())
        except BaseException:
            stage.unlink(missing_ok=True)
            raise
    try:
        neural.Router.load(stage,catalog,encoder)
        os.replace(stage,folder/name)
        _flushdir(folder)
    finally:
        stage.unlink(missing_ok=True)
    db.execute("INSERT INTO versions VALUES(?,?,NULL,'base','{}')",('base',name))
    db.executemany('INSERT INTO state VALUES(?,?)',[('base_digest',digest),('active','base')])


@contextlib.contextmanager
def _writable(folder):
    folder.mkdir(parents=True,exist_ok=True,mode=0o700)
    with contextlib.closing(sqlite3.connect(folder/'events.sqlite3',timeout=60)) as db:
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('PRAGMA synchronous=FULL')
        db.executescript(SCHEMA)
        with db:
            db.execute('BEGIN IMMEDIATE')
            yield db


def _arrays(rows, order):
    return (np.array([features.encode(r['text'],r['data']) for r in rows]),
            np.array([order[r['op']] for r in rows],dtype=int))


def _lang(text):
    c=bool(re.search('[А-Яа-яЁё]',text))
    l=bool(re.search('[A-Za-zÁÉÍÓÚÑáéíóúñ]',text))
    return 'mixed' if c and l else 'cyrillic' if c else 'latin' if l else 'other'


def _score(model, rows, xy):
    x,y=xy
    hit=model.predict(x)==y
    correct=Counter()
    for row,h in zip(rows,hit):
        for regime in ('lang/'+_lang(row['text']), 'domain/'+row['op'].split('.')[0]):
            correct[regime]+=int(h)
    return {'correct':int(hit.sum()),'n':len(rows),'by_regime':dict(correct)},hit


def _fit(db,folder,ids,cat,enc,kernel,seed,epochs,rank,lr):
    fresh=[json.loads(r[0]) for r in db.execute('SELECT row_json FROM examples WHERE trial IS NULL ORDER BY rowid')]
    training,held=corpus.split_rows(fresh,seed=seed)
    # Fixed probes are intentionally known regression checks, never blind accuracy.
    guard=[{'text':kernel.meta[o],'data':{},'op':o} for o in ids]+corpus.seed_rows()
    training_keys={corpus._identity(r) for r in training}
    guard_train_overlap=sum(corpus._identity(row) in training_keys for row in guard)
    order={o:i for i,o in enumerate(ids)}
    train_xy=_arrays(training,order)
    hold_xy=_arrays(held,order)
    guard_xy=_arrays(guard,order)
    parent,parent_path=_active(db,folder)
    active=neural.Router.load(parent_path,cat,enc)
    candidate=neural.Router.load(parent_path,cat,enc)
    ref_path=folder/db.execute("SELECT filename FROM versions WHERE id='base'").fetchone()[0]
    frozen=neural.Router.load(ref_path,cat,enc) if parent!='base' else active
    if candidate.lora_rank not in (0,rank):
        candidate.merge_lora()
    if not candidate.lora_rank:
        candidate.enable_lora(rank=rank,seed=seed)
    rng=np.random.default_rng(seed)
    x,y=train_xy
    for _ in range(epochs):
        order_in_epoch=rng.permutation(len(y))
        for start in range(0,len(y),32):
            batch=order_in_epoch[start:start+32]
            candidate.train_lora_batch(x[batch],y[batch],lr=lr)
    before,_=_score(active,held,hold_xy)
    ref,_=_score(frozen,held,hold_xy)
    after,_=_score(candidate,held,hold_xy)
    g_before,ok_parent=_score(active,guard,guard_xy)
    g_ref,ok_ref=_score(frozen,guard,guard_xy) if parent!='base' else (g_before,ok_parent)
    g_after,ok_candidate=_score(candidate,guard,guard_xy)
    regressed=[k for k,v in after['by_regime'].items()
               if v<max(before['by_regime'][k],ref['by_regime'][k])]
    lost=int(((ok_parent|ok_ref)&~ok_candidate).sum())
    promote=after['correct']>before['correct'] and after['correct']>=ref['correct'] and not regressed and not lost
    trial=uuid.uuid4().hex
    version='lora-'+trial
    filename=version+'.npz'
    candidate.save(folder/filename,cat,enc)
    _flushdir(folder)
    restored=neural.Router.load(folder/filename,cat,enc)
    if not np.array_equal(restored.logits(hold_xy[0]),candidate.logits(hold_xy[0])):
        raise RuntimeError('Повторное чтение модели дало иные оценки')
    groups={r['group'] for r in fresh}
    report={'status':'promoted' if promote else 'challenger_retained','candidate':version,
            'active':version if promote else parent,'examples':len(fresh),'groups':len(groups),
            'train_n':len(training),'holdout_labels':len({r['op'] for r in held}),
            'held_out':{'parent':before,'initial_base':ref,'candidate':after},
            'regressed_regimes':regressed,'lost_guard_examples':lost,
            'guard':{'parent':g_before,'initial_base':g_ref,'candidate':g_after},
            'guard_distinct_labels':len({r['op'] for r in guard}),'guard_train_overlap':guard_train_overlap,
            'logits_compared':len(ids),'rank':rank,'epochs':epochs,'mode':'suggest_only',
            'checkpoint_sha256':_sha((folder/filename).read_bytes())}
    db.execute('INSERT INTO versions VALUES(?,?,?,?,?)',(version,filename,parent,report['status'],_compact(report)))
    db.executemany('INSERT INTO used_groups VALUES(?,?)',[(g,trial) for g in groups])
    db.execute('UPDATE examples SET trial=? WHERE trial IS NULL',(trial,))
    if promote:
        db.execute("UPDATE state SET value=? WHERE key='active'",(version,))
    return report


def submit_event(root, scope, base_checkpoint, event_id, row, *, min_groups=8,
                 seed=42, epochs=32, rank=4, lr=.12):
    """Attach a JSON-serializable opt-in example. Trigger a batch only when due.

    Once evaluated, a group is sealed; use a new independent scenario next time.
    Pins the initial checkpoint in the scope. Later changes to the supplied
    default cannot silently replace an existing scope's baseline or adapter.
    """
    if not isinstance(event_id,str) or not event_id.strip() or len(event_id)>200:
        raise ValueError('Нужен event_id для идемпотентности')
    if type(min_groups) is not int or min_groups<2 or type(epochs) is not int or not 1<=epochs<=1000:
        raise ValueError('Некорректный порог или число эпох')
    if type(seed) is not int or not 0<=seed<2**63 or type(rank) is not int or not 1<=rank<=10 or not np.isfinite(lr) or not 0<lr:
        raise ValueError('Некорректные параметры обучения')
    folder=_folder(root,scope)
    kernel=Kernel('unused')
    ids,cat,enc=train.identities(kernel)
    corpus._validate(row,set(ids))
    digest=_sha(_compact(row).encode('utf-8'))
    with _writable(folder) as db:
        _install_base(db,folder,base_checkpoint,cat,enc)
        found=db.execute('SELECT digest,receipt FROM events WHERE token=?',(event_id,)).fetchone()
        if found:
            if digest!=found[0]:
                raise ValueError('Один event_id получил разные данные')
            return json.loads(found[1])
        fingerprint=corpus._identity(row)
        duplicate=db.execute('SELECT label FROM examples WHERE fingerprint=?',(fingerprint,)).fetchone()
        if duplicate and duplicate[0]!=row['op']:
            raise ValueError('Метки одного образца противоречат друг другу')
        if duplicate:
            result={'status':'duplicate_example','active':_active(db,folder)[0]}
        elif db.execute('SELECT 1 FROM used_groups WHERE grp=?',(row['group'],)).fetchone():
            result={'status':'sealed_group','active':_active(db,folder)[0]}
        else:
            db.execute('INSERT INTO examples VALUES(?,?,?,?,NULL)',(fingerprint,row['op'],row['group'],_compact(row)))
            waiting=db.execute('SELECT count(DISTINCT grp) FROM examples WHERE trial IS NULL').fetchone()[0]
            result=({'status':'queued','groups':waiting,'min_groups':min_groups,'active':_active(db,folder)[0]}
                    if waiting<min_groups else _fit(db,folder,ids,cat,enc,kernel,seed,epochs,rank,lr))
        db.execute('INSERT INTO events(token,digest,receipt) VALUES(?,?,?)',(event_id,digest,_compact(result)))
        return result


def status(root,scope,base_checkpoint):
    folder=_folder(root,scope)
    path=folder/'events.sqlite3'
    if not path.is_file():
        return {'active':'default','checkpoint':str(base_checkpoint),'events':0,'waiting_groups':0}
    with contextlib.closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True,timeout=30)) as db:
        if not _initialized(db):
            return {'active':'default','checkpoint':str(base_checkpoint),'events':0,'waiting_groups':0}
        version,checkpoint=_active(db,folder)
        return {'active':version,'checkpoint':str(checkpoint),'events':db.execute('SELECT count(*) FROM events').fetchone()[0],
                'waiting_groups':db.execute('SELECT count(DISTINCT grp) FROM examples WHERE trial IS NULL').fetchone()[0],
                'versions':[{'id':v,'parent':p,'status':s} for v,p,s in db.execute('SELECT id,parent,status FROM versions ORDER BY rowid')]}


def rollback(root,scope,base_checkpoint):
    folder=_folder(root,scope)
    if not (folder/'events.sqlite3').is_file():
        return {'status':'at_base','active':'default','checkpoint':str(base_checkpoint)}
    with _writable(folder) as db:
        if not _initialized(db):
            return {'status':'at_base','active':'default','checkpoint':str(base_checkpoint)}
        version,path=_active(db,folder)
        parent=db.execute('SELECT parent FROM versions WHERE id=?',(version,)).fetchone()[0]
        if parent is None:
            return {'status':'at_base','active':version,'checkpoint':str(path)}
        filename=db.execute('SELECT filename FROM versions WHERE id=?',(parent,)).fetchone()[0]
        _,cat,enc=train.identities(Kernel('unused'))
        neural.Router.load(folder/filename,cat,enc)
        db.execute("UPDATE state SET value=? WHERE key='active'",(parent,))
        return {'status':'rolled_back','from':version,'active':parent,'checkpoint':str(folder/filename)}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',required=True)
    p.add_argument('--scope',required=True)
    p.add_argument('--base',required=True)
    ops=p.add_subparsers(dest='command',required=True)
    s=ops.add_parser('submit')
    s.add_argument('--event-id',required=True)
    s.add_argument('--row-file',required=True,help='Explicit curated JSON object with consent=true')
    s.add_argument('--min-groups',type=int,default=8)
    s.add_argument('--epochs',type=int,default=32)
    s.add_argument('--seed',type=int,default=42)
    s.add_argument('--rank',type=int,default=4)
    s.add_argument('--lr',type=float,default=.12)
    ops.add_parser('status')
    ops.add_parser('rollback')
    a=p.parse_args()
    if a.command=='submit':
        with open(a.row_file,encoding='utf-8') as f:
            row=json.load(f,object_pairs_hook=corpus._unique_dict)
        report=submit_event(a.root,a.scope,a.base,a.event_id,row,min_groups=a.min_groups,epochs=a.epochs,seed=a.seed,rank=a.rank,lr=a.lr)
    elif a.command=='rollback':
        report=rollback(a.root,a.scope,a.base)
    else:
        report=status(a.root,a.scope,a.base)
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
