"""T06: reuse the REAL Windows-PASS PyInstaller source, without repeated R11
extraction. One private source copy, one local NativeIngress, one exe and proof.
Manual same-VM build only. Neither published release nor GUI E2E acceptance.
"""
from __future__ import annotations
import hashlib,io,json,pathlib,zipfile
root=pathlib.Path(__file__).resolve().parents[2]
out=root/"work/t06-manual-source-inspect"
out.mkdir(parents=True,exist_ok=False)

# The immutable Python app is in the THREE original source parts, not P01_C07.
# Different provenance is essential: do not pretend R11 zip contains run_helion.py.
original_parts=("source_00.part","source_01.part","source_02.part")
original_expected="ff8e2848c7c7ab776b90cbd8ac28e41e3815e96373c3c5f635d7587284629e9a"
original_sha=hashlib.sha256(); original_bytes=io.BytesIO()
for part in original_parts:
    node=root/part
    assert node.is_file() and not node.is_symlink(), "T06_ORIGINAL_PART_ABSENT"
    with node.open("rb") as handle:
        while True:
            chunk=handle.read(1024*1024)
            if not chunk:break
            original_sha.update(chunk)
            original_bytes.write(chunk)
assert original_sha.hexdigest()==original_expected, "T06_ORIGINAL_THREE_PART_SHA_HOLD"

# Run one actual Windows Python source process on an isolated, fully verified
# source COPY. This is not the frozen PyInstaller EXE or installed E07.
import importlib.util, subprocess, sys, struct
from pathlib import PurePosixPath
native_root=out/"native-runtime"
native_root.mkdir(exist_ok=False)
with zipfile.ZipFile(original_bytes) as original:
    nodes=[x for x in original.infolist() if not x.is_dir()]
    total=0
    seen=set()
    for node in nodes:
        name=PurePosixPath(node.filename)
        if (name.is_absolute() or ".." in name.parts or "\\" in node.filename or
            not name.parts or ":" in name.parts[0] or node.filename.casefold() in seen):
            raise RuntimeError("E06_NATIVE_ORIGINAL_ZIP_MEMBER_UNSAFE")
        seen.add(node.filename.casefold())
        total+=node.file_size
        if node.file_size>80000000 or total>750000000:
            raise RuntimeError("E06_NATIVE_ORIGINAL_UNPACK_LIMIT")
    for node in nodes:
        target=native_root/pathlib.Path(*PurePosixPath(node.filename).parts)
        target.parent.mkdir(parents=True,exist_ok=True)
        with original.open(node) as reader,target.open("xb") as output:
            while chunk:=reader.read(1024*1024):
                output.write(chunk)
stage_path=root/"coordination/e06/stage_native_stdio.py"
spec=importlib.util.spec_from_file_location("nox_e06_original_stdio_stage",stage_path)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
overlay_receipt=module.stage(native_root)
run_id="NOX-P02-WINDOWS-NATIVE-SMOKE-20261030"
request={"protocol":"NOX-P02-NATIVE-v1","requestId":"1234567890abcdef1234567890abcdef",
         "route":"chat.model","payload":{},"runId":run_id}
payload=json.dumps(request,separators=(",",":")).encode("utf-8")
wire=struct.pack(">I",len(payload))+payload
data_dir=out/"native-user-data"
result=subprocess.run([sys.executable,"-u",str(native_root/"run_helion.py"),
                       "--native-stdio","--run-id",run_id,"--data-dir",str(data_dir)],
                      input=wire,cwd=native_root,capture_output=True,timeout=30)
if result.returncode!=0:
    print("T06_NATIVE_ORIGINAL_PROCESS_EXIT",result.returncode,
          "STDERR_TAIL",repr(result.stderr[-1200:]),flush=True)
    raise RuntimeError("T06_NATIVE_ORIGINAL_PYTHON_PROCESS_FAILED")
stdout=result.stdout
if len(stdout)<4:raise RuntimeError("T06_NATIVE_ORIGINAL_NO_FRAMED_OUTPUT")
frame_size=int.from_bytes(stdout[:4],"big")
if not 1<=frame_size<=1048576 or len(stdout)!=frame_size+4:
    raise RuntimeError("T06_NATIVE_ORIGINAL_FRAME_BOUNDS_INVALID")
