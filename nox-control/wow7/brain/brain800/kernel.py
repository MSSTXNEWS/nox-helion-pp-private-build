import contextlib
import hashlib
import importlib
import json
import os
from pathlib import Path
import sqlite3
from . import intent

MODULES = ("reason","memory","social","project","perception","learning","studio")
def registry():
    ops, meta = {}, {}
    for domain in MODULES:
        mod = importlib.import_module("." + domain, __package__)
        if set(mod.OPS) != set(mod.META) or len(mod.OPS) != 100:
            raise RuntimeError("Incomplete module: " + domain)
        for key, fn in mod.OPS.items():
            name = key if key.startswith(domain + ".") else domain + "." + key
            ops[name],meta[name] = fn,mod.META[key]
    meta.update({"intent."+k:v for k,v in intent.META.items()})
    return ops,meta

SCHEMA = """
CREATE TABLE IF NOT EXISTS entries(seq INTEGER PRIMARY KEY,scope TEXT NOT NULL,kind TEXT NOT NULL,
 key TEXT NOT NULL,version INTEGER NOT NULL,text TEXT NOT NULL,closed INTEGER NOT NULL,source TEXT NOT NULL,
 UNIQUE(scope,kind,key,version));
CREATE VIEW IF NOT EXISTS latest AS SELECT e.* FROM entries e WHERE NOT EXISTS
 (SELECT 1 FROM entries n WHERE (n.scope,n.kind,n.key)=(e.scope,e.kind,e.key) AND n.version>e.version);
CREATE TABLE IF NOT EXISTS receipts(scope TEXT NOT NULL,token TEXT NOT NULL,digest TEXT NOT NULL,
 result TEXT NOT NULL,PRIMARY KEY(scope,token));
"""
def pack(x):
    return json.dumps(x, ensure_ascii=False, allow_nan=False, separators=(",",":"))

def validate(data,depth=0):
    if depth>15:raise ValueError("Слишком глубокая структура JSON")
    if isinstance(data,(list,dict)):
        if len(data)>1500:raise ValueError("Слишком много элементов")
        for value in (data.values() if isinstance(data,dict) else data):validate(value,depth+1)

@contextlib.contextmanager
def connect_journal(path):
    path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    db = sqlite3.connect(path,timeout=4)
    db.row_factory = sqlite3.Row
    db.create_function("fold",1,lambda s:s.casefold(),deterministic=True)
    try:
        db.execute("PRAGMA journal_mode=WAL")
        db.executescript(SCHEMA)
        with db:yield db
    finally:db.close()


class Kernel:
    def __init__(self, path):
        self.path = Path(path)
        self.ops,self.meta = registry()

    def journal(self):
        return connect_journal(self.path)

    def run(self, name, data, scope="",token=""):
        if not isinstance(data,dict):raise ValueError("Ожидается объект JSON")
        validate(data)
        if name not in self.meta:raise ValueError("Неизвестная операция: "+str(name))
        if len(pack(data).encode())>96000:raise ValueError("Запрос превышает 96 КБ")
        if name in self.ops:
            value = self.ops[name](data)
        else:
            if not scope or scope=="default" or len(scope)>200:raise ValueError("Для памяти нужен отдельный идентификатор беседы")
            _,kind,act=name.split(".")
            with self.journal() as db:
                if act in intent.WRITES:
                    db.execute("BEGIN IMMEDIATE")
                    digest=hashlib.sha256(json.dumps([name,data],sort_keys=True,ensure_ascii=False).encode()).hexdigest()
                    if token:
                        stored=db.execute("SELECT digest,result FROM receipts WHERE scope=? AND token=?",(scope,token)).fetchone()
                        if stored:
                            if stored["digest"]!=digest:raise ValueError("Конфликт идентификатора запроса")
                            return json.loads(stored["result"])
                value=intent.execute(db,scope,kind,act,data)
                if act in intent.WRITES and token:
                    db.execute("INSERT INTO receipts VALUES(?,?,?,?)",(scope,token,digest,pack(value)))
        if len(pack(value).encode())>160000:raise ValueError("Слишком большой результат; уточните выборку")
        return value
