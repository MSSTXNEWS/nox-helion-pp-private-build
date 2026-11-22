"""life_journal: ЕДИНЫЙ append-only журнал жизни NOX (life_journal.jsonl) с хеш-цепочкой (= Genesis Ledger v5 §0.6).

Запись: {"seq","ts","kind","source","text","data","prev","hash"}; hash = sha256(prev + канонический JSON записи без hash).
kind: milestone | fact | thought | chapter | event.  Писатель «главы дня» - ТОЛЬКО MEM/autobio (kind=chapter, source=autobio);
CON (вехи) и PER (development) пишут события через append() - прямой записи в журнал в обход этого API нет.
Блокировка и fsync - COMMON/statefile. verify(path) -> (ok, n, первая_битая_запись).
"""
import hashlib
import json
import os
import sys
import time

for _c in (os.environ.get("NOX_COMMON", ""), os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "COMMON"),
           os.path.join(os.path.dirname(os.path.abspath(__file__)), "common"), os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "common")):
    if _c and os.path.isdir(_c) and _c not in sys.path:
        sys.path.append(_c)
import statefile  # noqa: E402

KINDS = ("milestone", "fact", "thought", "chapter", "event")
GENESIS = "0" * 64


def default_path(state_dir=None):
    return os.environ.get("NOX_LIFE_JOURNAL") or os.path.join(state_dir or os.environ.get("NOX_STATE", "/root/nox/state"), "life_journal.jsonl")


def _canon(rec):
    return json.dumps({k: v for k, v in rec.items() if k != "hash"}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(rec):
    return hashlib.sha256((rec["prev"] + _canon(rec)).encode("utf-8")).hexdigest()


def _last(path):
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - 65536))
            lines = [x for x in f.read().decode("utf-8", "replace").split("\n") if x.strip()]
        return json.loads(lines[-1]) if lines else None
    except (OSError, ValueError, IndexError):
        return None


class LifeJournal:
    def __init__(self, path=None, clock=time.time):
        self.path, self.clock = path or default_path(), clock

    def append(self, kind, text, source, data=None, ts=None):
        if kind not in KINDS:
            raise ValueError("life_journal: kind=%r" % kind)
        with statefile.locked(self.path):
            last = _last(self.path)
            rec = {"seq": (last["seq"] + 1) if last else 1, "ts": self.clock() if ts is None else ts, "kind": kind,
                   "source": str(source)[:20], "text": str(text)[:1500], "data": data or {}, "prev": last["hash"] if last else GENESIS}
            rec["hash"] = _hash(rec)
            fd = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
            try:
                os.write(fd, (json.dumps(rec, ensure_ascii=False) + "\n").encode("utf-8"))
                os.fsync(fd)
            finally:
                os.close(fd)
        return rec

    def read(self, kinds=None, limit=None):
        out = []
        try:
            with open(self.path, encoding="utf-8") as f:
                for ln in f:
                    if ln.strip():
                        r = json.loads(ln)
                        if not kinds or r["kind"] in kinds:
                            out.append(r)
        except (OSError, ValueError):
            pass
        return out[-limit:] if limit else out

    def verify(self):
        return verify(self.path)


def verify(path):
    prev, n = GENESIS, 0
    try:
        with open(path, encoding="utf-8") as f:
            for ln in f:
                if not ln.strip():
                    continue
                r = json.loads(ln)
                n += 1
                if r.get("prev") != prev or r.get("hash") != _hash(r) or r.get("seq") != n:
                    return False, n, r.get("seq")
                prev = r["hash"]
    except OSError:
        return True, 0, None
    except ValueError:
        return False, n + 1, None
    return True, n, None


if __name__ == "__main__":
    p = sys.argv[1] if len(sys.argv) > 1 else default_path()
    ok, n, bad = verify(p)
    print(json.dumps({"path": p, "ok": ok, "records": n, "first_bad": bad}))
    sys.exit(0 if ok else 1)
