# NOX HELION · CINEMATIC HOME · CONTRACT V16
10 November 2026 · source-based candidate, not production acceptance

## Inviolable design canon

1. **D02 is the only primary visual nucleus**: black obsidian / liquid metal eclipse, living gold corona, no decorative concentric rings, generic moon or flat 2D replacement.
2. **Cinematic hierarchy**: D02 dominates; "РЕЗОНАНС" is one deliberate metallic focal call-to-action **below** the corona and never occludes the disk; orbit controls remain visually secondary.
3. **14 original interactive objects preserved**: six color planets, five world/skin giants, three graphic-mode asteroid controls. Do not replace real working controls by a mock image; no duplicate engines.
4. **Three dimensions, not equal icons**: distinctly sized worlds, plausible materials (PBR textures, actual normals, lighting), individual axial rotation; selected state only is emphasized, exactly three active selection rings overall.
5. **Natural choreography**: independent asymmetric movement, no clock-face arrangement, gentle radial approach/retreat, collision avoidance and occasional elastic contact without jitter/teleports. Control movement remains slow and intentional.
6. **Lighting**: dark/black backdrop with sparse believable stars, visually coordinated scene lighting and world highlights. Four cinematic light scenes and at least five harmonious interface color themes, including black-gold. No brown haze/flat neon/cartoon gradients.
7. **Interface composition**: one compact top row of navigational icons, transparent industrial HUD panes, real CPU/GPU/VRAM metrics or unavailable indicator (no invented values), nine functional sections, bottom command buttons balanced with the stage.
8. **Responsiveness**: 320/390/800×480/1024/1440/1920/4K without collisions. `prefers-reduced-motion` must freeze decorative movement and preserve interaction. No CSS scale() on entire DOM stage.
9. **Technical**: preserve WebGL master, fallback only on actual failure, event-driven state updates, single renderer per responsibility. Preserve chat, SQLite, voice, S03, models, STOP, SAFE70 and all existing functionality. No loss / rollback.
10. **Acceptance**: screenshot + runtime metrics on actual GPU, no broken resources, 14/14 present, active switches work, no collisions on 6+ viewport sizes, no fake PASS.

## Screenshot 2026-11-09 problem list
The owner's screenshot of V15 showed a nucleus resembling a shaded moon, multiple detached oversized/similar worlds, a thin large contour around the sun, UI overlays competing with the stage, and a "РЕЗОНАНС" title nearly touching corona. Earlier versions had shown missing core entirely from 404 assets, fixed in V15. This screenshot is **not** visual acceptance.

## V16 delta actually deployed
- Master D02 retained. Core visual contrast darkened; fallback respects actual WebGL heartbeat and lost context.
- Large wave/ring invisible at rest; appears subdued only when Resonance is hovered/focused.
- Resonance Y tied to core + diameter + viewport safe-area instead of fixed percent.
- PBR worlds use heterogeneous per-index scales rather than the same all-world zoom, Reduced Motion stops axial rotation.
- Desktop HUD visual weight lowered; bottom navigation and the typography brought to a single cinematic palette.
- All existing pages and controls preserved; no model/training/native runtime mutation.

## Evidence / statuses
- Preview: https://nox-helion-real-home-preview-bxr06iflm-msttx.vercel.app/
- Vercel deployment `dpl_9h3XFeKe68TdS7edeRfAz6yQQRPK` READY, preview only.
- Source assets tested HTTP 200: index, D02 master, recovery CSS+JS, Resonance JS+CSS, PBR worlds, orbit JS, chat route.
- **HOLD**: physical browser screenshot / actual GPU rendering and interaction, real long-motion collision test, texture loads, 6 palettes + 5 skins + 3 modes cross-device, local runtime connections. No production promotion.
- Previous candidate: `dpl_ChLDzseHXhGkUoFenSyEs516Yzb7` remains rollback reference.
