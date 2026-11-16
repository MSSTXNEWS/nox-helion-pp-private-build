# NOX HELION WEB WOW MAX V11 · unified HOME glass

**Owner intent:** One shared HOME-cinematic background and one common top icon navigation on every NOX page. Transparent glass panels overlay the moving world; only button/plate material, font, and palette may differ. No dropdowns, no second WebGL renderer/backend, no fake LIVE status.

## Artifacts and verification

- [Complete unified V11 source ZIP](https://drive.google.com/file/d/1QfJTXV-t_ImhzzEYKX7ed_x-5XSwS4sN/view) — **83,961,727 bytes**, **1,261 members**, SHA-256 `1da2b3451ffbf4b47334a6f0f380aa6036179ac69af7b049a2b0e4b6914aab7d`. CRC PASS. Contains 1,258/1,258 paths from V10.
- [Master specification](https://drive.google.com/file/d/1VD2h92rbrq9EI19u_lOKy3f8nffiQ5o8/view)
- [Machine QA results](https://drive.google.com/file/d/1c-S4AoW6cAskFzbcyLaqbZYIY5ogxShW/view)
- [Final receipt](https://drive.google.com/file/d/1WQKXxjRSg_VlYp1Yh_EJs5tHIQEaxJkj/view)
- [Visual test capture, isolated Chromium](https://drive.google.com/file/d/1Ys5uB2PXDuAIsC2-msmtF0nkYBflBN46/view)

## Changed files in `site/`

These three files are **source-byte copies** from the complete V11 ZIP, intended to supersede their same-path V10 files:
- `nox-web-shell-v4.js` — prevent duplicate legacy navigation
- `nox-shared-chrome-v10.js` — single common route row, HOME native catalog forwarding, PC active route
- `nox-shared-chrome-v10.css` — glass panel correction, original alternative world visibility, preserve STOP focus

V11 source is based on the **complete V10 ZIP**, not on an asserted latest production OneHost revision. Do not copy these files blindly to live OneHost without checking exact served SHA and native owner lease, creating independently restorable backup, and testing original chat/S03/STOP/voice/cinema/GPU after installation.

**QA verified:** 43 HTML pages, 83 root JS/MJS syntax, 8 page fixtures across 320/390/800/1024/1440/1920, 13 native select-to-tile controls on PC modules. No lost source routes. **HOLD:** authenticated live OneHost E2E; Chromium HTTP navigation currently `ERR_BLOCKED_BY_ADMINISTRATOR`. No fake production PASS, no deletion of older archives.

instructions_version 0.0.6
