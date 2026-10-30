"""NOX V16 P01: reuse the OS browser, Edge bookmarks and pinned WinGet in ONE host.

No HTTP server, new database, installer or default privileged action. Page JSON
cannot select a URL, file, program, package or cleanup target. All selections
and fresh approvals come from the existing authenticated Windows owner.
SOURCE CANDIDATE: Windows native/WebView2 acceptance is separate.
"""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import ipaddress
import json
import os
from pathlib import Path
import platform
import re
import stat
import subprocess
import time
from typing import Callable
from urllib.parse import urlsplit
import webbrowser

SHA64 = re.compile(r"[0-9a-f]{64}\Z", re.I)
PACKAGE = re.compile(r"[A-Za-z][A-Za-z0-9.+_-]{0,127}\Z")
CACHE_NAME = re.compile(r"nox-[A-Za-z0-9_-]{1,80}\.(?:tmp|cache|log)\Z")
MAX_BOOKMARKS = 100
MAX_BOOKMARK_FILE = 4 * 1024 * 1024
MAX_CACHE_FILES = 128
MAX_CACHE_BYTES = 64 * 1024 * 1024

class OwnerHold(RuntimeError):
    """Missing installed trusted Windows capability or source receipt."""

class OwnerDenied(PermissionError):
    """Untrusted page input, identity or revoked native consent."""

@dataclass(frozen=True)
class TrustedUpdatePlan:
    winget: Path
    sha256: str
    package_id: str
    approved_package_ids: frozenset[str]


def _plain(path: Path, *, must_file: bool = False) -> Path:
    if not isinstance(path, Path) or not path.is_absolute():
        raise OwnerHold("NATIVE_ABSOLUTE_PATH_REQUIRED")
    for node in (path, *path.parents):
        if node.is_symlink():
            raise OwnerHold("REPARSE_OR_SYMLINK_REJECTED")
        try:
            info = node.lstat()
        except OSError as exc:
            raise OwnerHold("NATIVE_PATH_MISSING") from exc
        if getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
            raise OwnerHold("REPARSE_OR_SYMLINK_REJECTED")
    if not (path.is_file() if must_file else path.is_dir()):
        raise OwnerHold("NATIVE_PATH_NOT_REGULAR")
    return path.resolve(strict=True)


def _https_url(value: str) -> str:
    if type(value) is not str or not 1 <= len(value) <= 2048 or any(ord(x) < 32 or ord(x) == 127 for x in value):
        raise OwnerDenied("NATIVE_HTTPS_URL_REQUIRED")
    try:
        url = urlsplit(value)
        host = url.hostname
        if (url.scheme != "https" or not host or url.username is not None or
                url.password is not None or url.port is not None or
                value.startswith("https:////") or "\\" in value or url.fragment):
            raise ValueError("not a trusted HTTPS URL")
        ascii_host = host.encode("idna").decode("ascii")
        if ascii_host == "localhost" or ascii_host.endswith(".localhost") or ascii_host.endswith(".local"):
            raise ValueError("local destination blocked")
        try:
            ip = ipaddress.ip_address(ascii_host.strip("[]"))
        except ValueError:
            if "." not in ascii_host or ascii_host.startswith(".") or ascii_host.endswith("."):
                raise ValueError("invalid public DNS name")
        else:
            if not ip.is_global:
                raise ValueError("private or special IP blocked")
        return value
    except (ValueError, UnicodeError, OverflowError) as exc:
        raise OwnerDenied("NATIVE_PUBLIC_HTTPS_URL_REQUIRED") from exc


def _pairs_unique(pairs):
    # JSON object_pairs_hook runs on untrusted browser profiles. An explicit
    # case-folded membership set keeps duplicate protection linear rather than
    # comparing every new key against all preceding keys (quadratic DoS).
    out = {}
    seen = set()
    for key, value in pairs:
        if type(key) is not str:
            raise OwnerHold("BOOKMARK_JSON_DUPLICATE_MEMBER")
        folded = key.casefold()
        if folded in seen:
            raise OwnerHold("BOOKMARK_JSON_DUPLICATE_MEMBER")
        seen.add(folded)
        out[key] = value
    return out


