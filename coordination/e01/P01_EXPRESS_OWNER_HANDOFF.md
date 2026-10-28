# NOX V16 · P01 EXPRESS FINISH · owner-only handoff
RunID: NOX-V16-E01-P01-EXPRESS-FINISH-20261028
Owner: 1. Status: SOURCE COMPONENT VERIFIED / NATIVE WINDOWS HOLD / RELEASE BLOCKED.

This is an *additive receipt and handoff*, **not** a source merge or ready Windows EXE.
The exact NO-LOSS source delta is available as chat artifacts NOX_V16_E01_P01_EXPRESS_FINISH_HANDOFF.zip and NOX_V16_E01_P01_EXPRESS_FINISH.patch.

## Bytes and ownership
C16 source ZIP SHA256 735e2fdcd86c28750ba05f3adaed4285400ea6e723e26b5c79c8fa5186eff485
EXPRESS handoff ZIP SHA256 412b9aa1ce18442555d2b9dff5dcf8f3ce228b1e0db8dcc34e884f4e42887ff6
EXPRESS patch SHA256 2cea55179435b27cc2bce3bf05358538dca2d507b9778216a6335cf79f88c1bd
119/119 C16 source paths retained, 117 identical, 2 edited, 4 new code/QA/CI files, 2 new handoff files, 0 deleted.
All changed path owner=1, no MainWindow or P02–P05 modifications.

| Path | Pre SHA256 | Post SHA256 |
|---|---|---|
| R11/Assets/index.html | 1f62b16e7fdbd66f942564daf2a7085d1cb6a8832eb32f00d0f5136a035ea28f | f1e34b5389eb4f6a669f12e6edc5dc132dff40da1bb44065f8d90b6663f24e18 |
| R11/Installer/Test-NSIS-Windows.ps1 | 166e65011f6c0741e6ba594d3a0f27ef0a5a435f728f6d9299645edfe115fbdb | 1ca1a74fb5ae7bd5b1b3aefb125a8193efc6bbc05eaa667e779819caf97c2a66 |
| R11/.github/workflows/p01-express-native.yml | ABSENT | 42d300f6f5c65e5d05a0c95fab7c17ae93511b3af8036fc0fb8c79394fb4871c |
| R11/Installer/Run-P01-Express-Windows.ps1 | ABSENT | 16968cd8376f04507c6987dc947a9eb440bc898794fe58bc9659e4f314541f57 |
| R11/QA/P01_EXPRESS/test_express_source.py | ABSENT | a3a3b493293f75ee963d4e3905fac0b948dd1aedb78005997fe200d3e9e88826 |
| R11/QA/P01_EXPRESS/test_menu_routes_browser.py | ABSENT | b81370d36c2eaf51fd453aaa457a8e3dfb7c02c32d5ca5287ed6f4fba1527cb2 |

## Verified
33/33 owner source tests; 4/4 interactive Chromium UI widths with 8 MENU/16 existing-screen links, Ctrl+K, Esc, history back and deep link; 3/3 inline JS parse; exact byte preservation and ZIP CRC.

## Required for actual P01 completion
Apply the exact source delta onto E06 owner-sealed canonical source tree only with matching preimages. Place workflow at GitHub repository root .github/workflows/ if the canonical source lives under R11. Run Windows-2025 disposable CI: official signed WebView2 standalone prereq if needed, dotnet publish, real NSIS compile of distinct 16.0.0 / 16.0.1, /S install, installed WPF MainWindowHandle + WebView2 NAV_OK, upgrade, rollback, uninstall, data retention, exact SHA receipt. Stop on mismatch. Do not transfer previous different-SHA success. №6 serial integration, №7 independent E07 same-SHA acceptance.

E01 Drive evidence readback PASS:
https://docs.google.com/document/d/1mJA2eGuTwe-sQNgB_nrCl7is8jkIM7O-tGS5VRxyXX8/edit
E01 lessons readback PASS:
https://docs.google.com/document/d/1P__RHxWuH4f5cZ_4vwSIF-BN82FIGTzGzlhqCizMD1I/edit

Git tree/blob SHA for the local modified source are not yet established by a commit. This handoff file is documentation-only until actual source bytes are staged and merged; no EXE or P01 product completion claimed.
