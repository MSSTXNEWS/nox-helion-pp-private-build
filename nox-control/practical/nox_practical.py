#!/usr/bin/env python3
"""NOX practical chat tools for the owner (NOX HELION, server, web panel Resonance, design).
Stdlib only. Every tool: dict in -> dict out, read-only (no file writes, no network except advisor_review).
CLI: python3 nox_practical.py <tool> '<json args>' | --list | --manifest
"""
import colorsys
import json
import os
import re
import subprocess
import sys
import time
from html.parser import HTMLParser

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = {}


def tool(name, desc, params):
    def deco(fn):
        TOOLS[name] = {"fn": fn, "description": desc, "params": params}
        return fn
    return deco


# ---------- color helpers (WCAG 2.x) ----------
def hex_to_rgb(h):
    h = h.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if not re.fullmatch(r"[0-9a-fA-F]{6}", h):
        raise ValueError(f"bad hex color: {h!r}")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def rgb_to_hex(rgb):
    return "#%02x%02x%02x" % tuple(max(0, min(255, round(c))) for c in rgb)


def luminance(rgb):
    def ch(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    la, lb = luminance(hex_to_rgb(a)), luminance(hex_to_rgb(b))
    hi, lo = max(la, lb), min(la, lb)
    return round((hi + 0.05) / (lo + 0.05), 2)


def wcag(ratio, large=False):
    return {"AA": ratio >= (3.0 if large else 4.5), "AAA": ratio >= (4.5 if large else 7.0)}


def _hsl_shift(hexc, dh=0.0, ds=0.0, dl=0.0):
    r, g, b = (c / 255 for c in hex_to_rgb(hexc))
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    h = (h + dh / 360) % 1
    s = max(0, min(1, s + ds))
    l = max(0, min(1, l + dl))
    return rgb_to_hex(tuple(c * 255 for c in colorsys.hls_to_rgb(h, l, s)))


def _best_text(bg):
    return max(("#000000", "#ffffff"), key=lambda t: contrast(bg, t))


# ---------- design_brief ----------
_TONES = {"строг": "строгий", "премиум": "премиальный", "дорог": "премиальный", "тёмн": "тёмный",
          "темн": "тёмный", "светл": "светлый", "минимал": "минималистичный", "игрив": "игривый",
          "техно": "технологичный", "киберпанк": "технологичный", "дружелюб": "дружелюбный",
          "делов": "деловой", "спокой": "спокойный", "ярк": "яркий"}
_SECTION_WORDS = {"hero": ["главн", "hero", "первый экран"], "features": ["возможност", "функци", "преимуществ"],
                  "pricing": ["цен", "тариф"], "faq": ["faq", "вопрос"], "contacts": ["контакт", "связь"],
                  "status": ["статус", "дашборд", "панел"], "docs": ["документ", "инструкц"]}


@tool("design_brief", "Бриф дизайна из свободного текста: цель, аудитория, тон, секции, ограничения, вопросы.",
      {"text": "str, описание задачи"})
def design_brief(args):
    text = str(args.get("text", "")).strip()
    low = text.lower()
    sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text) if s.strip()]
    aud = re.search(r"для\s+([^.,;\n]{3,60})", low)
    tones = sorted({v for k, v in _TONES.items() if k in low})
    sections = [k for k, ws in _SECTION_WORDS.items() if any(w in low for w in ws)] or ["hero", "features", "contacts"]
    colors = re.findall(r"#[0-9a-fA-F]{3,6}\b", text)
    constraints = [s for s in sents if re.search(r"\b(нельзя|не надо|без|обязательно|только|до \d)", s.lower())]
    questions = []
    if not aud:
        questions.append("Кто целевая аудитория?")
    if not tones:
        questions.append("Какой тон/настроение (тёмный, светлый, строгий, игривый)?")
    if not colors:
        questions.append("Есть ли фирменный цвет? Иначе сгенерируем через palette_gen.")
    return {"goal": sents[0] if sents else "", "audience": aud.group(1) if aud else None,
            "tone": tones, "sections": sections, "brand_colors": colors, "constraints": constraints,
            "open_questions": questions,
            "next": ["palette_gen", "css_tokens", "copy_ru", "a11y_check"]}