response=json.loads(stdout[4:].decode("utf-8"))
if (response.get("protocol")!="NOX-P02-NATIVE-v1" or
    response.get("runId")!=run_id or
    response.get("requestId")!=request["requestId"] or
    response.get("status") not in ("OK","HOLD")):
    raise RuntimeError("T06_NATIVE_ORIGINAL_RESPONSE_AUTH_MISMATCH")
if response["status"]=="OK":
    body=response.get("result")
    if not isinstance(body,dict) or not isinstance(body.get("models"),list):
        raise RuntimeError("T06_NATIVE_ORIGINAL_MODELS_SHAPE_MISMATCH")
print("T06_NATIVE_ORIGINAL_SOURCE_PROCESS_FRAMED_REPLY",response["status"],flush=True)
(out/"NATIVE_STDIO_SOURCE_SMOKE.json").write_text(json.dumps({
    "phase":"ORIGINAL_PYTHON_SOURCE_EXECUTION_WINDOWS",
    "source_zip_sha256":original_expected,
    "original_archive_unchanged":True,
    "overlay":overlay_receipt,
    "native_process_exit_code":result.returncode,
    "framed_reply_status":response["status"],
    "run_id_matched":True,"request_id_matched":True,
    "built_pyinstaller_exe_tested":False,
    "installed_wpf_e07":False,
    "release_accepted":False},indent=2),encoding="utf-8")

# CI diagnostic only: prove exact original 729 archive + live native framed IPC
# without pretending a source process is a PyInstaller EXE. No output
# mutation or success-fake in the normal build path.
import os
if os.environ.get("NOX_T06_SOURCE_ONLY") == "YES":
    print("NOX_T06_VERIFIED_ORIGINAL_NATIVE_SOURCE_IPC_ONLY_NOT_EXE",flush=True)
    raise SystemExit(0)

# One REAL Windows native EXE candidate from the verified original 729-member
# source copy, with the original CLI patched ONLY inside this disposable copy.
# This is build-evidence, not release or independent E07 acceptance.
import os
candidate_dir=out/"python-exe-candidate"
candidate_dir.mkdir(exist_ok=False)
check=subprocess.run(
    [sys.executable,"-m","PyInstaller","--version"],
    capture_output=True,text=True,timeout=25)
version=(check.stdout.strip() if check.returncode==0 else "")
if version!="6.16.0":
    installed=subprocess.run(
        [sys.executable,"-m","pip","install","--disable-pip-version-check",
         "--no-input","pyinstaller==6.16.0"],
        capture_output=True,text=True,timeout=600)
    print("T06_PINNED_PYINSTALLER_SETUP",installed.returncode,flush=True)
    if installed.returncode!=0:
        print((installed.stdout+"\n"+installed.stderr)[-3000:],flush=True)
        raise RuntimeError("T06_WINDOWS_PINNED_PYINSTALLER_UNAVAILABLE")
verify=subprocess.run(
    [sys.executable,"-m","PyInstaller","--version"],
    capture_output=True,text=True,timeout=25)
if verify.returncode!=0 or verify.stdout.strip()!="6.16.0":
    raise RuntimeError("T06_PYINSTALLER_VERSION_MISMATCH")
# The CLI's native handler is loaded lazily; explicitly preserve it.
exe_name="NOX_HELION_PRIVATE_CANDIDATE"
cmd=[sys.executable,"-m","PyInstaller","--noconfirm","--clean",
     "--onefile","--console","--name",exe_name,
     "--distpath",str(candidate_dir),
     "--workpath",str(out/"pyinstaller-work"),
     "--specpath",str(out/"pyinstaller-spec"),
     "--paths",str(native_root),
     "--hidden-import","helion.e06_native_stdio_owner",
     "--hidden-import","p02_native_ingress",
     "--hidden-import","p02_framed_worker",
     "--hidden-import","nox_native_bridge",
     # Reuse PyInstaller's native package-data collector: the original
     # helion.traits imports traits_seed_64.json via importlib.resources.
     # Keep every original bundled data asset byte-for-byte, never a stub.
     "--collect-data","helion",
     # The legacy owner hashes its own exact source bytes at startup. PyInstaller
     # freezes bytecode, so explicitly include that SHA-evidence source verbatim.
     # Do NOT replace this live proof with a constant or synthetic receipt.
     "--add-data",str(native_root/"helion/e06_native_stdio_owner.py")+os.pathsep+"helion",
     str(native_root/"run_helion.py")]
