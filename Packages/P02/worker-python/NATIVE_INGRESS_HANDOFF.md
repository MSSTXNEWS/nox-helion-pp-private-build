# NOX V16 E02 — Native command boundary to existing PACK01 dispatcher

RunID: `NOX-V16-E02-NATIVE-INGRESS-20261028`
Owner: 2 (`Packages/P02/**` only). This is a source component for the existing WPF ↔ original Python host integration, **not a new server/second backend**.

- Host #6 MUST choose the one canonical Windows host and existing SQLite & events.v3. This module does **not** open stdio, HTTP, pipes, sockets, a process, or a DB; it only validates a byte-encoded JSON frame and delegates to an injected existing PACK01 `NoxPackHost` dispatcher.
- Use a **host-only** `native_session` callback after the WPF host checks the WebView2 navigation origin, authenticated native SID, session ACL and permissions. Never derive NativeSession from the request JSON. A page-provided authority field is rejected.
- This component accepts only the **nine existing P02 chat-related routes**. Only an existing PACK01 `BoundPort` with real owner receipt executes the action. No `calls.dial`/model downloads/PC CONTROL or GPU worker commands are introduced.
- One in-process serial lock protects the host SQLite from concurrent chat calls; `chat.stop` bypasses that lock so STOP can terminate blocked chat. Do not allow a separate web-exposed endpoint.
- Request frames are <=64 KiB, responses <=1 MiB, 32-hex single-use IDs, exact protocol & RunID. On 8192 nonces, **HOLD and rotate session/RunID**, never evict old IDs and admit replays. Unknown or unavailable provider returns HOLD, never success.
- A Windows host embedding CPython or supervising the **existing original Python backend** must supply the IPC transport and lifecycle. Do not infer this implementation has already connected the R11 host to the original Python EXE. #6 owns those files and the final package/rollback.

## Exact on-device integration acceptance

1. In the original WPF WebView2 host, verify the exact origin and use an authenticated Windows user SID to create a NativeSession. Enforce permission scopes independently of the browser.
2. Supply a trusted `NativeIngress(existing_pack01, native_session, expected_run_id=...)` once to the original host. The trusted host transports bytes without creating a public Ollama port.
3. Confirm one actual installed Ollama model, one existing history SQLite, one P04 index, and the same STOP/Persona/RAG source handlers. Missing provider => HOLD.
4. Diagnostic Windows build on exact SourceLock/owner receipts; only then native test user/UI, fault handling, reload, rollback and E07 same BuildID/EXE SHA.

`python -m unittest -q test_p02_native_ingress.py` passed locally on Python 3.13.5 with six self-contained component tests. No genuine WPF runtime, Ollama/GPU, ASR/TTS/SIP or E07 testing was performed here.
