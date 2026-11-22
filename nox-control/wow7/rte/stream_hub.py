"""RTE-02 stream_hub.py: asyncio-хаб ходов диалога. Генерация живёт в своей задаче и НЕ зависит от HTTP-соединения клиента:
 - события ходов упорядочены turn_id + seq, SSE `id: <turn_id>:<seq>`; переподключение с Last-Event-ID доигрывает пропущенное без дублей;
 - идемпотентный старт (conversation_id, client_msg_id): повтор POST после обрыва не запускает вторую генерацию;
 - один conversation_id для полного и мини-чата (источник source=full|mini, общая история);
 - heartbeat — настоящие data-кадры (event: hb, без id), прокси не считает поток пустым;
 - журнал ходов в jsonl (переживает рестарт хаба; незавершённые помечаются error:restart)."""
import os as _os, sys as _sys  # общие модули COMMON (statefile/quiet/fastq/datafence)
for _c in (_os.environ.get("NOX_COMMON", ""), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "COMMON"), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "common"), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "common")):
    if _c and _os.path.isdir(_c) and _c not in _sys.path:
        _sys.path.append(_c)
import statefile
import asyncio, json, os, time, uuid

TERMINAL = ("done", "error", "stopped")


def parse_last_event_id(value, turn_id):
    """'turn:seq' -> seq. Чужой turn_id или мусор -> 0 (отдаём ход с начала, клиент дедуплицирует по seq)."""
    try:
        t, _, s = (value or "").rpartition(":")
        return int(s) if t == turn_id and int(s) >= 0 else 0
    except ValueError:
        return 0


def to_sse(turn_id, ev, compat=None):
    """Кадр SSE. compat='openai' -> chat.completion.chunk для текущего веба; иначе нативный."""
    if ev["type"] == "hb":
        return ("event: hb\ndata: " + json.dumps(ev, ensure_ascii=False) + "\n\n").encode()
    head = "id: %s:%d\n" % (turn_id, ev["seq"])
    if compat == "openai":
        nox = {"turn_id": turn_id, "seq": ev["seq"], "stage": ev.get("stage"), "type": ev["type"]}
        if ev["type"] == "delta":
            o = {"object": "chat.completion.chunk", "model": "nox", "choices": [{"index": 0, "delta": {"content": ev["text"], "nox_stage": ev.get("stage")}, "finish_reason": None}], "nox": nox}
            return (head + "data: " + json.dumps(o, ensure_ascii=False) + "\n\n").encode()
        if ev["type"] in TERMINAL:
            nox.update({k: v for k, v in ev.items() if k not in ("seq", "type", "t")})
            o = {"object": "chat.completion.chunk", "model": "nox", "choices": [{"index": 0, "delta": {}, "finish_reason": "stop" if ev["type"] != "error" else "error"}], "nox": nox}
            return (head + "data: " + json.dumps(o, ensure_ascii=False) + "\n\ndata: [DONE]\n\n").encode()
        o = {"object": "chat.completion.chunk", "model": "nox", "choices": [{"index": 0, "delta": {}, "finish_reason": None}], "nox": dict(nox, **{k: v for k, v in ev.items() if k not in ("seq", "type", "t")})}
        return (head + "data: " + json.dumps(o, ensure_ascii=False) + "\n\n").encode()
    return (head + "event: " + ev["type"] + "\ndata: " + json.dumps(ev, ensure_ascii=False) + "\n\n").encode()


