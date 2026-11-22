"""statefile: единственный способ писать JSON-состояние NOX (REVIEW_1 п.4.3, исправление 6).

save(path, obj)   - tmp + fsync + os.replace + fsync каталога, под межпроцессной блокировкой fcntl.flock(<path>.lock);
                    в dict добавляется "_schema" (версия схемы) и "_rev" (счётчик записей, растёт на 1).
load(path, default) - читает под общей блокировкой; служебные ключи _schema/_rev убираются; битый/пустой файл -> default.
update(path, fn, default) - read-modify-write ЦЕЛИКОМ под эксклюзивной блокировкой (нет потерянных обновлений между процессами).
locked(path)      - контекст-менеджер эксклюзивной блокировки (для составных операций).
write_bytes(path, data) - то же для байт/текста без служебных ключей.
append_line(path, line) - дозапись строки в jsonl под блокировкой (O_APPEND + fsync).
CLI: python3 statefile.py --check <dir>  - ищет в каталоге JSON без _schema (диагностика).
"""
import contextlib
import json
import os
import sys
import tempfile

try:
    import fcntl
except ImportError:  # pragma: no cover  (не-POSIX: блокировка деградирует до no-op)
    fcntl = None

SCHEMA = 1
META = ("_schema", "_rev")


@contextlib.contextmanager
def locked(path, shared=False):
    lp = path + ".lock"
    d = os.path.dirname(os.path.abspath(lp))
    os.makedirs(d, exist_ok=True)
    fd = os.open(lp, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        if fcntl:
            fcntl.flock(fd, fcntl.LOCK_SH if shared else fcntl.LOCK_EX)
        yield
    finally:
        try:
            if fcntl:
                fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def _read(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read()
        return json.loads(raw) if raw.strip() else default
    except (OSError, ValueError):
        return default


def _strip(o):
    if isinstance(o, dict) and any(k in o for k in META):
        o = {k: v for k, v in o.items() if k not in META}
    return o


def _write_locked(path, obj, schema, indent, ensure_ascii):
    cur = _read(path, None)
    rev = (cur.get("_rev", 0) if isinstance(cur, dict) else 0) + 1
    if isinstance(obj, dict):
        obj = dict(_strip(obj))
        obj["_schema"] = schema
        obj["_rev"] = rev
    d = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(prefix=os.path.basename(path) + ".", suffix=".tmp", dir=d)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=ensure_ascii, indent=indent)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    try:
        dfd = os.open(d, os.O_RDONLY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    except OSError:
        pass
    return rev


def save(path, obj, schema=SCHEMA, indent=None, ensure_ascii=False):
    with locked(path):
        return _write_locked(path, obj, schema, indent, ensure_ascii)


def write_bytes(path, data, lock=True):
    """Атомарная запись произвольных байт/текста (квитанции, css, md) под блокировкой, без служебных ключей.
    lock=False - без .lock-файла рядом (файлы рабочих папок задач: единственный писатель, рядом ничего лишнего не оставляем)."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with (locked(path) if lock else contextlib.nullcontext()):
        d = os.path.dirname(os.path.abspath(path))
        fd, tmp = tempfile.mkstemp(prefix=os.path.basename(path) + ".", suffix=".tmp", dir=d)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise


def load(path, default=None):
    if not os.path.exists(path):
        return default
    with locked(path, shared=True):
        return _strip(_read(path, default))


def update(path, fn, default=None, schema=SCHEMA, indent=None, ensure_ascii=False):
    """fn(cur)->new (или мутирует cur и возвращает None). Возвращает новое значение."""
    with locked(path):
        cur = _strip(_read(path, default if default is not None else {}))
        new = fn(cur)
        if new is None:
            new = cur
        _write_locked(path, new, schema, indent, ensure_ascii)
        return new


def append_line(path, line):
    if not line.endswith("\n"):
        line += "\n"
    with locked(path):
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        try:
            os.write(fd, line.encode("utf-8"))
            os.fsync(fd)
        finally:
            os.close(fd)


def rev(path):
    cur = _read(path, None)
    return cur.get("_rev", 0) if isinstance(cur, dict) else 0


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--check":
        bad = []
        for fn in sorted(os.listdir(sys.argv[2])):
            if fn.endswith(".json"):
                o = _read(os.path.join(sys.argv[2], fn), None)
                if isinstance(o, dict) and "_schema" not in o:
                    bad.append(fn)
        print(json.dumps({"no_schema": bad}, ensure_ascii=False))
        sys.exit(1 if bad else 0)
    print(__doc__)
