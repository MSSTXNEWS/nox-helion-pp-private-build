#!/usr/bin/env python3
"""Fail-closed, read-only SHA-256 audit of the original three NOX ZIP parts."""
from __future__ import annotations
import argparse, contextlib, hashlib, json, os, pathlib, re, stat, sys, tempfile, unicodedata, zipfile

PARTS = ("source_00.part", "source_01.part", "source_02.part")
EXPECTED_SIZE = 60364346
EXPECTED_PART_SIZES = (20971520, 20971520, 18421306)
EXPECTED_PART_GIT_BLOBS = (
    "e484e10d7b4ec9badeaae4c9d3a7e3aee5faa16b",
    "7853cb43ff4ba0ed3023e8d794d8222eedea56a6",
    "cbd9deb30860737f15e2adbaef2eaaf5d607a0de",
)
EXPECTED_SHA256 = "ff8e2848c7c7ab776b90cbd8ac28e41e3815e96373c3c5f635d7587284629e9a"
BAD = re.compile(r'[<>:"|?*\x00-\x1f]')
# Win32 also reserves COM¹/²/³ and LPT¹/²/³; fail closed on ZIP device aliases.
RESERVED = re.compile(r'^(CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³])(?:\..*)?$', re.I)


def _trusted_part_parent(part: pathlib.Path) -> None:
    """Reject symlink/junction ancestry before opening an original ZIP part."""
    parent = part.absolute().parent
    for node in (parent, *parent.parents):
        try:
            attrs = node.lstat()
        except OSError as exc:
            raise ValueError("SOURCE_PART_PARENT_UNAVAILABLE") from exc
        if (not stat.S_ISDIR(attrs.st_mode) or stat.S_ISLNK(attrs.st_mode) or
                getattr(attrs, "st_file_attributes", 0) &
                getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
            raise ValueError("SOURCE_PART_PARENT_REPARSE_OR_UNSAFE")


@contextlib.contextmanager
def _trusted_part_stream(part: pathlib.Path):
    """Pin a regular descriptor and its live name through the entire read."""
    _trusted_part_parent(part)
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    try:
        initial = part.lstat()
    except OSError as exc:
        raise ValueError("SOURCE_PART_LEAF_UNAVAILABLE") from exc
    if (not stat.S_ISREG(initial.st_mode) or stat.S_ISLNK(initial.st_mode)
            or getattr(initial, "st_file_attributes", 0) & reparse):
        raise ValueError("SOURCE_PART_LEAF_NOT_REGULAR")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(part, flags)
    except OSError as exc:
        raise ValueError("SOURCE_PART_UNTRUSTED_OPEN") from exc
    try:
        reader = os.fdopen(fd, "rb")
    except BaseException:
        os.close(fd)
        raise

    def identity(attrs):
        return (attrs.st_dev, attrs.st_ino, attrs.st_size,
                attrs.st_mtime_ns, attrs.st_ctime_ns)

    with reader:
        opened = os.fstat(reader.fileno())

        def same_path():
            try:
                _trusted_part_parent(part)
                live = part.lstat()
            except (OSError, ValueError):
                return False
            return (stat.S_ISREG(live.st_mode) and not stat.S_ISLNK(live.st_mode)
                    and not (getattr(live, "st_file_attributes", 0) & reparse)
                    and identity(live) == identity(opened))

        if identity(initial) != identity(opened) or not same_path():
            raise ValueError("SOURCE_PART_OPEN_IDENTITY_MISMATCH")
        yield reader
        if identity(os.fstat(reader.fileno())) != identity(opened) or not same_path():
            raise ValueError("SOURCE_PART_CHANGED_DURING_READ")

def safe_name(name: str) -> bool:
    # Exactly one trailing slash denotes a directory; // is an ambiguous
    # Windows archive namespace and must fail before any member extraction.
    if (not name or name.startswith("/") or name.endswith("//")
            or "\\" in name or BAD.search(name)
            or unicodedata.normalize("NFC", name) != name):
        return False
    parts = name.rstrip("/").split("/")
    return bool(parts) and all(p not in ("", ".", "..")
                               and not p.endswith((" ", "."))
                               and not RESERVED.match(p) for p in parts)

def validate_members(infos) -> None:
    """One canonical ZIP namespace/type gate, before any member bytes are read.

    Reject explicit file ancestors, implicit-directory -> file conflicts and
    case-insensitive Windows collisions, regardless of ZIP entry ordering.
    """
    explicit = {}
    required_directories = set()
    for info in infos:
        name = info.filename
        if not safe_name(name):
            raise ValueError(f"Unsafe path: {name!r}")
        canonical = name.rstrip("/")
        folded = canonical.casefold()
        is_directory = info.is_dir()
        mode_type = stat.S_IFMT(info.external_attr >> 16) if info.create_system == 3 else 0
        if mode_type not in (0, stat.S_IFREG, stat.S_IFDIR):
            raise ValueError(f"Symlink/special file: {name!r}")
        if (mode_type == stat.S_IFDIR and not is_directory or
                mode_type == stat.S_IFREG and is_directory):
            raise ValueError(f"ZIP entry kind/type mismatch: {name!r}")
        if folded in explicit:
            raise ValueError(f"Duplicate/case collision: {name!r}")
        segments = canonical.split("/")
        ancestors = ["/".join(segments[:i]).casefold()
                     for i in range(1, len(segments))]
        for parent in ancestors:
            if explicit.get(parent) is False:
                raise ValueError(f"File used as parent path: {name!r}")
        if not is_directory and folded in required_directories:
            raise ValueError(f"File conflicts with directory path: {name!r}")
        explicit[folded] = is_directory
        required_directories.update(ancestors)


def audit(directory: pathlib.Path, expected_files: int):
    paths = [directory / p for p in PARTS]
    _trusted_part_parent(paths[0])
    if any(not p.is_file() or p.is_symlink() for p in paths):
        raise ValueError("Missing or nonregular part / symlink detected")
    sizes = [p.stat().st_size for p in paths]
    if sum(sizes) != EXPECTED_SIZE or tuple(sizes) != EXPECTED_PART_SIZES:
        raise ValueError(f"Part sizes mismatch {sizes}; expected {EXPECTED_PART_SIZES}")
    sha = hashlib.sha256()
    part_receipts = []
    with tempfile.TemporaryDirectory(prefix="nox-original-audit-") as tmp:
        out = pathlib.Path(tmp) / "input-original.zip"
        with out.open("wb") as dest:
            for index, p in enumerate(paths):
                part_git = hashlib.sha1(f"blob {sizes[index]}\0".encode("ascii"))
                part_sha256 = hashlib.sha256()
                with _trusted_part_stream(p) as stream:
                    for chunk in iter(lambda: stream.read(1024*1024), b""):
                        sha.update(chunk)
                        part_git.update(chunk)
                        part_sha256.update(chunk)
                        dest.write(chunk)
                actual_part_blob = part_git.hexdigest()
                if actual_part_blob != EXPECTED_PART_GIT_BLOBS[index]:
                    raise ValueError(f"Part Git blob mismatch: {p.name}")
                part_receipts.append({"name": p.name, "bytes": sizes[index],
                                      "git_blob_sha1": actual_part_blob,
                                      "sha256": part_sha256.hexdigest()})
        actual = sha.hexdigest()
        if actual != EXPECTED_SHA256:
            raise ValueError(f"ZIP SHA256 mismatch: {actual}")
        entries, total = [], 0
        with zipfile.ZipFile(out) as z:
            # Validate the ENTIRE namespace before hashing any member data:
            # children can precede their parent in a hostile ZIP.
            validate_members(z.infolist())
            for info in z.infolist():
                name = info.filename
                if info.is_dir():
                    continue
                total += info.file_size
                if total > 4*1024**3 or info.flag_bits & 1:
                    raise ValueError(f"Archive quota/encryption gate: {name!r}")
                digest, count = hashlib.sha256(), 0
                with z.open(info) as stream:
                    for chunk in iter(lambda: stream.read(1024*1024), b""):
                        count += len(chunk); digest.update(chunk)
                if count != info.file_size:
                    raise ValueError(f"Entry length mismatch: {name!r}")
                entries.append({"path": name, "bytes": count, "sha256": digest.hexdigest()})
        if len(entries) != expected_files:
            raise ValueError(f"Expected {expected_files} files, observed {len(entries)}")
    return {"schema": "NOX_ORIGINAL_SOURCE_729_SHA256_V1",
            "status": "SOURCE_ARCHIVE_VERIFIED_ONLY_NOT_E07_RELEASE",
            "zip_bytes": EXPECTED_SIZE, "zip_sha256": actual,
            "parts": part_receipts,
            "file_count": len(entries), "files": entries}


def publish_manifest_exclusive(output: pathlib.Path, data: dict) -> None:
    """Publish an audited receipt atomically, never replacing or following an output.

    The private temp leaf is only linked into place after fsync. A hard-link
    create is atomic and fails if even a dangling destination symlink exists.
    This preserves previous SourceLock/owner receipts during concurrent jobs.
    """
    def require_trusted_parents() -> None:
        for ancestor in (output.parent, *output.parent.parents):
            try:
                info = ancestor.lstat()
            except FileNotFoundError:
                continue
            if (stat.S_ISLNK(info.st_mode) or
                    getattr(info, "st_file_attributes", 0) &
                    getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
                raise ValueError("OUTPUT_PARENT_REPARSE_HOLD")

    require_trusted_parents()
    output.parent.mkdir(parents=True, exist_ok=True)
    require_trusted_parents()
    payload = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                         prefix=".nox-source-audit-", suffix=".tmp",
                                         dir=output.parent, delete=False) as handle:
            temporary = pathlib.Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        # Never os.replace/rename: both can overwrite a concurrent valid receipt.
        # NTFS and POSIX hard-link creation both reject an existing output leaf.
        try:
            os.link(temporary, output)
        except FileExistsError as exc:
            raise ValueError("OUTPUT_EXISTS_NO_OVERWRITE") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--parts-dir", type=pathlib.Path, default=pathlib.Path("."))
    ap.add_argument("--output", type=pathlib.Path, required=True)
    ap.add_argument("--expected-files", type=int, default=729)
    args = ap.parse_args()
    try:
        data = audit(args.parts_dir, args.expected_files)
        publish_manifest_exclusive(args.output, data)
        print(json.dumps({k: v for k, v in data.items() if k != "files"}))
        return 0
    except (ValueError, OSError, zipfile.BadZipFile) as exc:
        print(json.dumps({"status": "HOLD", "reason": str(exc)}), file=sys.stderr)
        return 2

if __name__ == "__main__":
    sys.exit(main())
