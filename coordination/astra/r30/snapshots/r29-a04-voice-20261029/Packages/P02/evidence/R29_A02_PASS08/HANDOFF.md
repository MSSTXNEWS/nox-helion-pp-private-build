# R29 A02 PASS08 — strict Ollama stream and immutable completion state

Parent 5c3e407b6e22a8467c11cc3ee75a7f779698b686. Same-owner source consolidation for R29 A02 approach03 / V16 §26.4.3; no canonical product TaskID denominator claimed. A02 8/10 approaches.

Reused A04 p02_runtime.py donor blob 1908f8c41c4c86da0b9772b61356a63316c45158: strict UTF-8/duplicate-key/nonfinite JSON decoder for tags and stream, bounded readline before allocation, and snapshot of validated terminal bit before yielding mutable dictionaries. Reused A04 p02_chat_bridge.py donor 19632f3a0d2abbd94a58dfa2af86db299347b87e terminal snapshot before suspended UI delta. Existing R29 ProviderTimeout, exact finite timeout policy and distinct TIMEOUT/STOP mapping preserved; no blanket donor replacement. Existing SQLite/history/native origin section untouched in this block.

RED: 8 donor tests,10 failing subcases+1 error, including accepted duplicate/NaN/invalid UTF-8, unbounded read and mutation of completion state. GREEN:36 tests including donor protocol/snapshot and existing runtime/STOP/typed-timeout regressions. Reused tests moved into P02 owner path; only their harness path insertion adjusted. Offline byte streams, no installed Ollama or Windows acceptance.

Command: PYTHONPATH=Packages/P02/worker-python python -m unittest test_ollama_protocol_r27.OllamaProtocolTests test_stream_snapshot_r27.StreamSnapshotTests test_p02_runtime test_p02_chat_stop_gates test_p02_loader_timeout_r29.TimeoutContract -v

Remaining ready source: A05 SIP quote freshness/STOP donor, plus A04 exact SQLite schema/native-origin proof admission. Native host/provider composition and Windows same-SHA verification are later distinct obligations, not substitutes for these ready source fixes. VoiceSession/consent/source originals unchanged. No cross-owner integration/build/CI.

Lesson: transplant strict transport and terminal snapshots while retaining the newer typed error overlay; consumer mutation after yield must never redefine an already validated completion state.

## Append-only donor provenance correction (PASS09)

The current R27 A04 runtime donor blob is dde0caf8fe8d0a56a9ec7d0b985a95ba2aec05fd, confirmed by authenticated GitHub readback of astra/r27-a04-20261029 and exact equality to the reused local donor bytes. The earlier 1908f8c41c4c86da0b9772b61356a63316c45158 reference above was stale. Production source, pre/post receipt hashes, tests and saved PASS08 commit are unaffected. The ChatBridge donor blob remains 19632f3a0d2abbd94a58dfa2af86db299347b87e.