class P01WindowsOwnerPorts:
    """Tiny OS adapters registered only in the existing native PACK01 host."""
    def __init__(self, *, native_permission: Callable,
                 native_stop: Callable, native_select_url: Callable,
                 native_select_bookmarks: Callable,
                 native_select_update: Callable,
                 native_select_cache: Callable,
                 windows_ready: Callable = lambda: platform.system() == "Windows",
                 browser_open: Callable = webbrowser.open_new_tab,
                 winget_run: Callable = subprocess.run,
                 monotonic_time: Callable = time.time):
        fields = (native_permission, native_stop, native_select_url,
                  native_select_bookmarks, native_select_update, native_select_cache,
                  windows_ready, browser_open, winget_run, monotonic_time)
        if not all(callable(v) for v in fields):
            raise OwnerHold("TRUSTED_NATIVE_OWNER_CALLBACKS_REQUIRED")
        self.permission, self.stop = native_permission, native_stop
        self.select_url, self.select_bookmarks = native_select_url, native_select_bookmarks
        self.select_update, self.select_cache = native_select_update, native_select_cache
        self.windows_ready, self.browser_open = windows_ready, browser_open
        self.winget_run, self.clock = winget_run, monotonic_time

    def available(self) -> bool:
        try:
            return self.windows_ready() is True and self.stop() is False
        except Exception:
            return False

    def _gate(self, session, route: str, payload: dict):
        if type(payload) is not dict or payload:
            raise OwnerDenied("NO_WEB_SELECTED_WINDOWS_TARGET")
        if not self.available():
            raise OwnerHold("WINDOWS_NATIVE_OR_STOP_HOLD")
        if self.permission(session, route) is not True:
            raise OwnerDenied("FRESH_NATIVE_PERMISSION_REQUIRED")

    def _recheck(self, session, route):
        if self.stop() is not False or self.permission(session, route) is not True:
            raise OwnerDenied("NATIVE_CONSENT_REVOKED_OR_STOPPED")

    def open_browser(self, session, payload: dict):
        self._gate(session, "browser.open", payload)
        target = _https_url(self.select_url(session))
        self._recheck(session, "browser.open")
        if self.browser_open(target) is not True:
            raise OwnerHold("SYSTEM_BROWSER_LAUNCH_NOT_CONFIRMED")
        # A launch request is not a page-load proof. If consent was revoked
        # during the OS callback do not return an affirmative host receipt.
        self._recheck(session, "browser.open")
        return {"status": "SYSTEM_BROWSER_OPEN_REQUESTED_NOT_PAGE_LOADED", "accepted": False}

    def bookmarks(self, session, payload: dict):
        self._gate(session, "browser.bookmarks", payload)
        chosen = self.select_bookmarks(session)
        if not isinstance(chosen, tuple) or len(chosen) != 2:
            raise OwnerHold("NATIVE_BOOKMARK_SELECTION_REQUIRED")
        localappdata, path = chosen
        root = _plain(localappdata)
        target = _plain(path, must_file=True)
        relative = target.relative_to(root) if target.is_relative_to(root) else None
        if (relative is None or len(relative.parts) != 5 or
            relative.parts[:2] not in (("Microsoft", "Edge"), ("Google", "Chrome")) or
            relative.parts[2] != "User Data" or
            not re.fullmatch(r"(?:Default|Profile [0-9]{1,3})", relative.parts[3]) or
            relative.parts[4] != "Bookmarks"):
            raise OwnerDenied("UNAPPROVED_BROWSER_BOOKMARK_PATH")
        # Do not follow a new symlink or accept a swapped bookmark file between
        # owner path selection and read. This is source hardening; Windows reparse
        # and directory TOCTOU still require independent native tests.
        try:
            chosen_stat = target.lstat()
            if chosen_stat.st_size > MAX_BOOKMARK_FILE or not stat.S_ISREG(chosen_stat.st_mode):
                raise OwnerHold("BOOKMARK_FILE_SIZE_LIMIT")
            self._recheck(session, "browser.bookmarks")
            with target.open("rb") as stream:
                opened_stat = os.fstat(stream.fileno())
                if (not stat.S_ISREG(opened_stat.st_mode) or
                    (chosen_stat.st_dev, chosen_stat.st_ino) !=
                    (opened_stat.st_dev, opened_stat.st_ino) or
                    getattr(opened_stat, "st_file_attributes", 0) &
                    getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
                    raise OwnerHold("BOOKMARK_FILE_SWAPPED_BEFORE_READ")
                raw = stream.read(MAX_BOOKMARK_FILE + 1)
                finished_stat = os.fstat(stream.fileno())
            current_stat = target.lstat()
        except OSError as exc:
            raise OwnerHold("BOOKMARK_READ_FAILED") from exc
        if len(raw) > MAX_BOOKMARK_FILE:
            raise OwnerHold("BOOKMARK_FILE_SIZE_CHANGED")
        identity = lambda x: (x.st_dev, x.st_ino, x.st_size, x.st_mtime_ns)
        if (identity(chosen_stat) != identity(opened_stat) or
            identity(opened_stat) != identity(finished_stat) or
            identity(finished_stat) != identity(current_stat) or
            not stat.S_ISREG(current_stat.st_mode)):
            raise OwnerHold("BOOKMARK_FILE_CHANGED_DURING_READ")
        try:
            obj = json.loads(raw, object_pairs_hook=_pairs_unique)
        except (ValueError, UnicodeError, RecursionError) as exc:
            raise OwnerHold("INVALID_BROWSER_BOOKMARK_JSON") from exc
        items = []
        stack = [(obj.get("roots", {}), 0)] if type(obj) is dict else []
        while stack and len(items) < MAX_BOOKMARKS:
            node, depth = stack.pop()
            if depth > 12:
                raise OwnerHold("BOOKMARK_TREE_TOO_DEEP")
            if type(node) is dict:
                title, url = node.get("name"), node.get("url")
                if type(title) is str and type(url) is str and len(title) <= 200:
                    try: clean_url = _https_url(url)
                    except OwnerDenied: pass
                    else: items.append({"title": title, "url": clean_url})
                for k, value in reversed(list(node.items())):
                    if k in ("children", "bookmark_bar", "other", "synced") and type(value) in (list, dict):
                        stack.append((value, depth + 1))
            elif type(node) is list:
                if len(node) > 10000:
                    raise OwnerHold("BOOKMARK_TREE_TOO_LARGE")
                stack.extend((entry, depth + 1) for entry in reversed(node))
        self._recheck(session, "browser.bookmarks")
        return {"status": "LOCAL_BOOKMARKS_READ_WITH_NATIVE_PERMISSION",
                "items": items, "truncated": len(items) >= MAX_BOOKMARKS,
                "accepted": False}

    def update(self, session, payload: dict):
        self._gate(session, "system.update", payload)
        plan = self.select_update(session)
        if (type(plan) is not TrustedUpdatePlan or type(plan.package_id) is not str or
                not PACKAGE.fullmatch(plan.package_id) or type(plan.approved_package_ids) is not frozenset or
                plan.package_id not in plan.approved_package_ids or type(plan.sha256) is not str or
                not SHA64.fullmatch(plan.sha256)):
            raise OwnerDenied("NATIVE_PINNED_WINGET_PLAN_REQUIRED")
        executable = _plain(plan.winget, must_file=True)
        if executable.name.lower() != "winget.exe":
            raise OwnerHold("WINGET_EXECUTABLE_REQUIRED")
        if sha256(executable.read_bytes()).hexdigest() != plan.sha256.lower():
            raise OwnerHold("WINGET_BINARY_SHA_DRIFT")
        self._recheck(session, "system.update")
        args = (str(executable), "upgrade", "--id", plan.package_id, "--exact",
                "--silent", "--accept-package-agreements", "--accept-source-agreements",
                "--disable-interactivity")
        # The result contract uses exit code only. Do not buffer unbounded
        # WinGet stdout/stderr in process memory or expose package logs to JS.
        try:
            proc = self.winget_run(args, shell=False, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   timeout=900, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise OwnerHold("WINGET_EXECUTION_FAILED_OR_TIMED_OUT") from exc
        self._recheck(session, "system.update")
        if type(proc.returncode) is not int or proc.returncode != 0:
            raise OwnerHold("WINGET_UPDATE_NOT_CONFIRMED")
        return {"status": "WINGET_EXIT_ZERO_NEEDS_INSTALLED_VERSION_ATTESTATION",
                "accepted": False}

    def pc_control(self, session, payload: dict):
        self._gate(session, "system.pc_control", payload)
        chosen = self.select_cache(session)
        if not isinstance(chosen, tuple) or len(chosen) != 3:
            raise OwnerHold("TRUSTED_NOX_CACHE_PLAN_REQUIRED")
        localappdata, root_candidate, mode = chosen
        if mode not in ("inspect", "clean"):
            raise OwnerDenied("UNSUPPORTED_NATIVE_PC_CONTROL_MODE")
        base = _plain(localappdata)
        folder = _plain(root_candidate)
        if not folder.is_relative_to(base) or folder.relative_to(base).parts != ("NOX-HELION", "cache"):
            raise OwnerDenied("ONLY_NOX_OWNED_CACHE_ALLOWED")
        marker = _plain(folder / ".nox-owner", must_file=True)
        if marker.read_bytes() != b"NOXHELION.P01 V16\n":
            raise OwnerHold("NOX_CACHE_OWNERSHIP_MARKER_INVALID")
        candidates = []
        count = 0
        budget = 0
        for p in folder.iterdir():
            count += 1
            if count > 1024:
                raise OwnerHold("CACHE_SCAN_BOUNDED")
            if not CACHE_NAME.fullmatch(p.name):
                continue
            try:
                stat1 = p.lstat()
            except OSError:
                continue
            if (not stat.S_ISREG(stat1.st_mode) or
                    getattr(stat1, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400) or
                    stat1.st_size < 0 or self.clock() - stat1.st_mtime < 86400):
                continue
            budget += stat1.st_size
            if budget > MAX_CACHE_BYTES or len(candidates) >= MAX_CACHE_FILES:
                raise OwnerHold("CACHE_CLEAN_BOUNDED")
            candidates.append((p, stat1))
        if mode == "inspect":
            self._recheck(session, "system.pc_control")
            return {"status": "NOX_CACHE_INSPECT_ONLY", "eligibleFiles": len(candidates),
                    "eligibleBytes": budget, "accepted": False}
        cleaned, reclaimed = 0, 0
        for p, old in candidates:
            self._recheck(session, "system.pc_control")
            try: new = p.lstat()
            except OSError: continue
            if (not stat.S_ISREG(new.st_mode) or
                    (old.st_dev, old.st_ino, old.st_size, old.st_mtime_ns) !=
                    (new.st_dev, new.st_ino, new.st_size, new.st_mtime_ns) or
                    getattr(new, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
                continue
            # Windows native owner must still prevent concurrent path replacement;
            # independently verify junction/reparse/TOCTOU behavior before acceptance.
            try: p.unlink()
            except OSError: continue
            cleaned += 1
            reclaimed += new.st_size
        return {"status": "NOX_OWNED_CACHE_CLEANUP_REQUIRES_NATIVE_QA",
                "deletedFiles": cleaned, "reclaimedBytes": reclaimed, "accepted": False}

    def register(self, existing_host, *, receipt: str) -> frozenset[str]:
        """Atomic four-route P01 source bind via pre-existing PACK01 policy."""
        if not self.available():
            raise OwnerHold("WINDOWS_NATIVE_CALLBACKS_UNAVAILABLE")
        from native_bridge import bind_owner_methods
        return bind_owner_methods(existing_host, 1, self, {
            "browser.open": "open_browser", "browser.bookmarks": "bookmarks",
            "system.update": "update", "system.pc_control": "pc_control"},
            receipt=receipt, probe=self.available)
