# NOX V16 E02 C11 · Binary WPF-to-existing-Python transport candidate

Owner 2; do not merge directly into WPF MainWindow/host. This module is a .NET8 **library** that consumes E06-owned private stdin/stdout streams and sends the precise `p02_native_ingress.NativeIngress` / `p02_framed_worker.serve_native_frames` protocol. It does not launch a process, start a server, create a DB, or create a second LLM. Only the **smoke test** starts a throwaway Python fixture child.

Wire spec: exactly five JSON request keys (`protocol`, `requestId`, `route`, `payload`, `runId`) inside 4-byte BE length frame, 64KiB request, 1MiB response. Enforces authenticated host-owned RunID, cryptographically random 32-lowercase-hex nonce, one in-flight non-STOP request, concurrent STOP, route allowlist and page identity-claim denial. Python ingress separately owns SID/ACL and the single existing PACK01 dispatcher. The C# client matches out-of-order replies by requestId and denies unknown responses. All timeouts are fail-closed: no automatic replay of uncertain actions.

Windows component smoke, *not* actual NOX integration:
`dotnet run --project Packages/P02/worker-chat/pipe-smoke/P02.NativePipeSmoke.csproj --configuration Release`
This launches `fixture_existing_owner.py` using the **current P02 source** and communicates over real OS process pipes to prove HELION/STOP framing, rejection of page authority, and exact RunID. No Ollama models, dataset, SIP, D02, UI or user file is used. The smoke runner must not be packaged into production.

Integration actions owned exclusively by #6:
1. Reassemble original 729-file Python source, decide one host and pin current SourceLock / 5 owner pre/post receipts.
2. Add `serve_native_frames` to the **original Python app process** under host-authenticated native SID/session, with original SQLite, Ollama and P04 RAG, without creating a second Python daemon. Existing compiled Python binary is still `--diagnose` only until explicitly rebuilt.
3. WPF host launches/supervises ONE original Python process with private pipe; instantiate `NativePythonPipe(stdout, stdin, nativeRunId)` and supply only trusted host-created command payloads. Existing WebView2 origin/route allowlist belongs to #6. Never take native identity or session approvals from page JSON.
4. Test real WPF `chat.model`, HELION streaming/STOP, native events.v3, history/ACL, installer `/S`, rollback, exact BuildID/EXE SHA; #7 independently accepts. Keep all original D02, 8 CoreID, original Persona, GPU training/weights and WOW 10+10+10.

Strict boundary: source+OS pipe smoke PASS does NOT prove actual end-user GUI, final EXE, or independent E07.
