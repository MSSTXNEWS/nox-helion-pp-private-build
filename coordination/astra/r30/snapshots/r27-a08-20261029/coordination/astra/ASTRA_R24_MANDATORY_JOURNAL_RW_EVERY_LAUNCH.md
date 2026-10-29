# R26 SOURCE/BUILD TARGET CORRECTION — OWNER CHOSE GITLAB FREE (2026-10-28)

Primary Windows build platform **is GitLab Free**, not Azure or GitHub Actions: private `https://gitlab.com/s-grouptwet/nox-helion-pp-private-build`, historical branch `migration/nox-v16-gitlab-free-20261028-r01`; pipeline `3000422727`, Windows job `17549234693`, runner `saas-windows-medium-amd64`; P02 test failed, no EXE. GitLab CI source files (present on GitHub migration branch): `.gitlab-ci.yml` → `coordination/e06/gitlab_windows_entrypoint.ps1` → existing stage descriptions `azure-pipelines-nox-v16.yml` → original `private_build.ps1` + `coordination/e06/build_onehost_installer.ps1` → receipts under `work/gitlab-artifacts/`. GitLab branch not proven synced with current Astra; source Git histories diverge. **Read the exact verified handoff** `coordination/astra/ASTRA_R26_GITLAB_FREE_PRIMARY_BUILD_HANDOFF.md` before acting on build assumptions. Astra edits only source in its GitHub working branch; GitLab final synchronization/build belong to later separate integrator after full source completion and SourceLock. DO NOT launch GitLab CI/EXE/NSIS now. Old instructions leaving build provider "undecided" are superseded. 56 V15 rules, 10x10 agent matrix, Drive error/lesson readback remain binding.

# NOX HELION · ASTRA R24 · 56 V15 RULES + ERROR JOURNAL + SELF-IMPROVEMENT
## MANDATORY before/after EVERY actual Astra supervisor LAUNCH, append-only, evidence-first

**OWNER INSTRUCTION:** 56 consolidated V15 rules and past error journals are permanent prerequisites, not optional references. Every actual launch reads rules + last errors + lessons BEFORE coding, and writes factual results AFTER coding, verifying Google Drive readback. No write → REPORT_GATE=HOLD (source code commits still kept). This is a hard control, not a reason to spend all tokens journaling or to fabricate ten agents.

### 1. Canonical rule file (56/56 exact)
**READ FIRST:**
`coordination/astra/ASTRA_V16_R24_ALL_56_V15_RULES_EXACT_SECTION33.md`.
This is an unchanged copy of the complete numbered 01..56 list from V16 §33, verified 56/56, and links to original V15 FIN ZAGR: https://drive.google.com/file/d/1CTwrMzhusE4DYKIwhOdrnNmyhOSPERbV/view .
V16 main: https://docs.google.com/document/d/11EM0qW3PJN0WqV8Euc1A2X4c0UukHiVq_0WfaLYVYpc/edit
**Priority:** §54 owner SOURCE_FIRST overrides obsolete V15 organizational instructions for 7 operators/old cycle count and old early build. IT DOES NOT override or delete features (D02/8 CoreIDs/5 Persona/WOW200/50+50/729), progress formula or logs/QA. Every agent maps relevant rules to specific owner TaskIDs; if unclear, HOLD, don't reinterpret to reduce scope.

### 2. Exact error, run and learning documents (Google Drive)
Each of the following documents has been *successfully read* during preparation of this protocol:
**ACTIVE ERROR MASTER / V16 JOURNAL, primary read+write:**
https://docs.google.com/document/d/1qPG5zZIrqHvAxOzjeLqGKN12gxjeNf0Pj4bHMJrjS50/edit
Document title NOX_GROWTH_JOURNAL_MASTER_CONTINUATION_V16_20261028_R04 ; it records error details, current P0/P1, RunID, source status and per-block evidence. **This is the live error master**. Treat existing entries as immutable.
**HISTORICAL ERROR JOURNAL, read every launch, append a compact new status only when appropriate/authorized:**
https://docs.google.com/document/d/1DzXIiABcXOgh4fyaCz84ApEp59lY317HRgVdPtXNVLU/edit
Title NOX C34 Error Journal ; historical C34–C76 entries and their no-loss lessons. It is not a substitute for current V16 master. Never clear or rewrite history; append if owner has write permission. If user expects one consistent active log, the V16 master is the authoritative write target, but C34 must still be inspected for recurrent root causes and marked HISTORICAL.
**RUN REPORT, read delta + append every launch:**
https://docs.google.com/document/d/17scXv-pnI0hJYAw1I706cxc3lybsO23yue1AIYsmNU4/edit
**SELF-IMPROVEMENT JOURNAL, read last actionable lesson + append every launch:**
https://docs.google.com/document/d/14FXmVrgd7rCR7mDKDfJ-1hpbU6DNI_Znqk1af_6BrDQ/edit
**EARLIER MASTER, historical read reference (no large overwrite):**
https://docs.google.com/document/d/1evk2XhCAT_zY97MmMunTCCHXViSlnTshf2EzfKYWR98/edit

All four active Google Docs have independently verifiable document IDs. Supervisor owns Google Docs writes, not each of ten agents; avoids Drive CAS contention and lost appends.