built=subprocess.run(cmd,cwd=native_root,capture_output=True,text=True,timeout=900)
(out/"PYINSTALLER_WINDOWS_BUILD_LOG.txt").write_text(
    built.stdout+"\nSTDERR:\n"+built.stderr,encoding="utf-8",errors="replace")
print("T06_WINDOWS_PYINSTALLER_BUILD_EXIT",built.returncode,flush=True)
if built.returncode!=0:
    print((built.stdout+"\n"+built.stderr)[-3500:],flush=True)
    raise RuntimeError("T06_ORIGINAL_PYTHON_NATIVE_EXE_BUILD_FAILED")
exe=candidate_dir/(exe_name+".exe")
if not exe.is_file() or exe.stat().st_size<1000000:
    raise RuntimeError("T06_NATIVE_PYTHON_EXE_MISSING_OR_TRUNCATED")
exe_hash=hashlib.sha256(exe.read_bytes()).hexdigest()
# R66 CI: build only the real frozen EXE, with NO claim of IPC or a model.
# The next CircleCI job attaches this SAME binary by SHA and runs the real
# framed-IPC / SQLite acceptance. Normal builder behavior is unchanged.
if os.environ.get("NOX_T06_BUILD_ONLY")=="YES":
    (candidate_dir/"NATIVE_PYINSTALLER_BINARY_RECEIPT.json").write_text(
        json.dumps({"phase":"BUILT_NOT_NATIVE_VERIFIED",
            "exe_file":exe.name,"exe_size":exe.stat().st_size,
            "exe_sha256":exe_hash,"source_original_archive_sha256":original_expected,
            "original_729_unchanged":True,"release_accepted":False},indent=2),
        encoding="utf-8")
    print("NOX_R66_FROZEN_BINARY_BUILT_NOT_IPC_VERIFIED",exe_hash,flush=True)
    raise SystemExit(0)
# EXACT binary P02 request/response on Windows, not an imported Python module.
binary_run_id="NOX-P02-EXE-E2E-20261030"
binary_request=dict(request,runId=binary_run_id,
                    requestId="fedcba0987654321fedcba0987654321")
binary_payload=json.dumps(binary_request,separators=(",",":")).encode("utf-8")
binary_wire=struct.pack(">I",len(binary_payload))+binary_payload
binary_data_dir=out/"exe-user-data"
executed=subprocess.run(
    [str(exe),"--native-stdio","--run-id",binary_run_id,
     "--data-dir",str(binary_data_dir)],
    input=binary_wire,cwd=native_root,
    capture_output=True,timeout=120)
if executed.returncode!=0:
    print("T06_NATIVE_PYTHON_EXE_FAILURE",
          executed.returncode,repr(executed.stderr[-2000:]),flush=True)
    raise RuntimeError("T06_NATIVE_PYTHON_EXE_PROCESS_FAILED")
raw_reply=executed.stdout
if len(raw_reply)<5:
    raise RuntimeError("T06_NATIVE_PYTHON_EXE_NO_FRAMED_REPLY")
reported=int.from_bytes(raw_reply[:4],"big")
if not 1<=reported<=1048576 or len(raw_reply)!=4+reported:
    raise RuntimeError("T06_NATIVE_PYTHON_EXE_FRAMING_INVALID")
answer=json.loads(raw_reply[4:].decode("utf-8"))
# Model discovery in a fresh Windows CI VM commonly has no Ollama listener.
# This is NOT a real-model PASS: allow only the exact provider HOLD also
# observed in the authenticated original Python source probe above.
if (answer.get("protocol")!="NOX-P02-NATIVE-v1" or
    answer.get("runId")!=binary_run_id or
    answer.get("requestId")!=binary_request["requestId"] or
    answer.get("status") not in ("OK","HOLD")):
    raise RuntimeError("T06_NATIVE_PYTHON_EXE_ROUNDTRIP_HOLD")
