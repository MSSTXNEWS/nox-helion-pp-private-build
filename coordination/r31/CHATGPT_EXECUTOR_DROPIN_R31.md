# NOX HELION · ChatGPT Executor Bridge R31

**ChatGPT does not support installing arbitrary binary "patches" inside its chat engine.** This is a small prompt+structured-receipt+external-validator integration using existing GitHub, T02, and the protected NOX site. It neither grants tool rights nor creates new executors or TaskIDs.

## READY: manual activation suffix for existing roles #1/#3/#2

Append to each existing manual role prompt (do **not** replace its canon and owner permissions):

> **NOX_CHATGPT_OTCH1_R31 · 1 = 10 MEANINGFUL APPROACHES · MANUAL FIRST.** Preserve the full 56 §33 rules, §§54–56/R29, original SourceLock 729/3 ZIP, D02/WOW200, all DONE, TaskID, consent/STOP/ACL/NO-LOSS. At each `1`, actually perform A READ (revisions/HEAD/register), B PHYSICAL (authorized work), C JOURNAL (exact ERROR_ID/T02 handoff), D LESSONS (root cause/recurrence), and E ОТЧ-1 (visible factual bars). Run up to ten **real** sequential approaches; no synthetic tasks, commits or approvals. After real Git save/readback, submit one immutable receipt to the existing authorized role/branch, then post a short immutable handoff link to GitHub Issue #177 for T02. Append one well-formed machine-readable `NOX_OTCH1_JSON_BEGIN ... NOX_OTCH1_JSON_END` block with the exact schema below. If readback or journal CAS fails, report BLOCKED/PARTIAL with error ID and truthful last-run checkpoint. No ChatGPT response can self-certify `QA_ACCEPTED`, `SOURCE_READY`, journal CAS or product %. Preserve role scopes: #1 shared source integrator, #3 isolated P04/P05 owner, #2 independent QA; AUTO roles only assist.

### JSON envelope (source of truth is Git receipt, NOT the pasted text)

```text
NOX_OTCH1_JSON_BEGIN
{
  "schema": "NOX_R31_CHATGPT_OTCH1_RECEIPT_V1",
  "run_id": "NOX-M1-EXAMPLE-C01",
  "executor_id": "1",
  "task_id": "P04/model_snapshot",
  "started_at": "2026-10-30T00:00:00Z",
  "finished_at": "2026-10-30T00:20:00Z",
  "source_head": "0000000000000000000000000000000000000000",
  "approaches": [],
  "cycle_complete": false,
  "gates": {
    "A": {"status": "PARTIAL"},
    "B": {"status": "NOT_RUN"},
    "C": {"status": "BLOCKED"},
    "D": {"status": "NOT_RUN"},
    "E": {"status": "NOT_RUN"}
  },
  "error_ids": [],
  "stage": "QA_PENDING",
  "physical_proof": null,
  "journal_sync": "PENDING_T02",
  "product_percent": null
}
NOX_OTCH1_JSON_END
```

**This JSON block is only a shape example**, not a real run, SHA or evidence. Replace all fields with verified values. Do not use the placeholder SHA to claim work.

Accepted approach proof: `{"n":1,"status":"DONE","proof":{"git_blob":"<actual 40-hex>","git_url":"https://github.com/MSSTXNEWS/nox-helion-pp-private-build/blob/<exact-commit>/<authorized-owner-path>"}}`. Only `DONE` with valid proof counts. `cycle_complete=true` requires ten real verified approaches.

### Delivery and evidence chain

1. ChatGPT executor owns its **authorized task**. Git write requires current exact PRE/CAS/readback, not merely a link.
2. Existing Issue #177 is the handoff index; user-facing OТЧ-1 is not a substitute for immutable Git receipts.
3. T02 (sole shared ledger writer) obtains per-ID last **actual** run from authenticated Automations.peek for AUTO; manual last-run comes from immutable owner receipts. It does **not** infer individual manual activity from automation run counts.
4. Run `chatgpt_otch1_adapter.js` to parse and validate shape. It returns `NEEDS_GIT_READBACK` even when shape is valid.
5. Use `nox_delivery_watchdog.js` to match `executor_id + RunID`; verify actual Git blob and exact HEAD; check history coverage. An incomplete receipt index must say `RECEIPT_INDEX_INCOMPLETE`, not fabricate a missed receipt.
6. Update the protected dashboard snapshot only after T02 CAS/readback. If E06 or Git CAS fails, mark `BLOCKED_OR_UNVERIFIED` and **never** mark 100%.
7. The R29/R30 progress graphs require independent same-HEAD QA receipts and a fixed denominator; where absent, show N/D.

## What we do **not** claim
- Cannot modify ChatGPT's underlying model, its private chain of thought, or enforce other manual chats from here.
- Cannot guarantee that an executor delivers unless GitHub/Issue receipts and T02 CAS readback are observed.
- The guarded JS files have local syntax and test checks; they are **not** a deployed network service until integrated with an authenticated runner/API.
- This specification does **not** approve the Windows build or release; T09/T10/T11/T12/T13 gates remain.

## Test commands
- `node coordination/r31/test_chatgpt_otch1_adapter.cjs` — 14 checks covering shape, 10 approaches, old HEAD, forbidden self-acceptance, journal claims.
- `node coordination/r31/test_nox_delivery_watchdog.cjs` — 14 checks covering missing/stale/unverified run receipt and journal/panel failures.

## Ready-made official components to consider for future migration
- ChatGPT scheduled tasks and eligible event-triggered GitHub events (subject to account and approvals).
- OpenAI Agents SDK built-in tools/MCP, guardrails, handoffs, tracing and recorded execution.
- Structured model outputs in API apps for guaranteed JSON **syntax**, not verified real-world effects.

Avoid adding a second backend, second LLM, or third-party untrusted script; prefer the existing NOX Vercel/GitHub contracts.
