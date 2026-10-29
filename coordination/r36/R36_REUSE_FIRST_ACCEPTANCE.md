# NOX HELION · R36 · READY-MADE OSS INTEGRATION · 2026-10-30

## Exact scope
Incremental secondary Control Center adapters. **NOT** a substitute for owner-approved HOME/MENU/WORK or the source of NOX/Windows PR162. No new permissions, auto-acceptance, output formatting changes, image/persona regeneration, or external paid APIs.

A local deliverable was assembled and tested as `NOX_HELION_R36_REUSE_PACK.zip` (file bytes must be obtained from the producing assistant's verified attachment; this Git receipt is *not* a claim that the binary is uploaded to GitHub).
- Zip SHA-256: `9c0260cf566cb13103dbb9b1c5bc9a3835f328429adf0922cac993db2ba18655`
- 16/16 Node contract tests PASS; ZIP CRC PASS.
- Existing V25.1 raw JS original SHA-256 `fd573dad49679ce1d0cec74a4f0df331da1aafcc94082f5e9bbf36d414b19d3e`; R36 add-only patched SHA-256 `68a3aabc7435d72e841e7488dac7edaea7469813382f6986e8454c3af56f7bdd`. Patch: on verified snapshot emit `nox:snapshot`, on error emit `nox:snapshot-error`, reduce polling 4s→90s and pause while hidden. Do not overwrite an unverified Vercel production revision.

## Exactly checked upstream packages (all free/open-source)
| Function | Package | Version | License | URL |
| --- | --- | --- | --- | --- |
| Graph & DAG inspection | cytoscape | 3.34.4 | MIT | https://github.com/cytoscape/cytoscape.js |
| Run/QA time series | uplot | 1.6.32 | MIT | https://github.com/leeoniya/uPlot |
| Verified event FX | motion | 14.7.1 | MIT | https://github.com/motiondivision/motion |
| Owner-approved 3D scene (optional) | three | 0.186.1 | MIT | https://github.com/mrdoob/three.js |
| Additional complex analytics (optional) | echarts | 6.1.0 | Apache-2.0 | https://github.com/apache/echarts |

Adapters use native npm packages via dynamic import once dependencies are installed in the actual project. The offline Node tests run without pulling private data or contacting external servers. Unconfirmed integration/render paths MUST remain NOT_VERIFIED. No external CDN or embedded API keys. All five package versions were checked on npm pages.

## Current NOX design guards
D02/WOW200 with owner-approved HOME `NOX_HELION_HOME_CURRENT_OWNER_APPROVED_20261022.png` SHA256 `382c1069afcaaaed11c319796f2c553d2bd977d7e46c68ecd7d55af26e132a4a`. MENU has current ten floating worlds visual override with legacy eight menu route mapping preserved. Approved identity is immutable and Elina remains IDENTITY_CONFLICT_HOLD. Full visual acceptance: A01–A10 + R01–R10 + U01–U10 + C01–C10. Never elevate demo metrics (e.g. 84.6%, 42/50, estimated 34–48 min) to production without frozen ledger and independent exact-head QA.

## Next exact physical integration gates
1. Resolve canonical deployed V25 `v25.js` Git/file hash and secure API, verify current owner-approved assets/permission.
2. Rebase only patch anchors onto *current exact source*. Install from pinned npm registry with lockfile and license notices, check CVEs and bundle size.
3. Mount graph/trends into existing secondary screens only. Unknown owner→task links remain HOLD; no fake FX.
4. Browser QA with real packages + 320/390/800x480/1440/1920/4K, reduced-motion, actual source snapshots and offline/failover.
5. Independent D/art acceptance plus manual #2 source QA; deploy only after authorized approval, Vercel readback and verified authenticated refresh. No EXE/CI/E07 before SOURCE_READY.
