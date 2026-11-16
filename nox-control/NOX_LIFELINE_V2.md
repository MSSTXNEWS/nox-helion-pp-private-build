# NOX Lifeline V2 — existing OneHost / Supervisor

Status: SOURCE STAGED; HOST DEPLOYMENT NOT VERIFIED. This is a **safety guard**, NOT a second scheduler, model backend, S03 or trainer.

## What was corrected
The V1 sample on the GitHub main branch assumed a systemd unit named `nox-dispatcher.service`, but the verified existing OneHost uses Supervisor programs `nox-dispatcher-t855u`, `nox-priority-scheduler`, `nox-selfheal` and `nox-gpu-watchdog-t865u`. This V2 watches those exact identities through `supervisorctl`. It NEVER operates on the trainer `nox-train-volta-t866u`, the weights, memory databases or checkpoints.

1. The existing NOX mentor already has a native `owner_dispatcher_mentor.py` that writes observed failures to `/root/nox/memory/dispatcher_mentor/events.jsonl`. Source-verified achievements go to `/root/nox/distill/queue/owner_verified_experience.jsonl`; failures and unverifiable suggestions are quarantined. The lifeline does not pretend that writing that queue trains model weights.
2. The lifeline emits a small JSON report under `/root/nox/state/lifeline/state.json` for NOX to inspect. Supervisor keeps the lifeline process alive. A separate independent boot-level monitor remains a HOST ACCEPTANCE gate if Supervisor itself dies.
3. It NEVER restarts a RUNNING but slow process. It checks status every 60 seconds; only `STOPPED` or `EXITED` on three consecutive observations is recoverable; `UNKNOWN/FATAL/BACKOFF` escalates. Every mutation must be locally authorized for one exact name, not from GitHub, an LLM or a prompt.
4. Persistent daily budgets (default two attempts/24h), cooldown, maintenance STOP and pre-action attempt persistence stop restart storms. Any restart is reported verified only after Supervisor readback returns RUNNING with a PID. Ambiguous outcomes are HOLD and the attempt budget is consumed.

## Deployment to ORIGINAL Vast.ai #60509551 only
Authentication and the host identity must be verified via the existing `owner_native_operator.py` SSH workflow (real instance ID, signed key, pinned host fingerprint), or via another owner-authenticated route. Do not upload new code to an unverified IP. Never expose secrets in GitHub files.

Only after authorized connection:
- Inspect `supervisorctl status`, `supervisorctl pid`, `/proc/<PID>/cmdline`, available disk, STOP, trainer checkpoint and live S03; compare exact expected service paths and running master ID.
- Save a rollback copy of affected config and read the current source hash before replacing anything. Do not modify original dispatcher code or its pinned mentor sources.
- Install exact reviewed `nox_native_lifeline.py` to `/root/nox/scripts/`; install `lifeline.example.json` with mode 0600 to `/etc/nox/lifeline.json`; keep `enabled=false`.
- Validate syntax and test in read-only mode: `python3 -m py_compile /root/nox/scripts/nox_native_lifeline.py` then `python3 .../nox_native_lifeline.py --once --dry-run`.
- Copy `supervisor/nox-lifeline-guard.conf` to `/etc/supervisor/conf.d/nox-lifeline-guard.conf`, make `/root/nox/state/lifeline/`, then `supervisorctl reread && supervisorctl update nox-lifeline-guard && supervisorctl status nox-lifeline-guard`. Confirm exact PID, report JSON and all original services still RUNNING.
- After native check and owner approval only, set `enabled=true` and `restart=true` on reviewed control services. The trainer remains excluded. Leave policy disabled if STOP/maintenance signals, process identity or fresh controller metadata cannot be authenticated.

## Neural growth and continuous optimization
The existing verified-experience queue feeds the candidate learning-data path, but it is NOT a receipt of successful weight updates. A true optimizer cycle needs validated live cgroup/VRAM/thermal/SSD telemetry, pinned training data and base revision, an uninterrupted or safely checkpointed optimizer step, model/optimizer/scheduler/RNG states, readback SHA, regression evaluation, rollback snapshot, and independently measured throughput/quality improvement. NOX should propose bounded changes from these receipts, quarantine unverified suggestions, and never bypass STOP, SAFE70 or overwrite the only good checkpoint.

## Native acceptance — all pending
1. Host identity and authorized SSH, 2. service identity/STOP, 3. one safe simulated outage, 4. lifeline restart via Supervisor, 5. real S03 restart persistence, 6. checkpoint and trainer continuation, 7. holdout measured benchmark, 8. proof any new model weights differ and improve quality. Do not report these as PASS from source tests.
