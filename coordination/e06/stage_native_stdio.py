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
    ('coordination/e06/e06_native_stdio_owner.py', 'helion/e06_native_stdio_owner.py', '2dce8b8a1d68c6ca801e56741aba5d3705674566'),
    ('Packages/P02/worker-python/p02_native_ingress.py', 'p02_native_ingress.py', '3bb6dd7d507bc0a7c917a25025866321503fa5c6'),
    ('Packages/P02/worker-python/p02_framed_worker.py', 'p02_framed_worker.py', '3045af6e93586e393debae2520ea5c289a3b866d'),
    ('Packages/P02/worker-python/p02_runtime.py', 'p02_runtime.py', 'c4b68f2c7763288a15709e81404d4afa91f2e8e4'),
    ('Packages/P02/worker-python/p02_chat_bridge.py', 'p02_chat_bridge.py', '0b83e0a391b4cda18b9cb7726607927013c3fa4e'),
    ('Packages/P02/worker-python/p02_onehost.py', 'p02_onehost.py', 'f799e7600e10bc5cd900350527cb40d78ed78bdd'),
    ('proposals/NOX-PACK01-50/native_bridge.py', 'nox_native_bridge.py', 'f26648755a6efa9cbc047ab481af1ba38bb9dc55'),
    ('Packages/P03/Source/python-host/p03_onehost_port.py', 'p03_onehost_port.py', 'f8992171f6d3e39d449fac4c2103d7530f6f79e2'),
    ('Packages/P03/Source/python-host/catalog30.discovery.json', 'catalog30.discovery.json', 'dea8fb4bfbea61ce845d3ced17b0ef3596f6ae8a'),
    ('src/nox_selfbuilder/__init__.py', 'nox_selfbuilder/__init__.py', '1d0670e51efab53271385c13c156f2809a25adf1'),
    ('src/nox_selfbuilder/background_forge.py', 'nox_selfbuilder/background_forge.py', '9ee9bf7696cd95f9bae0f5b4410b9012910e7cae'),
    ('src/nox_selfbuilder/builder.py', 'nox_selfbuilder/builder.py', '974d383bd2180908d7f343821dd16e6a93925675'),
    ('src/nox_selfbuilder/complete_builder.py', 'nox_selfbuilder/complete_builder.py', '616aedc351171d3c0365b3c6814d9d22c6cd7227'),
    ('src/nox_selfbuilder/evolution.py', 'nox_selfbuilder/evolution.py', '9c38ca9b1063cda7b0569af7ce622b739213adf4'),
    ('src/nox_selfbuilder/learning.py', 'nox_selfbuilder/learning.py', '3e1cf4f26cfab2505558d67fd5a5bd76ea172e06'),
    ('src/nox_selfbuilder/model_admission.py', 'nox_selfbuilder/model_admission.py', '27abfefec3b7347dab008396524bf94dd8c0e0bd'),
    ('src/nox_selfbuilder/onehost_builder.py', 'nox_selfbuilder/onehost_builder.py', 'f2085971020b4288403cc1409ee755693679df37'),
    ('src/nox_selfbuilder/onehost_queue.py', 'nox_selfbuilder/onehost_queue.py', '0342506d58c3c078292d1f25e4cb1ae124b71cee'),
    ('src/nox_selfbuilder/onehost_store.py', 'nox_selfbuilder/onehost_store.py', '686911c6102c7ab18a6f07bb2a3b3687fb9c2c45'),
    ('src/nox_selfbuilder/original_store_adapter.py', 'nox_selfbuilder/original_store_adapter.py', 'e01bd595b32977582fef410abd83de2bd21fc537'),
    ('src/nox_selfbuilder/p02_coder.py', 'nox_selfbuilder/p02_coder.py', '2a9940916424ed851b446f253ed68dab7798e675'),
    ('src/nox_selfbuilder/p04_forge_bridge.py', 'nox_selfbuilder/p04_forge_bridge.py', 'a65c0f4bf5e04d18d5e90eec56a7ed46b3a3accf'),
    ('src/nox_selfbuilder/release_governor.py', 'nox_selfbuilder/release_governor.py', '451d5c17f3ef9ea0a83670ed90fface36512fc36'),
    ('src/nox_selfbuilder/release_learning.py', 'nox_selfbuilder/release_learning.py', '331cb6f6b1d2a403d6134afbd27770585961018b'),
    ('src/nox_selfbuilder/seed.py', 'nox_selfbuilder/seed.py', '9b3a19cbd985620e9527cf168b02cae0ee12453a'),
    ('src/nox_selfbuilder/source_catalog.py', 'nox_selfbuilder/source_catalog.py', '6c2ccccb46085a0e2152dbe989ee95ef3244f8a0'),
    ('src/nox_selfbuilder/wow_background.py', 'nox_selfbuilder/wow_background.py', 'dc5c1272116163fedf18851eba21d1c69bca7f1a'),
    ('src/nox_selfbuilder/wow_design.py', 'nox_selfbuilder/wow_design.py', '7135576489151bb90dfd1c552746fd723c0ea729'),
    ('src/nox_selfbuilder/wow_onehost_port.py', 'nox_selfbuilder/wow_onehost_port.py', '8101bfb4657e776d519e8a98cfc862709fee1e1c'),
    ('src/nox_selfbuilder/wow_owner_binding.py', 'nox_selfbuilder/wow_owner_binding.py', 'b9dadf87f02b1e3345efb20523a6799f1586423d'),
    ('Packages/P04/train_qlora.py', 'Packages/P04/train_qlora.py', '82fad1f4aec3bc9ebb34958ece3fd5786e1adbea'),
    ('Packages/P04/preflight_local_gpu.py', 'Packages/P04/preflight_local_gpu.py', '15d6807033040711ac54c4c9f63432c5653e62bd'),
    ('Packages/P04/merge_qlora_adapter.py', 'Packages/P04/merge_qlora_adapter.py', '51a27181e94cf5e766e2faf943f8aa17ec6418c7'),
    ('assets/NOX_SOUL_CPU_REAL_WEIGHTS_TRAINED_V1_20261022.zip', 'assets/NOX_SOUL_CPU_REAL_WEIGHTS_TRAINED_V1_20261022.zip', '35ee9b4ad6500af6cd219becc4244333c7c5f618'),
)
ARG_ANCHOR="    parser.add_argument('--diagnose',action='store_true',help='headless functional contracts check')"
PARSE_ANCHOR="    args=parser.parse_args()"
STAGED_MODE="""    if args.native_stdio:
        if not args.run_id or args.desktop_v23 or args.diagnose or args.infer_local or args.core_runtime_local:
            parser.error('native_stdio_requires_exclusive_trusted_run_id')
        from .e06_native_stdio_owner import serve_existing_store
        from nox_selfbuilder.onehost_store import OneHostStoreActor
        with OneHostStoreActor(lambda: Store(args.data_dir/'helion.sqlite3')) as original_store:
            return serve_existing_store(original_store, args.run_id, args.data_dir)
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
                runtime_data_files=[dict(source=rel, runtime_path=dest,
                    sha256=hashlib.sha256((source/dest).read_bytes()).hexdigest(),
                    pyinstaller_destination=str(Path(dest).parent))
                    for rel,dest,_blob in ADDONS
                    if dest.endswith((".json", ".zip")) or dest.startswith("Packages/P04/")],
                native_python_source_smoke_verified_separately=True,
                installed_windows_exe_accepted=False)

if __name__=="__main__":
    if len(sys.argv)!=2:raise SystemExit("USAGE: stage_native_stdio.py ORIGINAL_SOURCE_COPY")
    print(stage(Path(sys.argv[1])))
