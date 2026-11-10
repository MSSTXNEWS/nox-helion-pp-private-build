# NOX V16 · E01/P01 C09 · NO-LOSS candidate · NOT integrated
RunID: NOX-V16-E01-C09-20261028-TURBO10. Owner: executor #1.

## Scope and invariants
Only owner #1 installer scripts and reviewable independent P01 tests are changed.
The complete C08 application donor and all C07/C08 originals remain in the full Drive ZIP.
Original D02 HOME/MENU/CORE image bytes, five Persona, WOW 10+10+10, WebView2
MainWindow, local Ollama / RAG / SQLite / GPU training and voice paths remain unchanged.
The C08 two-full-pass no-loss uninstall protection is preserved and hardened.
No second host, renderer, downloader, LLM, GPU worker, service or database is created.

## Files for serial #6 integration
Apply owner-scoped files in Installer/ to the *verified matching C08 preimage* under
R11/Installer. Check P01_C09_RECEIPTS.json pre/post SHA256, per-file patch SHA256
and full-source archive SHA; do not attempt to apply straight to GitHub main
packaging tree; restore from immutable previous ZIP for rollback. The existing
C08 source file and fixture are independently preserved for comparison.
The versioned candidate branch deliberately does not replace production MainWindow.

## Verified and unverified
Local pytest E01 C5+C08+C09 static checks 20/20 PASS; SHA visual preservation
and regression included. Windows PowerShell native fixture is executed only by
an actual Windows GitHub Actions runner; no PASS should be claimed before
there is a matching run ID, head SHA and successful logs. WPF/WebView2, NSIS
installer update/rollback/uninstall transactional run, GPU and final EXE are
not accepted by this source candidate. #6 and #7 keep their gates.

## Failure isolation
Current canonical main Git SHA1 eb46b49fb8a022cefa679afb8606877016808db1
is packaging only, NOT the C08 donor full SourceLock; do not join these hashes.
If owner preimages, current source tree, old manifest or approved assets disagree,
OWNER_CONFLICT/HOLD. Never delete old ZIPs, branch PRs or owner receipts.
