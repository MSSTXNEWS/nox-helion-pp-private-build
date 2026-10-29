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

## E04 acceleration delta: official reusable integrations, no duplicate engines
- Existing local RAG continues using the official Ollama POST /api/embed format with array input, embeddings array, truncate=false and no fallback vectors: https://docs.ollama.com/api/embed
- Existing PEFT worker keeps the official Transformers Trainer checkpoint resume path; optimizer/scheduler/RNG and adapter identity are checked rather than inventing a new trainer: https://huggingface.co/docs/transformers/trainer_recipes
- Existing LoRA merge uses PEFT merge_and_unload(safe_merge=True) in a new output location; base weights and immutable adapter remain intact: https://huggingface.co/docs/peft/main/package_reference/peft_model
- Added a strict non-boolean and finite evaluation-loss gate, plus fail-closed original symlink-root/JSON input checks. Tests import the actual P04 Python modules.
- Optional real local Ollama smoke exists as tests/P04/RagLiveSmoke.csproj. It compiles in candidate CI but is NOT run against a real model there. On an authorized machine set NOX_P04_EMBED_MODEL to an already-installed licensed embedding model tag and run: dotnet run --project tests/P04/RagLiveSmoke.csproj -c Release . No Ollama pulls, internet access or installs are performed by this smoke. Output code 3 means HOLD on unavailable prerequisites.
- No NVIDIA CUDA hardware, rights-attested training set, licensed local base snapshot or full Windows host is available in this connected execution environment; actual QLoRA training, checkpoint resume, eval and merge remain HOLD.
- Integrator #6 must bind these changes to its current SourceLock and single host and execute one authorized GPU session. E07 independently accepts the same EXE SHA. Preserve original D02, approved 10+10+10, WOW and every unique source candidate.

## C14: Windows GPU/VRAM readiness and safe QLoRA resource policy

- Real no-download probe: `py -3 Packages/P04/preflight_local_gpu.py --profile BALANCED --gpu-index 0` on the owner's authorized Windows machine. It checks actual NVIDIA nvidia-smi free VRAM, temperature, installed Torch/PEFT/TRL dependencies and CUDA visibility. It never calls a model server, trains or merges; status HARDWARE_READY_ONLY is not licensed dataset, training, checkpoint or E07 proof.
- train_qlora.py now reserves GUI memory before CUDA and monitors real vendor free VRAM during optimizer steps (ECO 30%, BALANCED and INTENSIVE 20%, minimum 1GiB plus 1GiB startup allowance). On unavailable sensor or insufficient free VRAM, it requests full checkpoint + cooperative HOLD rather than allowing silent memory starvation. This is GPU memory headroom protection, NOT a hard power/clock/utilization cap or proof training succeeded.
- Approved source data is SHA-256 re-attested before AND after datasets.load_dataset. A real result requires exact model revision and license, external rights verifier, distinct train/holdout, actual CUDA optimizer, STOP/PAUSE/RESUME, evaluation and safe merge with signed receipts.
- #6 binds only the one selected P04 runtime to the canonical existing host and current whole-tree SourceLock. Do not activate Python and C# RAG index writers on the same file together. #7 accepts only the final Windows EXE with one exact BuildID/SHA.
