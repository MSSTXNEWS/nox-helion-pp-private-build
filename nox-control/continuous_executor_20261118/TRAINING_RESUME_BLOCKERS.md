# Training resume blockers — 2026-11-18

The read-only observations below do **not** admit further optimizer updates. Training cannot safely resume with the observed quality policy, sealed source bindings and resource availability. Stopping chat alone would not resolve the quality or source-binding barriers. This note records a handoff; it does not authorize a guard reset, descriptor rewrite, chat stop or weight update.

## Evidence

| Observation | Native workflow run | Result |
| --- | --- | --- |
| Training service and process memory | [44336463012](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/actions/runs/44336463012) | Read-only diagnostic completed; trainer `FATAL`, no trainer PID; anonymous-file owner identified. |
| Exact anonymous inode mappings | [44338410353](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/actions/runs/44338410353) | Complete census of 60 processes, no unavailable or unstable processes; active chat maps the target file. |
| Training resume preflight | [44340725422](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/actions/runs/44340725422) | Read-only preflight completed; quality, freshness, source and resource barriers remain. |

These are timestamped observations, not a standing permission or a promise that resources remain unchanged. The probes did not import training modules, read checkpoint payloads, issue optimizer permission or change services, flags or weights.

## Quality policy and checkpoint evidence

The freshly **read stored guard record** was `INHIBITED`, with `inhibit=true`, reason `HOLDOUT_REGRESSION` and regression streak **2**. Its best recorded holdout loss was **1.2216252349317074**; CP55 recorded **1.3216557949781418** at successful update **55**. The guard sample itself was **131,493.988 seconds old** and was explicitly reported as not fresh. This verifies an existing latched policy state; it is not a new holdout evaluation or live optimizer permission.

The deployed guard preserves the inhibit latch. Removing a pause/stop flag or obtaining more memory does not clear it. The deployed optimizer-permission check requires a matching execution/checkpoint binding, a guard sample no older than **30 seconds**, state `MONITORING`, `inhibit=false`, `complete=false` and the required disk margin. See [`owner_qwen_successor_guard.py`](../owner_qwen_successor_guard.py) and [`owner_qwen_execution_successor.py`](../owner_qwen_execution_successor.py), deployed under their revision/guard consumer names and verified by the preflight's source pins.

CP55's current metadata hashes matched:

| Metadata | SHA-256 |
| --- | --- |
| Latest checkpoint pointer | `192d07c459c7ad7c89d30d2803fea574e1bc407d37ad755c1f61294748d4ece0` |
| Checkpoint manifest | `458310555dc0a2a5e4e7b3fa127e7a642bb1d5651aa2393777c50f0c6c4e1a65` |

**No full weight/optimizer payload hashes or restoration were verified by these probes.** The saved count of 55 updates is historical checkpoint evidence, not proof that training is currently progressing. A future restore must verify every required payload and the adapter, optimizer, scheduler, scaler, RNG and lineage bindings before any update.

## Sealed source mismatch

The receipt/descriptor metadata chain, admission and wrapper matched the current seal. Eight of nine declared runtime/consumer files matched; the sole mismatch was `nox_dispatcher_t855u.py`:

| Binding | SHA-256 |
| --- | --- |
| Sealed expected source | `c8e6adccf85b9dd089486cdbcc192261d34390cba9fb68231b4966e82d7024bb` |
| Observed live source | `9ae0c67523967756206a0da31d1a1cab65281dc2f4f28989f2156cd27da43a21` |

The live hash predates this repair's module updates. The successful [continuous installation run 44334613561](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/actions/runs/44334613561), using [source `1d17cf6a5699832b00fc01d26fa55ec0c17f6355`](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/tree/1d17cf6a5699832b00fc01d26fa55ec0c17f6355/nox-control), required that exact dispatcher hash in `expected_native` and checked all native preimages before stopping or applying changes. Its runtime replacement set did not include this controller file. This is a pre-existing training consumer-binding mismatch, not a reason to silently advance the sealed descriptor.

## Resources and active chat memory

The resume preflight verified the deployed source pins for these requirements. RAM means **raw** cgroup headroom (`memory.max - memory.current`); inactive file cache is not credited.

| Gate | Required | Observed at resume preflight |
| --- | --- | --- |
| Training entry RAM | **32 GiB** = 34,359,738,368 bytes | 53,678,080 bytes, approximately **0.050 GiB** |
| Memfd staging RAM base | **48 GiB** = 51,539,607,552 bytes, plus any specified staging allowance | Same insufficient raw headroom |
| Full handoff restaging RAM | **70,869,001,213 bytes**, approximately **66.002 GiB** | Same insufficient raw headroom |
| GPU 1 free memory for handback | **30,000 MiB**, approximately **29.3 GiB** | **4,757 MiB**, approximately **4.65 GiB** |
| Disk floor | **10 GiB** = 10,737,418,240 bytes | **18,116,448,256 bytes**; also above the stored guard's 11,832,524,800-byte early threshold |

The 75,266,239,716-byte anonymous file (`device=1`, `inode=131095`) is an active chat dependency. Keeper PID **498569**, start ticks **168416044**, held its descriptor. The complete mapping census found the entire file mapped solely by chat PID **3266857**, start ticks **172046662**; neither keeper nor parent mapped it. Logical file size and virtual mapping coverage are **not resident-memory measurements**. Closing the keeper would not free the file while chat retains its mapping and could compromise a future restart path. No memory was released.

The existing reviewed media handoff concerns trainer/GPU-1 media ownership; it does not establish a reversible stop/restore contract for this current chat process. No such transition is warranted while independent quality and seal barriers remain.

## Next concrete work

1. Prepare a reviewed, isolated **evaluation-only** contract: pin CP55 and the best actually retained checkpoint, verify full payload hashes and restoration requirements, and preserve the current pointer, checkpoints and guard history. The recorded best loss alone does not establish which best checkpoint is still available.
2. Compare those checkpoints on the **same pinned holdout**, evaluation configuration and library versions. Obtain numeric evidence without optimizer updates or automatic promotion. Any execution still requires sufficient resources and a reviewed resource plan; this note does not start it.
3. Review an **additive execution-context migration** for the actual consumer sources and checkpoint lineage. Preserve the original immutable receipt/descriptor and quality latch. A new context must have an explicit quality decision and verified bindings; it must not be manufactured by rewriting the old descriptor or clearing the guard.

Only after quality, restoration and source-binding evidence is reconciled should a separately reviewed bounded training/handback plan be considered. Keep the 32/48 GiB RAM gates, full restaging requirement, GPU gate and checkpoint protections intact.
