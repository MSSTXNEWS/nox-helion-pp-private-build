# R29 A02 — existing Express Integrator P02 source checkpoint

Five tested source passes, not product readiness. Owner branch `astra/r29-a02-20261029`, base commit `f04f616091ffae9b2421a1d353e6610550edf327`, base tree `ce1942cc8e743f3670e11577645e413bdae89ac2`. No staging, build, CI, EXE or cross-owner integration.

| Pass | Existing loader defect corrected | Source commit / evidence |
|---|---|---|
| 1 | Binary private pipe short writes corrupted length-prefixed replies, including STOP | `89214cee5d6f5579b722d9b0efbda83a6699e753`; R29_A02_PASS01; 12/12 Python PASS |
| 2 | Mutable registered host event map could retarget admitted frames; nonboolean native proof accepted | `3f6f867c236b411d41f263e22062caa326134358`; R29_A02_PASS02; 13/13 PASS |
| 3 | Registered voice route dropped the existing host cancellation token | `95461800d6fbd8e2c4989f74c3f81e6a3c03200c`; R29_A02_PASS03; 18/18 PASS |
| 4 | P02 registration rejected the actual read-only NoxPackHost route registry | `23686b38471fee3811a7f1da3abc682ffc9706a6`; R29_A02_PASS04; 16/16 PASS |
| 5 | Provider timeout became generic OLLAMA_ERROR; malformed timeout budgets admitted | This commit; R29_A02_PASS05; 6 focused + 22 existing runtime/STOP tests PASS |

Counts overlap existing fixtures; do not sum them as unique product tasks. Exact changed-path Git blobs and SHA256 plus RED/GREEN logs reside in each pass receipt. Passes 6–10 NOT_EXECUTED, product P02 denominator unknown.

## Voice STOP binding and no-loss proof

At the inspected primary, `proposals/NOX-PACK01-50/native_bridge.py` Git blob `805ade553b3fd102f8995a54632d0ad904316c9c` constructs `NoxPackHost.routes` and each route entry as `MappingProxyType`. Old P02 `register_with_existing_pack01` required `dict` for both, so **all three ports were already HOLD** when used with that actual host. Pass04's RED demonstrates this, then GREEN imports the exact original host and catalog blob `c8c9b19e44d9b5ff3af00a38e8446d8c0507b69d`, retaining its 50 routes and immutable registry identity. RAG and call history become usable on the authorized offline fixture. Original host files are read-only dependencies, not modified or merged.

With the old registration call shape, `chat.voice` remains explicitly HOLD before one-use capture; it is not silently disabled from a demonstrated working native integration. `native_stop_from_session(session)` is a new optional **injection point in the existing registration helper**, not a new host or cancellation registry. It must return the actual existing authenticated session's `threading.Event`, the same token the native STOP action sets. Missing or malformed token fails closed. Tests pass an Event fixture and exercise pre-capture STOP plus STOP within ASR; they do not prove installed voice cancellation.

Actual inspected source paths:
- `Packages/P02/worker-python/p02_owner_route_ports.py`: registration helper and three P02 owner ports.
- `proposals/NOX-PACK01-50/native_bridge.py`: existing dispatcher, `ExistingP02Adapter.stop()` invokes only `OllamaClient.stop()`. Its `ExistingP02VoiceAdapter` covers different routes (`translate.ru_es`, `maestro.spanish`, `calls.dial`, `voice.settings`), unchanged here.
- `coordination/e06/onehost_p02_p04.py`: existing chat `stream_chat(..., stop)` seam, no registration call or session-token resolver for the voice helper.
- `coordination/e06/stage_onehost.py`: pinned diagnostic staging patch, not a voice registration call.
- `tests/e06/test_p02_pack01_atomic_bind_r16.py` and P02 owner tests: fixture registration calls.

No production invocation/token provider was established in those inspected paths; do not claim whole-repository absence or native acceptance. **E06 handoff HOLD:** identify the actual original host registration and authenticated cancellation lifetime, pass that existing resolver at registration, and ensure STOP targets the same voice run/session. Do not invent an Event per request or use page JSON as authority. This must be independently source-reviewed before later Windows acceptance.

## Preserve prior saved candidates

R27 branches `astra/r27-a04-20261029` and `astra/r27-a05-20261029` remain independent and unchanged. Their saved Ollama protocol, output snapshot, native-session revocation, microphone consent, request/result validation and voice/SIP lifecycle fixes were inspected and not redone. This R29 branch is based on primary, so it does NOT automatically include them. Later owner integration must combine narrow verified hunks, especially overlapping `p02_runtime.py`, `p02_chat_bridge.py` and `p02_owner_route_ports.py`, without whole-file overwrites. Old DONE is not reset.

Remaining gates: original 729-member SourceLock, genuine WPF/Python session identity, installed Ollama/model selector and Windows pipe behavior, authentic RU↔ES microphone/ASR/TTS/model rights, native voice STOP provider, and one future independent GitLab integration/build. All remain unclaimed. No new backend, DB, model download or network service was created.
