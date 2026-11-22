"""con_hooks (CON-05/06): мост <-> сознательное ядро WOW7.

mark_chat()  — отметка «чат идёт»: mtime файла NOX_CHAT_ACTIVITY (по умолчанию /root/nox/state/chat_activity);
               nox_inner_loop.make_chat_busy() читает его (окно 120 с) и уступает слот владельцу.
self_vol()   — блок «Я сейчас»: Workspace.render_block + LiveSelfModel.render.
               Вопрос про состояние/модель: фокус + эмоция + живая проба моделей + поправка к самоописанию + тело + время.
               Обычный вопрос: только фокус + эмоция (мало токенов, префикс не растёт). Всегда <= MAX_CHARS.
Модули CON ищутся в NOX_WOW7/CON (по умолчанию /root/nox/src/wow7/CON) и рядом с файлом.
"""
import os
import sys
import threading

MAX_CHARS = 900
_HERE = os.path.dirname(os.path.abspath(__file__))
for _d in (os.path.join(os.environ.get("NOX_WOW7", "/root/nox/src/wow7"), "CON"), _HERE):
    if os.path.isdir(_d) and _d not in sys.path:
        sys.path.append(_d)

_lock = threading.Lock()
_core = {}


def activity_path():
    return os.environ.get("NOX_CHAT_ACTIVITY", "/root/nox/state/chat_activity")


def mark_chat(path=None):
    """Одна строка из CON-05: создать файл при отсутствии и обновить mtime. Ошибка записи не должна ронять чат."""
    p = path or activity_path()
    try:
        os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
        open(p, "a").close()
        os.utime(p)
        return True
    except OSError:
        return False


def _get_core():
    with _lock:
        if not _core:
            from nox_workspace import Workspace
            from nox_self_model_live import LiveSelfModel
            _core["ws"], _core["sm"] = Workspace(), LiveSelfModel()
        return _core["ws"], _core["sm"]


def reset_core(ws=None, sm=None):
    """Подменить/сбросить ядро (тесты, перезапуск)."""
    with _lock:
        _core.clear()
        if ws is not None and sm is not None:
            _core["ws"], _core["sm"] = ws, sm


def self_vol(user, emotion_text, body_text="", claimed_text="", state_question=False, max_chars=MAX_CHARS):
    """body_text — строка тела (GPU/RAM) или вызываемое; только для вопросов про состояние."""
    ws, sm = _get_core()
    if user:
        ws.post("owner:chat", "мессир пишет: " + user[:160], 1.0, kind="owner", ttl=600.0)
    extra = ["Эмоция: %s." % emotion_text]
    if state_question:
        sm_lines = sm.render(claimed_text or None)
        head = [l for l in sm_lines if l.startswith(("Мозг", "Поправка"))]
        rest = [l for l in sm_lines if l not in head]
        body = body_text() if callable(body_text) else body_text
        extra += head + (["Тело: %s." % body] if body else []) + rest
    if user:
        sm.note_owner_message()
    return ws.render_block(extra, max_chars=max_chars)
