# NOX HELION · R30 — Evidence-based executor velocity

Purpose: show real growth / decline for each **manual primary owner** and **supporting automation**, without manufacturing performance from reports or Git commit counts. No new product TaskID, role, backend, model, runtime, or release permission.

## Reuse before new dependencies
- Reuse the existing D02 cinematic styling in `coordination/r26/nox-control-center.html` and NOX Cinema FX CSS conventions in `proposals/NOX-CINEMA-FX/nox-cinema.css`.
- Reuse the existing NOX R29 actual-run clock/curve module `coordination/r26/nox-ops-timing-r29.js`, current executor roster `coordination/r29/NOX_EXECUTOR_ROSTER.json`, and T02 journal owner. These provide actual run times, enabled state, statuses and scope, **not automatic proof of accepted product functionality**.
- Reuse native SVG for small trend sparklines: this avoids large new JS dependencies, build tooling, privacy-leaking CDNs and loading/initialization costs. For future very long timeseries, official **uPlot** (MIT) and **Apache ECharts** (Apache-2.0) were evaluated as optional locally vendored choices, not shipped here.
- UI module `coordination/r26/nox-executor-comparison-r30.js` added to existing Control Center. Zero external packages.

## Required input (T02 coordination only, permission-preserving)
`window.NOX_CONTROL_DATA.performance_history` can be a T02-signed export (or `window.NOX_PERFORMANCE_HISTORY`) with:

```json
{"schema":"NOX_R30_HISTORY_V1","snapshots":[]}
```

Only populate with **real, SHA-checked** historical observations of the exact existing TaskID ledger:

- `snapshots[]` — ordered events `{ "at":"UTC or offset ISO8601", "head":"full 40-char current PR HEAD", "workers":[...] }`.
- `workers[]` — `{ "id":"manual or auto canonical ID", "accepted":integer >= 0, "integrated":integer >= 0, "fixed_total":integer|null, "receipt_blob":"real 40-char Git blob", "evidence_url":"verified github.com URL", "qa_reviewer":"manual-2"|null }`.
- `accepted` is **cumulative unique TaskIDs actually accepted by independent QA** at that HEAD. A manual author, owner, helper, passing unittest, completed automation or raw Git receipt is insufficient.
- `integrated` counts distinct stage-integrated TaskIDs with exact Git readback, **not** QA acceptance and not additive with accepted.
- `fixed_total` only after the full criterion denominator is frozen for that role. Unknown must be `null`.
- Source of each snapshot: T02's verified CAS/readback of its own immutable ledger, same-HEAD independent receipt and timestamp; T02 must not pass arbitrary Sheet events as independently accepted tasks.
- If original source HEAD changed and no independent revalidation exists, leave the new HEAD's accepted fields missing. Do not carry them forward blindly.
- Preserve snapshots as evidence/history even if a role is paused or archived. The current roster controls visibility, not data deletion.

## Metrics and mathematical limits
- **Δ accepted** = accepted at latest verified snapshot − previous verified snapshot, only if they share one exact HEAD and counting definition. A decrease is **REVALIDATION_REQUIRED**, not casually called performance decline.
- **Current rate** = unique new QA_ACCEPTED TaskIDs / measured hours between two consecutive verifications. At least two points.
- **Growth / decline of rate** = compare rates in two adjacent measured intervals. At least **three** signed snapshots, exact same HEAD and criterion methodology. A positive change shows "РОСТ СКОРОСТИ"; negative "ПАДЕНИЕ СКОРОСТИ"; equality "СКОРОСТЬ БЕЗ ИЗМЕНЕНИЙ".
- **Percent** = 100 × accepted / fixed_total. If no fixed denominator, show **Н/Д** and an unfilled evidence bar, not a fictional 0%.
- **ETA** remains locked under R29 until frozen prebuild remainder + independent accepted throughput exist. Trends by role alone are not a valid release date.
- **Manual roles** always appear before autos. Count is from the owner roster and authenticated scheduler export; currently 3 primary manual, 15 support auto and 10 historical/future, but these are observations, not hardwired permanent caps.
- UI is a **snapshot viewer** unless deployed behind the existing protected Vercel API with verified back-end data source. Do not claim a deployed or continuously live integration from successful Git code changes alone.

## Regression contract
`node coordination/r26/test-nox-executor-comparison-r30.cjs`
covers growth, decline, unchanged rate, no history, stale HEAD, false independent reviewer, zero additional QA and invalid decrease. Quick runtime evaluation of seven analogous checks was completed in the connected GitHub execution session; the stored CJS suite has not yet been run by Node on a checkout.

Control security: NO-LOSS, §33 56 rules, 729 source files, STOP, ACL, consent, SourceLock, T06 sole shared source writer and T02 sole shared journal writer unchanged. This visualization does not release Windows builds or sign QA.
