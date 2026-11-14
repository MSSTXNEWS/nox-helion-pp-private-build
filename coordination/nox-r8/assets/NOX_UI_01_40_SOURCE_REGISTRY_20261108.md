# NOX HELION UI 01–40 — canonical verified source library (2026-11-08)

**instructions_version:** 0.0.6
**Status:** SOURCE_BUNDLE_VERIFIED; **RUNTIME_INTEGRATION: NOT_VERIFIED**; **RELEASE: HOLD**.

This entry indexes the exact 40 third-party library source artifacts available for selective integration into the existing NOX R8 WPF/WebView2 application. It is **not** a replacement renderer, a separate backend or an installation receipt.

- **Canonical Drive folder (30 parts):** https://drive.google.com/drive/folders/1CK8B-KOasziDFMvcamt8vuNQxpjpmTuR
- **Part manifest:** https://drive.google.com/file/d/1N-e-H2H9aJMCcPKGK7OR8NdC4xRP4JL9/view
- **Join and verify script:** https://drive.google.com/file/d/1gmM_sxRmFD8TIOC-PiMnkxPrHVEeyiuQ/view
- **Independent Drive readback receipt:** https://drive.google.com/file/d/1dhTsP0xTgDnIds_J7aSLga3XhV4WCr6O/view
- **40-component SHA index:** https://drive.google.com/file/d/1SS1MMQ4f5m9NI83bvcDFVdS-9TZaMjJG/view
- **40-component CSV index:** https://drive.google.com/file/d/1gnt1AhM5NNTADwe-5CEpAKDnwt9e5PK-/view

**Reconstructed source archive SHA-256:** `952c662513f145ddf4e12717d67ca3b67978cbae2dd60e1dfc5d6d336529d657`
**Archive length:** 2,059,163,673 bytes
**Parts:** 30 × up to 70,000,000 bytes
**Component inventory:** 40 named entries, 39 distinct SHA-256 payloads; `10_tabler.zip` and `11_tabler-demo.zip` were byte-identical. The duplicated entry is an alias in the manifest, not silently dropped.
**Proof:** all 30 Drive parts independently downloaded, SHA-256 matched, exact full archive SHA-256 matched, ZIP CRC passed and all 39 unique ZIP payloads present. All original source-group MANIFEST/README/SHA provenance retained inside `provenance/`.

**Cleanup:** 45 superseded UI 01–40 multipart transport wrappers (2,078,104,840 bytes) deleted from their former Drive root after verification; new 30 parts remain. This cleanup does not include NOX model weights, local SQLite, private data, unrelated source archives, or other installers.

## Source integration boundary

The library bundles contain templates and dependencies (e.g. Three.js, D3, GSAP, Motion, React components) but copying their ZIP files does not wire these libraries into the actual production `index.html`. For each dependency, extract only the required source and licenses, verify version/compatibility and wire it into the existing renderer/host; independently test at the exact Windows build SHA. Do not overwrite the current native WPF/SQLite/Qwen/STOP/Persona code, duplicate frameworks, or infer runtime acceptance from this source integrity receipt.
