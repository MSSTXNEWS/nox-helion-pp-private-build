# Подключение гонки /llm в чат (клиентский фрагмент для C)
Сервис: POST http://127.0.0.1:8810/llm (в браузере /svc/agents/llm). Тело `{"prompt": "...", "system": "...", "max_tokens": 300}`. Ответ `{"answer", "seconds", "by": "local|advisor|advisor(breaker)"}`. Локальная модель не дала первый токен за 8 с -> параллельно советник :8793, берётся первый ответ; поздний локальный ответ пишется как шаг `late`.
Для чата поставить `backend:"main"`; задачи исполнителей уже идут через гонку (15 с).
## JS (браузер)
```js
async function nuxAsk(prompt, system) {
  const ac = new AbortController(); const t = setTimeout(() => ac.abort(), 12000);   // ни одного ожидания >10-12 с без хоть какого-то ответа
  try {
    const r = await fetch('/svc/agents/llm', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({prompt, system, max_tokens: 400, backend: 'main'}), signal: ac.signal});
    const j = await r.json(); return r.ok ? j : {answer: '', error: j.error};
  } catch (e) { return {answer: '', error: String(e)}; } finally { clearTimeout(t); }
}
// показ: j.by === 'advisor' -> подпись «ответил советник» (локальная модель занята)
```
## Python (бэкенд чата, httpx)
```python
r = httpx.post('http://127.0.0.1:8810/llm', json={'prompt': text, 'system': sys, 'max_tokens': 400, 'backend': 'main'}, timeout=130); ans = r.json()['answer']
```
