"""Exact V24 error/completion transform; no private native file is exported."""
import hashlib

PREIMAGE_SHA256 = '92b952b6c7ee31f22ed74912d9444a88989c014694424083336660dce21a8a5b'
POSTIMAGE_SHA256 = '4568a5075fca9c13ad535814059df933d2642835d2a4db0be755ee0c7904a22d'
HELPER = "  function chatFailure(value) {\n    const raw = String(value?.code || value?.message || value || 'CHAT_STREAM_INTERRUPTED');\n    const code = raw.match(/(?:HOLD|WAIT|STREAM|CHAT)_[A-Z0-9_]{1,150}/)?.[0] ||\n      (/401|403/.test(raw) ? 'CHAT_AUTH_REQUIRED' : 'CHAT_STREAM_INTERRUPTED');\n    let message = 'Ответ прервался. Сообщение отправлено, но завершённый ответ не получен.';\n    if (/CONTEXT|TOKEN_BUDGET|MODEL_LENGTH/.test(code)) message = 'Не хватило места для ответа в контексте модели. Поручение не завершено; нужен повтор с сокращённым контекстом.';\n    else if (/MODEL_EMPTY|INCOMPLETE_NATIVE_RESPONSE/.test(code)) message = 'Модель не вернула содержательный ответ. Поручение не считается выполненным.';\n    else if (/AUTH|SESSION/.test(code)) message = 'Сессия подключения истекла. Войдите в NOX снова, чтобы продолжить этот диалог.';\n    else if (/S03|HISTORY|PERSIST|RECEIPT/.test(code)) message = 'Не удалось подтвердить сохранение ответа. Перед повтором действия нужно сверить его результат.';\n    else if (/TOOL/.test(code)) message = 'Вызов инструмента не завершился корректно. Результат действия пока не подтверждён.';\n    else if (/TIMEOUT|UNAVAILABLE|CONNECT|HTTP_50/.test(code)) message = 'Модель сейчас не ответила. Поручение не завершено; подключение требует проверки.';\n    return {code, message};\n  }\n"
ERROR_BLOCK = "      else {\n        const failure = chatFailure(e);\n        out.box.classList.add('error'); out.box.dataset.errorCode = failure.code;\n        if (!result.trim()) out.body.textContent = failure.message;\n        out.meta.textContent = (result.trim() ? 'Ответ прерван. ' + failure.message + ' · ' : '') + failure.code;\n        phase('error'); say(failure.message);\n      }"


def replace_one(source, old, new):
    if source.count(old) != 1:
        raise ValueError('HOLD_SMART_CHAT_UI_ANCHOR')
    return source.replace(old, new, 1)


def transform(raw):
    if not isinstance(raw, bytes) or hashlib.sha256(raw).hexdigest() != PREIMAGE_SHA256:
        raise ValueError('HOLD_SMART_CHAT_UI_PREIMAGE')
    text = raw.decode('utf-8')
    text = replace_one(text, '  async function send(text) {', HELPER + '  async function send(text) {')
    text = replace_one(text,
        "      if (!r.ok || !r.body) throw Error((await r.json().catch(() => ({}))).error || 'HTTP ' + r.status);",
        "      if (!r.ok || !r.body) { const failed = await r.json().catch(() => ({})); throw Error(failed.error?.code || failed.error || 'HTTP ' + r.status); }")
    text = replace_one(text, "          } else if (f.type === 'token') {",
        "          } else if (f.type === 'token') {\n            if (typeof f.t !== 'string' || result.length + f.t.length > 300000) throw Error('HOLD_CHAT_TOKEN_FRAME');")
    text = replace_one(text, "          else if (f.type === 'error') throw Error(f.error);",
        "          else if (f.type === 'error') throw Error(f.error?.code || f.error || f.code || 'CHAT_STREAM_INTERRUPTED');")
    old = """      } else if (done) {
        const h = result && md(result); if (h) { out.body.innerHTML = h; highlight(out.body); } else if (!result) out.body.textContent = done.status === 'STOP_FLAG' ? '— STOP активен —' : '—';
        out.meta.textContent = (done.seconds ? done.seconds + ' с' : '') + (done.corrected ? ' · уточнено' : '');
        phase(done.status === 'done' ? 'done' : 'stopped');
      }"""
    new = """      } else if (done?.status === 'STOP_FLAG') {
        out.box.classList.add('stopped'); out.body.textContent = result || 'Включена остановка владельца.';
        out.meta.textContent = 'Выполнение остановлено'; phase('stopped');
      } else if (done?.status === 'done' && result.trim() && !controller.signal.aborted) {
        const h = md(result); if (h) { out.body.innerHTML = h; highlight(out.body); } else out.body.textContent = result;
        out.meta.textContent = (done.seconds ? done.seconds + ' с' : '') + (done.corrected ? ' · уточнено' : '');
        phase('done');
      } else {
        throw Error(result.trim() ? 'CHAT_STREAM_INTERRUPTED' : 'HOLD_MODEL_EMPTY');
      }"""
    text = replace_one(text, old, new)
    text = replace_one(text,
        "      else { if (!result) out.body.textContent = '—'; out.meta.textContent = ''; phase('error'); say(String(e.message || e)); }", ERROR_BLOCK)
    candidate = text.encode('utf-8')
    if POSTIMAGE_SHA256 != 'PENDING' and hashlib.sha256(candidate).hexdigest() != POSTIMAGE_SHA256:
        raise ValueError('HOLD_SMART_CHAT_UI_POSTIMAGE')
    return candidate
