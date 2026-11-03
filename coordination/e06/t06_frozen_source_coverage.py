"""Package every admitted native Python addon; inspect the resulting executable.
No new runtime, route, permission, installer or E07 acceptance is introduced.
"""
from __future__ import annotations
import hashlib
import keyword
import re
import stat
from pathlib import Path, PurePosixPath


def _hold(condition, code):
    if not condition:
        raise RuntimeError("T06_PACKAGE_" + code)


def _relative(value):
    _hold(type(value) is str and bool(value) and len(value) <= 512, "PATH_HOLD")
    _hold("\\" not in value and ":" not in value and "\x00" not in value and
          all(part not in ("", ".", "..") for part in value.split("/")), "PATH_HOLD")
    return PurePosixPath(value)


def _plain_file(root, relative):
    root = Path(root).absolute()
    target = root.joinpath(*_relative(relative).parts)
    for node in (target, *target.parents):
        info = node.lstat()
        _hold(not stat.S_ISLNK(info.st_mode) and not
              (getattr(info, "st_file_attributes", 0) & 0x400), "REPARSE_HOLD")
    _hold(target.is_file() and target.resolve().is_relative_to(root.resolve()), "FILE_HOLD")
    return target


def _blob(raw):
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def module_plan(root, addons):
    """Use the existing stage manifest as the sole list; never scan extra code."""
    _hold(type(addons) in (tuple, list) and 0 < len(addons) <= 1000, "ADDONS_HOLD")
    seen, modules, result = set(), set(), []
    for row in addons:
        _hold(type(row) in (tuple, list) and len(row) == 3, "ROW_HOLD")
        source, destination, expected = row
        _relative(source)
        relative = _relative(destination)
        _hold(type(expected) is str and re.fullmatch(r"[0-9a-f]{40}", expected), "PIN_HOLD")
        key = destination.casefold()
        _hold(key not in seen, "DESTINATION_COLLISION")
        seen.add(key)
        # P04 jobs run in their separately approved interpreter and are data,
        # not imports into the OneHost interpreter. Existing data gate covers them.
        if relative.suffix != ".py" or destination.startswith("Packages/P04/"):
            continue
        path = _plain_file(root, destination)
        _hold(path.stat().st_size <= 4 * 1024 * 1024, "SOURCE_SIZE_HOLD")
        raw = path.read_bytes()
        canonical = raw.replace(b"\r\n", b"\n")
        _hold(_blob(raw) == expected or
              (b"\r" not in canonical and _blob(canonical) == expected), "SOURCE_PIN_HOLD")
        compile(raw, destination, "exec")
        parts = list(relative.with_suffix("").parts)
        if parts[-1] == "__init__":
            parts.pop()
        _hold(parts and all(p.isidentifier() and not keyword.iskeyword(p) for p in parts), "MODULE_HOLD")
        module = ".".join(parts)
        _hold(module.casefold() not in modules, "MODULE_COLLISION")
        modules.add(module.casefold())
        result.append({"module": module, "runtime_path": destination,
                       "source_blob": expected, "sha256": hashlib.sha256(raw).hexdigest()})
    _hold(bool(result), "EMPTY_MODULE_PLAN")
    return sorted(result, key=lambda row: row["module"])


def verify_archive_contents(reader, plan, data_files):
    """Read PyInstaller 6.16 CArchive/PYZ indexes and data, never execute code."""
    _hold(type(plan) is list and bool(plan), "EMPTY_MODULE_PLAN")
    frozen, names = set(), {}
    for name, entry in reader.toc.items():
        normalized = name.replace("\\", "/")
        _relative(normalized)
        _hold(normalized.casefold() not in names, "ARCHIVE_NAME_COLLISION")
        names[normalized.casefold()] = name
        if entry[-1] == "z":
            frozen.update(reader.open_embedded_archive(name).toc)
        elif entry[-1] in ("m", "M"):
            frozen.add(name)
    missing = sorted(row["module"] for row in plan if row["module"] not in frozen)
    _hold(not missing, "FROZEN_MODULES_MISSING:" + ",".join(missing)[:1200])
    _hold(type(data_files) is list and bool(data_files), "DATA_PLAN_HOLD")
    checked = set()
    for row in data_files:
        _hold(type(row) is dict, "DATA_RECORD_HOLD")
        rel = row.get("runtime_path")
        _relative(rel)
        _hold(rel.casefold() not in checked, "DATA_DUPLICATE")
        checked.add(rel.casefold())
        expected = row.get("sha256")
        _hold(type(expected) is str and re.fullmatch(r"[0-9a-f]{64}", expected), "DATA_SHA_HOLD")
        name = names.get(rel.casefold())
        _hold(name is not None and reader.toc[name][-1] == "x", "FROZEN_DATA_MISSING:" + rel)
        _hold(0 <= reader.toc[name][2] <= 512 * 1024 * 1024, "FROZEN_DATA_SIZE_HOLD")
        raw = reader.extract(name)
        _hold(type(raw) is bytes and hashlib.sha256(raw).hexdigest() == expected,
              "FROZEN_DATA_SHA_HOLD:" + rel)
    return {"schema": "NOX-T06-FROZEN-SOURCE-COVERAGE-v1",
            "modules_checked": len(plan), "data_files_checked": len(checked),
            "release_accepted": False, "independent_e07": "NOT_RUN"}


def verify_frozen_binary(executable, plan, data_files):
    from PyInstaller.archive.readers import CArchiveReader
    path = Path(executable)
    _plain_file(path.parent, path.name)
    def digest():
        with path.open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest()
    before = digest()
    result = verify_archive_contents(CArchiveReader(str(path)), plan, data_files)
    _hold(before == digest(), "BINARY_CHANGED_DURING_READ")
    result["binary_sha256"] = before
    return result
