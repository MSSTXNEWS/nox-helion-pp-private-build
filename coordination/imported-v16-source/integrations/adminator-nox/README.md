# NOX HELION · Adminator UI donor adapter

Pinned donor: adminator-admin-dashboard 4.4.0 (MIT, Colorlib/Aigars Silkalns). Its upstream repository documents 18 static pages, vanilla JavaScript, CSS-variable theming, dark mode, Chart.js, FullCalendar and jsvectormap. This is an internal-page donor only; it does not replace NOX HOME/D02, MENU10, WPF, WebView2, Python OneHost or the native security boundary.

## Included

- Exact npm dependency pin and deterministic staging script. The script copies the donor dist tree, injects the NOX skin and entry module into every HTML page, copies the canonical P01 dispatcher, and writes a SHA-256 source manifest.
- Obsidian/ember/ice visual skin. Nested sidebar groups become permanently expanded visible action grids. HTML select controls become visible button groups. Demo notification/profile popovers are removed.
- Fail-closed native route layer. Only route IDs from contracts/menu_v2_existing_routes.json are accepted. A click is confirmed only after the existing native dispatcher returns a matching native ACK/receipt. Missing bindings, unavailable host methods and failures remain HOLD.
- Telemetry rendering accepts only supplied native snapshots. Missing CPU/GPU/RAM/VRAM readings display as unavailable. Sparkline geometry is generated only from validated numeric samples; no random or seeded synthetic telemetry is used.

## Build in a network-enabled runner

From this directory:

    npm install --ignore-scripts --no-audit --no-fund
    npm run test
    npm run prepare:donor

The staging script requires exactly version 4.4.0, checks the MIT license and requires at least 18 HTML pages. It emits artifacts/adminator-dist/NOX_ADMINATOR_SOURCE_MANIFEST.json. Preserve the manifest with the Windows build artifact. Before release, generate and commit the npm lockfile from the trusted registry; do not use an unpinned dependency.

## Native host contract

Before shipping, WPF/WebView2 must initialize both globals before the page adapter mounts:

- window.noxNativePort: the existing host port implementing isAvailable(routeId), invokeRoute({routeId, origin}) and, for sensitive routes, authorizeSensitive({routeId, origin}).
- window.NOX_ADMINATOR_ROUTE_BINDINGS: an explicit key-to-route map using only canonical legacy route IDs. No route is guessed from page title or link text.

The default binding map is empty. Binding values must be exact native action IDs already admitted by `ui/onehost-menu-bindings.mjs` (for example `helion.chat`, `chat.commands`, `models.catalog`, `models.pull`, `models.cancel`, `training.start`). Legacy screen IDs such as `model-library`, `gpu-training`, and `commands` are not native action IDs and are rejected. Until WPF supplies capabilities and bindings, native action controls remain HOLD. Telemetry is delivered using window.NOX_ADMINATOR_UI.updateTelemetry(snapshot) or a nox:telemetry event.

Snapshot contract:

    {
      timestamp: "2026-11-03T12:00:00Z",
      metrics: { cpu: 14, gpu: 22, ram: 38, vram: 31, disk: 42 },
      series: { cpu: [10, 12, 14], gpu: [18, 20, 22] }
    }

These numbers illustrate the schema only, not actual device readings.

## NOX visual rules

- HOME/D02 and the approved eight top-level tiles / ten logical worlds remain with the existing P01 renderer and approved media.
- This package supplies internal work-area pages and components; it does not add MENU roots or new native route IDs.
- No dropdown menus. Nested navigation is expanded as visible button/link grids; select controls become visible button groups.
- Reduced Motion is respected.
- Donor demo identity, sample messages, seeded charts, sample weather and example metrics must never be presented as live NOX data.

## Acceptance boundary

This is an additive source candidate. Still required: npm lock/integrity, WPF host initialization and explicit route bindings, Windows WebView2 rendering, same-SHA Setup packaging, and independent E07 verification. It is not a release until those gates pass.
