"""E06 build stage — immutable R11 source, strictly from pinned owner #1 donor.

Run only on an authorized isolated Windows CI runner. Never replace a source in
the repository or claim E07 acceptance from a diagnostic EXE.
"""
import hashlib
import json
import re
import stat
import zipfile
import importlib.util
from pathlib import Path, PurePosixPath

ROOT=Path(__file__).resolve().parents[2]
RECEIPT=ROOT/"donors/P01_C07/P01_C07_RECEIPT.json"
WORK=ROOT/"work/e06/staged"
R11=WORK/"R11"
RUN="NOX-V16-E06-P01-STAGE-20261028-R03"
CANONICAL_ZIP_VALIDATOR=ROOT/"coordination/source-lock/verify_original_archive.py"
def sha256(data):return hashlib.sha256(data).hexdigest()
def safe(name,metadata):
    if not name or "\\" in name or name.startswith("/") or "\0" in name:
        raise ValueError("UNSAFE_ZIP_PATH")
    p=PurePosixPath(name)
    if p.is_absolute() or ".." in p.parts or ":" in p.parts[0] or stat.S_IFMT(metadata.external_attr>>16)==stat.S_IFLNK:
        raise ValueError("UNSAFE_ZIP_MEMBER:"+name)
    return p
def main():
    lock=json.loads(RECEIPT.read_text(encoding="utf-8"))
    sources=lock["parts"]
    if len(sources)!=28 or sum(p["size_bytes"] for p in sources)!=lock["original_zip_bytes"]:
        raise SystemExit("DONOR_PART_MAP_INCOMPLETE")
    # This existing stage is the only R11 extractor. Reuse the canonical ZIP
    # namespace validator; never fork a weaker second implementation.
    if not CANONICAL_ZIP_VALIDATOR.is_file() or CANONICAL_ZIP_VALIDATOR.is_symlink():
        raise SystemExit("CANONICAL_SOURCE_VALIDATOR_MISSING")
    spec=importlib.util.spec_from_file_location("nox_canonical_zip_names",CANONICAL_ZIP_VALIDATOR)
    if spec is None or spec.loader is None:
        raise SystemExit("CANONICAL_SOURCE_VALIDATOR_UNAVAILABLE")
    canonical=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(canonical)
    if not callable(getattr(canonical,"validate_members",None)):
        raise SystemExit("CANONICAL_ZIP_NAMESPACES_GATE_MISSING")
    WORK.mkdir(parents=True,exist_ok=True)
    if WORK.is_symlink() or R11.is_symlink():
        raise SystemExit("E06_STAGE_REPARSE_ROOT_HOLD")
    temp=WORK/"source-donor-immutable.zip"
    if temp.exists() or temp.is_symlink():
        raise SystemExit("E06_ORIGINAL_DONOR_TEMP_ALREADY_EXISTS")
    total=hashlib.sha256()
    try:
        with temp.open("xb") as stream:
            for item in sources:
                src=ROOT/item["path"]
                if not src.is_file() or src.is_symlink():raise SystemExit("MISSING_PINNED_SOURCE:"+str(src))
                part=src.read_bytes()
                if len(part)!=item["size_bytes"]:raise SystemExit("DONOR_PART_SIZE_MISMATCH")
                gitblob=hashlib.sha1(b"blob "+str(len(part)).encode()+b"\0"+part).hexdigest()
                if gitblob!=item["git_blob_sha1"]:raise SystemExit("DONOR_GIT_SHA1_MISMATCH")
                stream.write(part);total.update(part)
        if temp.stat().st_size!=lock["original_zip_bytes"] or total.hexdigest()!=lock["original_zip_sha256"]:
            raise SystemExit("DONOR_ZIP_SHA256_FAIL")
        with zipfile.ZipFile(temp) as archive:
            # Source ZIP fixed SHA is not enough: file/parent conflicts,
            # casefold paths, special UNIX entries must be rejected BEFORE extraction.
            try:
                canonical.validate_members(archive.infolist())
            except ValueError as exc:
                raise SystemExit("E06_CANONICAL_ZIP_NAMESPACE_HOLD:"+str(exc)) from exc
            seen=set();files=[];uncompressed=0
            for inf in archive.infolist():
                name=safe(inf.filename,inf).as_posix()
                if inf.is_dir():continue
                if name.casefold() in seen:raise SystemExit("DUPLICATE_ARCHIVE_MEMBER")
                seen.add(name.casefold())
                uncompressed+=inf.file_size
                if uncompressed>200*1024*1024 or inf.file_size>64*1024*1024:
                    raise SystemExit("ARCHIVE_SIZE_CAP")
                if name.startswith("R11/"):
                    target=WORK/name
                    # Reject a symlink at any pre-existing parent or leaf.
                    node=target.parent
                    while True:
                        if node.is_symlink():raise SystemExit("E06_STAGE_REPARSE_PARENT:"+name)
                        if node==WORK:break
                        if WORK not in node.parents:raise SystemExit("E06_TARGET_OUTSIDE_STAGE")
                        node=node.parent
                    target.parent.mkdir(parents=True,exist_ok=True)
                    if target.exists() or target.is_symlink():
                        raise SystemExit("TARGET_EXISTS_NO_OVERWRITE:"+name)
                    with archive.open(inf) as reader,target.open("xb") as writer:
                        b=hashlib.sha256()
                        while chunk:=reader.read(1024*1024):
                            b.update(chunk);writer.write(chunk)
                    files.append({"path":name,"bytes":inf.file_size,"sha256":b.hexdigest()})
            if len(files)<75:raise SystemExit("R11_ORIGINAL_MISSING_FILES")
            names={x["path"] for x in files}
            required={"R11/MainWindow.xaml.cs","R11/NOX.P01.Shell.csproj","R11/Assets/index.html",
                      "R11/Installer/NOX-HELION-Setup.nsi","R11/Contracts/EventV3Bridge.cs",
                      "R11/Packages/P04/train_qlora.py"}
            if not required<=names:raise SystemExit("P01_REQUIRED_ASSETS_MISSING:"+repr(required-names))
            report={"schema":"NOX-E06-P01-WINDOWS-DIAGNOSTIC-SOURCE-v1","run_id":RUN,
                    "source_origin":"NOX_V16_E01_TURBO10_C07_HANDOFF.zip","donor_zip_sha256":total.hexdigest(),
                    "original_members":len(files),"uncompressed_bytes":uncompressed,
                    "source_unchanged":True,"diagnostic":True,"release_accepted":False,
                    "artifacts":files}
        lock_out=WORK/"source_lock.json"
        # Do not overwrite a concurrent or historical SourceLock.
        with lock_out.open("x",encoding="utf-8") as receipt:
            receipt.write(json.dumps(report,indent=2)+"\n")
        print("E06_P01_DONOR_HASH_PASS",total.hexdigest())
        print("E06_P01_CANDIDATE_SOURCE_FILES",len(files))
    finally:
        if temp.exists():temp.unlink()
if __name__=="__main__":main()
