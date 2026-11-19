# Continuous source work through the existing native queue

The initial reviewed package is `mission_pack_v1/batch.json`. Its manifest is
`ae6181de5b6970ab4b572aa0c5a2e9bc24632668dd31e6a15327de5f8bf507d4`.
The package contains three actual source corrections, bound to existing original
parents 3A03, 4A02 and 3B05. It adds no source path or trusted test. All three
parents require native evidence beyond this source work; their acceptance remains
false. The denominator remains 295 original tasks.

## Queue integration

The native config points to one immutable reviewed manifest:

```json
{
  "systemic_relay": {
    "path": "/root/nox/state/dispatcher/project_executor/package/relay/ae6181de5b6970ab4b572aa0c5a2e9bc24632668dd31e6a15327de5f8bf507d4.json",
    "sha256": "ae6181de5b6970ab4b572aa0c5a2e9bc24632668dd31e6a15327de5f8bf507d4"
  }
}
```

`runtime/owner_systemic_refill.py` is a pure selector. The dispatcher reads the
manifest by its raw SHA, obtains requested source files through the existing
executor tree, and calls:

```python
validate_manifest(manifest)
source_requests(manifest)  # root_id -> sorted relative paths
select_next(manifest, existing_tasks, current_source_pins, capacity)
validate_binding(ancestral_manifest, binding, reviewed_row, exact_contract)
```

`capacity` contains `slots_available` (0–3), `now`, the current callback SHA,
the verified raw `manifest_sha256`, and optional `reserved_sources` rows with
`root_id` and `path`. These reservations include unsettled older native work.
The authoritative resource, owner, STOP, source, claim and S03 checks remain in
the existing execution path.

The selector returns `rows`, content-addressed `contracts`, `bindings`, `state`,
`fingerprint`, `outcomes`, `deferred` and a possible `refill_request`. It does not
write a queue, call a model, run a test or accept an original task. Admitted
mission revisions are not replayed after success or failure. Source drift
requires a newly reviewed proposal; it never silently rebases a contract.

Durable task metadata uses `NOX_SYSTEMIC_RELAY_TASK_V1`, the pinned manifest SHA,
the complete reviewed row, and its binding. The dispatcher verifies the exact
ancestral manifest on restart. A successful task is validated against that
historical contract, not against its now-obsolete source preimage.

## Initial concrete work

| Mission | Current source defect | Existing immutable verification | Focus bytes |
| --- | --- | --- | ---: |
| `cache_fill_ttl` | The fill expiry uses the timestamp sampled before potentially blocking recall and revision callbacks. | 16 existing cache tests | 2549 |
| `forge_read_budget` | The split reader has a line limit but no total byte budget; excessive declared rows are checked only after EOF. | 39 existing split/coverage tests | 857 |
| `skill_journal_budget` | Journal iteration and marker reads can consume growing input after their initial size checks. | 10 existing JSON/ancestor tests | 1805 |

The contract shapes, exact source snapshots and focus anchors were checked by
the existing planner validator during package construction. No new unit test was
added and no unit test was run for this relay package construction. The native
executor will run the already pinned immutable verifiers against each actual
candidate. These older tests provide regression coverage; the requested new
behavior also needs review of the resulting source diff.

The common experience record points to the independently observed failed C02
planner receipt
`399e3dc5f153ac8832dfb41d74fead6b30f76f2be5257820af39a6e86dea7599`:
10 reads, no patch, no test attempt, and a repeated-action stop. This is measured
feedback for avoiding the same stalled approach, not permission or a success
claim.

## Producing the next batch

An external existing B4/D3 producer consumes the latest
`NOX_SYSTEMIC_REFILL_REQUEST_V1` from the normal dispatcher status. The request
has a deterministic ID derived from the manifest, current source pins, bounded
task outcomes and current states for indexed original TaskIDs. Clock-only ticks
do not create fresh requests. B4/D3
schedule changes are outside this package.

The producer must read the actual predecessor manifest, current source census,
existing catalog/receipts and the relevant canonical backlog. It should research
the next concrete defect when useful and record its primary source. It may then
prepare at most three grounded proposals within already allowed existing source
paths and existing immutable verifier paths. Research objectives alone are not
executable missions. An unchanged failed approach requires a materially changed
reviewed correction; renaming work is not progress.

