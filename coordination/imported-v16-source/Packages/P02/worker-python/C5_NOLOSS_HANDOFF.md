# NOX V16 E02 C5 — no-loss handoff to integrator #6

RunID: `NOX-V16-E02-C5-20261028`. Owner **2**. This is a source-only candidate, not an integrated Windows EXE. `main`, `MainWindow`, D02 HOME/MENU/CORE, original 8 CoreID, Persona, GPU LoRA/QLoRA, voices, SIP, model weights and all WOW 10+10+10 are untouched. No new backend, renderer, SQLite DB, event bus, model downloader or server.

## Apply selectively — do not overwrite the existing host

Use `P02_C5.patch` only after owner #6 reconstructs and hashes original source archive, freezes a current SourceLock and maps the authoritative database, selected model, WebView2 origin and existing events.v3 bridge. The Python code is **not** evidence of a production .NET/Python host binding. Retain every other candidate as an independent preserved source until content-level reconciliation is complete.

## Ten fail-closed corrections

1. Reject symlink attachment roots before `.resolve()` (never let root link select a foreign store).
2. Explicit SQLite `BEGIN IMMEDIATE` makes initial DDL and metadata rollbackable on a failure.
3. Deny existing schemas with matching columns but missing chat/message/attachment primary keys.
4. Deny existing attachment schemas with no UNIQUE index on `storage`.
5. Revalidate staging/storage roots **before** creating the first temporary file.
6. Check trusted-owner ACL **before** consuming an input stream; recheck before transaction commit.
7. Reject `read()` returning `None`, non-byte output or chunks larger than the requested bound.
8. Reject `text/plain` containing NUL anywhere or invalid/incomplete UTF-8 even across chunks.
9. Detect unexpected hardlink aliases on authorized reads and queued physical deletion.
10. Validate existing host event model/complete ranges and reject unsafe citation URL schemes at the relay boundary.

### Focused evidence and limitations

`python -m unittest discover -p 'test_*.py' -q`: **52/52 PASS** in isolated Python 3.13 fixture on Linux. `python -m compileall -q`: PASS. New file `test_p02_c5_integrity.py` covers 11 adversarial cases. This does **not** test actual native Windows, Windows NTFS hardlink behavior, live Ollama, real user SQLite migrations or native WebView2. Critical HOLD until #6 maps real app and #7 validates exact EXE SHA.

Source-admission guard: Git blob SHA-1 preimages of `p02_runtime.py` and `p02_host_admission.py` must exactly match values recorded in `P02_C5_RECEIPT.json`. Do not use a 40-hex Git blob as a 64-hex SourceLock hash. Existing C4 source and tests stay preserved. Verify snapshot and target files before any cherry-pick.

Host privacy: native authority supplies actual principal, tenant, consent and RouteID mapping. Never accept a page-provided userId, bridge scope, model-installed flag, microphone authorization, tariff or SIP quote. No Codex login without approved official flow. No new model downloads, hardware training or calls were performed.
