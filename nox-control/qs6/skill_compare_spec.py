#!/usr/bin/env python3
"""Навык «Сравни файл с ТЗ»: сверяет текст/Markdown/JSON-файл со списком требований.

Как работает (без нейросети, правила явные):
 1. Из ТЗ (Markdown/текст/JSON) берутся пункты: нумерованные, маркированные, «ТЗ-01:», строки таблицы,
    при отсутствии списка - предложения со словами «должен/необходимо/нужно/...».
 2. В каждом пункте выделяются признаки: СИЛЬНЫЕ (кавычки, `код`, идентификаторы, числа, ЗАГЛАВНЫЕ
    сокращения) и СЛАБЫЕ (значимые слова, сравниваются по основе слова).
 3. Файл режется на единицы: строки Markdown/текста и окна по 3 строки; для JSON - листья и объекты (путь вида a.b[0]).
 4. Уверенность = 0.6 * лучшая единица + 0.4 * покрытие по всему файлу; если сильный признак нигде не найден,
    «найдено» невозможно (потолок 0.69). Пороги: >= 0.75 да, >= 0.4 частично, иначе нет.
Ограничения: сопоставление по словам, а не по смыслу; запреты («не должен») и качество реализации не проверяются
(такие пункты помечаются для ручной проверки). Это помощник проверки, не доказательство соответствия.
Запуск: python3 skill_compare_spec.py ТЗ.md файл.(md|txt|json) [--json] [--strict]
"""
import argparse
import json
import os
import re
import sys

FOUND_T, PARTIAL_T = 0.75, 0.4
FILLER = set("должен должна должно должны необходимо нужно требуется реализовать обеспечить система системой модуль "
             "также может быть которые который которая этого этом своих должна быть когда чтобы если после перед "
             "через между только можно нельзя пункт требование файл файле файла документ работать работает выполнять "
             "описание описанием упоминать содержать содержит раздел разделе секция заголовок".split())
NEG_RE = re.compile(r"\bне\s+(должен|должна|должно|должны|допускается|разрешается|следует|нужно)|запрещ|нельзя|\bбез\s", re.I)
ITEM_RE = re.compile(r"^\s*(?:(?P<num>\d+(?:\.\d+)*[.)]?)|(?P<id>(?:ТЗ|REQ|FR|NFR|R|T)[-_ ]?\d+[:.)]?)|(?P<bul>[-*+•](?:\s+\[[ xX]\])?))\s+(?P<text>\S.*)$", re.I)
NEED_RE = re.compile(r"должн|необходимо|нужно|требуется|обязан|следует|must|shall", re.I)
STRUCT_HEAD_RE = re.compile(r"раздел|заголов|секци|глав", re.I)
STRUCT_KEY_RE = re.compile(r"\bполе\b|\bполя\b|\bключ", re.I)


def stem(w):
    w = w.casefold()
    return w if len(w) <= 4 else w[:max(4, min(len(w) - 2, 6))]


FILLER_STEMS = {stem(w) for w in FILLER}


# ---------- ТЗ ----------
def parse_spec(text):
    """-> [{"id","text","line"}]"""
    s = text.strip()
    if s[:1] in "[{":
        try:
            return _spec_from_json(json.loads(s))
        except ValueError:
            pass
    items, cur = [], None
    for n, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            cur = None
            continue
        if re.match(r"^\s{0,3}#{1,6}\s", line) or re.match(r"^\s*\|?\s*:?-{3,}", line):
            cur = None
            continue
        if line.lstrip().startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|") if c.strip()]
            if len(cells) >= 2 or cells:
                body = max(cells, key=len)
                if not re.fullmatch(r"(№|#|id|требование|описание|пункт)", body, re.I) and len(cells) >= 1:
                    ident = cells[0] if len(cells) > 1 and len(cells[0]) <= 12 else str(len(items) + 1)
                    items.append({"id": ident, "text": body, "line": n}); cur = None
            continue
        m = ITEM_RE.match(line)
        if m and not (m.group("num") and re.fullmatch(r"\d{4}", m.group("num").rstrip(".)"))):
            ident = (m.group("num") or m.group("id") or "").rstrip(".):") or str(len(items) + 1)
            cur = {"id": ident, "text": m.group("text").strip(), "line": n}
            items.append(cur)
        elif cur is not None and line.startswith((" ", "\t")):
            cur["text"] += " " + line.strip()
    if items:
        return items
    # нет списка: предложения-требования
    out = []
    for n, line in enumerate(text.splitlines(), 1):
        for sent in re.split(r"(?<=[.!?])\s+", line.strip()):
            if sent and NEED_RE.search(sent):
                out.append({"id": str(len(out) + 1), "text": sent, "line": n})
    if out:
        return out
    return [{"id": str(i + 1), "text": l.strip(), "line": i + 1} for i, l in enumerate(text.splitlines())
            if l.strip() and not l.lstrip().startswith("#")]


