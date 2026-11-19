"""NOX V84: owner-scoped, source-backed offline memory retrieval.
Runs INSIDE existing OneHost. Does not create a database, daemon, second model,
training set, exported chat transcript or public endpoint.
"""
from __future__ import annotations
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
import hashlib
import json
import re
import sqlite3

_SEGMENT_LEVELS=frozenset({"M0","M1","M2","M3","M4","M5","M6","M7"})
_TERMS=re.compile(r"[\w\-]{3,}",re.UNICODE)

@dataclass(frozen=True)
class NativeMemoryAccess:
    """Authorization comes ONLY from trusted existing OneHost, not model output."""
    authorize: Callable[[str, str], bool]
    allow_record: Callable[[str, str, Mapping], bool]
    stop_active: Callable[[], bool]

def _open(path: str) -> sqlite3.Connection:
    p=Path(path)
    if not p.is_file() or p.is_symlink() or p.stat().st_size>200_000_000:
        raise ValueError("HOLD_DB_FILE_GATE")
    con=sqlite3.connect("file:"+str(p)+"?mode=ro",uri=True,timeout=3)
    con.row_factory=sqlite3.Row
    con.execute("PRAGMA query_only=ON")
    return con

def _clean_string(v,limit=1400):
    if not isinstance(v,str): return ""
    return v.strip()[:limit]

def _search_terms(question: str):
    if not isinstance(question,str) or not 3<=len(question)<=1000:
        raise ValueError("HOLD_QUERY")
    terms=list(dict.fromkeys(w.casefold() for w in _TERMS.findall(question)))
    if not terms:raise ValueError("HOLD_QUERY_TERMS")
    return terms[:10]

def retrieve(question: str, *, scope: str, paths: Mapping, native: NativeMemoryAccess, limit: int=10):
    """Bounded local graph+S03 search; returns content only to authorized OneHost.

    Owner_scope + per-record ACL enforced before any text is returned.
    Records with no provenance and untrusted graph nodes are not released.
    SQLite read-only connections include committed WAL data.
    """
    if not isinstance(scope,str) or not 3<=len(scope)<=128:
        return {"state":"HOLD_SCOPE","results":[]}
    if type(limit) is not int or not 1<=limit<=20:
        return {"state":"HOLD_LIMIT","results":[]}
    if not isinstance(paths,Mapping) or not isinstance(native,NativeMemoryAccess):
        return {"state":"HOLD_NATIVE","results":[]}
    try:
        terms=_search_terms(question)
        if native.stop_active() is not False or native.authorize(scope,"s03.recall") is not True:
            return {"state":"HOLD_STOP_OR_ACCESS","results":[]}
    except Exception:
        return {"state":"HOLD_NATIVE_ACCESS","results":[]}
    results=[]; seen=set()
    def append(kind,row,text,provenance,identity):
        text=_clean_string(text)
        provenance=_clean_string(provenance,500)
        if len(text)<3 or not provenance:return
        if not any(t in text.casefold() for t in terms):return
        obj={"kind":kind,"id":str(identity)[:128],"text":text,"source":provenance}
        # Native callback sees source metadata and MUST evaluate tenant/persona ACL.
        # The trusted host must receive the record's own session/scope metadata
        # to enforce ACL; the model/user never supplies this metadata.
        acl_meta=dict(obj)
        if kind.startswith("s03_"):
            acl_meta["record_session"]=_clean_string(row["session"],128)
        elif kind=="fact":
            acl_meta["record_dialog_id"]=_clean_string(row["dialog_id"],128)
        elif kind=="node":
            acl_meta["record_node_meta"]=_clean_string(row["meta"],600)
        if native.allow_record(scope,kind,acl_meta) is not True:return
        digest=hashlib.sha256((kind+"|"+text+"|"+provenance).encode()).hexdigest()
        if digest in seen:return
        seen.add(digest)
        obj["sha256"]=digest
        obj["term_hits"]=sum(t in text.casefold() for t in terms)
        results.append(obj)
    try:
        if paths.get("seed"):
            with _open(paths["seed"]) as con:
                # S03 level stored by native runtime; no assumption that every row
                # belongs to a particular tenant without host ACL callback.
                for row in con.execute("SELECT id,level,content,provenance,ref,sha256,session FROM s03_segments ORDER BY significance DESC LIMIT 900"):
                    kind=str(row["level"])
                    if kind not in _SEGMENT_LEVELS:continue
                    append("s03_"+kind,row,row["content"],row["provenance"] or row["ref"],row["id"])
                # Genesis payload can contain sensitive biographical history;
                # do not release raw payload through generic knowledge retrieval.
        if paths.get("infinite"):
            with _open(paths["infinite"]) as con:
                for row in con.execute("SELECT fact_id,key,value,source,active,is_test,superseded_by,dialog_id FROM facts ORDER BY ts_utc DESC LIMIT 500"):
                    if row["active"] != 1 or row["is_test"] == 1 or row["superseded_by"]:continue
                    append("fact",row,str(row["key"])+": "+str(row["value"]),row["source"],row["fact_id"])
                for row in con.execute("SELECT node_id,text,source,is_test,hidden,kind,meta FROM brain_nodes ORDER BY ts_utc DESC LIMIT 1000"):
                    if row["is_test"] == 1 or row["hidden"] == 1:continue
                    append("node",row,row["text"],row["source"],row["node_id"])
        results.sort(key=lambda x:(-x["term_hits"],x["kind"],x["id"]))
        if native.stop_active() is not False or native.authorize(scope,"s03.recall") is not True:
            return {"state":"HOLD_STOP_REVOKED","results":[]}
        return {"state":"NATIVE_LOCAL_MEMORY_RETRIEVED","results":results[:limit],
                "returned":min(limit,len(results)),"weights_changed":False}
    except (OSError,ValueError,sqlite3.DatabaseError,KeyError):
        return {"state":"HOLD_S03_QUERY_OR_SCHEMA","results":[]}
    except Exception:
        return {"state":"HOLD_NATIVE_RECORD_ACL","results":[]}

def distillation_reference_plan(*, scope:str, query:str, paths:Mapping,
                                native:NativeMemoryAccess, owner_training_opt_in:bool=False):
    """Only local hashed references, never private text or a fake trainable model."""
    if owner_training_opt_in is not True:
        return {"state":"HOLD_TRAINING_CONSENT","trainset_created":False}
    if native.authorize(scope,"forge.plan") is not True or native.stop_active() is not False:
        return {"state":"HOLD_FORGE_SCOPE_OR_STOP","trainset_created":False}
    found=retrieve(query,scope=scope,paths=paths,native=native,limit=20)
    if found.get("state")!="NATIVE_LOCAL_MEMORY_RETRIEVED":
        return {"state":"HOLD_MEMORY_SOURCE","trainset_created":False}
    return {"state":"LOCAL_REFERENCE_CANDIDATES_ONLY",
            "source_sha256":[r["sha256"] for r in found["results"]],
            "candidate_count":len(found["results"]),
            "trainset_created":False,"optimizer_steps":0,
            "privacy_review_needed":True,"holdout_needed":True,
            "backup_restore_needed":True,"student_base_weights_needed":True}
