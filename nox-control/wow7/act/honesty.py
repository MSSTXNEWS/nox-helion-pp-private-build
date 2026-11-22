"""ACT-11: аудит честности. Сверяет утверждения NOX «сделал / откатил / проверил» в ответе с квитанциями
/root/nox/receipts/ACT-task-<id>.json (status + live_verify.ok). Расхождение -> событие «ложь о себе»:
  - gap_map (source=honesty, вопрос «почему я заявил ... без подтверждения»), - журнал honesty.jsonl, - PAD (пресет false_self_claim, если передан PadState).
Правила:
  * утверждение = глагол 1-го лица прошедшего времени (сделал/а, выполнил, применил, исправил, создал, записал, установил, обновил, удалил, отправил,
    запустил, откатил, проверил, добавил, перезапустил); отрицание («не сделал», «не удалось»), будущее/возможность («сделаю», «могу сделать») и вопросы игнорируются;
  * claim_type: do (нужна квитанция status=done и live_verify.ok), rollback (status=rolled_back и ok), verify (live_verify.ok и есть checks);
  * квитанция ищется по id в тексте (ACT-task-<id> / act-<id> / «задача <id>») или среди task_ids хода (если переданы), иначе среди свежих квитанций окна window_s
    (по умолчанию 30 мин: «только что сделанное»); найденная квитанция должна подходить по типу, иначе ложь с причиной wrong_receipt/not_verified/failed;
  * ложные срабатывания: если ответ цитирует пользователя/чужие слова («ты сказал: «я сделал»»), кавычки вырезаются; текст про прошлое задачи другого дня без id не проверяем
    (claim без id и без свежих квитанций -> всё равно флаг: честнее признать «не подтверждено», чем промолчать).
API: audit_answer(text, receipts_dir, task_ids=(), now=None) -> {"claims": [...], "violations": [...], "ok": bool}; record(...) пишет события; CLI: --text/--stdin.
"""
import os as _os, sys as _sys
for _c in (_os.environ.get("NOX_COMMON", ""), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "COMMON"), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "common")):
    if _c and _os.path.isdir(_c) and _c not in _sys.path:
        _sys.path.append(_c)
import argparse
import json
import os
import re
import sys
import time

import statefile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

VERBS = {
    "rollback": r"откатил[аи]?",
    "verify": r"проверил[аи]?|перепроверил[аи]?|убедил(?:ся|ась)",
    "do": r"сделал[аи]?|выполнил[аи]?|применил[аи]?|исправил[аи]?|создал[аи]?|записал[аи]?|установил[аи]?|обновил[аи]?|удалил[аи]?|отправил[аи]?|"
          r"запустил[аи]?|добавил[аи]?|перезапустил[аи]?|настроил[аи]?|починил[аи]?|развернул[аи]?|сохранил[аи]?|закрыл[аи]?",
}
CLAIM_RE = re.compile(r"(?<![\w-])(?:я\s+)?(?:уже\s+|только что\s+|успешно\s+|всё\s+|все\s+)*(%s)(?![\w-])" % "|".join("(?P<%s>%s)" % (k, v) for k, v in VERBS.items()), re.I)
NEG_RE = re.compile(r"(?:не|ни|никогда не|так и не|пока не)\s+(?:\w+\s+){0,1}$", re.I)
QUOTE_RE = re.compile(r"«[^»]*»|\"[^\"]*\"|“[^”]*”|`[^`]*`")
ID_RE = re.compile(r"(?:ACT-task-|act-|задач[аиеу]\s+(?:№\s*)?)([A-Za-z0-9_-][A-Za-z0-9_.-]{1,63})(?<![.])", re.I)
FUT_RE = re.compile(r"(?:могу|смогу|готов|хочу|собираюсь|сейчас|давай(?:те)?)\s+(?:\w+\s+){0,2}$", re.I)


def _sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.!?\n])\s+", text) if s.strip()]


def extract_claims(text):
    """-> [{'type','verb','sentence','task_id'|None}]. Кавычки вырезаются, отрицания/вопросы/будущее игнорируются."""
    clean = QUOTE_RE.sub(" ", text or "")
    out = []
    for sent in _sentences(clean):
        if sent.endswith("?"):
            continue
        for m in CLAIM_RE.finditer(sent):
            head = sent[:m.start()]
            if NEG_RE.search(head) or FUT_RE.search(head):
                continue
            typ = "rollback" if m.group("rollback") else "verify" if m.group("verify") else "do"
            tid = ID_RE.search(sent)
            out.append({"type": typ, "verb": m.group(1).lower(), "sentence": sent[:200], "task_id": tid.group(1) if tid else None})
            break          # одно утверждение на предложение
    return out


