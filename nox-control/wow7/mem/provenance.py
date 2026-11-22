"""provenance: «какие воспоминания вошли в ответ и откуда они».

qs6/recall_api.Recall уже пишет mem_usage (turn_id, ref, via, score, query). Здесь поверх этого:
  - snapshot_turn(): слепок ТЕКСТА на момент ответа (mem_usage_snap) - после правки/отзыва видно, что именно
    лежало в контексте тогда и изменилось ли с тех пор;
  - explain_item(): происхождение записи: свидетельства лестницы Riverse (источник, вид, знак, время), история
    уровней, журнал правок владельца, эпизоды-источники (та же сессия, пересечение слов);
  - explain_turn(): весь ход; различает «лежало в контексте» и «вероятно отражено в тексте ответа» (эвристика
    по пересечению основ слов, честно помечена как эвристика, не как доказательство);
  - render_ru(): текст для мессира; без выдумок - только то, что есть в S03.
"""
import hashlib
import json
import time

from memcommon import commit as _commit, ensure_schema, stems

REPLY_OVERLAP = 0.5    # доля значимых основ записи, найденных в ответе, чтобы счесть «вероятно использовано»
ORIGIN_OVERLAP = 0.6   # доля основ факта в эпизоде-кандидате в источники
VIA_RU = {"core": "ядро (всегда в контексте)", "search": "найдено поиском"}


def _sha(t):
    return hashlib.sha256((t or "").encode("utf-8")).hexdigest()[:16]


def recall_with_provenance(recall, query, turn_id=None, **kw):
    """Recall.recall_for_reply + слепок. Использовать вместо прямого вызова в memory_layer.prepare."""
    ensure_schema(recall.s)
    out = recall.recall_for_reply(query, turn_id=turn_id, **kw)
    snapshot_turn(recall.s, out["turn_id"])
    return out


def install_hook(recall):
    """Подменить recall.recall_for_reply так, чтобы КАЖДЫЙ ход (memory_layer.prepare) оставлял слепок. Идемпотентно."""
    if getattr(recall, "_prov_hooked", False):
        return recall
    orig = recall.recall_for_reply

    def hooked(query, turn_id=None, **kw):
        out = orig(query, turn_id=turn_id, **kw)
        snapshot_turn(recall.s, out["turn_id"])
        return out
    recall.recall_for_reply = hooked
    recall._prov_hooked = True
    return recall


def snapshot_turn(store, turn_id, ts=None):
    """Сохранить текст/уровень/источник каждой записи хода (идемпотентно, первое значение не затирается)."""
    ensure_schema(store)
    n = 0
    for ref, via in store.db.execute("SELECT ref,via FROM mem_usage WHERE turn_id=? ORDER BY id", (turn_id,)).fetchall():
        rec = store.get(ref)
        if rec is None:
            continue
        text = store.text_of(rec)
        level = rec.get("level") if rec["type"] == "fact" else None
        cur = store.db.execute("INSERT OR IGNORE INTO mem_usage_snap(turn_id,ref,via,text,text_sha,level,source,ts) "
                               "VALUES(?,?,?,?,?,?,?,?)", (turn_id, ref, via, text, _sha(text), level, rec.get("source"),
                                                          ts or time.time()))
        n += cur.rowcount
    _commit(store)
    return n


def _evidence(store, ladder_id):
    if not ladder_id:
        return [], []
    ev = [{"source": s, "kind": k, "polarity": p, "ts": t} for s, k, p, t in store.db.execute(
        "SELECT source,kind,polarity,ts FROM evidence WHERE fact_id=? ORDER BY ts", (ladder_id,))]
    tr = [{"from": a, "to": b, "reason": r, "ts": t} for a, b, r, t in store.db.execute(
        "SELECT from_level,to_level,reason,ts FROM transitions WHERE fact_id=? ORDER BY id", (ladder_id,))]
    return ev, tr


def _origin_episodes(store, fact_text, source, limit=3):
    """Эпизоды, из которых мог прийти факт: сессия из source 'chat:<сессия>' + пересечение основ."""
    want = set(stems(fact_text))
    if not want:
        return []
    sess = source.split(":", 1)[1] if source and source.startswith("chat:") else None
    q, a = "SELECT id,ts,role,text FROM mem_episodes WHERE status='active' AND role='user'", []
    if sess:
        q += " AND session=?"
        a.append(sess)
    out = []
    for i, ts, role, text in store.db.execute(q + " ORDER BY id DESC LIMIT 2000", a):
        have = set(stems(text))
        ov = len(want & have) / len(want)
        if ov >= ORIGIN_OVERLAP:
            out.append({"ref": "e:%d" % i, "ts": ts, "role": role, "overlap": round(ov, 2), "quote": text[:160]})
    out.sort(key=lambda x: -x["overlap"])
    return out[:limit]


