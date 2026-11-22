# gateway_patch.md — точные места врезки (клон: nox-helion-pp-private-build/nox-control, на момент чтения main)
Принцип: sync-шлюз НЕ переписываем. `rte_server.py` (:8084) стоит перед ним и держит ход/seq/resume/STOP; в шлюзе — 4 малые правки.

## Найденные дефекты (проверены чтением кода)
1. `glm53/qs6_core.py:93` — `if req_mt and mode in ("auto",) and mt is None: mt = req_mt` — мёртвый код: строкой выше (92) `mt` уже не None, если есть effort. Клиентский `max_tokens` для GLM игнорируется.
2. `glm53/glm_profile.py:86-89` — `max_tokens = max(mt, MAX_TOKENS_MIN[effort])` (≥2048 даже для «low»): при ~1,5 ток/с это до ~23 минут вместо ответа на 400 токенов, если thinking выключен.
3. `glm53/gateway.py:70-72` — `/v1/stop` отдаёт только `{"stopped": bool}`: нет проверки, что llama-server перестал считать. Квитанцию даёт `stop.py`.
4. `s1web/web_server.py:50-57` — `/api/chat/stop` закрывает соединение и отвечает `{"ok":true,"stopped":bool}` — тоже без квитанции; `_chat` (стр. 94-110) при падении шлюза отдаёт голый 502 (источник «502» для браузера).
5. `glm53/gateway.py:_sse(": ping")` — комментарные пинги не являются кадрами данных: прокси/клиент, считающий `data:`, видит «0 кадров» всё время размышления GLM. В RTE — `event: stage/hb` с `data:`.

## Правка A — режим deep_only (qs6_core.py:12, после строки "max")
```python
    "deep_only": {"tier": "deep", "effort": None, "max_tokens": None, "expected_tokens": 400, "two_stage": False},   # RTE: только GLM, вступление даёт rte_server
```
`Cfg.__init__` (стр. 47) обновляет только существующие ключи — новый режим появится автоматически.

## Правка B — max_tokens и thinking от плана RTE (qs6_core.py:92-93)
```python
    if mt is None and effort: mt = P.MAX_TOKENS_MIN[effort]
    if req_mt and mode in ("auto", "deep_only"): mt = req_mt          # было: mt is None -> недостижимо
```
и в `glm_profile.build_request` (стр. 86-89):
```python
    need = MAX_TOKENS_MIN[effort]
    if (b.get("chat_template_kwargs") or {}).get("enable_thinking") is False: need = 0   # без размышлений резерв 2048 не нужен
```
`enable_thinking` доходит до llama-server: `_strip_nox` (qs6_core.py:259) пропускает не-`nox_` ключи, `build_request` строка 91 копирует `chat_template_kwargs`.

## Правка C — STOP со ссылкой на слот (gateway.py:70-72), необязательно, но дешёво
```python
            if p == "/v1/stop":
                rid = body.get("request_id") or ""
                return self._json(200, {"request_id": rid, "stopped": st.reg.stop(rid), "active_after": st.reg.active()})
```
Квитанция `tokens_after_stop` строится в `rte_server`/`stop.py` по `/slots` llama-server (:8081), шлюз для этого не нужен.

## Правка D — веб-сервер S1 (s1web/web_server.py)
Добавить в `do_GET`/`do_POST` проксирование `/rte/*` -> `127.0.0.1:8084` по аналогии со строкой 58 (`/glm/`) — **без буферизации, close-delimited SSE**:
```python
        if p.startswith("/rte/"): return self._proxy("POST", p[4:], raw, "127.0.0.1:8084", "RTE (127.0.0.1:8084)")   # do_POST, после строки 58
        if p.startswith("/rte/"): return self._proxy("GET", p[4:] + qs, None, "127.0.0.1:8084", "RTE (127.0.0.1:8084)")   # do_GET, после строки 27
```
`_proxy` (web_server.py:72) заголовок `Last-Event-ID` НЕ передаёт — добавить после строки 72: `if self.headers.get("Last-Event-ID"): hd["Last-Event-ID"] = self.headers["Last-Event-ID"]`. Внешний nginx/Cloudflare: `proxy_buffering off; X-Accel-Buffering: no` (RTE ставит заголовок сам).
`/api/chat/stop` (стр. 50) заменить на вызов `POST /rte/v1/turns/<turn_id>/stop` и возврат квитанции как есть (`{"ok":true,"receipt":{...}}`).

## Правка E — клиент (web/files/nox-web-extras.js, общий для полного и мини-чата)
Один `conversation_id` в localStorage (`nox.conv`), `client_msg_id = crypto.randomUUID()` на каждую отправку.
```js
async function rteSend(text, source){            // source: 'full' | 'mini'
  const conv = localStorage.getItem('nox.conv') || ('c-'+crypto.randomUUID().slice(0,12)); localStorage.setItem('nox.conv', conv);
  const cmid = crypto.randomUUID();
  let r = await fetch('/rte/v1/turns',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({conversation_id:conv,client_msg_id:cmid,message:text,source})});
  const t = await r.json(); if (r.status===409) return attach(t.turn_id);   // идёт ход: подписаться, не стартовать второй
  return attach(t.turn_id);
}
let lastSeq = 0;                                  // дедуп: seq <= lastSeq игнорируем
function attach(turnId){
  const es = new EventSource('/rte/v1/turns/'+turnId+'/events'+(lastSeq?('?after='+lastSeq):''));   // браузер сам шлёт Last-Event-ID при авто-реконнекте
  for (const ty of ['meta','stage','delta','done','error','stopped'])
    es.addEventListener(ty, e => { const ev = JSON.parse(e.data); if (ev.seq <= lastSeq) return; lastSeq = ev.seq; render(ev); if (['done','error','stopped'].includes(ty)) es.close(); });
  es.addEventListener('hb', () => {});            // кадр жизни: сбросить «нет связи»
}
// STOP: fetch('/rte/v1/turns/'+turnId+'/stop',{method:'POST'}).then(r=>r.json()).then(j=>showReceipt(j.receipt))  // показать «остановлено, токенов после стопа: 0»
```
`render(ev)`: `stage==='intro'` — приглушённым стилем, не озвучивать как факт; `memory:false` — в S03 не писать.
Правка-баг из OWNER_GAPS (nox-web-extras.js:37-58): обновлять факт в UI только при `j.ok===true`.

## Что НЕ трогаем
Шлюзовой `two_stage` остаётся для старого `/api/chat`; для RTE-пути он выключен режимом `deep_only` (иначе два вступления).
Запуск: `deploy_rte.sh`, порт 8084, env `NOX_GATEWAY_URL/NOX_DEEP_SLOTS_URL/NOX_FAST_UPSTREAM`. llama-server GLM должен отдавать `/slots` (не запускать с `--no-slots`) — иначе квитанция честно скажет `verified:false`.
