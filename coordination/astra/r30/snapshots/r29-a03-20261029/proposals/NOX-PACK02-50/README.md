# NOX HELION V16 — PACK02 / 50 local tools

**Status: 50 implemented offline source operations with a working opt-in secondary-screen UI. Not installed or accepted in the final Windows EXE.**

Fifty new distinct TaskIDs NIP02-01..50, divided into 5 groups (media / documents / data / developer / workflow, 10 each), each mapped to a real callable method in `ops.mjs`. All fifty have a real button in `panel.mjs`; text/options enter memory and results display via `textContent` with no HTML injection. `catalog.mjs` and `catalog.json` hold matching contracts. `smoke.test.mjs` exercises all fifty, 50-route collision checks versus PACK01, genuine timing/CSV/progress regression and failure-closed protections.

### How to run without altering D02

```js
import { mountPack02 } from "./proposals/NOX-PACK02-50/panel.mjs";
const view = mountPack02(document.querySelector("#approved-secondary-tools-mount"));
// CSS: proposals/NOX-PACK02-50/panel.css
// view.dispose() on navigation.
```

Runs **locally without installing or contacting a service**. Reuses browser/Node built-ins rather than adding another Ollama, database, events bus, media player, FFmpeg worker, or Web server. Captions conversion, subtitle timeline checks, documents, quoted CSV, JSON, UTF-8 codecs and weighted task progress actually compute results in process. This is NOT a media playback engine, Whisper ASR, GPU LoRA training, backup of files, or SIP telephony.

### Ready-made upstream candidates for future host admission

When legally compatible and needed, the canonical owners can adapt [subtitle.js](https://github.com/gsantiago/subtitle.js) (MIT), [Papa Parse](https://github.com/mholt/PapaParse) (MIT), [Marked](https://www.npmjs.com/package/marked) (MIT) with [DOMPurify](https://www.npmjs.com/package/dompurify) (MPL-2.0/Apache-2.0), and Microsoft WebView2. They are **not bundled, downloaded, installed or purported to be working** in this branch. No new paid APIs are added.

### No-loss release boundary

The branch is stacked on PACK01 PR #27; no original application files, canonical D02 HOME/MENU/CORE art, Persona, trainer, RAG, installer, host bridge, backups or source archive parts changed. Only integrator #6 may mount the additional view within the authorized original host after exact SourceLock and owner receipts. Owner #7 independently tests the final Windows EXE BuildID/SHA. Isolated CI PASS is source/component evidence only. RELEASE stays BLOCKED until those gates.

Potentially unsafe inputs are bounded (100k chars, max 200k result), no privileged calls are available, and no network/IO is executed. Avoid using `innerHTML`; all displayed results are plain text. Local clipboard/export/download is not done without user action. On HOME, mount is denied.

### Tests

`node --test proposals/NOX-PACK02-50/smoke.test.mjs`

### RunID and ownership

`NOX-V16-PACK02-50-20261028`, coordinator-only isolated new paths owned by #6 pending authorization to include in original SourceLock. `NIP02` TaskIDs avoid all `NIP01` collisions. Every existing PR remains untouched. Acceptance: source functions 50/50, native EXE 0/50 unverified, independently verified Windows EXE 0/50, progress of whole product N/D.