if answer["status"]=="OK":
    if (type(answer.get("result")) is not dict or
        type(answer["result"].get("models")) is not list):
        raise RuntimeError("T06_NATIVE_PYTHON_EXE_MODELS_INVALID")
elif (answer.get("errorCode")!="NATIVE_PROVIDER_HOLD" or
      response.get("status")!="HOLD" or
      answer.get("result") is not None):
    raise RuntimeError("T06_NATIVE_PYTHON_EXE_UNEXPECTED_HOLD")
frozen_chat_model_status=answer["status"]
# Reuse the original native ModelCenter inventory; verify the SECOND
# permitted route against the actual frozen EXE, not a Python import or UI fake.
p03_request={"protocol":"NOX-P02-NATIVE-v1",
             "requestId":"789abcde1234567089abcdef12345670",
             "route":"models.installed","payload":{},
             "runId":"NOX-P03-MODELS-INSTALLED-WINDOWS"}
p03_payload=json.dumps(p03_request,separators=(",",":")).encode("utf-8")
p03_wire=struct.pack(">I",len(p03_payload))+p03_payload
p03_result=subprocess.run([str(exe),"--native-stdio","--run-id",
    p03_request["runId"],"--data-dir",str(out/"p03-native-data")],
    input=p03_wire,cwd=native_root,capture_output=True,timeout=120)
if p03_result.returncode!=0 or len(p03_result.stdout)<5:
    raise RuntimeError("T06_FROZEN_MODEL_CENTER_PROCESS_HOLD")
p03_size=struct.unpack(">I",p03_result.stdout[:4])[0]
if not 1<=p03_size<=1048576 or len(p03_result.stdout)!=p03_size+4:
    raise RuntimeError("T06_FROZEN_MODEL_CENTER_FRAMING_HOLD")
p03_answer=json.loads(p03_result.stdout[4:].decode("utf-8"))
if (p03_answer.get("protocol")!=p03_request["protocol"] or
    p03_answer.get("requestId")!=p03_request["requestId"] or
    p03_answer.get("runId")!=p03_request["runId"] or
    p03_answer.get("status")!="OK" or
    type(p03_answer.get("result")) is not dict or
    type(p03_answer["result"].get("models")) is not list):
    # Preserve the exact bounded native HOLD code for root-cause diagnostics.
    # Do not output local model names, paths, credentials or full payloads.
    try:
        body=p03_result.stdout[4:]
        parsed=json.loads(body.decode("utf-8")) if body else {}
        code=parsed.get("errorCode","UNKNOWN")
        print("T06_P03_NATIVE_HOLD_CODE",code if isinstance(code,str)
              and len(code)<=100 else "INVALID",flush=True)
    except (UnicodeError,ValueError):
        print("T06_P03_NATIVE_HOLD_CODE","INVALID_FRAME",flush=True)
    raise RuntimeError("T06_FROZEN_MODEL_CENTER_OWNER_ROUTE_HOLD")
p03_receipt=candidate_dir/"NATIVE_PYTHON_EXE_CANDIDATE_RECEIPT.json"
p03_proof={"phase":"BUILT_AND_NATIVE_STDIO_SMOKE_PASS",
    "source_original_archive_sha256":original_expected,
    "staged_original_app_sha256":overlay_receipt["staged_app_sha256"],
    "exe_file":exe.name,"exe_size":exe.stat().st_size,
    "exe_sha256":exe_hash,"native_windows_exe_request_reply":"PASS",
    "run_id_matched":True,"request_id_matched":True,
    "supported_route_verified":"chat.model",
    "frozen_chat_model_response_status":frozen_chat_model_status,
    "real_ollama_model_inference_tested":False,
    "original_729_unchanged":True,"installed_wpf_e07":False,
    "release_accepted":False,
    "native_modelcenter_installed_read_only":"PASS",
    "models_installed_uses_original_local_discovery":True}
# Do not emit a successful build receipt until the SECOND real frozen EXE
# route has completed, even when chat.model correctly reports provider HOLD.
p03_receipt.write_text(json.dumps(p03_proof,indent=2),encoding="utf-8")
print("T06_NATIVE_ORIGINAL_PYINSTALLER_EXE_IPC_OK",exe_hash,
      "P03_MODELS_INSTALLED_PASS",flush=True)
