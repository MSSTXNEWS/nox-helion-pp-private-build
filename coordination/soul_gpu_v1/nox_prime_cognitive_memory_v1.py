"""NOX PRIME M0/M1 read-only episodic retrieval from existing chat transcript.

NOT an authoritative S03 clone; authorized OneHost S03 remains the sole
long-term memory writer. This module makes existing PRIME conversations
searchable until the native S03 bridge is approved and physically tested.
Never import or expose data from another PersonaID.
"""
from __future__ import annotations
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re

MAX_HISTORY_BYTES=5_000_000
MAX_EPISODES=1200
MAX_RESULTS=3
STOPWORDS={"и","в","на","что","как","это","тот","эта","там","из","для",
           "не","но","мы","он","она","ты","я","все","уже","ещё",
           "the","and","for","you","are","was","with","this","that",
           "de","el","la","que","los","por","con","una","las"}

def tokens(text):
    values=re.findall(r"[^\W_]{3,}",str(text).casefold(),flags=re.UNICODE)
    return {w for w in values if w not in STOPWORDS}

def _path(root):
    return Path(root)/"brain"/"history"/"unified_chat_v1.jsonl"

def _read_rows(root):
    path=_path(root)
    if not path.is_file() or path.is_symlink():
        return []
    with path.open("rb") as f:
        f.seek(0,2)
        size=f.tell()
        f.seek(max(0,size-MAX_HISTORY_BYTES))
        if size>MAX_HISTORY_BYTES:f.readline()
        data=f.read(MAX_HISTORY_BYTES)
    out=[]
    for raw in data.splitlines():
        try:
            v=json.loads(raw)
            if not isinstance(v,dict) or v.get("role") not in ("user","assistant"):
                continue
            # Old PRIME-only chat logs have no persona field. Never infer that
            # another PersonaID may read these global PRIME events.
            scope=v.get("persona_id","PRIME")
            if scope!="PRIME":continue
            content=v.get("content")
            if not isinstance(content,str) or not content.strip():continue
            out.append({"role":v["role"],"content":content[:4000],
                        "time":str(v.get("time") or "")[:64]})
        except (UnicodeError,ValueError,TypeError):
            continue
    return out[-MAX_EPISODES*2:]

def episodes(root):
    rows=_read_rows(root)
    result=[]
    current=None
    for record in rows:
        if record["role"]=="user":
            if current:
                result.append(current)
            current={"user":record["content"],"assistant":"",
                     "time":record["time"]}
        elif current and not current["assistant"]:
            current["assistant"]=record["content"]
            result.append(current)
            current=None
    if current:result.append(current)
    return result[-MAX_EPISODES:]

def recall(root,query,limit=MAX_RESULTS):
    if not isinstance(query,str) or not query.strip():
        return []
    limit=max(1,min(5,int(limit)))
    q=tokens(query)
    if not q:return []
    scored=[]
    for order,event in enumerate(episodes(root)):
        content=(event["user"]+" "+event["assistant"])[:4000]
        matching=q & tokens(content)
        if not matching:continue
        # Lexical semantic fallback: no claim to be a neural embedding model.
        # Source/time are preserved for transparent claims.
        score=len(matching)/len(q) + .2*len(matching)/max(1,len(tokens(content)))
        score+=.00002*order
        source=sha256((event["time"]+"\n"+content).encode("utf-8")).hexdigest()[:16]
        scored.append((score,order,{"source":"NOX_LOCAL_TRANSCRIPT",
                                    "event_id":source,
                                    "time":event["time"] or None,
                                    "user":event["user"][:450],
                                    "assistant":event["assistant"][:650],
                                    "matched_terms":sorted(matching)[:12],
                                    "verified":False}))
    scored.sort(key=lambda row:(row[0],row[1]),reverse=True)
    return [v for _,_,v in scored[:limit]]

def memory_context(root,user_text):
    """Retrieve only evidence for a context-relevant question."""
    if not isinstance(user_text,str):return []
    query_tokens=tokens(user_text)
    if not query_tokens:return []
    # A lightweight context mode: routine greetings do not scan the archive.
    if len(query_tokens)<2 and not any(x in user_text.casefold() for x in
        ("помн","вчера","раньше","прошл","remember","antes","ayer")):
        return []
    return recall(root,user_text)
