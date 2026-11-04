"""NOX FASTLANE-2: bounded, read-only-first task/patch accelerator.

Designed for the EXISTING NOX HELION EXPRESS INTEGRATOR, PR #162.
This module is NOT an agent, a new service, a downloader, a release builder,
GitHub/Drive writer, owner-lease authority, or an installer.

Owner I0 alone merges; PATCH-A and PATCH-B alone hold cumulative state.
Prepared candidates are immutable off-tree handoffs awaiting owner CAS review.
An unverified input is never promoted into native acceptance or an EXE PASS.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
from typing import Any

SHA1 = re.compile(r"[0-9a-f]{40}\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
TASK_ID = re.compile(r"[A-Z][A-Z0-9_-]{1,63}\Z")
RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{3,127}\Z")
MAX_LEDGER = 512_000
MAX_TASKS = 1000
MAX_LEASES = 1024
MAX_PATHS = 48
MAX_BYTES = 512 * 1024
ALLOWED_PHASES = ("BOOT", "LOADER", "RELEASE1", "FREE")
PHASE_PREVIOUS = {"BOOT": None, "LOADER": "BOOT", "RELEASE1": "LOADER", "FREE": "RELEASE1"}
STATUS = frozenset(("PENDING", "OFFTREE_READY", "INTEGRATED", "ACCEPTED", "HOLD", "FAILED"))


class FastlaneHold(RuntimeError):
    """Fail-closed. An explicit HOLD never means successful work."""


def _sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def git_blob(b: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(b)).encode() + b"\0" + b).hexdigest()


def _safe_path(s: Any) -> bool:
    return (type(s) is str and 0 < len(s) <= 240 and
            not s.startswith("-") and "\\" not in s and ":" not in s and
            not any(ord(c) < 32 or ord(c) == 127 for c in s) and
            not PurePosixPath(s).is_absolute() and
            all(p not in ("", ".", "..") for p in s.split("/")))


def _real_regular(path: Path) -> bool:
    try:
        entry = path.lstat()
        if not stat.S_ISREG(entry.st_mode) or path.is_symlink():
            return False
        if getattr(entry, "st_file_attributes", 0) & 0x400:
            return False
        for parent in path.parents:
            node = parent.lstat()
            if stat.S_ISLNK(node.st_mode) or getattr(node, "st_file_attributes", 0) & 0x400:
                return False
        return True
    except OSError:
        return False


def _unique_fields(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise FastlaneHold("DUPLICATE_JSON_FIELD")
        result[key] = value
    return result


def _finite_number(token):
    value = float(token)
    if not __import__("math").isfinite(value):
        raise FastlaneHold("NONFINITE_JSON_NUMBER")
    return value


def _read_json(path: Path, *, limit: int = MAX_LEDGER) -> dict:
    if not _real_regular(path) or path.stat().st_size > limit:
        raise FastlaneHold("UNVERIFIED_JSON_FILE_OR_QUOTA")
    try:
        data = json.loads(path.read_bytes().decode("utf-8"),
                          object_pairs_hook=_unique_fields,
                          parse_float=_finite_number,
                          parse_constant=lambda _v: (_ for _ in ()).throw(FastlaneHold("NONFINITE_JSON_NUMBER")))
    except FastlaneHold:
        raise
    except (UnicodeError, ValueError, OSError) as e:
        raise FastlaneHold("INVALID_LEDGER_JSON") from e
    if type(data) is not dict:
        raise FastlaneHold("JSON_OBJECT_REQUIRED")
    return data


def _git(root: Path, *args: str, timeout: int = 8) -> bytes:
    try:
        p = subprocess.run(("git", "-C", str(root), "--no-pager", *args),
                           input=b"", capture_output=True, timeout=timeout, check=False,
                           env={**os.environ, "GIT_OPTIONAL_LOCKS": "0", "GIT_TERMINAL_PROMPT": "0"})
        if p.returncode or len(p.stdout) > 3_000_000:
            raise FastlaneHold("GIT_EXACT_SOURCE_HOLD")
        return p.stdout
    except (OSError, subprocess.TimeoutExpired) as e:
        raise FastlaneHold("GIT_EXACT_SOURCE_UNAVAILABLE") from e


def source_snapshot(root: Path, *, clean: bool = True) -> dict:
    """One small Git query per property; no archive downloads or scan of history."""
    if not root.is_dir() or not (root / ".git").exists():
        raise FastlaneHold("GIT_CHECKOUT_REQUIRED")
    root = root.absolute()
    if any(p.is_symlink() or (getattr(p.lstat(), "st_file_attributes", 0) & 0x400)
           for p in (root, *root.parents)):
        raise FastlaneHold("SOURCE_REPARSE_HOLD")
    head = _git(root, "rev-parse", "HEAD").decode("ascii", "strict").strip()
    if not SHA1.fullmatch(head):
        raise FastlaneHold("SOURCE_HEAD_REQUIRED")
    if clean and _git(root, "status", "--porcelain", "--untracked-files=no").strip():
        raise FastlaneHold("SOURCE_DIRTY_HOLD")
    raw = _git(root, "ls-tree", "-r", "-z", head)
    if raw and not raw.endswith(b"\0"):
        raise FastlaneHold("TRUNCATED_GIT_TREE")
    paths = {}
    for entry in raw.split(b"\0"):
        if not entry:
            continue
        try:
            mode_type_blob, path_b = entry.split(b"\t", 1)
            mode, typ, sha_b = mode_type_blob.split(b" ")
            path = path_b.decode("utf-8", "strict")
            blob = sha_b.decode("ascii")
        except (ValueError, UnicodeError) as e:
            raise FastlaneHold("GIT_TREE_ROW_INVALID") from e
        if mode in (b"120000", b"160000"):
            continue  # Not a regular source file.
        if mode not in (b"100644", b"100755") or typ != b"blob" or not SHA1.fullmatch(blob):
            raise FastlaneHold("GIT_TREE_MODE_HOLD")
        if _safe_path(path):
            if path in paths:
                raise FastlaneHold("GIT_DUPLICATE_PATH")
            paths[path] = blob
    if _git(root, "rev-parse", "HEAD").decode().strip() != head:
        raise FastlaneHold("SOURCE_HEAD_DRIFT")
    return {"source_head": head, "regular_blobs": paths,
            "tree_count": len(paths), "read_only": True}


@dataclass(frozen=True)
class Task:
    id: str
    phase: str
    lane: str
    priority: int
    paths: tuple[str, ...]
    depends: tuple[str, ...]
    status: str
    requires_gates: tuple[str, ...]

    @staticmethod
    def parse(row: Any) -> "Task":
        if type(row) is not dict or set(row) != {"id", "phase", "lane", "priority", "paths", "depends", "status", "requires_gates"}:
            raise FastlaneHold("TASK_SCHEMA_INVALID")
        ident, phase, lane = row["id"], row["phase"], row["lane"]
        if (type(ident) is not str or not TASK_ID.fullmatch(ident) or
                phase not in ALLOWED_PHASES or lane not in ("A", "B") or
                type(row["priority"]) is not int or not 0 <= row["priority"] <= 100 or
                row["status"] not in STATUS):
            raise FastlaneHold("TASK_IDENTITY_INVALID")
        paths, depends, gates = row["paths"], row["depends"], row["requires_gates"]
        if (type(paths) is not list or not 1 <= len(paths) <= MAX_PATHS or
                any(not _safe_path(p) for p in paths) or len(set(paths)) != len(paths) or
                type(depends) is not list or len(depends) > MAX_TASKS or
                any(type(d) is not str or not TASK_ID.fullmatch(d) for d in depends) or
                len(set(depends)) != len(depends) or ident in depends or
                type(gates) is not list or set(gates) != {"G1", "G2", "G3", "G4"} or len(gates) != 4):
            raise FastlaneHold("TASK_PATH_DEPENDENCY_GATE_INVALID")
        return Task(ident, phase, lane, row["priority"], tuple(paths), tuple(depends), row["status"], tuple(gates))


def _phase_order(phase: str) -> int:
    return ALLOWED_PHASES.index(phase)


def _valid_ledger(data: dict) -> dict:
    if data.get("schema") != "NOX-FASTLANE2-LEDGER-v1" or type(data.get("tasks")) is not list or len(data["tasks"]) > MAX_TASKS:
        raise FastlaneHold("LEDGER_SCHEMA_OR_QUOTA")
    tasks = {t.id: t for t in map(Task.parse, data["tasks"])}
    if len(tasks) != len(data["tasks"]):
        raise FastlaneHold("DUPLICATE_TASK_ID")
    for t in tasks.values():
        for dep in t.depends:
            if dep not in tasks or _phase_order(tasks[dep].phase) > _phase_order(t.phase):
                raise FastlaneHold("TASK_DEPENDENCY_UNKNOWN_OR_FUTURE")
    # Bounded iterative dependency walk: a 1000-task deep chain must never
    # recurse into Python's call stack or silently skip a cycle.
    unresolved = {key: len(task.depends) for key, task in tasks.items()}
    successors = {key: [] for key in tasks}
    for key, task in tasks.items():
        for dependency in task.depends:
            successors[dependency].append(key)
    ready = sorted(key for key, count in unresolved.items() if count == 0)
    seen = 0
    while ready:
        key = ready.pop()
        seen += 1
        for dependent in successors[key]:
            unresolved[dependent] -= 1
            if unresolved[dependent] == 0:
                ready.append(dependent)
    if seen != len(tasks):
        raise FastlaneHold("DEPENDENCY_CYCLE")
    return tasks


def _lease_paths(leases: dict, tasks: dict[str, Task]) -> tuple[set[str], set[str]]:
    if leases.get("schema") != "NOX-FASTLANE2-LEASES-v1" or type(leases.get("items")) is not list or len(leases["items"]) > MAX_LEASES:
        raise FastlaneHold("LEASE_SCHEMA_OR_QUOTA")
    occupied, owners = set(), set()
    active_owners_by_path = {}
    active_owners_by_task = {}
    for row in leases["items"]:
        if type(row) is not dict or set(row) != {"task_id", "owner", "run_id", "active", "paths"}:
            raise FastlaneHold("LEASE_ROW_INVALID")
        task_id, owner, run_id, paths = row["task_id"], row["owner"], row["run_id"], row["paths"]
        if task_id not in tasks or type(owner) is not str or not owner or type(run_id) is not str or not RUN_ID.fullmatch(run_id) or type(row["active"]) is not bool or type(paths) is not list or not paths or any(not _safe_path(x) for x in paths):
            raise FastlaneHold("LEASE_IDENTITY_INVALID")
        if not set(paths).issubset(tasks[task_id].paths):
            raise FastlaneHold("LEASE_TASK_PATH_MISMATCH")
        if row["active"]:
            key = (owner, run_id)
            if task_id in active_owners_by_task:
                raise FastlaneHold("OVERLAPPING_ACTIVE_TASK_LEASE")
            active_owners_by_task[task_id] = key
            for path in paths:
                if path in active_owners_by_path:
                    raise FastlaneHold("OVERLAPPING_ACTIVE_PATH_LEASE")
                active_owners_by_path[path] = key
            occupied.update(paths)
            owners.add(task_id)
    return occupied, owners


def locate_reusable_source(snapshot: dict, target: str, *, limit: int = 8) -> list[dict]:
    """Fast reuse-before-build shortlist from ONE verified Git-tree lookup.

    This is source discovery, never licence approval, remote download or auto-import.
    Historical conflict archives cannot supersede canonical HEAD code.
    """
    if not _safe_path(target) or type(limit) is not int or not 1 <= limit <= 16:
        raise FastlaneHold("REUSE_LOOKUP_INPUT_INVALID")
    paths = snapshot.get("regular_blobs")
    if type(paths) is not dict:
        raise FastlaneHold("REUSE_REQUIRES_VERIFIED_GIT_INVENTORY")
    basename = PurePosixPath(target).name.lower()
    stem = PurePosixPath(target).stem.lower()
    terms = tuple(t for t in re.split(r"[^a-z0-9]+", stem) if len(t) >= 4)
    found = []
    for path, blob in paths.items():
        if path == target or not SHA1.fullmatch(str(blob)):
            continue
        low = path.lower()
        if any(tag in low for tag in ("/donor_conflicts/", "/archive/", "/legacy/", "/stale/")):
            continue
        name = PurePosixPath(path).name.lower()
        score = (100 if name == basename else
                 20 + sum(6 for t in terms if t in name) if terms else 0)
        if score <= 20:
            continue
        found.append((score, path, blob))
    found.sort(key=lambda r: (-r[0], r[1]))
    return [{"path": path, "git_blob_sha1": blob,
             "status": "SOURCE_DONOR_CANDIDATE_REVIEW_RIGHTS_AND_SHA256",
             "not_installed": True, "not_owner_approved": True}
            for _, path, blob in found[:limit]]


def choose_free(ledger: dict, leases: dict, snapshot: dict, *, phase_acceptance: dict,
                preferred: str | None = None, lane: str | None = None,
                stopped: bool = False) -> dict:
    """ERR-25: bypass occupied sections only by SAFE independent work.

    This NEVER claims a lease, writes a group patch, merges, or executes code.
    Acceptance means external verified phase evidence, not this helper's vote.
    """
    tasks = _valid_ledger(ledger)
    occupied, busy_tasks = _lease_paths(leases, tasks)
    if type(phase_acceptance) is not dict or set(phase_acceptance) != {"BOOT", "LOADER", "RELEASE1"} or any(type(v) is not bool for v in phase_acceptance.values()):
        raise FastlaneHold("PHASE_ACCEPTANCE_EVIDENCE_REQUIRED")
    if preferred is not None and preferred not in tasks:
        raise FastlaneHold("UNKNOWN_PREFERRED_TASK")
    if lane is not None and lane not in ("A", "B"):
        raise FastlaneHold("INVALID_LANE")
    head = snapshot.get("source_head")
    if type(head) is not str or not SHA1.fullmatch(head):
        raise FastlaneHold("VERIFIED_SOURCE_HEAD_REQUIRED")
    if ledger.get("source_head") != head:
        raise FastlaneHold("STALE_LEDGER_HEAD")
    if stopped:
        return {"schema": "NOX-FASTLANE2-PLAN-v1", "source_head": head,
                "state": "STOPPED", "selected": None, "ready": [], "rejected": [],
                "executed": False, "autonomous_merge": False, "release_pass": False}
    candidates = []
    rejected = []
    for t in tasks.values():
        why = None
        required = PHASE_PREVIOUS[t.phase]
        if lane is not None and t.lane != lane:
            why = "OTHER_LANE"
        elif required is not None and phase_acceptance[required] is not True:
            why = "PHASE_GATE_HOLD"
        elif t.status != "PENDING":
            why = "ALREADY_MATERIAL_OR_HOLD"
        elif any(tasks[d].status not in ("INTEGRATED", "ACCEPTED") for d in t.depends):
            why = "DEPENDENCY_NOT_INTEGRATED"
        elif t.id in busy_tasks or occupied.intersection(t.paths):
            why = "LIVE_OWNER_OCCUPIED"
        elif any(path not in snapshot["regular_blobs"] for path in t.paths):
            why = "SOURCE_PATH_NOT_IN_HEAD"
        if why is None:
            candidates.append(t)
        else:
            rejected.append({"id": t.id, "reason": why})
    # Keep deterministic ordering. Priority isn't a permission bypass.
    candidates.sort(key=lambda x: (-x.priority, x.id))
    if preferred in {t.id for t in candidates}:
        candidates.sort(key=lambda x: (x.id != preferred, -x.priority, x.id))
    selected = candidates[0] if candidates else None
    blocked_preferred = next((x["reason"] for x in rejected if x["id"] == preferred), None)
    return {"schema": "NOX-FASTLANE2-PLAN-v1", "source_head": head,
            "state": "OFFTREE_CANDIDATE_ALLOWED" if selected else "WAIT_NO_FREE_SAFE_TASK",
            "preferred": preferred, "preferred_blocker": blocked_preferred,
            "selected": selected.id if selected else None,
            "selected_paths": list(selected.paths) if selected else [],
            "selected_lane": selected.lane if selected else None,
            "selected_preimages": {p: snapshot["regular_blobs"][p] for p in selected.paths} if selected else {},
            "reuse_before_recoding": [locate_reusable_source(snapshot, p) for p in selected.paths] if selected else [],
            "ready": [t.id for t in candidates], "rejected": sorted(rejected, key=lambda x: x["id"]),
            "changed_only": True, "four_gates": {"G1": "SOURCE_ONLY", "G2": "NOT_CLAIMED",
                "G3": "NOT_RUN", "G4": "WINDOWS_NOT_RUN"},
            "executed": False, "autonomous_merge": False, "release_pass": False}


def _dir_outside_repo(path: Path, repo: Path) -> Path:
    """Reject links and in-repo output; realpath escape doesn't grant trust."""
    path = path.absolute()
    if any(p.is_symlink() or (getattr(p.lstat(), "st_file_attributes", 0) & 0x400)
           for p in (path, *path.parents) if p.exists() or p.is_symlink()):
        raise FastlaneHold("HANDOFF_SYMLINK_OR_REPARSE_HOLD")
    resolved = path.resolve()
    if resolved == repo.resolve() or resolved.is_relative_to(repo.resolve()):
        raise FastlaneHold("OFFTREE_OUTPUT_REQUIRED")
    return resolved


