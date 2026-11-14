# NOX V16 · E03 direct-source handoff to integrator 6

**RunID:** NOX-V16-E03-CONSOLIDATED-20261028. **Owner:** executor 3 only. **Status:** owner source candidate; host integration/E07 acceptance HOLD.

## Why the approach changed
Previous C40/TURBO10/TURBO11/TURBO12/TURBO13/TURBO14 packages were versioned independently and latest TURBO14 ZIP omitted earlier TURBO11 unique registry/hardware source. This branch now preserves the original C40 ZIP and all committed TURBO10–TURBO12 patches AND materializes the current P03 source into `Packages/P03/Source/`. It restores model review registry, 15 REVIEW_REQUIRED source leads, Windows hardware facts, WinGet exact-ID gate and expanded WebView command schema without replacing archived originals. TURBO13/TURBO14 security changes are in the direct source tree.

## Exact component and build source
- `Packages/P03/Source/P03.ModelCenter/`: existing Ollama transport, queue and worker, immutable installation receipts, catalog, registry, device probes. No second model downloader.
- `Packages/P03/Source/P03.ModelCenter.Wow/`: original P03 micro-WOW UI, CSS, JS, SVG icons, third-party license notices; D02 HOME/MENU/CORE are untouched.
- `Packages/P03/Source/P03.ModelCenter.Smoke/` and `P03.ModelCenter.HardeningSmoke/`: test harness source, not production features.
- `Packages/P03/Source/E03_CONSOLIDATED_RECEIPT.json`: per-path pre/post local source SHA-256 from preserved TURBO14 snapshot, with no removals.
- One source prerequisite `WindowsComponentAdapter.cs` remains in immutable C40→T10→T11 donor chain because direct upload was unavailable. CI assembles it by exact path from the pinned original before compiling. It MUST be integrated by #6 without changing or dropping installation permissions.
- Source may require semantic port into the *actual original Python* `helion/` host identified by E06; do not introduce a second WPF host just because this .NET component compiles. Integrator #6 owns the single native host/bridge and final EXE.

## NO-LOSS / owner boundaries
Do not auto-merge overlapping #5/#8/#17 P03 or overlapping #6/#7/#12 P04 trainer. Keep original source_00/01/02.part, all archival backups, D02, eight CoreID, five Personas, GUI effects 10+10+10, P02/P04/P05, voice/SIP/Mobile. No silent downgrade of authorization gates. Only owner 6 merges with a full extracted app SourceLock, owner-map, verified receipts and route diff.

## Feature truth
- Family-card discovery ≥24 (30 in current candidate) is *not* 15+ legally licensed immutable downloadable artifacts.
- Official model URL leads remain REVIEW_REQUIRED until independently verified tag/revision/license/size/SHA/VRAM; never fabricate model weights or VRAM.
- Pull/GGUF API and component smoke do not prove an actual local Ollama daemon or real GGUF load.
- Client STOP is not a guarantee that all server-side shared Ollama work was cancelled.
- WinGet/Python/CUDA/PEFT checks are read-only prerequisites, not proof a GPU training job ran.
- Original graphics unchanged does not prove a final EXE preserved every function.

## Integrator action
Freeze exact current app tree and SourceLock; audit `Packages/P03/Source` and archived TURBO11 donor with file hashes; reconcile PR #8 queue once; connect ONE host bridge (trusted local WebView2 origin, authenticated user/job ACL, consent, events.v3), P02 installed model selection and P04 GPU prerequisites. Run live local Pull/GGUF/recovery only with rights-approved models, then independent E07 same EXE SHA. Final EXE remains blocked until owners 1–5 are evidence-based complete.
