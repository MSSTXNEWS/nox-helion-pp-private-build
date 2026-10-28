# NOX HELION V16 · Unified WOW 1–150 · Native event admission

**Status: additional tested source layer, NOT 150 approved Windows EXE features.**

This PR is **stacked on PR #32** (which is stacked on #31 → #30). Original approved D02 HOME, 8 CoreID, five Persona, training, installer, media, models, and existing effects are not overwritten. A separate PACK01 PR #33 contains the 50 UI-function cinema materials and route gates and must be admitted independently by integrator #6.

## What was actually corrected
- 50 existing WOW #51–100 are retained (five groups of ten, 100 existing keyframe channels).
- 50 existing WOW #101–150 are retained (one shared Web Animations director, three existing layer channels per shot).
- One **new admission layer**, not a competing renderer, mounts those original two components only on approved *secondary* screens. Only one visual group is active at a time. D02 HOME is never modified or rendered by this adapter.
- Strict canonical `NOX-INSTALLER-EVENT-v3` envelopes with event_id, task_id, run_id, positive monotonic event_sequence, source ownership, SHA256 receipt, timestamp freshness, and truthful progress bounds before showing any event-driven cue. The trusted Windows host must verify event producer/session and receipt signature independently. Web pages do not obtain that privilege.
- The historical WOW #82, #83, #84, #88, #90 event types do **not** exist in the current approved v3 schema. They are **DEMO/HOLD** until an explicitly reviewed schema extension. No fake listening, thinking, voice streaming, pause, or offline telemetry.
- Supported native event visual mappings: task.started→#81, verified P03 model pull progress→#85, P04 rag.ingest completion→#86, verified P04 training.step/checkpoint.saved→#87, P03/P04 model.stopped→#89. These translations exist only inside the visual adapter; the original event log is immutable.
- Replay suppression per RunID with bounded cache (64 runs), 30-second event freshness window, duplicate mount protection, fail-closed subscription errors, cleanup/unsubscribe, Reduced Motion and ECO profiles.
- No second Ollama, RAG, database, frontend router, subprocess, public server, privileged bridge, external CSS/font/SDK, or GPU runtime.

## Integration contract
```js
import {mountUnifiedCinema,reviewWowScopes} from "./gate.mjs";
// Only a trusted, already-approved SECONDARY slot.
const wow=mountUnifiedCinema(secondarySceneRoot,{
  mode:"BALANCED",
  trustedEventPort:existingNativeEventsV3, // trusted host only; returns unsubscribe
  nativeAuthorizeShot:existingHostAuthorizeShot
});
wow.preview(51);   // clearly marked DEMO
wow.preview(101);  // existing director; clearly marked DEMO
// When native producer emits source-verified events, visual effects can react.
// Do not call receiveCanonicalEvent on untrusted website JSON.
wow.destroy();
```

Include existing 51–100 CSS, existing 101–150 CSS, and **this** `scene.css` on the secondary scene only. Source receipts are emitted from Windows CI as an artifact; existing PR #31 receipts are read and checked without rewriting historical hashes.

## Acceptance gates and remaining scope
- **Source:** original 51–100 and 101–150, one attached admission controller, deterministic tests and SHA receipts.
- **Windows component:** a passing Windows CI run on exact head commit is required.
- **Native host:** E06 needs a verified source tree and single authenticated events.v3 bridge; UI cannot prove producer integrity by itself. PACK01 #33 1–50 stays separate and its 50 buttons are not integrated by this commit.
- **Release:** no production WOW percentages. E07 independently tests actual Windows EXE same BuildID/SHA, D02 original art, 10 realism+10 WOW+10 cinematography checks, actual WebView2 animations, CPU/GPU budget under local LoRA training, reduced motion and key/touch accessibility.

The collection has 150 *source candidates* across separate PRs, **not 150 accepted interactive functions**. P04 real training, SIP calling, downloaded voice/model weights and private mobile gateway require their own host/rights/QA acceptance.
