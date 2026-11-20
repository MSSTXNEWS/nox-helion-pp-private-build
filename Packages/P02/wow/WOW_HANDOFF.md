# NOX V16 — P02 optional WOW handoff (not integrated)

Owner #2 delivers CSS **candidate only** at `Packages/P02/wow/p02-state-wow.css`.
Only #1 may touch approved UI markup/navigation; only #6 may bind shared host/events.v3.
This file must not be added directly to MAIN/HOME or injected into external websites.

## UX change without additional feature scope
1. Existing streaming status gains an orbital-style breathing dot and honest state colors.
2. Existing reply appears via a tiny 220 ms transform/opacity reveal.
3. Existing source citations, stored attachment ACK, STOP/retry/copy buttons receive
   a consistent NOX glass visual style **only if those functional elements already exist**.
4. Errors, cancellations, and timeouts are visually distinct; no decorative success
   when the actual Ollama response is incomplete.

Optional activation: load the CSS in the existing **trusted chat** WebView2 content,
then put `class="nox-p02-chat" data-nox-wow="on" data-nox-state="idle"` on
the existing chat root (NOT a new wrapper/host). The existing status element may
receive `class="nox-p02-state"`, reply `nox-p02-reply`, existing source link
`nox-p02-source`, attachment receipt `nox-p02-attachment`,
and functional action buttons `nox-p02-action`. Leave original handlers attached.

## Real event mappings (owned by #6)
- request initiated: `loading`
- actual received Ollama NDJSON partial chunks: `streaming`
- provider confirmed `done=true`: `done`
- caller STOP acknowledged: `stopped`
- enforced timeout: `timeout`
- other validated error: `error`
- no active operation: `idle`
- attachment `data-state="stored"` only after SHA-256/SQLite ACK
- remove `data-new="true"` on the reply after reveal, do not restart animation per token
- NEVER derive state from a timer alone or fabricate progress/percentages.

## Budget / safety
No third-party package, font, JS, WebGL, new process, network call, browser engine,
storage, telemetry producer, or extra visual panel. Approx. 4 KB CSS; adds zero
dependencies. Performance animation only uses `opacity` and `transform`.
Supports OS `prefers-reduced-motion`, focus-visible and state color + text.
Explicit feature-flag `data-nox-wow="on"` permits immediate rollback without touching core.
This is a proposed **micro-change in the existing +15% V16 WOW budget**; actual
1–2% person-effort requires measured baseline, not an invented estimate.

## Verification / completion gate
- #1 confirms compatibility with existing approved HOME/MENU/CORE design; do not
  change D02 HOME or add menu tiles.
- #6 reviews the actual trusted WebView2 markup and maps it to existing events.v3.
- Component/static and native Windows tests: state truthfulness (stop/error/done),
  reduced motion, 320/390 px, 800x480, high DPI, keyboard, contrast, ECO FPS.
- #7 separately checks same BuildID/EXE SHA. Source present is NOT integrated/accepted.

External implementation references:
- https://developer.mozilla.org/en-US/docs/Learn_web_development/Extensions/Performance/CSS
- https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/At-rules/@media/prefers-reduced-motion
- Existing official WebView2 controls and resource mapping; do not create a second browser.

Recommendation: do not add Lucide/other icon package unless existing approved resources
lack required glyphs. Existing icon assets are cheaper than a new icon bundle.
