# NOX V16 · E03 one-host Python admission for integrator 6

RunID: `NOX-V16-E03-ONEHOST-PY-20261028` · Owner 3 · Scope `Packages/P03/Source/python-host/**`.

## Actual reusable source
- `p03_onehost_port.py` plugs into **existing** PACK01 NoxPackHost and injects **existing** P02 OllamaClient. It does not instantiate Ollama, SQLite, HTTP, a second downloader, installer, RAG or an app host.
- `catalog30.discovery.json` is generated from the existing P03 `ModelCatalog.cs` (Git blob SHA-1 `9b9e293be5a785369764fe378ee69c6c88c86b46`). All 30 families are REVIEW_REQUIRED, none enable downloads or assert legal rights, specific tags, digest, size or VRAM.
- `test_p03_onehost_port.py` runs on Windows against pinned **real source** P02 owner branch commit `71a32bf4e2d5ab7f1e17fc91de3502170a8885f7` and existing PACK01 native-host commit `be1fe05d88443e41b0d196617840508d9dd39b7d`. Only local fake /api/tags server; no weights, disk installs, P02 database migration or paid APIs.
- `.github/workflows/e03-p03-python-onehost.yml` is owner3 component source CI; not a production EXE test.

## Three source-connected read-only routes
`models.catalog`: 30 discovery cards, search, explicit `downloadEligible: false`.
`models.installed`: original P02 `OllamaClient.models()` calls loopback `/api/tags` and returns installed tag names. No invented digest or model licensing.
`models.digest`: reuses **existing P02 OllamaClient._open()** to read bounded loopback `/api/tags` and reports exact Ollama-returned manifest digest for an unambiguous installed tag. It never downloads or hashes weights. `independentlyVerified: false` and `licenseVerified: false` even if a digest is present; malformed/duplicated/missing tags HOLD. This is a P02 internal source seam pinned in CI, not a stable public SDK API: #6 must review it against the chosen canonical host.

## Six guarded owner routes
`models.pull`, `models.gguf.import`, `models.queue`, `models.cancel`, `models.retry`, `models.preflight` remain HOLD by default. They bind **only** when #6 injects an actual owner3 backend with a matching method, a live `available()` probe, verified user scope, SourceLock-bound owner receipt, and fresh native approval for sensitive writes. The host must not infer installed state from an enqueued/queued job.

## Exact #6 hookup (in canonical single Python host, after SourceLock)
```python
from native_bridge import BoundPort  # existing PACK01 module, not a new host
from p03_onehost_port import P03OneHostPort
p03 = P03OneHostPort(existing_p02_ollama_client)
routes = p03.register(existing_dispatcher, BoundPort,
    receipt=verified_owner3_source_lock_receipt)
assert routes == frozenset(("models.catalog", "models.installed", "models.digest"))
```
The caller owns `existing_dispatcher`, `existing_p02_ollama_client`, its ACL and root WebView2 navigation. The receipt must be bound to a frozen source tree by #6; do not accept a string from page JS. Do not register a duplicate P03 handler from PACK01 C# proposal simultaneously. The actual original `helion/` host is only declared verified by E06 on whole-source SHA/owner audit; no main merge performed here.

## NO-LOSS and acceptance
Original C40 and TURBO10/11/12 archives, C# queue worker, GUI D02, eight CoreID/five Persona, P04 training, P05 events.v3, voice, mobile and WOW 10+10+10 untouched. CI code/Python source may be verified as a component. No real local user Ollama download/GGUF or licensed pinned model, no canonical original host integration, no final EXE, and no E07 same-SHA acceptance are claimed. Output is owner3 integration **candidate**, not full release.
