# NOX V16 · TURBO10 · P02 · non-destructive handoff to #6

**Owner:** Executor 2. **Scope:** `Packages/P02/worker-python/**` only. All original C#,
D02/HOME/MENU/CORE, 8 CoreID, personas, GPU/LoRA, assets, WOW, and other PR files are
unchanged. This patch is deliberately *additive*. Nothing is merged to production.

## Ten tasks from V16 §26.4

1. **Original host recovery — HOLD with physical preflight utility.** `p02_host_probe.py`
   reads 3 package parts and verifies their joined exact source SHA without extracting
   or rewriting; reports missing original parts as HOLD. The GitHub parts are not
   available as raw bytes in this executor's workspace. Original SourceLock/host APIs
   and existing database mapping remain #6-only tasks. A donor receipt with 76/78
   matched hashes cannot be substituted for current source.
2. **Installed Ollama models — candidate hardened.** The existing `/api/tags` result is
   size-limited to 2 MiB; malformed JSON fails closed; requested model is verified
   by the live `/api/tags` list *before* saving a user prompt. No fake tags.
3. **Live streaming/STOP/TIMEOUT — candidate hardened.** Existing single-stream
   STOP and worker+consumer lease retained; redirects out of loopback now denied
   to prevent prompt exfiltration. Oversized answer stops stream, not stored as
   completed. Deterministic regression checks added.
4. **One SQLite + ACL/migrations — compatibility gate.** New read-only inventory of
   existing schema; existing `p02_*` migration remains disabled if original chat
   schema exists. #6 must map/backup and migrate the actual application DB.
5. **MIME/quota/SHA/STORED-ID — retained, tested.** Existing physical staging,
   sha256, owner checks, safe delete and crash-restart GC not deleted or replaced.
6. **Chat ↔ RAG — verified source seam retained.** Existing scoped RAG callback,
   link validation, `chat.sources` event, no second index or chat. Timeout/error
   response does not persist a successful assistant completion.
7. **HELION/CoreID/Persona — independent context contract.** `context_key` uses
   native-host-approved CoreID and Persona registry; unknown names are refused.
   It returns an opaque deterministic context ID, not an authority token or DB.
   Original CoreID/Persona names are intentionally not invented here.
8. **RU↔ES ASR/LLM/TTS + MAESTRO — consent/rights-gated local pipeline.**
   `LocalVoicePipeline` injects original host ASR/TTS and SAME chat LLM callbacks.
   No actual ASR/TTS weights, microphone or live voice runtime were available.
9. **SIP call + mobile/private media — fail-closed contract.** Fresh provider-verified
   tariff quote, independently checked native consent, single-use receipt, E.164,
   STOP, private-peer+HTTPS-origin+CSRF+native-session check; no new public gateway.
   Optional local-video path validation requires explicit picker consent.
   SIP provider and Tailscale identity proof MUST be supplied by #6, not JS.
10. **Contracts/tests/receipts.** Offline deterministic Python unittest + compile
   across all P02 files; SHA-256 and Git blob SHA-1 before/after receipts; exact
   handoff to #6. Component PASS does not certify Windows, real local models,
   microphone, SIP, public networking, or the final EXE.

## Integration rules

- A single original Windows EXE and trusted `events.v3` host are authoritative.
  No second DB, Ollama server, UI, RAG index, web engine, or paid API.
- #6 inspects original archive and every donor PR (esp. #16 mobile and #18 voice)
  before choosing implementations; adapt only **missing** semantics into the
  existing original host and preserve both candidates until verified equivalence.
- Native host verifies identity, owned file bytes, model installation, voice
  model rights, provider tariff, microphone and call consent. Never trust page JSON.
- Device limitations / unavailable rights or credentials yield HOLD and never
  synthetic success. One writer owns `MainWindow` and the original host (#6).
- All optional WOW and cinema 10+10+10 remain in separate unchanged assets.
- #7 reviews one immutable final EXE BuildID/SHA after #1–#5 readiness.

## Source references

- Official Ollama `/api/tags` and `/api/chat` NDJSON interface.
- Microsoft WebView2 security guidance: validate browser-reported source, prefer
  structured `PostWebMessageAsJson`, disable host objects on untrusted content.
- PR #18 already contains voice/teacher/SIP *UI candidate*; this code is
  non-UI host contracts, not a replacement of that approved candidate.