def _spec_from_json(d):
    if isinstance(d, dict):
        for k in ("requirements", "items", "требования", "tz", "spec"):
            if isinstance(d.get(k), list):
                d = d[k]
                break
        else:
            d = [{"id": k, "text": v} for k, v in d.items() if isinstance(v, str)]
    out = []
    for i, it in enumerate(d, 1):
        if isinstance(it, str):
            out.append({"id": str(i), "text": it, "line": i})
        elif isinstance(it, dict):
            t = next((it[k] for k in ("text", "requirement", "description", "title", "требование") if isinstance(it.get(k), str)), None)
            if t:
                out.append({"id": str(it.get("id", i)), "text": t, "line": i})
    return out


# ---------- признаки ----------
def tokens(req):
    """-> (strong, weak): списки строк."""
    strong, rest = [], req
    for rx in (r"`([^`]+)`", r"«([^»]+)»", r"\"([^\"]+)\""):
        for m in re.finditer(rx, rest):
            strong.append(m.group(1).strip())
        rest = re.sub(rx, " ", rest)
    for m in re.finditer(r"[\w./\\-]*[A-Za-z_][\w./\\-]*[_./][\w./\\-]+|\b[A-Z][a-z]+[A-Z]\w*\b|\b[A-ZА-Я0-9]{2,}\d*\b", rest):
        t = m.group(0).strip(".,;:")
        if t:
            strong.append(t)
    for m in re.finditer(r"\d+(?:[.,]\d+)?", rest):
        strong.append(m.group(0))
    seen, st = set(), []
    for t in strong:
        k = t.casefold()
        if k and k not in seen:
            seen.add(k); st.append(t)
    weak, ws = [], set()
    for w in re.findall(r"[^\W\d_]{5,}", rest, re.U):
        sw = stem(w)
        if w.casefold() in FILLER or sw in FILLER_STEMS:
            continue
        if sw not in ws and not any(sw in s.casefold() for s in st):
            ws.add(sw); weak.append(sw)
    return st, weak[:10]


# ---------- файл ----------
class Unit:
    __slots__ = ("text", "where", "heading", "words", "low")

    def __init__(self, text, where, heading=""):
        self.text, self.where, self.heading = text, where, heading
        self.low = text.casefold()
        self.words = re.findall(r"[^\W_]+", self.low, re.U)


def units_from_text(text):
    lines, units, head = text.splitlines(), [], ""
    heads = []   # (номер строки, название)
    for i, l in enumerate(lines, 1):
        m = re.match(r"^\s{0,3}#{1,6}\s+(.*\S)\s*$", l)
        if m:
            head = m.group(1)
            heads.append((i, head))
        if l.strip():
            units.append(Unit(l, "строка %d" % i + (" (раздел «%s»)" % head if head else ""), head))
    for i in range(len(lines) - 2):
        w = "\n".join(lines[i:i + 3])
        if w.strip():
            units.append(Unit(w, "строки %d-%d" % (i + 1, i + 3)))
    return units, [h for _, h in heads], False


def _flatten(o, path, units, keys):
    if isinstance(o, dict):
        scal = []
        for k, v in o.items():
            keys.append(str(k))
            p = "%s.%s" % (path, k) if path else str(k)
            if isinstance(v, (dict, list)):
                _flatten(v, p, units, keys)
            else:
                scal.append("%s %s" % (k, v))
                units.append(Unit("%s %s" % (k, v), p))
        if scal:
            units.append(Unit(" ".join(scal), path or "корень"))
    elif isinstance(o, list):
        for i, v in enumerate(o):
            p = "%s[%d]" % (path, i)
            if isinstance(v, (dict, list)):
                _flatten(v, p, units, keys)
            else:
                units.append(Unit(str(v), p))
        sc = [str(v) for v in o if not isinstance(v, (dict, list))]
        if sc:
            units.append(Unit(" ".join(sc), path or "корень"))


def load_target(text):
    """-> (units, headings, keys, is_json)"""
    s = text.strip()
    if s[:1] in "[{":
        try:
            data = json.loads(s)
            units, keys = [], []
            _flatten(data, "", units, keys)
            return units, [], keys, True
        except ValueError:
            pass
    u, h, _ = units_from_text(text)
    return u, h, [], False


# ---------- сравнение ----------
def _hit_strong(unit, tok):
    return tok.casefold() in unit.low


def _hit_weak(unit, st):
    return any(w.startswith(st) for w in unit.words)