# ---------- palette_gen ----------
@tool("palette_gen", "Палитра от базового цвета + расчёт контраста WCAG (AA/AAA) для пар текст/фон.",
      {"base": "hex, напр. #3b82f6", "scheme": "analogous|complementary|triad (по умолч. analogous)",
       "dark": "bool, тёмная тема"})
def palette_gen(args):
    base = rgb_to_hex(hex_to_rgb(args["base"]))
    scheme = args.get("scheme", "analogous")
    shifts = {"analogous": (30, -30), "complementary": (180, 150), "triad": (120, 240)}
    if scheme not in shifts:
        raise ValueError("scheme must be one of " + ",".join(shifts))
    dark = bool(args.get("dark"))
    bg = "#0f1115" if dark else "#ffffff"
    surface = "#1a1d24" if dark else "#f4f5f7"
    pal = {"primary": base, "secondary": _hsl_shift(base, shifts[scheme][0]),
           "accent": _hsl_shift(base, shifts[scheme][1]),
           "bg": bg, "surface": surface, "text": _best_text(bg), "muted": "#9aa3b2" if dark else "#5b6472"}
    # primary text-on-button color chosen by computed contrast
    pal["on_primary"] = _best_text(pal["primary"])
    pairs = [("text", "bg"), ("text", "surface"), ("muted", "bg"), ("on_primary", "primary"),
             ("primary", "bg"), ("accent", "bg")]
    checks = []
    for fg, bgk in pairs:
        r = contrast(pal[fg], pal[bgk])
        checks.append({"fg": fg, "bg": bgk, "ratio": r, "normal": wcag(r), "large": wcag(r, True)})
    return {"scheme": scheme, "dark": dark, "colors": pal, "checks": checks,
            "all_text_pairs_AA": all(c["normal"]["AA"] for c in checks if c["fg"] != "accent" and c["fg"] != "primary" or c["fg"] == "on_primary")}


@tool("css_tokens", "CSS custom properties из палитры (+ отступы, радиусы, шрифты, фокус).",
      {"colors": "dict имя->hex (например из palette_gen.colors)", "prefix": "str, по умолч. nox"})
def css_tokens(args):
    prefix = re.sub(r"[^a-z0-9-]", "", str(args.get("prefix", "nox")).lower()) or "nox"
    lines = [":root {"]
    for k, v in args["colors"].items():
        lines.append(f"  --{prefix}-color-{re.sub(r'[^a-z0-9]+', '-', k.lower())}: {rgb_to_hex(hex_to_rgb(v))};")
    for i, px in enumerate((4, 8, 12, 16, 24, 32, 48), 1):
        lines.append(f"  --{prefix}-space-{i}: {px / 16:g}rem;")
    lines += [f"  --{prefix}-radius: 8px;", f"  --{prefix}-tap-min: 44px;",
              f"  --{prefix}-font: system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif;",
              f"  --{prefix}-focus: 2px solid var(--{prefix}-color-primary, #3b82f6);", "}"]
    return {"css": "\n".join(lines) + "\n", "count": len(lines) - 2}


# ---------- HTML parsing for a11y_check / html_lint ----------
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}


def _css_decls(s):
    return {k.strip().lower(): v.strip().lower() for k, _, v in
            (d.partition(":") for d in s.split(";") if ":" in d)}


def _px(v):
    m = re.fullmatch(r"(\d+(?:\.\d+)?)(px|rem|em)?", v or "")
    if not m:
        return None
    n = float(m.group(1))
    return n * 16 if m.group(2) in ("rem", "em") else n


