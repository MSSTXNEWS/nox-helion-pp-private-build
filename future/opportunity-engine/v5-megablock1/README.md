# NOX HELION · Opportunity Invention Engine V4

**WORKING STANDALONE FUTURE-MODULE / NOT INTEGRATED INTO NOX WINDOWS R1.**

A complete *read-only idea-research workflow* with 60 retained passports, 12 future search cores and 12 functional agent roles, real local web UI, deterministic idea generator, optional local Ollama ideation, read-only allowlisted scholarly search providers, research notes, independent evidence/pilot gating, journal, versioned JSON adapter, and tests. No model is supplied and no API is required for the basic offline mode.

The module does NOT claim to have validated demand, secured any customer, obtained independent legal/medical review, launched a company, or deployed itself into the Windows NOX HELION EXE. Real business operations always require separately authenticated grants and host integration.

## Windows quick start

Requires **Python 3.10+** installed. Unzip once, then double-click `START_NOX_OIE_STUDIO.cmd` (or run the command below). The app runs on **your own machine**, no remote server or subscription.

```powershell
cd NOX_OPPORTUNITY_ENGINE_V4
python -m engine.cli studio --port 8765
```

Open `http://127.0.0.1:8765` in your browser. Search 60 ideas, inspect their audit blockers, and click **«Найти 3 идеи»** to generate three unverified concepts. Desktop and mobile viewport layouts are responsive. The UI is **a future-module preview**, not a replacement for the approved NOX Windows HOME/MENU/WORK.

## CLI

```powershell
python -m engine.cli verify
python -m engine.cli report
python -m engine.cli list
python -m engine.cli audit OI-001
python -m engine.cli mission --count 3 --seed 3 --output output/my-run.json
python -m engine.cli research-packet examples/care_source_notes.json
python -m engine.cli bridge --input examples/nox_readonly_job.json
python -m engine.cli journal-verify --db state/oie.db
python -m unittest discover -s tests -q
```

`mission --output` will **refuse overwriting** a previous output file. Any source/grant review flags in the input remain untrusted; they cannot authorize a pilot.

### Optional local Ollama

If the user independently installed and authorized a local Ollama service, a compatible model, and its license:

```powershell
python -m engine.cli mission --provider ollama --model llama3.2:3b --count 1 --theme "Практическая проблема маленького бизнеса"
```

The model isn't downloaded or started by the module. It is called only when this explicit command is requested; its response is kept `IDEA_UNVERIFIED`. No remote LLM calls.

### Optional read-only research APIs

Crossref supports free public REST metadata queries. OpenAlex public low-volume exploration is available, while its **production use may require an activated free key and respect for budget/rate limits**; this module intentionally does not handle credentials. **No sandbox live API test was possible.** Both adapters were tested with mock HTTP responses and fixed HTTPS provider allowlists. Bibliographic records are only background, **not proof of customer demand, market novelty, or legal authority**.

```powershell
python -m engine.cli mission --count 1 --research crossref --network --theme "caregiving companion"
python -m engine.cli mission --count 1 --research openalex --network --theme "family wellbeing"
```

These are explicit read-only HTTP requests to the provider, not arbitrary web crawling; failure returns a truthful `UNAVAILABLE`. Do not send private/sensitive user details to research providers.

## Main modules

- `engine/discovery.py`: deterministic offline creative hypotheses, diversifying streams.
- `engine/llm.py`: explicit local Ollama model helper; validated output is still a hypothesis.
- `engine/research.py`: bounded safe HTTPS context search of Crossref/OpenAlex, **not** general market search.
- `engine/evidence.py`: import contextual source notes without promoting them into verified market demand.
- `engine/pipeline.py`: mission orchestration (`DISCOVER → CONTEXT → SKEPTIC → PASSPORT → QA`), exclusive JSON result saving and optional journal receipts.
- `engine/integration.py`: versioned `nox.oie.job.v1` read-only future host interface; denies external actions.
- `engine/studio.py`: actual local HTTP server, catalog, inspector and clickable ideation UI.
- `engine/gates.py`, `workflow.py`, `journal.py`: evidence/consent/pilot veto, stage planning, SQLite hash chain.
- `catalog/ideas_60.json` and `passports/*.md`: original approved V3 concept data retained unchanged.

## Security and limitations

The standalone UI binds to `127.0.0.1`, checks Host, Origin and an unpredictable POST token, and does not expose a remote listener. External read-only research uses fixed HTTPS hosts, strict response-size/time limits, and disables redirects. It has no payment/publishing/clinical/commercial capability. Never put medical data or secrets in ideas/themes sent to providers. Inputs and LLM output are untrusted.

This implementation deliberately cannot self-authorize pilots. An actual future NOX host must verify principal identity, tenant rights, owner consent, independent source and professional reviews, budgets, execution permissions, STOP and rollback. **NOX R1 Function Lock remains unchanged** (approved 729 SourceLock, D02 media, 8 CoreID, 5 PersonaID, WPF/NSIS). The standalone V4 module is not the released NOX EXE, and these source tests do not pass Windows installed E07/G5 QA.

The local SQLite event hash chain is tamper-evident against accidental changes, **not a digitally signed or adversary-resistant audit system**.

## Status

- Offline core & local HTTP interface: source tests PASS.
- Original 60 passports and 12+12 architecture definitions: verified preserved.
- Mock OpenAlex/Crossref integration: source tests PASS; real network integration NOT VERIFIED in this environment.
- Local Ollama integration: response parsing tests PASS with simulated transport; real model NOT RUN.
- Chromium pixel/interactive GUI E2E: NOT VERIFIED here — headless browser blocked by container administrator. HTTP endpoints and UI payload tested.
- Real demand, consented pilots, independently reviewed results, commercial revenue, registered company, fully integrated Windows NOX: **NOT VERIFIED / NOT DONE**.

**The valid “100%” statement is scope-bounded:** implementation of the versioned *standalone read-only foundation* is complete, but the *autonomous business platform* is not deployable without authorization, connectors, real validation, and Windows integration.

## V5 · MEGA-BLOCK 1 (dedicated future branch, not merged into Windows R1)

Standalone **read-only Opportunity Analysis** adds `megablock1` and `megablock1-verify`.
It performs deterministic `DISCOVER → DIVERSIFY → CRITIQUE → PASSPORT → EVIDENCE_GATE → RECEIPT` on the existing approved 60-item catalog and ten existing problem seeds. It writes *three complete hypothesis passports* with named payer/beneficiary, first-five-minute experience, an existing-alternative question, a falsification test, internal catalog similarity (explicitly **not** proof of market novelty), unresolved evidence checks, immutable file output and SHA256 integrity receipts. Passports cannot be promoted to pilots by offline code.

```powershell
python -m engine.cli megablock1 --count 3 --seed 11 --output output/v5_megablock1.json
python -m engine.cli megablock1-verify output/v5_megablock1.json
python -m unittest discover -s tests -q
python -m engine.cli studio --port 8765
```

In the existing standalone studio (a **future preview, not approved HOME/MENU/WORK**) press **«МЕГА-БЛОК 1 · Паспорта + QA»**. The UI presents honest HOLD criteria and no publishing or paid actions. Read-only `nox.oie.job.v1` host contract adds `megablock1.preview` without changing existing action names.

**Release gate:** offline source and local HTTP tests PASS; there is no real market research, external independent customer validation, verified investment, deployment into Windows NOX, or accepted live UI QA. After owner-approved integration, use actual market sources and authenticated grants; never infer approval from submitted JSON. Existing V4 source/tests and 60 idea passports are retained.
