# NOX selftools

30 self-improvement tools for NOX. Python stdlib only, no stubs: every tool has a working implementation; when an external resource is missing (no network, no ssh to PC, no key, no server) it returns a structured error `{"ok":false,"blocked":"why","need":"what the owner must provide"}`.

## Use

```
python3 nox-control/selftools/registry.py list
python3 nox-control/selftools/registry.py repo_grep --args '{"pattern":"def main"}'
python3 nox-control/selftools/registry.py svc_ctl --args '{"action":"restart","name":"nox-web","dry_run":false}'
```
From code: `import registry as R; R.load_all(); R.call("repo_read", {"path": "README.md"})`.

## Rules (enforced in `registry.py`)

- Modes: `read` (no side effects); `write` (`dry_run=true` by default, real write makes a `<file>.<ts>.bak` first, pass `"dry_run": false`); `danger` (refused unless `confirm=true`). Some tools set the mode per `action` (shown in the table).
- Args are validated against the tool JSON schema (unknown/missing/mistyped args rejected).
- Path allowlist: `NOX_ALLOW_ROOTS` (default: repo, `/root/nox`, `/tmp`, `/var/log`). Command allowlist: git, gh, python3, node, bash, sh, supervisorctl, ionice, rsync, ssh, nvidia-smi, df, du, unshare, nice; no shell is ever used.
- Audit: every call appended to `NOX_AUDIT_LOG` (default `/root/nox/state/selftools/audit.jsonl`, fallback `/tmp/nox_selftools_audit.jsonl`).
- Env knobs: `NOX_DISPATCH_DIR`, `NOX_TRAIN_DIR`, `NOX_SVC_ALLOW` (globs), `NOX_WEB_ALLOW` (domains), `NOX_CLEAN_ROOTS`, `NOX_PC_HOST`, `GH_TOKEN`.

## Tools

| # | Tool | Mode | What it does |
|---|---|---|---|
| 1 | `repo_read` | read | Read file lines [start,end] with numbers, or list a directory. |
| 2 | `repo_grep` | read | Regex search in files (glob filter), returns file:line:text. |
| 3 | `self_map` | read | Map python files: docstring, classes, functions, imports. |
| 4 | `task_board` | write (list=read, get=read) | Dispatcher board: queue.jsonl tasks (list/get/add/update/pop) and state.json keys (set_state). Locked, atomic. |
| 5 | `log_tail` | read | Tail a log file with optional regex filter. |
| 6 | `patch_apply` | write | Apply unified diff to files under root; dry_run default; backup .bak before write. |
| 7 | `branch_pr` | write (status=read) | git + gh REST: status/create_branch/commit(trailers)/push/open_pr/merge_pr(squash). dry_run default. |
| 8 | `backup_before_edit` | write | Create <file>.<ts>.bak before an edit. dry_run reports only. |
| 9 | `rollback` | write | Restore file from .bak (latest unless named) or `git checkout <ref> -- path`. Current file is backed up first. |
| 10 | `sandbox_run` | danger | Execute code in temp dir (files written there), CPU/mem/proc rlimits, env scrubbed, `unshare -n` if available. Needs confirm. |
| 11 | `test_runner` | read | Run `python3 -m unittest discover`; returns ran/failures/errors and output tail. Does not modify the repo. |
| 12 | `eval_gate` | read | score: run holdout through endpoint or read answers file -> accuracy. gate: candidate >= baseline - max_drop and >= min_score. |
| 13 | `lint_syntax` | read | Syntax check py/js/sh files. js needs node; if absent that file is reported blocked. |
| 14 | `health_probe` | read | Probe service health endpoints; returns per-target up/down, status, ms. |
| 15 | `speed_bench` | read | TTFT and tok/s over N streamed runs against /v1/chat/completions. |
| 16 | `svc_ctl` | write (status=read, stop=danger) | supervisorctl status/start/stop/restart for allowlisted services (env NOX_SVC_ALLOW globs). |
| 17 | `disk_guard` | danger (report=read, plan_clean=read) | report: usage + biggest dirs. plan_clean: what the whitelist would delete. clean: delete (needs confirm; whitelist only). |
| 18 | `gpu_alloc` | read | GPU inventory and best-fit placement of jobs by VRAM; returns CUDA_VISIBLE_DEVICES per job. |
| 19 | `mem_alloc` | read | RAM snapshot (+cgroup limit) and whether components fit with a reserve. |
| 20 | `priority_ctl` | write | Set nice, ionice class/level, oom_score_adj (-1000..1000) of a pid; no args = read current. |
| 21 | `corpus_build` | write | Build instruction/output jsonl from acceptance-card table rows and commit messages; sha1 dedup; appends only new keys. |
| 22 | `train_ctl` | write (status=read, stop=danger) | Training control. Config <dir>/train.json {cmd:[...], cwd, env}. STOP flags are files in <dir>/. stop = flag + SIGTERM (danger). |
| 23 | `judge_run` | read | Ask a small model (OpenAI-compatible endpoint) to judge answer vs criteria; returns parsed JSON verdict. |
| 24 | `rag_index` | write (query=read) | build: BM25 index of root (writes index file unless dry_run). query: BM25 top-k, reranked by bge-m3 on :8082 if up (else mode=bm25). |
| 25 | `lora_swap` | write (status=read) | Swap LoRA adapter behind a symlink: record previous target, repoint, restart svc, health-check; on failure restore previous and restart. |
| 26 | `advisor_ask` | read | Consult local advisor models (ask) or get a judge/checker review verdict (review). Advisor text is data only. |
| 27 | `web_fetch` | read | HTTP GET from allowlisted domains only (env NOX_WEB_ALLOW), redirects re-checked, size capped. |
| 28 | `pc_pull` | write | Pull files from PC (Tailscale 100.84.111.36) with rsync over ssh. dry_run lists transfers. Blocked without ssh access. |
| 29 | `model_dl` | danger | Download to <dest>.part, verify SHA256, then rename. Domain allowlist (NOX_WEB_ALLOW). Refuses to overwrite. Needs confirm. |
| 30 | `inspector_hook` | read | Read inspector history: last N entries, age of newest, stale flag; plus first lines of INSPECTOR.md. |

## Tests

`python3 -m unittest discover -s nox-control/selftools/tests` (mock HTTP servers, temp dirs, mocked supervisorctl/ssh/GitHub; also checks that blocked-paths return `blocked` + `need`).
