"""Grow conversation-scoped compositions from observed JSON input/output examples.

The caller supplies a SQLite connection and Kernel.run or the trusted Kernel.ops
registry. No source, model output, expression, or SQL is interpreted as code.
One successful observation is a candidate, two distinct intermediates from
different effective inputs activate a recipe version. Events are idempotent.
"""
import hashlib
import json
import re
from contextlib import contextmanager
from functools import lru_cache

from .kernel import Kernel, registry as core_registry, validate

DDL = (
    """CREATE TABLE IF NOT EXISTS growth_head (
       scope TEXT NOT NULL, rule TEXT NOT NULL, active INTEGER, epoch INTEGER NOT NULL,
       PRIMARY KEY(scope,rule))""",
    """CREATE TABLE IF NOT EXISTS growth_version (
       scope TEXT NOT NULL, rule TEXT NOT NULL, version INTEGER NOT NULL,
       recipe TEXT NOT NULL, revoked INTEGER NOT NULL DEFAULT 0,
       PRIMARY KEY(scope,rule,version))""",
    """CREATE TABLE IF NOT EXISTS growth_proof (
       scope TEXT NOT NULL,rule TEXT NOT NULL,epoch INTEGER NOT NULL,
       recipe TEXT NOT NULL,input_hash TEXT NOT NULL,intermediate_hash TEXT NOT NULL,
       PRIMARY KEY(scope,rule,epoch,recipe,input_hash),
       UNIQUE(scope,rule,epoch,recipe,intermediate_hash))""",
    """CREATE TABLE IF NOT EXISTS growth_event (
       scope TEXT NOT NULL,event TEXT NOT NULL,digest TEXT NOT NULL,result TEXT NOT NULL,
       PRIMARY KEY(scope,event))""",
)
FIELD = re.compile(r'^[a-zA-Z][a-zA-Z0-9_]{0,63}$')

def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False,
                      separators=(",", ":"))

