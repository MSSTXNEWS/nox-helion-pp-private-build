"""NOX SYNAPTIC MEMORY V1: additive local semantic memory for the existing NOX S03 host.

No downloads, no writes to S03. Ollama qwen3-embedding:0.6b is required.
Graph relationships are semantic associations, NOT trained neural synapses.
Python 3.10+ stdlib only. All data stays inside NOX_NEW/brain/memory.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
import struct
import time
from urllib.request import Request, urlopen
from urllib.error import URLError

MODEL = "qwen3-embedding:0.6b"
API = "http://127.0.0.1:11434/api/embed"
ROOT = Path(os.environ.get("NOX_ROOT",r"C:\NOX_HELION\NOX_NEW" if os.name == "nt" else "."))
DB = ROOT / "brain" / "memory" / "synaptic.sqlite3"
PERSONAS = {"KV", "AM", "LA", "EV", "KW"}

def embed(text: str, api=API):
    payload = json.dumps({"model":MODEL,"input":text}).encode()
    req = Request(api, data=payload,headers={"Content-Type":"application/json"},method="POST")
    with urlopen(req,timeout=90) as reply:
        obj = json.loads(reply.read())
    vectors=obj.get("embeddings")
    if not vectors or not vectors[0]:
        raise RuntimeError("Ollama embedding returned no vector")
    vec=[float(x) for x in vectors[0]]
    norm=math.sqrt(sum(x*x for x in vec))
    if not norm or not math.isfinite(norm):
        raise ValueError("Invalid embedding norm")
    return [x/norm for x in vec]

def cosine(a,b):
    if len(a)!=len(b):
        raise ValueError("Embedding dimension mismatch")
    return sum(x*y for x,y in zip(a,b))

def connect(db=DB):
    db.parent.mkdir(parents=True,exist_ok=True)
    cx=sqlite3.connect(db)
    cx.execute("PRAGMA journal_mode=WAL")
    cx.execute("PRAGMA foreign_keys=ON")
    cx.executescript("""
    CREATE TABLE IF NOT EXISTS nodes(
      id TEXT PRIMARY KEY, persona TEXT NOT NULL, project TEXT NOT NULL,
      source TEXT NOT NULL, body TEXT NOT NULL, embedding TEXT NOT NULL,
      model TEXT NOT NULL, created INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS edges(
      source_id TEXT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
      target_id TEXT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
      similarity REAL NOT NULL, created INTEGER NOT NULL,
      PRIMARY KEY(source_id,target_id));
    CREATE INDEX IF NOT EXISTS nodes_scope ON nodes(persona,project);
    CREATE INDEX IF NOT EXISTS edges_source ON edges(source_id);
    """)
    return cx

def remember(text,source,persona="KV",project="default",approved=False,db=DB,vector=None,threshold=0.78):
    if not approved:
        raise PermissionError("Memory requires explicit owner approval")
    if persona not in PERSONAS or not source.strip() or not text.strip() or len(text)>12000:
        raise ValueError("Invalid persona, source or memory body")
    vector=vector if vector is not None else embed(text)
    if not vector:
        raise ValueError("Empty vector")
    nodeid=hashlib.sha256(json.dumps([persona,project,source,text],ensure_ascii=False).encode()).hexdigest()
    with connect(db) as cx:
        prior=cx.execute("SELECT embedding,model FROM nodes WHERE id=?",(nodeid,)).fetchone()
        if prior:
            return {"id":nodeid,"status":"already-present"}
        matches=[]
        for other_id,encoded,model in cx.execute("SELECT id,embedding,model FROM nodes WHERE persona=? AND project=?",(persona,project)):
            if model!=MODEL:
                continue
            try:
                score=cosine(vector,json.loads(encoded))
            except (ValueError,TypeError):
                continue
            if score>=threshold:
                matches.append((other_id,score))
        cx.execute("INSERT INTO nodes VALUES (?,?,?,?,?,?,?,?)",
                   (nodeid,persona,project,source,text,json.dumps(vector),MODEL,int(time.time())))
        for other_id,score in matches:
            now=int(time.time())
            cx.execute("INSERT OR REPLACE INTO edges VALUES (?,?,?,?)",(nodeid,other_id,score,now))
            cx.execute("INSERT OR REPLACE INTO edges VALUES (?,?,?,?)",(other_id,nodeid,score,now))
    return {"id":nodeid,"status":"stored","linked":len(matches)}

def recall(question,persona="KV",project="default",limit=5,db=DB,vector=None):
    if persona not in PERSONAS:
        raise ValueError("Invalid persona")
    vector=vector if vector is not None else embed(question)
    with connect(db) as cx:
        matches=[]
        for nodeid,source,body,encoded,model in cx.execute(
            "SELECT id,source,body,embedding,model FROM nodes WHERE persona=? AND project=?",(persona,project)):
            if model!=MODEL:
                continue
            try: score=cosine(vector,json.loads(encoded))
            except (ValueError,TypeError): continue
            matches.append({"id":nodeid,"source":source,"text":body,"similarity":round(score,5)})
    return sorted(matches,key=lambda x:x["similarity"],reverse=True)[:max(0,min(limit,20))]

def status(db=DB):
    with connect(db) as cx:
        nodes=cx.execute("SELECT count(*) FROM nodes").fetchone()[0]
        edges=cx.execute("SELECT count(*) FROM edges").fetchone()[0]
    return {"nodes":nodes,"directed_edges":edges,"model":MODEL,"db":str(db),"s03_integrated":False,"weights_trained":False}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("status","remember","recall"))
    p.add_argument("--text")
    p.add_argument("--source",default="owner")
    p.add_argument("--persona",default="KV")
    p.add_argument("--project",default="default")
    p.add_argument("--approved",action="store_true")
    p.add_argument("--db",type=Path,default=DB)
    a=p.parse_args()
    if a.action=="status": result=status(a.db)
    elif a.action=="remember":result=remember(a.text or "",a.source,a.persona,a.project,a.approved,a.db)
    else:result=recall(a.text or "",a.persona,a.project,db=a.db)
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=="__main__":main()
