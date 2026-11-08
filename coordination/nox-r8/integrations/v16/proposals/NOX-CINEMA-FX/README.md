# NOX HELION V16 · Living D02 Cinema FX

**Status:** new working source components; not integrated into the released Windows EXE.

The cinematic renderer decorates nine **existing** approved orb elements: HELION and exactly eight CoreID. It adds liquid lava, drifting obsidian crust, glowing filaments, a rotating luminous rim, energy corona and rare lava/black-obsidian particles that travel outward and return to the surface.

There is one animation scheduler for all nine orbs. MAX permits 24 particles, BALANCED 12, ECO 3, Reduced Motion none. Hidden surfaces pause and release particles. Original elements, handlers, keyboard focus, images and identities are preserved. Buttons float only when the approved owner sets the opt-in `data-nox-float="true"` flag. Panels are translucent and readable. No shaders, GPU framework, new LLM, model loader, second database or external service.

**Source:** `nox-cinema.mjs`, `nox-cinema.css`.
**Events:** `nox-cinema-events.mjs` maps existing installer events.v3 to decorative states; GPU sensor events never imply training.
**Demo:** `preview.html` is a self-contained browser visual QA fixture with temporary backgrounds, NOT replacement D02 artwork.
**Tests:** `nox-cinema.test.mjs` and `nox-cinema-events.test.mjs`, Windows GitHub Actions.

Integration owner #1 must supply original D02 DOM nodes and canonical eight IDs to `installNoxCinemaFX({root,orbs,controls,panels,profile})`. Events owner #5 supplies the existing trusted native event subscriber to `attachCinemaToNativeEvents(scene,subscribeNative)`. Integrator #6 must reconcile approved R11 assets, micro-WOW PR #14/#15, SourceLock and per-file SHA before admitting this additive package. No duplicate HOME, event writer or training runtime.

The approved original 10 realism + 10 WOW + 10 cinema criteria remain the acceptance target, with both ECO and Reduced Motion required. Component tests do not prove visual acceptance on the user's Windows hardware or final EXE same-SHA E07 acceptance. No production assets or host were modified by this PR.
