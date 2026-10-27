# V16 FASTPATH UPDATE (RunID NOX-V16-E02-FASTPATH-20261028-01)

**Preferred compatibility route: Python stdlib candidate**, now preserved at
`Packages/P02/worker-python/p02_runtime.py`,
`p02_chat_bridge.py`, `test_p02_runtime.py`, and README.
Synthetic local component tests: 6/6 PASS on Python 3.13 with no third-party dependency.
The three Python files were read back from GitHub and byte-pinned against local git blob SHA-1.
Official references: https://github.com/ollama/ollama/blob/main/docs/api.md
and https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/security .

Original C# files in this PR remain uncompiled, unintegrated fallback candidates ONLY.
**Do not load C# and Python as two simultaneous chat engines or create a new SQLite DB.**
#6 must inventory source ZIP + current Python/PyInstaller runtime, choose existing paths
and either reuse or port only nonduplicative behavior. Do not copy Python files into
an installer without the SourceLock and owner's acceptance.
No live Ollama provider, real RAG pipeline, WebView2, Windows EXE or E07 acceptance
was exercised. Component fixture proof != integrated/accepted.
---
# NOX FIN ZAGR V16 — Executor 2 · P02 owner handoff

Status: PATCH_CANDIDATE only. Integrator #6 must reconcile existing source archive and
SourceLock before transplant. E07 independently verifies the resulting exact Windows BuildID.
Never merge these files as a replacement UI, a second chat engine, or a second DB.

## Files and purpose

- worker-chat/OllamaChatClient.cs — localhost-only Ollama `/api/tags`, `/api/chat` NDJSON streaming,
  STOP via caller token, first-response and stream-idle timeouts, incomplete stream fails closed.
- worker-chat/ChatSqliteStore.cs — one database path supplied by native host; user_version 1,
  ACL (trusted tenant+principal+chat), messages, attachment metadata, pruning and delete receipts.
- worker-chat/AttachmentPipeline.cs — picker stream supplied by native host; allowed MIME signature,
  max 25 MiB/file and 100 MiB/chat, staging and opaque ID, SHA256, authorized read and purge.
- worker-chat/SpaceBrowserBoundary.cs — policy for existing WebView2; no external-page native
  privileges, no host objects anywhere, only mapped `https://nox.invalid/` can request whitelisted
  bridge operations, with additional native ACL/gesture confirmation.
- P02.Candidate.csproj + smoke/P02.Smoke.csproj + smoke/Program.cs — isolated net8.0
  dependency-pin and offline contract fixture. Not executed here.

## Critical integration sequence for #6

1. Verify source_00.part + source_01.part + source_02.part against the pinned ZIP SHA-256
   from BUILD_INPUTS_README, extract the real application source, and produce current
   Git-bound SourceLock + owner receipts. The packaging on current main is a Python/
   PyInstaller candidate; do not assume a C# host exists or change runtime architecture.
2. Inventory the real existing chat database, UI, picker, RAG and events.v3 code.
   If Python is canonical, port individual checked semantics into the existing Python host;
   do not silently add a second runtime or second data store.
3. If a native .NET host is confirmed, resolve package restore/pinning (Microsoft.Data.Sqlite
   8.0.32), call InitializeAsync against **the one authoritative database** after controlled
   schema migration/backups, and derive tenant/principal ONLY from trusted host identity.
4. Route the existing model selector to GetModelsAsync; reuse existing selected-model state.
   Route existing chat to StreamChatAsync; STOP cancels the caller CTS, UI shows actual errors.
   Do not persist partial assistant output as completed when STOP, timeout or EOF occurs.
5. Native picker passes byte stream to StoreAsync; show ACK only after SQLite commits.
   Pass only attachment ID to chat/RAG; read via OpenAuthorizedAsync after owner check.
   Deletion: DeleteAttachmentAsync/DeleteChatAsync first, then purge returned storage IDs.
   On startup reconcile orphans after grace period, respecting concurrent sessions.
6. Native WebView2 mapping must pin the reserved shell origin to packaged local files and
   disable host objects/capabilities for all external pages and subframes. Validate WebMessage
   SOURCE from the browser control; never accept page-provided origin or identity.
7. Bridge state changes ONLY over the ONE existing events.v3 contract in host #6; events
   must have real RunID/error/status, not a new parallel bridge.

## Explicit limitations / blockers

- Original source archive was NOT extracted in this run; no original app preimage, compile,
  smoke execution, .NET restoration, Windows runtime, or E07 acceptance evidence.
- Database encryption/OS file ACL, full backup+nontrivial migrations, crash-safe orphan
  reaper, total-disk quota, antivirus/deep media scanning and multi-process quota races
  require integration work. Logical ACL alone is not OS ACL.
- Browser boundary is policy-only; host must enforce it at actual WebView2 events.
- Offline smoke is source, NOT evidence it passed.
- Current main still the authoritative production candidate. None of these files belongs to
  shared host/MainWindow, training/model catalog or P05 worker paths.

Run offline (on a machine with .NET 8 SDK and approved offline NuGet package cache):
`dotnet run --project Packages/P02/smoke/P02.Smoke.csproj`
It proves only local contract fixtures, never actual Ollama/GPU/WebView2/Windows acceptance.

Owner: Executor 2. Roles (virtual tracks, not separately spawned): transport, async
control, data architecture, ACL/security, attachment integrity, browser boundary.
TaskIDs: N2-01 15; N2-02 20; N2-03 20; N2-04 10; N2-05 20; N2-06 10; N2-07 5.
Activity approach count is NOT product completion. Verified accepted weights: 0/100,
until real component + integration receipts and same-BuildID E07 pass.
