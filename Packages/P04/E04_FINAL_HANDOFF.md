# NOX V16 E04 component handoff
RunID NOX-V16-E04-C07-20261028
Status SOURCE_CANDIDATE; integrated=NO; component-verified=NO; Windows-accepted=NO.

Canonical worker decision: PR7 plus PR12 is the only training implementation. PR6 is an alternative controller with no trainer backend and must not be merged over the selected train_qlora.py. PR6 useful atomic and immutable receipt protection has now been ported into PR12 under the existing training receipt v2 schema. Owner of trainer content=4. Owner of actual application tree merge=6.

E06 ordered handoff:
1. Reconstruct original frozen app source from existing archives and verify its SourceLock. Do not assume repository-root Packages are packaged.
2. Compare exact PR7 base and PR12 head, per-file pre/post SHA-256 and Git blob SHA-1 separately; see E04_HANDOFF_RECEIPTS.json.
3. Serially admit one selected train_qlora.py from PR12 with all RAG services, GPU Guardian, schema and tests from PR7.
4. Connect RagChatContextProvider to existing authenticated chat through #2 and single host bridge #6. Do not create second chat, SQLite or embedded model API.
5. Connect worker process, stop/pause/resume control and v3 progress reporting to existing #5 adapter. No fake GPU values.
6. Run Packages/P04/verify_components.ps1: Python synthetic tests, .NET8 build, in-process fake-loopback RAG ACL/ingest/search/upsert/delete fixture. Any missing runtime=HOLD.
7. Resolve exact compatible Python/Torch/PEFT/TRL/CUDA wheel versions, hashes and licenses for target Windows/GPU; keep dependencies fail-closed.
8. With approved licensed local base-model weights, rights-verified data and available CUDA GPU, run true train/pause/full checkpoint/resume/evaluate/merge. Confirm optimizer, scheduler, RNG, trainer state and adapter in the checkpoint, receipt schema and exact input identity.
9. Produce current source tree seal, exact owner receipts, runtime evidence, BuildID/EXE SHA. Independent E07 evaluates the same Windows EXE; do not claim final release before E07 PASS.

E04 fixed areas: E04.01 ingestion/index; .02 search/citations/chat context; .03 ACL/update/delete; .04 dataset rights and holdout; .05 actual PEFT worker and STOP/PAUSE/RESUME/checkpoint; .06 GPU telemetry, modes, evaluation and merge; .07 events contract, component tests and handoff.

Conditions that keep status HOLD: missing SourceLock, unauthorized dataset, missing model license/revision, unavailable GPU, unverified Windows host. All accepted product progress=N/D until exact complete criteria are evidenced. This handoff is source documentation, not a proof of tests or training.
