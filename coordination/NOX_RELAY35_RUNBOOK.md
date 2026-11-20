# NOX HELION · RELAY35 · 7×5 · 2026-11-19

instructions_version: 0.0.6

This is a **planning/handoff manifest**, not an executable native taskpack and not a second dispatcher. Task IDs and spec SHA are copied from [original 295 evidence](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/blob/c4683943fe17368ab2086f6ae7ff27ad21732ef7/nox-control/complete_executor_20261118/evidence/all295_execution_disposition.json).

## Global worker algorithm

1. Read `coordination/NOX_RELAY35_20261119.json` at an exact source commit; read latest native owner state/claims and original acceptance receipts. **Do not claim solely based on a static backlog.**
2. Choose the lowest-rank **eligible**, not accepted and not leased original TaskID from the 35; the five seeded tasks per lane are hints, not exclusive assignments. Skip blocked work and take another free TaskID, with source-path conflict avoidance.
3. Obtain a unique owner/CAS lease in the **existing** NOX dispatcher and bind to the original spec SHA, exact source preimage and immutable verifier. If the lease or admission fails, do not mutate.
4. Each worker owns the whole lifecycle: implement a substantive change → **one** focused verification (no repeated QA loops) → **one** integration through the reviewed path → configure → save source+native receipt → enable if allowed. No central assembler or isolated testers.
5. Verify the actual result at its specified scope: source, native installed SHA, browser/OneHost/S03 or Drive readback as relevant. Classify as SOURCE_CHANGED, SOURCE_VERIFIED, NATIVE_APPLIED, NATIVE_EXECUTED or ORIGINAL_ACCEPTED. Count toward 295 **only** with an independent exact original acceptance record.
6. Handoff next unclaimed task immediately; if the claimed task is blocked, record only its concrete blocker, release/reconcile the claim by existing CAS, and continue independent work. Never rename/replay terminal task IDs.
7. For failed subagent/worker: check fresh supervisor/PID/start_ticks, STOP, owner lease and resource admission; restart only the failed *owned* process by existing reversible runbook. Do **not** reboot Vast or terminate healthy model/proxy/web/active jobs. Native physical concurrency stays **3**, even though six scheduled assistant lanes plus A0 exist.

## Seven lanes, five starting tasks each

| Lane | Seed TaskIDs | Scope |
|---|---|---|
| A0 (lead) | 1A03, 1A02, 1V14-06, 3A01, 3A04 | Resume, message identity, STOP, C01–C08, self-model |
| A1 | 1A01, 6A05, 3A02, 3A03, 3B01 | Stream, truthful blocker/retry, S03, FTS, Hunter |
| A2 | 1V14-01, 6V14-01, 6V14-04, 6B01, 4A02 | Endpoint, existing dispatcher, task states, fairness, quality dataset |
| A3 | 6B04, 0A03, 3A05, 6A03, 3B02 | Recovery, browser/S03 contract, checkpoint readback, yield, provenance |
| A4 | 6A02, 0A01, 2V14-03, 6A04, 3B03 | CAS, sequence, owner restart authority, GPU budgets, search |
| A5 | 0V14-02, 5V14-01, 2A02, 2A05, 4B01 | Priority queue, WEB, storage, latency, FORGE |
| A6 | 1A04, 0B05, 2A03, 2A01, 4B04 | STOP UX, end-to-end demo, model SHA, GPUs, DREAM |

**Global stealing:** If the seed is already claimed, DONE, or not currently admitted, any lane immediately selects the highest-ranked eligible TaskID from another seed. No lane may claim an original already owned by another executor. Each lane's cap is five *completed full-cycle work attempts* for this relay; unfinished attempts are not counted as completed tasks.

## Current known blockers, do not misrepresent

- Latest owner source evidence: one-turn live SSE and owner-dialog first-turn readback were proved in [run #44586143135](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/actions/runs/44586143135); two-turn exact S03 independent writer/readback is not proved.
- Native refill package has sometimes held on active claims (e.g. [#44586844544](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/actions/runs/44586844544)). Never override a real lease or blindly republish stale tasks.
- Current server-side Google Drive `rclone` OAuth remains `CONFIG_MISSING` in [#44583655578](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/actions/runs/44583655578). No Drive offload or remote deletion before owner OAuth and hash readback.
- Cgroup raw RAM was low on observed snapshots; CPU/source-only work may proceed independently when admitted, but no GPU model load, RAM staging or training without fresh separate admission.
- GitHub repository is **public**: no tokens, personal data, server secrets or private samples in source/CI receipts.

The current goal is physical useful progress with evidence, not 35 fabricated PASS statuses or the creation of 35 duplicate queues. Existing Automations A1–A6 recur hourly and D1–D3 own recovery/resource/dispatch controls.
