#!/usr/bin/env python3
"""Plan or explicitly build one ZIP64 of downloaded artifacts; never install/run them."""
from __future__ import annotations

import argparse
import contextlib
import copy
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import struct
import time
import zipfile

CHUNK = 1024 * 1024
RESERVE = 8 * 1024**3
ALLOWANCE = 16 * 1024**2
STATUS = "DOWNLOADED_SET_WITHOUT_PRIMARY_WEIGHTS"


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def safe_name(name):
    p = PurePosixPath(name)
    if (not name or p.is_absolute() or ".." in p.parts or "\\" in name
            or "\x00" in name or name != p.as_posix() or name.endswith("/")):
        raise ValueError(f"Unsafe archive name: {name!r}")
    return name


def refresh_coordination(plan, directory):
    """Explicitly snapshot the owner's latest coordination documents, not binaries."""
    plan = copy.deepcopy(plan)
    directory = Path(directory).resolve(strict=True)
    root = plan.get("archive_root", "NOX_UNIFIED")
    referenced = set()
    for entry in plan["entries"]:
        source = entry["source"]
        if source["kind"] != "file":
            continue
        path = Path(source["path"])
        if path.parent.resolve() != directory:
            continue
        before = path.stat()
        sha = digest(path)
        after = path.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError(f"Coordination document changed during snapshot: {path.name}")
        entry.update(size_bytes=after.st_size, sha256=sha)
        source.update(size_bytes=after.st_size, mtime_ns=after.st_mtime_ns)
        referenced.add(path.resolve())
    for path in sorted(directory.iterdir()):
        if (not path.is_file() or path.is_symlink() or path.name.startswith(".")
                or path.suffix not in {".md", ".json", ".txt", ".lock"}
                or path.resolve() in referenced):
            continue
        if path.name in {"LAUNCH_QUEUE_RU.md", "training_notes.md", "TRAINING_NOTES_RU.md"}:
            destination = "02_program/" + path.name
        elif path.name in {"system_runtime_profile.json", "maya_launch_profile.json"}:
            destination = "05_runtime_design/" + path.name
        else:
            destination = "06_evidence/coordination_latest/" + path.name
        before = path.stat()
        sha = digest(path)
        after = path.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError(f"Coordination document changed during snapshot: {path.name}")
        plan["entries"].append({
            "archive_path": f"{root}/{destination}", "category": "coordination_latest",
            "size_bytes": after.st_size, "sha256": sha, "method": "ZIP_STORED",
            "source": {"kind": "file", "path": str(path), "size_bytes": after.st_size,
                       "mtime_ns": after.st_mtime_ns},
            "verification_provenance": "EXPLICIT_LATEST_COORDINATION_SNAPSHOT",
        })
    plan["entries"].sort(key=lambda e: e["archive_path"])
    plan["coordination_refreshed_from"] = str(directory)
    plan["input_file_count"] = len(plan["entries"])
    plan["payload_bytes"] = sum(e["size_bytes"] for e in plan["entries"])
    plan["zip_header_upper_bound_bytes"] = sum(
        200 + 2 * len(e["archive_path"].encode()) for e in plan["entries"]) + 100
    plan["archive_size_upper_bound_bytes"] = (
        plan["payload_bytes"] + plan["zip_header_upper_bound_bytes"] + ALLOWANCE)
    categories = {}
    for entry in plan["entries"]:
        category = categories.setdefault(entry.get("category", "uncategorized"), {"files": 0, "bytes": 0})
        category["files"] += 1
        category["bytes"] += entry["size_bytes"]
    plan["categories"] = categories
    return plan


