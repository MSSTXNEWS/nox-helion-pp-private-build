# Existing P04 installer dependency contract — R29 A04

Scope: source-only readiness of the existing Express Integrator P04 worker.
No package installation, model download, training, build, or integration occurred.

## What the source already fixes

At parent `f62b87099472c33ab912e3727f958f94746dd3ce`:

- `private_build.ps1` (blob `75fb303d65d83ab7b272b02bce44a9d3be0956aa`)
  requires CPython 3.12.10, 64-bit and PyInstaller 6.16.0 for its **build venv**.
- `evidence/NOX_HELION_PORTABLE_PREREQUISITES_RUN40210839317.md`
  (blob `0e778ca54ca6fac68337c933c34db39eb3e3a9bb`) records packaging 25.0
  in that historical build environment. It explicitly does not establish an
  owner-selected AI runtime profile or bundled model/provider payload.
- `requirements-qa-win64-hashed.txt` contains document/media QA packages, not
  torch/PEFT/TRL/bitsandbytes. Its hashes cannot substitute for a P04 wheel lock.
- `requirements-qlora.txt` remains the existing eight-package compatibility
  range policy. No exact versions, channels or hashes were invented here.
- Existing `train_qlora.py` already uses Transformers/TRL/PEFT/Accelerate and
  bitsandbytes. Keep that worker and the original RAG adapter; no replacement
  training engine, downloader, environment manager or RAG store is needed.

## Executable readiness correction

`preflight_local_gpu.inspect` now checks installed versions against the exact
adjacent `requirements-qlora.txt` using PyPA `packaging.requirements.Requirement`
and `packaging.version.Version`. Missing/invalid contract or parser returns HOLD;
an installed but out-of-range package is INCOMPATIBLE. CUDA checks cannot turn
these errors into HARDWARE_READY_ONLY.

`dependency_status=RANGE_CHECK_PASSED` means only that the eight direct installed
versions satisfy existing declared ranges. `dependency_lock_verified=false` and
`runtime_compatibility_verified=false` remain explicit. This does not solve the
transitive dependency graph or establish binary ABI compatibility, hashes,
licenses of selected wheel artifacts, or real GPU acceptance.

The next source check uses standard `importlib.metadata` and the same PyPA
parser for each of those eight installed roots: its `Requires-Python`, active
`Requires-Dist` markers and installed direct dependency versions. Conflicts,
missing/malformed metadata and unverified direct URLs return HOLD.
`dependency_metadata_status=DIRECT_BASE_METADATA_CHECK_PASSED` is explicitly
limited to these direct base-package checks. Unselected optional feature
markers are skipped; explicitly requested dependency extras are listed in
`dependency_extras_unverified` for the later resolver, not guessed or claimed
verified. No unrelated environment packages or recursive graph are scanned.

This reuses existing metadata APIs instead of implementing another dependency
resolver. Existing `train_qlora.py` rights, model-lock and
`validated_checkpoint` gates remain in place; no second checkpoint adapter or
training worker was introduced. Earlier A08 checkpoint corrections remain in
their saved owner candidate for the independent integrator.

Reuse evidence: packaging is already a historical build dependency and an
official Transformers dependency. Its Requirement API exists since 16.1 and
its license permits either Apache-2.0 or BSD. No library source was copied and
no new library version was selected. Targeted tests ran with locally available
packaging 26.3; they do not attest the historical 25.0 binary.

## Exact remaining target inputs

| Input | Confirmed | Needed to resolve existing worker wheels |
| --- | --- | --- |
| OS/architecture | Historical build is Windows x64 | Supported target Windows release and whether worker shares that interpreter |
| Python | Historical build CPython 3.12.10 x64 | Approved worker interpreter/ABI; do not silently bind the worker to build Python |
| NVIDIA | Existing worker selects a real GPU UUID | Supported GPU compute-capability floor and driver floor; actual device validation later |
| CUDA | No P04 wheel channel pinned | Owner-approved torch CUDA wheel channel compatible with those floors |
| Package closure | Eight existing direct ranges | Resolver output for that target, transitive versions, official wheel URLs/SHA-256 and artifact notices |

Official bitsandbytes documentation provides Windows x86-64 prebuilt CUDA
wheels. Its supported CUDA/compute-capability matrix differs by release; the
current document cannot be retroactively applied to all versions allowed by
`>=0.45,<1.0`. PyTorch likewise selects binaries by OS/Python/compute platform.
Thus a universal exact dependency set cannot be verified from the current
source inputs. Do not compile vendor libraries from source or install the
latest release merely to fill this missing target decision.

Once those target inputs are fixed, reuse the existing official binary package
route to resolve/hash-lock one compatible closure and preserve its notices.
Real Windows GPU execution is a later verification phase, not a request to
write another training implementation. Final packaging/host integration stays
with the independent integrator.

Finite remaining handoff items for this inspected P04 installer contract
(not a complete product TaskID denominator):

1. `P04-INSTALL-TARGET-PROFILE`: bind approved worker ABI/Windows and GPU/driver/
   CUDA policy to this handoff; target-specific source inputs remain unknown.
2. `P04-INSTALL-WHEEL-CLOSURE`: resolve the existing `requirements-qlora.txt`
   for that profile, including declared extras/transitives; commit exact
   official wheel hashes/notices through the existing packaging route.
3. `P04-INSTALL-AUTHORIZED-RUN-INPUTS`: supply model-lock/dataset/holdout/verifier
   evidence to existing `train_qlora.py` gates and an approved embedding model
   to the selected existing RAG adapter. These are operating inputs, not a
   request for another engine or made-up rights approval.

After those decisions, independent host composition and Windows/GPU acceptance
remain separate phases. Hardware unavailability does not mean new training
code must be invented. No additional concrete source defect is asserted here
without a failing test.

## Official references inspected

- https://packaging.pypa.io/en/stable/requirements.html
- https://packaging.pypa.io/en/stable/specifiers.html
- https://packaging.pypa.io/en/stable/markers.html
- https://docs.python.org/3.12/library/importlib.metadata.html
- https://github.com/pypa/packaging/blob/main/LICENSE
- https://github.com/huggingface/transformers/blob/main/src/transformers/dependency_versions_table.py
- https://pytorch.org/get-started/locally/
- https://huggingface.co/docs/bitsandbytes/v0.45.0/installation
- https://huggingface.co/docs/bitsandbytes/v0.48.0/installation

No complete wheel set, model rights or hardware compatibility is declared
verified by these web references alone.
