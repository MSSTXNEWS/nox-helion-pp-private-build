# NOX HELION HOME · V15 candidate repair — 2026-11-09

Status: **QA / HOLD** (not production-accepted). Do not claim complete UI/GPU acceptance.

## Deployed candidate
- Vercel project: `prj_VkqYRnaJscug0ZBiMIpi3yi8JEPb`
- Deployment: `dpl_ChLDzseHXhGkUoFenSyEs516Yzb7`
- Preview: https://nox-helion-real-home-preview-d7hrdljj6-msttx.vercel.app/
- Prior tested recovery: `dpl_5Q4GkviqHGmxaZgGc5s9zU41EP14`
- No production alias changed.

## Scope of preserved source
Four actual files from that Vercel preview:
1. `nox-home-recovery.js`: fallback heartbeat + WebGL loss handling, Reduced Motion state refresh, four subdued scene backgrounds.
2. `nox-resonance-cinema-v13.css`: positioning follows the computed `--nox-resonance-label-top`.
3. `nox-orbit-original.js`: 14 original controllers, bounded motion, enlarged Saturn-ring collision reservation.
4. `nox-engines/physical-worlds-v7.mjs`: physical world renderer with adjusted scale.

The full deployed static website (186 source inputs) is **not** recreated by these four files alone. Source input for the remaining unchanged files came from Vercel deployment `dpl_5Q4GkviqHGmxaZgGc5s9zU41EP14`; five previously omitted core/recovery resources were explicitly re-inlined. This is an incremental patch checkpoint, not a merged complete repository or native Windows runtime.

## Verification
- Vercel READY.
- GET `/`, `/nox-home.mjs`, `/nox-home-recovery.css`, `/nox-home-recovery.js`, `/nox-home-flow.js`, `/nox-home-flow.css`, `/nox-resonance-cinema-v13.css`, `/nox-orbit-original.js`, and `/nox-engines/physical-worlds-v7.mjs`: HTTP 200.
- Returned fallback JS contains heartbeat check; returned resonance CSS contains variable-driven position.
- True WebGL GPU and rendered screenshot: **not tested** due Vercel preview access constraints in automated browser.
- Production unchanged, local model/training/SQLite/checkpoints untouched.

## Known acceptance blockers
- Physical D02 GPU scene and 14-world long-motion visual acceptance.
- Real 3D planet materials and axial rotation observed on owner's hardware.
- Responsive screenshots 320/390/800/1024/1440/1920/4K.
- Functional validation of routes, tabs, five skins, six color palettes, three modes, reduced motion, real telemetry, and native operations.
- Whole-platform NOX V9/R8/V16 GitHub/GitLab/Drive integration and deletion not established.
