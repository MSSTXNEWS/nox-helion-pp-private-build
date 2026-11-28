# -*- coding: utf-8 -*-
"""M10: проверка цитат [m:id] и утверждений «ты говорил…» (stdlib). Встраивание: см. STREAMS_NOTES.md.
verify(answer, get_records, allowed_ids=None, user=None, rerank=None) -> dict
  get_records(ids) -> {id: {"text":str,"user":str,"status":str}}
  rerank(claim, [texts]) -> [score]  (необязательно; bge-reranker :8083)
Результат: {"ok":bool, "cites":[{id,status,sentence}], "uncited":[sentence], "clean":str, "regen":bool}
status: ok | missing | foreign | forgotten | unsupported
"""
import re
try: from m10_logic import stems
except ImportError:
    import os, sys; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); from m10_logic import stems
CITE = re.compile(r"\[m:(\d+)\]")
CLAIM = re.compile(r"\b(?:ты|вы)\b[^.!?\n]{0,40}?\b(?:говорил\w*|сказал\w*|упоминал\w*|рассказывал\w*|писал\w*|просил\w*|обещал\w*|делил\w+)|\b(?:помню|как)\s*,?\s*(?:что\s+)?(?:ты|вы)\s+\w+|в\s+прошлый\s+раз\s+ты|ранее\s+ты\s+\w+", re.I)
UNKNOWN = "Не помню этого. Расскажешь?"
def _sents(text):
    return [s for s in re.split(r"(?<=[.!?…])\s+|\n+", text) if s.strip()]
def overlap(claim, rec):
    a = set(stems(CITE.sub("", claim))); b = set(stems(rec))
    if not a or not b: return 0, 0.0
    sh = len(a & b); return sh, sh / float(min(len(a), len(b)))
def supported(claim, rec, rerank=None, min_ratio=0.34):
    sh, r = overlap(claim, rec)
    need = 1 if min(len(set(stems(CITE.sub("", claim)))), len(set(stems(rec)))) <= 2 else 2
    if sh >= need and r >= min_ratio: return True
    if rerank:
        try: return rerank(CITE.sub("", claim), [rec])[0] >= 0.30
        except Exception: return False
    return False
def verify(answer, get_records, allowed_ids=None, user=None, rerank=None):
    ids = sorted({int(x) for x in CITE.findall(answer)}); recs = get_records(ids) if ids else {}
    cites = []; clean = answer; bad_sent = set()
    for s in _sents(answer):
        prev = 0
        for m in CITE.finditer(s):
            clause = s[prev:m.start()]; prev = m.end()
            i = int(m.group(1)); r = recs.get(i)
            if not r: st = "missing"
            elif r.get("status") == "forgotten" or not r.get("text"): st = "forgotten"
            elif (user and r.get("user") != user) or (allowed_ids is not None and i not in allowed_ids and r.get("user") != user): st = "foreign"
            elif supported(clause if stems(clause) else s, r["text"], rerank): st = "ok"
            else: st = "unsupported"
            cites.append({"id": i, "status": st, "sentence": s[:200]})
            if st != "ok": bad_sent.add(s)
    for c in cites:
        if c["status"] != "ok": clean = clean.replace("[m:%d]" % c["id"], "")
    uncited = [s for s in _sents(answer) if CLAIM.search(s) and not any(c["status"] == "ok" and c["sentence"][:200] == s[:200] for c in cites)]
    clean = re.sub(r"[ \t]{2,}", " ", clean).strip()
    return {"ok": not bad_sent and not uncited, "cites": cites, "uncited": [u[:200] for u in uncited], "clean": clean, "regen": bool(bad_sent or uncited), "unknown": UNKNOWN}
