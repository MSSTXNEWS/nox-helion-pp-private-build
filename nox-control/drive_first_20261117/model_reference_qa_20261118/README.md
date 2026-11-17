# One changed-path model-reference QA

This package is the follow-up to the **actual successful** proxy installation:

- Request `6963969126`, source `5da7849bffc2b590201bb1917840b5a2b39ca2a7`.
- Native run `44198936370`, job `134447651037`.
- Proxy PID `3648425`, start ticks `175058217`.
- Model service, counters, queue and S03 were not restarted or reset by that installation.

The earlier completed canary is not repeated. This request exercises the newly installed model-reference branch and menu overlay.

## Exact change under test

The sole model question is `Какая модель в твоей основе сейчас?`. Its text must stay exact: the installed matcher accepts the entire short standalone question. The new random nonce belongs only to `request_id` and the private durable journal. The body contains the existing own QA dialog `12092579cf5144419cfa4fadc2e3a03b`, empty client history and `max_tokens=256`. The server reads the committed conversation itself.

Before sending, the QA verifies the previous two messages, their exchange `48140046c4684fe5`, and the known canonical M1 digest `b7513f8177f4ec65b9dd65f248097108bf4e2a2cb364e407e3cb191f98e4bdec`. Their text and title never enter the report. After the new terminal SSE frame, the QA requires exactly four own messages: the original two rows unchanged, followed by the exact new question and complete new answer. It independently verifies the new canonical full-turn M1 record, its digest and exchange ID, and compares the authenticated HTTP history to SQLite.

The model's answer is not invented or replaced by a script. Only the new synthetic answer, at most 4096 UTF-8 bytes, can appear in the private receipt and private owner-run output. Root explicitly authorized this bounded text for semantic review. No new encryption keys or seal are needed. Old personal history and credentials stay private.

## Single-send and scope

The distinct reservation directory `/root/nox/state/owner_model_reference_acceptance_20261118` is created with exclusive semantics and mode 0700. The code never deletes, adopts or reopens an existing reservation. A durable 0600 `model_post_intent.json` is verified and synced before the one socket attempt. A timeout or lost acknowledgement consumes that attempt permanently. There is no retry loop, dialog creation, service mutation, source edit, counter reset or external HTTP destination.

The existing native authentication path is derived from pinned source by the reviewed AST-only helper. Its credential is used for the existing loopback login and is not exported. The inherited process helper privately selects Supervisor identity and S03_DB from bounded process metadata; it never exports the environment.

All five installed files are checked against the actual installation, including the recorded source and new-artifact inodes. The installed receipt must bind the exact request, source and reloaded proxy lifetime. The unchanged common, agent-loop, S03 and OneHost-forwarder source pins are checked too. These observations do not directly inspect the Python interpreter's loaded module memory.

Root coordinates the quiet window and the existing maintenance lease. Fresh owner priority and idle model slots are observed twice. The lease serializes cooperating maintenance writers; it is not an atomic exclusion of a new user message. Old ambiguous global counters are not reset or promoted into an admission proof.

## Bounded requests and acceptance

The UI client allows at most one login POST, one chat POST, two own-history GETs and one menu JavaScript GET, all on `127.0.0.1:18775`. The report explicitly counts `owner_chat_posts`; its legacy `model_posts` field has the same owner-UI scope. Backend model HTTP posts are **not directly observed**. Separately, the reused owner-idle helper permits up to two slot GETs on `127.0.0.1:8098`. The menu response must match the installed served overlay hash and 43021-byte length. This verifies the served bytes; it does not claim a visual browser click test.

The reused SSE parser requires context, matching dialog metadata, non-placeholder content, a successful terminal frame with the full-frame S03 digest, and normal EOF. It keeps its existing 90-second cooperative stream bound. An outer 120-second SIGALRM covers the entire native QA; the socket timeout is 20 seconds. The entry refuses to replace a pre-existing timer. Maximum receipt size is 65536 bytes. Generation token count remains unknown; SSE token frames are transport events.

Successful completion is named `TRANSPORT_AND_PERSISTENCE_COMPLETE_SEMANTIC_REVIEW_PENDING`. The script deliberately leaves `accepted=false`. Root must read the actual new answer and judge whether it accurately describes the observed model reference without claiming verified weight contents, architecture, consciousness or training. A basename-presence flag is evidence for review, not automatic semantic acceptance.

Completion through the newly reloaded process and pinned source supports an **inference** that the small system-prefix path fit for this question. The helper import and actual model input are not directly traced. The report names this `system_prefix_bound_path_completion_inferred` and explicitly sets `actual_model_input_trace_observed=false`. The script does not claim the exact prefix byte count, exact input token count, or a mathematically exact context window. No completion inference is reported before the native answer is obtained.

## Local verification and publication

Five distinct offline checks passed: existing history and M1 preservation, exact matcher/nonce placement, lost-acknowledgement single-send fencing and forbidden create, actual install generation binding, and full synthetic SSE-to-SQLite orchestration. The first orchestration attempt exposed only a fixture UID error: mocking native root also changed real TempFS ownership checks. The fixture now waives only the native entry-context check while keeping real filesystem UIDs. Its one targeted rerun passed; the four already-passing tests were not repeated.

`PEER_INPUT_FREEZE.json` pins code and fixtures. `build_payload.py` creates a deterministic four-module wrapper, compiles it and writes `BUILD_MANIFEST.json`; it never executes native code. Root alone publishes and invokes the unchanged owner repair route after independent review. On any uncertain native result, inspect the durable journal and actual run receipt. Do not resend the same question or reset its reservation.
