#!/usr/bin/env python3
r"""Merge the EXISTING NOX WEB and CHAT sources into isolated, auditable staging.

No live writes to C:\NOX\helion, training, OneHost, S03, Ollama, or port 8766.
An output ZIP is a SOURCE candidate only; Windows E2E is a separate release gate.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import shutil
import sys
import zipfile
from pathlib import Path, PurePosixPath

ROUTES = ("index.html", "chat.html", "memory.html", "training.html",
          "models.html", "system.html", "settings.html", "projects.html",
          "cinema.html", "install.html")
CHAT_MAIN = frozenset(("chat.html", "memory.html"))
NO_OVERWRITE = frozenset(("index.html", "nox-home.mjs", "nox-orbit-original.js",
                          "nox-orbit-14.css", "nox-engines/physical-worlds-v7.mjs"))
MAX_FILES = 20000
MAX_UNCOMPRESSED = 3 * 1024**3
MAX_ZIP_RATIO = 20000
STATIC_SUFFIXES = frozenset((".html", ".htm", ".js", ".mjs", ".css", ".json", ".wasm",
    ".svg", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".avif",
    ".mp3", ".wav", ".ogg", ".mp4", ".webm", ".woff", ".woff2", ".ttf",
    ".glb", ".gltf", ".ktx2", ".bin", ".vtt", ".ico"))
WINDOWS_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
                    *(f"LPT{i}" for i in range(1, 10))}
QA_REQUIRED = ("NOX_ONEPASS.mjs", "START_NOX_ONEPASS.cmd", "NOX_LIVE_ONEHOST_E2E.mjs")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def digest_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fp:
        for part in iter(lambda: fp.read(1024 * 1024), b""):
            h.update(part)
    return h.hexdigest()


def safe_archive_name(name: str) -> str:
    """Windows-safe and portable: reject traversal, ADS, device names and aliases."""
    if not name or "\\" in name or name.startswith("/") or "\x00" in name or ":" in name:
        raise ValueError("NOX_UNSAFE_ARCHIVE_ENTRY: " + repr(name))
    bits = name.split("/")
    if (len(bits) > 25 or any(not p or p in (".", "..") or p.endswith((" ", "."))
                              for p in bits)
            or any(p.split(".")[0].upper() in WINDOWS_RESERVED for p in bits)):
        raise ValueError("NOX_UNSAFE_ARCHIVE_ENTRY: " + repr(name))
    return "/".join(bits)


def read_archive(path: Path) -> dict[str, bytes]:
    if not path.is_file():
        raise ValueError("NOX_ARCHIVE_MISSING: " + str(path))
    files, seen, total = {}, set(), 0
    with zipfile.ZipFile(path) as z:
        for info in z.infolist():
            if info.is_dir():
                continue
            name = safe_archive_name(info.filename)
            canonical = name.casefold()
            if canonical in seen:
                raise ValueError("NOX_CASEFOLD_ZIP_COLLISION: " + name)
            seen.add(canonical)
            if info.flag_bits & 1:
                raise ValueError("NOX_ENCRYPTED_ZIP_HOLD: " + name)
            if ((info.external_attr >> 16) & 0o170000) == 0o120000:
                raise ValueError("NOX_SYMLINK_ENTRY_HOLD: " + name)
            if info.file_size > MAX_UNCOMPRESSED:
                raise ValueError("NOX_OVERSIZED_ENTRY: " + name)
            if info.file_size and (not info.compress_size or
                    info.file_size > max(1, info.compress_size) * MAX_ZIP_RATIO):
                raise ValueError("NOX_ZIP_EXPANSION_RATIO_HOLD: " + name)
            total += info.file_size
            if total > MAX_UNCOMPRESSED or len(files) >= MAX_FILES:
                raise ValueError("NOX_ARCHIVE_SIZE_LIMIT")
            files[name] = z.read(info)  # also checks member CRC-32
    return files


def _prefixes(raw: dict[str, bytes], suffix: str) -> set[str]:
    return {path[:-len(suffix)] for path in raw if path.endswith(suffix)}


def site_files(raw: dict[str, bytes], *, required=("index.html",), strict=True):
    candidates = []
    for prefix in _prefixes(raw, "index.html"):
        if not all(prefix + route in raw for route in required):
            continue
        score = sum((prefix + route) in raw for route in ROUTES)
        if strict and score != len(ROUTES):
            continue
        candidates.append((prefix, score))
    if not candidates:
        raise ValueError("NOX_WEB_SITE_ROOT_OR_REQUIRED_PAGES_MISSING")
    candidates.sort(key=lambda a: (-a[1], len(a[0]), a[0]))
    if len(candidates) > 1 and candidates[0][1] == candidates[1][1] and (
        len(candidates[0][0]) == len(candidates[1][0])
    ):
        raise ValueError("NOX_MULTIPLE_EQUIVALENT_WEB_ROOTS_HOLD")
    prefix = candidates[0][0]
    return {name[len(prefix):]: data for name, data in raw.items()
            if name.startswith(prefix) and len(name) > len(prefix)}


def chat_files(raw: dict[str, bytes]):
    """A chat V25 source root MUST contain both the chat and memory entrypoints."""
    prefixes = [p for p in _prefixes(raw, "chat.html") if p + "memory.html" in raw]
    if not prefixes:
        raise ValueError("NOX_CHAT_V25_BOTH_ENTRYPOINTS_REQUIRED")
    prefixes.sort(key=lambda p: (len(p), p))
    if len(prefixes) > 1 and len(prefixes[0]) == len(prefixes[1]):
        raise ValueError("NOX_CHAT_AMBIGUOUS_ROOT_HOLD")
    root = prefixes[0]
    return {name[len(root):]: data for name, data in raw.items()
            if name.startswith(root) and len(name) > len(root)}


def dependencies(file: str, data: bytes):
    """Static local dependency finder; never pretends to resolve arbitrary runtime imports."""
    if not file.lower().endswith((".html", ".htm", ".css", ".js", ".mjs")):
        return set()
    s = data.decode("utf-8", "replace")
    refs = []
    refs.extend(re.findall(
        r'\b(?:src|href|poster|data-src)\s*=\s*["\x27]([^"\x27]+)["\x27]', s, re.I))
    refs.extend(re.findall(
        r'\b(?:from|import)\s*["\x27]([^"\x27]+)["\x27]', s, re.I))
    refs.extend(re.findall(
        r'\b(?:import|require|fetch)\s*\(\s*["\x27]([^"\x27]+)["\x27]', s, re.I))
    refs.extend(re.findall(r'\burl\s*\(\s*["\x27]?([^)"\x27]+)', s, re.I))
    refs.extend(re.findall(r'\b@import\s+["\x27]([^"\x27]+)["\x27]', s, re.I))
    out = set()
    for raw in refs:
        ref = raw.split("#", 1)[0].split("?", 1)[0].strip()
        if (not ref or ref.startswith(("#", "/", "\\", "//")) or
                re.match(r"(?i)^[a-z][a-z0-9+.-]*:", ref)):
            continue
        if not ref.startswith((".", "assets/", "nox-", "scripts/", "styles/", "js/", "css/")) and "/" not in ref:
            # Root-relative bare asset names (e.g. 'app.js') still count.
            if PurePosixPath(ref).suffix.lower() not in STATIC_SUFFIXES:
                continue
        parts = list(PurePosixPath(file).parent.parts)
        if parts == ["."]:
            parts.clear()
        for bit in ref.replace("\\", "/").split("/"):
            if bit in ("", "."):
                continue
            if bit == "..":
                if not parts:
                    raise ValueError("NOX_CHAT_REFERENCE_ESCAPES_SITE: " + file)
                parts.pop()
            else:
                parts.append(bit)
        if parts and PurePosixPath(parts[-1]).suffix.lower() in STATIC_SUFFIXES:
            out.add("/".join(parts))
    return out


def choose_chat_sources(chat25, chat24):
    if not CHAT_MAIN.issubset(chat25):
        raise ValueError("NOX_V25_CHAT_MEMORY_ENTRYPOINTS_REQUIRED")
    combined = dict(chat24)
    combined.update(chat25)
    used, pending = set(), list(sorted(CHAT_MAIN))
    while pending:
        path = pending.pop()
        if path in used or path not in combined:
            continue
        if path not in chat25 and path.lower().endswith((".html", ".htm")):
            raise ValueError("NOX_V24_HTML_NOT_ALLOWED_IN_V25: " + path)
        used.add(path)
        for dep in dependencies(path, combined[path]):
            if dep in combined and dep not in used:
                pending.append(dep)
    return combined, used


def merge(web, chat25, chat24):
    """Return (site, receipt); no file system effects or host operations."""
    combined, selected = choose_chat_sources(chat25, chat24)
    result = dict(web)
    actions, conflicts = [], []
    for path in sorted(selected):
        body = combined[path]
        if path in NO_OVERWRITE:
            if path in web and web[path] != body:
                conflicts.append({"path": path, "reason": "ORIGINAL_D02_PROTECTED"})
            continue
        before = result.get(path)
        if before == body:
            actions.append({"path": path, "action": "IDENTICAL_REUSED"})
        elif path in CHAT_MAIN:
            result[path] = body
            actions.append({"path": path, "action": "V25_ROUTE_REPLACED"})
        elif before is None:
            result[path] = body
            actions.append({"path": path, "action":
                "V25_DEPENDENCY_ADDED" if path in chat25 else "V24_MISSING_DEPENDENCY_ADDED"})
        else:
            conflicts.append({"path": path, "reason": "SHARED_DEPENDENCY_DIFFERENT_SHA",
                              "web_sha256": digest(before), "chat_sha256": digest(body)})
    seen = set()
    for name in result:
        key = name.casefold()
        if key in seen:
            conflicts.append({"path": name, "reason": "WINDOWS_CASE_INSENSITIVE_COLLISION"})
        seen.add(key)
    missing = set()
    # Include dependencies discovered in V25 entrypoints / selected code, but do not
    # claim to resolve computed imports or real OneHost API calls.
    for path in selected:
        if path in combined:
            for dep in dependencies(path, combined[path]):
                if dep not in result and dep not in combined:
                    missing.add((path, dep))
    for source, dep in sorted(missing):
        conflicts.append({"path": source, "reason": "MISSING_STATIC_DEPENDENCY",
                          "dependency": dep})
    for route in ROUTES:
        if route not in result:
            conflicts.append({"path": route, "reason": "REQUIRED_ROUTE_MISSING"})
    if any(result.get(p) != web.get(p) for p in NO_OVERWRITE if p in web):
        raise ValueError("NOX_PROTECTED_D02_SHA_CHANGED")
    receipt = {
        "status": "HOLD_CONFLICTS" if conflicts else "SOURCE_MERGED_PHYSICAL_QA_HOLD",
        "actions": actions,
        "conflicts": conflicts,
        "source_routes": len(ROUTES),
        "selected_chat_dependencies": len(selected - CHAT_MAIN),
        "v24_dependency_count": len((selected - CHAT_MAIN) - set(chat25)),
        "onehost": "NOT_TESTED", "s03": "NOT_TESTED",
        "live_chat": "NOT_TESTED", "windows_gpu": "NOT_TESTED",
        "gpu_training": "UNTOUCHED", "production_modified": False,
        "owner_acceptance": False
    }
    return (None if conflicts else result), receipt


def verify_onepass(path: Path):
    raw = read_archive(path)
    names = {PurePosixPath(p).name for p in raw}
    missing = sorted(set(QA_REQUIRED) - names)
    if missing:
        raise ValueError("NOX_ONEPASS_REQUIRED_FILE_MISSING: " + ",".join(missing))
    return {"source": path.name, "sha256": digest_file(path),
            "zip_members": len(raw), "executed": False,
            "hardware_e2e": "NOT_RUN"}


def output_candidate(dest, merged, receipt, inputs, onepass_path=None):
    if dest.exists():
        raise ValueError("NOX_OUTPUT_ALREADY_EXISTS_NO_OVERWRITE")
    dest.mkdir(parents=True)
    try:
        if merged is not None:
            for name, body in merged.items():
                file = dest / "site" / name
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_bytes(body)
            receipt["files_count"] = len(merged)
            receipt["file_sha256"] = {p: digest(v) for p, v in sorted(merged.items())}
        receipt["inputs"] = {name: {"filename": path.name,
                             "sha256": digest_file(path), "bytes": path.stat().st_size}
                             for name, path in inputs.items()}
        if onepass_path is not None:
            receipt["onepass"] = verify_onepass(onepass_path)
        (dest / "NOX_MERGE_RECEIPT.json").write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (dest / "READ_ME.txt").write_text(
            "NOX original WEB + CHAT V25/V24 staging. Do not deploy over live C:\\NOX.\n"
            "Original D02/14 worlds, S03, STOP, OneHost and trainer require independent Windows QA.\n"
            "A source/CI PASS is NOT GPU-training, runtime, or release acceptance.\n", encoding="utf-8")
        if merged is not None:
            output = dest / "NOX_WEB_WOW_V25_UNIFIED_CANDIDATE.zip"
            with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED,
                                 compresslevel=6) as z:
                for path in sorted((dest / "site").rglob("*")):
                    if path.is_file():
                        z.write(path, "site/" + path.relative_to(dest / "site").as_posix())
                for name in ("NOX_MERGE_RECEIPT.json", "READ_ME.txt"):
                    z.write(dest / name, name)
                if onepass_path is not None:
                    z.write(onepass_path, "qa/NOX_ONEPASS_V2_SOURCE_UNEXECUTED.zip")
            with zipfile.ZipFile(output) as check:
                if check.testzip() is not None:
                    raise ValueError("NOX_CANDIDATE_ZIP_CRC_FAILED")
                for p, original in merged.items():
                    if digest(check.read("site/" + p)) != digest(original):
                        raise ValueError("NOX_CANDIDATE_ZIP_MEMBER_SHA_FAILED: " + p)
            receipt["output_zip_sha256"] = digest_file(output)
            (dest / "NOX_MERGE_RECEIPT.json").write_text(
                json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8")
            # ZIP contains the immutable receipt without output ZIP SHA, because the
            # hash cannot be embedded into its own bytes. External receipt has SHA.
    except BaseException:
        shutil.rmtree(dest, ignore_errors=True)
        raise


def main():
    a = argparse.ArgumentParser(description="NOX WEB + CHAT source merge (staging only)")
    a.add_argument("--web-v25", type=Path, required=True)
    a.add_argument("--chat-v25", type=Path, required=True)
    a.add_argument("--chat-v24", type=Path, required=True)
    a.add_argument("--onepass-v2", type=Path)
    a.add_argument("--output", type=Path, required=True)
    ns = a.parse_args()
    if ns.output.exists():
        raise ValueError("NOX_OUTPUT_ALREADY_EXISTS_NO_OVERWRITE")
    inputs = {"web_v25": ns.web_v25, "chat_v25": ns.chat_v25,
              "chat_v24": ns.chat_v24}
    web = site_files(read_archive(ns.web_v25), strict=True)
    chat25 = chat_files(read_archive(ns.chat_v25))
    chat24 = chat_files(read_archive(ns.chat_v24))
    result, receipt = merge(web, chat25, chat24)
    receipt["policy"] = "NO_LOSS; ONE_NOX; SINGLE_S03; NO_AUTO_PROMOTE"
    output_candidate(ns.output, result, receipt, inputs, ns.onepass_v2)
    print(json.dumps({"status": receipt["status"],
                      "conflicts": len(receipt["conflicts"]),
                      "staging": str(ns.output)}, ensure_ascii=False))
    return 0 if result is not None else 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, zipfile.BadZipFile, OSError) as exc:
        print("NOX_MERGE_HOLD: " + str(exc), file=sys.stderr)
        sys.exit(2)
