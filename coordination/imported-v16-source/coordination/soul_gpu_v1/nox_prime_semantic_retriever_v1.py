"""Real local semantic memory search using already-installed Ollama embeddings.

Reads the original PRIME transcript and ranks episodes with Qwen3-Embedding.
No remote providers, no canonical S03 writes, no hidden downloads, no invented
semantic scores. Lexical fallback remains available if GPU is busy or unknown.
"""
from __future__ import annotations
import hashlib
import json
import math
import re
from urllib.request import Request, urlopen
from nox_prime_cognitive_memory_v1 import episodes, recall, tokens
from nox_prime_resource_advisor_v1 import trainer_active

MODEL="qwen3-embedding:0.6b"
MAX_EPISODES=16
MAX_CHARS=1300
MAX_RESULT=3

def explicit_memory_query(query):
    if not isinstance(query,str):return False
    return bool(re.search(
        r"помн|вчера|прошл|раньше|обсуждал|говорили|истори|"
        r"remember|last time|yesterday|previously|"
        r"recuerda|ayer|antes|última vez",
        query.casefold()))

def _embedding_batch(texts):
    """One local GPU admission; no pull and no blind long model warming."""
    data=json.dumps({"model":MODEL,"input":texts,
                     "truncate":True,"keep_alive":"1m"},
                    ensure_ascii=False).encode("utf-8")
    req=Request("http://127.0.0.1:11434/api/embed",data=data,
                method="POST",headers={"Content-Type":"application/json"})
    with urlopen(req,timeout=30) as resp:
        answer=json.loads(resp.read(3_000_000))
    vectors=answer.get("embeddings")
    if not isinstance(vectors,list) or len(vectors)!=len(texts):
        raise ValueError("INVALID_EMBEDDING_COUNT")
    if not vectors or not isinstance(vectors[0],list) or not vectors[0]:
        raise ValueError("INVALID_EMBEDDING_SHAPE")
    width=len(vectors[0])
    if not 32<=width<=8192:raise ValueError("INVALID_EMBEDDING_WIDTH")
    for row in vectors:
        if not isinstance(row,list) or len(row)!=width or any(
                not isinstance(x,(int,float)) or not math.isfinite(x) for x in row):
            raise ValueError("NONFINITE_EMBEDDING")
    return vectors

def _cosine(a,b):
    dot=sum(x*y for x,y in zip(a,b))
    sa=sum(x*x for x in a)
    sb=sum(y*y for y in b)
    return dot/math.sqrt(sa*sb) if sa>1e-12 and sb>1e-12 else 0

def _candidates(root,query):
    es=episodes(root)
    if not es:return []
    query_words=tokens(query)
    counts=[]
    for i,e in enumerate(es):
        score=len(query_words & tokens(e["user"]+" "+e["assistant"]))
        counts.append((score,i))
    # Mix lexical similarities and most recent episodes. Deduplicate.
    indices={i for _,i in sorted(counts,reverse=True)[:8]}
    indices.update(range(max(0,len(es)-8),len(es)))
    return [es[i] for i in sorted(indices)[:MAX_EPISODES]]

def retrieve(root,query,limit=MAX_RESULT):
    """Return actual semantic results; explicit fallback metadata if not run."""
    limit=max(1,min(5,int(limit)))
    lexical=recall(root,query,limit)
    if not explicit_memory_query(query):
        return {"method":"LEXICAL","results":lexical,"reason":"NOT_EXPLICIT_MEMORY_TASK"}
    running=trainer_active()
    if running is not False:
        return {"method":"LEXICAL","results":lexical,
                "reason":"GPU_TRAINING_ACTIVE_OR_UNVERIFIED"}
    pool=_candidates(root,query)
    if not pool:return {"method":"LEXICAL","results":[],"reason":"NO_EPISODES"}
    batch=[query[:MAX_CHARS]]+[
        (p["user"]+" "+p["assistant"])[:MAX_CHARS] for p in pool]
    try:
        vectors=_embedding_batch(batch)
    except (OSError,TimeoutError,ValueError,TypeError,KeyError,RuntimeError) as e:
        return {"method":"LEXICAL","results":lexical,"reason":type(e).__name__}
    scored=[]
    for e,v in zip(pool,vectors[1:]):
        similarity=_cosine(vectors[0],v)
        if not math.isfinite(similarity):continue
        combined=(e["time"]+"\n"+e["user"]+"\n"+e["assistant"])[:5000]
        ident=hashlib.sha256(combined.encode("utf-8")).hexdigest()[:16]
        scored.append((similarity,{"source":"NOX_LOCAL_TRANSCRIPT",
                                   "event_id":ident,"user":e["user"][:450],
                                   "assistant":e["assistant"][:650],
                                   "time":e["time"] or None,
                                   "similarity":round(similarity,4),
                                   "verified":False}))
    scored.sort(key=lambda x:x[0],reverse=True)
    return {"method":"QWEN3_EMBEDDING_LOCAL","results":[x for _,x in scored[:limit]],
            "model":MODEL,"gpu_training_active":False}
