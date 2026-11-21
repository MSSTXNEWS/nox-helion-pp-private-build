#!/usr/bin/env python3
"""NOX practical tools for the owner's work (NOX, server, web "Резонанс", design). Stdlib only.

Every tool: dict in -> dict out, {"ok": true, ...} or {"ok": false, "blocked": ..., "need": ...}.
Read-only: nothing is deployed, deleted or sent anywhere (advisor_review talks only to
the advisors from the given config).
CLI: practical_tools.py TOOL --json '{"k": "v"}' | --file in.json
"""
import argparse
import colorsys
import html.parser
import json
import os
import re
import shutil
import socket
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def _bad(why, need):
    return {"ok": False, "blocked": why, "need": need}


def _req(a, *names):
    miss = [n for n in names if not a.get(n)]
    return _bad("missing input: " + ", ".join(miss), "provide: " + ", ".join(miss)) if miss else None


# ---------- color math (WCAG 2.x) ----------
def parse_hex(h):
    h = str(h).strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if not re.fullmatch(r"[0-9a-fA-F]{6}", h):
        raise ValueError(f"bad hex color: {h!r}")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def to_hex(rgb):
    return "#%02x%02x%02x" % tuple(max(0, min(255, round(c))) for c in rgb)


def _lin(c):
    c /= 255
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def luminance(rgb):
    r, g, b = (_lin(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(fg, bg):
    l1, l2 = luminance(parse_hex(fg)), luminance(parse_hex(bg))
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def wcag(ratio):
    return {"ratio": round(ratio, 2), "AA_text": ratio >= 4.5, "AA_large": ratio >= 3.0,
            "AAA_text": ratio >= 7.0}


def palette_gen(a):
    e = _req(a, "base")
    if e:
        return e
    try:
        r, g, b = (c / 255 for c in parse_hex(a["base"]))
    except ValueError as x:
        return _bad(str(x), "base as #rrggbb")
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    scheme = a.get("scheme", "analogous")
    offs = {"mono": [0], "analogous": [0, -30, 30], "complementary": [0, 180],
            "triad": [0, 120, 240], "split": [0, 150, 210]}.get(scheme)
    if offs is None:
        return _bad(f"unknown scheme {scheme!r}", "mono|analogous|complementary|triad|split")
    colors = {}
    for i, o in enumerate(offs):
        rr, gg, bb = colorsys.hls_to_rgb(((h * 360 + o) % 360) / 360, l, s)
        colors["primary" if i == 0 else f"accent{i}"] = to_hex((rr * 255, gg * 255, bb * 255))
    colors["surface"], colors["text"] = "#ffffff", "#111111"
    out = {}
    for n, hx in colors.items():
        on = max(("#ffffff", "#111111"), key=lambda c: contrast_ratio(c, hx))
        out[n] = {"hex": hx, "on": on, **wcag(contrast_ratio(on, hx))}
    return {"ok": True, "scheme": scheme, "palette": out,
            "text_on_surface": wcag(contrast_ratio(colors["text"], colors["surface"]))}


def css_tokens(a):
    pal = a.get("palette")
    if not isinstance(pal, dict) or not pal:
        return _bad("missing palette", 'palette: {"primary":"#1a73e8",...}')
    try:
        for v in pal.values():
            parse_hex(v if isinstance(v, str) else v.get("hex"))
    except (ValueError, AttributeError) as x:
        return _bad(str(x), "palette values as #rrggbb")
    base = int(a.get("space_base", 4))
    ratio = float(a.get("type_ratio", 1.25))
    size = float(a.get("type_base_px", 16))
    lines = [":root {"]
    for k, v in pal.items():
        lines.append(f"  --color-{k}: {v if isinstance(v, str) else v['hex']};")
    for i, m in enumerate((1, 2, 3, 4, 6, 8, 12, 16), 1):
        lines.append(f"  --space-{i}: {base * m}px;")
    for i, n in enumerate(range(-1, 5)):
        lines.append(f"  --font-size-{i}: {round(size * ratio ** n / 16, 3)}rem;")
    lines += ["  --radius: 8px;", "  --tap-min: 44px;", "}"]
    return {"ok": True, "css": "\n".join(lines) + "\n"}


# ---------- HTML parsing: a11y + lint ----------
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source",
        "track", "wbr", "param"}
DEPRECATED = {"font", "center", "marquee", "blink", "big", "strike", "frame", "frameset", "acronym"}


def _style(s):
    return {k.strip().lower(): v.strip() for k, _, v in
            (p.partition(":") for p in (s or "").split(";")) if k.strip()}


def _px(v):
    m = re.fullmatch(r"([\d.]+)px", v or "")
    return float(m.group(1)) if m else None


def _color(v):
    try:
        return to_hex(parse_hex(v)) if v and v.strip().startswith("#") else None
    except ValueError:
        return None


class _P(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.tags, self.ids, self.issues = [], [], {}, []
        self.doctype = False
        self.text_in = []  # open elements collecting text
        self.labels_for, self.inputs = set(), []

    def pos(self):
        return self.getpos()[0]

    def add(self, code, msg, sev="error"):
        self.issues.append({"line": self.pos(), "code": code, "message": msg, "severity": sev})

    def handle_decl(self, d):
        if d.lower().startswith("doctype"):
            self.doctype = True

    def handle_starttag(self, tag, attrs):
        at = dict(attrs)
        self.tags.append((tag, at, self.pos()))
        if tag in DEPRECATED:
            self.add("deprecated-tag", f"<{tag}> is deprecated", "warning")
        if "id" in at:
            if at["id"] in self.ids:
                self.add("duplicate-id", f"duplicate id {at['id']!r}")
            self.ids[at["id"]] = 1
        if tag == "label" and at.get("for"):
            self.labels_for.add(at["for"])
        if tag in ("button", "a", "label", "h1", "h2", "h3", "h4", "h5", "h6"):
            self.text_in.append([tag, at, self.pos(), ""])
        if tag not in VOID:
            self.stack.append((tag, self.pos()))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID and self.stack and self.stack[-1][0] == tag:
            self.stack.pop()
        if self.text_in and self.text_in[-1][0] == tag:
            self.text_in.pop()

    def handle_data(self, data):
        for t in self.text_in:
            t[3] += data

    def handle_endtag(self, tag):
        if self.text_in and self.text_in[-1][0] == tag:
            t = self.text_in.pop()
            self.tags.append(("_text_" + tag, {**t[1], "_text": t[3].strip()}, t[2]))
        if tag in VOID:
            return
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                for u, ln in self.stack[i + 1:]:
                    self.issues.append({"line": ln, "code": "unclosed-tag",
                                        "message": f"<{u}> not closed before </{tag}>", "severity": "error"})
                del self.stack[i:]
                return
        self.add("stray-end-tag", f"</{tag}> without opening tag")


def html_lint(a):
    e = _req(a, "html")
    if e:
        return e
    p = _P()
    p.feed(a["html"]); p.close()
    for u, ln in p.stack:
        p.issues.append({"line": ln, "code": "unclosed-tag", "message": f"<{u}> never closed", "severity": "error"})
    names = [t[0] for t in p.tags]
    if not p.doctype:
        p.issues.append({"line": 1, "code": "no-doctype", "message": "missing <!doctype html>", "severity": "error"})
    for need, code in (("title", "no-title"), ("html", "no-html")):
        if need not in names:
            p.issues.append({"line": 1, "code": code, "message": f"missing <{need}>", "severity": "error"})
    if not any(t[0] == "meta" and t[1].get("name") == "viewport" for t in p.tags):
        p.issues.append({"line": 1, "code": "no-viewport", "message": "missing meta viewport", "severity": "warning"})
    if not any(t[0] == "meta" and ("charset" in t[1]) for t in p.tags):
        p.issues.append({"line": 1, "code": "no-charset", "message": "missing meta charset", "severity": "warning"})
    if names.count("h1") > 1:
        p.issues.append({"line": 1, "code": "multi-h1", "message": "more than one <h1>", "severity": "warning"})
    p.issues.sort(key=lambda i: i["line"])
    return {"ok": True, "errors": sum(i["severity"] == "error" for i in p.issues),
            "warnings": sum(i["severity"] == "warning" for i in p.issues), "issues": p.issues}


def a11y_check(a):
    e = _req(a, "html")
    if e:
        return e
    p = _P()
    p.feed(a["html"]); p.close()
    iss = []

    def add(line, code, msg):
        iss.append({"line": line, "code": code, "message": msg})
    root = next((t for t in p.tags if t[0] == "html"), None)
    if not root or not root[1].get("lang"):
        add(root[2] if root else 1, "html-lang", "<html> needs lang attribute (e.g. lang=\"ru\")")
    last_h = 0
    for tag, at, ln in p.tags:
        st = _style(at.get("style"))
        if tag == "img" and "alt" not in at:
            add(ln, "img-alt", "<img> without alt (use alt=\"\" for decorative images)")
        if tag in ("input", "select", "textarea") and at.get("type") not in ("hidden", "submit", "button"):
            if not (at.get("aria-label") or at.get("aria-labelledby") or at.get("title") or at.get("id") in p.labels_for):
                add(ln, "form-label", f"<{tag}> has no label")
        if tag in ("a", "button", "input", "select") or at.get("role") == "button":
            for dim in ("width", "height", "min-width", "min-height"):
                v = _px(st.get(dim))
                if v is not None and v < 44 and dim in ("width", "height"):
                    add(ln, "target-size", f"<{tag}> {dim}={v:g}px < 44px touch target")
        fg, bg = _color(st.get("color")), _color(st.get("background-color") or st.get("background"))
        if fg and bg:
            r = contrast_ratio(fg, bg)
            fs = _px(st.get("font-size")) or 16
            need = 3.0 if fs >= 24 else 4.5
            if r < need:
                add(ln, "contrast", f"contrast {r:.2f}:1 {fg} on {bg}, need {need}:1")
        if tag in ("_text_a", "_text_button") and not at["_text"] and not (
                at.get("aria-label") or at.get("title")):
            add(ln, "empty-control", f"<{tag[6:]}> has no accessible text")
        if re.fullmatch(r"_text_h[1-6]", tag):
            lvl = int(tag[-1])
            if last_h and lvl > last_h + 1:
                add(ln, "heading-order", f"heading jumps h{last_h} -> h{lvl}")
            last_h = lvl
    return {"ok": True, "violations": len(iss), "issues": iss}


# ---------- design / copy / planning ----------
def design_brief(a):
    e = _req(a, "project", "audience", "goal")
    if e:
        return e
    tone = a.get("tone") or "спокойный, ясный"
    cons = a.get("constraints") or []
    return {"ok": True, "brief": {
        "title": a["project"], "audience": a["audience"], "goal": a["goal"], "tone": tone,
        "constraints": cons,
        "deliverables": a.get("deliverables") or ["макет главной", "палитра + токены", "типографика", "компоненты (кнопка, форма, карточка)"],
        "principles": ["контраст текста >= 4.5:1", "цели нажатия >= 44px", "mobile first (360px)",
                       "один основной CTA на экран", "lang и alt везде"],
        "acceptance": [f"цель «{a['goal']}» достижима с главной за <= 2 клика",
                       "a11y_check без нарушений", "html_lint без errors",
                       "Lighthouse/ручная проверка на 360px и 1280px"],
        "open_questions": [q for q, k in (("референсы/бренд-цвета?", "brand"), ("логотип и шрифты?", "assets"))
                           if not a.get(k)]}}


def img_optimize_plan(a):
    paths = a.get("paths") or ([os.path.join(a["dir"], f) for f in sorted(os.listdir(a["dir"]))]
                               if a.get("dir") and os.path.isdir(a["dir"]) else None)
    if not paths:
        return _bad("no images", "paths: [files] or dir: existing directory")
    budget = int(a.get("max_kb", 200)) * 1024
    plan = []
    for p in paths:
        ext = os.path.splitext(p)[1].lower()
        if ext not in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"):
            continue
        try:
            size = os.path.getsize(p)
            dim = _img_size(p, ext)
        except OSError as x:
            plan.append({"file": p, "error": str(x)}); continue
        acts = []
        if ext in (".png", ".jpg", ".jpeg", ".gif"):
            acts.append("convert to WebP/AVIF q~80 with <picture> fallback")
        if dim and dim[0] > int(a.get("max_width", 1920)):
            acts.append(f"downscale {dim[0]}px -> {a.get('max_width', 1920)}px wide")
        if size > budget:
            acts.append(f"over budget {size // 1024}KB > {budget // 1024}KB")
        if dim and dim[0] > 800:
            acts.append("add srcset 480/800/1280 + loading=lazy + width/height attrs")
        if ext == ".svg":
            acts.append("minify SVG, strip metadata")
        plan.append({"file": p, "bytes": size, "dimensions": dim, "actions": acts or ["ok"]})
    return {"ok": True, "plan": plan, "executes": False,
            "tools": "cwebp/avif or squoosh by owner; this tool only plans"}


def _img_size(p, ext):
    with open(p, "rb") as f:
        d = f.read(65536)
    if d[:8] == b"\x89PNG\r\n\x1a\n":
        return struct.unpack(">II", d[16:24])
    if d[:6] in (b"GIF87a", b"GIF89a"):
        return struct.unpack("<HH", d[6:10])
    if d[:2] == b"\xff\xd8":
        i = 2
        while i + 9 < len(d):
            if d[i] != 0xFF:
                i += 1; continue
            m = d[i + 1]
            if m in (0xC0, 0xC1, 0xC2):
                h, w = struct.unpack(">HH", d[i + 5:i + 9]); return (w, h)
            i += 2 + struct.unpack(">H", d[i + 2:i + 4])[0]
    if d[:4] == b"RIFF" and d[8:12] == b"WEBP" and d[12:16] == b"VP8 ":
        w, h = struct.unpack("<HH", d[26:30]); return (w & 0x3FFF, h & 0x3FFF)
    return None


def screenshot_diff_plan(a):
    e = _req(a, "pages")
    if e:
        return e
    vps = a.get("viewports") or [[360, 800], [768, 1024], [1280, 800]]
    shots = [{"page": pg, "viewport": f"{w}x{h}", "baseline": f"shots/base/{re.sub(r'[^a-z0-9]+', '_', pg.lower()).strip('_')}_{w}.png",
              "current": f"shots/cur/{re.sub(r'[^a-z0-9]+', '_', pg.lower()).strip('_')}_{w}.png"}
             for pg in a["pages"] for w, h in vps]
    return {"ok": True, "shots": shots, "threshold_pct": a.get("threshold_pct", 0.5), "count": len(shots),
            "steps": ["снять baseline до правки", "снять current после правки", "сравнить попиксельно, порог из threshold_pct",
                      "diff > порога: приложить diff-картинку к PR"], "executes": False}


NBSP = " "
SHORT = r"(?:в|во|к|ко|с|со|у|о|об|на|за|по|из|от|до|и|а|но|не|ни|я|мы|вы|он|же|ли|бы)"


def copy_ru(a):
    e = _req(a, "text")
    if e:
        return e
    t, issues = a["text"], []
    n0 = t
    t = re.sub(r"[ \t]{2,}", " ", t)
    t = re.sub(r"\s+([,.;:!?])", r"\1", t)
    t = re.sub(r"\"([^\"]+)\"", r"«\1»", t)
    t = re.sub(r"(?<=\s)-(?=\s)", "—", t)
    t = re.sub(r"(?<=\d)-(?=\d)", "–", t)
    t = re.sub(r"(?i)(?<!\w)(" + SHORT + r") +(?=\S)", lambda m: m.group(1) + NBSP, t)
    t = re.sub(r"(?<=\d) (?=(?:₽|руб|р\.|%|кг|км|мс|мб|гб))", NBSP, t, flags=re.I)
    if t != n0:
        issues.append("типографика исправлена (кавычки «», тире, неразрывные пробелы, лишние пробелы)")
    sents = [s for s in re.split(r"(?<=[.!?])\s+", t) if s.strip()]
    long_s = [s[:60] + "…" for s in sents if len(s.split()) > 25]
    if long_s:
        issues.append(f"{len(long_s)} предложений длиннее 25 слов")
    if re.search(r"!{2,}|\?{2,}", t):
        issues.append("повторные !/? убрать")
    caps = re.findall(r"\b[А-ЯЁ]{5,}\b", t)
    if caps:
        issues.append("капс: " + ", ".join(sorted(set(caps))[:5]))
    return {"ok": True, "text": t, "issues": issues, "words": len(t.split()), "sentences": len(sents),
            "avg_words_per_sentence": round(len(t.split()) / max(1, len(sents)), 1)}


RISK = {r"деплой|deploy|прод": "затрагивает прод: нужен deploy_checklist и подтверждение владельца",
        r"удал|delete|rm -|drop": "деструктивное действие: запросить подтверждение, сделать бэкап",
        r"ключ|токен|парол|secret|api[_ -]?key": "секреты: только из окружения, не в коммит и не в лог",
        r"v29\.3": "защищённые файлы V29.3: не менять"}


def task_to_pr(a):
    e = _req(a, "text")
    if e:
        return e
    raw = [re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", l).strip() for l in a["text"].splitlines()]
    items = [l for l in raw if l]
    if len(items) <= 1:
        items = [s.strip() for s in re.split(r"(?<=[.!?;])\s+", a["text"]) if s.strip()]
    if not items:
        return _bad("empty task", "text with at least one requirement")
    title = items[0].rstrip(".")[:72]
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower().translate(str.maketrans(
        "абвгдеёжзийклмнопрстуфхцчшщъыьэюя", "abvgdeejzijklmnoprstufhccss_y_eua"))).strip("-")[:40] or "task"
    steps = [{"n": i, "step": it, "check": f"виден результат: «{it[:60]}» подтверждён тестом/командой/скриншотом"}
             for i, it in enumerate(items, 1)]
    risks = [m for rx, m in RISK.items() if re.search(rx, a["text"], re.I)]
    return {"ok": True, "pr_title": title, "branch": "task/" + slug, "steps": steps,
            "acceptance": [f"[ ] {s['step']}" for s in steps] + ["[ ] тесты зелёные", "[ ] нет TODO/заглушек"],
            "risks": risks, "needs_owner": bool(risks)}


def changelog_gen(a):
    repo = a.get("repo", ".")
    if not os.path.isdir(os.path.join(repo, ".git")) and not os.path.isfile(os.path.join(repo, ".git")):
        return _bad("not a git repository", "repo: path to a git checkout")
    n = max(1, min(int(a.get("n", 30)), 500))
    cmd = ["git", "-C", repo, "log", f"-{n}", "--no-merges", "--pretty=format:%h\x1f%ad\x1f%s", "--date=short"]
    if a.get("since"):
        cmd.insert(5, "--since=" + str(a["since"]))
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if p.returncode:
        return _bad("git log failed: " + p.stderr[:200], "check repo path")
    groups = {}
    for line in p.stdout.splitlines():
        h, d, s = line.split("\x1f", 2)
        m = re.match(r"^([A-Za-z0-9_\-]+)(?:\([^)]*\))?:\s*(.*)", s)
        kind, msg = (m.group(1), m.group(2)) if m else ("other", s)
        groups.setdefault(kind, []).append({"hash": h, "date": d, "msg": msg})
    md = ["# Changelog"] + [f"\n## {k}\n" + "\n".join(f"- {c['msg']} ({c['hash']}, {c['date']})" for c in v)
                            for k, v in groups.items()]
    return {"ok": True, "commits": sum(map(len, groups.values())), "groups": groups, "markdown": "\n".join(md) + "\n"}


CHECKLISTS = {
    "web": ["html_lint без errors", "a11y_check без нарушений", "картинки по img_optimize_plan", "проверка 360/768/1280px",
            "meta title/description/og", "бэкап текущей версии", "выкладка владельцем/главным агентом", "smoke: 200 на главной и ключевых страницах", "план отката записан"],
    "nox": ["unittest nox-control зелёные", "файлы V29.3 не изменены (git diff)", "бенчмарк tok/s не хуже -5%",
            "бэкап состояния и конфига", "рестарт с health-check и авто-откатом", "лог без ключей и путей", "план отката записан"],
    "server": ["df -h: свободно >= 15%", "free: swap не растёт", "бэкап конфигов", "окно работ согласовано",
               "изменение через dry-run, затем apply", "проверка портов после", "откат записан"],
}


def deploy_checklist(a):
    kind = a.get("kind", "web")
    if kind not in CHECKLISTS:
        return _bad(f"unknown kind {kind!r}", "kind: " + "|".join(CHECKLISTS))
    items = CHECKLISTS[kind] + list(a.get("extra") or [])
    return {"ok": True, "kind": kind, "checklist": [f"[ ] {i}" for i in items],
            "executes": False, "note": "чеклист; деплой выполняет владелец или главный агент"}


def server_status_summary(a):
    out = {"ok": True}
    try:
        with open(a.get("proc", "/proc") + "/loadavg") as f:
            la = f.read().split()[:3]
        out["load"] = [float(x) for x in la]
        out["cpus"] = os.cpu_count()
        mem = {}
        with open(a.get("proc", "/proc") + "/meminfo") as f:
            for line in f:
                k, _, v = line.partition(":")
                mem[k] = int(v.split()[0]) // 1024
        out["mem_mb"] = {"total": mem.get("MemTotal"), "available": mem.get("MemAvailable"),
                         "swap_used": mem.get("SwapTotal", 0) - mem.get("SwapFree", 0)}
        with open(a.get("proc", "/proc") + "/uptime") as f:
            out["uptime_h"] = round(float(f.read().split()[0]) / 3600, 1)
    except (OSError, ValueError) as e:
        return _bad(f"cannot read /proc: {e}", "run on the Linux server")
    du = shutil.disk_usage(a.get("disk_path", "/"))
    out["disk"] = {"free_gb": round(du.free / 1e9, 1), "used_pct": round(100 * du.used / du.total, 1)}
    ports = {}
    for name, port in (a.get("ports") or {}).items():
        s = socket.socket(); s.settimeout(0.5)
        ports[name] = s.connect_ex(("127.0.0.1", int(port))) == 0
        s.close()
    out["ports"] = ports
    warn = []
    if out["load"][0] > out["cpus"]:
        warn.append("load выше числа ядер")
    if out["mem_mb"]["available"] is not None and out["mem_mb"]["total"] and out["mem_mb"]["available"] < 0.1 * out["mem_mb"]["total"]:
        warn.append("доступной памяти < 10%")
    if out["disk"]["used_pct"] > 85:
        warn.append("диск заполнен > 85%")
    warn += [f"порт {n} не отвечает" for n, up in ports.items() if not up]
    out["warnings"] = warn
    out["summary"] = ("Проблемы: " + "; ".join(warn)) if warn else "Всё в норме"
    return out


def advisor_review(a):
    e = _req(a, "task", "acceptance", "answer", "config")
    if e:
        return e
    if not os.path.isfile(a["config"]):
        return _bad("advisors config not found: " + a["config"], "copy advisors.example.json to advisors.json and fill it")
    sys.path.insert(0, os.path.join(HERE, "..", "advisors"))
    import nox_advisors
    r = nox_advisors.review(a["task"], a["acceptance"], a["answer"], a["config"])
    return {"ok": True, "label": nox_advisors.LABEL, **r}


TOOLS = {f.__name__: f for f in (design_brief, palette_gen, css_tokens, a11y_check, html_lint,
                                 img_optimize_plan, screenshot_diff_plan, copy_ru, task_to_pr,
                                 changelog_gen, deploy_checklist, server_status_summary, advisor_review)}


def run(tool, args):
    if tool not in TOOLS:
        return _bad(f"unknown tool {tool!r}", "one of: " + ", ".join(sorted(TOOLS)))
    try:
        return TOOLS[tool](args or {})
    except Exception as e:
        return {"ok": False, "blocked": f"{type(e).__name__}: {str(e)[:300]}", "need": "check input"}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("tool", choices=sorted(TOOLS) + ["list"])
    ap.add_argument("--json"); ap.add_argument("--file")
    ns = ap.parse_args(argv)
    if ns.tool == "list":
        print(json.dumps(sorted(TOOLS))); return 0
    args = json.loads(open(ns.file, encoding="utf-8").read()) if ns.file else json.loads(ns.json or "{}")
    out = run(ns.tool, args)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
