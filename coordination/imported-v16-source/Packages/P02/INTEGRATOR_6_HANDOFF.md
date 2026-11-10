# NOX V16 · Executor #2 · final component handoff

**RunID:** `NOX-V16-E02-FINALPASS-20261028`

These three updated Python components have passed 10 deterministic local tests. Neither the original NOX archive nor the Windows host has been rebuilt or validated here. This is a **PATCH_CANDIDATE** with full pre/post SHA-256, per-file Git blob SHA-1, and unified patch SHA-256 in `evidence/receipt.json`.

## Minimal serial integration plan for #6

1. Reassemble/verify the original signed source archive and matching `SourceLock`; locate canonical existing Python chat, SQLite, event bus and picker. Record authoritative baseline SHA-256. **No blind merge.**
2. Apply only compatible changes from `evidence/P02_V16_E2_component.patch` to the matching `Packages/P02/worker-python` candidate, then port the semantics into the existing ONE runtime as needed. No new .NET runtime; preserve existing functional UI and model registry.
3. The current `P02Store` intentionally refuses to initialize when known native chat tables exist. Map or migrate the real host history (with SQLite's `Connection.backup()` and restoration validation) rather than bypassing this gate or creating a parallel chat history.
4. Bind Ollama selection `/api/tags`, chat `/api/chat`, stop/timeout/errors and the native picker to existing `events.v3` via host adapter only. Integration tests must verify stop after tokens have started and after blocking reads.
5. Bind `ChatBridge._rag_evidence()` to #4's approved RAG source schema. Only `verified` citations enter `chat.sources`; no external source bytes become system instructions. Confirm trust model.
6. Bind the existing secure WebView2 navigation/message handler to the browser-source policy. Never pass native privileges to external sites, browser URLs, or embedded frames. Video file access must require host-confirmed user selection.
7. Add receipt/run id in own system journal; after final 1–5 PREBUILD acceptance, build ONE Windows EXE. #7 independently tests identical BuildID and EXE SHA before release.

## Acceptance evidence (NOT yet proven)

- Existing app backup/restore, schema reconciliation, migrations, ACL and profile persistence.
- Live actual Ollama `/api/tags`, `/api/chat`, STOP, timeout and selection.
- Actual WebView2 trusted origin and local video with user consent.
- Existing picker/file ACK/STORED-ID/restart recovery and RAG citation injection.
- Runtime UI events, Windows packaging/install/rollback and E07 independent acceptance.
- Documentation/report journal and Drive write/readback by the **app** (connector readback is not equivalent).

Do not count 10 local passing tests as 100% completed criteria. Do not replace original design. Optional WOW CSS remains a nonblocking candidate with a feature flag.

Documentation used: Python sqlite3 backup API and Ollama HTTP API, built-in `urllib.request`, existing WebView2 virtual host mapping policy; no dependency packages introduced.
