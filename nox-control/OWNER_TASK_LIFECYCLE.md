# Owner task lifecycle and proactive reports

## Required behavior

An already authorized task proceeds through native admission, execution and
verification without asking the owner to approve the same operation again.
The existing dispatcher continues after a browser disconnect. Closing a tab
does not cancel a task; owner STOP flags and native resource admission remain
authoritative.

Every claimed task receives a durable preflight record in the existing
`memory/dispatcher_mentor/events.jsonl`. It records recall of prior technical
errors and verified decisions, shared S03 recall availability, the reviewed
native plan and parallel branch accounting, senior consultation availability,
and the status of internet research. Retrieved text and model advice are data,
never executable instructions. New optimization candidates require bounded
evaluation; the lifecycle does not execute generated shell or Python.

The existing pool has six global worker slots. A decomposable, reviewed plan
uses three to six queued branches under the current NORMAL/TASK_BOOST policy
and observed resource budget. Planned branches, admitted width, currently
running claims and queued children are separate quantities. Dependencies and
exclusive GPU/model/disk writer locks can reduce simultaneous work below the
plan width. A child cannot recursively create another worker tree. An atomic
native operation records why it is not decomposed.

Mode targets remain three and six. The planner samples only bounded cgroup
memory and CPU-pressure files, with a three-second cache. New branch admission
is reduced at 85% memory usage or 20% CPU pressure, and paused at 95% memory
usage; high CPU pressure can reduce new concurrency to one. Existing claims
continue under their original owner/resource gates. Planned branch count does
not change. Missing load observations use a conservative maximum of three.

## Source interfaces

- `owner_task_plans.bind_dispatcher(namespace)` supplies the reviewed routing
  templates and changes accepted-only owner orders into real native task IDs
  or explicit `NEEDS_PLAN`. Its `plan_metadata(task, state)` supplies bounded
  accounting. Its optional `verify_success(task, evidence)` must independently
  verify any additional result types.
- `owner_task_lifecycle.patch_dispatcher(source, expected_sha256, source_pins)`
  adds one binder before the existing main entry. It requires the exact current
  dispatcher hash, including existing BOOST/media/plan bindings. The native
  claim function and six-worker loop remain in place.
- `source_pins` pins the installed `owner_mentor` and `owner_event_outbox` files,
  plus present `owner_task_plans`, `owner_media_runtime` and
  `owner_senior_gateway` modules. Import names must already be bound in the
  native namespace. Deployment must verify the lifecycle file itself as well.
- `owner_senior_gateway.consult_plan(context, deadline_seconds=2.0)` receives
  only technical handler/policy identifiers, evidence digests, bounded prior
  error categories and counts. No raw private S03 items, owner prompts, file
  contents, credentials or shell commands are sent. Consultation is cached per
  distinct plan and evidence group; child attempts link that result. Missing
  configuration is `MISSING_SENIOR_GATEWAY`, and absent verified research is
  reported separately. A pending consultation is not a completed consultation.
  V2 also provides a fixed task intent and observed resource/timing measurements
  when available, plus allowlisted public error codes. One verified provider
  can advise; a council is reported only after two or more actual replies.
  Proposals include a change, expected effect, evaluation and rollback. They
  remain local candidates; neither the gateway nor lifecycle executes them.

Shared S03 recall uses the existing native `s03_memory.recall` API in a
single bounded child process only after the inspected native source hash is
configured in `config/owner_task_lifecycle.json` with schema
`NOX_OWNER_TASK_LIFECYCLE_V1` and `s03_source_sha256`. The inspected implementation
uses FTS plus pinned memory items and optional local CPU reranking. Its reported
retrieval kind is `LEXICAL_WITH_PINS`; this helper does not claim BGE semantic
retrieval. A bounded k=16 avoids having every lexical match hidden behind the
native pinned prefix; at most eight hashed references and the actual lexical
match count leave the child. No new GPU model is loaded. It does not call the
synchronous proxy recall route on the chat event loop. Missing pins, busy
admission and timeouts remain explicit.

## Verification and learning

The lifecycle captures the result of the existing mentor's independent
verification and training/holdout/quarantine decision. It never treats a
handler's `True`, an accepted order, a ready engine or a GPU allocation as proof
of finished work. Completion reports are written only after the persisted
native queue state matches the task's exact claim nonce and final status.

Component reports retain their original scope and blockers. A health check does
not prove an end-to-end chat; GGUF header verification does not prove model
quality; adapter receipt metadata does not prove a restore or model promotion.
Media completion additionally requires the native decoded-output receipt and
fresh scoped file size/SHA verification. Generation, GPU release and training
resume remain separate claims. Cancelled media is not a completed generation.

Failure reports link the actual observed error and mentor resolution state.
A verified service restart still leaves the original task awaiting a new
verified run. Unverified results remain quarantined. Reporting failure never
causes task replay or silently changes its status.

