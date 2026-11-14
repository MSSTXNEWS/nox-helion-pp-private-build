# NOX HELION V16 — Integration Pack 01 / 50

**SOURCE CANDIDATE, not 50 installed integrations.** Goal: eliminate 50 repeated UI/route implementations while preserving every approved function and WOW effect. One native Windows EXE, one WebView2, one native host, one Ollama/chat/SQLite/RAG/GPU pipeline, one events.v3, one NSIS installer. All original D02 art assets, five approved personas and the 8 CoreID unchanged. Never draw this catalogue on HOME.

## Physically delivered in this pack
- `catalog.json` — exactly **50 distinct feature/task IDs** grouped 10 each into Chat/Core, ModelCenter, RAG/GPU, Voice/Media, NOX SPACE/System. Each has a title, owner, risk, precise action ID and optional real settings schema.
- `registry.mjs` — validates all 50 entries, detects duplicate IDs, enforces immutable options for actual installed voices/models/cores, creates normalized host requests, supports search/categories, fails closed if capability or consent unavailable.
- `panel.mjs` — one searchable NOX screen; each of the 50 cards opens its own settings, real host-provided capability state, and (only if verified and permitted) sends one structured request to the local host. No action is sent from a disabled route. Ctrl+K is accessible outside HOME.
- `panel.css` — transparent graphite/obsidian materials, light sweeps, readable glowing card edges, 44px touch targets, mobile 320–4K, ECO and Reduced Motion. No new 3D library/GPU engine.
- `smoke.test.mjs` — 50 per-route deterministic native-contract checks plus schema/search/security tests; validates data only, not Ollama/SIP/Windows end-to-end.
- Windows Node CI workflow, requiring no npm packages.

## Native bridge admission (required, not yet implemented)
The integrator #6 MUST bind each proposed `routeId` to the existing canonical NOX RouteID/ActionID in its exact approved source tree, or explicitly report HOLD. The JS module MUST NOT rewrite the actual host routing table or grant privileges:

```js
// Simplified shape: use an already-loaded catalog object and trusted NOX bridge.
const view = mountPack(secondaryRoot, { catalog, bridge: trustedHost });
view.setCapabilities({
  "helion.chat": {state:"VERIFIED",enabled:true,sourceId:"host-chat-receipt"},
  "models.pull": {state:"CONNECTED",enabled:true,sourceId:"host-model-pull"},
  "system.update": {state:"HOLD",enabled:false}
});
view.setHostChoices({
  "host.models.installed": [{id:"qwen3:4b",label:"Qwen 3 4B",installed:true}]
});
```

The host must **independently verify** current session identity, local network origin, exact route allowlist, consent, licence, dataset rights, device permission, user data ACL and command arguments. `risk=dangerous` can be enabled in the UI only if the host advertises `nativeConsent:true`, and STILL requires native consent at execution time. No secrets in JS, no direct Windows/Disk/SIP/GPU calls, no public Ollama or Tailscale Funnel exposure.

## Source-based handoff by owner
- **#1:** D02/MENU/WORK navigation, transparent button styles, browser/media/installer routes. Keep HOME just central black-liquid HELION and 8 separate CoreID.
- **#2:** chat, model selection, SQLite/attachments, HELION/Core/Persona, RU↔ES and MAESTRO/SIP provider only after authorization.
- **#3:** original P03 C37/C40 and PR #17, not a second downloader; 15–20 actual pinned weights and licenses required for one-click download.
- **#4:** PR #7/#12 RAG/LoRA/QLoRA and GPU safety; actual training must happen with licensed dataset and real GPU. Images.Generate optional if an installed local ComfyUI/Diffusers backend exists, never blocks core training.
- **#5:** existing events.v3 and PR #9 weather/news/FX/BTC/Brent, honest telemetry and app-side Google Drive receipts.
- **#6:** one SourceLock/current full source tree, canonical route mapping, serial merges and host. No final EXE build until 1–5 component-verified 100%.
- **#7:** independent Windows QA of same EXE build/hash, including permission bypasses, STOP, RAG and real GPU training.

## What is NOT complete
None of the 50 host action handlers are assumed installed or verified. Without native host capabilities they show **HOLD / Не подключено**; the clickable card opens its description/settings only. No automatic external downloads, login, billing, phone calls, PC CONTROL, data deletion, training or installs are triggered by this source candidate. A green CI is a **component-contract pass**, not an integrated feature or release acceptance.

## No-loss and acceleration rules
- Canonical spec: https://docs.google.com/document/d/11EM0qW3PJN0WqV8Euc1A2X4c0UukHiVq_0WfaLYVYpc/edit (V16 sections 1–27; 56 inherited V15 rules).
- Preservation registry: https://github.com/MSSTXNEWS/nox-helion-pp-private-build/pull/19 — all original source archives/asset SHA/Persona/WO​W/provenance must remain; append-only owner handoff.
- This pack adds only proposal paths and a focused CI file. No production host/MainWindow, installed models, GPU files or original graphics changed.
- The remaining priority is native wiring and evidence, not 50 additional user-visible placeholder features.
- After per-owner source receipts and contract tests, E06 integrates accepted routes in one serialized batch and E07 independently accepts same EXE SHA.

Acceptance criteria: 50 unique contract IDs, search and settings working in local UI test; unknown backend disabled; source/catalog 50/50 validated; host-integrated X/50 independently counted; functional native Windows acceptance X/50 independently counted. Never equate the first with the last two.
