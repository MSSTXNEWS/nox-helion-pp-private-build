# NOX V16 · Mobile-responsive candidate and private remote gateway contract

**Status:** source-only integration candidate for E01/E06; no network server is launched by this PR. Existing Windows EXE remains authoritative and must continue working with no mobile connection. One local Ollama, one RAG/SQLite, one GPU training worker.

## UI integration (E01)
Attach `nox-responsive` to the trusted root element of the **existing** local NOX frontend. Mark current screen with `data-nox-page="home"` only on HOME. HOME contains exactly one central HELION and eight canonical CoreID objects in a single `nox-home-orbits` container:

- Nine direct child objects have `data-orbit-slot="HELION"` and slots `1` … `8` in canonical visual order.
- Keep approved original D02 textures/video/motion beneath this layout. This CSS only sets sizing/position, not the artistic assets.
- All search, weather, market, news and control panels belong on **secondary** screens, not HOME.
- Use `nox-view`, `nox-screen-toolbar`, `nox-function-search`, `nox-grid`, `nox-surface` and `nox-chat-shell` for responsive secondary screens; ensure focusable controls and touch targets.
- `prefers-reduced-motion` and `data-nox-mode="eco"` decrease visual work. No fake learning telemetry.

## Safe remote architecture (E06, E02, E07)
1. **Local-only** host API gateway listening at `127.0.0.1` (loopback). It is a thin adapter to existing host routes; do not expose raw Ollama :11434, local files, CUDA/QLoRA workers, Windows RPC or privileged WebView2 bridge.
2. Prefer **Tailscale Serve** to privately HTTPS-proxy that local gateway to the user's own phone (with Tailscale installed/logged in on both devices). Example, after an approved gateway is running at `127.0.0.1:8765`: `tailscale serve 8765`. No Tailscale Funnel or router port forwarding.
3. Gateway enforces authentication **even over a VPN**: user/device pairing, short session, scope-limited permissions, Origin/Host checks and CSRF protection; upload size/type limits, rate limits, WebSocket handshake and per-message checks, audit RunID, revoke/logout, NO secrets in page JS.
4. Approved public interface only: `GET /nox/v1/status`, `GET /nox/v1/routes`, `POST /nox/v1/chat`, `GET /nox/v1/events` (SSE or WebSocket), `POST /nox/v1/audio` (push-to-talk), `POST /nox/v1/queue/control` (scoped), `POST /nox/v1/session/revoke`. These are proposed contracts, **not existing endpoints**. Exact implementation belongs to E06/owners.
5. Real GPU training remains on PC. Remote dashboards show verified training metrics. START/PAUSE/RESUME/MERGE, premium calls, install/update, PC CONTROL and deletion require explicit permission and extra local owner confirmation for high-impact operations. Default remote policy: read-only or restricted safe chat.
6. Mobile microphone requires HTTPS and permission, with buffering, STOP and reconnection; do not secretly continue capture after network failure. Speech/translator/teacher reuse existing audio/LLM workers, no second engine.
7. Browser rendering of arbitrary public sites is in an isolated WebView2 profile without NOX privileged bridge.

## Release conditions
- E01 validates actual responsive screenshots at 320/360/390/430/768, 800×480, 1920×1080, 4K, landscape, keyboard, focus, reduced-motion.
- E02/E06/E07 verify session isolation, unauthorized access denial, websocket/CSRF/Origin, mic permission, STOP, offline/reconnect.
- E06 does **not** switch the EXE to a web release. Final Windows build only after five core blocks reach verified component 100%; E07 independently accepts same EXE SHA.
- Do not claim remote access functional from this stylesheet or README; this is solely a safe, deployable design candidate with no backend changes.

Tailscale Serve documentation: https://tailscale.com/docs/features/tailscale-serve
Web microphone secure origin: https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia
Microsoft Kestrel gateway security: https://learn.microsoft.com/aspnet/core/fundamentals/servers/kestrel/security-considerations
