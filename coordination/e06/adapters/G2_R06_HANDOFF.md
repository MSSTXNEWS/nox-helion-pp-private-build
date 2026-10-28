# E06 №6 · G2-05 TURBO10 R06 · handoff to E07 (source only)

RunID: NOX-V16-E06-G2-05-20261028T1109MSK-R06
Frozen main: 0b3a7d435be735148d64171deb9027093a89646e; tree f108d604c444f718b32aaecfd07b90b8f91b9a6f; GitHub compare main MATCH.
Owner E06 #6, immutable integration candidate parent a29f407eb12377c2b55e0991094e0c736a6efd1f; branch e06/v16-g2-05-atomic-event-20261028-r06.
PR #66 inventory is NOT original raw source_00/01/02 or 729-member verified SourceLock; full native reconciliation HOLD.
No main merge, original assets, D02, WOW, 8 CoreIDs, 5 Persona, owner components, archives, EXE, model weights modified.
Technical change: the ONE existing events.v3 publisher gets exactly the bytes validated before the original native evidence callback. Every event must be bounded JSON, and any mutation of input during evidence/source-lock callbacks FAILS CLOSED; no new event bus/worker/network.
All P02/P03/P05 owner adapters are still registered only under existing PACK01 host lock + owner receipts; voice/MAESTRO/SIP only with real provider, quote and native consent; ModelCenter Pull/GGUF/STOP/Retry remain owner P03; E05 read-only real snapshot; Mobile gateway not established by this source candidate.
TaskIDs G2-05-R06-01..10: 01 main frozen compare PASS; 02 E06 preimage/ownership MATCH own paths; 03 P02 reused source only; 04 P03 reused source only; 05 E05 real-snapshot contract source only; 06 events.v3 freeze source patched; 07 callback mutation fail-closed source patched; 08 Mobile/SIP no side-effect contract retained; 09 8 targeted regressions authored (total 67, native Windows NOT_RUN); 10 E06 SHA receipt/Drive report/one lesson/E07 handoff pending independent readback.
E01 SOURCE PR109 owner, COMPONENT local synthetic, INTEGRATED HOLD, WINDOWS ACCEPTED NOT_RUN, % N/D.
E02 SOURCE PR110 owner, COMPONENT local mocks, INTEGRATED HOLD, WINDOWS ACCEPTED NOT_RUN, % N/D.
E03 SOURCE PR112 owner, COMPONENT local offline, INTEGRATED HOLD, WINDOWS ACCEPTED NOT_RUN, % N/D.
E04 SOURCE PR108 owner, COMPONENT GPU native NOT_RUN, INTEGRATED HOLD, WINDOWS ACCEPTED NOT_RUN, % N/D.
E05 SOURCE PR111 owner, COMPONENT Linux synthetic, INTEGRATED HOLD, WINDOWS ACCEPTED NOT_RUN, % N/D.
E06 SOURCE R06 this isolated branch, COMPONENT 67 defined/Windows NOT_RUN, INTEGRATED HOLD, WINDOWS ACCEPTED NOT_RUN, % N/D.
E07 SOURCE PR46 historical diagnostic, COMPONENT installed final EXE absent, INTEGRATED HOLD, WINDOWS ACCEPTED NOT_RUN, % N/D.
Weighted accepted = 0.20 P01 + 0.25 P02 + 0.20 P03 + 0.25 P04 + 0.10 P05 = N/D.
E07 gate: freeze owner reconciled tree + original 3 raw parts/729 SHA, installed single BuildID and EXE SHA; run one fresh Windows native install/update/rollback, WebView2→Python IPC, Ollama /api/chat + STOP and no late SQLite write, P03 model/GGUF queue, P05 real telemetry/providers and authenticated private Mobile gateway. No auto paid call.
Exactly one practical lesson: ATOMIC_EVENT_ENVELOPE — capture bounded canonical source bytes before native callbacks, revalidate unchanged provenance and publish a fresh copy of the identical attested snapshot. Engineering check, NOT LoRA retraining.