class Turn:
    def __init__(self, turn_id, conv_id, client_msg_id, user_text, source, persist_path=None):
        self.id, self.conv_id, self.client_msg_id, self.user_text, self.source = turn_id, conv_id, client_msg_id, user_text, source
        self.events, self.status = [], "running"
        self.cond = asyncio.Condition()
        self.task = None
        self.created, self.finished_at = time.time(), None
        self.stop_requested, self.frames_dropped_after_stop = False, 0
        self.upstream = {}          # request_id шлюза, слот и т.п. (кладёт продюсер, читает stop.py)
        self._path = persist_path
        self.hb_s = 3.0

    @property
    def text(self):
        return "".join(e["text"] for e in self.events if e["type"] == "delta")

    async def publish(self, type, **data):
        """Добавляет событие; после запроса STOP дельты не публикуются, а считаются (квитанция)."""
        if type in TERMINAL and self.status != "running":
            return None
        if type == "delta" and self.stop_requested:
            self.frames_dropped_after_stop += 1
            return None
        ev = {"seq": len(self.events) + 1, "type": type, "t": round(time.time(), 3)}
        ev.update(data)
        self.events.append(ev)
        if self._path:
            try:
                with open(self._path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(ev, ensure_ascii=False) + "\n")
            except OSError:
                self._path = None      # диск недоступен: поток живёт, журнал отключён
        if type in TERMINAL:
            self.status = {"done": "done", "error": "error", "stopped": "stopped"}[type]
            self.finished_at = time.time()
        async with self.cond:
            self.cond.notify_all()
        return ev

    async def subscribe(self, after=0):
        """Асинхронный итератор событий с seq > after, затем живые; между ними hb-кадры без seq."""
        i = max(int(after), 0)
        while True:
            while i < len(self.events):
                yield self.events[i]
                i += 1
            if self.status != "running":
                if i >= len(self.events):
                    return
                continue
            async with self.cond:
                if i >= len(self.events) and self.status == "running":
                    try:
                        await asyncio.wait_for(self.cond.wait(), self.hb_s)
                    except asyncio.TimeoutError:
                        yield {"type": "hb", "t": round(time.time(), 3), "elapsed_s": round(time.time() - self.created, 1), "last_seq": len(self.events)}

    def summary(self):
        return {"turn_id": self.id, "conversation_id": self.conv_id, "status": self.status, "last_seq": len(self.events), "source": self.source,
                "client_msg_id": self.client_msg_id, "chars": len(self.text)}


