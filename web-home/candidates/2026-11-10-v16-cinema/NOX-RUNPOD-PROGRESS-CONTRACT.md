# NOX HELION — RunPod distillation-progress contract (2026-11-10)

**STATUS: implemented proof-gated web display and read-only auditor; NOT connected to the Pod filesystem or Windows transfer.**

## What exists

- SYSTEM and TRAINING keep their original pages and load `nox-progress-panel.js`, `nox-progress-panel.css`.
- Browser reads the existing owner's same-origin `GET /api/nox/progress` if supported, else a local `nox-progress-receipt.json`.
- When neither a real checkpoint attestation nor the runtime API is available, the panel explicitly displays **HOLD** and no percentage. No external GPU API token appears in the browser.
- `nox-progress-core.mjs` calculates **checkpointed student steps / target steps**, NOT a percentage of transferred knowledge or intelligence.
- `tools/nox-audit-distillation.mjs` verifies local bytes (SHA-256) for each FULL student and baseline weights shard, checks that their combined digest differs, rejects adapter/model-peft paths, and checks the real `trainer_state.json` hash plus matching `global_step` and `max_steps`.
- Quality/evaluation, provenance of the three teachers, and Windows readback **remain HOLD** until separately verified. The auditor intentionally cannot manufacture a completion flag.

## Evidence input

Create `distillation-evidence.json` only from actual worker output. This structure documents **required fields**, not an example of completed work:

```json
{
  "schema": "nox-distillation-evidence-v1",
  "model": "NOX",
  "operation": "FULL_WEIGHT_DISTILLATION",
  "podId": "the actual RunPod Pod ID",
  "observedAt": "ISO timestamp from the worker",
  "completedSteps": 0,
  "targetSteps": 0,
  "baseline": {
    "files": [
      {"path": "relative/path/to/full/baseline-model-shard.safetensors", "sha256": "actual sha256"}
    ]
  },
  "weights": {
    "files": [
      {"path": "relative/path/to/full/NOX-student-shard.safetensors", "sha256": "actual sha256"}
    ]
  },
  "trainerState": {"path": "relative/path/to/trainer_state.json", "sha256": "actual sha256"}
}
```

The `0` step values above are **schema placeholders, NOT measurements**. A report with a zero target is rejected, and a missing manifest creates HOLD.

## Read-only verification on the actual owner-authorized Pod

With an authorized terminal and this repository's scripts available on the mounted volume:

```bash
node tools/nox-audit-distillation.mjs --workspace /workspace --manifest /workspace/NOX/distillation-evidence.json --out /workspace/NOX/nox-progress-receipt.json
```

Run from the candidate project root so `tools/...` is present. No model, Pod, endpoint, storage, credential or worker configuration is changed. Do not run a second trainer automatically.

The file must then be moved through the **existing authenticated NOX host/Windows synchronization channel** and independently SHA-256 read back. If that channel is not working, leave `windowsSyncVerified=false`, do not pretend that a file found on the Pod has reached Windows.

## Mandatory next physical gates

1. Owner-authorized Pod workspace read: actual trainer state, full NOX weights, baseline and three teacher provenance reports, no adapters.
2. Evidence run with matching on-disk bytes and timestamped receipt.
3. Independent student-vs-baseline quality comparison (same eval dataset, RU/ES, regressions and skill recall).
4. Actual Windows download and matching SHA-256, then one NOX runtime loads the new student weights and can answer coherently; preserve rollback/STOP.
5. Real GPU, browser and native E2E acceptance. Do not promote production on the basis of mere CI success.

**Do not equate GPU utilization, GPU temperature, downloaded models, number of files, or teacher outputs with verified student-weight distillation.** No authentic project percentage is available until gate 1 and 2 are met.
