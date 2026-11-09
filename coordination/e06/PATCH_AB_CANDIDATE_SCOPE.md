# PATCH-A / PATCH-B — CANDIDATE SCOPE (NOT SEALED)

Status: **CANDIDATE_NOT_SEALED**
Date: 2026-11-03
Branch: candidate/patch-ab-scope-20261103
Base: integration/nox-v16-unified-candidate-20261028-r01 (01de5948)

This file records scope only. It is **not** a CAS seal, not an I0 merge, and not release acceptance.

## PATCH-A (FirstBoot + P03 + S03)
- FirstBoot: autosearch, rights, consent, stop_epoch match with A1OwnerPorts
- P03: ModelCenter native routes, retry re-binds license/rights/revision/bytes
- S03: single SQLite knowledge import, native find/write, readback, STOP/ACL

Status: code present in tree; **sealed DONE + native ACK = NOT_RUN**

## PATCH-B (MENU10 / Browser / NAVIDLE)
- MENU10: menu_v2_full_catalog.json bundled (see PP_MENU_CATALOG_BUNDLE.patch)
- Browser / NAVIDLE: B1/B2 recovery; last known result NAV_OK → BrowserProcessExited

Status: partial; **sealed + native ACK = NOT_RUN**

## What is required before SEALED
1. Formal CAS acceptance (not a file commit)
2. I0 merge into PR162 with pin cascade
3. Native ACK on the same Windows EXE SHA
4. Independent E07

## Explicit non-claims
- release_accepted = false
- independent_e07 = NOT_RUN
- sealed = false
