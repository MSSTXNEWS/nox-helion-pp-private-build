# NOX HOME — cinematic acceptance rules · 2026-11-09

**Canonical principle:** NOX D02 is the protagonist of a single coherent cinematic environment, not one of fourteen unrelated planetoids.

1. **Eclipse / D02:** deep-black obsidian/liquid-metal microstructure, realistic thermal corona, dark readable silhouette, restrained gold edge radiation; no grey moon-like frontlit sphere. Preserve the existing WebGL renderer, live telemetry, STOP, and reduced-motion fallback.
2. **Visual hierarchy:** D02 dominates. Space and stars recede. Controls remain selectable, but never cover the core or its corona. No large visible orbital lines or uniform clock arrangement.
3. **Materials and lighting:** physically based planets, shared lighting state, sensible roughness/metalness, directional and rim lights; single consistent exposure, no cartoon color gradients when WebGL is available.
4. **14 controls:** six color worlds, five theme gas worlds, three graphics asteroids; independent slow motion, smooth proximity/retreat and physical near-contact responses, axial self-rotation, safe-area collision checks including labels, rings, monitored panels and nav.
5. **Resonance:** centered elegant metallic typographic treatment under (not across) the disk; actual `chat.html` navigation. Its vertical coordinate follows computed core position. Resonance effects are local corona glints, never huge 2D wireframe ellipses.
6. **Scenic light:** the whole environment responds to a theme; black-gold plus other existing palettes. Deep near-black backgrounds with subdued atmospheric variations, no brown wall/wash.
7. **Panels:** industrial, translucent, cinematic; true CPU/GPU/RAM/VRAM data or explicit unknown dashes, no fake sensor numbers or gauges.
8. **Navigation:** compact single-line top nav, existing 9 functional routes below, no duplicate Home or extra backend.
9. **Quality & accessibility:** check 320/390/800/1024/1440/1920/4K and Reduced Motion; test the actual GPU WebGL path, 3D shaders/materials, long-duration collisions, keyboard focus, theme switching and links.
10. **Release:** only patch existing NOX source. One patch, one test, one verified save. Preview READY/HTTP 200 is not a GPU visual PASS. No production promotion until evidence and owner acceptance.

## Observed failures in the owner's screenshot
2026-11-09 screenshot of V15 preview: frontlit grey core, oversize wavy dark outline around sun, relatively uniform floating planets and huge bottom navigation; strong separation between UI panels and space. The prior V14 snapshot also had missing main WebGL module due nested source paths. Both are actionable code/integration defects.

## V16 changes, tested scope
Preview: https://nox-helion-real-home-preview-3ddbr66ax-msttx.vercel.app/
Deployment: `dpl_6pkmkZYsZcpwEiUZSUVM1aAhisRd` (READY, preview only).

- `eclipse-materials.mjs`: darken solid mineral surface after metallic PBR reflections but before molten fracture emission.
- `nox-resonance-cinema-v13.js`: replace broad 2D concentric wireframe with three dim local corona arcs and tiny ash points; title anchored from measured core.
- `nox-resonance-cinema-v13.css`: unify dark background, cold metal text, panel material, navigation lighting, reduce competing overlays.
- Original 14-control motion/PBR modules preserved from V15 without losing functions.
- Modified outputs fetched from protected preview with HTTP 200 and string integrity checks; modified classic JS parses successfully.
- **HOLD**: true browser screenshot/GPU confirmation, natural encounters, full app integration; production untouched.
