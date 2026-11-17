# NOX OneHost integrations bridge

Status: **IMPLEMENTED_SOURCE / TESTED_LOCAL**. This package has not been installed
on the NOX server. No live Drive, Notion, GitHub or GitLab API call was made by this
package during development. Tests use a local fake rclone executable and captured
HTTPS connection fixtures. Credentials have not been created, copied or requested.

Python standard library only, Linux, Python 3.9+. No server, daemon, queue, model,
database, timer or scheduler is created. Run handlers inside an existing OneHost
worker. Network and subprocess operations must not run in the foreground chat loop.

The existing repository already contains `owner_drive_ram_bridge.py` and
`owner_drive_storage_bridge.py`. This package is a reusable rclone/OAuth backend
for those existing bridges and OneHost, not a second production bridge service.
The installed paths/SHA and callback contracts must be resolved before binding.

## Current owner policy: Drive first, RAM next

Canonical model/weight/dataset flow is **approved external source → verified
Google Drive object and manifest → owned RAM artifact**. New downloads do not go
directly from Hugging Face or another Internet URL into RAM or local SSD.

This package implements the **existing verified Drive → RAM** portion. Arbitrary
URL ingestion is not exposed. Ingestion from a new approved source still requires
a host-owned source manifest and a separately authorized existing transfer path
into Drive, followed by verified size/hash readback. It is not reported as
implemented or run by this package. Legacy direct-HF-to-RAM helpers must be
re-bound only after checking their installed version; no installed helper was
modified here.

Disk cache is an explicit optional route, disabled by default. Set
`NOX_ALLOW_DISK_CACHE=1` only for an explicit owner-approved disk-cache operation.
Otherwise the disk handler returns `DISK_CACHE_REQUIRES_EXPLICIT_OPT_IN` and its
registry state is `disabled_by_policy`. There is no fallback from RAM admission
failure to disk or to an external URL.

## Implemented operations

| Handler | Effect | Concrete behavior |
| --- | --- | --- |
| `nox.integrations.drive.check.v1` | Read | `rclone lsjson --stat` of the configured project directory |
| `nox.integrations.drive.list.v1` | Read | One directory level, bounded JSON output and at most 500 returned entries |
| `nox.integrations.drive.read.v1` | Read | Stat, bounded `rclone cat`, UTF-8 decode and SHA-256; at most 1 MiB |
| `nox.integrations.drive.upload.v1` | Write | Private stable artifact snapshot, immutable copy, complete SHA-256 readback, deterministic sidecar manifest and its readback |
| `nox.integrations.drive.download.v1` | Explicit disk option | Disabled by default; stat/size check, bounded `.part`, SHA-256, fsync, atomic no-clobber publication |
| `nox.integrations.notion.search.v1` | Read | Official title search over pages shared with the integration |
| `nox.integrations.github.repo.v1` | Read | Metadata for one server-configured repository |
| `nox.integrations.gitlab.project.v1` | Read | Metadata for one server-configured project |

The three HTTP adapters are readiness proofs, not full write APIs. They do not
publish comments, modify repositories, create paid resources or provision access.
No arbitrary shell, URL, endpoint, headers or credential is accepted in a task.

## Server-owned configuration

Set configuration in the existing service environment, or supply
`NOX_INTEGRATIONS_SECRETS_FILE` pointing to an **existing absolute JSON file owned
by the service UID, mode 0600**. The package never creates that file. Its keys are
the same names below and values are strings. Environment values override file
values. Unknown file keys and a symlink leaf/parent are rejected. Do not place the
secret file inside an uploadable artifact directory or a repository.

Required for Drive:

- `NOX_DRIVE_REMOTE`: existing rclone remote name, without colon; on-the-fly rclone remote syntax is rejected.
- `NOX_DRIVE_ROOT`: nonempty relative project path inside that remote. Requests cannot leave this root.
- `NOX_RCLONE_BIN`: optional absolute executable path; otherwise the installed `rclone` is located.
- `NOX_RCLONE_CONFIG`: optional existing config path; defaults to the service user's `~/.config/rclone/rclone.conf`.
- `RCLONE_CONFIG_PASS`: optional existing encrypted-config password, passed only through the child environment.
- `NOX_ARTIFACT_ROOT`: existing owner-controlled local directory for uploads.
- `NOX_DRIVE_CACHE_ROOT`: existing owner-controlled local directory for explicit disk downloads.
- `NOX_ALLOW_DISK_CACHE`: optional explicit disk-cache opt-in, exact value `1`; omitted by default.