## Durable outbox and UI contract

`owner_event_outbox.register_owner_events(app, trusted)` registers only
`GET /api/ui/events`, using the existing `_session_ok` and `_unauthorized`
callbacks. Authentication is checked before parsing or reading private files.
There is no Telegram, email, external push or separate reporting daemon.

The response schema is `NOX_OWNER_EVENTS_V1`, with `events`, `next_cursor`,
`latest_cursor`, `has_more` and `initial_snapshot`. Omitted cursor returns at
most the latest 20 events. An explicit nonnegative cursor replays later events
in increasing order, with a maximum page size of 50. The UI can save its cursor
locally and render fixed text cards using text nodes, not HTML from task data.
It should identify cards as operational reports and preserve ordinary chat
history separately.

The response also contains `availability`, based on a bounded current local
model health request, a read-only S03 schema probe and fresh six-worker status.
Its `awake`, `busy`, `drowsy`, `offline` and `unknown` states describe observed
service availability. A held trainer does not make a healthy core unavailable.
Training HOLD/pause reasons remain separate and explicit. Observations are
cached for five seconds and do not create idle event cards or stop any service.
Core chat, shared memory, dispatcher and owner reports remain continuously
available; background learning yields at checkpoints under native admission.

Immutable mode-0600 event files live under `state/owner_events/events`.
Deduplication, cooldown indices and cursor state are private. Existing event
files are retained; the helper does not delete history. Interrupted commits
recover their sequence/deduplication index. The existing dispatcher status
callback drains only newly appended report records from the mentor journal, so
temporary UI or outbox failure can be replayed without repeating work. Initial
activation does not replay historic checks as newly completed operations.

Only fixed projected evidence and titles enter owner cards. Raw prompts,
credentials, arbitrary tool output, model advice and private memory text do not.
Repeated unchanged proof is deduplicated. Repeated error reports have a
five-minute cooldown. Progress requires an actual changed measurement and a
one-minute cooldown; bytes require at least 256 MiB, optimizer steps at least
five, and subsequent incomplete progress at least five percent of the total.
The currently attached media progress callback reports a persisted accepted
generation prompt once; it does not invent a completion percentage. Idle polls
and continuous-duty placeholders produce no owner cards.

## Deployment evidence still required

These source modules do not deploy themselves. A native installer must pin the
current dispatcher and helper sources, back them up, install the modules,
preserve STOP/mode policy and restart only the exact owned dispatcher/proxy
services. Native acceptance must check six unique worker IDs, a real authorized
task with preflight and proof, authenticated cursor replay, anonymous rejection,
continued execution after disconnect, and no additional GPU model process.
Unavailable senior credentials or research capability must remain visible.

## Bounded native acceptance task

After the native source-pinned installation, enqueue this shape in the existing
queue under its owner maintenance/queue lock. Give the task a fresh ID tied to
the actual owner request; do not reset an old task or replay an old claim.

```json
{
  "id": "owner.autonomy.audit.REQUEST_ID",
  "handler": "owner_order",
  "class": "owner_order",
  "priority": 0,
  "status": "pending",
  "deps": [],
  "locks": [],
  "retries": 0,
  "max_retries": 1,
  "params": {
    "plan": {"schema": "NOX_OWNER_PLAN_REQUEST_V1", "intent": "audit"}
  }
}
```

It must create six unique native child task IDs, execute the six bounded
component checks, preserve their scopes/blockers, and join only after all six
claim-bound receipts verify. Acceptance is six child reports plus one verified
join, with the original preflight and learning records, cursor replay and no
duplicate task execution. NORMAL may admit three at a time; TASK_BOOST may
admit six when load permits. This audit does not imply training or generation
has passed its own acceptance.

## Explicit remaining work

`owner_task_lifecycle.json` records the current coverage. The following are
not implemented by this release and must not be reported as complete:

- Standalone Supervisor worms that do not execute through the dispatcher do
  not yet receive this full lifecycle. Their existing STOP/BOOST/service guards
  remain intact; their source-specific admission adapters need separate review.
- The legacy mentor failure path still uses its existing allowlisted repair
  logic and older senior-discovery callback. Bridging that path to the shared
  gateway requires a typed, independently verified repair adapter. A missing
  senior configuration must not be described as an applied correction.
- Training continuation and requested download mutation nodes expose
  `WAIT_TRAINING_ADMISSION` and `WAIT_DOWNLOAD_ADMISSION`. They do not call the
  obsolete service-start shortcuts or remove HOLD. Dedicated verified native
  actions must be attached before these requests can finish.
- Senior recommendations are available for local evaluation, but automatic
  experiment selection, holdout comparison, safe promotion and rollback are
  not implemented here. Only already verified native task examples enter the
  existing train/holdout learning queues; guesses and failures stay quarantined.
- Calling an API model is not web research. Verified internet research needs
  its own source-attributed adapter; current reports say it was not performed.