def compare(spec_text, target_text):
    reqs = parse_spec(spec_text)
    units, headings, keys, is_json = load_target(target_text)
    whole = Unit(target_text, "файл")
    rows = []
    for r in reqs:
        strong, weak = tokens(r["text"])
        total = 2 * len(strong) + len(weak)
        remarks = []
        if total == 0:
            rows.append({"id": r["id"], "requirement": r["text"], "status": "нет", "found": False, "where": "-", "confidence": 0.0,
                         "remark": "в требовании нет проверяемых признаков (слов/идентификаторов/чисел), проверь вручную"})
            continue
        glob_s = [t for t in strong if _hit_strong(whole, t)]
        glob_w = [w for w in weak if _hit_weak(whole, w)]
        glob = (2 * len(glob_s) + len(glob_w)) / total
        best, best_u = -1.0, None
        for u in units:
            sc = (2 * sum(1 for t in strong if _hit_strong(u, t)) + sum(1 for w in weak if _hit_weak(u, w))) / total
            if sc > best or (sc == best and best_u is not None and len(u.text) < len(best_u.text)):
                best, best_u = sc, u
        conf = 0.6 * max(best, 0.0) + 0.4 * glob
        miss_s = [t for t in strong if t not in glob_s]
        if miss_s:
            conf = min(conf, 0.69)
            nums = [t for t in miss_s if re.fullmatch(r"\d+(?:[.,]\d+)?", t)]
            other = [t for t in miss_s if t not in nums]
            if other:
                remarks.append("не найдено: " + ", ".join(other))
            if nums:
                remarks.append("число не встречается в файле: " + ", ".join(nums))
        miss_w = [w for w in weak if w not in glob_w]
        if miss_w and len(miss_w) <= 4:
            remarks.append("нет слов с основой: " + ", ".join(miss_w))
        # структура
        quoted = [t for t in strong if not re.fullmatch(r"\d+(?:[.,]\d+)?", t)]
        if STRUCT_HEAD_RE.search(r["text"]) and quoted and not is_json:
            if not any(t.casefold() in h.casefold() for t in quoted for h in headings):
                conf = min(conf, 0.6)
                remarks.append("нет заголовка раздела с таким названием")
        if STRUCT_KEY_RE.search(r["text"]) and quoted and is_json:
            if not any(t.casefold() == k.casefold() for t in quoted for k in keys):
                conf = min(conf, 0.6)
                remarks.append("нет поля/ключа с таким именем")
        if NEG_RE.search(r["text"]):
            remarks.append("запрет: совпадение слов не доказывает выполнение, проверь вручную")
        conf = round(max(0.0, min(1.0, conf)), 2)
        status = "да" if conf >= FOUND_T else "частично" if conf >= PARTIAL_T else "нет"
        rows.append({"id": r["id"], "requirement": r["text"], "status": status, "found": status != "нет",
                     "where": best_u.where if best_u is not None and best > 0 else "-", "confidence": conf,
                     "remark": "; ".join(remarks) or "-"})
    return rows


def render_table(rows):
    def cell(x):
        return str(x).replace("|", "\\|").replace("\n", " ")
    out = ["| № | Требование | Найдено | Где | Уверенность | Замечание |", "|---|---|---|---|---|---|"]
    for r in rows:
        out.append("| %s | %s | %s | %s | %d%% | %s |" % (cell(r["id"]), cell(r["requirement"]), r["status"], cell(r["where"]),
                                                          round(r["confidence"] * 100), cell(r["remark"])))
    n = len(rows)
    yes = sum(1 for r in rows if r["status"] == "да")
    part = sum(1 for r in rows if r["status"] == "частично")
    out.append("")
    out.append("Итого требований: %d; найдено: %d; частично: %d; не найдено: %d." % (n, yes, part, n - yes - part))
    return "\n".join(out)


def _read(path):
    with open(path, "rb") as f:
        raw = f.read()
    if b"\x00" in raw[:8192]:
        raise ValueError("%s: двоичный файл, нужен текст/Markdown/JSON" % path)
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("cp1251", errors="replace")


def compare_files(spec_path, target_path):
    return compare(_read(spec_path), _read(target_path))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Сравнить файл с ТЗ")
    ap.add_argument("spec")
    ap.add_argument("target")
    ap.add_argument("--json", action="store_true", help="вывод JSON вместо таблицы")
    ap.add_argument("--strict", action="store_true", help="код 1, если есть требования со статусом «нет»")
    a = ap.parse_args(argv)
    try:
        rows = compare_files(a.spec, a.target)
    except (OSError, ValueError) as e:
        print("ошибка: %s" % e, file=sys.stderr)
        return 2
    if not rows:
        print("В ТЗ не найдено ни одного пункта.", file=sys.stderr)
        return 2
    print(json.dumps(rows, ensure_ascii=False, indent=1) if a.json else render_table(rows))
    return 1 if a.strict and any(r["status"] == "нет" for r in rows) else 0


if __name__ == "__main__":
    sys.exit(main())
