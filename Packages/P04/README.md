# P04 RAG, memory, and QLoRA package

## Scope and integration boundary

This directory is a source package proposal for NOX P04. It provides local retrieval and training primitives; the host remains responsible for Windows user identity, file-picker authorization, attachment storage, chat routing, worker process lifecycle, and user-visible status. The package must not be treated as an integrated or accepted NOX runtime until those host seams are connected and verified on one immutable application build.

### RAG and memory

- Use Ollama's loopback embedding endpoint only. Missing Ollama, model, or vectors are errors; never substitute synthetic embeddings.
- Scope every index record and retrieval to both the authenticated Windows owner SID and conversation ID. A source ID is stable within that scope.
- Upsert by source ID so re-ingestion replaces the prior revision. Persist source and chunk SHA-256 values, offsets, filename, and embedding model identity for citations and integrity checks.
- Retrieval returns ranked passages with provenance. The host adds only the bounded context and citations to a local model request. Retrieved text is untrusted data and must not become system instructions.
- Ingestion accepts already-authorized text or a host-selected bounded TXT/MD file. The host must enforce ACLs and file-selection policy before handing text to this package.

### Training authorization and model compatibility

- Training is fail-closed. Require a dataset manifest with explicit rights approval, consent, immutable dataset/revision identifiers, train and holdout SHA-256 values, owner approval, and a configured external rights/signature verifier. A manifest's self-asserted booleans alone do not prove authorization.
- Require a compatible local model snapshot plus an immutable upstream revision recorded in the run identity. Use trust_remote_code=false; do not download models or datasets implicitly from a training run.
- QLoRA uses Transformers/TRL Trainer with PEFT and Accelerate. Only one Trainer/Accelerate execution path owns the GPU. Quantized base weights are not merged in place; any merge must target a fresh output directory after checking exact base revision and adapter metadata.
- Preserve a separate validation holdout. Report measured train/eval losses and checkpoint receipts only when produced by the real worker.
- STOP and PAUSE act at optimizer-step boundaries and request a full resumable checkpoint. RESUME requires matching model, dataset hashes, and training configuration. An absent or invalid checkpoint remains HOLD.

### GPU ECO Guardian

ECO, BALANCED, and INTENSIVE are cooperative scheduling profiles. They may change queue priority, batch settings, or worker delays. Telemetry may be reported only from a real NVIDIA sensor query such as nvidia-smi/NVML, with unavailable values represented as N/D. Do not claim a hardware power, clock, fan, or temperature cap unless the exact device and driver expose and confirm it. Thermal STOP is a worker-level safety action, not proof of a hardware cap.

### P05 event bridge

Training and GPU events use Contracts/events.v3.json. P05 may classify the event for reporting, but must keep evidence_verified=false unless a separate verifier validates the referenced receipt. A progress event, dashboard bar, or task completion is not a training result or release acceptance.

## Current builder limitation

The current nox-helion-pp-private-build repository is a Windows candidate builder, not the full application source tree. Its private_build.ps1 reconstructs a source archive from source_00.part through source_02.part, checks a pinned archive SHA-256 and base/patched Git trees, then applies a fixed patch chain. Adding these files to this repository alone does not put them into the installer. Before release integration, an owner must rebuild and hash-lock the authorized source archive, bind the P04 patch and dependency lock to the same source tree, update the freeze manifest and builder checks in a dedicated change, then build and accept the same EXE SHA. This candidate package has not been added to that archive or verified in a Windows build.

## Dependency lock

requirements-qlora.txt gives compatibility ranges only. Before a production build, resolve and hash-lock an exact set of PyTorch/CUDA, Transformers, TRL, PEFT, Accelerate, bitsandbytes, datasets, and safetensors wheels for the supported Windows/Python/GPU matrix. Do not use this range file as a reproducible release lock.