class Hub:
    """producer: async def producer(turn, messages, opts) — публикует turn.publish('delta'|'stage'|'meta', ...) и возвращается; хаб ставит done/error."""

    def __init__(self, producer, persist_dir=None, ttl_s=1800.0, max_turns=500, max_history=40):
        self.producer, self.dir, self.ttl, self.max_turns, self.max_history = producer, persist_dir, ttl_s, max_turns, max_history
        self.turns, self.convs, self.keys = {}, {}, {}
        if persist_dir:
            os.makedirs(persist_dir, exist_ok=True)

    # ---- диалоги
    def conversation(self, conv_id=None):
        cid = conv_id or "c-" + uuid.uuid4().hex[:12]
        return self.convs.setdefault(cid, {"id": cid, "messages": [], "turns": [], "created": time.time()})

    def history(self, conv_id):
        return list(self.conversation(conv_id)["messages"])

    def running_turn(self, conv_id):
        for tid in reversed(self.conversation(conv_id)["turns"]):
            t = self.turns.get(tid)
            if t and t.status == "running":
                return t
        return None

    # ---- ходы
    def start_turn(self, conv_id, client_msg_id, user_text, source="full", opts=None):
        """-> (turn, state): 'created' | 'duplicate' (тот же client_msg_id: вернули существующий) | 'busy' (идёт другой ход этого диалога)."""
        conv = self.conversation(conv_id)
        key = (conv["id"], client_msg_id)
        if client_msg_id and key in self.keys:
            return self.turns[self.keys[key]], "duplicate"
        run = self.running_turn(conv["id"])
        if run:
            return run, "busy"
        self._gc()
        tid = "t-" + uuid.uuid4().hex[:12]
        turn = Turn(tid, conv["id"], client_msg_id, user_text, source, os.path.join(self.dir, tid + ".jsonl") if self.dir else None)
        self.turns[tid] = turn
        if client_msg_id:
            self.keys[key] = tid
        conv["turns"].append(tid)
        messages = list(conv["messages"]) + [{"role": "user", "content": user_text}]
        conv["messages"].append({"role": "user", "content": user_text, "source": source, "turn_id": tid})
        turn.task = asyncio.ensure_future(self._run(turn, messages, dict(opts or {}, source=source)))
        return turn, "created"

    async def _run(self, turn, messages, opts):
        await turn.publish("meta", conversation_id=turn.conv_id, source=turn.source, client_msg_id=turn.client_msg_id, text=turn.user_text[:400])   # text: для RTE-11/12 (журнал самонастройки)
        try:
            await self.producer(turn, [{k: v for k, v in m.items() if k in ("role", "content")} for m in messages][-self.max_history:], opts)
            await turn.publish("done", chars=len(turn.text))
        except asyncio.CancelledError:
            if not turn.stop_requested:
                await turn.publish("error", code="cancelled", message="ход прерван")
        except Exception as e:  # продюсер сам объясняет причину; здесь — страховка
            await turn.publish("error", code="producer_failed", message="%s: %s" % (type(e).__name__, e))
        finally:
            self._finish_conv(turn)

    def _finish_conv(self, turn):
        conv = self.conversation(turn.conv_id)
        if turn.text and not any(m.get("turn_id") == turn.id and m["role"] == "assistant" for m in conv["messages"]):
            conv["messages"].append({"role": "assistant", "content": turn.text, "turn_id": turn.id, "stopped": turn.status == "stopped"})
        if self.dir:
            try:
                statefile.save(os.path.join(self.dir, "conv_%s.json" % conv["id"]), conv)
            except OSError:
                pass

    def finish_stopped(self, turn):
        """Вызывает stop.py после публикации stopped: фиксирует частичный текст в истории."""
        self._finish_conv(turn)

    def get(self, turn_id):
        return self.turns.get(turn_id)

    def _gc(self):
        now = time.time()
        for tid, t in list(self.turns.items()):
            if t.status != "running" and t.finished_at and (now - t.finished_at > self.ttl or len(self.turns) > self.max_turns):
                self.turns.pop(tid, None)
                self.keys = {k: v for k, v in self.keys.items() if v != tid}

    # ---- восстановление после рестарта
    def load(self):
        if not self.dir:
            return 0
        n = 0
        for name in sorted(os.listdir(self.dir)):
            p = os.path.join(self.dir, name)
            if name.startswith("conv_") and name.endswith(".json"):
                try:
                    with open(p, encoding="utf-8") as fh:
                        c = json.load(fh)
                    self.convs[c["id"]] = c
                except Exception:
                    continue
        for name in sorted(os.listdir(self.dir)):
            if not (name.startswith("t-") and name.endswith(".jsonl")):
                continue
            p = os.path.join(self.dir, name)
            evs = []
            with open(p, encoding="utf-8") as fh:
                for line in fh:
                    try:
                        evs.append(json.loads(line))
                    except ValueError:
                        break
            if not evs or evs[0].get("type") != "meta":
                continue
            m = evs[0]
            t = Turn(name[:-6], m.get("conversation_id"), m.get("client_msg_id"), "", m.get("source", "full"), p)
            t.events = evs
            last = evs[-1]["type"]
            t.status = {"done": "done", "error": "error", "stopped": "stopped"}.get(last, "error")
            t.finished_at = os.path.getmtime(p)
            if last not in TERMINAL:
                t.events.append({"seq": len(evs) + 1, "type": "error", "t": round(time.time(), 3), "code": "restart", "message": "хаб перезапущен во время ответа"})
                with open(p, "a", encoding="utf-8") as f:
                    f.write(json.dumps(t.events[-1], ensure_ascii=False) + "\n")
            self.turns[t.id] = t
            if t.client_msg_id:
                self.keys[(t.conv_id, t.client_msg_id)] = t.id
            conv = self.conversation(t.conv_id)
            if t.id not in conv["turns"]:
                conv["turns"].append(t.id)
            n += 1
        return n