def fingerprint(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()

def token(value, label, limit):
    if not isinstance(value, str) or not value.strip() or len(value)>limit or any(ord(c)<32 for c in value):
        raise ValueError("Некорректный идентификатор: "+label)
    return value

def identifiers(scope, rule):
    token(scope,"scope",200)
    if scope=="default":
        raise ValueError("Нужна отдельная область разговора")
    token(rule,"rule",150)

@contextmanager
def transaction(db, write):
    outer = db.in_transaction
    if outer:
        db.execute("SAVEPOINT growth_action")
    else:
        db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
    try:
        for ddl in DDL:
            db.execute(ddl)
        yield
    except BaseException:
        if outer:
            db.execute("ROLLBACK TO growth_action")
            db.execute("RELEASE growth_action")
        else:
            db.rollback()
        raise
    else:
        if outer:
            db.execute("RELEASE growth_action")
        else:
            db.commit()

@lru_cache(maxsize=1)
def approved_operations():
    return core_registry()[0]

def registry(run):
    if isinstance(getattr(run,"__self__",None),Kernel) and getattr(run,"__func__",None) is Kernel.run:
        return run.__self__.ops
    if isinstance(run,dict):
        # A mapping supplied by the trusted host, not accepted in JSON inputs.
        return run
    raise TypeError("Требуется Kernel.run или доверенный реестр Kernel.ops")

def bounded(value,limit):
    validate(value)
    data=canonical(value).encode()
    if len(data)>limit:
        raise ValueError("Объект превышает лимит составной операции")
    return json.loads(data)

def compose(run, recipe, a, b):
    first,second,bind=recipe
    if not isinstance(bind,str) or not FIELD.fullmatch(bind):
        raise ValueError("Некорректное поле связи")
    ops=registry(run)
    approved=approved_operations()
    for name in (first,second):
        if not isinstance(name,str) or name not in approved or ops.get(name) is not approved[name]:
            raise ValueError("Доступны только зарегистрированные чистые операции")
    if not isinstance(a,dict) or not isinstance(b,dict):
        raise ValueError("Операциям требуются JSON-объекты")
    a=bounded(a,96000)
    b=bounded(b,96000)
    b.pop(bind,None)
    effective_input=fingerprint([a,b])
    inter=bounded(ops[first](a),160000)
    data=bounded({**b,bind:inter},96000)
    result=bounded(ops[second](data),160000)
    return result,effective_input,fingerprint(inter)

def propose_observation(db,scope,event,rule,first,second,bind,first_data,
                        second_data,expected,run):
    identifiers(scope,rule)
    token(event,"event",200)
    if rule in registry(run) or rule.startswith("intent."):
        raise ValueError("Имя уже зарезервировано ядром")
    recipe=[first,second,bind]
    expected=bounded(expected,160000)
    encoded=canonical(recipe)
    result,input_hash,inter_hash=compose(run,recipe,first_data,second_data)
    digest=fingerprint([rule,recipe,input_hash,expected])
    with transaction(db,True):
        old=db.execute("SELECT digest,result FROM growth_event WHERE scope=? AND event=?",
                       (scope,event)).fetchone()
        if old:
            if old[0]!=digest:
                raise ValueError("Конфликт идентификатора наблюдения")
            return json.loads(old[1])
        db.execute("INSERT OR IGNORE INTO growth_head VALUES(?,?,NULL,0)",(scope,rule))
        active,epoch=db.execute("SELECT active,epoch FROM growth_head WHERE scope=? AND rule=?",
                                (scope,rule)).fetchone()
        key=(scope,rule,epoch,encoded)
        current=db.execute("SELECT recipe FROM growth_version WHERE scope=? AND rule=? AND version=?",
                           (scope,rule,active)).fetchone()
        if canonical(result)!=canonical(expected):
            status="rejected"
        elif current and current[0]==encoded:
            status="active"
        else:
            veto=db.execute("""SELECT 1 FROM growth_version WHERE scope=? AND rule=? AND recipe=?
                               AND revoked=1 LIMIT 1""",(scope,rule,encoded)).fetchone()
            status="revoked" if veto else "candidate"
        if status=="candidate":
            db.execute("INSERT OR IGNORE INTO growth_proof VALUES(?,?,?,?,?,?)",(*key,input_hash,inter_hash))
        examples=db.execute("""SELECT count(*) FROM growth_proof WHERE scope=? AND rule=?
                                AND epoch=? AND recipe=?""",key).fetchone()[0]
        if status=="candidate" and examples>=2:
            active=db.execute("SELECT COALESCE(max(version),0)+1 FROM growth_version WHERE scope=? AND rule=?",
                              (scope,rule)).fetchone()[0]
            db.execute("INSERT INTO growth_version(scope,rule,version,recipe) VALUES(?,?,?,?)",
                       (scope,rule,active,encoded))
            db.execute("UPDATE growth_head SET active=?,epoch=epoch+1 WHERE scope=? AND rule=?",
                       (active,scope,rule))
            status="active"
        if status=="active":
            examples=max(examples,2)
        response=dict(status=status,rule=rule,version=active,examples=examples)
        db.execute("INSERT INTO growth_event VALUES(?,?,?,?)",(scope,event,digest,canonical(response)))
        return response

def execute(db,scope,rule,a,b,run):
    identifiers(scope,rule)
    with transaction(db,False):
        row=db.execute("""SELECT v.recipe FROM growth_head h JOIN growth_version v
                          ON h.scope=v.scope AND h.rule=v.rule AND h.active=v.version
                          WHERE h.scope=? AND h.rule=? AND v.revoked=0""",(scope,rule)).fetchone()
    if not row:
        raise ValueError("В этой области нет активной версии способности")
    return compose(run,json.loads(row[0]),a,b)[0]

def catalog(db,scope):
    identifiers(scope,"catalog")
    with transaction(db,False):
        rows=db.execute("""SELECT v.rule,v.version,v.recipe,v.revoked,h.active FROM growth_version v
                           JOIN growth_head h ON v.scope=h.scope AND v.rule=h.rule
                           WHERE v.scope=? ORDER BY v.rule,v.version""",(scope,)).fetchall()
    return [dict(rule=r,version=v,first=f,second=s,bind=b,active=v==current,revoked=bool(revoked))
            for r,v,recipe,revoked,current in rows for f,s,b in [json.loads(recipe)]]

def rollback(db,scope,rule,version=None):
    """Deactivate and revoke current version, or explicitly select an existing version."""
    identifiers(scope,rule)
    if version is not None and (type(version) is not int or version<=0):
        raise ValueError("Некорректная версия")
    with transaction(db,True):
        head=db.execute("SELECT active FROM growth_head WHERE scope=? AND rule=?",(scope,rule)).fetchone()
        if not head:
            raise ValueError("Неизвестная способность")
        current=head[0]
        if version is not None:
            target=db.execute("SELECT 1 FROM growth_version WHERE scope=? AND rule=? AND version=?",
                              (scope,rule,version)).fetchone()
            if not target:
                raise ValueError("Версия не найдена")
            db.execute("UPDATE growth_version SET revoked=0 WHERE scope=? AND rule=? AND version=?",
                       (scope,rule,version))
        if current is not None and current!=version:
            db.execute("UPDATE growth_version SET revoked=1 WHERE scope=? AND rule=? AND version=?",
                       (scope,rule,current))
        if current!=version:
            db.execute("UPDATE growth_head SET active=?,epoch=epoch+1 WHERE scope=? AND rule=?",
                       (version,scope,rule))
        return dict(rule=rule,version=version,status="active" if version else "revoked")

def revoke(db,scope,rule):
    return rollback(db,scope,rule)
