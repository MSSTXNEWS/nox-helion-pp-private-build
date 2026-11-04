"""I2: imported T06 local Windows candidate must never borrow diagnostic/E07 proofs."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

MODULE=Path(__file__).resolve().parents[2]/"coordination/e06/t06_samevm_installed_smoke.py"
SPEC=importlib.util.spec_from_file_location("t06_smoke_i2",MODULE)
smoke=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(smoke)
ROOT=MODULE.parents[2]
COMPILER_SPEC=importlib.util.spec_from_file_location(
    "t06_i2_preflight_owner",MODULE.with_name("t06_compile_original_wpf_p02.py"))
compiler=importlib.util.module_from_spec(COMPILER_SPEC)
COMPILER_SPEC.loader.exec_module(compiler)
ORIGINAL="ff8e2848c7c7ab776b90cbd8ac28e41e3815e96373c3c5f635d7587284629e9a"
R11="90076eba83a213ba2b410632ced3288d41a6691ab63f81ad0520aa3cbbbfcb52"

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def write_json(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value),encoding="utf-8")

class UninstallOwnerImport(unittest.TestCase):
    def test_arbitrary_cwd_uses_both_existing_sibling_functions(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory)/"t06_uninstall_admission.py").write_text(
                "raise AssertionError('SEARCH_PATH_OWNER_EXECUTED')\n",encoding="utf-8")
            script="""
import importlib.util
from pathlib import Path
import sys
before=tuple(sys.path)
source=Path(sys.argv[1])
spec=importlib.util.spec_from_file_location("arbitrary_smoke_alias",source)
smoke=importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)
expected=source.resolve().with_name("t06_uninstall_admission.py")
for name in ("owned_payload_paths","verify_original_uninstall"):
    function=getattr(smoke,name)
    assert function.__name__==name
    assert Path(function.__code__.co_filename).resolve()==expected
assert smoke.owned_payload_paths.__globals__ is smoke.verify_original_uninstall.__globals__
assert tuple(sys.path)==before
"""
            result=subprocess.run([sys.executable,"-c",script,str(MODULE)],
                                  cwd=directory,capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_missing_sibling_cannot_use_uninstall_stub_from_search_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);isolated=root/"isolated";isolated.mkdir()
            source=isolated/MODULE.name;source.write_bytes(MODULE.read_bytes())
            (root/"t06_uninstall_admission.py").write_text(
                "def owned_payload_paths(*args): return ()\n"
                "def verify_original_uninstall(*args): return None\n",encoding="utf-8")
            script="""
import importlib.util
from pathlib import Path
import sys
source=Path(sys.argv[1])
spec=importlib.util.spec_from_file_location("missing_uninstall_owner",source)
smoke=importlib.util.module_from_spec(spec)
try:
    spec.loader.exec_module(smoke)
except FileNotFoundError as error:
    # Compare canonical paths: Windows TEMP can have an 8.3 alias.
    assert Path(error.filename).resolve()==source.resolve().with_name("t06_uninstall_admission.py")
else:
    raise AssertionError("MISSING_UNINSTALL_OWNER_WAS_ACCEPTED")