Optional host budgets (positive decimal strings):

| Setting | Default | Meaning |
| --- | ---: | --- |
| `NOX_UPLOAD_MAX_BYTES` | 536870912 | Max artifact bytes per upload |
| `NOX_DOWNLOAD_MAX_BYTES` | 1073741824 | Max selected file bytes per download |
| `NOX_CACHE_HEADROOM_BYTES` | 67108864 | Required local filesystem reserve beyond the selected download |
| `NOX_TRANSFER_TIMEOUT_SECONDS` | 300 | Per-command transfer deadline |

These are admission ceilings, not preallocated RAM. The warm-weights controller
must separately admit cgroup/RAM/VRAM/page-cache/I/O costs. A tmpfs cache also
consumes real memory. Large weight sets can use individually verified shards.
The upload snapshot temporarily needs an additional full artifact copy on the
artifact filesystem; its disk check is explicit. Full upload readback costs one
additional transfer of the artifact. No streaming model inference from Drive is
claimed.

For proof adapters:

- `NOX_NOTION_TOKEN`; optional `NOX_NOTION_VERSION`, pinned default `2026-03-11`.
- `NOX_GITHUB_TOKEN` and `NOX_GITHUB_REPO` in `owner/repo` form; optional `NOX_GITHUB_API_VERSION`, pinned default `2026-03-10`.
- `NOX_GITLAB_TOKEN` and `NOX_GITLAB_PROJECT` (numeric ID or namespace/project).

Existing permissions determine which data is visible. The package does not widen
them. Token values do not appear in repr, public status or error bodies. Only the
rclone password is forwarded to rclone; unrelated provider tokens are excluded.
Configured secret values are rejected in task payloads and plaintext upload
content, and redacted in selected responses. This is not a general-purpose secret
scanner for all unknown credentials.

## Exact host contract

```python
from nox_integrations import Config, IntegrationBridge, CAPABILITIES

# These callbacks must come from the installed OneHost; do not substitute an
# always-true function or an in-memory acknowledgement in production.
bridge = IntegrationBridge(
    Config.load(),
    authorize=existing_integration_admission,  # (kind, payload, task_id) -> bool
    result_sink=existing_durable_result_sink,  # (receipt) -> nonempty receipt ref
    native_runtime=True,                      # only in the actual native worker
    should_pause=existing_stop_or_foreground_pause,
)

def make_handler(kind):
    def handler(payload, task_id):
        return bridge.execute(kind, payload, task_id=task_id)
    return handler

for kind in CAPABILITIES:
    existing_tool_registry.register(kind, make_handler(kind))
```

The exact registry method above is illustrative: adapt it to the installed
OneHost API. The callback signatures and handler names are the package contract.
Authorization must check the actual owner scope, TaskID, output artifact, fixed
project scope, writer claim and resource lease. Hold/release native resource
permits in the existing worker lifecycle. Missing authorization or durable sink
returns `HOST_BINDING_REQUIRED` without an external call. A second queue is not
needed. Failed durable acknowledgement never counts as completed native work.

`registry()` is local and reports only presence booleans. `pending_credentials`
means required configuration is missing; `ready` means present, not proven valid.
`tested_native` is set only after an actual handler result with remote proof and a
durable sink acknowledgement in a host-created `native_runtime=True` instance.
Evidence belongs to the particular capability, not all operations on that service.
The package keeps no persistent private status database; after a process restart
it returns to `ready` until the host verifies the operation again. Operator CLI
and local fixtures never mark native acceptance.

## Direct Drive-to-RAM API for the warm-weights controller

```python
from nox_integrations import Config, DriveAdapter

adapter = DriveAdapter(Config.load(), should_pause=host_stop_or_pause)
handle = adapter.download_memfd_verified(
    remote_path, expected_sha256, size_bytes,
    reserve_ram=host_reserve_ram_bytes,  # bytes -> opaque reservation, or None
    release_ram=host_release_ram,       # reservation -> release acknowledgement
    should_pause=controller_work_pause,
)
```