class _Doc(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.els, self.stack, self.problems = [], [], []
        self.doctype = False
        self.css = ""
        self._in_style = False
        self.text_stack = []

    def handle_decl(self, decl):
        if decl.lower().startswith("doctype"):
            self.doctype = True

    def handle_starttag(self, tag, attrs):
        a = dict((k, v if v is not None else "") for k, v in attrs)
        line = self.getpos()[0]
        el = {"tag": tag, "attrs": a, "line": line, "text": ""}
        self.els.append(el)
        if tag == "style":
            self._in_style = True
        if tag not in VOID:
            self.stack.append(el)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID and self.stack and self.stack[-1]["tag"] == tag:
            self.stack.pop()

    def handle_endtag(self, tag):
        if tag == "style":
            self._in_style = False
        if tag in VOID:
            return
        if self.stack and self.stack[-1]["tag"] == tag:
            self.stack.pop()
        elif any(e["tag"] == tag for e in self.stack):
            while self.stack and self.stack[-1]["tag"] != tag:
                bad = self.stack.pop()
                self.problems.append((bad["line"], f"<{bad['tag']}> не закрыт до </{tag}>"))
            self.stack.pop()
        else:
            self.problems.append((self.getpos()[0], f"лишний </{tag}>"))

    def handle_data(self, data):
        if self._in_style:
            self.css += data
        for e in self.stack:
            e["text"] += data

    def close(self):
        super().close()
        for e in self.stack:
            if e["tag"] not in ("html", "body", "head", "p", "li"):
                self.problems.append((e["line"], f"<{e['tag']}> не закрыт"))


def _parse(html):
    d = _Doc()
    d.feed(html)
    d.close()
    return d


def _rules(css):
    out = []
    for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", re.sub(r"/\*.*?\*/", "", css, flags=re.S)):
        for s in sel.split(","):
            out.append((s.strip(), _css_decls(body)))
    return out


def _style_of(el, rules):
    d = {}
    cls = set(el["attrs"].get("class", "").split())
    for sel, decls in rules:
        if sel == el["tag"] or (sel.startswith(".") and sel[1:] in cls) or \
                (sel.startswith("#") and sel[1:] == el["attrs"].get("id")) or \
                (sel.startswith(el["tag"] + ".") and sel.split(".", 1)[1] in cls):
            d.update(decls)
    d.update(_css_decls(el["attrs"].get("style", "")))
    return d


def _hex_in(v):
    m = re.search(r"#(?:[0-9a-f]{6}|[0-9a-f]{3})\b", v or "")
    return m.group(0) if m else None


@tool("a11y_check", "Статическая проверка HTML: lang, alt, подписи полей, контраст (inline/<style>), цели касания 44px.",
      {"html": "str, HTML-текст"})
def a11y_check(args):
    d = _parse(str(args["html"]))
    rules = _rules(d.css)
    issues = []

    def add(sev, line, msg):
        issues.append({"severity": sev, "line": line, "msg": msg})
    html_el = next((e for e in d.els if e["tag"] == "html"), None)
    if not html_el or not html_el["attrs"].get("lang"):
        add("error", html_el["line"] if html_el else 1, "у <html> нет атрибута lang")
    if not any(e["tag"] == "title" and e["text"].strip() for e in d.els):
        add("warn", 1, "нет непустого <title>")
    labels_for = {e["attrs"].get("for") for e in d.els if e["tag"] == "label"}
    for e in d.els:
        t, a = e["tag"], e["attrs"]
        if t == "img" and "alt" not in a:
            add("error", e["line"], "<img> без alt")
        if t in ("input", "select", "textarea") and a.get("type") not in ("hidden", "submit", "button"):
            if not (a.get("aria-label") or a.get("aria-labelledby") or a.get("id") in labels_for or a.get("title")):
                add("error", e["line"], f"<{t}> без подписи (label/aria-label)")
        if t == "a" and not (e["text"].strip() or a.get("aria-label")):
            add("error", e["line"], "ссылка без текста")
        if t == "button" and not (e["text"].strip() or a.get("aria-label")):
            add("error", e["line"], "кнопка без текста")
        st = _style_of(e, rules)
        fg, bg = _hex_in(st.get("color")), _hex_in(st.get("background-color") or st.get("background"))
        if fg and bg:
            r = contrast(fg, bg)
            large = (_px(st.get("font-size", "")) or 0) >= 24
            if not wcag(r, large)["AA"]:
                add("error", e["line"], f"контраст {r}:1 ({fg} на {bg}) ниже AA")
        if t in ("a", "button", "input", "select") or a.get("role") == "button":
            w, h = _px(st.get("width", "")), _px(st.get("height", ""))
            for dim, val in (("ширина", w), ("высота", h)):
                if val is not None and val < 44:
                    add("warn", e["line"], f"цель касания: {dim} {val:g}px < 44px")
    sev = [i["severity"] for i in issues]
    return {"ok": "error" not in sev, "errors": sev.count("error"), "warnings": sev.count("warn"), "issues": issues,
            "note": "статическая проверка: контраст считается только по заданным цветам, наследование не учитывается"}


_DEPRECATED = {"font", "center", "marquee", "blink", "big", "strike", "frame", "frameset"}


@tool("html_lint", "Линтер HTML: doctype, charset, viewport, незакрытые/лишние теги, дубли id, устаревшие теги.",
      {"html": "str, HTML-текст"})
def html_lint(args):
    html = str(args["html"])
    d = _parse(html)
    out = [{"line": ln, "msg": m} for ln, m in d.problems]
    if not d.doctype:
        out.append({"line": 1, "msg": "нет <!doctype html>"})
    metas = [e["attrs"] for e in d.els if e["tag"] == "meta"]
    if not any("charset" in m for m in metas):
        out.append({"line": 1, "msg": "нет <meta charset>"})
    if not any(m.get("name") == "viewport" for m in metas):
        out.append({"line": 1, "msg": "нет <meta name=viewport>"})
    seen = {}
    for e in d.els:
        i = e["attrs"].get("id")
        if i:
            if i in seen:
                out.append({"line": e["line"], "msg": f"дубль id={i!r} (первый на строке {seen[i]})"})
            seen.setdefault(i, e["line"])
        if e["tag"] in _DEPRECATED:
            out.append({"line": e["line"], "msg": f"устаревший тег <{e['tag']}>"})
    if sum(1 for e in d.els if e["tag"] == "h1") > 1:
        out.append({"line": 1, "msg": "несколько <h1>"})
    return {"ok": not out, "count": len(out), "problems": sorted(out, key=lambda x: x["line"])}


# ---------- img_optimize_plan ----------
def _img_dims(path):
    with open(path, "rb") as f:
        b = f.read(65536)
    if b[:8] == b"\x89PNG\r\n\x1a\n":
        return "png", int.from_bytes(b[16:20], "big"), int.from_bytes(b[20:24], "big")
    if b[:6] in (b"GIF87a", b"GIF89a"):
        return "gif", int.from_bytes(b[6:8], "little"), int.from_bytes(b[8:10], "little")
    if b[:2] == b"\xff\xd8":
        i = 2
        while i + 9 < len(b):
            if b[i] != 0xFF:
                i += 1
                continue
            m = b[i + 1]
            if m in (0xC0, 0xC1, 0xC2):
                return "jpeg", int.from_bytes(b[i + 7:i + 9], "big"), int.from_bytes(b[i + 5:i + 7], "big")
            i += 2 + int.from_bytes(b[i + 2:i + 4], "big")
    return None, None, None


@tool("img_optimize_plan", "План оптимизации картинок (без внешних либ): формат, размер, lazy, бюджет. Вход: список или пути.",
      {"images": "list of {path?, format?, width?, height?, bytes?, display_width?}", "budget_kb": "int, по умолч. 200"})
def img_optimize_plan(args):
    budget = int(args.get("budget_kb", 200)) * 1024
    plan = []
    for n, im in enumerate(args.get("images", [])):
        im = dict(im)
        p = im.get("path")
        if p and os.path.isfile(p):
            fmt, w, h = _img_dims(p)
            im.setdefault("format", fmt)
            im.setdefault("width", w)
            im.setdefault("height", h)
            im.setdefault("bytes", os.path.getsize(p))
        fmt = (im.get("format") or "").lower()
        rec = []
        size = im.get("bytes")
        if fmt in ("png", "jpeg", "jpg", "gif", "bmp"):
            rec.append("конвертировать в WebP (или AVIF) с <picture> и fallback" + (" ; для анимации — WebM/MP4" if fmt == "gif" else ""))
        if fmt == "svg":
            rec.append("минифицировать SVG, убрать метаданные")
        dw, w = im.get("display_width"), im.get("width")
        if dw and w and w > 2 * dw:
            rec.append(f"уменьшить до {int(dw * 2)}px по ширине (2x от показа {dw}px), добавить srcset")
        if size and size > budget:
            rec.append(f"размер {size // 1024} КБ > бюджета {budget // 1024} КБ: качество 75-82, убрать EXIF")
        if n > 0 or im.get("below_fold"):
            rec.append('loading="lazy" decoding="async"')
        if w and im.get("height"):
            rec.append(f'указать width={w} height={im["height"]} (против CLS)')
        plan.append({"image": p or im.get("name", f"#{n}"), "format": fmt or None, "bytes": size,
                     "recommendations": rec or ["ok"]})
    return {"budget_kb": budget // 1024, "plan": plan,
            "tools_hint": "squoosh/cwebp/avifenc/svgo локально у владельца; здесь только план"}


@tool("screenshot_diff_plan", "План визуального сравнения скриншотов: страницы x вьюпорты, имена, пороги, шаги.",
      {"pages": "list of str (URL/пути)", "viewports": "list of 'WxH' (по умолч. 375x812,768x1024,1440x900)",
       "threshold_pct": "float, по умолч. 0.1"})
def screenshot_diff_plan(args):
    vps = args.get("viewports") or ["375x812", "768x1024", "1440x900"]
    for v in vps:
        if not re.fullmatch(r"\d{3,4}x\d{3,4}", v):
            raise ValueError(f"bad viewport {v!r}")
    shots = []
    for p in args.get("pages", []):
        slug = re.sub(r"[^a-z0-9]+", "-", p.lower()).strip("-")[:40] or "page"
        for v in vps:
            shots.append({"page": p, "viewport": v, "baseline": f"shots/baseline/{slug}_{v}.png",
                          "candidate": f"shots/candidate/{slug}_{v}.png", "diff": f"shots/diff/{slug}_{v}.png"})
    return {"shots": shots, "threshold_pct": float(args.get("threshold_pct", 0.1)),
            "steps": ["зафиксировать baseline до изменений (анимации выключить, шрифты загружены, фикс. время/данные)",
                      "сделать candidate теми же вьюпортами", "сравнить попиксельно, порог threshold_pct",
                      "превысили порог: открыть diff и принять/отклонить вручную", "baseline обновлять только после ревью"],
            "capture_hint": "Chrome headless: chrome --headless --screenshot=out.png --window-size=WxH URL (у владельца)"}


# ---------- copy_ru ----------
_COPY = {
    "headline": ["{s}: просто и без лишнего", "{s} — сделано для вас", "Всё о {s} в одном месте", "{s}, который работает",
                 "Начните с {s} за минуту"],
    "cta": ["Начать", "Попробовать {s}", "Открыть {s}", "Получить доступ", "Связаться с нами"],
    "empty": ["Пока здесь пусто. Добавьте первый элемент: {s}.", "Ничего не найдено. Измените запрос или создайте {s}."],
    "error": ["Не получилось: {s}. Попробуйте ещё раз через минуту.", "Что-то пошло не так с {s}. Данные сохранены, повторите действие."],
    "success": ["Готово: {s}.", "{s} — успешно сохранено."],
    "loading": ["Загружаем {s}…", "Подождите, готовим {s}…"],
    "confirm": ["Точно выполнить: {s}? Это действие нельзя отменить.", "Подтвердите: {s}."],
}


@tool("copy_ru", "Заголовки и микротексты по шаблонам (RU): headline|cta|empty|error|success|loading|confirm.",
      {"kind": "str, один из шаблонов или all", "subject": "str, о чём текст", "max_len": "int, обрезка по умолч. 80"})
def copy_ru(args):
    kind, s = args.get("kind", "all"), str(args.get("subject", "")).strip() or "сервис"
    if kind != "all" and kind not in _COPY:
        raise ValueError("kind must be all or one of " + ",".join(_COPY))
    ml = int(args.get("max_len", 80))
    kinds = list(_COPY) if kind == "all" else [kind]
    out = {k: [t.format(s=s)[:ml] for t in _COPY[k]] for k in kinds}
    return {"subject": s, "copy": out, "note": "шаблоны; финальный тон согласовать с design_brief"}


# ---------- task_to_pr ----------
_TR = dict(zip("абвгдеёжзийклмнопрстуфхцчшщъыьэюя", "a b v g d e e zh z i y k l m n o p r s t u f h c ch sh sch _ y _ e yu ya".split()))


def _slug(t, n=40):
    s = "".join(_TR.get(c, c) for c in t.lower())
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:n].strip("-") or "task"