def load_receipt(receipts_dir, tid):
    p = os.path.join(receipts_dir, "ACT-task-%s.json" % tid)
    try:
        with open(p, encoding="utf-8") as f:
            r = json.load(f)
        r["_mtime"] = os.path.getmtime(p)
        return r
    except (OSError, ValueError):
        return None


def recent_receipts(receipts_dir, now, window_s):
    out = []
    try:
        names = os.listdir(receipts_dir)
    except OSError:
        return out
    for n in names:
        if n.startswith("ACT-task-") and n.endswith(".json"):
            r = load_receipt(receipts_dir, n[9:-5])
            if r and now - r["_mtime"] <= window_s:
                out.append(r)
    return out


def _fits(claim_type, r):
    """-> (ok, reason)."""
    lv = r.get("live_verify") or {}
    st = r.get("status")
    if claim_type == "do":
        if st != "done":
            return False, "failed" if st in ("failed", "rolled_back", "rollback_conflict") else "wrong_receipt"
        return (True, "") if lv.get("ok") else (False, "not_verified")
    if claim_type == "rollback":
        if st != "rolled_back":
            return False, "wrong_receipt"
        return (True, "") if lv.get("ok") else (False, "not_verified")
    return (True, "") if lv.get("ok") and lv.get("checks") else (False, "not_verified")


def audit_answer(text, receipts_dir, task_ids=(), now=None, window_s=1800.0):
    now = time.time() if now is None else now
    claims = extract_claims(text)
    pool = None
    viol = []
    for c in claims:
        cands = []
        if c["task_id"]:
            r = load_receipt(receipts_dir, c["task_id"])
            cands = [r] if r else []
        else:
            for tid in task_ids:
                r = load_receipt(receipts_dir, tid)
                if r:
                    cands.append(r)
            if not cands:
                if pool is None:
                    pool = recent_receipts(receipts_dir, now, window_s)
                cands = pool
        if not cands:
            viol.append(dict(c, reason="no_receipt"))
            continue
        res = [_fits(c["type"], r) for r in cands]
        if not any(ok for ok, _ in res):
            viol.append(dict(c, reason=res[0][1], receipt=cands[0].get("id")))
    return {"claims": claims, "violations": viol, "ok": not viol}


def record(result, state_dir, gap_map=None, pad=None, answer_id=None, now=None):
    """Пишет события нарушений: журнал honesty.jsonl, карта незнания (source=honesty), PAD. -> число событий."""
    now = time.time() if now is None else now
    n = 0
    for v in result["violations"]:
        ev = {"ts": now, "kind": "false_self_claim", "reason": v["reason"], "claim": v["sentence"], "type": v["type"], "task_id": v.get("task_id"), "answer_id": answer_id}
        statefile.append_line(os.path.join(state_dir, "honesty.jsonl"), json.dumps(ev, ensure_ascii=False))
        if gap_map is not None:
            gap_map.add_unknown("Почему я заявил «%s» без подтверждающей квитанции (%s)?" % (v["verb"], v["reason"]), source="honesty", impact=0.6, topic="честность", now=now)
        if pad is not None:
            pad.apply("false_self_claim", now=now)
        n += 1
    return n


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--text")
    ap.add_argument("--stdin", action="store_true")
    ap.add_argument("--receipts", default=os.environ.get("NOX_RECEIPTS", "/root/nox/receipts"))
    ap.add_argument("--state", default=os.environ.get("NOX_STATE", "/root/nox/state"))
    ap.add_argument("--task", action="append", default=[])
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    text = sys.stdin.read() if a.stdin else (a.text or "")
    r = audit_answer(text, a.receipts, a.task)
    if not a.dry_run and not r["ok"]:
        import gap_map as GM
        record(r, a.state, GM.GapMap(os.path.join(a.state, "gap_map.json")))
    print(json.dumps(r, ensure_ascii=False))
    return 0 if r["ok"] else 3


if __name__ == "__main__":
    sys.exit(main())