### 3. REQUIRED START-OF-RUN EVIDENCE
Before choosing source tasks record one immutable local checkpoint:
- `run_id` unique and exact, `started_at` real observed time, Astra working source HEAD SHA, `source_baseline` and actual GitHub access.
- `rules`: 56/56 numbered rules read, linked source/revision, which ones apply to this run, any conflict with newer V16 §54 explicitly resolved by priority, never discarded.
- `error_master_last_seen_runid`, `historical_error_c34_last_relevant`, last master error `OPEN/CLOSED/HOLD`, last self-improvement lesson ID, last E06 report RunID, prior product TaskIDs and latest SHA in relevant owner paths.
- `mistakes_to_avoid` from journal: e.g. stale HEAD writes, repeated EXE builds, already-patched defects, fake Done/100%, missing Drive CAS proof, unsafe STOP/ACL/SourceLock or discarded WOW assets.
- Extract only *new delta* since prior confirmed checkpoint when possible; avoid rereading full 1MB+ docs every approach if unchanged. If tool returns whole Google Doc, extract relevant last RunIDs and record document revision. Master original bytes not to be rewritten.

### 4. DURING TEN AGENT PASSES: REAL CODING + ROOT-CAUSE LEARNING
A01–A10 actual agent roles and passes: `coordination/astra/ASTRA_V16_R23_10_AGENTS_X_10_APPROACHES.json`.
Each agent gets last applicable error/lesson and owner preimage SHA. For each actual pass record:
`agent_id`, `approach_index`, `TaskID`, original issue/root cause, exactly changed code file/commit, RED→GREEN or targeted test command/result, fixed or unresolved evidence, next prevent-regression lesson.
The *next pass* must apply one actionable lesson from prior launch/pass to an actual source check or code change and cite its regression. No "self-training weights" claims: process self-improvement is source QA + memory; P04 GPU real LoRA/QLoRA training is a separate hardware/rights-gated function.

### 5. REQUIRED END-OF-LAUNCH APPEND + READBACK — EXACT FOUR-DOC CONTROL
Coordinator appends exactly one compact immutable `ASTRA_RUN_<RunID>` block per **actual Astra launch**:
1. **ACTIVE V16 ERROR MASTER:** new error IDs, original vs current status, what was fixed with real code receipts, remaining reproduction P0/P1, root cause, location, NO_NEW_ERRORS if none, novel QA-gate failures. Never erase previous master errors.
2. **E06 RUN REPORT:** exact RunID, real spawned agent receipts (or SPAWN_UNAVAILABLE), per-agent completed approaches / 10, new *verified* product TaskIDs, code SHA, isolated actual tests, remaining P01–P05 blockers and integration/Windows=NOT_RUN.
3. **E06 SELF-IMPROVEMENT:** exactly one genuine lesson `R24_LESSON_<RunID>`: observed error, precise root cause, source prevention action/test, prior lesson applied yes/no with evidence, performance lesson for next pass. If no genuine new lesson, document `NO_NEW_LESSON` accurately, not an invented cure.
4. **Historical C34 Error Journal:** read every launch. Append a succinct pointer to the primary master RunID only when permitted/needed to bridge the historical journal, preserving C34 records. If no permission or journal is designated historical read-only, mark `C34_READ_PASS_WRITE_NOT_REQUIRED` and do NOT quietly claim a saved C34 write. The mandatory new-error write is the active V16 master.

**WRITE PROCEDURE:** Google Docs append via `batch_update_document` with latest `requiredRevisionId` (or equivalent CAS) and `endOfSegmentLocation/tabId`; write when necessary. If concurrent edit changed revision, *reread, reconcile and retry once*. Read each changed document back and verify exact RunID and new content text, not just success response. Record write status per Doc `READ_PASS+APPEND_ACK+READBACK_PASS` or `DRIVE_WRITE_HOLD`, including last observed revision and why. Do not claim save on a failed ACK/readback.

**Fallback:** on any failed Google Drive write, commit `coordination/astra/run-receipts/<RunID>_DRIVE_HOLD.json` with exact desired payload/error/target URL, preserve user data; retry in next authorized run, no fabricated Google Drive success. Do not overwrite an existing backup/RunID.

### 6. Progress bars per launch — keep numbers honest
Print exactly 10 agent pass bars:
`A01 [##........] 2/10 PASSES`, `A02 [..........] 0/10 PASSES`, … `A10 [...] actual/10 PASSES`.
Use **verified actual approach completions only**, no fictional spawned agents; planned 100 passes != percent product ready.
Then 5 product bars/values **P01 / P02 / P03 / P04 / P05** using original fixed TaskID denominator with weights 20/25/20/25/10; if denominator/evidence unavailable, `PRODUCT Н/Д` (not 0 or 100).
Separately `SourceLock: HOLD/PASS`, `COMPONENT_VERIFIED`, `INTEGRATED: NO`, `WINDOWS BUILT: NO`, `E07: 0/10 NOT_RUN`, `SOURCE_CODE_COMPLETE_CANDIDATE` only with independently checkable coverage.

### 7. What counts as fulfilled
One launch is journal-compliant **ONLY** if 56/56 rules and recent relevant journal delta were checked, actual source work/negative tests recorded, and master/report/lesson appended and read back (or explicitly HOLD with GitHub fallback). Failed or unavailable Drive write is REPORT_GATE_HOLD, **never a veto on saving independent safe source code to the isolated Astra branch**. It is not necessary to write a huge report or rehash all raw 729 ZIP every pass. Never claim code completeness or 100% no loss before original physical ZIP/semantic tests.
