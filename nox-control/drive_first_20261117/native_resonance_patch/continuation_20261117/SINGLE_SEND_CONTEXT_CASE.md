# One-send contextual reasoning case

This is the next concrete scenario for the existing owner canary, after the O1
four-file installation and exact postimage rebind. It is not a new backend or an
instruction to send another request now. The narrow executor patch alongside
this file fixes history acceptance and supplies a literal token budget; its
preserved arithmetic scenario does not claim smart-chat or model-path acceptance.

## One synthetic request

Use one newly owned dialog allocated by the existing runner. Before the network
effect, the existing operation receipt must bind the operation key, dialog ID,
source pins, expected synthetic input hashes and dispatch intent. A retry reads
that receipt and reconciles the same dialog; it must not send again merely because
the previous request timed out.

History supplied to the one stream request:

```json
[
  {"role":"user","content":"Условия этой проверки: метка obsidian-f3a71c, число 19. Сохрани их для следующего вопроса."},
  {"role":"assistant","content":"Условия этой проверки приняты."}
]
```

Current message:

> Используй условия из истории. Удвой число и прибавь 3. Ответь только JSON с ключами label и value. Сохрани исходную метку без изменений.

Exact expected semantic JSON result:

```json
{"label":"obsidian-f3a71c","value":41}
```

Use `task=general`, the actually allocated `dialog_id`, and `max_tokens=64` for this
JSON scenario. Do not substitute the fixed historical QA dialog as a new target.
The historical reconciliation target remains
`5ce69137da0a4c42a0387917c8567d52`, read-only only.

This single reply exercises supplied dialogue context and a two-step numerical
instruction. It does not ask for identity, capabilities, self-description or a
memory codeword. The matching answer proves this bounded task only.

## Evidence required before calling this a real model reply

1. Authoritative server route/request evidence must bind the stream to the actual
   model backend and exclude identity/template interception. The current task has
   not yet received the frozen terminal model-path contract from O1/root; no
   imagined field name is used and the result must not be labelled model-path PASS.
2. Capture the terminal `saved` and `s03_integrated` booleans plus timing and answer
   SHA immediately, before a later history request can fail. The pinned base
   already preserves this partial report; retain that behavior.
3. Read exactly the owned dialog's two-message exchange. Require `status=READY`,
   matching top-level dialog ID, exact question/answer and equal non-empty typed
   exchange IDs. Require terminal `done.exchange_id` to equal that same exchange;
   reject a conflicting optional terminal `dialog_id`. The candidate patch closes
   these missing checks in the base canary.
4. Store the sanitized terminal report and question/answer/exchange hashes in the
   existing operation receipt. Further checks use read-only history reconciliation
   and this prior proof. A successful history GET cannot recover a terminal record
   that was never saved.
5. Report supplied-context reasoning, model-path provenance, stream persistence,
   owner-scoped STOP and UI delivery separately. One successful JSON answer does
   not establish long-term recall, general intelligence or STOP cancellation.

If the one request fails, preserve the exact state and unresolved external run.
Reconcile before permitting a new model request with a new explicitly reviewed
operation. Never change pins or admission guards to make this scenario pass.
