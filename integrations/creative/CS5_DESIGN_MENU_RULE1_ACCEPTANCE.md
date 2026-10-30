# NOX Creative Studio · Designer and MENU acceptance · PR #225

Source authority: Google Drive `NOX HELION · CREATIVE STUDIO V5`, `DESIGNER TASK LIST · PERSONAS + MENU NAV MOTION` (22.10.2026), `CONTROL CENTER V1.0` (30.10.2026), approved HOME/MENU/WORK SHA manifest. Source-scoped audit on PR225 HEAD only; **not an independent native Windows art signoff**.

## Exact source-lock and menu facts
- The root NOX HOME, MENU, WORK, all approved PNG/passport sources, 8 technical CoreID and the owner-approved visual composition are **not edited in this PR**. Never substitute V18/V19 alternative MENU or regenerate a face. EV is `IDENTITY_CONFLICT_HOLD`.
- `integrations/creative/web/entry.js` must remain byte-identical to original PR162 blob `34032ba9cb41bc3d71afcdbe57f690e15fd76755`; strict Node regression checks this.
- Inside existing Creative `studio.html`, the script order is `studio.js` → `five_blocks.js` → `persona-media.js`. The addon only creates an internal `five` screen/tab; it never changes root MENU tiles/RouteIDs. Real artwork remains under the original owner.
- Existing `rpc`, `task`, `navigate`, `stop`, and provider catalog are reused. CS5 invokes original `storyboard`, `create_text`, `project_files`; ModelCenter stays P03. Browser messages are not independent OS/ACL authorization.
- Existing Studio touch target raised from 41 to 44 CSS pixels; no new palette, typography, hero, orbit, faces or root-menu visuals were introduced.
- The late current MENU ten-world visual has **no validated 10-world ↔ 8-legacy-route mapping on this PR**. Route mapping and visual replacement belong exclusively to the actual main-menu owner; absence of this evidence is HOLD, not a mandate to make a second menu.
- The five local project records are explicitly `SAVED_LOCAL_NOT_E11`, NOT a migration of E11/S26. End-to-end E11 admission is HOLD.

## Designer Rule 1 · source status, NOT an invented 30/30 PASS
In this matrix, `UNCHANGED` means PR #225 has not modified owner graphics, not that a criterion has passed independent art QA. `LOCAL` means testable source-level UI behavior. `HOLD` means no qualifying native/device/video evidence was produced.

| Criterion | Current source status | Evidence/gap |
|---|---|---|
| A01 eight independent Core orbits | UNCHANGED / HOLD | Original owner visual; 30–60s independent frame proof missing |
| A02 viscous solar surface | UNCHANGED / HOLD | No new renderer; native motion proof missing |
| A03 asynchronous coronas | UNCHANGED / HOLD | No new animated assets accepted |
| A04 spatial smoke and ash | UNCHANGED / HOLD | Real scene footage/FPS absent |
| A05 true event-driven motion | HOLD | No verified native event trace |
| A06 Persona physiology | N/A for Creative subpage; system HOLD | No approved five-persona videos |
| A07 simulated emotions | N/A for Creative subpage | No persona media injected |
| A08 PCM-synchronized lip-sync | N/A for Creative subpage; system HOLD | No untrusted mouth animation added |
| A09 reversible cinematic HOME→MENU→Creative | UNCHANGED / HOLD | Existing root navigation preserved; native trace absent |
| A10 truthful STOP/connection | LOCAL / HOLD | Uses original STOP; needs same-EXE proof |
| R01 canonical FaceID/BodyID lock | UNCHANGED | Original assets untouched; EV conflict remains |
| R02 permitted PBR microtextures | UNCHANGED / HOLD | No new material generated |
| R03 eyes/microsaccades | N/A on Creative panel | No synthesized face |
| R04 irregular breath/blinks | N/A on Creative panel | No synthesized face |
| R05 anatomical articulation | N/A on Creative panel | No synthesized face |
| R06 cinema optics/DOF | UNCHANGED / HOLD | No native filmic shot accepted |
| R07 coherent scene lighting | UNCHANGED / HOLD | New panel inherits original Studio CSS |
| R08 obsidian/graphite/titanium | UNCHANGED / HOLD | Owner materials not replaced |
| R09 atmospheric occlusion | UNCHANGED / HOLD | No 3D render evidence |
| R10 independent anti-uncanny QA | HOLD | Requires qualified visual reviewer on approved assets |
| U01 panel depth/bevel/contact shadow | UNCHANGED / HOLD | Existing panel CSS preserved |
| U02 metallic edge/specular typography | UNCHANGED / HOLD | Existing tokens preserved |
| U03 readable Cyrillic/hierarchy | LOCAL | Real Russian controls and static DOM test; device QA pending |
| U04 hover/focus/disabled/busy/STOP | PARTIAL | Reuses existing controls; browser + native acceptance pending |
| U05 8 CoreIDs and root MenuID/RouteID | UNCHANGED / HOLD | Original menu entry blob pinned; runtime mapping not attested |
| U06 no fictional LIVE/success | LOCAL | LOCAL_NOT_E11 / HOLD statuses; external receipts unverified |
| U07 working buttons/route parity | LOCAL / HOLD | Node routing QA added; same-EXE native proof missing |
| U08 factual telemetry/time/source | HOLD | No fabricated metrics added, but native dashboard not covered |
| U09 shared materials, icons and lighting | UNCHANGED | Addon uses existing `panel`, `action`, `formrow` classes |
| U10 44px touch, keyboard, ECO/reduced motion/device perf | PARTIAL | 44px source, inherited style; 320/390/G-FLIP/4K FPS and Windows E07 missing |

