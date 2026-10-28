"""E06 read-only deep inventory of the exact original NOX source zip.

No archive member is executed, extracted over repository files or published as a build.
GitHub content/branch state and application source SHA must be kept distinct.
"""
import hashlib
import json
import re
import stat
import sys
import tempfile
import importlib.util
import zipfile
from collections import Counter
from pathlib import Path, PurePosixPath

ROOT=Path(__file__).resolve().parents[2]
PARTS=("source_00.part","source_01.part","source_02.part")
EXPECTED_SHA="ff8e2848c7c7ab776b90cbd8ac28e41e3815e96373c3c5f635d7587284629e9a"
EXPECTED_SIZE=60364346
TARGETS=("MainWindow.xaml","MainWindow.xaml.cs","App.xaml","App.xaml.cs",
         "Contracts/EventV3Bridge.cs","Contracts/events.v3.json",
         "NOX.P01.Shell.csproj","C_RELEASE_SPRINT_BUILD.ps1",
         "Contracts/integration.manifest.json","Assets/index.html")
TEXT_EXTS=(".csproj",".sln",".json",".yml",".yaml",".xaml",".cs",".ps1",".md")
def safe_member(member):
    name=member.filename.replace("\\","/")
    p=PurePosixPath(name)
    if (not name or name.startswith("/") or "\x00" in name or
        ".." in p.parts or p.is_absolute() or ":" in p.parts[0] or
        (stat.S_IFMT(member.external_attr>>16)==stat.S_IFLNK)):
        raise RuntimeError("UNSAFE_ZIP_MEMBER:"+name)
    return name.rstrip("/")
def main():
    out=ROOT/"e06-source-inventory.json"
    # Never reconstruct over an owner archive: private temporary bytes are removed
    # on every success and failure path, including checksum rejection.
    with tempfile.TemporaryDirectory(prefix="nox-deep-inventory-") as temporary:
        file=Path(temporary)/"original.zip"
        sha=hashlib.sha256()
        with file.open("wb") as sink:
            for path in PARTS:
                with (ROOT/path).open("rb") as src:
                    while chunk:=src.read(1024*1024):
                        sha.update(chunk);sink.write(chunk)
        if file.stat().st_size!=EXPECTED_SIZE or sha.hexdigest()!=EXPECTED_SHA:
            raise SystemExit("ARCHIVE_SHA_OR_SIZE_HOLD")
        lines=[]
        with zipfile.ZipFile(file) as archive:
            members=archive.infolist()
            seen=set()
            total=0
            for item in members:
                name=safe_member(item)
                if not name:continue
                low=name.casefold()
                if low in seen:raise RuntimeError("DUPLICATE_ZIP_PATH:"+name)
                seen.add(low)
                total+=item.file_size
                if total>1024*1024*1024:raise RuntimeError("OVERSIZED_ORIGINAL_ARCHIVE")
                if item.file_size > 200*1024*1024:raise RuntimeError("OVERSIZED_MEMBER:"+name)
            wanted=[]
            for item in members:
                name=safe_member(item)
                if not item.is_dir():
                    with archive.open(item) as f:
                        digest=hashlib.sha256()
                        while chunk:=f.read(1024*1024):digest.update(chunk)
                    lines.append(dict(path=name,bytes=item.file_size,sha256=digest.hexdigest()))
                if any(name.endswith(x) for x in TARGETS) or name.endswith(".sln") or name.endswith(".csproj"):
                    wanted.append(name)
            lines.sort(key=lambda a:a["path"])
            source_paths=[x["path"] for x in lines]
            roles={key: [n for n in source_paths if key.lower() in n.lower()][:30]
                   for key in ("MainWindow","Assets/","Persona","Core","Modules/","Contracts/","Packages/","Installer","voice","train","rag","model","NSIS","MAESTRO")}
            samples={}
            for name in wanted[:35]:
                obj=archive.getinfo(name)
                if obj.file_size>1024*1024:continue
                data=archive.read(obj)
                if b"\x00" in data[:1024]:continue
                text=data.decode("utf-8",errors="replace")
                if name.endswith(("MainWindow.xaml.cs","C_RELEASE_SPRINT_BUILD.ps1")):
                    methods=re.findall(r"(?m)^\s*(?:private|public|internal|protected|async|static|\s){1,70}(?:void|Task|bool|string|int|[A-Za-z]+)\s+([A-Za-z_]\w*)\s*\(",text)
                    samples[name]={"bytes":len(data),"method_names":methods[:90],"lines_start":text[:1300]}
                else:
                    samples[name]={"bytes":len(data),"lines_start":text[:4000]}
            manifest={"schema":"NOX-E06-ORIGINAL-SOURCE-SCAN-v1",
                      "source_archive_sha256":sha.hexdigest(),"archive_bytes":file.stat().st_size,
                      "source_member_count":len(lines),"uncompressed_bytes":total,
                      "role_paths":roles,"important_sources":wanted,"samples":samples,"members":lines,
                      "integrated":False,"release_accepted":False}
        # Resolve from this script for isolated input roots as well as real checkout.
        canonical=Path(__file__).resolve().parents[1]/"source-lock/verify_original_archive.py"
        spec=importlib.util.spec_from_file_location("nox_inventory_publication",canonical)
        if spec is None or spec.loader is None:
            raise RuntimeError("CANONICAL_ARCHIVE_VALIDATOR_UNAVAILABLE")
        module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.publish_manifest_exclusive(out,manifest)
        print("E06_ARCHIVE_SHA_PASS",sha.hexdigest(),"MEMBERS",len(lines),"UNCOMPRESSED",total)
        for k,names in roles.items():
            print("E06_SOURCE_AREA",k,json.dumps(names[:16]))
        for key,entry in samples.items():
            print("E06_CODE_CONTRACT",key,json.dumps(entry,ensure_ascii=False)[:2400])
        print("E06_INVENTORY_ARTIFACT_BYTES",out.stat().st_size)
if __name__=="__main__":main()
