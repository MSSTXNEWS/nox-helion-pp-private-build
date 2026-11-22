"""Source-linked advice for Zamysel.

This layer stores advice in the existing S03 SQLite database. Every structured premise
points to an S03 ref and the full SHA-256 observed when the advice was written. Call
refresh_stale_advice after correction/revocation or before presenting saved advice.
"""
import hashlib
import json
import os
import re
import time

from memcommon import commit, ensure_schema

try:
    from correction import SECRET_RE
except Exception:  # pragma: no cover - standalone import fallback
    SECRET_RE = re.compile(
        r"(sk-[A-Za-z0-9_\-]{16,}|ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|"
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----|"
        r"(?:password|passwd|пароль|token|токен|api[_-]?key|secret)\s*[:=]\s*\S{6,})",
        re.I,
    )

SPEAKERS = ("owner", "nox")
PRIVACY = "owner_only"
SRC_KINDS = ("nox_generated", "nox_inferred", "owner_stated", "owner_choice", "import")
OWNER_SOURCE_KINDS = frozenset(("owner", "owner_stated", "owner_choice"))


def _sha(text):
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _json(value, default):
    try:
        result = json.loads(value)
        return result if result is not None else default
    except (TypeError, ValueError):
        return default


def _source(store, ref):
    """Return (text, status) for an S03 ref without trusting a cached snippet."""
    try:
        rec = store.get(ref)
    except (KeyError, LookupError, ValueError, TypeError):
        return None, None
    if not rec:
        return None, None
    text = store.text_of(rec) if hasattr(store, "text_of") else rec.get("text")
    return text, rec.get("status", "active")


def _owner_source_ok(store, ref):
    """Require actual owner provenance for an owner-scoped premise.

    A speaker label describes the advice scope; it does not promote arbitrary S03
    content to owner evidence. Facts use the Riverse evidence ladder, profiles use
    their stored source, and episodes are not treated as owner-confirmed evidence.
    """
    try:
        rec = store.get(ref)
    except (KeyError, LookupError, ValueError, TypeError):
        return False
    if not rec or rec.get("status", "active") != "active":
        return False
    if rec.get("type") == "profile":
        return rec.get("source") in OWNER_SOURCE_KINDS and rec.get("section") == "owner"
    if rec.get("type") == "episode":
        return False
    if rec.get("type") not in (None, "fact"):
        return False
    if rec.get("owner_confirmed"):
        return True
    ladder_id = rec.get("ladder_id")
    if ladder_id:
        try:
            kinds = [r[0] for r in store.db.execute(
                "SELECT kind FROM evidence WHERE fact_id=? AND polarity>0", (ladder_id,)
            ).fetchall()]
        except Exception:
            kinds = []
        if kinds:
            return any(kind in OWNER_SOURCE_KINDS for kind in kinds)
    return rec.get("source_kind") in OWNER_SOURCE_KINDS or rec.get("source") in OWNER_SOURCE_KINDS


def _check_text(text, label):
    if not isinstance(text, str) or not text.strip():
        raise ValueError("%s: пустой текст" % label)
    if SECRET_RE.search(text):
        raise ValueError("%s: секретные данные не сохраняются" % label)
    return text.strip()


def _default_journal(store, clock):
    path = getattr(store, "path", None)
    if not path or path == ":memory:":
        return None
    try:
        from life_journal import LifeJournal, default_path
        state_dir = os.path.dirname(os.path.abspath(path))
        return LifeJournal(default_path(state_dir), clock=clock)
    except Exception:  # journal availability must be explicit in result, not fatal to DB operation
        return None


def _journal_event(store, journal, clock, text, data):
    journal = journal if journal is not None else _default_journal(store, clock)
    if journal is None:
        return {"ok": False, "error": "journal_unavailable"}
    try:
        journal.append("event", text, "zamysel", data=data, ts=clock())
        return {"ok": True, "error": None}
    except Exception as exc:
        # The S03 transaction has already committed. Surface the journal failure
        # as metadata instead of claiming the write itself failed.
        return {"ok": False, "error": type(exc).__name__}


def _get_advice(store, advice_id, speaker):
    row = store.db.execute(
        "SELECT id,speaker,privacy,text,premises,breakers,free_premises,nox_conf,status,history,"
        "src_kind,t_event,t_learned,created,updated FROM zm_advice WHERE id=? AND speaker=?",
        (int(advice_id), str(speaker)),
    ).fetchone()
    if not row:
        raise KeyError("совет не найден")
    names = ("id", "speaker", "privacy", "text", "premises", "breakers", "free_premises",
             "nox_conf", "status", "history", "src_kind", "t_event", "t_learned", "created", "updated")
    out = dict(zip(names, row))
    for key in ("premises", "breakers", "free_premises", "history"):
        out[key] = _json(out[key], [])
    return out