def save_handoff(*, repo: Path, output: Path, candidate: Path,
                 task_id: str, plan: dict, run_id: str, test_log: Path | None = None) -> dict:
    """Immutable OFFTREE handoff; does not claim tests, source merge or release.

    A test log is evidence bytes only and its status remains UNVERIFIED until
    a real independent runner validates it. No source code is executed here.
    """
    if type(task_id) is not str or task_id != plan.get("selected") or plan.get("state") != "OFFTREE_CANDIDATE_ALLOWED":
        raise FastlaneHold("HANDOFF_TASK_NOT_FREE")
    if type(run_id) is not str or not RUN_ID.fullmatch(run_id):
        raise FastlaneHold("HANDOFF_RUNID_INVALID")
    repo = repo.absolute()
    output = _dir_outside_repo(output, repo)
    candidate = candidate.absolute()
    if not _real_regular(candidate) or candidate.stat().st_size > MAX_BYTES or candidate.stat().st_size < 1:
        raise FastlaneHold("CANDIDATE_REGULAR_FILE_AND_QUOTA_REQUIRED")
    if candidate.resolve().is_relative_to(repo.resolve()):
        raise FastlaneHold("CANDIDATE_MUST_BE_OFFTREE")
    paths = plan.get("selected_paths")
    if type(paths) is not list or len(paths) != 1:
        raise FastlaneHold("ONE_CANDIDATE_TARGET_PER_HANDOFF")
    target = paths[0]
    before = plan.get("selected_preimages", {}).get(target)
    snapshot = source_snapshot(repo)
    if (snapshot["source_head"] != plan.get("source_head") or
            snapshot["regular_blobs"].get(target) != before or
            not isinstance(before, str) or not SHA1.fullmatch(before)):
        raise FastlaneHold("HANDOFF_SOURCE_PREIMAGE_DRIFT")
    content = candidate.read_bytes()
    # An unchanged donor is not an improvement. Do not consume a slot with
    # a no-op patch that a previous worker already finished.
    if git_blob(content) == before:
        raise FastlaneHold("CANDIDATE_IDENTICAL_TO_SOURCE")
    if b"\0" in content:
        raise FastlaneHold("HANDOFF_BINARY_SOURCE_DENIED")
    try:
        content.decode("utf-8", "strict")
    except UnicodeError as e:
        raise FastlaneHold("HANDOFF_UTF8_SOURCE_REQUIRED") from e
    proof = None
    if test_log is not None:
        if not _real_regular(test_log) or test_log.stat().st_size > 128_000:
            raise FastlaneHold("TEST_LOG_INVALID")
        proof = {"sha256": _sha256(test_log.read_bytes()), "state": "UNVERIFIED_EXTERNAL_LOG"}
    fingerprint = _sha256(content)
    receipt = {"schema": "NOX-FASTLANE2-OFFTREE-RECEIPT-v1",
               "status": "OFFTREE_READY_FOR_OWNER_REBASE_NOT_MERGED", "task_id": task_id,
               "run_id": run_id, "source_head": plan["source_head"], "path": target,
               "original_git_blob_sha1": before, "candidate_git_blob_sha1": git_blob(content),
               "candidate_sha256": fingerprint, "candidate_bytes": len(content),
               "lane": plan["selected_lane"], "test_evidence": proof,
               "test_execution_by_this_tool": False, "owner_cas_write": False,
               "native_model_run": False, "windows_build_id": None, "e07_accepted": False,
               "next": "APPROVED_GROUP_OWNER_MUST_REBASE_INHERITED_A_OR_B_DIFF_AND_CAS_SAVE"}
    token = f"{task_id}-{fingerprint[:20]}"
    source_target = output / f"{token}.candidate"
    receipt_target = output / f"{token}.receipt.json"
    if source_target.exists() or receipt_target.exists():
        raise FastlaneHold("IMMUTABLE_HANDOFF_ALREADY_PRESENT")
    output.mkdir(parents=True, exist_ok=True)
    if not _real_regular(candidate):
        raise FastlaneHold("CANDIDATE_CHANGED_OR_REPARSE_HOLD")
    if _sha256(candidate.read_bytes()) != fingerprint:
        raise FastlaneHold("CANDIDATE_CHANGED_DURING_HANDOFF")
    # Exclusive writes plus readback; a crash leaves an explicit incomplete hold.
    try:
        with source_target.open("xb") as fp:
            fp.write(content)
            fp.flush()
            os.fsync(fp.fileno())
        with receipt_target.open("xb") as fp:
            fp.write((json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8"))
            fp.flush()
            os.fsync(fp.fileno())
    except BaseException:
        if source_target.is_file() and not source_target.is_symlink() and _sha256(source_target.read_bytes()) == fingerprint:
            source_target.unlink()
        raise
    if _sha256(source_target.read_bytes()) != fingerprint or _read_json(receipt_target) != receipt:
        raise FastlaneHold("HANDOFF_READBACK_FAILED")
    return {"receipt_path": str(receipt_target), "candidate_path": str(source_target),
            "sha256": fingerprint, "status": receipt["status"]}


def plan_from_files(repo: Path, ledger: Path, leases: Path, acceptance: Path, **kwargs) -> dict:
    return choose_free(_read_json(ledger), _read_json(leases), source_snapshot(repo),
                       phase_acceptance=_read_json(acceptance), **kwargs)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="NOX FASTLANE-2 exact-HEAD safe candidate scheduler")
    parser.add_argument("command", choices=("plan", "handoff"))
    parser.add_argument("--repo", required=True)
    parser.add_argument("--ledger", required=True)
    parser.add_argument("--leases", required=True)
    parser.add_argument("--acceptance", required=True)
    parser.add_argument("--task")
    parser.add_argument("--lane", choices=("A", "B"))
    parser.add_argument("--stop", action="store_true")
    parser.add_argument("--candidate")
    parser.add_argument("--output")
    parser.add_argument("--run-id")
    parser.add_argument("--test-log")
    args = parser.parse_args(argv)
    try:
        plan = plan_from_files(Path(args.repo), Path(args.ledger), Path(args.leases),
                               Path(args.acceptance), preferred=args.task,
                               lane=args.lane, stopped=args.stop)
        if args.command == "plan":
            print(json.dumps(plan, ensure_ascii=False, sort_keys=True))
            return 0
        if not all((args.candidate, args.output, args.run_id, args.task)):
            raise FastlaneHold("HANDOFF_ARGS_REQUIRED")
        result = save_handoff(repo=Path(args.repo), output=Path(args.output),
                              candidate=Path(args.candidate), task_id=args.task,
                              plan=plan, run_id=args.run_id,
                              test_log=Path(args.test_log) if args.test_log else None)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except (FastlaneHold, OSError, ValueError) as exc:
        code = str(exc)
        if not re.fullmatch(r"[A-Z0-9_]+", code):
            code = "FASTLANE2_GENERAL_HOLD"
        print(json.dumps({"status": "HOLD", "reason": code, "release_pass": False}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
