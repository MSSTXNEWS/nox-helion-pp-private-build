"""Импорт старой памяти/личности в Store из каталога распакованного бэкапа.

Формат файла определяется по СОДЕРЖИМОМУ: SQLite (сигнатура), JSON, JSONL, Markdown/текст.
Структура бэкапа заранее неизвестна, поэтому разбор терпимый: тип записи (факт/эпизод/личность/
владелец/установки) выводится из имени файла/таблицы/ключей и полей записи. Всё, что не удалось
принять, попадает в отчёт с причиной. Ничего не удаляется, исходные файлы читаются только на чтение.
"""
import hashlib
import json
import os
import re
import sqlite3
import time

from .s03_store import SECRET_RE, parse_ts, ref_of
from riverse_ladder import norm_text

TEXT_FIELDS = ("text", "content", "value", "fact", "memory", "body", "message", "summary", "note",
               "description", "statement", "utterance", "запись", "текст", "факт")
TS_FIELDS = ("ts", "timestamp", "created", "created_at", "time", "date", "datetime", "updated_at", "когда")
SKIP_EXT = {".zst", ".zstd", ".gz", ".tgz", ".xz", ".bz2", ".zip", ".tar", ".7z", ".png", ".jpg", ".jpeg", ".gif",
            ".webp", ".pdf", ".bin", ".pt", ".pth", ".gguf", ".safetensors", ".npy", ".npz", ".pyc", ".so",
            ".mp3", ".wav", ".mp4", ".onnx", ".pkl", ".lock", ".wal", ".shm", ".journal"}
SQL_AUX = re.compile(r"(^sqlite_|_fts(_\w+)?$|_(data|idx|content|docsize|config)$)")
MAX_FILE = 64 * 1024 * 1024
MAX_FACT, MAX_EPISODE, MIN_LEN = 1000, 8000, 3
HINTS = [("persona", re.compile(r"persona|soul|identity|personalit|character|личност|душ|характер|стиль", re.I)),
         ("settings", re.compile(r"setting|config|rules?|prefs?|preferences|установ|настрой|правил|предпочт", re.I)),
         ("owner", re.compile(r"owner|user|profile|about|владел|хозяин|мессир|профил", re.I)),
         ("episode", re.compile(r"episod|chat|conversation|dialog|history|messages?|diary|journal|log|эпизод|диалог|истори|дневник|журнал", re.I)),
         ("fact", re.compile(r"fact|memor|knowledge|notes?|факт|знани|памят", re.I))]
PROFILE_HINTS = {"persona": "persona", "owner": "owner", "settings": "settings"}


def hint_of(*parts):
    s = " ".join(str(p) for p in parts if p)
    for name, rx in HINTS:
        if rx.search(s):
            return name
    return "fact"


class Report:
    def __init__(self, root, dry):
        self.root, self.dry, self.files, self.skipped = root, dry, [], []
        self.totals = {"facts": 0, "episodes": 0, "profile": 0, "updated": 0, "rejected": 0}
        self.reasons = {}
        self.cur = None

    def begin(self, rel, fmt):
        self.cur = {"path": rel, "format": fmt, "facts": 0, "episodes": 0, "profile": 0, "updated": 0, "rejected": {}}
        self.files.append(self.cur)

    def ok(self, kind):
        self.cur[kind] += 1
        self.totals[kind if kind in self.totals else "facts"] += 1

    def rej(self, reason, n=1):
        self.cur["rejected"][reason] = self.cur["rejected"].get(reason, 0) + n
        self.reasons[reason] = self.reasons.get(reason, 0) + n
        self.totals["rejected"] += n

    def as_dict(self):
        return {"root": self.root, "dry_run": self.dry, "totals": self.totals, "rejected_reasons": self.reasons,
                "files": self.files, "skipped_files": self.skipped}

    def text(self):
        t = self.totals
        out = ["Импорт из %s%s: принято фактов %d, эпизодов %d, записей профиля %d (обновлено %d); отброшено %d." % (
            self.root, " (пробный, без записи)" if self.dry else "", t["facts"], t["episodes"], t["profile"], t["updated"], t["rejected"])]
        for r, n in sorted(self.reasons.items(), key=lambda x: -x[1]):
            out.append("  отброшено %d: %s" % (n, r))
        for f in self.skipped:
            out.append("  файл пропущен: %s (%s)" % (f["path"], f["reason"]))
        return "\n".join(out)