"""
            result=subprocess.run([sys.executable,"-c",script,str(source)],
                                  cwd=directory,capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)

class BridgeReceiptGate(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root=Path(self.temp.name)
        # Reuse the real reviewed C09 source and existing stage implementation;
        # this creates source-test evidence, never an installed Windows receipt.
        self.build=root/"build"
        r11=self.build/"R11"
        self.preflight=r11/"Installer/Preflight-InstallPath.ps1"
        self.preflight.parent.mkdir(parents=True)
        self.preflight.write_bytes((ROOT/"stage/proposals/P01/C09/Installer/Preflight-InstallPath.ps1").read_bytes())
        compiler.stage_exact_owner_webview2_registry_views(
            r11,ROOT/"coordination/e06/build_onehost_installer.ps1")
        self.payload=root/"payload"
        self.payload.mkdir()
        for name in ["NOX.P01.Shell.exe","Backend/NOX_HELION_PRIVATE_CANDIDATE.exe"]+[
            "Assets/source_%02d.bin"%i for i in range(10)]:
            item=self.payload/name
            item.parent.mkdir(parents=True,exist_ok=True)
            item.write_bytes(("source:"+name).encode())
        manifest={"schema":"NOX_P01_PAYLOAD_SHA256_V1","entrypoint":"NOX.P01.Shell.exe",
                  "files":[{"path":p.relative_to(self.payload).as_posix(),
                            "bytes":p.stat().st_size,"sha256":digest(p)}
                           for p in sorted(self.payload.rglob("*")) if p.is_file()]}
        write_json(self.payload/"payload.sha256.json",manifest)
        self.setup=root/"NOX-HELION-V16-ONEHOST-CANDIDATE-SETUP.exe"
        self.setup.write_bytes(b"MZ synthetic test fixture -- never install")
        self.receipt=root/"ONEHOST_CANDIDATE_RECEIPT.json"
        self.native=root/"NATIVE_PYTHON_EXE_CANDIDATE_RECEIPT.json"
        self.original=root/"work/t06-manual-source-inspect/NATIVE_STDIO_SOURCE_SMOKE.json"
        self.source={"schema":"NOX-E06-ONEHOST-CANDIDATE-v1",
            "source_zip_sha256":R11,"release_accepted":False,"e07":"NOT_ACCEPTED",
            "webview2_p01_source_git_blob":"e683e30b4e6fc32c31652061c569d6ce77c2cb2e",
            "webview2_p01_preflight_sha256":digest(self.preflight),
            "wpf_source_compilation":"PASS","backend_native_stdio_windows_exe_smoke":"PASS",
            "setup_bytes":self.setup.stat().st_size,"setup_sha256":digest(self.setup),
            "wpf_sha256":digest(self.payload/"NOX.P01.Shell.exe"),
            "backend_sha256":digest(self.payload/"Backend/NOX_HELION_PRIVATE_CANDIDATE.exe"),
            "manifest_sha256":digest(self.payload/"payload.sha256.json")}
        self.py={"phase":"BUILT_AND_NATIVE_STDIO_SMOKE_PASS",
            "native_windows_exe_request_reply":"PASS",
            "native_modelcenter_installed_read_only":"PASS",
            "models_installed_uses_original_local_discovery":True,
            "modelcenter_provider_offline_verified":False,
            "real_ollama_model_inference_tested":False,
            "original_729_unchanged":True,"source_original_archive_sha256":ORIGINAL,
            "installed_wpf_e07":False,"release_accepted":False,
            "exe_file":"NOX_HELION_PRIVATE_CANDIDATE.exe",
            "exe_size":(self.payload/"Backend/NOX_HELION_PRIVATE_CANDIDATE.exe").stat().st_size,
            "exe_sha256":self.source["backend_sha256"]}
        self.source_original={"phase":"ORIGINAL_PYTHON_SOURCE_EXECUTION_WINDOWS",
            "source_zip_sha256":ORIGINAL,"original_archive_unchanged":True,
            "run_id_matched":True,"request_id_matched":True,
            "native_process_exit_code":0,"release_accepted":False}
        self.configure()
        self.stack=patch.multiple(smoke,ROOT=root,BUILD=self.build,PAYLOAD=self.payload,
            CANDIDATE=self.receipt,SETUP=self.setup,NATIVE_PROOF=self.native,
            ON_LOCAL_BRIDGE=True)
        self.stack.start()
        self.addCleanup(self.stack.stop)

    def configure(self):
        write_json(self.receipt,self.source)
        write_json(self.native,self.py)
        write_json(self.original,self.source_original)

    def test_real_local_schema_with_full_payload_identity(self):
        proof=smoke.candidate_gate()
        self.assertEqual(proof["setup_sha256"],digest(self.setup))
        self.assertEqual(proof["manifest_files_checked"],12)
        self.assertNotIn("build_id",proof)

    def test_missing_staged_preflight_rejected(self):
        self.preflight.unlink()
        with self.assertRaisesRegex(RuntimeError,"PREFLIGHT_NOT_STAGED"):
            smoke.candidate_gate()

    def test_changed_staged_preflight_rejected(self):
        self.preflight.write_bytes(self.preflight.read_bytes()+b"\n# unreviewed change\n")
        with self.assertRaisesRegex(RuntimeError,"PREFLIGHT_SOURCELOCK_HOLD"):
            smoke.candidate_gate()

    def test_installer_bytes_tamper_rejected(self):
        self.setup.write_bytes(b"MZ changed while candidate claims old SHA")
        with self.assertRaisesRegex(RuntimeError,"SETUP_SOURCE_IDENTITY"):
            smoke.candidate_gate()

    def test_provider_tag_cannot_replace_frozen_models_route(self):
        self.py["native_modelcenter_installed_read_only"]="HOLD"
        self.configure()
        with self.assertRaisesRegex(RuntimeError,"NATIVE_MODEL_INVENTORY_HOLD"):
            smoke.candidate_gate()

    def test_source_archive_and_false_e07_must_agree(self):
        self.source_original["source_zip_sha256"]="0"*64
        self.configure()
        with self.assertRaisesRegex(RuntimeError,"SOURCE_OR_WPF_SHA"):
            smoke.candidate_gate()
        self.source_original["source_zip_sha256"]=ORIGINAL
        self.source["release_accepted"]=True
        self.configure()
        with self.assertRaisesRegex(RuntimeError,"SETUP_SOURCE_IDENTITY"):
            smoke.candidate_gate()

    def test_manifest_path_escape_and_unlisted_binary_rejected(self):
        m=json.loads((self.payload/"payload.sha256.json").read_text("utf-8"))
        m["files"][0]["path"]="../outside"
        write_json(self.payload/"payload.sha256.json",m)
        self.source["manifest_sha256"]=digest(self.payload/"payload.sha256.json")
        self.configure()
        with self.assertRaisesRegex(RuntimeError,"PAYLOAD_PATH_INVALID"):
            smoke.candidate_gate()

if __name__=="__main__":
    unittest.main()
