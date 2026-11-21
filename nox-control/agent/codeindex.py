"""Индекс собственного кода (шаг 36): SQLite FTS5 по файлам, символам и docstring. Запрос «где у меня X» -> путь:строка.
Python разбирается через ast (классы, функции, методы, docstring модуля); Markdown: заголовки; shell/JS: функции регулярками.
Индекс инкрементальный (по mtime+размеру). Только stdlib."""
import ast, fnmatch, os, re, sqlite3, sys, time
from .skills import terms, fts_query

SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", "BACKUPS", ".claude", ".mypy_cache", "dist", "build"}
EXTS = {".py": "py", ".md": "md", ".sh": "sh", ".js": "js", ".mjs": "js"}
MAX_BYTES = 1_000_000
CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def split_ident(name):
    """snake_case/CamelCase -> слова: `build_core_block` -> `build core block`."""
    return " ".join(w.lower() for w in re.split(r"[_\W]+", CAMEL.sub("_", name)) if w)


def _doc_first(d, n=400):
    if not d: return ""
    return re.sub(r"\s+", " ", d.strip())[:n]


def parse_py(src):
    """-> [(kind, qualname, line, doc)]. SyntaxError даёт пустой список."""
    try:
        tree = ast.parse(src)
    except (SyntaxError, ValueError):
        return []
    out = []
    md = ast.get_docstring(tree)
    if md: out.append(("module", "", 1, _doc_first(md)))

    def walk(body, prefix):
        for n in body:
            if isinstance(n, ast.ClassDef):
                q = prefix + n.name
                out.append(("class", q, n.lineno, _doc_first(ast.get_docstring(n))))
                walk(n.body, q + ".")
            elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                q = prefix + n.name
                out.append(("method" if prefix else "function", q, n.lineno, _doc_first(ast.get_docstring(n))))
    walk(tree.body, "")
    return out


def parse_md(src):
    return [("heading", m.group(2).strip(), src.count("\n", 0, m.start()) + 1, "") for m in re.finditer(r"^(#{1,4})\s+(.+)$", src, re.M)]


def parse_sh(src):
    out = []
    for m in re.finditer(r"^\s*(?:function\s+)?([A-Za-z_][\w-]*)\s*\(\)\s*\{", src, re.M):
        out.append(("function", m.group(1), src.count("\n", 0, m.start()) + 1, ""))
    head = re.match(r"(?:#![^\n]*\n)?((?:#[^\n]*\n)+)", src)
    if head: out.insert(0, ("module", "", 1, _doc_first(re.sub(r"^#\s?", "", head.group(1), flags=re.M))))
    return out


