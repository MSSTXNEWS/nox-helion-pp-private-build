"""MB1 1–7: extract exact existing owner implementation surfaces read-only.

This script does not replace, mock or modify the 729-member Python archive or
original approved WPF/HOME/MENU/WORK. It exports ONLY bounded UTF-8 source
snippets required to reuse real Store/chat, navigation and D02 assets.
"""
from __future__ import annotations
import importlib.util
import hashlib
import io
import json
from pathlib import Path
import zipfile

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/"work/mb1-owner-source"
PYSHA="ff8e2848c7c7ab776b90cbd8ac28e41e3815e96373c3c5f635d7587284629e9a"
WPFZIP="90076eba83a213ba2b410632ced3288d41a6691ab63f81ad0520aa3cbbbfcb52"
PYFILES={
 "helion/app.py","helion/storage.py","helion/desktop_routes.py",
 "helion/core_chat_bridge.py","helion/local_model.py",
 "helion/ai_core_runtime.py","helion/local_voice.py","helion/voice.py",
 "helion/e06_route_adapter.py",
}
ALLOWED={".py",".js",".mjs",".css",".html"}
def require(ok,reason):
    if not ok:raise RuntimeError(reason)
def git_blob(data:bytes)->str:
    return hashlib.sha1(b"blob "+str(len(data)).encode()+b"\x00"+data).hexdigest()
def _owner_part_reader():
    """Reuse the immutable 729 owner's checked descriptor/ancestor reader.

    An archive SHA pins content but does not permit a symlinked parent,
    reparse redirection, or name-to-open-descriptor identity mismatch.
    """
    source = Path(__file__).with_name("verify_original_729_source.py")
    require(source.is_file() and not source.is_symlink(),
            "MB1_SOURCELOCK_OWNER_READER_UNAVAILABLE")
    spec = importlib.util.spec_from_file_location("mb1_verified_owner_reader", source)
    require(spec is not None and spec.loader is not None,
            "MB1_SOURCELOCK_OWNER_READER_INVALID")
    owner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(owner)
    reader = getattr(owner, "_trusted_part_reader", None)
    require(callable(reader), "MB1_SOURCELOCK_OWNER_READER_INVALID")
    return reader


def join_and_verify_python():
    buffer=io.BytesIO();dig=hashlib.sha256()
    reader=_owner_part_reader()
    for name in ("source_00.part","source_01.part","source_02.part"):
        path=ROOT/name
        require(path.is_file() and not path.is_symlink(),"MB1_SOURCE_PART_MISSING")
        with reader(path) as f:
            while block:=f.read(1048576):
                buffer.write(block);dig.update(block)
    require(dig.hexdigest()==PYSHA and buffer.tell()==60364346,
            "MB1_SOURCE_729_SHA256_HOLD")
    buffer.seek(0)
    return buffer
def join_and_verify_wpf():
    reader=_owner_part_reader()
    manifest_path=ROOT/"donors/P01_C07/P01_C07_RECEIPT.json"
    with reader(manifest_path) as stream:
        manifest=json.load(stream)
    combined=io.BytesIO();digest=hashlib.sha256()
    for part in manifest["parts"]:
        f=ROOT/part["path"]
        require(f.is_file() and not f.is_symlink(),"MB1_WPF_PART_MISSING")
        with reader(f) as stream:
            content=stream.read()
        require(len(content)==part["size_bytes"] and
                git_blob(content)==part["git_blob_sha1"],
                "MB1_ORIGINAL_P01_PART_SHA_HOLD")
        digest.update(content);combined.write(content)
    require(digest.hexdigest()==WPFZIP and
            combined.tell()==manifest["original_zip_bytes"],
            "MB1_ORIGINAL_WPF_ZIP_SHA_HOLD")
    combined.seek(0);return combined
def collect(archive,root,select,max_file,total_cap):
    results=[];total=0
    for item in archive.infolist():
        name=item.filename
        if item.is_dir() or not select(name):continue
        parts=Path(name).parts
        require(not name.startswith("/") and "\\" not in name and
                all(x not in (".","..") for x in parts) and
                item.file_size<=max_file,"MB1_SOURCE_MEMBER_PATH_OR_SIZE_HOLD")
        blob=archive.read(item)
        require(len(blob)==item.file_size and
                total+len(blob)<=total_cap,"MB1_SOURCE_EXCERPT_CAP_HOLD")
        # Original raw codepoint bytes, no rewriting, no fake generated UI.
        text=blob.decode("utf-8-sig")
        rel=Path(*parts)
        dest=root/rel;dest.parent.mkdir(parents=True,exist_ok=True)
        require(not dest.exists() and not dest.is_symlink(),
                "MB1_SOURCE_EXTRACTION_COLLISION")
        dest.write_bytes(blob)
        results.append({"path":name,"size":len(blob),
                        "sha256":hashlib.sha256(blob).hexdigest(),
                        "lines":len(text.splitlines())})
        total+=len(blob)
    return results
def main():
    OUT.mkdir(parents=True,exist_ok=False)
    with zipfile.ZipFile(join_and_verify_python()) as arc:
        py=collect(arc,OUT/"python",lambda name:name in PYFILES,
                   max_file=300000,total_cap=1300000)
    with zipfile.ZipFile(join_and_verify_wpf()) as arc:
        def chosen(name):
            if not name.startswith("R11/Assets/"):return False
            rel=name.removeprefix("R11/Assets/")
            if rel=="index.html":return True
            if Path(rel).suffix.lower() not in ALLOWED:return False
            parts=Path(rel).parts
            return (len(parts)<=3 and
                    any(k in rel.lower() for k in
                        ("main","home","core","menu","scene","cinema","style",
                         "app","nox","visual","nav")))
        web=collect(arc,OUT/"wpf",chosen,
                    max_file=400000,total_cap=2500000)
    require(any(row["path"]=="helion/storage.py" for row in py) and
            any(row["path"]=="helion/app.py" for row in py) and
            any(row["path"]=="R11/Assets/index.html" for row in web),
            "MB1_REQUIRED_ORIGINAL_OWNER_SURFACES_ABSENT")
    ledger={"schema":"NOX-MB1-EXACT-OWNER-SOURCE-v1",
            "original_python_sha256":PYSHA,"original_wpf_sha256":WPFZIP,
            "python":py,"approved_html_css_js":web,
            "original_archives_modified":False,"release_accepted":False}
    (OUT/"RECEIPT.json").write_text(json.dumps(ledger,indent=2),"utf-8")
    print("MB1_EXACT_OWNERS_VERIFIED",len(py),len(web),
          "SOURCEREAD_NO_MUTATION",flush=True)
if __name__=="__main__":main()