def record_advice(store, text, premises, speaker="owner", breakers=None, free_premises=None,
                  nox_conf=None, src_kind="nox_generated", t_event=None, t_learned=None,
                  clock=time.time, journal=None):
    """Store private advice with validated, ref+SHA S03 premises.

    Each premise must be a mapping with ref. sha/text, if supplied, are checked
    against the current S03 record; the persisted snippet is always read from S03.
    """
    ensure_schema(store)
    text = _check_text(text, "совет")
    speaker = str(speaker)
    if speaker not in SPEAKERS:
        raise ValueError("speaker должен быть owner или nox")
    if src_kind not in SRC_KINDS:
        raise ValueError("неизвестный src_kind")
    premises = list(premises or [])
    for item in free_premises or []:
        if not isinstance(item, dict) or not item.get("ref"):
            raise ValueError("свободная посылка должна иметь ref+SHA; текст без источника запрещён")
        premises.append(item)
    if not premises:
        raise ValueError("нужна хотя бы одна адресуемая посылка ref+sha")
    checked = []
    seen = set()
    for item in premises:
        if not isinstance(item, dict) or not item.get("ref"):
            raise ValueError("посылка должна содержать ref")
        ref = str(item["ref"])
        if ref in seen:
            continue
        seen.add(ref)
        current_text, status = _source(store, ref)
        if current_text is None or status != "active":
            raise ValueError("посылка %s недоступна или отозвана" % ref)
        if speaker == "owner" and not _owner_source_ok(store, ref):
            raise ValueError("посылка %s не имеет подтверждённого owner_* происхождения" % ref)
        current_text = _check_text(str(current_text), "посылка")
        current_sha = _sha(current_text)
        supplied_sha = item.get("sha")
        if supplied_sha is not None and str(supplied_sha).lower() != current_sha:
            raise ValueError("SHA посылки %s устарел" % ref)
        supplied_text = item.get("text")
        if supplied_text is not None and supplied_text != current_text:
            raise ValueError("текст посылки %s не совпадает с S03" % ref)
        checked.append({"ref": ref, "sha": current_sha, "text": current_text})
    safe_breakers = [_check_text(str(x), "условие пересмотра") for x in (breakers or [])]
    # Legacy column remains empty for schema compatibility. All evidence is stored
    # in premises as ref+SHA records.
    safe_free = []
    now = float(clock())
    ev = now if t_event is None else float(t_event)
    learned = now if t_learned is None else float(t_learned)
    history = [{"ts": now, "action": "created", "src_kind": src_kind,
                "premise_refs": [p["ref"] for p in checked]}]
    cur = store.db.execute(
        "INSERT INTO zm_advice(speaker,privacy,text,premises,breakers,free_premises,nox_conf,status,history,"
        "src_kind,t_event,t_learned,created,updated) VALUES(?,?,?,?,?,?,?,'live',?,?,?,?,?,?)",
        (speaker, PRIVACY, text, json.dumps(checked, ensure_ascii=False, sort_keys=True),
         json.dumps(safe_breakers, ensure_ascii=False), json.dumps(safe_free, ensure_ascii=False),
         nox_conf, json.dumps(history, ensure_ascii=False), src_kind, ev, learned, now, now),
    )
    advice_id = int(cur.lastrowid)
    commit(store)
    journal_status = _journal_event(store, journal, clock, "Создан совет с адресуемыми основаниями",
                                    {"advice_id": advice_id, "speaker": speaker,
                                     "premises": [{"ref": p["ref"], "sha": p["sha"]} for p in checked]})
    return {"id": advice_id, "journaled": journal_status["ok"],
            "journal_error": journal_status["error"]}


