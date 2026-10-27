# NOX V16 · Five WOW microfeatures — integration handoff

This source patch is for **trusted secondary NOX screens only**. HOME D02 remains solely central HELION + 8 orbiting CoreIDs. Existing approved art and Persona identities are untouched.

Five effects, one dependency-free JavaScript module:
1. Obsidian translucent glass edge with state-based illumination.
2. Real CPU/GPU/VRAM readout; missing sensors show Н/Д.
3. Up to eight allowlisted quick commands, disabled unless enabled by the host.
4. Last six real run events from host, no simulated progress.
5. Focus mode with one-click visual decluttering.

## Integration
Load `Assets/nox-wow5-secondary.js` in a local, NOX-controlled WebView2 page, never arbitrary websites:

```js
const ui = NoxWowFive.mount(document.querySelector('#secondaryStatus'), {
  send: (type, payload) => chrome.webview.postMessage({type, ...payload}),
  isHome: false
});
ui.setState('running'); // Only on real host status
ui.setTelemetry({cpu: null, gpu: null, vram: null}); // Host measurements only
ui.setCommands([{id:'model.center', label:'Модели', enabled:true}]); // Host allowlist
ui.addEvent({runId:'r-1',state:'running',timeUtc:'2026-10-28T00:00:00Z'});
```

The native Windows host **MUST** validate trusted origins, route IDs, privilege grants and message schema before executing commands. No privileges in a browser page displaying outside websites. No artificial values, model downloads or EXE acceptance claimed.

Other previously agreed V16 decisions remain: 20 one-click `p03.install` model buttons connected to the **existing** P03 C37 Ollama queue after in-app license consent; `nox.update.request` goes only to the P01 installer; one chat for HELION and selected Core/Persona; function search Ctrl+K everywhere **except HOME**; standalone WebView2 browser with no privileged bridge; optional image generation must not postpone working chat/RAG/training.

Owner #1/#5 validates original UI/telemetry contract, integrator #6 serially merges the approved source, owner #7 verifies Windows behavior. No need for another rendering library or background process.
