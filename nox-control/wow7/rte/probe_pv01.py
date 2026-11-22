"""RTE-06 probe_pv01.py: живая приёмка P0 чата против rte_server (:8084). Только stdlib. Пишет квитанцию /root/nox/receipts/RTE-06.json.
Проверки: (1) первый кадр < --first-frame-s; (2) есть вступление; (3) обрыв клиента + Last-Event-ID -> без дублей/пропусков, одна генерация;
(4) повтор POST с тем же client_msg_id -> duplicate; (5) мини-чат видит историю полного; (6) STOP -> квитанция slot_idle и tokens_after_stop==0."""
import argparse, asyncio, json, os, sys, time
import aio


async def sse(url, headers=None, limit=None, timeout=20.0):
    st, h, r, w = await aio.open_request("GET", url, None, timeout, headers)
    out, buf = [], b""
    try:
        async for chunk in aio._chunks(r, h):
            buf += chunk
            while b"\n\n" in buf:
                frame, buf = buf.split(b"\n\n", 1)
                cur = {}
                for ln in frame.decode().split("\n"):
                    k, _, v = ln.partition(": ")
                    cur[k] = v
                if "data" in cur:
                    out.append((cur.get("id"), cur.get("event"), json.loads(cur["data"]), time.time()))
                    if limit and len([e for e in out if e[1] in ("delta", "meta", "stage")]) >= limit:
                        return out
    finally:
        w.close()
    return out


async def run_probe(base, message, first_frame_s=2.0, stop_message=None):
    res, t0 = {}, time.time()
    conv = "probe-%d" % int(t0)
    st, t = await aio.json_call("POST", base + "/v1/turns", {"conversation_id": conv, "client_msg_id": "p1", "message": message, "source": "full"}, 10)
    tid = t["turn_id"]
    first = await sse(base + "/v1/turns/%s/events" % tid, limit=3)
    res["first_frame_s"] = round(first[0][3] - t0, 2) if first else None
    res["first_frame_ok"] = bool(first) and first[0][3] - t0 < first_frame_s
    last_id = [e[0] for e in first if e[0]][-1]
    rest = await sse(base + "/v1/turns/%s/events" % tid, {"Last-Event-ID": last_id}, timeout=900)
    allev = [e for e in first + rest if e[1] != "hb"]
    seqs = [int(e[0].split(":")[1]) for e in {e[0]: e for e in allev if e[0]}.values()]
    ids = [e[0] for e in first + rest if e[0] and e[1] != "hb"]
    overlap = len(ids) - len(set(ids))
    res["resume_overlap_frames"] = overlap          # кадры с id из first, повторённые в rest, обязаны отсутствовать
    res["resume_no_dups"] = overlap == 0 and sorted(seqs) == list(range(1, len(seqs) + 1))
    deltas = [e[2] for e in allev if e[1] == "delta"]
    res["intro_present"] = bool(deltas) and deltas[0].get("stage") == "intro"
    res["terminal"] = allev[-1][1] if allev else None
    st, t2 = await aio.json_call("POST", base + "/v1/turns", {"conversation_id": conv, "client_msg_id": "p1", "message": message}, 10)
    res["dup_post_is_duplicate"] = t2.get("state") == "duplicate" and t2.get("turn_id") == tid
    st, c = await aio.json_call("POST", base + "/v1/turns", {"conversation_id": conv, "client_msg_id": "p2", "message": stop_message or message + " Продолжи подробнее.", "source": "mini"}, 10)
    res["mini_shares_conversation"] = c.get("conversation_id") == conv and c.get("state") == "created"
    await asyncio.sleep(3.0)
    st, r = await aio.json_call("POST", base + "/v1/turns/%s/stop" % c["turn_id"], {}, 15)
    rc = r.get("receipt") or {}
    res["stop_receipt"] = rc
    res["stop_ok"] = bool(rc.get("slot_idle")) and rc.get("tokens_after_stop") == 0
    st, cv = await aio.json_call("GET", base + "/v1/conversations/" + conv, None, 5)
    res["history_roles"] = [m["role"] for m in cv["messages"]]
    res["ok"] = all(res[k] for k in ("first_frame_ok", "resume_no_dups", "intro_present", "dup_post_is_duplicate", "mini_shares_conversation", "stop_ok"))
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8084")
    ap.add_argument("--message", default="Объясни подробно, почему архитектура памяти устроена так, и сравни варианты")
    ap.add_argument("--first-frame-s", type=float, default=2.0)
    ap.add_argument("--receipts", default="/root/nox/receipts")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if a.dry_run:
        print(json.dumps({"would_probe": a.base, "receipt": os.path.join(a.receipts, "RTE-06.json")}))
        return 0
    res = asyncio.run(run_probe(a.base, a.message, a.first_frame_s))
    try:
        os.makedirs(a.receipts, exist_ok=True)
        with open(os.path.join(a.receipts, "RTE-06.json"), "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=1)
    except OSError as e:
        print("receipt not written:", e, file=sys.stderr)
    print(json.dumps(res, ensure_ascii=False, indent=1))
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
