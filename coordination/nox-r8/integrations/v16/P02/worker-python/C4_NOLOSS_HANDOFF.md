# NOX P02 · C4 NO-LOSS owner handoff

RunID: NOX-V16-E02-C4-NOLOSS-20261028. Owner #2. Draft PR #13 only; no main merge.

Ten targeted technical constraints strengthened: (1) reject symlinked attachment staging, (2) reject symlinked stored directory, (3) refuse outside-root storage drift, (4) SQLite FK enforcement before every mutation, (5) verify existing P02 cascade FK relationships, (6) reject historical FK violations without modifying rows, (7) publish immutable stored blobs without overwrite on UUID collision, (8) validate roots before read and deferred GC, (9) allowlist exact existing host event payload fields, (10) validate RAG citation/event schemas and bounded JSON prior to native delivery.

`python -m unittest discover -s Packages/P02/worker-python -p 'test_*.py' -q` -> 41/41 PASS on synthetic local Python. `python -m compileall -q Packages/P02/worker-python` -> PASS. These tests DO NOT prove real Windows EXE, live Ollama/voices/SIP, or current E06 SourceLock.

#6 must use the existing native SQLite connection and events.v3 bridge, preserve the original D02, WOW 10+10+10, approved voice/MAESTRO, model/QLoRA and every unique file. No second DB/UI/backend. This is a source patch candidate and must be adapted only after verified source tree + native owner map. #7 owns independent same-BuildID EXE acceptance.

Do not merge this branch merely because tests pass. Existing C# candidate and P01/P03/P04/P05 donor branches remain intact and unmodified.
