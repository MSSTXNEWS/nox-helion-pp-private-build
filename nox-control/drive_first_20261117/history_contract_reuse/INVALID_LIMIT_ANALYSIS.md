# Observed history error: INVALID_LIMIT

The root-dispatched read-only reconciliation returned HTTP422, application/json,25bytes, SHA256 `c72ee0295be63b2e06c1de1ec0b5c22e9dd197c48172348d9a6317799dc73a61`. This exactly matches the saved compact JSON error `INVALID_LIMIT`. Authentication and all three UI assets passed. Model requests and created dialogs remained0. This proves the response classification, not its causal source.

The frozen client constructs exactly `GET /api/ui/memory/dialogs/history?dialog_id=5ce69137da0a4c42a0387917c8567d52&limit=2`. Its request guard only allows that shape, and `urllib.request.Request(BASE + path)` does not add or re-encode parameters. The single local capture fixture passed: one request object, GET, no body, exact own ID, and `limit=['2']`; no network was used.

The saved bridge candidate parses `max(1,min(int(request.query_params.get('limit','100')),100))`. Both literal2 and the missing-parameter default100 are valid. Simple loss of the entire query would therefore not produce INVALID_LIMIT in that candidate. However, its complete SHA3cd548… differs from native0cff…, so this does not prove what the live parser or wrapper received.

## Can the exact O1 inverse recover the native preimage?

No, using the available source. The complete O1 transform pins a47831-byte0cff… preimage and a49331-byteffdefe48… postimage. The available saved candidate is37613-byte3cd548… and matches neither input. The guarded inverse requires the complete exact postimage. The complete601-line unified diff and transform omit the unchanged history handler and cannot reconstruct those missing native bytes. Applying snippets to a different candidate or accepting its resulting hash without matching0cff… would manufacture evidence.

## Next ready

Use the already existing authenticated O1/O2 source handoff for exact bridge0cff… and wrapper0a0165…. Inspect the history limit parser/helper and URL query construction, then make only the supported source fix. No expected pin or canary code changed, no new native probe/export/request was added, and no new generation is needed. Full identities and captured-request evidence are in INVALID_LIMIT_ANALYSIS.json.

## Exact source handoff resolves the cause

Root/O0 subsequently verified shared journal marker `NOX_A1_RECONCILE_INVALID_LIMIT_20261117`: wrapper SHA0a0165… constructs `target = path + (f"?{url.query}" if url.query else "")`. In httpx0.28.1, `url.query` is bytes. Interpolation introduces the Python bytes representation, so the downstream key becomes `b'dialog_id` and limit becomes `2'`. The exact bridge0cff… integer parser raises ValueError and returns the observed INVALID_LIMIT.

One independent local reproduction on actual httpx0.28.1 confirmed that behavior and that ASCII decoding preserves ordinary dialog_id/limit parameters. It used no HTTP/native call. QUERY_TARGET_REPRODUCTION.json separates parent-verified source identity from this independent runtime-library reproduction. O0 owns the narrow source fix; no native postimage or successful history acceptance is claimed yet. The earlier UNKNOWN findings above describe the information available before this source handoff.
