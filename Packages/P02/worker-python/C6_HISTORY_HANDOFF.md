# NOX V16 · Executor #2 · C6 history ordering and input integrity

RunID: `NOX-V16-E02-C6-20261028`
Status: **isolated component-tested candidate**, not merged/integrated into original Windows host.

## Exact owner-scoped changes

- `p02_runtime.py`: for equal-second timestamps, use internal SQLite `rowid` as a tie breaker instead of random UUID `id`, preserving insertion order in the **existing** P02 rowid schema. This makes prompt and assistant reply order deterministic without creating a second database or rewriting user messages.
- Existing `WITHOUT ROWID` variants are explicitly held for owner #6 migration; no implicit repair.
- `history(limit)` rejects booleans/nonintegers, retention cutoff rejects booleans and millisecond/malformed values before any DELETE, and tenant/user/chat identifiers reject control characters and whitespace-only values.
- `test_p02_c6_history_order.py`: 13 focused fixtures for same-second ordering, mixed roles, limit, restart, scoped ACL, pruning, existing incompatible schema, and invalid arguments. Combined suite: 65/65 PASS.

## CRITICAL durability limit

SQLite documentation explains that unaliased `rowid` may change after `VACUUM`. This is a **safe non-schema patch for the currently staged C5 candidate**, not a guarantee of permanent chronological ordering through all future DB rebuilds. #6 must choose the authoritative existing chat DB and, after exact byte backup and owner approval, add a stable monotonic message sequence/INTEGER PRIMARY KEY or equivalent migration if needed. Never silently modify an approved production database. `WITHOUT ROWID` and schema drift remain HOLD.

Official reference: https://www.sqlite.org/rowidtable.html .

## Integration and acceptance

#6: match preimage SHA, SourceLock, existing chat schema and events.v3 first; port only missing semantics; do not introduce second SQLite, backend, event bus or C# runtime.
#7: native Windows, real Ollama/STOP, authorized host and same BuildID/EXE SHA review, including database reboot, VACUUM/migration scenario, ACL and retention.

No originals, D02, 8 CoreID, 5 Persona, Ollama, RAG/LoRA GPU, RU↔ES/MAESTRO/SIP/mobile, cinematic 10+10+10 or approved WOW were removed. This patch does not edit any of those files.
