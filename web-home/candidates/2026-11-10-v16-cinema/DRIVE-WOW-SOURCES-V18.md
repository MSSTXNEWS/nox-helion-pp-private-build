# NOX V18 — Drive WOW source ledger (verified 2026-11-10)

Repository source of truth: PR #241. These sources were **actually downloaded into the verification workspace** and hashed as raw bytes. This ledger is not a claim that their historical demo files are production modules, nor that every binary is hosted by Vercel.

| Original Drive artifact | SHA-256 | Role |
|---|---|---|
| [WEB templates ZIP](https://drive.google.com/file/d/1YeLlV1BQvjhwFcuIKolcEzJE4GholXHh/view) | `4515f794d7f0be66c5257c8a0b59d3531d69714615d9ce0e60480cb7a7959b14` | Historical reference; do not replace live routes |
| [Cinematic report ZIP](https://drive.google.com/file/d/1Q69yL_KQjRquhA2xEVZVk2uuFLr2BwO1/view) | `a69885b9ee4139d3f52745077d386b1d23f0c682af9142eeaef724421ed72d5a` | Report art only |
| [10 sections menu pack](https://drive.google.com/file/d/1StiW0V_7tFT94Xdjid7WaUSZ4doex0cZ/view) | `b6bfcbda484c3bb902dc3c9f580d875e844eb7850428d655042d6a4260f3e3d7` | 10 approved section mocks + button/action matrices. ZIP integrity passed |
| [Iron HUD HTML](https://drive.google.com/file/d/19tkzANLsWFx04XGW5EYNmkwRsoDf8Lbb/view) | `299d894bc079fda0ec8b8f79a66431c7f30f6aacc70acc8386a1426052e93087` | Glass/bevel/microstates reference; not a replacement page |
| [Cinematic Motion HTML](https://drive.google.com/file/d/1Ze10h4fPBtS94Cecp5ZthuCtciLHfyIY/view) | `43c04eb6b26663d91e4e70ca2aad166169d440e218e809d67eb4220cb4cf58b7` | Motion/layout reference; includes embedded raster; do not substitute for D02 |
| [Current approved HOME](https://drive.google.com/file/d/11d2ND8pbmZHmdeucuJqYfmds9NJ38wOF/view) | `382c1069afcaaaed11c319796f2c553d2bd977d7e46c68ecd7d55af26e132a4a` | Canonical visual comparison |
| [MAX Motion approved HOME](https://drive.google.com/file/d/1mRSl5BLx_jYBCrEAR-VCWgHlbihaxfMd/view) | `7531c69813c7214a6fdd0780192bd8b9818fd946cb6ba6edcc8b75aa45595ef6` | Motion/detail reference |

## Actual shared integration in PR #241

- `nox-global-wow-v18.css`: consistent premium glass, warm metallic bevels, gentle animated material, active/pressed/focus states, reduced motion and transparency fallbacks.
- `nox-global-wow-v18.js`: existing select controls are represented by genuine clickable button groups, retaining their original native change/input handlers. Glass surface layers use existing `vendor/nox-liquid-glass/liquid-glass.css`.
- `tools/assemble-verified-site.mjs`: injects the shared CSS and JS into ALL TEN existing pages only after a complete existing site and pinned resource bundle pass integrity gates.
- `tools/browser-acceptance.mjs`: checks ten page routes, visible dropdown count, shared script/style and seven viewport sizes; images and true physical GPU remain HOLD until observed.

## Non-loss constraints

Never turn an old HTML demo into a replacement home, flatten D02 into a PNG, delete working handlers, or report a passing visual acceptance without actual browser GPU screenshots. Do not publish to production until independent acceptance.