@tool("task_to_pr", "Текст задачи -> карточка: заголовок, ветка, acceptance-чеклист, тест-план, риски.",
      {"text": "str, описание задачи"})
def task_to_pr(args):
    text = str(args["text"]).strip()
    lines = [l.strip(" -*•\t") for l in text.splitlines() if l.strip()]
    title = lines[0][:72] if lines else "task"
    body = lines[1:] or re.split(r"(?<=[.!?])\s+", text)[1:]
    accept = [l for l in body if len(l) > 3][:10]
    if not accept:
        accept = [title]
    low = text.lower()
    risks = []
    if re.search(r"deploy|деплой|прод|сервер", low):
        risks.append("затрагивает прод/сервер: нужен чек-лист deploy_checklist и откат")
    if re.search(r"ключ|токен|парол|secret|api", low):
        risks.append("секреты: только через переменные окружения, не в git")
    return {"title": title, "branch": "feat/" + _slug(title),
            "acceptance": [{"id": i + 1, "text": a, "verify": "проверяемо командой/тестом/скриншотом", "done": False}
                           for i, a in enumerate(accept)],
            "test_plan": ["unit-тесты на новую логику", "ручная проверка по каждому пункту acceptance"],
            "risks": risks or ["низкий"], "pr_body_footer": "🤖 Generated with [Claude Code](https://claude.com/claude-code)"}


