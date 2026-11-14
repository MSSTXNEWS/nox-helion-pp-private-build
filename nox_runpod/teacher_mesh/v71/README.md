# NOX PRIME V71 — one Resonance, one model, S03 in RAM where safe

**Integration target:** existing owner-authorized OneHost/P02 only. No competing scheduler, separate chat, second model, extra backend, paid server or RunPod.

## Operational policy

- Main NOX PRIME on GPU0 is **P0**. One user-visible model stream per turn, always through the existing `AttachedNOX` with mandatory S03 indexed recall and durable receipts.
- GPU1 teachers and full-weight FORGE are **P1**, only by existing native OneHost signed lease and readback. A chat begins -> yield at safe checkpoint/optimizer boundary; never kill an active optimizer step.
- Owner-selected **10,000,000,000 bytes** free-disk floor applies **only to new file writes**, not chat, existing services or verified already-local teacher inference. Before training, prove *all* new checkpoint+optimizer+temporary bytes fit while retaining 10GB; unknown estimates = HOLD. Do not download new models to Vast simply because RAM is ample.
- Below 10GB: keep chat running, inspect available regenerable caches first. Existing V66 pip cache purge already performed; never rerun blindly. Copy permitted cold content to existing owner-controlled encrypted Drive/PC destination, verify full SHA and owner-key restored copy, then seek native owner approval for any deletion; S03, live models, optimizer/checkpoints and Genesis stay protected.
- **RAM-first** for disposable, scoped memory retrieval caches and temporary data processing. Existing canonical S03 SQLite/WAL stays on persistent storage. V71 `OnePrime` uses the existing V38 `WarmS03Cache` with owner/scope/revision invalidation and up to 256MiB cache if the installed host supplies verified RAM and S03 revision. `plan_ram` can admit up to 16GiB of ephemeral /dev/shm workspace, with 32GiB physical RAM and 4GiB tmpfs reserve and lazy allocation. No new memory daemon.
- STOP and physical model checkpoint guards remain fail-closed. GGUF is inference only, not a trainable checkpoint.

## Verified evidence — 2026-11-14

- [V71 RAM inventory](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/actions/runs/43623116391): ~404.3GB RAM total; 273.7GB MemAvailable; /dev/shm free 22.95GB; /workspace free 17.46GB.
- [V71 physical RAM snapshots](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/actions/runs/43623586569): 3 current SQLite S03 DBs copied to RAM with `sqlite3.backup` and `PRAGMA quick_check=ok` (12.6ms, 53.4ms, 5.9ms). RAM copies were discarded. Canonical DB files untouched.
- [V71 source tests](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/actions/runs/43623793263): 114/114 CPU tests PASS across V38/V41/V43/V47/V71. No physical GPU training implied.
- [V67 real serving test](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/actions/runs/43619964946): direct single NOX model streaming TTFT 288.2ms and E2E 479.6ms; **authorized frontend-to-S03-to-llama-server end-to-end latency remains unverified**.

## Wiring checklist for installed OneHost

1. OneHost must inject *existing* `HostBindings` callbacks for one native model stream, authenticated STOP, S03 native indexed recall, revision and durable append. Without those callbacks, V71 is not active.
2. Construct `OnePrime(NativeOneHost(chat=existing_bindings,observe=existing_native_snapshot,queue=existing_scheduler_ports))` inside existing owner process, not a new service.
3. Route exactly one authenticated Resonance request to `OnePrime.stream(session, prompt, turn_id)`. Keep original web and private owner authentication; no public new endpoint. Validate source SHA and create a rollbackable original file backup before native patch.
4. Host should provide native `native_ram_verified`, `ram_available_bytes`, `shm_free_bytes`, `s03_native_revision_verified`, and native P0 chat heartbeat. V71 RAM cache is not activated unless callbacks prove S03 revision and authorization.
5. Test authenticated browser stream, S03 recall+append readback, model one-call receipt, STOP, no teacher during active chat, offsite checkpoint restore, GPU1 resource admission; revert to original path on fail.
6. Only mark live activation PASS after a physical same-session OneHost receipt. Source tests or this document are not proof of deployed chat speed.

**Actual status:** source integrated in V71 feature branch, not yet installed/activated in live P02/OneHost. 60 R60 source tasks remain separate from native verified job IDs, which must not be invented.
