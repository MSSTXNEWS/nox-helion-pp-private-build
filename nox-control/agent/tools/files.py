"""read_file / write_file / edit_file: только внутри рабочей ветки репо (worktree), запись только если HEAD = nox/*."""
import fnmatch, os, re, subprocess
from . import Tool, err

DENY_NAMES = (".env", ".env.*", "*.pem", "*.key", "id_rsa*", "id_ed25519*", "id_ecdsa*", ".netrc", ".git-credentials", "credentials*", "secrets*", "*.p12", "*.pfx")
DENY_DIRS = {".git", ".ssh", ".aws", ".kube", ".gnupg", "secrets", "__pycache__"}
MAX_WRITE = 500_000
BRANCH_RE = re.compile(r"^nox/[a-z0-9][a-z0-9._/-]{0,80}$")


def current_branch(workdir):
    try:
        r = subprocess.run(["git", "-C", workdir, "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True, timeout=15)
        return r.stdout.strip() if r.returncode == 0 else None
    except Exception:
        return None


def resolve(ctx, path, for_write=False):
    """-> (abs_path, None) или (None, ошибка)."""
    if not isinstance(path, str) or not path or "\x00" in path: return None, "пустой путь"
    root = ctx.workdir
    p = os.path.realpath(path if os.path.isabs(path) else os.path.join(root, path))
    if p != root and not p.startswith(root + os.sep): return None, "путь вне рабочей ветки: " + path
    rel = os.path.relpath(p, root)
    parts = rel.split(os.sep)
    if any(x in DENY_DIRS for x in parts if x != "__pycache__" or for_write): return None, "каталог запрещён: " + rel
    base = os.path.basename(p)
    if any(fnmatch.fnmatch(base, pat) for pat in DENY_NAMES): return None, "файл с секретами запрещён: " + rel
    return p, None


def _guard_write(ctx):
    b = current_branch(ctx.workdir)
    if b is None: return "рабочая папка не git-репозиторий"
    if not BRANCH_RE.match(b): return "правки только в ветке nox/<задача>; сейчас ветка %r" % b
    return None


def read_file(a, ctx):
    p, e = resolve(ctx, a["path"])
    if e: return err(e)
    if os.path.isdir(p):
        names = sorted(os.listdir(p))
        names = [n + ("/" if os.path.isdir(os.path.join(p, n)) else "") for n in names if n not in DENY_DIRS][:300]
        return {"ok": True, "dir": os.path.relpath(p, ctx.workdir), "entries": names}
    if not os.path.isfile(p): return err("нет файла: " + a["path"])
    if os.path.getsize(p) > 5_000_000 and not a.get("start"): return err("файл больше 5 МБ: задай start/end")
    with open(p, "rb") as f:
        raw = f.read(5_000_000)
    if b"\x00" in raw[:4096]: return err("двоичный файл")
    lines = raw.decode("utf-8", "replace").splitlines()
    s = max(int(a.get("start") or 1), 1)
    en = min(int(a.get("end") or s + 399), s + 799, len(lines))
    body = "\n".join("%d\t%s" % (i, lines[i - 1]) for i in range(s, en + 1))
    return {"ok": True, "path": os.path.relpath(p, ctx.workdir), "total_lines": len(lines), "start": s, "end": en, "text": body}


def write_file(a, ctx):
    g = _guard_write(ctx)
    if g: return err(g, denied=True)
    p, e = resolve(ctx, a["path"], True)
    if e: return err(e)
    c = a["content"]
    if len(c.encode("utf-8")) > MAX_WRITE: return err("файл больше %d байт" % MAX_WRITE)
    if os.path.isdir(p): return err("это каталог")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    existed = os.path.exists(p)
    tmp = p + ".tmp%d" % os.getpid()
    with open(tmp, "w", encoding="utf-8") as f: f.write(c)
    os.replace(tmp, p)
    return {"ok": True, "path": os.path.relpath(p, ctx.workdir), "bytes": len(c.encode("utf-8")), "created": not existed}


def edit_file(a, ctx):
    g = _guard_write(ctx)
    if g: return err(g, denied=True)
    p, e = resolve(ctx, a["path"], True)
    if e: return err(e)
    if not os.path.isfile(p): return err("нет файла: " + a["path"])
    with open(p, encoding="utf-8") as f: s = f.read()
    old, new = a["old"], a["new"]
    if not old: return err("old пустой")
    n = s.count(old)
    if n == 0: return err("old не найден в файле (проверь пробелы и отступы)")
    if n > 1 and not a.get("replace_all"): return err("old встречается %d раз: дай более длинный фрагмент или replace_all=true" % n)
    s2 = s.replace(old, new) if a.get("replace_all") else s.replace(old, new, 1)
    tmp = p + ".tmp%d" % os.getpid()
    with open(tmp, "w", encoding="utf-8") as f: f.write(s2)
    os.replace(tmp, p)
    return {"ok": True, "path": os.path.relpath(p, ctx.workdir), "replaced": n if a.get("replace_all") else 1}


S = "string"
TOOLS = [
    Tool("read_file", "Прочитать файл рабочей ветки (с номерами строк) или список каталога.",
         {"type": "object", "properties": {"path": {"type": S}, "start": {"type": "integer"}, "end": {"type": "integer"}}, "required": ["path"]}, read_file),
    Tool("write_file", "Создать/перезаписать файл в рабочей ветке (только ветка nox/*).",
         {"type": "object", "properties": {"path": {"type": S}, "content": {"type": S}}, "required": ["path", "content"]}, write_file),
    Tool("edit_file", "Заменить фрагмент old на new в файле (old должен быть уникален, либо replace_all).",
         {"type": "object", "properties": {"path": {"type": S}, "old": {"type": S}, "new": {"type": S}, "replace_all": {"type": "boolean"}}, "required": ["path", "old", "new"]}, edit_file),
]
