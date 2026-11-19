"""Stage a bounded owner advisor action in the existing public Resonance edge."""

from hashlib import sha256

from nox_advisors.handoff import WEB_UI
from nox_advisors.native import PUBLIC_QUESTIONS

EDGE_PREIMAGE = '4dfc48d178de35c1ba3b6625fd2cd7e2df891b3dac6c515947971e4863a97eeb'

ADVISOR_UI = '''<details class="wow"><summary>Внешний советник</summary>
<p>Будет использован только заранее заданный вопрос о проверке источников.</p>
<button type="button" id="advisor-queue">Запросить бесплатный совет</button>
<button type="button" id="advisor-handoff">Открыть вручную</button>
<p id="advisor-status" role="status"></p><p id="advisor-link"></p>
</details>'''

ADVISOR_SCRIPT = '''
async function adviser(kind, button) {
  const status = by('advisor-status'), link = by('advisor-link');
  button.disabled = true;
  link.replaceChildren();
  const request_id = crypto.randomUUID().replaceAll('-', '');
  const advisor_action = {kind, topic:'verification', request_id, remote_opt_in:true};
  if (kind === 'handoff') advisor_action.service = 'chatgpt';
  try {
    const reply = await fetch('/api/nox/advisor', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({advisor_action}), cache:'no-store'
    });
    const proof = await reply.json();
    if (reply.status === 202 && proof.state === 'QUEUED_NOT_ANSWERED' &&
        proof.request_id === request_id && /^[A-Za-z0-9_.:-]{1,96}$/.test(proof.native_task_receipt?.job_id ?? '')) {
      status.textContent = 'Запрос поставлен в очередь. Ответ ещё не получен.';
      return;
    }
    if (reply.ok && kind === 'handoff' && proof.status === 'WAITING_FOR_HUMAN' &&
        proof.request_id === request_id && proof.automatic_submission === false &&
        proof.url === 'https://chatgpt.com/' && typeof proof.brief === 'string' && proof.brief.length <= 6000) {
      const a = document.createElement('a'), brief = document.createElement('p');
      a.href = proof.url; a.rel = 'noopener noreferrer'; a.target = '_blank';
      a.textContent = 'Открыть ChatGPT'; brief.textContent = proof.brief;
      link.append(a, brief);
      status.textContent = 'Вопрос можно отправить самостоятельно.';
      return;
    }
    if (proof.state === 'HOLD' || proof.state === 'DISABLED') {
      status.textContent = 'Советник пока недоступен.';
      return;
    }
    status.textContent = 'Приём запроса не подтверждён. Повторная отправка отключена.';
  } catch {
    status.textContent = 'Приём запроса не подтверждён. Повторная отправка отключена.';
  }
}
by('advisor-queue').onclick = event => adviser('queue', event.currentTarget);
by('advisor-handoff').onclick = event => adviser('handoff', event.currentTarget);
'''

ADVISOR_ROUTE = '''
    def route_advisor(self, target):
        if self.command != 'POST':
            self.reply(405)
            return
        if target.query or self.headers.get('Sec-Fetch-Site') != 'same-origin':
            self.reply(403)
            return
        if 'Cookie' not in self.upstream_headers(False):
            self.reply(401)
            return
        raw = self.read_body()
        if raw is None or len(raw) > 768:
            self.reply(400)
            return

        def unique_pairs(pairs):
            value = {}
            for name, item in pairs:
                if name in value:
                    raise ValueError('duplicate field')
                value[name] = item
            return value

        try:
            body = json.loads(raw.decode('utf-8'), object_pairs_hook=unique_pairs)
            if type(body) is not dict or set(body) != {'advisor_action'}:
                raise ValueError('action')
            action = body['advisor_action']
            if type(action) is not dict:
                raise ValueError('descriptor')
            kind = action.get('kind')
            fields = {'kind', 'topic', 'request_id', 'remote_opt_in'}
            if kind == 'handoff':
                fields.add('service')
                if action.get('service') not in ADVISOR_SERVICES:
                    raise ValueError('service')
            elif kind != 'queue':
                raise ValueError('kind')
            request = action.get('request_id')
            if (set(action) != fields or action.get('remote_opt_in') is not True
                    or action.get('topic') not in ADVISOR_TOPICS
                    or not isinstance(request, str) or not ID.fullmatch(request)):
                raise ValueError('scope')
        except (ValueError, TypeError, RecursionError):
            self.reply(422)
            return
        self.forward(NATIVE_ADVISOR, json_bytes(body))

'''


def attach_advisor_edge(raw: bytes) -> bytes:
    """Apply only to the exact currently observed public gateway artifact."""
    if sha256(raw).hexdigest() != EDGE_PREIMAGE:
        raise ValueError('ADVISOR_EDGE_PREIMAGE_MISMATCH')
    source = raw.decode('utf-8')
    changes = (
        ("TURN = '/api/nox/chat/turn'\n",
         "TURN = '/api/nox/chat/turn'\n"
         "ADVISOR = '/api/nox/advisor'\n"
         "NATIVE_ADVISOR = '/api/nox/chat'\n"
         f"ADVISOR_TOPICS = {tuple(PUBLIC_QUESTIONS)!r}\n"
         f"ADVISOR_SERVICES = {tuple(WEB_UI)!r}\n"),
        ('</nav></details><div id="history"', '</nav></details>' + ADVISOR_UI + '<div id="history"'),
        ("call('/chat/session').then(open).catch(() => {",
         ADVISOR_SCRIPT + "call('/chat/session').then(open).catch(() => {"),
        ('        if target.path in (TURN, STOP):',
         '        if target.path == ADVISOR:\n'
         '            self.route_advisor(target)\n'
         '            return\n'
         '        if target.path in (TURN, STOP):'),
        ('    def read_body(self):', ADVISOR_ROUTE + '    def read_body(self):'),
        ('    def forward(self, target, body):\n        headers = self.upstream_headers(body is not None)\n',
         '    def forward(self, target, body):\n        headers = self.upstream_headers(body is not None)\n'
         '        if target == NATIVE_ADVISOR:\n'
         "            headers['Sec-Fetch-Site'] = 'same-origin'\n"),
    )
    for anchor, substitute in changes:
        if source.count(anchor) != 1:
            raise ValueError('ADVISOR_EDGE_ANCHOR_MISMATCH')
        source = source.replace(anchor, substitute, 1)
    candidate = source.encode('utf-8')
    compile(candidate, 'owner_resonance_gateway.py', 'exec')
    return candidate
