# NOX FIN ZAGR V16 — P02 Python fast path (owner #2)

Status: isolated **component-verified on local synthetic fixture**, **NOT integrated** in recovered archived Windows source and **NOT Windows accepted**.

This package uses only Python 3.11+ standard library: `urllib.request`, `sqlite3`, `hashlib`, `threading`, `http.server` (in tests), etc. No second application, browser engine, SQLite database, host bridge or paid API. Integrator #6 must recover the authoritative archive and either adopt equivalent existing code or transplant only the needed semantics.

- `p02_runtime.py`: localhost-only Ollama `/api/tags` and streaming `/api/chat`; STOP; HTTP timeout/errors; one SQLite connection passed in from host (no second DB); owner ACL, schema, history, retention; MIME/size, SHA-256, staging, STORED-ID, read verification, crash-safe GC outbox; strict WebView2 source policy (requires actual native enforcement by #6).
- `p02_chat_bridge.py`: host-only chat orchestration; optional preauthorized RAG callback; successful assistant output persisted only after `done=true`; lightweight event output for mapping to **existing** `events.v3`.
- `test_p02_runtime.py`: six local synthetic component scenarios, including loopback HTTP fake Ollama.

Run `python -m unittest discover -v -p 'test_*.py'` from this directory. Real provider/GPU/E07 acceptance not covered.

## Security and integration blockers

- Host must authenticate tenant+principal, map app/browser origin from WebView2's **reported** navigation/message source and never page-supplied JSON; never reveal local file path or storage IDs to external sites. See official Microsoft WebView2 security guidance.
- SQLite parameterization & ACL are in code, but OS file permissions, database backups, integration with existing schema and migration rollout are host-specific.
- Untrusted context is labeled, but a complete RAG provenance/citation contract belongs to #4.
- Attachments MIME checks are first-byte signatures only, **not deep AV scanning**; leave dangerous formats disabled; text/plain may need full UTF-8 validation before rendering.
- `OllamaClient.stop()` closes the active response; stream cancellation may depend on socket behavior on Windows. Test on exact target OS and real Ollama with response stalls.
- STAGED orphan cleanup requires safe post-crash scan with retention; GC outbox covers committed chat deletes.
- Do not overwrite the legacy SourceLock or master journal: both require #6 coordinated, guarded recovery.
- No official Codex login until authorized client flow is verified.

RunID: `NOX-V16-E02-FASTPATH-20261028-01`. All product acceptance bars remain evidence-gated; local fixture tests are only **COMPONENT_VERIFIED (synthetic)**, not an accepted integrated feature.
