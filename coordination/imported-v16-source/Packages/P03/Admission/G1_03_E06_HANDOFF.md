# NOX V16 · E03 G1-03 R02 · ModelCenter C40 owner candidate

**Owner:** №3. **RunID:** NOX-V16-E03-G1-03-20261028T0651MSK-R02.
**Frozen baseline:** commit `0b3a7d435be735148d64171deb9027093a89646e`,
tree `f108d604c444f718b32aaecfd07b90b8f91b9a6f`.
**Pinned original P03 donor:** PR17 at `8657491117f4221c053a0ea5111f68a61f5ad06a`.
**Status:** independent SOURCE candidate only; full extracted 729-source SHA256 SourceLock,
E06 integration, same-EXE Windows acceptance, actual model weights all HOLD.

This admission module adds **no second model downloader, model queue, server, LLM,
voice engine, database, disk mutation or HTTP request**. It is a pure policy
gate for an E06-attested call to existing P03 ModelDownloadQueueStore,
ModelDownloadQueueWorker and OllamaModelAdapter. It never authorizes downloads by
itself. It is not yet connected to the original host.

## TURBO10 TaskID ledger

1. E03.G1.03.01 frozen current Git baseline + PR66 inventory checked; extracted source SHA HOLD.
2. E03.G1.03.02 existing C40 queue, worker and ownership audited without replacement.
3. E03.G1.03.03 25 exact Ollama tag discovery variants copied from original source; 25 HOLD (mutable tags, not immutable pins).
4. E03.G1.03.04 17 multimodal/ASR/TTS/image/video/training/aligner leads source-audited; 17 HOLD (project links not weight artifacts).
5. E03.G1.03.05 Ollama Pull route remains existing `EnqueueVerifiedPullAsync`; no actual download started.
6. E03.G1.03.06 GGUF import route remains existing `EnqueueVerifiedGgufAsync`; actual local file rights/hash and import NOT_RUN.
7. E03.G1.03.07 byte-progress monotonic per attempt gate added; no synthetic percent.
8. E03.G1.03.08 STOP is an unconfirmed request; retry requires a new job receipt and cannot be silently called completed.
9. E03.G1.03.09 checks frozen commit/tree, donor, session, user consent, license URL/ack, SHA256, revision, rights receipt, native measured disk/VRAM, attestation.
10. E03.G1.03.10 Python/Git/Ollama/CUDA/PEFT prerequisites guarded from trusted host facts; real Windows CUDA/PEFT NOT_RUN.

**Model truth:** 25 concrete tags are TAG leads, not 25 immutable verified
artifacts; nothing becomes a button that initiates a download until independent
artifact SHA, pinned revision/manifest, rights receipt, actual bytes and native
hardware requirements are verified by #6. ASR/TTS/video external downloads are
HOLD because existing queue has no verified external transport.

## E06 №6 handoff (non-destructive)

Only after owner6 approves exactly one extracted SourceLock and reconciles
PR5/8/17 P03 preimages, add one call to
`admit_for_existing_downloader(evidence, context, existing_trusted_owner_attestor)`
at original host's authorization boundary; after PASS, call ONLY its verified
existing queue method, under P02 native session permissions. All evidence values
must be from owner receipts and real native hardware, **not** editable VRAM UI
input or user-provided strings. Passing this gate is not proof that an Ollama
model was installed. The original adapter still must check pulled manifest
digest and local GGUF bytes/SHA.

CI runs 32 offline deterministic regressions on Windows+Linux, with one pinned
immutable original owner3 source read. If GitHub Actions has 0 executed steps,
mark TEST_NOT_RUN, not a successful compilation. No change to main, original
D02/WOW, archives, owner runtime, EXE, models or data; original PR branches are
not merged, rebased, deleted or overwritten.
