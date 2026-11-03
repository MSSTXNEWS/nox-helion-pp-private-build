"""T06 · Stage existing ORIGINAL Python CLI and PACK01/P02 on an immutable copy.

The original three-part 729-file source archive remains byte-identical.
Call ONLY on the verified disposable extracted Python tree; do not install,
replace user data, spin up another backend, or imply a released EXE.
"""
from __future__ import annotations
import hashlib
import os
import tempfile
from pathlib import Path
import sys
import stat

ROOT=Path(__file__).resolve().parents[2]
ORIGINAL_APP_SHA256="e43a1d1ef6875b75f4d0da1434464f675a77f3fc592941e2bb7f3410dae7cdae"
ADDONS=(
    ('src/nox_selfbuilder/activator_worm.py', 'nox_selfbuilder/activator_worm.py', 'e19eb797aceb4d102bae27bf41783802a0438656'),
    ('coordination/e06/nox_foundation_readiness.py', 'nox_selfbuilder/foundation_readiness.py', '7d20cb6f750610d2e8122698cdcc190db31ce106'),
    ('contracts/p03_download_candidates.json', 'nox_selfbuilder/p03_download_candidates.json', '17053ed67af3bd74c9f767b9d6cc33d66c3eab73'),
    ('contracts/p04_module_candidates.json', 'nox_selfbuilder/p04_module_candidates.json', '3b034ba129c0ed434fe858ac132b1a15ea222d3b'),
    ('coordination/e06/e06_native_stdio_owner.py', 'helion/e06_native_stdio_owner.py', '099c2132a83d2ca05d1cde7e9a2d7e2632db09f0'),
    ('src/nox_selfbuilder/a1_native_command.py', 'nox_selfbuilder/a1_native_command.py', '9797e87208a20d59ff0a51477e90ca317332a92c'),
    ('src/nox_selfbuilder/a1_existing_components.py', 'nox_selfbuilder/a1_existing_components.py', 'eac8f3ffd834e4cf8d5e99996d3b7a55a45b70cc'),
    ('src/nox_selfbuilder/firstboot_coordinator.py', 'nox_selfbuilder/firstboot_coordinator.py', '598f72feff4947e42d2abd9dd83bdad792e2ed8f'),
    ('src/nox_selfbuilder/acquisition_library.py', 'nox_selfbuilder/acquisition_library.py', 'df8f2c8259efdf3d3fff5a344164bced13144fab'),
    ('src/nox_selfbuilder/worms.py', 'nox_selfbuilder/worms.py', '28d788ee753665785ec56f81b7b577b2a3ba4d07'),
    ('src/nox_selfbuilder/worm_autopilot.py', 'nox_selfbuilder/worm_autopilot.py', '7f71acc6836826ed1a04b566486adbd43eba3f95'),
    ('src/nox_selfbuilder/worm_idea_loop.py', 'nox_selfbuilder/worm_idea_loop.py', '2b1aadd1b8880d38af8b4a3498a090c7e83de08e'),
    ('src/nox_selfbuilder/a1_initiative_bridge.py', 'nox_selfbuilder/a1_initiative_bridge.py', 'e11b9e2921368f32e76b859f64994312c4ac012d'),
    ('src/nox_selfbuilder/growth_sandbox.py', 'nox_selfbuilder/growth_sandbox.py', '2c708c2b4aa429e291b045f75d3d4f64521abdae'),
    ('src/nox_selfbuilder/growth_forge.py', 'nox_selfbuilder/growth_forge.py', 'ffdb0239ae54c4c1ac27d0eaceac5153ff6f8069'),
    ('src/nox_selfbuilder/a1_official_catalog.py', 'nox_selfbuilder/a1_official_catalog.py', 'efa4f3c6f44875d90f6c74a914f062fa45d09517'),
    ('src/nox_selfbuilder/a1_wpf_owner_proof.py', 'nox_selfbuilder/a1_wpf_owner_proof.py', 'af42b4737be450039ca7f9c8b3c767aa931ccbf2'),
    ('Packages/P02/worker-python/p02_native_ingress.py', 'p02_native_ingress.py', '885b41b6ba178bcb7da8962334eff2a46e775fcf'),
    ('Packages/P02/worker-python/p02_framed_worker.py', 'p02_framed_worker.py', '5e7df6b7b93b4d01f19ca3ece90266b1eb30611c'),
    ('Packages/P02/worker-python/p02_runtime.py', 'p02_runtime.py', 'c4b68f2c7763288a15709e81404d4afa91f2e8e4'),
    ('Packages/P02/worker-python/p02_chat_bridge.py', 'p02_chat_bridge.py', '0b83e0a391b4cda18b9cb7726607927013c3fa4e'),
    ('Packages/P02/worker-python/p02_onehost.py', 'p02_onehost.py', 'f799e7600e10bc5cd900350527cb40d78ed78bdd'),
    ('proposals/NOX-PACK01-50/native_bridge.py', 'nox_native_bridge.py', 'f26648755a6efa9cbc047ab481af1ba38bb9dc55'),
    ('Packages/P03/Source/python-host/p03_onehost_port.py', 'p03_onehost_port.py', '25ec92c638ff572718acd6ef5354411f91384b93'),
    ('Packages/P03/Source/python-host/catalog30.discovery.json', 'catalog30.discovery.json', 'dea8fb4bfbea61ce845d3ced17b0ef3596f6ae8a'),
    ('src/nox_selfbuilder/__init__.py', 'nox_selfbuilder/__init__.py', '1d0670e51efab53271385c13c156f2809a25adf1'),
    ('src/nox_selfbuilder/background_forge.py', 'nox_selfbuilder/background_forge.py', '9ee9bf7696cd95f9bae0f5b4410b9012910e7cae'),
    ('src/nox_selfbuilder/builder.py', 'nox_selfbuilder/builder.py', '421105f531d4342c880ab0548109fc2e4d1db746'),
    ('src/nox_selfbuilder/complete_builder.py', 'nox_selfbuilder/complete_builder.py', 'f82679bc1ec648135c29abdef964adc3a097e0e6'),
    ('src/nox_selfbuilder/evolution.py', 'nox_selfbuilder/evolution.py', '9c38ca9b1063cda7b0569af7ce622b739213adf4'),
    ('src/nox_selfbuilder/learning.py', 'nox_selfbuilder/learning.py', '3e1cf4f26cfab2505558d67fd5a5bd76ea172e06'),
    ('src/nox_selfbuilder/model_admission.py', 'nox_selfbuilder/model_admission.py', 'a6457f1a1f3b77364a20ff47b3e87a8a9b544b8d'),
    ('src/nox_selfbuilder/onehost_builder.py', 'nox_selfbuilder/onehost_builder.py', 'ed1f3838479f0af63ab8f88f7434e9ea06cd20f6'),
    ('src/nox_selfbuilder/onehost_queue.py', 'nox_selfbuilder/onehost_queue.py', '07d77019cfc4b29001bfc7299b57a9c07a8c6e86'),
    ('src/nox_selfbuilder/onehost_store.py', 'nox_selfbuilder/onehost_store.py', '686911c6102c7ab18a6f07bb2a3b3687fb9c2c45'),
    ('src/nox_selfbuilder/original_store_adapter.py', 'nox_selfbuilder/original_store_adapter.py', '6fcbd9b2f90dc54767728d7ee120ffb7595c019b'),
    ('src/nox_selfbuilder/p02_coder.py', 'nox_selfbuilder/p02_coder.py', '2a9940916424ed851b446f253ed68dab7798e675'),
    ('src/nox_selfbuilder/p04_forge_bridge.py', 'nox_selfbuilder/p04_forge_bridge.py', 'a65c0f4bf5e04d18d5e90eec56a7ed46b3a3accf'),
    ('src/nox_selfbuilder/release_governor.py', 'nox_selfbuilder/release_governor.py', '4a43dd2adffec3f31cb9030c3dfeb1da596e34ba'),
    ('src/nox_selfbuilder/release_learning.py', 'nox_selfbuilder/release_learning.py', '331cb6f6b1d2a403d6134afbd27770585961018b'),
    ('src/nox_selfbuilder/seed.py', 'nox_selfbuilder/seed.py', '9b3a19cbd985620e9527cf168b02cae0ee12453a'),
    ('src/nox_selfbuilder/source_catalog.py', 'nox_selfbuilder/source_catalog.py', 'f08c7fef62179e9e1ec753cae4f9c68c6b23111e'),
    ('src/nox_selfbuilder/wow_background.py', 'nox_selfbuilder/wow_background.py', 'dc5c1272116163fedf18851eba21d1c69bca7f1a'),
    ('src/nox_selfbuilder/wow_design.py', 'nox_selfbuilder/wow_design.py', '7135576489151bb90dfd1c552746fd723c0ea729'),
    ('src/nox_selfbuilder/wow_onehost_port.py', 'nox_selfbuilder/wow_onehost_port.py', '8101bfb4657e776d519e8a98cfc862709fee1e1c'),
    ('src/nox_selfbuilder/wow_owner_binding.py', 'nox_selfbuilder/wow_owner_binding.py', 'b9dadf87f02b1e3345efb20523a6799f1586423d'),
    ('Packages/P04/train_qlora.py', 'Packages/P04/train_qlora.py', '82fad1f4aec3bc9ebb34958ece3fd5786e1adbea'),
    ('Packages/P04/preflight_local_gpu.py', 'Packages/P04/preflight_local_gpu.py', '50756c056cd298152d2d3da5a9de2ec877f6cb86'),
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

def refuse_reparse_components(root: Path, target: Path) -> None:
    """Reject symlink/junction ancestors in the ORIGINAL disposable stage tree.

    A pinned app.py hash is insufficient if helion/ is a reparse point to an
    external same-byte original. Check source and destination ancestry before
    every stage operation; native Windows installation still requires E07.
    """
    try:
        parts = target.relative_to(root).parts
    except ValueError as exc:
        raise RuntimeError("E06_NATIVE_STAGING_OUTSIDE_ROOT_HOLD") from exc
    current = root
    for name in parts:
        if name in (".", ".."):
            raise RuntimeError("E06_NATIVE_STAGING_NONCANONICAL_PATH_HOLD")
        current = current / name
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            continue
        if (stat.S_ISLNK(metadata.st_mode) or
            bool(getattr(metadata, "st_file_attributes", 0) &
                 getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))):
            raise RuntimeError("E06_NATIVE_STAGING_REPARSE_HOLD:" +
                               str(current.relative_to(root)))


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
    # The named disposable root and all its ancestors must be plain BEFORE
    # resolve() can follow any junction/symlink to an unapproved directory.
    named_root=source.absolute()
    for node in (named_root,*named_root.parents):
        try:
            info=node.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise RuntimeError("E06_NATIVE_STAGING_ROOT_PATH_HOLD") from exc
        if (stat.S_ISLNK(info.st_mode) or
            bool(getattr(info,"st_file_attributes",0) &
                 getattr(stat,"FILE_ATTRIBUTE_REPARSE_POINT",0))):
            raise RuntimeError("E06_NATIVE_STAGING_ROOT_REPARSE_HOLD")
    if not named_root.is_dir():
        raise RuntimeError("E06_NATIVE_STAGING_ROOT_REQUIRED")
    source=named_root.resolve(strict=True)
    app=source/"helion/app.py"
    refuse_reparse_components(source,app)
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
        refuse_reparse_components(ROOT,src)
        refuse_reparse_components(source,target)
        if target.exists() or target.is_symlink() or not target.resolve(strict=False).is_relative_to(source):
            raise RuntimeError("E06_NATIVE_SOURCE_COLLISION_OR_ESCAPE")
        sources.append((target,pinned_bytes(src,blob)))
    updated=text.replace(ARG_ANCHOR,ARG_ANCHOR+"\n"+
        "    parser.add_argument('--native-stdio',action='store_true')\n"+
        "    parser.add_argument('--run-id',type=str)")
    updated=updated.replace(PARSE_ANCHOR,PARSE_ANCHOR+"\n"+STAGED_MODE)
    compile(updated,str(app),"exec")
    # Fail BEFORE mutating the disposable original if ANY pinned Python donor
    # has invalid syntax for the actual interpreter used to stage/package it.
    # Git SHA validates bytes, not Python grammar. Avoid a half-staged loader.
    for target,data in sources:
        if target.suffix.lower() == ".py":
            try:
                compile(data, str(target), "exec")
            except (SyntaxError, ValueError) as exc:
                raise RuntimeError(
                    "E06_NATIVE_PINNED_PYTHON_SYNTAX_HOLD:" +
                    str(target.relative_to(source))) from exc
    # All pinned sources are validated before touching the disposable copy.
    # Roll back ONLY new files created by this call on a failed publication.
    staged_app=updated.encode("utf-8")
    data_by_dest={dest:data for (_rel,dest,_blob),(_target,data) in zip(ADDONS,sources)}
    created=[]
    temp_app=None
    try:
        for target,data in sources:
            refuse_reparse_components(source,target)
            target.parent.mkdir(parents=True,exist_ok=True)
            refuse_reparse_components(source,target)
            with target.open("xb") as f:
                created.append(target)  # Include partial writes in rollback.
                f.write(data)
            refuse_reparse_components(source,target)
            if target.read_bytes()!=data:
                raise RuntimeError("E06_NATIVE_ADDON_READBACK_HOLD")
        refuse_reparse_components(source,app)
        fd,temp_name=tempfile.mkstemp(prefix=".nox-native-",suffix=".tmp",dir=app.parent)
        temp_app=Path(temp_name)
        with os.fdopen(fd,"wb") as f:
            f.write(staged_app)
            f.flush()
            os.fsync(f.fileno())
        refuse_reparse_components(source,temp_app)
        if temp_app.read_bytes()!=staged_app or app.read_bytes()!=original:
            raise RuntimeError("E06_NATIVE_APP_PUBLISH_PREIMAGE_HOLD")
        # Prepare all receipts before the irreversible final app publication.
        receipt = dict(original_app_sha256=ORIGINAL_APP_SHA256,
                staged_app_sha256=hashlib.sha256(staged_app).hexdigest(),
                pinned_addons=len(sources),original_archive_modified=False,
                runtime_data_files=[dict(source=rel, runtime_path=dest,
                    sha256=hashlib.sha256(data_by_dest[dest]).hexdigest(),
                    pyinstaller_destination=str(Path(dest).parent))
                    for rel,dest,_blob in ADDONS
                    if dest.endswith((".json", ".zip")) or dest.startswith("Packages/P04/")
                    or dest == "nox_selfbuilder/a1_native_command.py"
                    or dest == "nox_selfbuilder/a1_existing_components.py"
                    or dest in (
                                "nox_selfbuilder/firstboot_coordinator.py",
                                "nox_selfbuilder/acquisition_library.py",
                                "nox_selfbuilder/worms.py",
                                "nox_selfbuilder/worm_autopilot.py",
                                "nox_selfbuilder/worm_idea_loop.py",
                                "nox_selfbuilder/a1_initiative_bridge.py",
                                "nox_selfbuilder/growth_sandbox.py",
                                "nox_selfbuilder/growth_forge.py",
                                "nox_selfbuilder/a1_official_catalog.py")
                    or dest == "nox_selfbuilder/a1_wpf_owner_proof.py"
                    or dest in ("nox_selfbuilder/activator_worm.py",
                                "nox_selfbuilder/foundation_readiness.py")],
                native_python_source_smoke_verified_separately=True,
                installed_windows_exe_accepted=False)

        refuse_reparse_components(source,app)
        os.replace(temp_app,app)
        temp_app=None
        return receipt
    except BaseException:
        rollback_failed=False
        if temp_app is not None:
            try: temp_app.unlink(missing_ok=True)
            except OSError: rollback_failed=True
        for target in reversed(created):
            try: target.unlink(missing_ok=True)
            except OSError: rollback_failed=True
        if rollback_failed:
            raise RuntimeError("E06_NATIVE_STAGE_ROLLBACK_INCOMPLETE_HOLD")
        raise

if __name__=="__main__":
    if len(sys.argv)!=2:raise SystemExit("USAGE: stage_native_stdio.py ORIGINAL_SOURCE_COPY")
    print(stage(Path(sys.argv[1])))