# ---------- changelog_gen ----------
_KIND = {"feat": "Добавлено", "fix": "Исправлено", "docs": "Документация", "refactor": "Рефакторинг",
         "test": "Тесты", "chore": "Прочее", "perf": "Производительность", "ci": "Прочее"}


def _git_log(repo, since, n):
    cmd = ["git", "-C", repo, "log", f"-n{int(n)}", "--pretty=format:%h\t%s"]
    if since:
        cmd.append(f"{since}..HEAD")
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if p.returncode:
        raise RuntimeError(p.stderr.strip()[:300])
    return p.stdout.splitlines()


@tool("changelog_gen", "Changelog из git log (только чтение) или из переданных строк; группировка по feat/fix/...",
      {"repo": "путь к репозиторию (по умолч. .)", "since": "ref/тег (опц.)", "n": "int, по умолч. 50",
       "lines": "list '<hash>\\t<subject>' вместо git (опц.)"})
def changelog_gen(args):
    lines = args.get("lines")
    if lines is None:
        lines = _git_log(args.get("repo", "."), args.get("since"), args.get("n", 50))
    groups = {}
    for ln in lines:
        h, _, subj = ln.partition("\t")
        m = re.match(r"(\w+)(?:\([^)]*\))?!?:\s*(.+)", subj)
        kind = _KIND.get(m.group(1).lower(), "Прочее") if m else "Прочее"
        groups.setdefault(kind, []).append(f"{m.group(2) if m else subj} ({h})")
    md = ["# Changelog"]
    for k, items in groups.items():
        md += ["", f"## {k}"] + [f"- {i}" for i in items]
    return {"commits": len(lines), "groups": groups, "markdown": "\n".join(md) + "\n"}