def preflight(plan, output, reserve=RESERVE):
    if plan.get("status") != STATUS:
        raise ValueError("Plan must explicitly disclose missing primary weights")
    output = Path(output)
    if not output.parent.is_dir():
        raise ValueError("Output parent must already exist")
    reserved = {f"{plan['archive_root']}/{name}" for name in (
        "00_README_PRIMARY_WEIGHTS_MISSING.md", "00_CURRENT_STATUS.json",
        "MANIFEST.json", "SHA256SUMS")}
    names = set()
    zip_cache = {}
    try:
        for entry in plan["entries"]:
            name = safe_name(entry["archive_path"])
            if not name.startswith(plan["archive_root"] + "/"):
                raise ValueError("Member outside configured archive root")
            if name in names or name in reserved:
                raise ValueError(f"Duplicate/reserved archive path: {name}")
            names.add(name)
            if (type(entry["size_bytes"]) is not int or entry["size_bytes"] < 0
                    or not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"])
                    or entry.get("method") != "ZIP_STORED"):
                raise ValueError(f"Invalid size/hash/method: {name}")
            source = entry["source"]
            path = Path(source["path"])
            if path.is_symlink() or not path.is_file():
                raise ValueError(f"Source must be a regular local file: {path}")
            stat = path.stat()
            if (stat.st_size != source["size_bytes"]
                    or stat.st_mtime_ns != source["mtime_ns"]):
                raise ValueError(f"Source changed; refresh reviewed plan: {path}")
            if source["kind"] == "file":
                if stat.st_size != entry["size_bytes"]:
                    raise ValueError(f"Source size differs: {path}")
            elif source["kind"] == "zip_member":
                if str(path) not in zip_cache:
                    zip_cache[str(path)] = zipfile.ZipFile(path)
                info = zip_cache[str(path)].getinfo(source["member"])
                if info.is_dir() or info.file_size != entry["size_bytes"] or info.flag_bits & 1:
                    raise ValueError("Invalid/encrypted source ZIP member")
            else:
                raise ValueError("Unsupported source kind")
    finally:
        for archive in zip_cache.values():
            archive.close()
    for suffix in ("", ".partial", ".offsets.json", ".offsets.json.partial",
                   ".sha256", ".sha256.partial", ".build.json", ".build.json.partial"):
        if Path(str(output) + suffix).exists():
            raise FileExistsError(f"Refusing to overwrite {output}{suffix}")
    payload = sum(e["size_bytes"] for e in plan["entries"])
    header = sum(200 + 2 * len(e["archive_path"].encode()) for e in plan["entries"]) + 100
    upper = payload + header + ALLOWANCE
    free = shutil.disk_usage(output.parent).free
    return {"status": STATUS, "build_performed": False, "input_files": len(names),
            "payload_bytes": payload, "archive_upper_bound_bytes": upper,
            "free_bytes": free, "reserve_bytes": reserve,
            "free_after_upper_bound": free - upper, "fits": free >= upper + reserve}


@contextlib.contextmanager
def source_stream(source):
    if source["kind"] == "file":
        with Path(source["path"]).open("rb") as stream:
            yield stream
    else:
        with zipfile.ZipFile(source["path"]) as archive:
            with archive.open(source["member"]) as stream:
                yield stream


def data_offset(handle, info):
    position = handle.tell()
    handle.flush()
    handle.seek(info.header_offset)
    local = handle.read(30)
    handle.seek(position)
    if len(local) != 30 or local[:4] != b"PK\x03\x04":
        raise ValueError("Invalid local ZIP header")
    filename_bytes, extra_bytes = struct.unpack_from("<HH", local, 26)
    return info.header_offset + 30 + filename_bytes + extra_bytes


def publish_without_overwrite(temporary, target):
    # Same filesystem hard link publishes atomically and refuses an existing destination.
    os.link(temporary, target)
    Path(temporary).unlink()


