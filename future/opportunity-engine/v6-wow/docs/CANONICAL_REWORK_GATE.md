# NOX HELION · OIE canonical integration gate · 2026-10-31

Scope: **OIE inside approved NOX**, not a new HOME/MENU/WORK. Supersedes the standalone V6 visual proposal as a release candidate; historical preview source remains for provenance only.

## Authority (checked against Drive)
- DESIGN MASTER V5: owner-approved HOME and SHA-locked original art; preserve immutable media.
- MENU+NAVIGATION V2: retain section IA, Function Lock and active route manifest.
- GOVERNANCE 144: especially rules 089–096 and 106–110; independent acceptance on same BuildID.

## Implementation
`engine/nox_canonical_panel.mjs` exports `mountOpportunityPanel(target, options)`.
Host creates an existing **approved** OIE route container with `data-nox-screen="opportunity-engine"`; this module never creates top-level navigation, asteroids, personas, or a competing Helion.
`options`: `apiBase` (read-only same-origin GET), `signal` (host cancel), `onBack`, `onEvent`, `requestJob(action, parameters, signal)` (trusted host IPC for privileged work).
The host **must** authorize and implement `requestJob` against existing `nox.oie.job.v1`; absent wiring returns `HOST_ACTION_NOT_CONNECTED`, never a false success. Do not inject tokens in markup or allow browser JS to grant consent.
No new release route or owner artwork is shipped in this future branch.

## Existing functionality retained
Catalog list, filter, 9-item pagination, inspector and escape, Ctrl+K focus, run 3 hypotheses, MB1 preview, back, errors, lifecycle/dispose. No publication, purchases, business launch, or fabricated sensor telemetry.

## Physical gate (still HOLD)
1. Integrator verifies approved routeId/parent section in authoritative menu manifest before mounting.
2. Verify original HOME/MENU/WORK image SHA-256 and PersonaIDs versus current Drive CANON.
3. Wire same-origin read-only API and authenticated host IPC; do not load independent V6 `studio_v6.html` into HOME.
4. Check R75 ten asteroid hit targets on actual original MENU image. CSS donor is unaccepted until pixel test.
5. Test full 193 navigation nodes separately from native handler claims, and cross-check 8 CoreIDs/5 PersonaIDs.
6. E07 installed Windows x64 test on **one** Setup SHA / EXE SHA / BuildID: STOP, history, real model, UI, ACL/consent/undo, DPI, keyboard, reduced-motion.
7. Only then update release status. Browser tests and GitHub file existence are not Windows E07 acceptance.

Status: SOURCE PATCH only; NO CLAIM of merged release, working Windows app or 100% fidelity.