## Final designer/navigation source fixes (same add-on)
- The existing NOX Creative parent `entry.js` is kept byte-identical (Git blob `34032ba9cb41bc3d71afcdbe57f690e15fd76755`); five-block script import is inside original Studio HTML.
- The **five segments are simultaneously visible** as five existing-class `.action` controls (B01–B05); each is keyboard-accessible, uses `aria-pressed`, updates the original select/kind, and does not create a ninth HOME/MENU item.
- The studio and five-block panel now sync the **same ProjectID**, both when entering CS5 and before native action routing. No second project name is invented on entry.
- Designer breadcrumb `NOX / ТВОРЧЕСТВО / 5 блоков` and BACK use the existing `navigate('create')` route, not a new router. Original CSS/material tokens are unchanged, 44px target remains.
- The original `storyboard`, `create_text`, `project_files`, model catalog and native STOP handlers remain the only execution owners; B05 external publishing and real revenue remain blocked without verified provider receipts.
- Source verification is not Windows art approval. The late 10-world current MENU ↔ 8 legacy groups mapping still requires exact owner/source review on one frozen HEAD.

## On-demand / history / real BACK QA addendum
- The Studio's original `studio.js` continues binding root Creative nav and provider actions. The CS5 addon **does not call any native RPC at page load**. It explicitly queries the original Worker only on first user click into CS5 or the manual status/retry button. No background scheduling or startup workload was added.
- `cs5_list` now accepts a validated stable integer `before` cursor and returns prior groups of 20 through the bounded original-worker IPC; all 45 test-version examples are reachable in added Python tests. Invalid booleans, negative or out-of-range cursors are rejected. These **new Python cases have not been executed by Windows CI**.
- Version records render as existing `model` cards with timestamp, `HYPOTHESIS` / `LOCAL_RECORD_ONLY` / `REPORTED_UNVERIFIED`, source and exact SHA. The UI validates stored links with the platform URL parser and blocks non-HTTP protocols/credential-bearing URLs. No HTML from records is interpolated.
- BACK remembers the last real `create/models/jobs/theater/immersive/about` Studio section, rather than always resetting to Create. No root MENU/WORK element changed.
- V8 source-level DOM fixture passed on the latest JS for lazy Worker, retry, real BACK, three history pages, provenance cards, original Storyboard/Music/ProjectFiles and STOP. The Node test source was updated, **not run in a real browser/Windows CI**.
- Required visual 10+10+10 art QA remains NOT_ACCEPTED; latest 10-world current visual → existing historical routes is not remapped by this PR.

## Tests and release gates
Run `python -m unittest discover -s integrations/creative/tests -p 'test_five_blocks*.py' -v`; `node --test integrations/creative/tests/five_blocks_ui.test.mjs`; `node --check integrations/creative/web/five_blocks.js`. Then test original `studio.js` and `entry.js`, visual screenshots 320/390/800×480/FullHD/4K, STOP/permissions, original routes, independent 10+10+10 and same-EXE E07. Never mark 100% from static source or browser mock.

**Source acceptance:** menu/source NO-LOSS candidate only. **Art 10+10+10:** NOT ACCEPTED. **E11/S26:** NOT ADMITTED. **Windows E07:** NOT RUN. **MAIN:** UNCHANGED.
