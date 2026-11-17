# Selected-backend context counter and protected trimming

Status: working isolated source, seven author tests and one additional independent test passed; independent source review PASS. Nothing in this package has been installed or invoked on the native server. The immediate model-reference QA continues separately.

## Concrete defect and change

The actual installed proxy is `chat_proxy.py` SHA `30207a85eed6c87df4a6ee4dd8614442a62622eefacac7fae822b23ad385b343`. Its old `_count_msg_tokens` returns zero when a successful HTTP response omits `prompt` or `tokens`. Its exception fallback returns a character estimate as though it were a measured token count. The old trim loop can invoke seven template/tokenizer pairs, and it counts against the configured primary backend even when completion has already selected fallback 8085.

The source transform changes only `_count_msg_tokens`, `_trim_ctx` and their call site inside `_proxy_completion`. The candidate proxy SHA is `1b468ebda8cdae0dce3fd1b9df4f7def64c56d708796b05e5bd7f88fbc76af62`. The new module is `/root/nox/scripts/owner_context_budget.py`, approximately 16 KB of source. The installed narrow identity-question branch keeps its original builder, without importing the new helper or making tokenizer HTTP calls.

The selected completion URL is passed explicitly into the generic path. Helpers accept only the existing loopback 8098/8085 completion route shapes; unsupported routes produce an unknown result and conservative local trimming, not a request to the primary backend. Slot limits are read from that same selected route, using the smallest valid observed slot context because this helper does not establish which slot will be assigned.

## Measurement and cache semantics

`Count.tokens` is an integer only after valid template and tokenizer responses. Missing fields, malformed token IDs, a nonempty prompt with an empty token list, timeouts and HTTP failures give `tokens=None` with a fixed reason. An actual empty template for an empty message list can legitimately measure zero. No character estimate is returned as a token measurement.

The cache lives only within one request. Its key is the selected backend URL, canonical message fingerprint and the hash of the actually rendered prompt. The template endpoint is called for each count round; a changed rendered template invalidates reuse. The helper does not observe an atomic backend-process/tokenizer identity, so this cache never becomes a persistent cache based on a model alias.

There are at most two count rounds, each with one template request and at most one tokenize request. Together with one slots request, the helper permits at most five HTTP attempts. This replaces the old worst case of fourteen template/tokenizer attempts plus one slots request. It does not describe all other work performed by the proxy or claim an end-to-end speedup measured on the server.

The request-local time budget is 1.2 seconds, checked between operations and on each raw response chunk, with socket phase timeouts bounded at 0.35 seconds and smaller connect/write/pool limits. This is a cooperative deadline with bounded blocking phases, not a mathematically exact hard wall timer. The maximum decoded JSON response is 512 KB, maximum rendered prompt is 256 KB, token lists are bounded, and the two-entry cache stores fingerprints/counts rather than conversation bodies. One short-lived HTTP client is closed after the helper finishes.

## Instruction and history preservation

The caller passes the latest original question separately from generated augmentation. The original question is never shortened, including text after literal delimiters. Stable system instructions through the known contract are never truncated. If a system-tail boundary is not uniquely recognizable, the whole system message is protected.

Older history is removed only in complete user-led groups, carrying their assistant/tool call and result messages together. Generated variable context and current augmentation can be removed when necessary; the authoritative original question remains. Source message dictionaries are not mutated. Unsupported message shapes are preserved unchanged and are explicitly unmeasured.

A valid first measurement can retain more history than the old character-only pre-trim. If the candidate is too large, one bulk reduction and at most one final measurement are made. If another reduction to the protected minimum is needed after the second round, its old candidate's token count is not assigned to the changed payload: final tokens remain unknown. If a valid measurement of the protected minimum itself exceeds the observed policy allowance, the proxy returns a specific 413 size response rather than silently cutting the question or instructions.

If measurement is unavailable, the helper uses the existing policy's conservative local character budget and keeps all protected text. It does not add a mandatory tokenizer-availability gate to ordinary chat. When the slot context is unavailable, the fallback is the legacy 2048-character floor for optional context; protected text can exceed that heuristic and remains intact. Older optional context can be dropped in this degraded case. No new context-window capacity is claimed.

Output reserve is at least 512 tokens or the larger explicit requested amount. The 1300-token tools reserve is the existing policy, not a fresh measurement. Counts cover messages at trim time; later tool schemas and enrichments are not directly counted. `exact_final_context_fit` therefore remains false, even when rendered messages fit the stated policy allowance.

## Verification and installation boundary

Seven targeted offline tests passed. They reproduce the actual old false-zero function through an AST-isolated call, then verify strict unknown results, valid real zero, selected fallback routing, template-bound cache invalidation, two-round and time limits, preservation of a long original question containing delimiters, whole tool groups, unavailable-tokenizer fallback, and a measured protected-only overflow. The source test checks the exact forward/inverse transform and confirms the identity branch gains no new helper dependency. After adding the canonical-input fingerprint to the cache key, only the affected cache test was repeated.

`PEER_INPUT_FREEZE.json` pins this source and its tests. The full proxy candidate remains a private local comparison input and is excluded from any publication list. A future install needs an absent-only helper write, an exact proxy CAS, original backup, source/readback checks and the existing root-coordinated proxy lifecycle. The model, queue and S03 must not be restarted or reset. Any package that pins the old proxy revision must be updated only after the actual accepted install receipt. This source package alone does not authorize or claim that installation.