def parse_js(src):
    out = []
    for m in re.finditer(r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)|^\s*(?:export\s+)?class\s+([A-Za-z_$][\w$]*)|^\s*(?:export\s+)?const\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\(", src, re.M):
        name = m.group(1) or m.group(2) or m.group(3)
        out.append(("class" if m.group(2) else "function", name, src.count("\n", 0, m.start()) + 1, ""))
    return out


PARSERS = {"py": parse_py, "md": parse_md, "sh": parse_sh, "js": parse_js}


class CodeIndex:
    def __init__(self, db_path, root, exclude=None):
        self.root = os.path.realpath(root)
        self.exclude = exclude or []
        if db_path != ":memory:": os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self.db = sqlite3.connect(db_path, timeout=30, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("CREATE TABLE IF NOT EXISTS files(path TEXT PRIMARY KEY, mtime REAL, size INTEGER, lang TEXT, doc TEXT)")
        self.db.execute("CREATE TABLE IF NOT EXISTS symbols(id INTEGER PRIMARY KEY, path TEXT, symbol TEXT, kind TEXT, line INTEGER, doc TEXT)")
        self.db.execute("CREATE INDEX IF NOT EXISTS symbols_path ON symbols(path)")
        try:
            self.db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS sym_fts USING fts5(path, symbol, words, doc, tokenize='unicode61 remove_diacritics 2')")
            self.fts = True
        except sqlite3.OperationalError:
            self.fts = False
        self.db.commit()

    def _files(self):
        for d, dirs, names in os.walk(self.root):
            dirs[:] = sorted(x for x in dirs if x not in SKIP_DIRS and not x.startswith(".git"))
            for n in sorted(names):
                ext = os.path.splitext(n)[1].lower()
                if ext not in EXTS: continue
                rel = os.path.relpath(os.path.join(d, n), self.root)
                if any(fnmatch.fnmatch(rel, p) for p in self.exclude): continue
                yield rel, EXTS[ext]

    def _drop(self, path):
        ids = [r[0] for r in self.db.execute("SELECT id FROM symbols WHERE path=?", (path,))]
        if self.fts:
            for i in ids: self.db.execute("DELETE FROM sym_fts WHERE rowid=?", (i,))
        self.db.execute("DELETE FROM symbols WHERE path=?", (path,))
        self.db.execute("DELETE FROM files WHERE path=?", (path,))

    def build(self):
        """Инкрементальная переиндексация. -> {"files","updated","removed","symbols"}."""
        seen, updated = set(), 0
        known = {r["path"]: (r["mtime"], r["size"]) for r in self.db.execute("SELECT path,mtime,size FROM files")}
        for rel, lang in self._files():
            seen.add(rel)
            full = os.path.join(self.root, rel)
            try: stt = os.stat(full)
            except OSError: continue
            if stt.st_size > MAX_BYTES: continue
            if known.get(rel) == (stt.st_mtime, stt.st_size): continue
            try:
                with open(full, encoding="utf-8", errors="replace") as f: src = f.read()
            except OSError:
                continue
            self._drop(rel)
            syms = PARSERS[lang](src)
            mod_doc = next((d for k, q, l, d in syms if k == "module"), "")
            self.db.execute("INSERT INTO files(path,mtime,size,lang,doc) VALUES(?,?,?,?,?)", (rel, stt.st_mtime, stt.st_size, lang, mod_doc))
            rows = [("file", os.path.basename(rel), 1, mod_doc)] + [(k, q or os.path.basename(rel), l, d) for k, q, l, d in syms if k != "module"]
            for kind, q, line, doc in rows:
                cur = self.db.execute("INSERT INTO symbols(path,symbol,kind,line,doc) VALUES(?,?,?,?,?)", (rel, q, kind, line, doc))
                if self.fts:
                    self.db.execute("INSERT INTO sym_fts(rowid,path,symbol,words,doc) VALUES(?,?,?,?,?)",
                                    (cur.lastrowid, " ".join(split_ident(p) for p in re.split(r"[/.]", rel)), q, split_ident(q.replace(".", "_")), " ".join(terms(doc, False))))
            updated += 1
        removed = [p for p in known if p not in seen]
        for p in removed: self._drop(p)
        self.db.commit()
        n = self.db.execute("SELECT COUNT(*) FROM symbols").fetchone()[0]
        return {"files": len(seen), "updated": updated, "removed": len(removed), "symbols": n}

    def where(self, query, k=8):
        """«Где у меня X»: [{path, line, symbol, kind, doc, score}] по убыванию релевантности."""
        q = fts_query(query)
        if not q: return []
        rows = []
        if self.fts:
            try:
                rows = self.db.execute("SELECT s.path,s.line,s.symbol,s.kind,s.doc FROM sym_fts f JOIN symbols s ON s.id=f.rowid WHERE sym_fts MATCH ? "
                                       "ORDER BY bm25(sym_fts, 1.0, 6.0, 5.0, 2.0) LIMIT ?", (q, k)).fetchall()
            except sqlite3.OperationalError:
                rows = []
        if not rows:
            ts = terms(query)
            cand = []
            for r in self.db.execute("SELECT path,line,symbol,kind,doc FROM symbols"):
                hay = (r["path"] + " " + split_ident(r["symbol"].replace(".", "_")) + " " + r["symbol"] + " " + r["doc"]).lower().replace("ё", "е")
                s = sum(1 for t in ts if t in hay)
                if s: cand.append((s, r))
            rows = [r for _s, r in sorted(cand, key=lambda x: -x[0])[:k]]
        return [{"path": r["path"], "line": r["line"], "symbol": r["symbol"], "kind": r["kind"], "doc": r["doc"][:200], "at": "%s:%d" % (r["path"], r["line"])} for r in rows]

    def stats(self):
        return {"files": self.db.execute("SELECT COUNT(*) FROM files").fetchone()[0], "symbols": self.db.execute("SELECT COUNT(*) FROM symbols").fetchone()[0], "fts": self.fts}


def main(argv=None):
    from .config import Config
    a = list(sys.argv[1:] if argv is None else argv)
    cfg = Config()
    ix = CodeIndex(cfg.code_db, cfg.repo)
    if a and a[0] == "build":
        print(ix.build()); return 0
    if len(a) >= 2 and a[0] == "where":
        ix.build()
        for h in ix.where(" ".join(a[1:])): print("%s\t%s %s\t%s" % (h["at"], h["kind"], h["symbol"], h["doc"][:100]))
        return 0
    print("usage: codeindex build | where <что ищем>"); return 2


if __name__ == "__main__":
    sys.exit(main())
