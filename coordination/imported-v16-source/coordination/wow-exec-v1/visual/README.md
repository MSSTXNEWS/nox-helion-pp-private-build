# NOX WOW R11/MENU10 — cinematic visual layers (additive)
**Scope:** existing NOX HELION EXPRESS INTEGRATOR WPF/WebView2 only. These sources are installed SOURCE candidates until I0 stages them and E06/E07 pass.

## Changes
- HOME black-sun: original orb image unchanged; two CSS pseudo-layers add rim/corona and pointer parallax (<=3px), with pulse derived only from admitted native bus events.
- MENU10: original 10 logical DOM world nodes receive focus/hover/ACK halo; click events and native routes remain exclusively owned by existing P01 dispatcher. Do not create another menu/section.
- Internal panels: opt-in titanium/obsidian/blur styling on existing approved nodes.
- Persistent event ticker: one tiny DOM component attached to existing original status host. Receives **only** events admitted by createD02NativeVisualBus().subscribe(), checks evidence and freshness, shows real numerator/denominator, routes through existing hostPort.isAvailable/invokeRoute and requires native ACK. No synthetic system.update, gpu.sample or fake LIVE. Stale after 30s and deep links disabled when unavailable.

## I0-only minimal integration in existing mount-p01.mjs
After nativeBus=createD02NativeVisualBus(...), import mountNoxWowVisualLayers from the staged *owner-pinned* E06 path:
```js
const ui=mountNoxWowVisualLayers({
 root,orb:orbs[0].element,
 menuWorlds:logicalMenu.map(x=>x.element),
 panels,notificationHost:existingTrustedStatusElementInsideRoot,
 nativeBus,routePort:hostPort
});
cleanups.push(()=>ui.destroy());
```
The existing host must provide an actual status element within root; do not create a second shell. Stage both exact files with the current Git SHA pin in integrations/wow200/stage_wow200.py and dependent build pin; CSS load only through the existing trusted WPF original asset route and payload. No CDN, npm, new 3D engine or WebView2 configuration loosening.

## Acceptance
`node --test coordination/wow-exec-v1/visual/nox-wow-visual-layers.test.mjs`.
I0 then verifies: 10 logical world hover/focus/ACK, one native route per click, no false events, stale-state behavior, keyboard, Back/Esc/F11, DPI100–200, ECO/Reduced Motion, consent/STOP, original 8 tiles/8 cores/5 persona untouched, same BuildID/installed WPF SHA and independent E07. Stage is not equivalent to runtime PASS.