Each proposal mission carries the manifest fields shown in
`mission_pack_v1/initial_proposals.json`, with `context_paths` instead of context
hashes. It also includes the actual observed source SHA and a description of the
defect, expected behavior and verification limits. The compiler fills hashes
from the exact census, verifies the original parent specification against the
295-task registry, and freezes the contract. It never fetches mutable source or
chooses permissions itself.

Inputs for a successor build:

| Input | Required content |
| --- | --- |
| Previous manifest | Exact canonical bytes and their known raw SHA |
| Proposal | `schema=NOX_SYSTEMIC_GROUNDED_PROPOSALS_V1`, predecessor SHA, refill `request_id`, 1–3 grounded missions, optional updated research topics |
| Census | `schema=NOX_SYSTEMIC_SOURCE_CENSUS_V1`, `roots[root_id][path]=sha256`, full native `observed_files_sha256` |
| Refill request | Exact latest `NOX_SYSTEMIC_REFILL_REQUEST_V1` bytes emitted by `select_next`; its request ID is recomputed from the pinned predecessor, source pins and bounded outcomes |
| Registry | The existing `all295_execution_disposition.json` with all original specs and source-registry pins |
| Review | `schema=NOX_SYSTEMIC_TASKPACK_REVIEW_V1`, `review_origin=OWNER_REVIEWED`, exact proposal/census/refill-request/predecessor hashes, settled-claims readback, immutable-verifier hash and `original_task_accepted=false` |
| Publish checkpoint | Exact current config/source hashes, director/worker/protected process identities, current manifest SHA and publisher template SHA |

The review file documents the exact material that was reviewed. It does not
replace the native owner's existing authorization and publication checks.
Each proposal also pins `parent_spec_sha256`. Only an original ID whose current
disposition remains `UNBOUND_PENDING_REAL_EXECUTION_PLAN` can be selected. The
producer rejects IDs already represented in the predecessor manifest or current
task outcomes, duplicate original IDs within a batch, stale refill requests,
and a changed test-module pin. The local package and publish request are not a
native queue write; the existing publisher still enforces current owner lease,
STOP, resource/process identity, immutable verifier, predecessor and config CAS,
and publish readback.

## Fail-closed eligibility audit

`owner_systemic_refill_producer.py` is a read-only diagnostic over the exact
predecessor manifest, refill request, proposal, source census, 295-task registry,
review receipt and original source documents. It emits one eligibility row per
original TaskID, a predicate diff for each proposed mission, and a short list of
missing source/verifier inputs. It cannot repair the proposal or create queue
records, status, acceptance, contracts or native jobs.

The checked snapshot in
`next_pack_44368502183/eligibility_predicate_audit.json` remains
`HOLD_NO_REVIEWED_TASKPACK`: its stored refill request does not contain the
required SHA-bound `original_task_states`, its owner review does not bind the
current input hashes, and all three stored proposal missions fail exact parent
acceptance and evidence binding. I-39, I-48 and I-50 are structural source
candidates only. The audit records their exact available source evidence and
actionable gaps; none is an executable mission, native job or accepted original
task.

For source tasks with registered acceptance, criteria fragments must cover the
entire exact acceptance text in order, without gaps. Each criterion must name a
module in the immutable verification set, pinned in the source context and
excluded from edits. This establishes traceable mapping; OWNER_REVIEWED must
still verify that the pinned test code proves the full behavior. Before publish,
the native publisher independently re-reads the original registry and checks
that embedded acceptance matches the canonical source spec. It also compares
the request's original-task-state snapshot to the current native queue at the
final CAS check. An admitted mission whose source pin drifted remains
`ALREADY_ADMITTED_NO_REPLAY`; it produces a revision-specific review candidate
and requires a new OWNER_REVIEWED revision.