This creates only its own `memfd`, streams rclone stdout into it without a whole
Python byte buffer or SSD stage, verifies size/SHA-256, then applies WRITE/GROW/
SHRINK/SEAL seals. It reserves file bytes plus a 64 MiB process/buffer allowance.
That allowance is not a measured universal peak; the existing resource arbiter
must also enforce actual cgroup headroom. Rclone buffers are limited explicitly
and only one transfer is admitted per adapter call.

The returned `MemfdHandle` is an internal Python object. `describe()` returns
size/hash/seal metadata and `model_loaded=false`, without descriptor or token.
`fileno()` exposes the descriptor only to the trusted host loader. Keep the
handle in the existing persistent host until all loader mappings, duplicate or
inherited references are released; then call `close()`. The handle owns only its
new descriptor and reservation. It never discovers, closes or adopts existing
Engram descriptors. Failure/cancellation closes only that newly created memfd
and releases its reservation. `close()` is idempotent.

Actual loading needs a compatible model loader and explicit descriptor
inheritance (`pass_fds` for a child) or an in-process mapping. Neither is invented
by this package. It does not claim an automatically loaded model or survive a
host restart. The RAM method is not registered as a model-callable JSON handler
until the installed host supplies a durable handle registry/lifetime binding;
it is a typed internal callback for the warm-weights controller.

## Optional explicit disk-cache API

```python
from nox_integrations import Config, DriveAdapter

adapter = DriveAdapter(Config.load(), should_pause=host_stop_or_pause)
metadata = adapter.stat(remote_path)
receipt = adapter.download_verified(
    remote_path, cache_path, expected_sha256, size_bytes,
    should_pause=controller_work_pause,
)
```

Both paths are relative: `remote_path` is below the configured Drive project;
`cache_path` is below `NOX_DRIVE_CACHE_ROOT`. The controller must use that same
cache root and compare returned size/SHA before activation. The result is
`downloaded_verified` or `cache_hit_verified`, with `cache_path`, `local_path`,
`sha256`, `size_bytes`, `receipt_id` and `verified_at`.

The optional pause callback and the adapter's host STOP callback are ORed. Pause
is checked before transfer, while draining the subprocess and hashing, and before
publication. It kills only this rclone process group and deletes the unpublished
part. A resumed transfer restarts that file; HTTP-range continuation is not
implemented and is not claimed. Already verified cache files are reused.

Publication uses a same-directory hard link followed by removal of the part,
which atomically exposes the complete file without replacing an existing file.
This gives no-clobber semantics that plain `os.replace` lacks. An existing file
with another hash is preserved and returns `CACHE_DESTINATION_CONFLICT`; a race
at publication returns `CACHE_CONCURRENT_WRITER`. No automatic deletion of old
models occurs.

Backup call:

```python
receipt = adapter.upload_artifact(
    artifact_path, remote_path, expected_sha256,
)
```

It confirms remote SHA-256 and `<remote_path>.sha256.json`. The manifest records
schema, path, byte length and SHA-256, without a timestamp that would make repeated
immutable copies differ. A remote mutation followed by timeout, cancellation or
failed readback is marked `outcome_uncertain`; reconcile it before counting a
backup. Remote artifact and sidecar are two writes, not one cross-file transaction.

## Local commands and validation

```bash
python -m nox_integrations status
python -m unittest discover -s tests -v
```

`status` never initiates a network request. The operator can explicitly run a
read-only proof after installing valid configuration:

```bash
python -m nox_integrations proof drive
python -m nox_integrations proof notion
python -m nox_integrations proof github
python -m nox_integrations proof gitlab
```

Proof results are labelled `operator_cli`, with `native_acceptance=false`.
No live proof was run during package creation.

## Official API sources checked 2026-11-17

- https://rclone.org/commands/rclone_lsjson/
- https://rclone.org/commands/rclone_cat/
- https://rclone.org/commands/rclone_copyto/
- https://rclone.org/flags/
- https://developers.notion.com/reference/post-search
- https://developers.notion.com/reference/versioning
- https://docs.github.com/en/rest/repos/repos#get-a-repository
- https://docs.gitlab.com/api/projects/#get-a-single-project

Notion search POST is a read operation. HTTPS connections use TLS verification,
fixed official hostnames and no redirect following or automatic retry. Errors
return status/code only, never a provider body. The socket timeout and per-read
deadline are bounded; OS DNS resolution is outside a strict portable Python
wall-clock guarantee. The existing worker remains responsible for a total task
deadline and cancellation around network proof operations.
