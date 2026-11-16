# NOX WEB29 3D · MOTION100 non-blocking overlay · 2026-11-16

**Scope:** SOURCE_TESTED, **NOT NATIVE_DEPLOYED**. This is an additive overlay for the original WEB29 main (D02, 14 worlds), not another UI, backend, dispatcher, S03, model or chat. No production overwrite.

## Pinned original inputs

- WEB29 main [Drive](https://drive.google.com/file/d/1R9RXZN0FJUJJUq8sJ_n1k3Rh1YcY3R5N/view), 84,223,045 bytes, SHA256 `611a3cf21b37ff79dbaece57f4c65c5efb70e0c302b5fc4b4f64dbfa060f15bc`, ZIP CRC pass, 1,212 entries.
- Original MOTION100 [Drive](https://drive.google.com/file/d/1JYQ7D6b1RXzG8W9pEz9NXXslHdRgcFzK/view), SHA256 `95fa245fa755684a53bed04de043d6e876997acdcdb962175f92b7587c3ef1a6`, 100 original verified SVGs, library license preserved.
- Safe overlay artifact `NOX_WEB29_3D_MOTION100_SAFE_OVERLAY_20261116.zip`, 161,332 bytes, SHA256 `18cb2692cf2c2be454d38778f20fced899f92d8608919446e17f43104cd10e0b`. Saved to the user's private ChatGPT Library under `/NOX_WEB29_3D_MOTION100_SAFE_OVERLAY_20261116.zip`. ZIP contains pinned `MANIFEST.json`, preimage rollback, three patched original HTML pages, and 110 additive assets; it is not installed on OneHost.
- The repo carries the two critical independently reviewed source changes: `site/nox-motion-idle-loader.js` and `site/nox-cinematic-accessibility-3d.css`, source-byte-aligned with the overlay artifact.

## Changes with NO-LOSS

1. `site/chat.html`: replace the original decorative Motion.js defer with the non-blocking `nox-motion-idle-loader.js`; it loads the existing vendor Motion.js only after page load/idle, while chat and voice are quiet. STOP, ECO, OS reduced motion and page visibility inhibit loading. The generator and original stream are never gated on decorative animation. Do not remove the original `vendor/fx/motion.js`.
2. `site/nox-cinematic-accessibility-3d.css`: fixes an existing `!important` cascade regression where a stronger live-mode animation rule defeated reduced motion; selects only decorative metal breathing, preserving main D02 shader and scene.
3. `site/pc/resonance.html`: add owner-only, idle-gated MOTION100 lazy loader for existing authenticated native waiting-state events (no fake progress).
4. `site/cinema.html`: add graphical navigation to the local MOTION100 gallery; preserve original CINEMA playback/controls. Existing voice RU/ES and MAESTRO files remain; no separate STUDIO module exists at `site/pc/pages/studio/index.html`, so STUDIO is HOLD, not a fake PASS.
5. Preserve every original WEB29 path. Original protected hashes: `site/nox-engines/nox-world-shaders.mjs=124a5d341059eb1070adcf58640657aa471ea4888e4409101503ecaa9337f952`, `site/nox-orbit-14.js=3aced1774354b6212b665ef40514e78fb7660a3319fd346c4b12bbf277a39d38`. Roll back original three HTML files via exact preimages in ZIP.

## Verified testing / limitations

- Original MOTION100 suite: **16/16 PASS** (offline Chromium DOM + source checks).
- New JS idle loader: **10/10 PASS** via Node; chat/voice mutex, STOP, ECO/reduced motion and page lifecycle.
- New protected-page/CSS/mobile tests: **10/10 PASS** (Chromium computed animation and widths **320, 390, 800, 1024, 1440, 1920**). **36/36 total SOURCE PASS**.
- Network/browser navigation to the original server was **ERR_BLOCKED_BY_ADMINISTRATOR**. Actual original OneHost #60509551 writer lease, independent S03/optimizer offsite restore, and owner-authenticated browser stream/STOP/voice/CINEMA E2E **not demonstrated**; production install remains **HOLD**.
- Do not infer actual training, live usage, installed assets, GPU progress, or production quality from ZIP CRC or offline DOM.

**Next authorized action:** At the precise serving target SHA, use only the existing owner-controlled OneHost deploy path to prove current preimage and independent restorable backup, then stage this additive overlay with rollback; run authenticated browser `/nox-web-v29/` stream, STOP, S03, voice, CINEMA and Reduced Motion E2E before promotion. No destructive cleanup.

## Incremental 3D runtime-gate repair · 2026-11-16 · NOX_WEB_WEIGHTS_V06

This source revision fixes a real accessibility and performance race found against the pinned original. The old CSS did not beat the original WEB29 live `!important` shorthand for all themes; real local Chromium computed-style verification confirmed the failure before repair. The stronger reduced-motion rule now covers live/still/contrast/default without touching D02 WebGL shaders, orbit data or model endpoints. Browser fixture check: **48/48 cases** across 320/390/800/1024/1440/1920 px, two themes, two modes, two OS motion states. This is **LOCAL CHROMIUM**, not authenticated OneHost acceptance.

The optional Motion.js loader now respects the original `nox-runtime-observed`/media/typing/training activity, fails closed while a native owner runtime is unknown or busy, and does not force `requestIdleCallback` to run after four seconds of sustained token rendering. Existing original chat, voice, STOP, vendor libraries and themes remain. Deterministic Node test assertions are under `tests/test_motion_idle_loader.mjs` and the original WEB29 ZIP/shader/orbit SHA was checked unchanged.

**Artifact divergence:** The older 161332-byte private overlay ZIP is a previous source stage and was not silently overwritten by this incremental Git commit. The repaired JS/CSS and tests here are the current source candidate; rebuild/stage only via existing exact-preimage authorised owner deploy with rollback. Owner authenticated streaming/S03/STOP/browser latency, production rendering and real GPU/weight training remain **HOLD**, not PASS.