def explain_item(store, ref):
    """Происхождение одной записи. Работает и для отозванных (status!=active) - для разбора."""
    ensure_schema(store)
    rec = store.get(ref)
    if rec is None:
        return {"ref": ref, "available": False, "note": "записи нет в S03"}
    text = store.text_of(rec)
    out = {"ref": ref, "type": rec["type"], "text": text, "status": rec.get("status", "active"), "available": True,
           "source": rec.get("source")}
    if rec["type"] == "fact":
        ev, tr = _evidence(store, rec["ladder_id"])
        out.update(level=rec["level"], level_name=rec["level_name"], kind=rec["kind"], pinned=bool(rec["pinned"]),
                   owner_confirmed=bool(rec["owner_confirmed"]), created=rec["created"], updated=rec["updated"],
                   access_count=rec["access_count"], evidence=ev, level_history=tr,
                   origin_episodes=_origin_episodes(store, text, rec.get("source")))
    elif rec["type"] == "episode":
        out.update(created=rec["ts"], session=rec["session"], role=rec["role"])
    else:
        out.update(created=rec["updated"], section=rec["section"])
    out["journal"] = [{"id": i, "ts": ts, "actor": a, "action": ac, "old": o, "new": n, "reason": r} for i, ts, a, ac, o, n, r in
                      store.db.execute("SELECT id,ts,actor,action,old,new,reason FROM mem_changes WHERE ref=? ORDER BY id", (ref,))]
    return out


def reply_overlap(text, reply):
    want = set(stems(text))
    if not want or not reply:
        return 0.0
    return len(want & set(stems(reply))) / len(want)


def explain_turn(store, turn_id, reply_text=None):
    """-> {turn_id, items:[...], in_context, probably_in_reply}. Порядок: как попали в контекст."""
    ensure_schema(store)
    rows = store.db.execute("SELECT ref,via,score,query,ts FROM mem_usage WHERE turn_id=? ORDER BY id", (turn_id,)).fetchall()
    snaps = {r[0]: r[1:] for r in store.db.execute("SELECT ref,text,text_sha,level FROM mem_usage_snap WHERE turn_id=?", (turn_id,))}
    items, seen = [], set()
    for ref, via, score, query, ts in rows:
        if ref in seen:
            continue
        seen.add(ref)
        it = explain_item(store, ref)
        it.update(via=via, via_ru=VIA_RU.get(via, via), score=score, query=query, used_at=ts)
        snap = snaps.get(ref)
        if snap:
            it["text_at_use"] = snap[0]
            it["changed_since"] = (snap[1] != _sha(it.get("text"))) if it.get("available") else True
        else:
            it["text_at_use"], it["changed_since"] = None, None
        if it.get("status", "active") != "active":
            it["revoked"] = True
        if reply_text is not None:
            ov = reply_overlap(it.get("text_at_use") or it.get("text") or "", reply_text)
            it["reply_overlap"] = round(ov, 2)
            it["probably_in_reply"] = ov >= REPLY_OVERLAP
        items.append(it)
    return {"turn_id": turn_id, "items": items, "in_context": len(items),
            "probably_in_reply": sum(1 for i in items if i.get("probably_in_reply")),
            "basis": "in_context - точные данные mem_usage; probably_in_reply - эвристика по пересечению слов"}


def _fmt_ts(ts):
    return time.strftime("%Y-%m-%d %H:%M", time.gmtime(ts + 3 * 3600)) if ts else "?"


def render_ru(expl):
    """Человекочитаемое объяснение хода."""
    if not expl["items"]:
        return "В этот ход ничего из памяти не попало."
    lines = ["В ход %s в контекст вошло записей: %d." % (expl["turn_id"], expl["in_context"])]
    for it in expl["items"]:
        if not it.get("available"):
            lines.append("- %s: записи уже нет в S03." % it["ref"])
            continue
        txt = (it.get("text_at_use") or it["text"])[:140]
        bits = ["«%s»" % txt, it["via_ru"]]
        if it["type"] == "fact":
            bits.append("уровень: %s" % it["level_name"])
            if it["owner_confirmed"]:
                bits.append("подтверждено мессиром")
            if it.get("source"):
                bits.append("источник: %s" % it["source"])
            bits.append("свидетельств: %d" % sum(1 for e in it["evidence"] if e["polarity"] > 0))
        elif it.get("source"):
            bits.append("источник: %s" % it["source"])
        if it.get("revoked"):
            bits.append("ОТОЗВАНО с тех пор")
        elif it.get("changed_since"):
            bits.append("ИЗМЕНЕНО с тех пор (сейчас: «%s»)" % it["text"][:80])
        edits = [j for j in it["journal"] if j["action"] in ("correct", "delete", "confirm")]
        if edits:
            bits.append("правок владельца: %d" % len(edits))
        if "probably_in_reply" in it:
            bits.append("вероятно отражено в ответе" if it["probably_in_reply"] else "в тексте ответа не заметно")
        lines.append("- " + "; ".join(bits))
    return "\n".join(lines)
