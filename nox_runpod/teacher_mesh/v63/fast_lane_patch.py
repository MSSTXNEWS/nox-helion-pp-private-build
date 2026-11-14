"""NOX V64: exact-source, NO-LOSS fast ordinary chat path for existing OneHost.

Pure source transformation only. Does not copy model, start server, replace S03,
change GPU configs, or install itself. Production admission is a separate gate.
"""
from __future__ import annotations
import ast
import hashlib
import re

EXPECTED_BASE_SHA256 = "3884a000ea7eaed267eb22d947e3897d6140ae5680dc78e613e8a5a3592deee7"
ANCHOR = re.compile(r"""(?m)^    req\[['"]tools['"]\]\s*=\s*TOOLS[ \t]*$""")
FAST_LANE = r"""
    # NOX V64: streaming-only ordinary conversation, existing student and context.
    # Tool, owner/admin, S03-memory, current-data and NOX-project requests
    # remain on the original authenticated agent/tool path.
    def _nox_v64_plain_chat(text):
        if not isinstance(text, str):
            return False
        stripped = text.strip()
        if not 2 <= len(stripped) <= 800:
            return False
        # Avoid routing administrative, retrieval or autobiographical requests
        # around the current OneHost / S03 / tool callback requirements.
        sensitive = (
            r'(?i)(?:\b|^)(?:nox|нокс|onehost|gpu|vast|github|drive|'
            r'памят|помни|вспомн|прошл|истор|раньше|вчера|сегодня|'
            r'завтра|вес|обучен|дистилл|загру|скач|запус|проверь|'
            r'провер|исправ|файл|документ|проект|сервер|систем|'
            r'команд|настрой|отправ|удал|модел|запомни|создат|'
            r'происхожд|родил|рецепт|письмо|себе|себя|сво|'
            r'помощник|реальн|актуальн|новост|свеж|'
            r'remember|memory|project|server|model|training|'
            r'current|latest|today|yesterday|tomorrow|'
            r'search|browse|download|install|send|file|'
            r'notion|calendar|email|repo|history)(?:\b|$)'
        )
        if re.search(sensitive, stripped):
            return False
        # Distinguish conversation from actionable instructions.
        conversational = re.match(
            r'(?i)^\s*(?:что такое\b|почему\b|как понять\b|'
            r'объясни\b|сочини\b|придумай\b|напиши стих\b|'
            r'расскажи\b|переведи\b|сколько будет\b|'
            r'что значит\b|what is\b|why\b|explain\b|tell me\b|'
            r'qué es\b|por qué\b|explica\b|traduce\b)',
            stripped
        )
        if not (conversational or stripped.endswith('?')):
            return False
        try:
            if heuristic_tools(stripped):
                return False
        except Exception:
            return False
        return True

    if stream and _nox_v64_plain_chat(user_text):
        _nox_v64_req = prepare_payload(dict(req), cache=False) if _POOL else dict(req)
        _nox_v64_req.pop('tools', None)
        _nox_v64_req['tool_choice'] = 'none'
        _nox_v64_req['stream'] = True
        _nox_v64_buffer = []
        _nox_v64_final = ''
        async with httpx.AsyncClient(timeout=180.0) as _nox_v64_client:
            async for _nox_v64_item in stream_tokens(_nox_v64_client, url, _nox_v64_req):
                if isinstance(_nox_v64_item, tuple):
                    if _nox_v64_item[0] == '__final__':
                        _nox_v64_final = _nox_v64_item[1] or ''
                    continue
                if isinstance(_nox_v64_item, str) and _nox_v64_item:
                    _nox_v64_buffer.append(_nox_v64_item)
                    yield ('token', _nox_v64_item)
        _nox_v64_final = _nox_v64_final or ''.join(_nox_v64_buffer)
        if _nox_v64_final.strip():
            # Preserve the already-installed success-path memory hooks.
            try:
                from slim_chat_t885u import save_last_reply as _nox_v64_save
                _nox_v64_save(_nox_v64_final)
            except Exception:
                pass
            try:
                from nox_cores_t899u import record_turn as _nox_v64_record
                _nox_v64_record(user_text, _nox_v64_final)
            except Exception:
                pass
            yield ('done', _nox_v64_final)
            return
    # Remaining requests continue through the existing native tool loop.
"""


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def patch_source(original: str, *, expected_sha256: str = EXPECTED_BASE_SHA256) -> dict:
    """Return exact reversible patch or fail closed on upstream source drift."""
    if not isinstance(original, str):
        raise ValueError("HOLD_SOURCE_TYPE")
    before = sha256(original)
    if before != expected_sha256:
        raise ValueError("HOLD_SOURCE_SHA_MISMATCH")
    if "NOX V64: streaming-only ordinary conversation" in original:
        raise ValueError("HOLD_ALREADY_PATCHED")
    matches = list(ANCHOR.finditer(original))
    if len(matches) != 1:
        raise ValueError("HOLD_TOOL_LOOP_ANCHOR")
    anchor = matches[0]
    patched = original[:anchor.start()] + FAST_LANE.lstrip("\n") + original[anchor.start():]
    before_ast = ast.parse(original)
    after_ast = ast.parse(patched)
    names = lambda mod: [node.name for node in ast.walk(mod)
                         if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
    if names(before_ast) != [n for n in names(after_ast) if n != "_nox_v64_plain_chat"]:
        raise ValueError("HOLD_SOURCE_SHAPE_DRIFT")
    if patched.replace(FAST_LANE.lstrip("\n"), "", 1) != original:
        raise ValueError("HOLD_NONREVERSIBLE_PATCH")
    compile(patched, "agent_loop.py", "exec")
    return {
        "source": patched,
        "old_sha256": before,
        "new_sha256": sha256(patched),
        "bytes": len(patched.encode("utf-8")),
        "insertion_count": 1,
        "native_execution": False,
    }
