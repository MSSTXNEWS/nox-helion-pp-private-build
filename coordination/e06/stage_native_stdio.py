"""T06 · Stage existing ORIGINAL Python CLI and PACK01/P02 on an immutable copy.

The original three-part 729-file source archive remains byte-identical.
Call ONLY on the verified disposable extracted Python tree; do not install,
replace user data, spin up another backend, or imply a released EXE.
"""
from __future__ import annotations
import hashlib
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
ORIGINAL_APP_SHA256="e43a1d1ef6875b75f4d0da1434464f675a77f3fc592941e2bb7f3410dae7cdae"
ORIGINAL_STORAGE_SHA256="145f23a7df0cff95c5287cf35edfdbac4831af0357c6c5d8cf4c92fbe9c58f93"
ADDONS=(
    ("coordination/e06/e06_native_stdio_owner.py","helion/e06_native_stdio_owner.py","afd3d369e92fbd1a659f8aafbe80ea7ca77a88a7"),
    ("Packages/P02/worker-python/p02_native_ingress.py","p02_native_ingress.py","842f3d60f9506a7ed54a4cf4e158254bf6617df6"),
    ("Packages/P02/worker-python/p02_framed_worker.py","p02_framed_worker.py","8af1338bee7ebb03ffbb0dd4bfdeed7af7870bc1"),
    ("Packages/P02/worker-python/p02_runtime.py","p02_runtime.py","ac1620ef6584debcea30d9ea169c2cc0a2cd566b"),
    ("Packages/P02/worker-python/p02_history_stable.py","p02_history_stable.py","0ec3a074b17c618b3665b126419d5625d84b99f5"),
    ("proposals/NOX-PACK01-50/native_bridge.py","nox_native_bridge.py","1708ae1b187a9716878c49dfcdb420821cb134df"),
)
ARG_ANCHOR="    parser.add_argument('--diagnose',action='store_true',help='headless functional contracts check')"
PARSE_ANCHOR="    args=parser.parse_args()"
STAGED_MODE="""    if args.native_stdio:
        if not args.run_id or args.desktop_v23 or args.diagnose or args.infer_local or args.core_runtime_local:
            parser.error('native_stdio_requires_exclusive_trusted_run_id')
        from .e06_native_stdio_owner import (
            require_original_v4_before_store, serve_existing_store)
        require_original_v4_before_store(args.data_dir/'helion.sqlite3')
        with Store(args.data_dir/'helion.sqlite3',native_thread_safe=True) as original_store:
            return serve_existing_store(original_store, args.run_id)
"""

def git_blob(raw:bytes)->str:
    return hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()

def pinned_bytes(src:Path, expected:str)->bytes:
    if not src.is_file() or src.is_symlink():
        raise RuntimeError("E06_NATIVE_OWNER_SOURCE_MISSING")
    raw=src.read_bytes()
    if git_blob(raw)==expected:return raw
    if b"\r\n" in raw and b"\r" not in raw.replace(b"\r\n",b""):
        canonical=raw.replace(b"\r\n",b"\n")
        if git_blob(canonical)==expected:return canonical
    raise RuntimeError("E06_NATIVE_OWNER_BLOB_SHA_HOLD:"+str(src))

def stage(source:Path)->dict:
    source=source.resolve(strict=True)
    app=source/"helion/app.py"
    if not app.is_file() or app.is_symlink():
        raise RuntimeError("E06_ORIGINAL_APP_SOURCE_MISSING")
    original=app.read_bytes()
    if hashlib.sha256(original).hexdigest()!=ORIGINAL_APP_SHA256:
        raise RuntimeError("E06_ORIGINAL_APP_PREIMAGE_MISMATCH")
    storage=source/"helion/storage.py"
    if not storage.is_file() or storage.is_symlink():
        raise RuntimeError("E06_ORIGINAL_STORE_SOURCE_MISSING")
    storage_original=storage.read_bytes()
    if hashlib.sha256(storage_original).hexdigest()!=ORIGINAL_STORAGE_SHA256:
        raise RuntimeError("E06_ORIGINAL_STORE_SOURCE_SHA_HOLD")
    original_connect="self.conn = sqlite3.connect(str(self.path), timeout=15)"
    original_ctor="def __init__(self, path: str | Path):"
    storage_text=storage_original.decode("utf-8")
    if storage_text.count(original_connect)!=1 or storage_text.count(original_ctor)!=1:
        raise RuntimeError("E06_ORIGINAL_STORE_NATIVE_ANCHOR_HOLD")
    storage_text=storage_text.replace(original_ctor,
        "def __init__(self, path: str | Path, *, native_thread_safe: bool = False):")
    storage_text=storage_text.replace(original_connect,
        "self.conn = sqlite3.connect(str(self.path), timeout=15, check_same_thread=not native_thread_safe)")
    compile(storage_text,str(storage),"exec")
    text=original.decode("utf-8")
    if text.count(ARG_ANCHOR)!=1 or text.count(PARSE_ANCHOR)!=1 or "--native-stdio" in text:
        raise RuntimeError("E06_ORIGINAL_CLI_ANCHOR_MISMATCH")
    sources=[]
    for rel,dest,blob in ADDONS:
        src=ROOT/rel
        target=source/dest
        if target.exists() or target.is_symlink() or not target.resolve(strict=False).is_relative_to(source):
            raise RuntimeError("E06_NATIVE_SOURCE_COLLISION_OR_ESCAPE")
        sources.append((target,pinned_bytes(src,blob)))
    updated=text.replace(ARG_ANCHOR,ARG_ANCHOR+"\n"+
        "    parser.add_argument('--native-stdio',action='store_true')\n"+
        "    parser.add_argument('--run-id',type=str)")
    updated=updated.replace(PARSE_ANCHOR,PARSE_ANCHOR+"\n"+STAGED_MODE)
    compile(updated,str(app),"exec")
    # All source/addon checks complete before writing any disposable output.
    for target,data in sources:
        target.parent.mkdir(parents=True,exist_ok=True)
        with target.open("xb") as f:f.write(data)
    storage.write_bytes(storage_text.encode("utf-8"))
    app.write_bytes(updated.encode("utf-8"))
    if (app.read_bytes()!=updated.encode("utf-8") or
            storage.read_bytes()!=storage_text.encode("utf-8")):
        raise RuntimeError("E06_NATIVE_ORIGINAL_SOURCE_READBACK_HOLD")
    return dict(original_app_sha256=ORIGINAL_APP_SHA256,
                original_storage_sha256=ORIGINAL_STORAGE_SHA256,
                staged_app_sha256=hashlib.sha256(app.read_bytes()).hexdigest(),
                pinned_addons=len(sources),original_archive_modified=False,
                native_python_source_smoke_verified_separately=True,
                installed_windows_exe_accepted=False)

if __name__=="__main__":
    if len(sys.argv)!=2:raise SystemExit("USAGE: stage_native_stdio.py ORIGINAL_SOURCE_COPY")
    print(stage(Path(sys.argv[1])))
