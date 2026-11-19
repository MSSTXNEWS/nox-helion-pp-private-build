"""Resume the existing owner turn from its server journal after a page reload."""
from hashlib import sha256


EDGE_SHA256 = '4dfc48d178de35c1ba3b6625fd2cd7e2df891b3dac6c515947971e4863a97eeb'


def replace_once(source, before, after):
    if source.count(before) != 1:
        raise ValueError('HOLD_RESONANCE_RESUME_ANCHOR')
    return source.replace(before, after, 1)


def attach_turn_resume(edge: bytes) -> bytes:
    if sha256(edge).hexdigest() != EDGE_SHA256:
        raise ValueError('HOLD_RESONANCE_RESUME_PREIMAGE')
    source = edge.decode()
    source = replace_once(source, 'let pending = null;\n', '''let pending = null;
const resumeKey = 'nox.resonance.active.v1';
const turnId = value => typeof value === 'string' && /^[0-9a-f]{32}$/.test(value);
function savedTurn() {
  try {
    const stored = JSON.parse(sessionStorage.getItem(resumeKey));
    if (turnId(stored?.dialog_id) && turnId(stored?.request_id))
      return {dialog_id:stored.dialog_id, request_id:stored.request_id};
  } catch {}
  return null;
}
function rememberTurn(binding) {
  try {
    if (binding) sessionStorage.setItem(resumeKey, JSON.stringify(binding));
    else sessionStorage.removeItem(resumeKey);
  } catch {}
}
''')
    source = replace_once(source, '''async function open() {
  await refresh();
  by('signin').hidden = true;
  by('workspace').hidden = false;
  status('');
  by('question').focus();
}''', '''async function open() {
  const binding = savedTurn();
  await refresh(binding?.dialog_id);
  by('signin').hidden = true;
  by('workspace').hidden = false;
  status('');
  if (binding && list.value === binding.dialog_id) {
    const turn = {binding, cursor:0, stopping:false, reopened:true};
    pending = turn;
    turn.answer = bubble('assistant', '');
    setBusy(true);
    phase(turn, 'preparing');
    void follow(turn);
  } else {
    if (binding) rememberTurn(null);
    by('question').focus();
  }
}''')
    source = replace_once(source, '  pending = null;\n  retry.hidden = true;', '''  pending = null;
  rememberTurn(null);
  retry.hidden = true;''')
    source = replace_once(source, '''      finish(turn, 'Ответ сохранён в памяти NOX.');
''', '''      finish(turn, 'Ответ сохранён в памяти NOX.');
      // The history may already contain the completed exchange on a reopened page.
      if (turn.reopened) void showHistory().catch(() => {});
''')
    source = replace_once(source, '''async function readTurn(turn) {
  const query = new URLSearchParams({...turn.binding, after:String(turn.cursor)});
''', '''async function readTurn(turn, reconcile = false) {
  const priorCursor = reconcile ? turn.cursor : 0;
  const query = new URLSearchParams({...turn.binding, after:String(priorCursor ? 0 : turn.cursor)});
  let replayed = 0;
  let replayText = '';
  let replayStop = false;
''')
    source = replace_once(source, '''        if (line && pending === turn) frame(turn, JSON.parse(line));
''', '''        if (!line || pending !== turn) continue;
        const value = JSON.parse(line);
        if (replayed < priorCursor) {
          if (value.dialog_id !== turn.binding.dialog_id || value.request_id !== turn.binding.request_id ||
              value.seq !== replayed + 1) throw new Error('snapshot');
          if (value.type === 'delta' && typeof value.text === 'string') replayText += value.text;
          else if (value.type === 'phase' && ['accepted','preparing','answering'].includes(value.phase))
            replayStop = value.scoped_stop === true;
          else throw new Error('snapshot');
          replayed += 1;
          if (replayed === priorCursor) {
            if (turn.answer.textContent !== replayText) turn.answer.textContent = replayText;
            turn.stopReady = replayStop;
            by('stop').disabled = turn.stopping || !turn.stopReady;
          }
        } else frame(turn, value);
''')
    source = replace_once(source, '''    let failures = 0;
    while (pending === turn && failures < 4) {
      const cursor = turn.cursor;
      try { await readTurn(turn); }
''', '''    let failures = 0;
    let reconcile = turn.cursor > 0;
    while (pending === turn && failures < 4) {
      const cursor = turn.cursor;
      try { await readTurn(turn, reconcile); }
''')
    source = replace_once(source, '''        failures = turn.cursor > cursor ? 1 : failures + 1;
        status('Восстанавливаем связь с ответом…');
''', '''        failures = turn.cursor > cursor ? 1 : failures + 1;
        reconcile = true;
        if (error.http === 404 && failures === 4) {
          if (!turn.answer.textContent) turn.answer.parentElement.remove();
          finish(turn, 'Поток больше недоступен. Проверяю историю диалога…');
          void showHistory().then(() => {
            if (!pending && list.value === turn.binding.dialog_id) status('Открыта сохранённая история диалога.');
          }).catch(() => {
            if (!pending && list.value === turn.binding.dialog_id) status('Сервер не подтвердил поток и историю.');
          });
          return;
        }
        status('Восстанавливаем связь с ответом…');
''')
    source = replace_once(source, '''  try { await call('/chat/logout', {}); } finally { location.reload(); }
''', '''  try { await call('/chat/logout', {}); } finally { rememberTurn(null); location.reload(); }
''')
    source = replace_once(source, '''  pending = turn;
  input.value = '';
''', '''  pending = turn;
  rememberTurn(turn.binding);
  input.value = '';
''')
    candidate = source.encode()
    compile(candidate, 'owner_resonance_gateway.py', 'exec')
    return candidate
