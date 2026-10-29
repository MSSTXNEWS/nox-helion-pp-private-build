# NOX V16 E02 · existing-host framed transport handoff

RunID: `NOX-V16-E02-STDIO-C10-20261028`. Owner: executor **2**, only `Packages/P02/**` source. The runner is **not a second backend** and opens no HTTP listener, database, frontend, Ollama provider, RAG index or process. It is an injectable function for the already-existing original Python backend, supervised by owner #6's single WPF/WebView2 host.

## Why this closes a different gap

Previous owner `p02_native_ingress.py` validated bytes in-process, but there was no reusable bounded OS process transport for #6 to send a request to the embedded original Python backend. `p02_framed_worker.serve_native_frames(ingress, binary_input, binary_output)` supplies this transport seam. Integrator #6 owns process launch/termination/identity, source lock, one actual SQLite connection, event translation and the real WPF WebView2 host. This module does NOT instantiate `NativeIngress` or decide who the user is.

### Protocol

Wire format: `uint32_be(payload_bytes) + JSON payload`, UTF-8, no line-delimiter ambiguity. Input must be 1–65,536 bytes. Output no more than 1,048,576 bytes. Header and payload are read byte-exact. Responses carry existing `NOX-P02-NATIVE-v1`, host RunID, requestId and `OK/result` or `HOLD/errorCode`. No raw file paths, prompts, provider secrets or stack traces in transport failures. On 8,192 frames, HOLD and restart an authenticated session/RunID; never recycle nonce IDs.

`chat.stop` is dispatched by the reader, bypassing the one non-STOP in-flight worker; other commands are immediately HOLD/NATIVE_BUSY while that worker is processing. Replies can arrive out of order; WPF must correlate by `requestId`. The caller owns the original process lifetime; no automatic retry/privilege escalation. If an active worker cannot drain at shutdown, the pump fails rather than falsely saying success. Write to stderr for host logs only; stdout is framed bytes.

### Trusted host requirements — owner #6 only

1. Verify WebView2 navigation/origin, Windows SID and native session permissions independently of page JSON. Inject `NativeIngress(existing_pack01_dispatcher, native_session_provider, expected_run_id=...)`; do NOT use page-supplied user, principal, consent, model rights or provider status.
2. Call `serve_native_frames` on the existing original Python backend's **host-owned private binary pipe**, never an unauthenticated public port. WPF must enforce same RunID, requestId, source provenance, session end and STOP priority.
3. Map one installed local Ollama to the preexisting `P02Store`, one owner #4 RAG runtime, existing events.v3 and approved Persona/CoreID contexts. No second service or storage. All provider-dependent operations without actual credentials/rights/hardware remain HOLD.
4. Only after pinned original source tree+owner receipts: exercise genuine WPF-to-Python request/STOP on a clean Windows runner, install/rollback, and original D02 visual. Final EXE needs independent executor #7 same-BuildID/SHA acceptance.

### Evidence and rollback

- Tests are in `test_p02_framed_worker.py`: 8 local Python tests, including actual OS subprocess stdio and STOP-overlapping-chat. A GitHub Windows CI on the exact owner commit is required. These do **not** establish original WPF host integration.
- No previous files are changed, so rollback is exclusion of these two additive owner paths. D02, 8 CoreID, GPU LoRA/QLoRA, original Python EXE, voices, SIP/mobile, approved WOW 10+10+10, historical archives and owner PRs remain untouched.
- Fresh E06 combined installer may have independent NSIS /S prerequisites/activation errors. This adapter does NOT cure or bypass them.
