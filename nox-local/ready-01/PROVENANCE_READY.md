# NOX READY Integration 01 — reused sources, no drawn imagery

- Base: local NOX V7_FIXED existing source, 47+ pre-existing dependencies; exact UI layout retained.
- Home scene: **sysscan/3d-blackhole-simulation** immutable commit `9cd793f34b972f6c8928b0d3127d94eff7613a61` / MIT. Original `index.html` and original Three.js r128 downloaded by installer, exact original bytes retained in `SOURCE.html`; only injected CSS to hide the original demo overlay while retaining the animated original shader/geometry.
- HUD: ready `cinema-hud.js/.css` from NOX Cinema HUD and Apache ECharts v5.6.0. Telemetry from Windows metrics; absent readings N/D.
- Chat: existing NOX streaming frontend patched STOP (`chat-patched.js`); backend `server_mega.py` connected to local Ollama.
- System push: `mega-ui.js`, `sw.js`, `nox_push.py`, `setup_vapid.py`. Actual Web Push requires VAPID/local key setup and subscribed browser; no false claims.
- Training: `nox_services.py` authenticates/read-only existing JSONL loss/checkpoints where configured. START/RESUME/ROLLBACK HOLD until original trainer verified.
- SQLite S03: read-only discovery only until original schema/API verified. No shadow database.
- Existing GPU/Ollama weights/SQLite remain untouched. Original versions stay intact.