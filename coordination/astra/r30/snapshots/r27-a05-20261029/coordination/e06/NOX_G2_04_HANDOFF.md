# NOX V16 · E06 G2·04 · P02↔P04 ONE-HOST handoff (SOURCE ONLY)

**RunID**: NOX-V16-E06-G2-04-20261028T0610MSK  
**Owner**: E06 (#6), integration-only; E02 owns P02; E04 owns P04; E05 owns events.v3; E01 owns original D02/Core/Persona assets.  
**Frozen E06 parent**: `0a832004d4b57127f08d3b045dc864ddf149d8a4` (PR #20).  
**Pinned donor P02**: `4939c92342e170a41dfca101b6a82c82c180041c` (PR #13).  
**Pinned donor P04**: `9ffc97beb1e3db1c869c18ffccff89104bece81b` (PR #12).  
**STATUS**: SOURCE_CANDIDATE / COMPONENT_TESTS_NOT_RUN / INTEGRATED=NO / WINDOWS_ACCEPTED=NO / RELEASE=HOLD.

This is an additive proposal in `coordination/e06/` only. Original P02/P04/729-file app, SQLite, WPF, D02, HELION+8 real CoreID, five approved Persona, WOW 1–200, model weights, Windows binaries, prior PRs and user data are **untouched**. Do not treat a passing mock-wire check as an installed Ollama, hardware GPU, real train/eval, or final EXE.

## One-host owner wiring (must be done by #6 on frozen FULL original app)

1. Native WPF/WebView2 host authenticates current session with existing Windows SID and map to existing authorized SQLite conversation. **No** WebView JSON-derived SID, file path, CoreID authorization or new account/DB. Existing `P02Store` is passed, never initialized against unreviewed host history; resolve PR #13 versus PR #58 shared `p02_runtime.py` ancestor conflict by serial three-way merge and backup-backed native migration first.
2. Admit the existing P02 `ChatBridge` + its existing `OllamaClient`, P04 `LocalRag`, exactly one existing P02/P04 loopback Ollama listener/port, and existing original P01 frozen 8 CoreID/5 Persona registry via trusted host attestation. HELION is the distinct 9th chat target. `context_key` is a locator, not an authentication credential; verify that the token resolves to the actual authorized existing SQLite chat.
3. Bind only existing P04 `p02_callback(index,native_sid)` to `ChatBridge.rag_context`, emitting verified `chat.sources` citations and bounded untrusted excerpts as **user data**, not system instructions. Native ingress retains source frame/STOP control. This code does **not** register a second RAG service or event bus.
4. Actual GPU STOP/PAUSE/RESUME/checkpoint/status commands go **only** to approved P04 already-running managed worker, with #4-issued observed receipts/ACK verified by trusted native host. Action ACK does **not** certify a completed CUDA optimizer step/checkpoint/eval. Owner #4 PR #65 may need serialized adoption after #4 signature; RAG PR #62 collides with other P04 branches: HOLD until preimage reviewed.
5. Only P05 schema-verified original `NOX-INSTALLER-EVENT-v3` producer may emit `training.step`, `checkpoint.saved`, `gpu.sample` etc. P02 `chat.start/chat.delta/chat.sources/chat.complete` are **native chat frames**, not permitted `event_type` values in canonical P05 v3 schema. Do not forge delivery receipt or events.
6. Before final release: reconstruct and seal complete 729-file original SourceLock; compare each owner preimage SHA256, Git blobs separately; review owner-map, no overwrite of any overlap; run native combined WPF+Python clean Windows installer, actual WebView2→Python→Ollama /api/tags + /api/chat streaming/STOP, real authorized RAG citations on existing SQLite, owner GPU worker real CUDA/weights/dataset/checkpoints/eval/merge and truthful P05 events; then #7 independently tests **ONE BuildID and same EXE SHA256** (incl. approved 10+10+10 cinema and Reduced Motion).

## Exactly 10 distinct E06 TaskID evidence slots

| TaskID | Completed engineering work | Acceptance |
|---|---|---|
| E06.G2.04.01 | Read V16 §26–36, master, E06 report/lessons, inspected current P02/P04 owner SHAs | SOURCE |
| E06.G2.04.02 | Created isolated branch from pinned E06 base; no owner files touched | SOURCE |
| E06.G2.04.03 | Implemented native-scope SID, session, Core/Persona registry preflight | SOURCE CANDIDATE |
| E06.G2.04.04 | Bound same Ollama port and existing P02 ChatBridge + SQLite | SOURCE CANDIDATE |
| E06.G2.04.05 | Bound existing P04 RAG callback with verified citations | SOURCE CANDIDATE |
| E06.G2.04.06 | P02 chat streaming/STOP exposure via existing native frames, no second bus | SOURCE CANDIDATE |
| E06.G2.04.07 | Attached optional P04 GPU worker commands, fail-closed on no real ACK | SOURCE CANDIDATE; GPU HOLD |
| E06.G2.04.08 | P05-verified events.v3 forwarding, no fake training events | SOURCE CANDIDATE; LIVE HOLD |
| E06.G2.04.09 | Authored 17 real-owner Python module test cases and pinned 2-OS workflow | TESTS AUTHORED, EXECUTION HOLD |
| E06.G2.04.10 | Generated owner permissions, hashes, receipt and E07 handoff | SOURCE (Windows acceptance HOLD) |

## Permissions ownership map

`chat.send` → owner E02/P02; `chat.rag` → E04/P04 index (authorized through E02 ACL); `gpu.stop/gpu.pause/gpu.resume/gpu.checkpoint/gpu.status` → E04 native worker only, verified receipt; `gpu.observe` → E04 event producer → **existing** E05 verifier/bus. Native trusted WPF host E06 authenticates/authorizes and maps SID and approved P01 immutable identities; WebView does **not** confer privileges. Unbound route or unapproved receipt = HOLD.

## Known HOLDs and tests

- Full immutable unpacked 729-file SourceLock + signed owner preimage and real existing production SQLite schema are not yet admitted. P02 PR #13 vs #58 same file and P04 PR #62/#65 alternate bases overlap; never clobber.
- No licensed GPU weights/training dataset and no NVIDIA runtime here; QLoRA optimizer state/checkpoint/evaluation/merge **NOT RUN**. No live installed Ollama or real WebView2-Python stream proven. Hardware/GUI/SIP/voice/WOW acceptance HOLD.
- GitHub Actions run `40625500707` at earlier proposal HEAD `7ed0f89bc88b77e36df7e04fe941ff0b5dbc63bb` completed FAILURE **with steps=null for both Linux and Windows jobs**. This proves test execution **NOT RUN** and infrastructure/dispatch diagnosis HOLD, not code PASS/FAIL. The later HEAD also requires its own execution.
- `P01–P05` weighted progress (20/25/20/25/10) **N/D**; E01–E05 N/D, E06 HOLD, E07 final NOT_RUN. No fabricated product percentage or claim of EXE 100%.
- Human/AI reviewer #7 must validate same final EXE SHA from **a later E06 final host build**, not this source-only PR.

**One practical improvement (lesson)**: pin a **single native trust attestation** of the approved P01 identities and shared P02/P04 Ollama listener *before* attaching existing P04 RAG to P02 ChatBridge, so a second unverified model endpoint or imposter Core/Persona fails closed before any user history mutation.

Run receipt: `coordination/e06/NOX_G2_04_RECEIPT.json`.
