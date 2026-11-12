# NOX HELION HOME — Asymmetric Living Worlds V10 (2026-11-09)

This is a scoped candidate against the existing NOX HOME Web UI. **Not a production acceptance**. Main canonical branch and user's local NOX/weights/SQLite/checkpoints are untouched.

## Source of truth and retained contracts
- Vercel project: prj_VkqYRnaJscug0ZBiMIpi3yi8JEPb.
- Candidate: dpl_C5rubUBJWxtKz3HB19tom84neX1o (test deployment; no production alias).
- Current production rollback: dpl_7DchiHr2Er6AQyVGB1CYEiRE6eCh.
- Keep actual original D02 WebGL entry; 14 independent UI controls = six color palettes + five page skins + three quality modes, exactly three independent selection rings.
- BLACK MONOLITH SKY: rare animated stars, near-black center, no fog or planet wallpaper competing with core.
- NO CLOCK: never equal angular placement, no single radial distance. Live independent motion with changing approach/recession, bounded obstacle clearance and elastic pair impulses. Surface spin only, not whole buttons.
- Keep original navigation, nine routes, no fake telemetry, STOP, SAFE, NO-LOSS, Reduced Motion.

## Relevant QA performed
- V10 HTTP 200 for index, 10 critical JS/CSS modules and nine section pages.
- Browser at 1440x900: 14 visible bodies, zero body overlaps, angular gap CV 0.549, radial distance CV 0.285 (not a clock).
- Over two seconds the scene showed measured body-position and axial-angle changes; actual collision self-test passed, but **no real impact had yet been observed**. Do not claim a physically witnessed collision.
- Reduced Motion: 14/14 positions and spin remained static under emulation.
- 6/6 palettes, 5/5 skins, 3/3 graphics modes changed as expected; three rings remained selected.
- 320x640, 390x844, 800x480, 1024x768, 1440x900, 1920x1080 were inspected in earlier candidate with same responsive CSS and no control overlap.

## HOLD
- Cloud browser exposes no WebGL context: D02 hardware GPU acceptance NOT_RUN, fallback Canvas2D is visible and clearly labeled in runtime state; cannot treat fallback as original D02 visual PASS.
- Physics impulse model is implemented and isolated self-test passed; owner-quality visual/physics acceptance and real pair impact observation remain OPEN.
- Public Vercel preview has no local Windows API, so CPU/GPU/RAM values are unknown, never simulated.
- Do not promote to production or delete previous deployments before independent WebGL-enabled browser QA and owner visual comparison.

Implementation assets are preserved as the five source files in this directory; the rest of the original deployment is not duplicated here. Keep this folder isolated from installer/Windows source until actual verification.