class Importer:
    def __init__(self, store, root, actor="import", dry_run=False):
        self.s, self.root, self.actor, self.dry = store, root, actor, dry_run
        self.rep = Report(root, dry_run)
        self.seen = set()
        self.source = "import"

    # --- приёмники с проверками ---
    def _check(self, text, limit):
        t = (text or "").strip() if isinstance(text, str) else ("" if text is None else str(text).strip())
        if not t:
            return None, "пусто"
        if len(t) < MIN_LEN:
            return None, "слишком коротко (< %d символов)" % MIN_LEN
        if len(t) > limit:
            return None, "слишком длинно (> %d символов), разбейте на части" % limit
        if SECRET_RE.search(t):
            return None, "похоже на секрет (ключ/пароль/токен), в память не берём"
        return t, None

    def fact(self, text, kind, ts):
        t, why = self._check(text, MAX_FACT)
        if why:
            return self.rep.rej(why)
        key = ("f", norm_text(t))
        if key in self.seen or self.s.db.execute("SELECT 1 FROM mem_facts WHERE key=? AND status='active'", (key[1],)).fetchone():
            return self.rep.rej("дубликат (уже есть в памяти или в этом импорте)")
        self.seen.add(key)
        if not self.dry:
            self.s.add_fact(t, kind=kind, source=self.source, source_kind="import", ts=ts, actor=self.actor)
        self.rep.ok("facts")

    def episode(self, text, role, ts, session):
        t, why = self._check(text, MAX_EPISODE)
        if why:
            return self.rep.rej(why)
        k = norm_text("%s|%s|%s" % (role, int(ts), t))
        if ("e", k) in self.seen or self.s.db.execute("SELECT 1 FROM mem_episodes WHERE key=? AND status='active'", (k,)).fetchone():
            return self.rep.rej("дубликат (уже есть в памяти или в этом импорте)")
        self.seen.add(("e", k))
        if not self.dry:
            self.s.add_episode(t, role=role or "user", ts=ts, session=session, source=self.source)
        self.rep.ok("episodes")

    def profile(self, key, value, section):
        k = re.sub(r"\s+", " ", str(key)).strip()[:120]
        v, why = self._check(value, MAX_EPISODE)
        if not k:
            return self.rep.rej("пустой ключ профиля")
        if why:
            return self.rep.rej(why)
        old = self.s.db.execute("SELECT value, source FROM mem_profile WHERE key=? AND status='active'", (k,)).fetchone()
        if ("p", k) in self.seen:
            return self.rep.rej("дубликат ключа профиля в этом импорте")
        if old and old[0] == v:
            return self.rep.rej("дубликат (в профиле уже то же значение)")
        if old and not str(old[1] or "").startswith("import"):
            return self.rep.rej("в профиле уже есть другое значение, заданное не импортом (не перезаписываю)")
        self.seen.add(("p", k))
        if not self.dry:
            self.s.set_profile(k, v, section, source=self.source, actor=self.actor)
        self.rep.ok("profile")
        if old:
            self.rep.cur["updated"] += 1
            self.rep.totals["updated"] += 1

    # --- записи ---
    def record(self, rec, hint, stem, default_ts):
        lk = {str(k).lower(): v for k, v in rec.items()}
        rec_h = hint_of(*[lk.get(f) for f in ("type", "kind", "category", "section") if isinstance(lk.get(f), str)])
        h = rec_h if rec_h != "fact" else hint_of(hint)
        text = next((self._text(lk.get(f)) for f in TEXT_FIELDS if self._text(lk.get(f))), None)
        ts = next((parse_ts(lk[f]) for f in TS_FIELDS if lk.get(f) not in (None, "") and parse_ts(lk[f]) is not None), default_ts)
        if "key" in lk and ("value" in lk or "val" in lk) and not any(f in lk for f in ("text", "content", "fact", "memory")):
            return self.profile(lk["key"], lk.get("value", lk.get("val")), PROFILE_HINTS.get(h, "other"))
        if text is None:
            sc = {k: v for k, v in rec.items() if isinstance(v, (str, int, float)) and not isinstance(v, bool) and str(v).strip()}
            sc = {k: v for k, v in sc.items() if str(k).lower() not in TS_FIELDS and str(k).lower() not in ("id", "uuid")}
            if not sc:
                return self.rep.rej("нет текстового поля")
            for k, v in sc.items():
                self.profile("%s/%s" % (stem, k) if h in PROFILE_HINTS else k, v, PROFILE_HINTS.get(h, "other"))
            return
        if h == "episode":
            role = lk.get("role") or lk.get("sender") or lk.get("author") or "user"
            if isinstance(role, dict):
                role = role.get("role", "user")
            return self.episode(text, str(role), ts or time.time(), lk.get("session") or lk.get("conversation_id") or stem)
        if h in PROFILE_HINTS:
            k = lk.get("key") or lk.get("name") or lk.get("title") or "%s/%s" % (stem, hashlib.sha1(text.encode()).hexdigest()[:8])
            return self.profile(k, text, PROFILE_HINTS[h])
        return self.fact(text, "fact", ts or time.time())

    def walk(self, obj, hint, stem, ts):
        if isinstance(obj, list):
            for it in obj:
                if isinstance(it, dict):
                    self.record(it, hint, stem, ts) if self._is_record(it) else self.walk(it, hint, stem, ts)
                elif isinstance(it, str):
                    self.record({"text": it}, hint, stem, ts)
                elif isinstance(it, list):
                    self.walk(it, hint, stem, ts)
        elif isinstance(obj, dict):
            if self._is_record(obj):
                return self.record(obj, hint, stem, ts)
            scal = {k: v for k, v in obj.items() if not isinstance(v, (dict, list))}
            for k, v in obj.items():
                if isinstance(v, (dict, list)):
                    self.walk(v, "%s %s" % (hint, k), stem, ts)
            if scal:
                self.record(scal, hint, stem, ts)

    @staticmethod
    def _text(v):
        if isinstance(v, str):
            return v if v.strip() else None
        if isinstance(v, list):
            parts = [x if isinstance(x, str) else (x.get("text") if isinstance(x, dict) and isinstance(x.get("text"), str) else "") for x in v]
            j = "\n".join(p for p in parts if p).strip()
            return j or None
        return None

    @classmethod
    def _is_record(cls, d):
        lk = {str(k).lower(): v for k, v in d.items()}
        if any(cls._text(lk.get(f)) for f in TEXT_FIELDS):
            return True
        return ("key" in lk and ("value" in lk or "val" in lk))

    # --- форматы ---
    def sqlite_file(self, path, rel, ts):
        self.rep.begin(rel, "sqlite")
        try:
            con = sqlite3.connect("file:%s?mode=ro" % path.replace("?", "%3f"), uri=True)
            tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        except sqlite3.Error as e:
            return self.rep.rej("SQLite не открылся: %s" % e)
        try:
            for t in tables:
                if SQL_AUX.search(t):
                    continue
                cols = [r[1] for r in con.execute('PRAGMA table_info("%s")' % t.replace('"', '""'))]
                try:
                    cur = con.execute('SELECT * FROM "%s"' % t.replace('"', '""'))
                    for row in cur:
                        rec = {c: v for c, v in zip(cols, row) if isinstance(v, (str, int, float))}
                        if not any(str(c).lower() in TEXT_FIELDS or str(c).lower() == "key" for c in cols):
                            self.rep.rej("таблица %s без текстового столбца" % t)
                            break
                        self.record(rec, "%s %s" % (os.path.basename(path), t), t, ts)
                except sqlite3.Error as e:
                    self.rep.rej("таблица %s не читается: %s" % (t, e))
        finally:
            con.close()

    def json_file(self, data, rel, stem, ts, fmt):
        self.rep.begin(rel, fmt)
        self.walk(data, rel, stem, ts)

    def text_file(self, text, rel, stem, ts):
        self.rep.begin(rel, "markdown/текст")
        h = hint_of(rel)
        blocks, head, body = [], stem, []
        for line in text.splitlines():
            m = re.match(r"^\s{0,3}#{1,6}\s+(.*\S)\s*$", line)
            if m:
                blocks.append((head, body)); head, body = m.group(1), []
            else:
                body.append(line)
        blocks.append((head, body))
        for head, body in blocks:
            paras = [p.strip() for p in re.split(r"\n\s*\n", "\n".join(body)) if p.strip()]
            if h in ("persona", "settings"):
                chunks, cur = [], ""
                for p in paras:
                    if cur and len(cur) + len(p) >= 1500:
                        chunks.append(cur); cur = p
                    else:
                        cur = (cur + "\n\n" + p).strip()
                if cur:
                    chunks.append(cur)
                for i, c in enumerate(chunks):
                    self.profile("%s/%s" % (stem, head) + (" (часть %d)" % (i + 1) if len(chunks) > 1 else ""), c, PROFILE_HINTS[h])
                continue
            for p in paras:
                items = [re.sub(r"^\s*(?:[-*+]|\d+[.)])\s+(?:\[[ xX]\]\s+)?", "", ln).strip() for ln in p.splitlines()
                         if re.match(r"^\s*(?:[-*+]|\d+[.)])\s+", ln)]
                if not items:
                    items = [re.sub(r"\s+", " ", p)]
                for it in items:
                    if h == "episode":
                        self.episode(it, "note", ts, stem)
                    else:
                        self.fact(it, {"owner": "owner", "settings": "setting"}.get(h, "fact"), ts)

    # --- файл ---
    def file(self, path):
        rel = os.path.relpath(path, self.root)
        ext = os.path.splitext(path)[1].lower()
        try:
            st = os.stat(path)
            if ext in SKIP_EXT:
                self.rep.skipped.append({"path": rel, "reason": "архив/двоичный (%s); распакуйте/конвертируйте" % ext}); return
            if st.st_size > MAX_FILE:
                self.rep.skipped.append({"path": rel, "reason": "больше %d МБ" % (MAX_FILE >> 20)}); return
            if st.st_size == 0:
                self.rep.skipped.append({"path": rel, "reason": "пустой файл"}); return
            with open(path, "rb") as f:
                raw = f.read()
        except OSError as e:
            self.rep.skipped.append({"path": rel, "reason": "не читается: %s" % e}); return
        self.source = "import:" + rel
        stem = os.path.splitext(os.path.basename(path))[0]
        ts = st.st_mtime
        if raw.startswith(b"SQLite format 3\x00"):
            return self.sqlite_file(path, rel, ts)
        if b"\x00" in raw[:8192]:
            self.rep.skipped.append({"path": rel, "reason": "двоичное содержимое, формат не распознан"}); return
        text = raw.decode("utf-8-sig", errors="replace")
        if text.count("�") > max(3, len(text) // 50):
            try:
                text = raw.decode("cp1251")
            except UnicodeDecodeError:
                pass
        body = text.strip()
        if body[:1] in "[{":
            try:
                return self.json_file(json.loads(body), rel, stem, ts, "json")
            except ValueError:
                pass
            lines = [ln for ln in body.splitlines() if ln.strip()]
            objs = []
            for ln in lines:
                try:
                    objs.append(json.loads(ln))
                except ValueError:
                    pass
            if lines and len(objs) * 2 >= len(lines):
                self.json_file(objs, rel, stem, ts, "jsonl")
                if len(objs) < len(lines):
                    self.rep.rej("битая строка JSONL", len(lines) - len(objs))
                return
        elif "\n" in body and body[:1] != "#":
            objs = []
            lines = [ln for ln in body.splitlines() if ln.strip()]
            for ln in lines:
                if ln.lstrip()[:1] == "{":
                    try:
                        objs.append(json.loads(ln))
                    except ValueError:
                        pass
            if lines and len(objs) * 2 >= len(lines):
                self.json_file(objs, rel, stem, ts, "jsonl")
                if len(objs) < len(lines):
                    self.rep.rej("битая строка JSONL", len(lines) - len(objs))
                return
        self.text_file(text, rel, stem, ts)

    def run(self):
        if not os.path.isdir(self.root):
            raise FileNotFoundError("нет каталога бэкапа: %s" % self.root)
        for dp, dn, fn in os.walk(self.root):
            dn.sort()
            for name in sorted(fn):
                p = os.path.join(dp, name)
                if os.path.islink(p):
                    self.rep.skipped.append({"path": os.path.relpath(p, self.root), "reason": "символическая ссылка"})
                    continue
                self.file(p)
        if not self.dry:
            self.s.db.execute("INSERT INTO mem_import_reports(ts,root,report) VALUES(?,?,?)",
                              (time.time(), self.root, json.dumps(self.rep.as_dict(), ensure_ascii=False)))
            self.s.db.commit()
        return self.rep


def import_tree(store, root, actor="import", dry_run=False):
    """Вернуть Report (as_dict()/text()). dry_run=True - только посчитать, ничего не писать."""
    return Importer(store, root, actor, dry_run).run()