# ---------- deploy_checklist ----------
@tool("deploy_checklist", "Чек-лист деплоя (web|server|nox): до / во время / после / откат. Деплой не выполняет.",
      {"kind": "web|server|nox (по умолч. web)", "protected": "list путей, которые нельзя трогать (опц.)"})
def deploy_checklist(args):
    kind = args.get("kind", "web")
    if kind not in ("web", "server", "nox"):
        raise ValueError("kind must be web|server|nox")
    before = ["изменения смержены в main через PR, CI/тесты зелёные", "git status чистый, версия/тег записаны",
              "защищённые файлы не менялись (git diff --stat по списку)", "резервная копия текущей версии сделана",
              "секреты только в окружении сервера, grep по diff на ключи пуст"]
    during = ["деплой одним скриптом, без ручных правок на сервере", "следить за логом, не прерывать на полпути"]
    after = ["health-проба отвечает 200 / статус ok", "ручной просмотр главной страницы на 375px и 1440px",
             "a11y_check и html_lint на выданном HTML", "метрика/лог ошибок за 10 минут без роста"]
    rollback = ["вернуть предыдущий тег/копию", "повторить health-пробу", "записать причину в журнал"]
    extra = {"web": ["кэш/CDN сброшен, версия ассетов в URL"],
             "server": ["probe-файлы свежие (server_status_summary)", "место на диске и память в норме до рестарта"],
             "nox": ["модель/контекст не перезапускать без проверки holder/топологии", "NOX_MASTER не менять без владельца"]}
    return {"kind": kind, "protected": list(args.get("protected", [])),
            "before": before, "during": during + extra[kind], "after": after, "rollback": rollback}


# ---------- server_status_summary ----------
_OK = {"ok", "healthy", "up", "running", "pass", "passed", "active", "true"}
_BAD = {"fail", "failed", "down", "error", "dead", "unhealthy", "false", "inactive"}


