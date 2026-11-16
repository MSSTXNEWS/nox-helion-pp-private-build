# NOX HELION WEB WOW MAX V12 · FIVE LIVING HEADERS · ONE HOME

**Status:** SOURCE INTEGRATED / ISOLATED CHROMIUM QA PASS / LIVE ONEHOST HOLD. `instructions_version 0.0.6`

## Visual design contract

One original living HOME/D02 world on all pages, transparent glass over the scene, one always-visible horizontal graphical top navigation with 13 native routes. Different artistic materials on **this same menu** for five fixed worlds: HELION (molten obsidian/eclipsed gold), CHRONOS (mechanical brass), SOMNIUM (prismatic organic glass), FORGE (cut titanium furnace), SYNAPSE (bioluminescent neural cells). Six palettes stay independent; existing button-material settings affect the shared header.

`site/nox-theme-header-v12.css` is the **new additive runtime CSS**, connected AFTER `nox-shared-chrome-v10.css` on all 43 active pages in the full archive. It follows live `html[data-nox-world]`, `--nox-world-rgb`, `html[data-nox-ui-button]`, quality mode and Reduced Motion. All original handlers, shaders, STOP, S03, voice and CINEMA are unchanged.

## Artifact receipts

- [Full unified V12 ZIP on Google Drive](https://drive.google.com/file/d/1VddHAsN1SrzbFyzs1hDdswx6JizcPpRb/view) — **84,513,325 bytes**, **1,265 members**, SHA-256 `5b1508b66e86f195ac396a1f7c4a3d7ada4dfbfbf6806b570784eb22a9eb331c`, ZIP CRC PASS. **1,261 / 1,261** V11 paths preserved.
- [Master specification V12](https://drive.google.com/file/d/1a4TtRkm_IgAQ8yE-jQRDSoVZOPnGKZhy/view)
- [Receipt JSON](https://drive.google.com/file/d/1fIPnbDdQdC8P4Nw7uU94U4st9AmF76WN/view)
- [Chromium five-theme comparison](https://drive.google.com/file/d/1YwKSPWvOx5CYNaxmFGW5f4iCLa95fr-q/view)

## Verified local behavior

- Distinct theme CSS geometry in Chromium: **five of five**; original nav **13 routes**, no dropdown, no extra Canvas/WebGL.
- Dynamic in-page switch: existing `NOX_CINEMATIC_WORLDS.setWorld('forge')` → `setWorld('somnium')` → `setPalette('glacier')` updates computed clip-path, radii and RGB, with **zero JS errors**.
- Responsive without horizontal overflow at **320, 390, 800, 1024 and 1920px** across all five themes. Reduced Motion disables decorative animation; ECO reduces work.
- The original five protected source files' SHA are byte-identical with V11; 43 active pages link to the additive CSS and all linked local files exist; 83 root JS/MJS syntax checks PASS.

## Deployment HOLD

This branch and source bundle do NOT prove the actual OneHost renderer, streaming chat, STOP, S03, native workers or GPU telemetry. Do not overwrite production without exact served SHA and authorized native lease, verified offsite backup and authenticated E2E. Retain previous archives until full rollback is demonstrated. No new second backend/renderer.
