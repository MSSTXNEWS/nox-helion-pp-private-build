#!/usr/bin/env python3
"""backup_memory: резервная копия и восстановление памяти S03 (SQLite) - раз в час.

  backup   - онлайн-копия через sqlite3 backup API (безопасно при работающем сервисе), запись во
             временный файл -> проверка integrity_check -> sha256 + JSON-метка -> атомарное переименование,
             ротация: хранится N новейших копий (старые копии удаляются ТОЛЬКО этим скриптом, только в --dir).
  verify   - проверить контрольную сумму и integrity_check копии.
  restore  - восстановить копию в базу: проверка суммы и целостности ДО замены; текущая база не удаляется,
             а переименовывается в <db>.before-restore-<время>.
  list     - показать копии.
  cron     - напечатать готовую строку cron / systemd-таймер.
Только stdlib. Коды выхода: 0 успех, 1 ошибка, 2 неверные аргументы.
"""
import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import time

PREFIX, EXT = "memory-", ".sqlite3"
TABLES = ("mem_facts", "mem_episodes", "mem_profile", "mem_changes")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def integrity(path):
    con = sqlite3.connect("file:%s?mode=ro" % path, uri=True)
    try:
        r = con.execute("PRAGMA integrity_check").fetchall()
        return r == [("ok",)], [x[0] for x in r][:5]
    finally:
        con.close()


def counts(path):
    con = sqlite3.connect("file:%s?mode=ro" % path, uri=True)
    try:
        out = {}
        for t in TABLES:
            try:
                out[t] = con.execute("SELECT COUNT(*) FROM %s" % t).fetchone()[0]
            except sqlite3.Error:
                out[t] = None
        return out
    finally:
        con.close()


def list_backups(bdir):
    res = []
    if not os.path.isdir(bdir):
        return res
    for n in sorted(os.listdir(bdir)):
        if n.startswith(PREFIX) and n.endswith(EXT) and os.path.exists(os.path.join(bdir, n + ".json")):
            with open(os.path.join(bdir, n + ".json"), encoding="utf-8") as f:
                try:
                    meta = json.load(f)
                except ValueError:
                    continue
            res.append(dict(meta, file=n, path=os.path.join(bdir, n)))
    return res


