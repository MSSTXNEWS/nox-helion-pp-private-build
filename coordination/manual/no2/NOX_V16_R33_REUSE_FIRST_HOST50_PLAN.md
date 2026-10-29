# NOX V16 · R33 · Reuse-first Host50 source gap closure · MANUAL2 independent QA

RunID: NOX-V16-MANUAL02-R33-20261030-REUSE-FIRST
Source HEAD observed: `0b30916551c34381b3a0905eeafa5e30050aacea`
Owner binding map Git blob: `6e3436821a975b1986261791de060a1020de7079`.
Counts: source 40/50; missing 10; 14 native-pending; 0 EXE accepted. NOT T06 8/8, NOT Windows E07.

**Policy:** Reuse existing owner code first, prefer free built-in Windows APIs or open-source libraries with known compatible licenses; do not create a second host/DB/trainer/browser. A candidate library, UI policy, or offline helper is NOT a native owner route. No fabricated route bindings. Manual #1/T06 sole PR162 source writer, manual #3 P04/P05 donor owner, manual #2 independent QA, T02 sole shared journal writer.

| Existing route | Actual grounded code/reuse | Real missing gate |
|---|---|---|
| training.start | `Packages/P04/train_qlora.py`, `proposals/NOX-PACK01-50/p04_training_readonly.py` | Native authenticated start callback, STOP, rights/holdout/GPU/receipt, no fake Process.Start success |
| training.evaluate | Same original QLoRA worker + read-only checkpoint policy | Native evaluate callback tied to the same signed checkpoint and holdout rights, real result receipt |
| media.player | `integrations/creative/web/persona-media.js` has persona optical loops **only**, not a proven player | Owner #1 must supply actual media transport + STOP/consent/license; no using persona animation as player acceptance |
| media.subtitles | `proposals/NOX-PACK02-50/ops.mjs` already contains SRT/VTT parse, shift, search etc., **offline only** | Bridge explicitly to existing native media owner; optionally use `pysubs2` (MIT) for format handling after dependency review; no duplicate parser |
| browser.open | `Packages/P02/worker-chat/SpaceBrowserBoundary.cs` already defines WebView2 origin policy | Existing WPF `CoreWebView2.Navigate` owner integration, NavigationStarting restrictions, origin/ACL, actual successful navigation proof |
| browser.bookmarks | Same origin boundary + pre-existing native SQLite ownership | Bookmark callback and safe persistence on existing database; no new history DB or silent cross-user reads |
| images.generate | `coordination/donor_workflows/PR56/nox-comfy-image-bridge.yml` is **workflow test only**, not image engine | Real local GPU model + verified license/weights + owner-approved local executor; `diffusers` Apache-2.0 is potential library, not installed or approved |
| system.update | PACK01 UI catalog/dispatcher contains route and consent policy, **not native implementation** | Existing privileged Windows updater with explicit user permission, rollback/readback, no fake DONE |
| system.backup | PACK01 UI catalog/dispatcher contains route and consent policy, **not native implementation** | Owner-verified Windows backup target, consent, file-system ACL, restore proof, never overwrite user data |
| system.pc_control | PACK01 UI catalog/dispatcher contains route and consent policy, **not native implementation** | Safe native control owner + allowlist, mandatory explicit confirmation, reversible/isolated tests |

## Free/upstream reference licenses (verified 2026-10-30)
- pysubs2 MIT, formats SRT/WebVTT/ASS, Python >=3.12: https://pypi.org/project/pysubs2/ ; https://github.com/tkarabela/pysubs2
- Microsoft WebView2 WPF is already the selected native browser control; use the existing Microsoft.Web.WebView2.Wpf integration rather than Chromium clone: https://learn.microsoft.com/en-us/windows/apps/develop/ui/controls/webview2
- Hugging Face diffusers has Apache-2.0 source licensing; individual MODEL WEIGHTS and output rights require separate provenance, VRAM and consent checks: https://github.com/huggingface/diffusers
- Native Windows update/backup/PC control: built-in Windows APIs, not a paid external API; privileges and user consent mandatory.

## Finite finish gate
1. Existing owner provides exact Git PRE/POST bytes and real native method with STOP/ACL/consent; user-facing button remains HOLD until owner method available.
2. Manual #1/T06 integrates on ONE live HEAD with targeted tests, owner receipts and readback.
3. Manual #2 independently checks changed source/security and native callbacks on the SAME frozen SHA; no source-only QA_ACCEPTED.
4. T09 frozen SHA/tree, T10 signed SOURCE_READY, separately authorized GitLab Free Windows build, E07 installed 10/10.
5. If source & owner receipts unchanged, stop with WAITING_OWNER_SOURCE_CHANGE; no endless cycles or synthetic percentage.