def _stale_reason(store, premise, created):
    ref = premise["ref"]
    current_text, status = _source(store, ref)
    if current_text is None or status != "active":
        return {"reason": "missing_or_inactive", "ref": ref,
                "expected_sha": premise["sha"], "current_sha": None}
    current_sha = _sha(str(current_text))
    if current_sha != premise["sha"]:
        return {"reason": "sha_changed", "ref": ref,
                "expected_sha": premise["sha"], "current_sha": current_sha}
    try:
        correction = store.db.execute(
            "SELECT op FROM mem_corrections WHERE ref=? AND ts>? AND verified=1 "
            "AND op IN ('correct','revoke','delete','restore') ORDER BY id LIMIT 1",
            (ref, float(created)),
        ).fetchone()
    except Exception:
        correction = None
    if correction:
        return {"reason": "memory_correction", "ref": ref, "operation": correction[0],
                "expected_sha": premise["sha"], "current_sha": current_sha}
    try:
        revoked = store.db.execute(
            "SELECT 1 FROM mem_revoked WHERE ref=? AND active=1 LIMIT 1", (ref,)
        ).fetchone()
    except Exception:
        revoked = None
    if revoked:
        return {"reason": "memory_revoked", "ref": ref,
                "expected_sha": premise["sha"], "current_sha": current_sha}
    return None


def refresh_stale_advice(store, speaker="owner", ref=None, clock=time.time, journal=None):
    """Mark live advice stale after S03 edits, revocations, or source disappearance."""
    ensure_schema(store)
    rows = store.db.execute(
        "SELECT id,text,premises,history,created FROM zm_advice WHERE speaker=? AND status='live' ORDER BY id",
        (str(speaker),),
    ).fetchall()
    changed = []
    for advice_id, text, premises_raw, history_raw, created in rows:
        premises = _json(premises_raw, [])
        if ref is not None and not any(p.get("ref") == str(ref) for p in premises):
            continue
        reason = next((r for p in premises if (r := _stale_reason(store, p, created))), None)
        if not reason:
            continue
        history = _json(history_raw, [])
        event = {"ts": float(clock()), "action": "marked_stale", **reason}
        history.append(event)
        store.db.execute("UPDATE zm_advice SET status='stale',history=?,updated=? WHERE id=? AND status='live'",
                         (json.dumps(history, ensure_ascii=False), event["ts"], advice_id))
        changed.append({"id": int(advice_id), "reason": reason})
    if changed:
        commit(store)
        journal_failures = []
        for item in changed:
            result = _journal_event(store, journal, clock, "Совет устарел после изменения основания",
                                    {"advice_id": item["id"], "speaker": str(speaker), **item["reason"]})
            if not result["ok"]:
                journal_failures.append({"advice_id": item["id"], "error": result["error"]})
    else:
        journal_failures = []
    return {"checked": len(rows), "stale": changed, "journal_failures": journal_failures}


def explain_advice(store, advice_id, speaker="owner"):
    """Build explanation only from persisted advice and its cited S03 snippets."""
    ensure_schema(store)
    item = _get_advice(store, advice_id, speaker)
    cite = "zm:advice:%d" % item["id"]
    lines = ["Совет: «%s» [%s]." % (item["text"], cite)]
    for premise in item["premises"]:
        lines.append("Основание: «%s» [%s@%s]." %
                     (premise["text"], premise["ref"], premise["sha"]))
    if item["status"] == "stale":
        stale = next((h for h in reversed(item["history"]) if h.get("action") == "marked_stale"), None)
        if stale:
            lines.append("Основание изменилось или отозвано: %s [%s]." % (stale["ref"], cite))
    return {"id": cite, "speaker": item["speaker"], "privacy": item["privacy"],
            "text": item["text"], "status": item["status"], "premises": item["premises"],
            "history": item["history"], "lines": lines}


def counterfactual_premises(store, advice_id, ref, alternative_text, explicit=False, speaker="owner"):
    """Return cited premise copy for a caller-requested counterfactual; performs no GLM call."""
    if not explicit:
        raise ValueError("контрфакт доступен только по явному запросу")
    ensure_schema(store)
    item = _get_advice(store, advice_id, speaker)
    alternative_text = _check_text(alternative_text, "альтернативный факт")
    ref = str(ref)
    matches = [p for p in item["premises"] if p["ref"] == ref]
    if len(matches) != 1:
        raise KeyError("посылка не найдена")
    before = item["premises"]
    after = [dict(p) for p in before]
    index = next(i for i, p in enumerate(after) if p["ref"] == ref)
    after[index] = {"ref": ref, "sha": _sha(alternative_text), "text": alternative_text,
                    "counterfactual": True}
    return {"advice_id": item["id"], "replaced_ref": ref,
            "before": before, "after": after, "citation": "zm:advice:%d" % item["id"],
            "note": "Подстановка посылки; новый вывод здесь не сгенерирован."}