def backup(db, bdir, keep=24, now=None):
    if not os.path.isfile(db):
        raise FileNotFoundError("нет базы памяти: %s" % db)
    os.makedirs(bdir, exist_ok=True)
    now = now if now is not None else time.time()
    stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime(now))
    # Reserve each filename atomically: two overlapping backup jobs and two
    # invocations with identical timestamps must never replace a good S03 copy.
    # The zero-byte reservation is deliberately not a verified backup until
    # its matching metadata is committed.
    for serial in range(10000):
        name = PREFIX + stamp + ("-%d" % serial if serial else "") + EXT
        final = os.path.join(bdir, name)
        if os.path.lexists(final + ".json") or os.path.lexists(final + ".json.tmp"):
            continue
        try:
            fd = os.open(final, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            continue
        os.close(fd)
        break
    else:
        raise RuntimeError("не удалось зарезервировать уникальное имя копии S03")

    tmp = os.path.join(bdir, "." + name + ".tmp")
    meta_tmp = final + ".json.tmp"
    tmp_owned = False
    meta_owned = False
    try:
        if os.path.lexists(tmp) or os.path.lexists(meta_tmp):
            raise RuntimeError("обнаружен незавершённый временный файл копии: HOLD")
        src = sqlite3.connect("file:%s?mode=ro" % db, uri=True)
        try:
            dst = sqlite3.connect(tmp)
            tmp_owned = True
            try:
                src.backup(dst)
            finally:
                dst.close()
        finally:
            src.close()
        # SQLite's default umask must not expose private S03 backup bytes.
        os.chmod(tmp, 0o600)
        ok, detail = integrity(tmp)
        if not ok:
            raise RuntimeError("копия не прошла integrity_check: %s" % detail)
        meta = {"created": now, "sha256": sha256_file(tmp),
                "size": os.path.getsize(tmp), "source": os.path.abspath(db),
                "counts": counts(tmp), "integrity": "ok"}
        with open(meta_tmp, "x", encoding="utf-8") as f:
            meta_owned = True
            json.dump(meta, f, ensure_ascii=False, indent=1)
        os.replace(tmp, final)  # replaces only our own exclusive reservation
        tmp_owned = False
        os.replace(meta_tmp, final + ".json")
        meta_owned = False
    except Exception:
        # Never unlink a pre-existing temporary file owned by another run.
        for p, owned in ((tmp, tmp_owned), (meta_tmp, meta_owned), (final, True)):
            if owned:
                try:
                    os.remove(p)
                except FileNotFoundError:
                    pass
        raise
    removed = rotate(bdir, keep)
    return dict(meta, file=name, path=final, rotated_out=removed)

def rotate(bdir, keep):
    """Оставить `keep` новейших копий (минимум 1). Возвращает имена удалённых."""
    keep = max(1, int(keep))
    items = sorted(list_backups(bdir), key=lambda m: (m["created"], m["file"]))
    gone = []
    for m in items[:-keep]:
        for p in (m["path"], m["path"] + ".json"):
            try:
                os.remove(p)
            except FileNotFoundError:
                pass
        gone.append(m["file"])
    return gone


def verify(path):
    """-> (ok, сообщение). Сверяет sha256 из метки и integrity_check."""
    meta_p = path + ".json"
    if not os.path.isfile(path):
        return False, "нет файла копии"
    if not os.path.isfile(meta_p):
        return False, "нет файла с контрольной суммой (.json)"
    with open(meta_p, encoding="utf-8") as f:
        meta = json.load(f)
    if sha256_file(path) != meta.get("sha256"):
        return False, "контрольная сумма не совпала (копия повреждена)"
    ok, detail = integrity(path)
    if not ok:
        return False, "integrity_check: %s" % detail
    return True, "ok: sha256 совпала, integrity_check ok, строки: %s" % meta.get("counts")


def restore(backup_path, db, force=False):
    ok, msg = verify(backup_path)
    if not ok:
        raise RuntimeError("восстановление отменено: " + msg)
    tmp = db + ".restore.tmp"
    d = os.path.dirname(os.path.abspath(db))
    os.makedirs(d, exist_ok=True)
    shutil.copyfile(backup_path, tmp)
    try:
        ok, detail = integrity(tmp)
        with open(backup_path + ".json", encoding="utf-8") as mf:
            want = json.load(mf)["sha256"]
        if not ok or sha256_file(tmp) != want:
            raise RuntimeError("копия повредилась при копировании")
        kept = None
        if os.path.exists(db):
            if not force and _in_use(db):
                raise RuntimeError("база занята (идёт запись); остановите сервис или используйте --force")
            kept = "%s.before-restore-%s" % (db, time.strftime("%Y%m%d-%H%M%S"))
            # A second restore in the same second must never overwrite the
            # previous pre-restore database (or either of its SQLite sidecars).
            if any(os.path.lexists(kept + ext) for ext in ("", "-wal", "-shm")):
                raise RuntimeError("предыдущая копия перед восстановлением уже существует: " + kept)
            moved = []
            try:
                for ext in ("", "-wal", "-shm"):
                    if os.path.lexists(db + ext):
                        os.replace(db + ext, kept + ext)
                        moved.append(ext)
                os.replace(tmp, db)
            except OSError as exc:
                # If installation failed after moving the original away,
                # recover only into vacant paths. Never overwrite another
                # process's newly created database during an ambiguous race.
                if os.path.lexists(db):
                    raise RuntimeError("восстановление прервано: проверьте прежнюю базу в " + kept) from exc
                failures = []
                for ext in reversed(moved):
                    try:
                        os.replace(kept + ext, db + ext)
                    except OSError:
                        failures.append(ext or "db")
                if failures:
                    raise RuntimeError("откат неполный (%s): прежняя база в %s" % (",".join(failures), kept)) from exc
                raise
        else:
            # Orphaned WAL/SHM must not attach to a newly restored main DB.
            if any(os.path.lexists(db + ext) for ext in ("-wal", "-shm")):
                raise RuntimeError("осиротевшие SQLite WAL/SHM без основной базы: HOLD")
            os.replace(tmp, db)
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
    return {"restored_from": backup_path, "db": db, "previous_kept_as": kept, "check": verify(backup_path)[1]}


def _in_use(db):
    try:
        con = sqlite3.connect(db, timeout=0.2)
        con.execute("BEGIN IMMEDIATE")
        con.rollback()
        con.close()
        return False
    except sqlite3.Error:
        return True


def cron_line(db, bdir, keep, python=None):
    """Строка для crontab: каждый час на 7-й минуте; лог рядом с копиями."""
    return "7 * * * * %s %s backup --db %s --dir %s --keep %d >> %s 2>&1" % (
        python or sys.executable or "python3", os.path.abspath(__file__), db, bdir, keep, os.path.join(bdir, "backup.log"))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    envdb = os.environ.get("NOX_MEMORY_DB", "")
    envdir = os.environ.get("NOX_MEMORY_BACKUP_DIR", "")
    for name in ("backup", "list", "cron"):
        p = sub.add_parser(name)
        p.add_argument("--db", default=envdb)
        p.add_argument("--dir", default=envdir)
        p.add_argument("--keep", type=int, default=int(os.environ.get("NOX_MEMORY_BACKUP_KEEP", "24")))
    pv = sub.add_parser("verify"); pv.add_argument("file")
    pr = sub.add_parser("restore"); pr.add_argument("file"); pr.add_argument("--db", default=envdb); pr.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    try:
        if a.cmd in ("backup", "cron") and not (a.db and a.dir) or a.cmd == "list" and not a.dir or a.cmd == "restore" and not a.db:
            print("нужны --db/--dir (или env NOX_MEMORY_DB, NOX_MEMORY_BACKUP_DIR)", file=sys.stderr)
            return 2
        if a.cmd == "backup":
            r = backup(a.db, a.dir, a.keep)
            print(json.dumps({k: r[k] for k in ("file", "sha256", "size", "counts", "rotated_out")}, ensure_ascii=False))
        elif a.cmd == "list":
            for m in list_backups(a.dir):
                print("%s  %s  %d байт  %s" % (time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(m["created"])), m["file"], m["size"], m["counts"]))
        elif a.cmd == "verify":
            ok, msg = verify(a.file); print(msg); return 0 if ok else 1
        elif a.cmd == "restore":
            print(json.dumps(restore(a.file, a.db, a.force), ensure_ascii=False))
        elif a.cmd == "cron":
            print(cron_line(os.path.abspath(a.db), os.path.abspath(a.dir), a.keep))
        return 0
    except (OSError, RuntimeError, sqlite3.Error, ValueError) as e:
        print("ошибка: %s" % e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
