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

### 2026-11-15 04:07 MSK · COORDINATOR · scheduler dedup and observed E1
- **Read back:** main 3-step Notion relay `https://app.notion.com/p/419acc184a9f81fca144dfe8432e1a5b` had **real E1 04:00** handoff and PR #286; previous GitHub handoff still bootstrap-only, leading to split-brain documentation. Preserved all earlier entries.
- **Attempted action:** unified the **original active** 3 automations `6af903a3a9f0819185c32b64e51e4ecc` (HH:00), `6af903a5c1208191a22263faae73d193` (HH:20), `6af903a81f348191b18f01a8cde7ec05` (HH:40); extended their instructions to include secure Vast/SSH owner access, original WEB/S03/bridge and FORGE/no-loss QA respectively. Existing three duplicating `Automation_c10be790f1cc819192f5678833c2c029`, `Automation_699343fbe37881919cdb75168812fafe`, `Automation_26409201a5f88191875878544488d623` now **paused, not deleted**, to prevent simultaneous operation at the same three minute slots. Schedule exact Europe/Moscow and enabled states were reread from Automations. No service affected.
- **Verified E1 work (source-only):** [PR #286](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/pull/286) owner V135/V136 Resonance bridge improved per-request downstream cancel / upstream AbortController; [Actions #43661088198](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/actions/runs/43661088198) **8/8 Node and 6/6 Python** tests success; newest [Actions #43661204275](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/actions/runs/43661204275) **9/9 Node and 6/6 Python** source acceptance. Native Vast/owner/S03/STOP/optimizer E2E **not** verified in these runs. PR #286 still draft at time of audit.
- **Root cause / lesson:** previous three-job creation was duplicated by another active three-job suite at identical schedule times; shared Notion handoff and GitHub handoff became temporarily inconsistent. Prevent both concurrent native jobs and fake success from coordination-only CI. A dashboard showing 6 active timers is **not** six verified independent execution agents.
- **Change and verification:** schedules/prompts updated; extra three paused; all six read back showing exactly original three enabled + three paused. This GitHub append is coordination-only, CAS by blob SHA; no runtime deployment.
- **Next action (E2, 04:20 MSK):** follow latest Notion E1 and PR #286 SHA (refresh before writing), test original V24/V135 streaming abort, owner ACL/S03 no false done and real Chromium if possible; source-only if OneHost auth not restored. Update both journals with one proof-backed change, and leave E3 an exact SHA and next blocker.
- **Safety:** native side effects, weights, S03, checkpoint, training changes = NONE. Existing Vast #60509551 and model left untouched.

### 2026-11-15 04:11 MSK · EXECUTOR_1 · vast-v131-v50-v51-list · starting_SHA 0b0c4cc1a6a94b33840c5b42b076d6a99e1b7dde

- **Read back:** BOOTSTRAP + concurrent coordinator 04:07 (preserved exactly); also read current PR #256 head, V49 empty inbox and receipts, Notion v0.0.6, original S03 task, previous SSH/Vast/Tigris Actions logs. Existing **original three** hourly automations remain active; duplicate three paused by coordinator; did not create/restart any scheduler.
- **Root cause 1 / fix:** V131/V50/V51 were querying unsupported Vast single-instance GET `/api/v0/instances/60509551/` instead of documented owner LIST GET `/api/v0/instances/`. Changed source to exact ID match only; accepted only `id=60509551` and running status; invalid Tigris/GitHub token shapes fail before HTTP; 404 auth_error is not evidence of server deletion. V50/V51 ephemeral attach still blocked pending authenticated provider API and owner approval.
- **Root cause 2 / fix:** V131 manual job had impossible workflow condition combining `workflow_dispatch` and `github.event.pull_request`; repaired explicit owner + `allow_native=YES` gate. Removed automatic Tigris S3 secret access from PR job, now manual owner-only. V134 status fixture assert moved into V134 source test to preserve test meaning and stop false positive on workflow secret scanner. V136 SSH observer now reports `SSH_LISTENER_REACHABLE`, with explicit `NATIVE_SSH_AUTHENTICATED=false`, not "native reachable".
- **Patch SHA chain:** [078d40ca](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/commit/078d40ca39ebc9d383cff2afb254431608544a0e) → [366c0480](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/commit/366c0480c88a957e0738d97e66153c99ba9e0859) → [4ea7db34](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/commit/4ea7db344abe3dace48ee31b64a19556517bc71e) → [5a33aca5](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/commit/5a33aca5c64158fb9bd3f8b8b8e4f5b59db24ce7). Source changes only, no native actions.
- **Verified tests (SOURCE PASS, not native):** [V131 #43661513855](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/actions/runs/43661513855) **5/5** (manual inspect SKIPPED); [V134 #43661513845](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/actions/runs/43661513845) **4+7** tests, derived release source only; [V50 #43661712760](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/actions/runs/43661712760) **19/19** security/source tests and instance delete guard; [V133 #43661712737](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/actions/runs/43661712737) **232 workflows, 151 sensitive jobs, 0 unsafe automatic native, 0 YAML parse errors**. Intermediate V133 at #43661356342 detected 3 native/false-positive hazards and at #43661671571 1 source-only scanner false positive; both eliminated by final PASS. Do not bypass scanner.
- **Physical blockers persist (HOLD):** [SSH #43660013421](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/actions/runs/43660013421) cannot authenticate without owner-provisioned pinned SSH credentials. [Vast NOX2 auth error #43659434017](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/actions/runs/43659434017) not cured by source routing alone; owner-approved current Vast API key must be verified. [V49 inbox](coordination/bridge/NOX_BRIDGE_INBOX.json) remains `requests=[]`; [V49 receipts](coordination/bridge/NOX_BRIDGE_RECEIPTS.json) remains `receipts=[]` and `live_bridge_verified=false`; no native S03 durability receipt, GPU readback, STOP or model trainer step proven.
- **Lessons:** (1) provider 404 `auth_error` vs wrong API path are distinct: fix source route and then verify authenticated owner key, without deleting/restarting the instance; (2) mocked CI/SSE does not prove live; (3) automatic source QA must not exercise live secrets, and false positives should be fixed by isolating fixture code, never weakening safety.
- **NEXT E2 04:20:** first read PR #256 latest SHA and this exact handoff, coordinator + original E1 PR #286. While SSH/Vast owner admission HOLD, safely test original V29.3/V135 streaming AbortController/cancel and S03 owner/persona false-done paths in source CI, record one proof-backed patch and append to both logs. No production install or duplicate job.
- **NEXT E1 next cycle:** only after owner updates Vast `NOX2` GitHub Secret or authorized pinned SSH keys, perform one owner-gated read-only exact instance status/S03/STOP/bridge handshake; do not attempt repeated credentials unchanged or assert native PASS from banner. No separate paid host.
- **Safety:** remote writes=NONE; weights/S03/checkpoints/training/services=UNCHANGED by this executor; no secret disclosure.

### 2026-11-15 04:24 MSK · V138 CHROMIUM QA HANDOFF
- **Predecessor:** E1 04:00 latest Notion handoff and draft PR #286; avoided parallel writes to S03/OneHost. This is a scoped independent source/browser acceptance result, NOT a GPU or native deployment.
- **Change:** added V138 real-Chromium owner V24 page-path test in [PR #287](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/pull/287), merged **only into PR #286 feature branch** as `7a2f65b4ccf6ca0c4c1ce22d9f9bb04daa6166a0`. On-feature CI triggers enabled via `dabf9f15`; no second backend, server, model or memory mutation.
- **First live source result:** [V138 #43662267142](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/actions/runs/43662267142) 5/5 Chromium PASS against existing owner bridge JS, MOCK native HTTP. Next feature edit awaited `requestAnimationFrame` and stalled Chromium: [#43662443645](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/actions/runs/43662443645) FAIL. The parallel V135 source fix `d1d07c9c` supplied bounded frame fallback; [#43662552979](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/actions/runs/43662552979) again 5/5 Chromium PASS. Our stale source-update attempt was safely abandoned after CAS/pattern drift (no overwrite).
- **New stress-test test-framework error:** added test for a completely suspended `requestAnimationFrame`. Initial [#43662745001](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/actions/runs/43662745001) FAIL because **fixture**, not production V135, incorrectly marked `rafblocked` as `saved=false`. Fixed mock receipt with `b7797fb4`. Next CI [#43662842631](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/actions/runs/43662842631) failed at shell parse before running Chrome: nested here-doc indentation in diagnostic path. Replaced with shell-safe DOM grep in `5546f047`.
- **Final independent proof:** [V138 #43662900138](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/actions/runs/43662900138) **SUCCESS, 6/6 REAL Chromium**: unauth, cancel, preabort, full, rejected-S03, rAF suspended. Existing Node/Python no-loss source tests in same job PASS. The native HTTP/S03 are TEST FIXTURES, no actual OneHost readback; source/browser block accepted at exact SHA `5546f047643f8ec9c2ee78269aab5e9ec5687233`.
- **Lesson:** distinguish contract regression vs bad fixture vs broken CI shell; show exact DOM result on a failing test; always rerun on latest V135 head, not only the isolated test branch. Never claim physical release from this.
- **Next baton:** E2/E3 must inspect latest PR #286 SHA and 6/6 proof, then independently test original full V134 page/script injection order and actual owner-cookie native S03 stream once authorized; native Vast/GPU STOP/checkpoint/Windows remain HOLD (missing SSH secret, NOX2 auth_error). No need to repeat V138 mock source tests without a source change.
- **Native side effects:** NONE; model weights, S03, STOP, service, checkpoints, Windows unchanged.
