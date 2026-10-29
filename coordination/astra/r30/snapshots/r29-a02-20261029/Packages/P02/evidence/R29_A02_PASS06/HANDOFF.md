# R29 A02 pass 06 — original VoiceSession STOP lifecycle

SOURCE_COMPONENT_VERIFIED, not native Windows acceptance. A02: 6/10 real passes; product TaskID denominator remains unknown. Parent: dc72e1a39633cadbd49a4eddf0cdae1663b36afb. Prior five code commits and diagnostic retained.

Critical source gap closed: the actual existing PACK01 chat.stop acknowledgement previously did not set the Event observed by captured_voice. NativeIngress can now own the ORIGINAL VoiceSession for exactly its admitted chat.voice request, lend its existing Event to the existing P02 pipeline, and invoke VoiceSession.stop only after the unchanged PACK01 STOP route authorizes/acknowledges. Original subprocess termination is reused. No duplicate VoiceSession, store, backend, router or process launcher was created.

The active scope is native-session-object + request nonce within the ingress's validated run ID. No page identity becomes authority. A different/equal-but-reconstructed native session is rejected; target request mismatches, old run IDs and replay nonces fail closed. STOP snapshots the active operation before its authorization and only cancels that same still-active operation afterward. Completion's final stopped check and active-scope retirement are atomic. Finally retires/terminates the original scope on success and exceptions. A completed scope/Event is never reset or reused.

## Reuse and exact source provenance

- Verified physical original ZIP: SHA256 ff8e2848c7c7ab776b90cbd8ac28e41e3815e96373c3c5f635d7587284629e9a; 60,364,346 bytes / 729 audited members (A06 manifest).
- Original helion_voice/control.py SHA256 30e51e9163683a6b8a84c306feba3bb6958f58e35d18a664e6bb08cc73137395. Tests import the untouched package directly from this verified ZIP; no app launch.
- R27 A04 p02_native_ingress.py donor blob 4efa3fec8ac7484d977e1a480dc37c00acb35805: reused queued native-session resolution inside serial admission, plus its exact test additions. Existing primary tests were retained.
- R27 A05 p02_owner_route_ports.py donor blob dcef668c010b9b215131e610eab960a3d864ec14: reused native_discard_output_audio constructor/field and exact STOP-during-output-persistence cleanup block. Only those independent hunks adopted; other consent/request/result/SIP candidate hunks remain on their owner branch, not silently marked integrated.
- Real PACK01 native_bridge.py blob 805ade553b3fd102f8995a54632d0ad904316c9c and catalog c8c9b19e44d9b5ff3af00a38e8446d8c0507b69d were imported unchanged.
- Immutable donor manifests, stager pins, original archive, main, PR162, other owner branches and GitLab are unchanged. receipt.json records pre/post overlay hashes; this is NOT an accepted integrated SourceLock.

## Exact future E06 native binding (not installed by this source task)

In the existing authenticated host composition, after original helion_voice is available, create the SAME NativeIngress with enable_voice_stop=True. Register owner #2 ports with native_stop_from_session=ingress.voice_stop_token. Keep the authenticated NativeSession object stable for its session lifetime; a new session object revokes access to the previous operation. Owner ports must receive the existing native_discard_output_audio callback for post-persistence STOP cleanup.

Original ASR/TTS adapters needing VoiceSession.run must receive ingress.voice_session_from_native(the_same_authenticated_session), rather than creating their own VoiceSession or using OllamaClient._cancel. P02's current Event-based pipeline receives the original VoiceSession._cancelled Event through the narrow pinned compatibility adapter. Original VoiceSession exposes no public Event accessor; future original-source updates must explicitly review this contract. No subclass or replacement Event is used.

chat.stop with an empty payload retains native stop-current semantics. Optional voice_request_id must exactly match the active request nonce; a stale explicit target fails closed. voiceStopped=True is returned only when that original active scope was actually stopped after authorization. Missing opt-in preserves old ingress behavior; missing registration resolver retains explicit voice HOLD (the original real host's dict-only registration was already HOLD before R29).

The initial R29_A02_VOICE_STOP_HOLD diagnostic remains immutable historical RED evidence. Its 'provider not recovered' note is superseded by A06's verified ZIP and this pass; it is not a successful STOP acceptance report.

## Verification

RED: six new lifecycle tests fail against pre-change API; prior diagnostic shows actual stopRequested:true but Event false. Deterministic completion-race regression fails when only atomic retirement is reverted, confirming the race assertion is meaningful.

GREEN: 46 selected unique unittest methods, including seven new lifecycle tests, existing ingress/owner/registration coverage and the donor queued-session test. Offline ASR/LLM/TTS callbacks are fixtures; the PACK01 host, original VoiceSession, native ingress, P02 pipeline/store and actual Python child cancellation are real imported source. Tests verify active token observed as set at STOP ACK before finally, cross-session/stale/replay denial, denied STOP leaves token unlatched, non-reuse/finally cleanup, native persisted receipt revocation, actual registered subprocess termination, and atomic completion retirement. Callback assertions cannot masquerade as expected ingress HOLD in the positive STOP proof.

Command (NOX_ORIGINAL_SOURCE_ZIP must point at the exact verified archive):

```
PYTHONPATH=Packages/P02/worker-python python -m unittest test_p02_native_ingress.IngressTests test_p02_owner_route_ports.RouteTests test_p02_loader_voice_stop_r29.VoiceStopWiring test_p02_loader_existing_pack_r29.ExistingPackContract test_p02_native_voice_lifecycle_r29.NativeVoiceLifecycle -v
```

Residual: E06's physical native composition and session/consent/capture/output callbacks, reconciliation of remaining A04/A05 candidate overlays, real Windows microphone/ASR/TTS/RU↔ES/audio tests and future independent source integration. No build, CI, installer packaging or final integration ran. DurableStopFence and m5_stop_bridge were inspected but are explicit unmounted candidates requiring their own transaction mapping; they were not transplanted as false native STOP authority.

Lesson: reuse the recovered original cancellation owner rather than a lookalike token; verify the actual authorization→STOP→in-flight provider path. Completion and STOP must share an atomic retirement boundary, and observations inside a provider callback must be asserted outside an ingress that intentionally wraps errors.
