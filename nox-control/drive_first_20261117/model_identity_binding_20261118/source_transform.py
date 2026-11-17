"""Exact-source identity route patch; local bytes only, with exact inverse."""
from __future__ import annotations

import argparse
import ast
import difflib
import hashlib
import json
from pathlib import Path

PINS = {
    'chat_proxy.py': 'b202301a3b94076a5152478dd9d1ad1eeceaa72e09cd2ce93e537eaab70740bc',
    'owner_chat_stream.py': '2c4ae86d1d8e2113c8dbb55807f0d52890f098904ac2914f0b1383156ed7ea25',
}
BRANCH = '''    if _model_reference.model_identity_query(user_text):
        request=await asyncio.to_thread(_model_reference.prepare_identity_request,url,payload,user_text)
        message=None
        async with httpx.AsyncClient(timeout=180.0,trust_env=False) as client:
            async with aclosing(_model_events(client,url,request)) as events:
                async for kind,value in events:
                    if kind=='token':yield kind,value
                    elif kind=='message':message=value
        if message is None or message.get('tool_calls'):
            raise StreamFailure('HOLD_MODEL_REFERENCE_COMPLETION')
        return
'''
EDITS = {
    'owner_chat_stream.py': [
        ('import owner_chat_evidence as _current\n',
         'import owner_chat_evidence as _current\nimport owner_model_reference_binding as _model_reference\n'),
        ('    return (status_needs_model(user_text) or executor_status_query(user_text) or _current.relevant_query(user_text)\n',
         '    return (_model_reference.model_identity_query(user_text) or status_needs_model(user_text) or executor_status_query(user_text) or _current.relevant_query(user_text)\n'),
        ('async def _run(native,url,payload,user_text):\n',
         'async def _run(native,url,payload,user_text):\n' + BRANCH),
    ],
    'chat_proxy.py': [
        ('        from owner_chat_stream import owner_request_query as _nox_owner_request_query\n',
         '        from owner_chat_stream import owner_request_query as _nox_owner_request_query\n'
         '        from owner_model_reference_binding import model_identity_query as _nox_model_identity_query\n'),
        ('        lambda: _trim_ctx(_build_messages(body)))\n',
         '        lambda: (_build_messages(body) if _owner and _nox_model_identity_query(_utext)\n'
         '                 else _trim_ctx(_build_messages(body))))\n'),
    ],
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _replace(source, pairs):
    for old, new in pairs:
        if source.count(old) != 1:
            raise ValueError('HOLD_NONUNIQUE_SOURCE_SPAN')
        source = source.replace(old, new, 1)
    return source


def minimality(name, before, after):
    old, new = ast.parse(before), ast.parse(after)
    allowed = {'_proxy_completion'} if name == 'chat_proxy.py' else {'_run', 'owner_request_query'}
    def unchanged(tree):
        return [ast.dump(node, include_attributes=False) for node in tree.body
                if not (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in allowed)
                and not (isinstance(node, ast.Import) and len(node.names) == 1
                         and node.names[0].name == 'owner_model_reference_binding')]
    if unchanged(old) != unchanged(new):
        raise ValueError('HOLD_OUTSIDE_AST_SCOPE')
    if name == 'owner_chat_stream.py':
        original = next(node for node in old.body if getattr(node, 'name', '') == '_run')
        revised = next(node for node in new.body if getattr(node, 'name', '') == '_run')
        # Every existing generic/tool-loop statement is byte-equivalent in AST.
        if [ast.dump(node) for node in original.body] != [ast.dump(node) for node in revised.body[1:]]:
            raise ValueError('HOLD_EXISTING_OWNER_LOOP_CHANGED')


def transform(name, raw):
    if name not in PINS or sha(raw) != PINS[name]:
        raise ValueError('HOLD_SOURCE_PIN')
    before = raw.decode('utf8')
    after = _replace(before, EDITS[name])
    minimality(name, before, after)
    restored = _replace(after, [(new, old) for old, new in reversed(EDITS[name])])
    if restored.encode() != raw:
        raise ValueError('HOLD_INVERSE_BYTES')
    return after.encode()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('source_dir', type=Path)
    parser.add_argument('output_dir', type=Path)
    args = parser.parse_args()
    args.output_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    manifest, patches = {}, []
    for name in PINS:
        before = (args.source_dir / name).read_bytes()
        after = transform(name, before)
        target = args.output_dir / name
        target.write_bytes(after)
        target.chmod(0o600)
        manifest[name] = {'pre_sha256': sha(before), 'pre_bytes': len(before),
                          'post_sha256': sha(after), 'post_bytes': len(after),
                          'ast_scope_verified': True, 'exact_inverse_verified': True}
        patches.extend(difflib.unified_diff(before.decode().splitlines(True), after.decode().splitlines(True),
                                            fromfile='a/' + name, tofile='b/' + name))
    (args.output_dir.parent / 'IDENTITY_ROUTE.patch').write_text(''.join(patches))
    (args.output_dir.parent / 'SOURCE_TRANSFORM_RECEIPT.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps(manifest))


if __name__ == '__main__':
    main()