def _probe_state(text):
    try:
        d = json.loads(text)
    except ValueError:
        d = None
    if isinstance(d, dict):
        for k in ("ok", "status", "state", "healthy", "result"):
            if k in d:
                v = str(d[k]).strip().lower()
                if v in _OK:
                    return "ok", d
                if v in _BAD:
                    return "fail", d
        return "unknown", d
    low = text.lower()
    if re.search(r"\b(fail|error|down|dead|unhealthy)\b", low):
        return "fail", None
    if re.search(r"\b(ok|healthy|up|running|pass)\b", low):
        return "ok", None
    return "unknown", None


@tool("server_status_summary", "Сводка статуса сервера из probe-файлов (json/txt): ok/fail/unknown, свежесть.",
      {"dir": "каталог с probe-файлами", "stale_after_s": "int, по умолч. 600", "now": "epoch (для тестов)"})
def server_status_summary(args):
    root = args["dir"]
    now = float(args.get("now", time.time()))
    stale = int(args.get("stale_after_s", 600))
    items = []
    for name in sorted(os.listdir(root)):
        p = os.path.join(root, name)
        if not os.path.isfile(p) or not name.lower().endswith((".json", ".txt", ".log", ".probe")):
            continue
        with open(p, encoding="utf-8", errors="replace") as f:
            state, d = _probe_state(f.read(20000))
        age = int(now - os.path.getmtime(p))
        items.append({"probe": name, "state": state, "age_s": age, "stale": age > stale})
    counts = {s: sum(1 for i in items if i["state"] == s) for s in ("ok", "fail", "unknown")}
    stale_n = sum(1 for i in items if i["stale"])
    overall = "fail" if counts["fail"] else ("degraded" if stale_n or counts["unknown"] else ("ok" if items else "no-data"))
    head = f"{overall.upper()}: ok={counts['ok']} fail={counts['fail']} unknown={counts['unknown']} stale={stale_n}"
    return {"overall": overall, "counts": counts, "stale": stale_n, "items": items,
            "summary": head + "".join(f"\n- {i['probe']}: {i['state']}" + (" (устарел)" if i["stale"] else "")
                                      for i in items if i["state"] != "ok" or i["stale"])}


# ---------- advisor_review ----------
@tool("advisor_review", "Отправить патч на ревью советникам (nox_advisors.review). Секреты/пути блокируются фильтром.",
      {"patch": "str, diff/текст", "task": "str", "acceptance": "str", "config": "путь к advisors.json"})
def advisor_review(args, _advisors=None):
    sys.path.insert(0, os.path.join(HERE, "..", "advisors"))
    import nox_advisors as na
    patch = str(args["patch"])
    kinds = na.find_sensitive(patch) + na.find_sensitive(str(args.get("task", "")))
    if kinds:
        return {"verdict": None, "blocked": True, "reason": "в патче/задаче секреты или пути: " + ",".join(sorted(set(kinds))),
                "label": na.ADVISOR_LABEL}
    res = na.review(str(args.get("task", "")), str(args.get("acceptance", "")), patch,
                    args.get("config"), _advisors=_advisors)
    res.update({"blocked": False, "label": na.ADVISOR_LABEL, "applied": False})
    return res


# ---------- registry / CLI ----------
def run_tool(name, args):
    if name not in TOOLS:
        raise KeyError("unknown tool: " + name)
    return TOOLS[name]["fn"](args)


def manifest():
    return {"name": "nox_practical_tools", "version": 1, "runtime": "python3-stdlib",
            "entry": "nox_practical.py", "call": "python3 nox_practical.py <tool> '<json args>'",
            "read_only": True,
            "tools": [{"name": n, "description": t["description"], "params": t["params"]}
                      for n, t in TOOLS.items()]}


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] == "--list":
        print("\n".join(f"{n}: {t['description']}" for n, t in TOOLS.items()))
        return 0
    if argv[0] == "--manifest":
        print(json.dumps(manifest(), ensure_ascii=False, indent=2))
        return 0
    try:
        args = json.loads(argv[1]) if len(argv) > 1 else {}
        out = run_tool(argv[0], args)
    except (KeyError, ValueError, RuntimeError, OSError) as e:
        print(json.dumps({"error": f"{type(e).__name__}: {e}"}, ensure_ascii=False))
        return 2
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
