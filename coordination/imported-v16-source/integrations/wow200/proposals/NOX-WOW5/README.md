# NOX WOW5 · isolated optional UI package

STATUS: SOURCE CANDIDATE ONLY. No application host or Windows EXE integration claimed.

Adds five complementary micro-interactions to the approved D02:
- Evidence Stack: show actual authenticated RAG citations and hashes.
- Mission Trail: show up to six fresh, ordered events.v3.
- Cinema Focus: scoped focus visual state without replacing HOME.
- Ghost Session: optional storage of selected CoreID and focus boolean only.
- Error Decoder: local safe explanations and copied code/RunID via host callback.

Already existing WOW2 by #5 covers orbits, GPU status and Ctrl+K: do not recreate it.

No dependencies, networking, new model, API, service, timers or background work. CSS/JS source only. Never display fabricated progress, citations, GPU telemetry, or training completion.

Integration owners: #1 UI assets and D02; #5 existing events; #6 only shared host bridge/serial merge; #7 independent native Windows acceptance.

Usage in approved WebView2 host (existing mount slot only):

  load wow-core.js, wow-ui.js and wow.css
  createNoxWow5({root: approvedMountElement,
    coreIds: existingEightCoreIds, storage: optionalApprovedViewStore,
    copyText: approvedClipboardFunction,
    onPanelSelected: approvedExistingMenuRoute,
    onFocusChange: approvedExistingFocusHandler})

Host calls setCitations with ACL-verified RAG result fields: file_name, source_id, chunk_sha256, source_sha256.
Host calls acceptEvent only with host-confirmed schema NOX-INSTALLER-EVENT-v3 event payloads.
Host calls setError with safe error code and RunID. Do not pass exception messages, raw paths or secrets.
All displayed text uses DOM textContent. Out-of-order and stale events are rejected. Optional persisted view data expires within 24h.
Feature flag off by default until #1/#6 approve installation; no automatic host action or restored training.
Acceptance gate: keyboard access, 320px, reduced-motion, no ACL leaks, no regressions, source SHA receipts and verified SourceLock.
Estimated extra implementation effort target <=2 percent of agreed baseline, not measured or guaranteed.
