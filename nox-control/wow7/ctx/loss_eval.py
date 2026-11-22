"""loss_eval: измерение потерь от сжатия - QA до/после (полный контекст | сжатый | сжатый+разворот по запросу).

Вопросы: свои (JSONL {q, gold, kind}) или авто-cloze из оригинала: предложение с жёстким фактом, факт замаскирован.
Ридер (LLM) отвечает ТОЛЬКО по контексту. Приёмка: acc(сжатый) >= acc(полный) - tol. Плюс статическая метрика
fact_retention (без LLM): доля жёстких фактов оригинала, присутствующих в сжатом тексте.
"""
import argparse
import json
import re
import sys

from ctxcommon import HARD, RE_SENT, check_facts, estimate_tokens, extract_facts, norm_number, stems_of

READER_SYS = "Отвечай ТОЛЬКО по приведённому контексту, одним коротким значением. Если в контексте этого нет - ответь «нет данных»."


def auto_qa(turns, max_items=40):
    """Cloze по каждому жёсткому факту каждого предложения; при избытке - равномерная выборка по всей беседе."""
    items = []
    for t in turns:
        for s in [x.strip() for x in RE_SENT.split(t["content"]) if x.strip()]:
            if len(s) > 300:
                continue
            for f in extract_facts(s):
                if f["kind"] in HARD and f["text"] in s and len(s) > len(f["text"]) + 8:
                    items.append({"q": "В беседе было сказано: «%s». Что стоит на месте ___ ?" % s.replace(f["text"], "___", 1),
                                  "gold": f["text"], "kind": f["kind"], "turn": t["id"]})
    if len(items) > max_items:
        step = len(items) / max_items
        items = [items[int(i * step)] for i in range(max_items)]
    return items


def judge(answer, item):
    a = (answer or "").strip()
    g = item["gold"]
    if item.get("kind") == "number":
        keys = {x["key"] for x in extract_facts(a) if x["kind"] == "number"} | {norm_number(m) for m in re.findall(r"\d[\d  .,]*\d|\d", a)}
        return norm_number(g) in keys
    if item.get("kind") == "decision":
        need = stems_of(g)
        return bool(need) and len(need & stems_of(a)) / len(need) >= 0.6
    return g.lower() in a.lower()


def render_turns(turns):
    return "\n".join("%s: %s" % ("мессир" if t["role"] == "user" else "NOX", t["content"]) for t in turns)


def ask(reader, context, q):
    return reader([{"role": "system", "content": READER_SYS}, {"role": "user", "content": "Контекст:\n%s\n\nВопрос: %s" % (context, q)}], 60)


def evaluate(cm, items, reader, tol=0.02):
    """cm - ContextManager с уже выполненным сворачиванием. reader(messages,max_tokens)->str."""
    all_turns = cm.store.after(0)
    full = render_turns(all_turns)
    comp = (cm.digest_text() + "\n" + render_turns(cm.l1_turns())).strip()
    rows, arms = [], {"full": 0, "compressed": 0, "compressed+expand": 0}
    for it in items:
        ctx_exp = comp + "\n" + cm.expand(query=it["q"])["text"]
        r = {"q": it["q"], "kind": it.get("kind"), "gold": it["gold"]}
        r["full"] = judge(ask(reader, full, it["q"]), it)
        r["compressed"] = judge(ask(reader, comp, it["q"]), it)
        r["compressed+expand"] = judge(ask(reader, ctx_exp, it["q"]), it)
        for k in arms:
            arms[k] += r[k]
        rows.append(r)
    n = max(1, len(rows))
    acc = {k: round(v / n, 4) for k, v in arms.items()}
    orig_facts = [f for t in all_turns for f in extract_facts(t["content"])]
    chk = check_facts([f for f in orig_facts if f["kind"] in HARD], comp, 0.0)
    return {"n": len(rows), "acc": acc, "delta_compressed": round(acc["compressed"] - acc["full"], 4),
            "delta_expand": round(acc["compressed+expand"] - acc["full"], 4),
            "lost": [r["q"][:120] for r in rows if r["full"] and not r["compressed"]],
            "rescued_by_expand": [r["q"][:120] for r in rows if not r["compressed"] and r["compressed+expand"]],
            "tokens": {"full": estimate_tokens(full), "compressed": estimate_tokens(comp)},
            "ratio": round(estimate_tokens(comp) / max(1, estimate_tokens(full)), 3),
            "fact_retention_static": round(chk["hard_cov"], 4), "missing_static": [f["text"] for f in chk["missing_hard"]][:20],
            "tol": tol, "pass": acc["compressed"] >= acc["full"] - tol and chk["hard_cov"] >= 1.0 - 1e-9}


def main(argv=None):
    from context_manager import ContextManager, TurnStore
    from ctxcommon import http_llm
    from summarizer import Summarizer
    ap = argparse.ArgumentParser(description="CTX loss_eval: QA до/после сжатия")
    ap.add_argument("--db", required=True)
    ap.add_argument("--state", required=True)
    ap.add_argument("--soul", required=True)
    ap.add_argument("--llm-url", default="http://127.0.0.1:8083")
    ap.add_argument("--qa", default="auto")
    ap.add_argument("--max-items", type=int, default=40)
    ap.add_argument("--tol", type=float, default=0.02)
    a = ap.parse_args(argv)
    llm = http_llm(a.llm_url)
    cm = ContextManager(open(a.soul, encoding="utf-8").read(), TurnStore(a.db), Summarizer(llm), state_path=a.state)
    items = auto_qa(cm.store.after(0), a.max_items) if a.qa == "auto" else [json.loads(l) for l in open(a.qa, encoding="utf-8") if l.strip()]
    rep = evaluate(cm, items, llm, a.tol)
    print(json.dumps(rep, ensure_ascii=False, indent=1))
    return 0 if rep["pass"] else 2


if __name__ == "__main__":
    sys.exit(main())
