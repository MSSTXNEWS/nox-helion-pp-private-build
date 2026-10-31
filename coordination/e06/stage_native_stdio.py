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
ADDONS=(
    ("coordination/e06/e06_native_stdio_owner.py","helion/e06_native_stdio_owner.py","6beaf43cd7b09d703819bb54eb9c53dc71876f0b"),
    ("Packages/P02/worker-python/p02_native_ingress.py","p02_native_ingress.py","842f3d60f9506a7ed54a4cf4e158254bf6617df6"),
    ("Packages/P02/worker-python/p02_framed_worker.py","p02_framed_worker.py","8af1338bee7ebb03ffbb0dd4bfdeed7af7870bc1"),
    ("proposals/NOX-PACK01-50/native_bridge.py","nox_native_bridge.py","63f32a41ee7bc72d248e9b9c26407fa738d9a0f4"),
)
ARG_ANCHOR="    parser.add_argument('--diagnose',action='store_true',help='headless functional contracts check')"
PARSE_ANCHOR="    args=parser.parse_args()"
STAGED_MODE="""    if args.native_stdio:
        if not args.run_id or args.desktop_v23 or args.diagnose or args.infer_local or args.core_runtime_local:
            parser.error('native_stdio_requires_exclusive_trusted_run_id')
        from .e06_native_stdio_owner import serve_existing_store
        with Store(args.data_dir/'helion.sqlite3') as original_store:
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
    app.write_bytes(updated.encode("utf-8"))
    if app.read_bytes()!=updated.encode("utf-8"):
        raise RuntimeError("E06_NATIVE_ORIGINAL_APP_READBACK_HOLD")
    return dict(original_app_sha256=ORIGINAL_APP_SHA256,
                staged_app_sha256=hashlib.sha256(app.read_bytes()).hexdigest(),
                pinned_addons=len(sources),original_archive_modified=False,
                native_python_source_smoke_verified_separately=True,
                installed_windows_exe_accepted=False)

if __name__=="__main__":
    if len(sys.argv)!=2:raise SystemExit("USAGE: stage_native_stdio.py ORIGINAL_SOURCE_COPY")
    print(stage(Path(sys.argv[1])))
