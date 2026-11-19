"""Bind current owner-dialog context to C02 retrieval on the pinned proxy."""

from hashlib import sha256


PROXY = 'chat_proxy.py'
CONTEXT = 'nox_v38_native_context.py'
PREIMAGES = {
    PROXY: 'd19027e3d12980baa619474e633c5cd452d1570d8c5549b1421fc8041e2c4064',
    CONTEXT: '32fa7c3729bbb7a4ab3e43183f10fec70e4c9254d0f9c2f9458db68c1c4a6deb',
}
POSTIMAGES = {
    PROXY: '792538243e37b69ffb937c3b36807840a56b3bc67d2fdbad587dc4a62c4d98d2',
    CONTEXT: '1f34c0dbd87723c17dc81126fca00e1843e64d14b9bcdf1fdf7028ec55e0e685',
}
RETAIN = {
    'nox_dialog_followup.py': '56440ce515f2f834b12ced9124999087b61df8fbeb78f694436c876d1df7f9f0',
    'nox_v29_chat_bridge.py': '3b1f1c22279b2fbca3be03ef53579e8dd93ab3ea44a3c5404e7584f07e3bbf1b',
    'nox_v38_s03_native.py': 'c1c4d77d86e833c69b5af8cee82bbd83211ca0184f4a63f66dc067eb0b50ebc3',
    'nox_s03_scoped_pair.py': 'd347ff7247e2f883b955094ca4e98205346ddb6e39b0fa52e13c360a8144c57f',
    'nox_v38_self_model.py': 'b15bf20557601028ecc4e6163d1d6add682616d466fa9fb78b3640411f7c1ada',
    'owner_drive_chat_health.py': 'ea71f14a8eb0ab9174904baa00a9cebe5cf309e08f343fdd5c2532ae628a6e19',
    'owner_drive_chat_route.py': '6b3e105aa20dabb16418af9d92ee4d6b40c3d3bf1237dedffc0a547678087306',
    'owner_native_drive_probe.py': '10b361e914eade7a9486dfabac92768b3e850869c2b1d5e71722f60758738167',
}


def replace_once(source, anchor, replacement):
    if source.count(anchor) != 1:
        raise RuntimeError('HOLD_S03_RESONANCE_CONTEXT_ANCHOR')
    return source.replace(anchor, replacement, 1)


def proxy_source(source):
    source = replace_once(source,
        'def _v38_dialog_context(dialog_id, user_text, stop_active):\n',
        'def _v38_dialog_context(dialog_id, user_text, stop_active, *, memory_query=None):\n')
    source = replace_once(source,
        "                                 {'persona_enabled': False, 'stop_active': stop_active})\n",
        "                                 {'persona_enabled': False, 'stop_active': stop_active,\n"
        "                                  'owner_followup_memory_query': memory_query})\n")
    return replace_once(source,
        '    cortex = _v38_dialog_context(nox_cortex_dialog, user_text, nox_cortex_stop)\n',
        '''    memory_query = None
    if nox_cortex_dialog and msgs and msgs[-1] == {"role": "user", "content": user_text}:
        try:
            from nox_dialog_followup import resolve_followup
            focus = resolve_followup(user_text, msgs[:-1])
            if focus and focus["state"] == "CONTEXTUAL":
                memory_query = focus["prior_user_text"]
        except (ImportError, TypeError, ValueError):
            pass  # A follow-up hint must not block the existing chat or memory.
    cortex = _v38_dialog_context(nox_cortex_dialog, user_text, nox_cortex_stop,
                                 memory_query=memory_query)
''')


def native_context_source(source):
    source = replace_once(source,
        '        recall_records = []\n\n        def recall(scope, text, limit):\n',
        '''        recall_records = []
        memory_query = tools.get('owner_followup_memory_query')
        if not isinstance(memory_query, str) or not 1 <= len(memory_query.strip()) <= 600:
            memory_query = None

        def recall(scope, text, limit):
''')
    return replace_once(source,
        '                records = scoped_recall(native_recall, scope, text, limit)\n',
        '                records = scoped_recall(native_recall, scope, memory_query or text, limit)\n')


def transform(name, raw):
    if not isinstance(raw, bytes) or name not in PREIMAGES or sha256(raw).hexdigest() != PREIMAGES[name]:
        raise RuntimeError('HOLD_S03_RESONANCE_CONTEXT_PREIMAGE')
    transform_source = proxy_source if name == PROXY else native_context_source
    candidate = transform_source(raw.decode('utf-8')).encode('utf-8')
    if sha256(candidate).hexdigest() != POSTIMAGES[name]:
        raise RuntimeError('HOLD_S03_RESONANCE_CONTEXT_POSTIMAGE')
    compile(candidate, name, 'exec')
    return candidate
