# Existing native voice STOP provider — verified source HOLD

RunID `ASTRA-R29-A02-20261029-VOICE-STOP-PROVIDER-AUDIT`.
Source parent `f0f453e50fce8b4973098672aa17d4fe273c98c5`.
This is a diagnostic receipt, **not a sixth completed code pass** and not a native acceptance result. Five prior R29 passes remain saved and unchanged.

Run `python Packages/P02/evidence/R29_A02_VOICE_STOP_HOLD/reproduce.py` from the repo checkout. It imports the actual unchanged `proposals/NOX-PACK01-50/native_bridge.py`, current P02 `NativeIngress`, current `OwnerTwoPorts`, actual `LocalVoicePipeline`, and an in-memory SQLite fixture. Model discovery, ASR/LLM/TTS and capture are offline fixtures, explicitly not installed providers.

The existing voice registration passes the exact fixture `threading.Event` into ASR. Inside that ASR boundary the diagnostic calls `NativeIngress.handle` with an independently authorized `chat.stop` request. The real native dispatcher invokes `ExistingP02Adapter.stop`, and returns `OK / stopRequested:true`. **The voice Event remains unset, and the active voice operation returns output_audio_id.** `observed.json` records the exact result. This demonstrates the missing cancellation connection; it must not be reported as STOP PASS.

## Exact inspected boundary

- `Packages/P02/worker-python/p02_owner_route_ports.py:register_with_existing_pack01`: the R29 `native_stop_from_session(session)` injection reaches `captured_voice(..., stop=event)` and its existing pipeline. With no resolver, voice is explicitly HOLD before capture.
- `Packages/P02/worker-python/p02_native_ingress.py:NativeIngress.handle`: dispatches `chat.stop` on the authenticated session, bypassing `_serial`; it owns no session/run Event registry.
- `proposals/NOX-PACK01-50/native_bridge.py:ExistingP02Adapter.stop`: calls only `self.client.stop()`; no voice token is resolved or set. `NativeSession` has tenant/principal/chat/scopes, no cancellation object.
- `Packages/P02/worker-python/p02_runtime.py:OllamaClient.stop` sets that client's active `_cancel`, which is created by `stream` for its current HTTP request. It is not a voice session/run token. Reusing it for ASR/TTS could target a different request and cannot cancel voice before an Ollama stream exists.
- `coordination/e06/onehost_p02_p04.py:P02P04OneHost.stream_chat` has a local `native_stop` argument for guarded chat; it supplies no voice resolver or shared registry.
- `Packages/P02/worker-chat/NativePythonPipe.cs:RequestAsync` accepts .NET `CancellationToken` for pipe writes/waits. This does not constitute a Python voice Event.
- `proposals/NOX-VOICE-LAB/README.md` explicitly marks `nox.voice.stop(operationId)` as a client-side proposal, not a bound native handler. Its UI operationId is not cancellation authority.

## Required existing owner source

The native owner must recover the original authenticated voice operation/session lookup, its existing cancellation object, and the STOP handler that sets that same object. Pass that existing lookup to `register_with_existing_pack01` and establish the authorized STOP connection at the original host call site; preserve tenant/principal/chat/session/run identity and native consent. Do not invent a global token store, use page-provided Event authority, reuse another chat's `_cancel`, or allocate an unrelated Event per callback.

The exact original symbol is **not yet established**. The existing `coordination/e06/original_host_contract_extract.py` names original archive inputs `helion/desktop_routes.py`, `helion/e06_route_adapter.py`, `helion/core_chat_bridge.py`, `helion_voice/service.py`, `helion_voice/integration.py`, `helion_scoped_capabilities.py`. They are not recovered in this checkout. E06 confirms only the small R08 C# host subset is recovered; the Python original 729-member archive remains pending. No whole-repository absence is claimed.

## Candidate preservation and overlap

R27 A04 `p02_native_ingress.py` candidate blob `4efa3fec8ac7484d977e1a480dc37c00acb35805` moves mutable native-session resolution inside actual serial execution. R29 has not changed that file and does not automatically include this candidate. It must be retained during independent source reconciliation.

R27 A05 `p02_owner_route_ports.py` candidate blob `dcef668c010b9b215131e610eab960a3d864ec14` and `p02_capabilities.py` candidate blob `d721cd9608d62052060ae2c7ff6db240b281802f` contain ready consent/request/result/STOP fixes. R29's owner-port changes concern registration, read-only Mapping acceptance and token injection; no whole-file replacement of either candidate was performed. The candidates must be combined by reviewed hunks, including STOP recheck after output persistence. Nothing here claims those earlier fixes already integrated.

No new production source edits, host, token store, database, UI route, build, CI, EXE, staging or final integration. The missing native provider remains a concrete source handoff HOLD, independent of later Windows/model/microphone acceptance.
