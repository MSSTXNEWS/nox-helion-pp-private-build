"""RTE-03 stop.py: настоящий STOP с серверной квитанцией.
Шаги: (1) turn.stop_requested -> новые дельты не публикуются и считаются; (2) снимок /slots llama-server (n_decoded занятого слота);
(3) отмена задачи продюсера -> закрытие сокета к шлюзу/апстриму (llama-server отменяет задачу при разрыве) + POST /v1/stop шлюзу;
(4) снимок после среза и опрос /slots до простоя слота (2 чтения подряд) -> tokens_after_stop = прирост n_decoded после отмены (нижняя оценка, basis указан);
(5) событие `stopped` с квитанцией в поток + файл квитанции.
Честность: если /slots недоступен, tokens_after_stop = null и verified = false (0 не выдумываем)."""
import asyncio, json, os, time
import aio


def parse_slots(obj):
    """/slots -> [{'id', 'busy', 'n_decoded'}]. Формат llama.cpp: список слотов; next_token может быть списком или словарём."""
    out = []
    if not isinstance(obj, list):
        return out
    for s in obj:
        if not isinstance(s, dict):
            continue
        nt = s.get("next_token")
        if isinstance(nt, list):
            nt = nt[0] if nt else {}
        nt = nt if isinstance(nt, dict) else {}
        n = nt.get("n_decoded", s.get("n_decoded"))
        busy = s.get("is_processing")
        if busy is None:
            busy = s.get("state") not in (0, None)
        out.append({"id": s.get("id"), "busy": bool(busy), "n_decoded": int(n) if isinstance(n, (int, float)) else None})
    return out


class StopController:
    def __init__(self, hub, slots_url=None, gateway_url=None, receipts_dir="/root/nox/receipts", settle_s=4.0, poll_s=0.15):
        self.hub, self.slots_url, self.gateway_url = hub, slots_url, gateway_url
        self.receipts_dir, self.settle_s, self.poll_s = receipts_dir, settle_s, poll_s

    async def _slots(self):
        if not self.slots_url:
            return None
        try:
            st, obj = await aio.json_call("GET", self.slots_url.rstrip("/") + "/slots", None, 2.0)
            return parse_slots(obj) if st == 200 else None
        except Exception:
            return None

    async def stop(self, turn_id):
        turn = self.hub.get(turn_id)
        if turn is None:
            return {"ok": False, "error": "unknown_turn", "turn_id": turn_id}
        if turn.status != "running":
            return {"ok": True, "turn_id": turn_id, "already": turn.status, "receipt": turn.upstream.get("stop_receipt")}
        t0 = time.time()
        before = await self._slots()
        base = {s["id"]: s["n_decoded"] for s in (before or []) if s["busy"] and s["n_decoded"] is not None}
        turn.stop_requested = True
        rid = turn.upstream.get("request_id")
        task = turn.task
        if task and not task.done():
            task.cancel()                       # finally продюсера закрывает сокет к апстриму
            try:
                await asyncio.wait_for(asyncio.shield(task), 3.0)
            except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
                pass
        gw = None
        if self.gateway_url and rid:
            try:
                st, obj = await aio.json_call("POST", self.gateway_url.rstrip("/") + "/v1/stop", {"request_id": rid}, 2.0)
                gw = {"status": st, "stopped": (obj or {}).get("stopped")}
            except Exception as e:
                gw = {"error": type(e).__name__}
        # ---- проверка простоя слота. База «после среза»: токены, добитые между снимком и закрытием сокета, - это латентность отмены, а не отказ сервера остановиться
        # (иначе квитанция флапала: +1 токен за 20 мс гонки). Считаем рост n_decoded ПОСЛЕ закрытия апстрима.
        cut = await self._slots() if before is not None else None
        if cut is not None:
            base = {s["id"]: s["n_decoded"] for s in cut if s["busy"] and s["n_decoded"] is not None}
        seen_max = dict(base)
        idle_reads, first_idle, polls, slots_ok = 0, None, 0, before is not None
        deadline = time.time() + self.settle_s
        while slots_ok and time.time() < deadline:
            cur = await self._slots()
            polls += 1
            if cur is None:
                slots_ok = False
                break
            busy = [s for s in cur if s["busy"]]
            for s in busy:
                if s["n_decoded"] is not None:
                    seen_max[s["id"]] = max(seen_max.get(s["id"], s["n_decoded"]), s["n_decoded"])
            if not busy:
                idle_reads += 1
                first_idle = first_idle if first_idle is not None else round(time.time() - t0, 3)
                if idle_reads >= 2:
                    break
            else:
                idle_reads = 0
            await asyncio.sleep(self.poll_s)
        verified = slots_ok and idle_reads >= 2
        if slots_ok:
            after = sum(max(seen_max.get(i, 0) - b, 0) for i, b in base.items())
            basis = "slots_n_decoded_delta" if base else "no_busy_slot_at_stop"
        else:
            after, basis = None, "slots_unavailable"
        receipt = {"turn_id": turn.id, "conversation_id": turn.conv_id, "stop_requested_at": round(t0, 3), "request_id": rid,
                   "upstream_closed": bool(task is None or task.done() or turn.upstream.get("closed")), "gateway_stop": gw,
                   "slot_idle": bool(verified), "slot_idle_after_s": first_idle, "slot_polls": polls,
                   "tokens_after_stop": after, "tokens_after_stop_basis": basis, "frames_dropped_after_stop": turn.frames_dropped_after_stop,
                   "partial_chars": len(turn.text), "verified": bool(verified and after == 0), "settle_s": self.settle_s}
        turn.upstream["stop_receipt"] = receipt
        await turn.publish("stopped", receipt=receipt)
        self.hub.finish_stopped(turn)
        self._write(receipt)
        return {"ok": True, "turn_id": turn.id, "receipt": receipt}

    def _write(self, receipt):
        if not self.receipts_dir:
            return
        try:
            os.makedirs(self.receipts_dir, exist_ok=True)
            p = os.path.join(self.receipts_dir, "RTE-stop-%s.json" % receipt["turn_id"])
            with open(p, "w", encoding="utf-8") as f:
                json.dump(receipt, f, ensure_ascii=False, indent=1)
        except OSError:
            pass
