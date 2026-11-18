# Context counter and model-reference wording: one proxy update

State: source frozen; independent composition review pending. No native action was performed by this package's author.

## Exact three-file change

| Native target | Existing state | Candidate |
|---|---|---|
| `/root/nox/scripts/chat_proxy.py` | `30207a85…`, 103831 bytes | `1b468ebd…`, 100684 bytes |
| `/root/nox/scripts/owner_model_reference_binding.py` | `b9f4addc…`, 18265 bytes | `78704531…`, 19122 bytes |
| `/root/nox/scripts/owner_context_budget.py` | Must be absent | `b405e628…`, 15511 bytes; private mode 0600 |

The proxy change fixes malformed successful tokenizer responses being treated as a known zero, binds counting to the selected backend, and bounds request-local tokenizer work. The existing identity-question path still avoids that counting work. The model-reference change gives the model separate verified and unverified wording, without exposing the internal evidence flags. It preserves the actual process and socket checks. These changes do not increase the model's claimed context window.

The complete six-module repair payload is `public_payload/nox-control/owner_resonance_canary_v3_20261117.py`, SHA-256 `0ebcf254853bc48a471b88ee7ca8caf256e5f20a63af438a9f729a8d3f1cda27`, 39959 bytes. It uses the existing owner repair route and unchanged successful lifecycle `dff6a384…`. The transaction's mutation and owned-inode rollback methods are unchanged from reviewed `40b93279…`.

## Current runtime anchor

Actual completed QA run `44207277921`, request `6965055656`, source `06666bd638579bb3d95317004bf293c299b79daa`, observed proxy PID `3648425`, start ticks `175058217`, argv SHA `da23c227…`, and the same installed source generation. Its transport, preserved two-message prefix, appended pair and full new M1 were independently accepted. Wording remained partial and is the reason for this patch. The completed question is not replayed.

The current four-queue/three-worker installation is retained. The package does not modify common.py, agent_loop.py, the worker or queue configuration, model processes, S03, the model-reference snapshot or chat history. Runtime dependency checks retain the current exact common/agent/owner-stream/bridge pins; an optional broader dispatcher cutover is not a prerequisite.

## Installation and rollback

The existing transaction checks the maintenance lock identity, owner STOP, fresh priority and model slots, current proxy lifetime/configuration, source bytes and ownership before stopping only `nox-proxy`. Private originals are written and verified inside the unique transaction directory. The new helper is created with an absent-only hard-link operation; the two existing targets use staged source replacement with exact hashes.

Rollback runs while the proxy is stopped. Both existing targets must still be the exact staged postimage inode, owner, mode, size and bytes before restoration. A foreign same-byte file causes HOLD instead of replacement. Only the newly created helper owned by this transaction may be removed. Unknown start state, explicit STOP or conflicting ownership keeps the inherited fail-closed recovery behavior. There is no standalone unbound rollback command.

The inherited lifecycle's historical `four_postimages_verified` step label is retained; the explicit file maps and this package's scope contain two existing files and one new helper. No fourth target is modified.

## Remaining gates

1. Independent review of this exact six-module composition and source freeze.
2. Root publishes the immutable candidate with the unchanged owner repair operator, coordinates a quiet window, and sends one command. All current native guards are checked inside that command.
3. Root reconciles the actual result, proxy lifetime and all three postimages. Runtime response quality and speed are not claimed from source tests; they remain observations for subsequent approved use.

Completed checks: three focused real-TempFS tests, including both existing targets' foreign-inode rollback cases, exact apply/restore, and an unexpected new helper collision; six decoded modules exact; source compiles; current process pins match the actual accepted QA. The full previous model, dispatcher and chat test suites were not repeated.
