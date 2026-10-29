# R29 A02 PASS10 — existing native authority and SQLite admission

Parent af4a7212594e701f54716b39ce521aaeece86269. A02 10/10 real test-backed approaches completed, not product completeness/acceptance. Matrix mapping: A02 approach01/05/10, V16 §26.4 existing authenticated boundary/history/contract tests. Canonical product TaskID denominator remains unknown.

The final known ready A04 source omissions were confirmed: a composite primary key whose first field was id passed as globally unique id; a partial unique storage index passed as global attachment ownership; truthy non-boolean native flags and parser-normalized URI/userinfo passed native policy admission. Reused exact P02Store.initialize and authorized_app_message sections from authenticated A04 runtime donor dde0caf8fe8d0a56a9ec7d0b985a95ba2aec05fd. Existing database structure/data are preserved on rejection; no auto-repair or second store.

RED:5 tests,12 failing subcases. GREEN:41 selected tests: donor SQLite cases, existing runtime/history/native flags, R29 typed timeout, donor strict stream/completion and chat STOP. Prior framed-write/voice/admission sources were not modified. No native Windows/installer or physical provider claim.

Command: PYTHONPATH=Packages/P02/worker-python python -m unittest test_sqlite_admission_r27.SchemaAdmissionTests test_p02_runtime test_p02_loader_timeout_r29.TimeoutContract test_ollama_protocol_r27.OllamaProtocolTests test_stream_snapshot_r27.StreamSnapshotTests test_p02_chat_stop_gates -v

## Ready donor reconciliation complete within this inspected scope

- p02_runtime.py now differs from current A04 runtime donor ONLY by preserved R29 typed ProviderTimeout/_transport_failure, strict timeout type/range, and TIMEOUT propagation in open/tags/stream.
- p02_chat_bridge.py preserves donor terminal snapshot and R29 typed TIMEOUT/STOP distinction.
- p02_capabilities.py now equals the exact A05 donor blob d721cd9608d62052060ae2c7ff6db240b281802f, including voice and SIP safety.
- p02_owner_route_ports.py retains exact A05 OwnerTwoPorts plus R29 immutable-host registration and actual voice Event binding.
- p02_native_ingress.py retains A04 queued-session admission plus R29 original VoiceSession lifecycle, actual authorized STOP and atomic retirement.
- No remaining ready source hunk identified in the inspected A04/A05 diffs is deferred merely because it originated on a donor branch. This statement is scoped to those inspected modules, not an exhaustive proof that all P02 product requirements are complete.

## Finite remaining obligations and ownership

| Reference | Concrete remaining obligation | Classification |
| --- | --- | --- |
| R29 A02 approach08 / V16 §26.4.8; Packages/P02/worker-python/p02_owner_route_ports.py and p02_native_ingress.py | Existing authenticated host supplies stable NativeSession, actual native_mic_consent(scope,capture_id), one-use capture, output persistence/revocation and original ASR/TTS adapters using ingress.voice_session_from_native; register with ingress.voice_stop_token and enable_voice_stop=True. | Existing-host composition owned by independent integrator; source gates ready, actual native implementations not fabricated. |
| R29 A02 approach09 / V16 §26.4.9; Packages/P02/worker-python/p02_capabilities.py:ConsentGatedSip | Bind actual provider quote verification, explicit native approval, real provider callback and operation cancellation. | Existing-provider composition/permissions; no fake quote, provider or outbound test. |
| R29 A02 approach10 / V16 §26.4.10 | Later accepted owner overlay/SourceLock then installed Windows same-SHA tests of real Ollama/models/history/attachments, voice RU↔ES/MAESTRO/STOP/output and SIP opt-in. | Independent source reconciliation and native verification, not current CODE_COMPLETE proof. |

No additional owned source defect is established by the completed donor diff review; unverified overall requirements remain N/D rather than silently DONE. Existing source receipts include exact pre/post SHA, RED/GREEN and limitations. Original729/three parts, approved visuals, prior DONE, main/PR162 and GitLab unchanged. No EXE, NSIS, CI, final host integration or external messages ran.

Lesson: validate the actual global database constraint and raw native proof, not a superficially matching field or truthy value. Keep source safety, host composition and physical acceptance as separate evidenced obligations.