```bash
python -B nox-control/systemic_relay_20261118/owner_systemic_taskpack.py \
  --previous-manifest CURRENT_MANIFEST.json \
  --previous-sha256 CURRENT_MANIFEST_SHA256 \
  --proposal grounded_proposals.json \
  --source-census current_source_census.json \
  --refill-request current_refill_request.json \
  --registry nox-control/complete_executor_20261118/evidence/all295_execution_disposition.json \
  --review exact_taskpack_review.json \
  --output NEXT_PACKAGE_DIRECTORY \
  --publisher-checkpoint current_publish_checkpoint.json \
  --publisher-template nox-control/systemic_relay_20261118/owner_systemic_relay_publish.py \
  --transaction-helper nox-control/continuous_executor_20261118/assets/continuous_transaction_helpers.py
```

The three publisher options are supplied together. The checkpoint uses
`schema=NOX_SYSTEMIC_NATIVE_PUBLISH_CHECKPOINT_V1` and these keys:
`expected_config_sha256`, `previous_manifest_sha256`,
`expected_source_files_sha256`, `expected_director`, `expected_workers`,
`protected_processes`, `publisher_template_sha256`.
Director and worker identities contain numeric `pid` and `start_ticks`.
There are exactly three workers; protected processes are `chat`, `proxy`, `web`.
The existing transaction helper is pinned to
`8470a6720ca69864bbc4e6e630a1f853344839af424d3829dcdf1774442db609`.

The CLI writes canonical `relay/<sha>.json`, `contracts/<sha>.json`, the publish
request and, with the publisher inputs, exact spec, bundle and executable native
entry files plus their hashes. It performs no upload or native execution. The
existing owner review/publication flow uses that concrete entry. Publication
waits for active claims to settle, checks the original owner lease, process
identities, STOP state, full source census and exact predecessor config, then
changes only the immutable manifest pointer. A subsequent native tick performs
normal admission. The existing tasks, claims, source roots, model and runtime
pins are preserved by the publisher.

## Evidence and continuation

### Reuse a reviewed solution when model iteration stalls

The first native cache attempt stopped with `PLANNER_REPEATED_ACTION_NO_PROGRESS`.
Independent source review also found incomplete new behavior in the first Forge
and skill patches despite their existing regression checks passing. The exact
receipts are pinned in `reviewed_recovery/publish_spec.json`.

`build_reviewed_recovery.py` freezes the three corrected source candidates and
their unchanged existing verifiers against a settled native readback.
`owner_systemic_reviewed_publish.py` adds their immutable plans to the existing
catalog without restarting any worker. The native executor then performs its
normal verification, source CAS, and S03 integration. No local model regeneration
is needed for an already reviewed patch. Prior attempts remain intact.
This is a separate, explicit `OWNER_REVIEWED` origin, not a claim that the native
model generated the recovery or that the original tasks were accepted.

`outcomes` exports bounded operational scalar fields and hashes. Reported test
counts, postimages or `done` are labelled as queue evidence requiring receipt and
postimage readback. A useful source completion requires the actual executor
integration receipt, immutable verifier result and observed current postimage.
It does not by itself accept the original task or establish benchmark quality.

The next producer should use verified failures and successes to update compact
host-curated lessons, then choose a new grounded task. When no eligible reviewed
work exists, the status remains `REFILL_REQUIRED` with actionable research
objectives instead of pretending that all original work is complete. Continuous
progress depends on the external producer consuming those requests and publishing
new reviewed packages; three initial missions alone do not prove that loop.

## Canonical context used

The initial intent links and exact Google Docs revisions are inside the
manifest. They refer to the
[NOX development program](https://docs.google.com/document/d/12SIMZNChehhT2ZIN61H6UdZIcEej2ZAD4GAqt9WjMW0/edit),
[main catalog](https://docs.google.com/document/d/1bP1sQLOA1TQrg6plLmZlbjGeSbd1cuaDqirjyyzbiwk/edit),
[shared journal](https://docs.google.com/document/d/1H5_4xk1a7xZxaGNMODfy6MR3-Zi5gkGWH-4aUUwtLtw/edit)
and [canonical Notion project memory](https://app.notion.com/p/40cacc184a9f8170bcabca204c7d4c33).
They support one PRIME/S03/dispatcher, priority for server resources and memory,
and an evidence journal separating intent, implementation, integration and
acceptance. Historical observations in those documents are not current native
state or new operating authority. Notion reads used instructions version 0.0.6.
