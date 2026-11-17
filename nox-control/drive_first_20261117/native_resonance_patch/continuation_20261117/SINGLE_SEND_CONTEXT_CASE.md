# One-send reasoning case and separately admitted context follow-up

This is the next concrete scenario for the existing owner canary, after the O1
four-file installation and exact postimage rebind. It is not a new backend or an
instruction to send another request now. The narrow executor patch alongside
this file fixes history acceptance and supplies a literal token budget; its
preserved arithmetic scenario does not claim smart-chat or model-path acceptance.

## One synthetic reasoning request

Use one newly owned dialog allocated by the existing runner. Before the network
effect, the existing operation receipt must bind the operation key, dialog ID,
source pins, expected synthetic input hashes and dispatch intent. A retry reads
that receipt and reconciles the same dialog; it must not send again merely because
the previous request timed out.

Current message:

> Условия этой проверки: метка obsidian-f3a71c, исходное число 19. Удвой исходное число и прибавь 3. Ответь только JSON с ключами label и value. Сохрани исходную метку без изменений.

Exact expected semantic JSON result:

```json
{"label":"obsidian-f3a71c","value":41}
```

Use `task=general`, `history=[]`, the actually allocated `dialog_id`, and
`max_tokens=64` for this JSON scenario. Do not substitute the fixed historical QA
dialog as a new target.
The historical reconciliation target remains
`5ce69137da0a4c42a0387917c8567d52`, read-only only.

This single reply exercises the current message and a two-step numerical
instruction. It does not establish retrieval of prior dialogue context. It does
not ask for identity, capabilities, self-description or a memory codeword. The
matching answer proves this bounded task only.

### Corrected native context assumption

The saved native bridge, SHA256
`3cd548a69ac0fa7128368bef77f5f7ef032359128cf723eaca1c6a0514c85dc6`,
replaces request-supplied `history` with `_dialog_context(dialog_id)` when a dialog
is bound. Supplying an invented user/assistant pair with a new empty dialog
therefore cannot demonstrate conversational recall. The complete current
postimage is not available in this review; do not assume that it changed this
behavior or that an undocumented history-seeding endpoint exists.

To test prior-turn context, first require a read-only, exact persisted-pair proof
for the successful reasoning request above in its own dialog. Only after a
separate owner admission and a new intent recorded in the existing operation
receipt may a follow-up use that same dialog with `history=[]` and this message:

> Возьми метку и исходное число из моего предыдущего сообщения в этом диалоге. Удвой исходное число и прибавь 5. Ответь только JSON с ключами label и value.

Its expected semantic result is `{"label":"obsidian-f3a71c","value":43}`.
The changed operation distinguishes the new answer from a replay of the prior
JSON. This is a second model request, not part of the one-send launch gate and
not authorized by merely saving this scenario. Repeated validation uses saved
terminal proof and history readback rather than generating again. No context
follow-up may target the fixed historical read-only QA dialog.

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
5. Report current-message reasoning, any separately exercised prior-turn context,
   model-path provenance, stream persistence, owner-scoped STOP and UI delivery
   separately. One successful JSON answer does not establish long-term recall,
   general intelligence or STOP cancellation.

If the one request fails, preserve the exact state and unresolved external run.
Reconcile before permitting a new model request with a new explicitly reviewed
operation. Never change pins or admission guards to make this scenario pass.
