"""Exact installed-proxy delta for bounded context counting; no app execution."""
import ast
import difflib
import hashlib
from pathlib import Path

BEFORE_SHA = '30207a85eed6c87df4a6ee4dd8614442a62622eefacac7fae822b23ad385b343'
BEFORE_BYTES = 103831
COUNT = '''def _count_msg_tokens(msgs, *, selected_url=None, session=None):
    """Structured measured/unknown result for the selected backend only."""
    from owner_context_budget import count_messages
    return count_messages(msgs, selected_url, session=session)
'''
TRIM = '''def _trim_ctx(msgs, budget=None, *, selected_url=None, original_user_text=None, output_tokens=None):
    """Bounded selected-route counting; original question/instructions survive."""
    from owner_context_budget import trim_messages
    return trim_messages(msgs, selected_url=selected_url, original_user_text=original_user_text,
                         output_tokens=output_tokens, char_budget=budget).messages
'''
OLD_CALL = '''    payload["messages"] = await _nox_chat_asyncio.to_thread(
        lambda: (_build_messages(body) if _owner and _nox_model_identity_query(_utext)
                 else _trim_ctx(_build_messages(body))))
'''
NEW_CALL = '''    if _owner and _nox_model_identity_query(_utext):
        # Preserve the installed narrow identity branch: no context-counter import or HTTP.
        payload["messages"] = await _nox_chat_asyncio.to_thread(lambda: _build_messages(body))
    else:
        from owner_context_budget import ProtectedContextTooLarge as _NoxProtectedContextTooLarge
        try:
            payload["messages"] = await _nox_chat_asyncio.to_thread(
                lambda: _trim_ctx(_build_messages(body), selected_url=url,
                                 original_user_text=_utext, output_tokens=body.get("max_tokens")))
        except _NoxProtectedContextTooLarge:
            from fastapi.responses import JSONResponse
            return JSONResponse({"error": {"message":
                "Полный вопрос и обязательные инструкции превышают доступный бюджет контекста запроса. "
                "Сократи материал или передай его файлом; текст вопроса не был обрезан.",
                "type": "context_budget", "protected_input_preserved": True}}, status_code=413)
'''


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _replace_function(text, name, replacement):
    tree = ast.parse(text)
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name]
    if len(nodes) != 1:
        raise ValueError('SOURCE_FUNCTION_NOT_UNIQUE')
    node = nodes[0]
    lines = text.splitlines(keepends=True)
    return ''.join(lines[:node.lineno - 1]) + replacement + ''.join(lines[node.end_lineno:])


def transform(raw):
    if sha(raw) != BEFORE_SHA or len(raw) != BEFORE_BYTES:
        raise ValueError('SOURCE_PREIMAGE_PIN')
    before = raw.decode()
    result = _replace_function(before, '_count_msg_tokens', COUNT)
    result = _replace_function(result, '_trim_ctx', TRIM)
    if result.count(OLD_CALL) != 1:
        raise ValueError('SELECTED_ROUTE_CALL_NOT_UNIQUE')
    result = result.replace(OLD_CALL, NEW_CALL)
    compile(result, 'chat_proxy.py', 'exec')
    old_nodes, new_nodes = ast.parse(before).body, ast.parse(result).body
    if len(old_nodes) != len(new_nodes):
        raise ValueError('SOURCE_TOP_LEVEL_STRUCTURE_CHANGED')
    changed = []
    for old, new in zip(old_nodes, new_nodes):
        if ast.dump(old, include_attributes=False) != ast.dump(new, include_attributes=False):
            name = getattr(old, 'name', None)
            if name not in ('_count_msg_tokens', '_trim_ctx', '_proxy_completion') or getattr(new, 'name', None) != name:
                raise ValueError('SOURCE_OUTSIDE_ALLOWED_FUNCTIONS_CHANGED')
            changed.append(name)
    if set(changed) != {'_count_msg_tokens', '_trim_ctx', '_proxy_completion'}:
        raise ValueError('SOURCE_EXPECTED_DELTA_MISSING')
    # All other bytes inside the large completion function stay exact; the
    # function replacement helpers affect only their two complete AST spans.
    return result.encode()


def reverse(candidate, original):
    if transform(original) != candidate:
        raise ValueError('ROLLBACK_POSTIMAGE_PIN')
    return original


def describe(original):
    result = transform(original)
    return {'before_sha256': sha(original), 'before_bytes': len(original),
            'after_sha256': sha(result), 'after_bytes': len(result),
            'changed_functions': ['_count_msg_tokens', '_trim_ctx', '_proxy_completion'],
            'identity_branch_new_dependency': False, 'native_calls': 0,
            'reverse_exact': reverse(result, original) == original}


if __name__ == '__main__':
    import json
    here = Path(__file__).resolve().parent
    source = here.parent / 'model_identity_binding_20261118/private_postimages/chat_proxy.py'
    original = source.read_bytes(); result = transform(original)
    private = here / 'private_postimage'; private.mkdir(exist_ok=True)
    (private / 'chat_proxy.py').write_bytes(result)
    diff = ''.join(difflib.unified_diff(original.decode().splitlines(keepends=True),
        result.decode().splitlines(keepends=True), fromfile='chat_proxy.py.before', tofile='chat_proxy.py.after'))
    (here / 'CONTEXT_COUNTER.patch').write_text(diff)
    receipt = describe(original)
    (here / 'SOURCE_TRANSFORM_RECEIPT.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt))
