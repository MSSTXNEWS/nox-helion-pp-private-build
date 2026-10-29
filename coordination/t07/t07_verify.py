#!/usr/bin/env python3
"""T07 source-only byte verification. Never builds, installs, extracts to product tree or mutates source."""
import hashlib, json, pathlib, zipfile, tempfile, collections, datetime, sys
ROOT = pathlib.Path(".")
OUT = pathlib.Path("t07-evidence")
OUT.mkdir(exist_ok=True)
PARTS = ("source_00.part", "source_01.part", "source_02.part")
EXPECTED_BYTES = 60364346
EXPECTED_SHA256 = "ff8e2848c7c7ab776b90cbd8ac28e41e3815e96373c3c5f635d7587284629e9a"
EXPECTED_COUNT = 729
receipt = dict(task="T07", status="ACCESS_HOLD", expected_size=EXPECTED_BYTES,
               expected_sha256=EXPECTED_SHA256, expected_count=EXPECTED_COUNT,
               parts=[], physical_members_verified=0, blocker=None,
               run_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
members = []
temp_path = None
try:
    missing = [n for n in PARTS if not (ROOT / n).is_file()]
    if missing:
        raise FileNotFoundError("Original binary sources unavailable: " + ", ".join(missing))
    combined_sha = hashlib.sha256()
    combined_bytes = 0
    with tempfile.NamedTemporaryFile(prefix="t07-joined-", suffix=".zip", delete=False) as tmp:
        temp_path = pathlib.Path(tmp.name)
        for name in PARTS:
            h = hashlib.sha256()
            part_size = 0
            with (ROOT / name).open("rb") as part:
                while chunk := part.read(1048576):
                    tmp.write(chunk)
                    combined_sha.update(chunk)
                    h.update(chunk)
                    combined_bytes += len(chunk)
                    part_size += len(chunk)
            receipt["parts"].append(dict(name=name, size=part_size, sha256=h.hexdigest()))
    receipt["joined_size"] = combined_bytes
    receipt["joined_sha256"] = combined_sha.hexdigest()
    if combined_bytes != EXPECTED_BYTES:
        raise ValueError("JOINED_LENGTH_MISMATCH")
    if combined_sha.hexdigest() != EXPECTED_SHA256:
        raise ValueError("JOINED_SHA256_MISMATCH")
    with zipfile.ZipFile(temp_path) as z:
        files = [i for i in z.infolist() if not i.is_dir()]
        counts = collections.Counter(i.filename for i in files)
        dup = [name for name, count in counts.items() if count != 1]
        receipt["zip_members"] = len(files)
        receipt["duplicates"] = dup
        if len(files) != EXPECTED_COUNT or dup:
            raise ValueError("ZIP_MEMBER_COUNT_OR_DUPLICATE_PATH_MISMATCH")
        for info in files:
            sha = hashlib.sha256()
            n = 0
            with z.open(info) as stream:
                while chunk := stream.read(1048576):
                    sha.update(chunk)
                    n += len(chunk)
            if n != info.file_size:
                raise ValueError("UNCOMPRESSED_SIZE_MISMATCH:" + info.filename)
            members.append(dict(path=info.filename, size=n,
                                sha256=sha.hexdigest(), crc32=f"{info.CRC:08x}"))
            receipt["physical_members_verified"] += 1
    receipt["status"] = "PASS"
except Exception as exc:
    receipt["status"] = "ACCESS_HOLD" if isinstance(exc, FileNotFoundError) else "INTEGRITY_HOLD"
    receipt["blocker"] = f"{type(exc).__name__}: {exc}"
finally:
    if temp_path is not None:
        temp_path.unlink(missing_ok=True)
    (OUT / "t07_729_members.json").write_text(json.dumps(members, ensure_ascii=False, indent=2), encoding="utf8")
    (OUT / "t07_receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf8")
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
sys.exit(0 if receipt["status"] == "PASS" else 2)