def build(plan, output, reserve=RESERVE, progress=print):
    output = Path(output)
    check = preflight(plan, output, reserve)
    if not check["fits"]:
        raise OSError("Insufficient disk for ZIP plus required reserve")
    # Verify each retained input ZIP once; no member is expanded to temporary disk.
    checked_archives = set()
    for entry in plan["entries"]:
        source = entry["source"]
        if source["kind"] == "zip_member" and source["path"] not in checked_archives:
            if digest(source["path"]) != source["archive_sha256"]:
                raise ValueError("Input ZIP SHA256 mismatch")
            checked_archives.add(source["path"])
    temporary = Path(str(output) + ".partial")
    root = plan["archive_root"]
    records = []
    started = time.monotonic()
    completed_bytes = 0
    next_report = 1_000_000_000

    def guard(amount):
        if shutil.disk_usage(output.parent).free < reserve + amount + CHUNK:
            raise OSError("DISK_RESERVE_HOLD: partial archive retained")

    with temporary.open("x+b") as handle:
        with zipfile.ZipFile(handle, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
            def write_member(name, stream, size, expected):
                nonlocal completed_bytes, next_report
                info = zipfile.ZipInfo(safe_name(name), date_time=(2026, 11, 16, 0, 0, 0))
                info.compress_type = zipfile.ZIP_STORED
                info.file_size = size
                info.external_attr = 0o100644 << 16
                sha = hashlib.sha256()
                count = 0
                guard(CHUNK)
                with archive.open(info, "w", force_zip64=True) as target:
                    for block in iter(lambda: stream.read(CHUNK), b""):
                        count += len(block)
                        if count > size:
                            raise ValueError(f"Input exceeded expected size: {name}")
                        guard(len(block))
                        target.write(block)
                        sha.update(block)
                        completed_bytes += len(block)
                        if completed_bytes >= next_report:
                            progress(json.dumps({"written_payload_bytes": completed_bytes, "current": name}))
                            next_report += 1_000_000_000
                if count != size or sha.hexdigest() != expected:
                    raise ValueError(f"Member size/SHA256 mismatch: {name}; partial retained")
                stored = archive.getinfo(name)
                records.append({"path": name, "bytes": count, "sha256": sha.hexdigest(),
                                "compression": "ZIP_STORED", "header_offset": stored.header_offset,
                                "data_offset": data_offset(handle, stored), "crc32": f"{stored.CRC:08x}"})

            def generated(name, data):
                import io
                write_member(f"{root}/{name}", io.BytesIO(data), len(data), hashlib.sha256(data).hexdigest())

            status = {"status": STATUS, "coverage": plan["coverage"], "installed": False,
                      "model_started": False, "training_started": False,
                      "primary_weights_missing": True}
            generated("00_CURRENT_STATUS.json", (json.dumps(status, ensure_ascii=False, indent=2) + "\n").encode())
            notice = ("# NOX SYSTEM KIT — PRIMARY_WEIGHTS_MISSING\n\n"
                      "Статус: DOWNLOADED_SET_WITHOUT_PRIMARY_WEIGHTS.\n\n"
                      "Qwen3.5-9B — полный учебный помощник. Основной DeepSeek1017 IQ2_XXS "
                      "представлен манифестом и metadata shard: полные веса отсутствуют. "
                      "Этот архив не является полным комплектом основной модели.\n\n"
                      "72 training wheels используют cu126. CUDA12.9 — отдельный резервный набор "
                      "для сборки Maya; имеющаяся CUDA12.4 также допустима по кандидатным исходникам, "
                      "но успешная сборка на сервере пока не подтверждена. Epistemic LoRA — неподтверждённый для Maya/IQ2_XXS "
                      "кандидат, автоматически не применяется. Установка, запуск и обучение не выполнены.\n\n"
                      "Актуальные документы: 02_program и 05_runtime_design. Приоритет фактического "
                      "состояния: 00_CURRENT_STATUS.json и свежие квитанции. Исторические receipts "
                      "сохраняют состояние на момент их создания.\n")
            generated("00_README_PRIMARY_WEIGHTS_MISSING.md", notice.encode())
            for entry in plan["entries"]:
                with source_stream(entry["source"]) as source:
                    write_member(entry["archive_path"], source, entry["size_bytes"], entry["sha256"])
            internal = {"status": STATUS, "coverage": plan["coverage"],
                        "entries_excluding_this_manifest_and_SHA256SUMS": list(records)}
            generated("MANIFEST.json", (json.dumps(internal, ensure_ascii=False, indent=2) + "\n").encode())
            sums = "".join(f"{record['sha256']}  {record['path']}\n" for record in records)
            generated("SHA256SUMS", sums.encode())
        handle.flush()
        os.fsync(handle.fileno())
    whole_sha = digest(temporary)
    receipt = {"status": STATUS, "archive": output.name, "archive_bytes": temporary.stat().st_size,
               "archive_sha256": whole_sha, "member_count": len(records),
               "elapsed_seconds": round(time.monotonic() - started, 3),
               "reserve_bytes": reserve, "free_disk_bytes_after": shutil.disk_usage(output.parent).free,
               "all_member_sha256_verified": True, "installed": False, "executed": False,
               "training_started": False, "primary_weights_missing": True}
    sidecars = {
        ".offsets.json": (json.dumps({**receipt, "entries": records}, ensure_ascii=False, indent=2) + "\n").encode(),
        ".build.json": (json.dumps(receipt, ensure_ascii=False, indent=2) + "\n").encode(),
        ".sha256": f"{whole_sha}  {output.name}\n".encode(),
    }
    for suffix, content in sidecars.items():
        guard(len(content))
        with Path(str(output) + suffix + ".partial").open("xb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
    publish_without_overwrite(temporary, output)
    for suffix in sidecars:
        publish_without_overwrite(Path(str(output) + suffix + ".partial"), Path(str(output) + suffix))
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--refresh-coordination", type=Path,
                        help="Snapshot current reviewed docs, including newly added launch/runtime files")
    parser.add_argument("--write-refreshed-plan", type=Path)
    parser.add_argument("--build", action="store_true", help="Explicitly write the ZIP; default only checks the plan")
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text())
    if args.refresh_coordination:
        plan = refresh_coordination(plan, args.refresh_coordination)
    if args.write_refreshed_plan:
        with args.write_refreshed_plan.open("x") as handle:
            json.dump(plan, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
    result = build(plan, args.output) if args.build else preflight(plan, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
