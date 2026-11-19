# NOX bounded cgroup memory reclaim

`nox_memory_reclaim_watchdog.py` is an opt-in controller for one exact,
systemd-managed cgroup-v2 service leaf. The shipped policy is disabled. The
controller never runs `drop_caches`, changes a memory limit, restarts a service,
or walks arbitrary cgroups. It only writes a page-aligned, bounded request to
the allowlisted leaf's `memory.reclaim` after a fresh sample, a durable intent,
and repeated service/cgroup/process-membership checks.

## Admission conditions

An enabled policy is accepted only when all these conditions hold:

1. The policy is root-owned, mode `0600`, exact-schema, and names one `nox-*.service`
   and its exact ControlGroup path.
2. systemd reports that exact unit active in the pinned ControlGroup.
3. The path is a non-root systemd leaf cgroup with no child cgroups, domain type,
   finite `memory.max`, `memory.current`, `memory.stat`, `memory.events`, PSI,
   complete `cgroup.procs`, and a writable `memory.reclaim` interface.
4. There is no maintenance STOP marker, unresolved previous action, recent OOM,
   identity change, or unstable sample.

Any missing capability or ambiguous result produces a durable HOLD. It does not
fall back to a global cache purge. The request is capped at 256 MiB per action,
512 MiB per day by the example policy, page-aligned, and separated by at least
five minutes. The kernel may reclaim more or less than requested; receipts call
the result a reclaim attempt and record before/after samples rather than claiming
that the requested number of bytes was freed.

The estimated clean page-cache candidate is deliberately conservative:
`min(inactive_file, max(0, file - shmem - file_mapped - file_dirty - file_writeback))`.
This is only an estimate. `memory.stat:file` includes tmpfs/shared-memory pages;
`shmem` is excluded, as are mmap-backed, dirty, and writeback pages. PSI and OOM
counters are recorded as pressure and safety signals, not as a reason to purge
global caches.

## Service placement

The included `nox-memory-managed.slice` enables memory accounting for explicitly
placed services. A workload that is safe to manage must be installed as a
dedicated systemd service with `Slice=nox-memory-managed.slice`,
`MemoryAccounting=yes`, and a finite `MemoryMax=`. Its policy must then pin the
exact resulting ControlGroup, for example
`/nox-memory-managed.slice/nox-memory-worker.service`.

Current NOX chat and dispatcher processes are Supervisor-managed, not individual
systemd service units. The repository does not contain a verified one-to-one
mapping from those Supervisor programs to dedicated systemd service commands.
Do not invent unit names or move them implicitly. They can become eligible only
after an owner-reviewed systemd unit or auditable systemd-scope launcher is added,
with complete process membership and a real writable leaf `memory.reclaim`.

The last reported host inspection showed root-only/incomplete cgroup membership
and no target `memory.reclaim`; therefore the shipped service must remain
disabled until a new inspection proves the required leaf and systemd mapping.
The watchdog source and tests do not install or start the unit on a host.

## Install and inspect

Install the service file and slice file through the existing owner-approved
deployment path. Copy `memory-reclaim-policy.example.json` to
`/etc/nox/memory-reclaim-policy.json` with owner `root:root` and mode `0600`.
Keep `enabled` false until an exact workload leaf has passed all admission checks.
The JSON state under `/var/lib/nox-memory-reclaim/state.json` is atomically
replaced and fsynced after every observation, intent, attempt, or HOLD. A pending
intent after an interrupted/ambiguous write is intentionally retained and blocks
retries until inspected.
