"""Verify reconnect continuity on the released Resonance gateway."""

from hashlib import sha256

EDGE_SHA256 = 'bcdcb1244605c7ea6555322f02f9db39dd1a2e067c5841e8bc128e34e16b9fe6'


def attach_reconnect_continuity(edge: bytes) -> bytes:
    """Build the candidate from the exact 1A03 release; leave installation to its owner."""
    if sha256(edge).hexdigest() != EDGE_SHA256:
        raise ValueError('HOLD_RESONANCE_RECONNECT_PREIMAGE')
    source = edge.decode('utf-8')
    replacements = (
        (
            "    turn.answer.append(document.createTextNode(value.text));",
            "    turn.verifiedText = (turn.verifiedText ?? '') + value.text;\n"
            "    turn.answer.append(document.createTextNode(value.text));",
        ),
        (
            "            if (turn.answer.textContent !== replayText) turn.answer.textContent = replayText;",
            "            if (replayText !== (turn.verifiedText ?? ''))\n"
            "              throw Object.assign(new Error('snapshot prefix changed'), {continuity:false});\n"
            "            if (turn.answer.textContent !== replayText) turn.answer.textContent = replayText;",
        ),
        (
            "        failures = turn.cursor > cursor ? 1 : failures + 1;",
            "        if (error.continuity === false) {\n"
            "          status('Сервер вернул другой префикс ответа. Текущий текст сохранён.');\n"
            "          retry.hidden = false;\n"
            "          return;\n"
            "        }\n"
            "        failures = turn.cursor > cursor ? 1 : failures + 1;",
        ),
    )
    for previous, replacement in replacements:
        if source.count(previous) != 1:
            raise ValueError('HOLD_RESONANCE_RECONNECT_ANCHOR')
        source = source.replace(previous, replacement, 1)
    candidate = source.encode('utf-8')
    compile(candidate, 'owner_resonance_gateway.py', 'exec')
    return candidate
