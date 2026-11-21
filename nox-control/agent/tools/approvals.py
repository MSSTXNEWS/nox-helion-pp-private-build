"""Очередь подтверждений владельца. Файл JSONL (только дозапись, последнее решение побеждает).
Запрос:  {"id","ts","type":"request","action","detail","key","run_id"}
Решение: {"id","ts","type":"decision","decision":"approved"|"denied","by"}   (пишет владелец: CLI ниже или вручную)
Одобрение одноразовое: после использования дописывается {"type":"consumed"}."""
import fcntl, hashlib, json, os, sys, time


def _key(action, detail):
    return hashlib.sha1((action + "|" + str(detail)).encode("utf-8")).hexdigest()[:16]


class Approvals:
    def __init__(self, path):
        self.path = path

    def _append(self, rec):
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def _read(self):
        out = []
        try:
            with open(self.path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try: out.append(json.loads(line))
                        except ValueError: pass
        except FileNotFoundError:
            pass
        return out

    def requests(self):
        """Список запросов с текущим состоянием: pending | approved | denied | consumed."""
        reqs, order = {}, []
        for r in self._read():
            i = r.get("id")
            if r.get("type") == "request" and i not in reqs:
                reqs[i] = dict(r, state="pending"); order.append(i)
            elif i in reqs:
                if r.get("type") == "decision" and reqs[i]["state"] in ("pending", "approved", "denied"):
                    reqs[i]["state"] = r.get("decision", "pending"); reqs[i]["by"] = r.get("by")
                elif r.get("type") == "consumed":
                    reqs[i]["state"] = "consumed"
        return [reqs[i] for i in order]

    def pending(self):
        return [r for r in self.requests() if r["state"] == "pending"]

    def gate(self, action, detail, key=None, run_id=""):
        """Если для (action, detail) есть одобренный необработанный запрос, потребляет его и возвращает approved.
        Иначе возвращает denied/pending (создавая запрос, если открытого нет)."""
        key = key or _key(action, detail)
        mine = [r for r in self.requests() if r.get("key") == key]
        for r in reversed(mine):
            if r["state"] == "approved":
                self._append({"id": r["id"], "ts": time.time(), "type": "consumed"})
                return {"state": "approved", "id": r["id"]}
        for r in reversed(mine):
            if r["state"] == "denied": return {"state": "denied", "id": r["id"]}
            if r["state"] == "pending": return {"state": "pending", "id": r["id"]}
        rid = "ap-%s-%s" % (time.strftime("%Y%m%d%H%M%S"), key[:6])
        self._append({"id": rid, "ts": time.time(), "type": "request", "action": action, "detail": str(detail)[:2000], "key": key, "run_id": run_id})
        return {"state": "pending", "id": rid}

    def decide(self, rid, decision, by="owner"):
        if decision not in ("approved", "denied"): raise ValueError("approved|denied")
        if not any(r["id"] == rid for r in self.requests()): raise KeyError(rid)
        self._append({"id": rid, "ts": time.time(), "type": "decision", "decision": decision, "by": by})


def main(argv=None):
    a = list(sys.argv[1:] if argv is None else argv)
    from ..config import Config
    ap = Approvals(Config().approvals_file)
    if not a or a[0] == "list":
        for r in ap.requests(): print("%s\t%s\t%s\t%s" % (r["id"], r["state"], r["action"], r["detail"][:120]))
        return 0
    if a[0] in ("approve", "deny") and len(a) > 1:
        try: ap.decide(a[1], "approved" if a[0] == "approve" else "denied")
        except KeyError: print("нет такого запроса"); return 1
        print("ok"); return 0
    print("usage: approvals list | approve ID | deny ID"); return 2


if __name__ == "__main__":
    sys.exit(main())
