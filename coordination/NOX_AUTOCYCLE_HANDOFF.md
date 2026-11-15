# NOX HELION · ONEHOST · HOURLY CONTINUITY HANDOFF

> Shared baton log for the 3 hourly ChatGPT executors. Canonical source = this file on `feature/nox-v38-synaptic-brain-20261114`; PR #256 is the fallback ledger, and Notion Agent Task Control holds only verified durable task state. Never promote this document itself as a proof of production deployment.

- **Timezone:** Europe/Moscow (UTC+03); execution slots every hour `:00`, `:20`, `:40` beginning 2026-11-15.
- **Executor 1:** Vast / current SSH routes / GitHub V49 bridge / native access / inventory.
- **Executor 2:** existing OneHost, WEB V29.3/V135 «Резонанс», original S03 M0–M7, C01–C08, owner ACL, native route integration.
- **Executor 3:** FORGE full-weight optimizer proof, STOP, backup/checkpoint/restore, GPU safety, independent evaluation, Windows acceptance.
- **Single source:** [PR #256](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/pull/256); [Notion existing task](https://app.notion.com/p/417acc184a9f812ba675ff098621eec6); [Agent Operating Guide v0.0.6](https://app.notion.com/p/40cacc184a9f8154ba82feaa8f963e65).
- **Work loop:** read latest branch SHA, this handoff, GitHub receipt/CI and Notion task; verify the previous executor's SHA/outputs; pick the earliest safe unblocked step; patch → test → save; append your signed-off *observations* below; give next executor one concrete next action.
- **Concurrency discipline:** before modification reread repository HEAD and current file blob SHA. Commit with optimistic concurrency (GitHub contents API expected SHA), do not force push or overwrite a newer entry. If previous job still active, do not double-execute native actions. On conflict, re-read and retry once without losing entries; if unsafe to merge, comment on PR #256 with a unique executor/time/run ID and HOLD rather than clobber.
- **Структурированный журнал ошибок:** [NOX_AUTOCYCLE_ERRORS.jsonl](NOX_AUTOCYCLE_ERRORS.jsonl) содержит стабильные error_id, проверенную причину, lessons и безопасное следующее действие. В каждом цикле сначала ищи error_id и текущий статус; новую ошибку добавляй одной уникальной строкой через свежий blob SHA. При подтверждённом исправлении добавь новое событие того же error_id со ссылкой на PASS (не удаляй прежние события). Если одновременная запись конфликтует, сохрани факты в PR #256 comment и укажи conflict=HOLD.
- **Evidence vocabulary:** `PASS` only for proof attached to exact operation, `HOLD` for blocked/unverified, `FAIL` for attempted and failed. GitHub source CI != native server acceptance. Record test count, SHA, run URL and exact scope.
- **NO LOSS:** existing Vast.ai instance #60509551 only; no new billable host, no competing backend, no arbitrary remote shell, no export of keys/passwords, no blind GPU restart, no S03 or checkpoint deletion. Owner authorization, native STOP, offsite backup/restore and rollback gates before production mutation. `NOX2` Vast GitHub Secret is not the Tigris `nox2` object-storage key.

## Latest verified baseline · 2026-11-15 ~03:55 MSK

| Item | State | Evidence |
| --- | --- | --- |
| SSH relay `ssh9.vast.ai:26623` | TCP open, valid SSH-2 banner; authentication **not** proven | [V136 #43659934388](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/actions/runs/43659934388) |
| SSH direct `166.113.48.41:11234` | TCP open, valid SSH-2 banner in GitHub runner | [V136 #43659934388](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/actions/runs/43659934388) |
| SSH auth via existing GitHub Actions secrets | **HOLD**, `NOX_VAST_SSH_PRIVATE_KEY` empty; `NOX_VAST_SSH_KNOWN_HOSTS` unconfigured | [#43660013421](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/actions/runs/43660013421) |
| Vast API `NOX2` | **HOLD**, cloud/console `/api/v0/instances/` both `404 auth_error`; does **not** prove instance deleted | [#43659434017](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/actions/runs/43659434017) |
| V49 GitHub mailbox | inbox `requests=[]`, receipts `[]`, `live_bridge_verified=false`; owner HMAC signer + timer not verified | [V49 bridge](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/blob/feature/nox-v38-synaptic-brain-20261114/nox_runpod/teacher_mesh/v49/onehost_bridge.py) |
| S03 source fix | [PR #280 merged](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/pull/280), source tests 18/18; live native E2E **not** accepted | [source CI](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/actions/runs/43654388374) |
| Live full release / weight training | **HOLD**: no new native optimizer step, verified checkpoint, WEB full E2E, Windows acceptance from latest run | [PR #256](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/pull/256) |

## Priority handoff queue (never claim execution from a plan)

1. E1: prove owner-controlled SSH key or already installed V49 signed callback; retrieve *read-only* native instance, STOP, GPU/disk/S03 and bridge receipt without bypassing authorization.
2. E2: after E1 evidence, connect real OneHost/S03/WEB V29.3 and run bounded authenticated streaming and memory durability tests; otherwise source fixes and tests only.
3. E3: after native and backup/restore gates, investigate `train_error step=0`, checkpoint receipts and real student weight changes; otherwise source gates/tests only.
4. Next-hour E1: read E3 closure and prioritize highest evidence-supported remaining blocker, not the previous failed approach blindly.

## Append-only run and error journal

For every run, add a section in this format; **do not erase previous entries**:

`### YYYY-MM-DD HH:mm MSK · EXECUTOR_N · <run_id> · starting_SHA <sha>`

- **Read back:** predecessor entry ID, SHA, verified state; conflicts or lock.
- **Attempted action:** exact intended operation and bounded scope; commit/workflow URL.
- **Outcome:** PASS / HOLD / FAIL, native vs source distinction; proof URL and exact observed error.
- **Root cause / lesson:** evidence-based reason, one avoided error, or marked UNKNOWN.
- **Change and verification:** patch commit SHA, tests/workflow, reread result; `NONE` if no changes.
- **Next action:** a single executable item assigned to the following executor with unblock condition.
- **Safety:** native side effects / model weights / S03 / checkpoint changes, or `NONE`.

### 2026-11-15 03:55 MSK · BOOTSTRAP · source-only

- **Outcome:** schedules configured for 04:00/04:20/04:40 MSK hourly. No scheduled execution proof yet.
- **Current blocker:** signed SSH authentication not present in GitHub Actions; raw SSH TCP banners alone are not native OneHost access. Vast `NOX2` API credential unverified. No V49 signed receipt.
- **Improvement:** shared cross-executor continuity and mandatory failure-to-lessons conversion, grounded in the linked verified runs above.
- **Next:** E1 verify authentication safely and, if blocked, identify a reproducible source-level gap instead of reporting production PASS.
- **Native side effects:** NONE.
