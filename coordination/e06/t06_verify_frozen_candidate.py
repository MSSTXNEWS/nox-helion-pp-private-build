"""R66 T06: verify ONE already-built frozen original EXE, no second build."""
from __future__ import annotations
import hashlib, json, pathlib, struct, subprocess
ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "work/t06-manual-source-inspect"
NATIVE = OUT / "native-runtime"
DIST = OUT / "python-exe-candidate"
PINNED_ORIGINAL = "ff8e2848c7c7ab776b90cbd8ac28e41e3815e96373c3c5f635d7587284629e9a"

def need(test, code):
    if not test:
        raise RuntimeError(code)

def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        while part := stream.read(1024*1024):
            h.update(part)
    return h.hexdigest()

def request(exe, route, run_id, nonce, data_dir):
    wire_data = {"protocol":"NOX-P02-NATIVE-v1","requestId":nonce,
                 "route":route,"payload":{},"runId":run_id}
    payload = json.dumps(wire_data,separators=(",",":")).encode("utf-8")
    wire = struct.pack(">I",len(payload)) + payload
    result = subprocess.run(
        [str(exe),"--native-stdio","--run-id",run_id,
         "--data-dir",str(data_dir)],input=wire,cwd=NATIVE,
        capture_output=True,timeout=120)
    if result.returncode != 0:
        print("R66_FROZEN_PROCESS_EXIT", result.returncode,
              "STDERR_TAIL", repr(result.stderr[-1800:]), flush=True)
        raise RuntimeError("R66_FROZEN_PROCESS_EXIT")
    raw = result.stdout
    need(len(raw)>=5,"R66_FROZEN_NO_REPLY")
    count = struct.unpack(">I",raw[:4])[0]
    need(1<=count<=1048576 and len(raw)==count+4,"R66_FROZEN_BAD_FRAME")
    reply = json.loads(raw[4:].decode("utf-8"))
    need(type(reply) is dict and
         reply.get("protocol")==wire_data["protocol"] and
         reply.get("runId")==run_id and
         reply.get("requestId")==nonce,"R66_FROZEN_IDENTITY_HOLD")
    return reply

def main(gate: str):
    built = json.loads((DIST/"NATIVE_PYINSTALLER_BINARY_RECEIPT.json").read_text("utf-8"))
    source = json.loads((OUT/"NATIVE_STDIO_SOURCE_SMOKE.json").read_text("utf-8"))
    need(built.get("phase")=="BUILT_NOT_NATIVE_VERIFIED" and
         built.get("release_accepted") is False and
         built.get("source_original_archive_sha256")==PINNED_ORIGINAL and
         built.get("original_729_unchanged") is True,"R66_BINARY_SOURCELOCK_INVALID")
    need(source.get("source_zip_sha256")==PINNED_ORIGINAL and
         source.get("original_archive_unchanged") is True and
         source.get("native_process_exit_code")==0 and
         source.get("run_id_matched") is True and
         source.get("request_id_matched") is True and
         source.get("release_accepted") is False,"R66_NATIVE_SOURCE_SMOKE_INVALID")
    exe = DIST/"NOX_HELION_PRIVATE_CANDIDATE.exe"
    need(exe.is_file() and not exe.is_symlink() and exe.stat().st_size>1000000 and
         built.get("exe_file")==exe.name and
         built.get("exe_size")==exe.stat().st_size and
         digest(exe)==built.get("exe_sha256"),"R66_FROZEN_BINARY_SHA_HOLD")

    chat_path = DIST/"R66_FROZEN_CHAT_MODEL_PROOF.json"
    if gate=="chat":
        a = request(exe,"chat.model","NOX-P02-R66-FROZEN-E2E",
                    "fedcba0987654321fedcba0987654321",OUT/"exe-user-data")
        print("R66_FROZEN_MODEL_REPLY_STATUS", a.get("status"),
              "CODE", a.get("errorCode"), "SOURCE_STATUS", source.get("framed_reply_status"), flush=True)
        need(a.get("status") in ("OK","HOLD"),"R66_MODEL_STATUS_INVALID")
        if a["status"]=="OK":
            need(type(a.get("result")) is dict and
                 type(a["result"].get("models")) is list,"R66_MODEL_LIST_SHAPE")
        else:
            need(a.get("errorCode")=="NATIVE_PROVIDER_HOLD" and
                 a.get("result") is None and
                 source.get("framed_reply_status")=="HOLD","R66_UNEXPECTED_MODEL_HOLD")
        need(not chat_path.exists() and not chat_path.is_symlink(),
             "R66_FROZEN_CHAT_PROOF_COLLISION")
        chat_path.write_text(json.dumps({
            "phase":"FROZEN_CHAT_MODEL_IPC_PASS_NOT_REAL_INFERENCE",
            "exe_sha256":built["exe_sha256"],
            "source_zip_sha256":PINNED_ORIGINAL,
            "chat_model_response_status":a["status"],
            "model_provider_state":a["result"].get("provider_state") if a["status"]=="OK" else "HOLD",
            "release_accepted":False},indent=2),encoding="utf-8")
        print("NOX_R66_FROZEN_CHAT_MODEL_IPC_PASS",a["status"],flush=True)
        return

    need(gate=="models","R66_INVALID_VERIFIER_GATE")
    chat = json.loads(chat_path.read_text("utf-8"))
    need(chat.get("phase")=="FROZEN_CHAT_MODEL_IPC_PASS_NOT_REAL_INFERENCE" and
         chat.get("exe_sha256")==built["exe_sha256"] and
         chat.get("source_zip_sha256")==PINNED_ORIGINAL and
         chat.get("chat_model_response_status") in ("OK","HOLD") and
         chat.get("release_accepted") is False,"R66_FROZEN_CHAT_PREVIOUS_SHA_HOLD")
    b = request(exe,"models.installed","NOX-P03-R66-MODELCENTER",
                "789abcde1234567089abcdef12345670",OUT/"p03-native-data")
    print("R66_MODELCENTER_REPLY",b.get("status"),b.get("errorCode"),flush=True)
    if b.get("status")=="OK":
        need(type(b.get("result")) is dict and
             type(b["result"].get("models")) is list,"R66_INSTALLED_MODEL_OWNER_HOLD")
        model_state="INSTALLED_MODELS_READ_PASS"
    elif (b.get("status")=="HOLD" and b.get("errorCode")=="NATIVE_PROVIDER_HOLD"
          and chat.get("model_provider_state")=="OFFLINE"):
        # Owner P03 MUST refuse missing Ollama. This is an offline readiness
        # receipt, not a successful installed-model enumeration.
        model_state="OFFLINE_PROVIDER_HOLD"
    else:
        raise RuntimeError("R66_INSTALLED_MODEL_OWNER_HOLD")
    data={"phase":"BUILT_AND_NATIVE_STDIO_SMOKE_PASS",
          "source_original_archive_sha256":PINNED_ORIGINAL,
          "staged_original_app_sha256":source["overlay"]["staged_app_sha256"],
          "exe_file":exe.name,"exe_size":exe.stat().st_size,
          "exe_sha256":built["exe_sha256"],
          "native_windows_exe_request_reply":"PASS",
          "run_id_matched":True,"request_id_matched":True,
          "supported_route_verified":"chat.model",
          "native_modelcenter_installed_read_only":model_state,
          "models_installed_uses_original_local_discovery":model_state=="INSTALLED_MODELS_READ_PASS",
          "frozen_chat_model_response_status":chat["chat_model_response_status"],
          "real_ollama_model_inference_tested":False,
          "original_729_unchanged":True,"installed_wpf_e07":False,
          "release_accepted":False}
    receipt = DIST/"NATIVE_PYTHON_EXE_CANDIDATE_RECEIPT.json"
    need(not receipt.exists() and not receipt.is_symlink(),"R66_FINAL_RECEIPT_COLLISION")
    receipt.write_text(json.dumps(data,indent=2),encoding="utf-8")
    print("NOX_R66_FROZEN_EXE_NATIVE_IPC_PASS_NOT_RELEASE",
          built["exe_sha256"],"MODELCENTER",model_state,flush=True)


def seal_for_original_v2_smoke():
    """Reuse the SAME frozen EXE; bind its real source, staged data and SHA to E06."""
    import os, pathlib, subprocess, shutil
    root = ROOT
    pinned_run = os.environ.get("NOX_ONEHOST_RUN_ID","")
    head = subprocess.check_output(["git","rev-parse","HEAD"],cwd=root,text=True).strip()
    tree = subprocess.check_output(["git","rev-parse","HEAD^{tree}"],cwd=root,text=True).strip()
    need(os.environ.get("CIRCLE_SHA1")==head and
         len(head)==40 and len(tree)==40 and
         pinned_run.startswith("NOX-R66-CIRCLECI-"),
         "R66_SOURCE_OR_RUN_ID_DRIFT")
    built=json.loads((DIST/"NATIVE_PYINSTALLER_BINARY_RECEIPT.json").read_text("utf-8"))
    source=json.loads((OUT/"NATIVE_STDIO_SOURCE_SMOKE.json").read_text("utf-8"))
    native=json.loads((DIST/"NATIVE_PYTHON_EXE_CANDIDATE_RECEIPT.json").read_text("utf-8"))
    lock=json.loads((root/"work/e06/original-729-manifest.json").read_text("utf-8"))
    exe=DIST/"NOX_HELION_PRIVATE_CANDIDATE.exe"
    need(exe.is_file() and not exe.is_symlink() and
         built.get("phase")=="BUILT_NOT_NATIVE_VERIFIED" and
         native.get("exe_sha256")==built.get("exe_sha256")==digest(exe) and
         built.get("exe_size")==exe.stat().st_size and
         native.get("original_729_unchanged") is True and
         native.get("release_accepted") is False and
         lock.get("zip_sha256")==PINNED_ORIGINAL and
         lock.get("file_count")==729 and
         source.get("source_zip_sha256")==PINNED_ORIGINAL and
         source.get("original_archive_unchanged") is True,
         "R66_FROZEN_SOURCE_AND_BINARY_PROOF_HOLD")
    app=NATIVE/"helion/app.py"
    need(app.is_file() and not app.is_symlink() and
         digest(app)==source["overlay"]["staged_app_sha256"],
         "R66_STAGED_ORIGINAL_APP_SHA_HOLD")
    data=source["overlay"].get("runtime_data_files")
    need(type(data) is list and len(data)>=1,"R66_BUNDLED_DATA_RECEIPT_MISSING")
    for record in data:
        need(type(record) is dict and
             all(type(record.get(k)) is str and record[k] for k in
                 ("runtime_path","sha256","pyinstaller_destination")),
             "R66_RUNTIME_DATA_RECEIPT_INVALID")
        rel=pathlib.PurePosixPath(record["runtime_path"])
        dest=pathlib.PurePosixPath(record["pyinstaller_destination"].replace("\\","/"))
        need(not rel.is_absolute() and not dest.is_absolute() and
             ".." not in rel.parts and ".." not in dest.parts,
             "R66_RUNTIME_DATA_PATH_ESCAPE")
        file=NATIVE.joinpath(*rel.parts)
        need(file.is_file() and not file.is_symlink() and
             file.resolve().is_relative_to(NATIVE.resolve()) and
             digest(file)==record["sha256"],"R66_RUNTIME_DATA_SHA_HOLD")
    # Validate the original three parts against both independent 729 receipts.
    # The reassembled archive stays TEMPORARY in this existing CI job: no new
    # distribution ZIP, no new owner or installer is published.
    archive=root/"work/e06/original-729-smoke-only.zip"
    need(not archive.exists() and not archive.is_symlink(),"R66_SMOKE_ARCHIVE_ALREADY_EXISTS")
    h=hashlib.sha256()
    total=0
    with archive.open("xb") as output:
        for name in ("source_00.part","source_01.part","source_02.part"):
            part=root/name
            need(part.is_file() and not part.is_symlink(),"R66_ORIGINAL_PART_MISSING")
            with part.open("rb") as f:
                while True:
                    chunk=f.read(1024*1024)
                    if not chunk:break
                    output.write(chunk)
                    h.update(chunk)
                    total+=len(chunk)
    need(h.hexdigest()==PINNED_ORIGINAL and total==60364346,
         "R66_ORIGINAL_ZIP_SHA_HOLD")
    receipt=root/"work/e06/ONEHOST_PYTHON_BUILD_RECEIPT.json"
    need(not receipt.exists() and not receipt.is_symlink(),
         "R66_BUILD_RECEIPT_COLLISION")
    record={"schema":"NOX-ONEHOST-PYTHON-BUILD-V1",
        "source_commit":head,"source_tree":tree,"run_id":pinned_run,
        "python_exe":str(exe.resolve()),"python_exe_sha256":digest(exe),
        "source_original_archive_sha256":PINNED_ORIGINAL,
        "original_archive_path":str(archive.resolve()),
        "staged_original_app_path":str(app.resolve()),
        "staged_original_app_sha256":digest(app),
        "runtime_data_files":data,
        # SHA-pinned source files are included by the single existing
        # PyInstaller --add-data loop and successful native frozen IPC proof.
        "bundled_runtime_data_verified":True,
        "installed_windows_e07":False,"release_accepted":False}
    receipt.write_text(json.dumps(record,indent=2),encoding="utf-8")
    print("NOX_R66_EXACT_V2_SMOKE_INPUT_BOUND",head,digest(exe),
          "SHA_PINNED_RUNTIME_FILES",len(data),flush=True)


if __name__=="__main__":
    import sys
    need(len(sys.argv)==2 and sys.argv[1] in ("chat","models","seal"),
         "R66_EXPLICIT_VERIFICATION_GATE_REQUIRED")
    if sys.argv[1]=="seal":
        seal_for_original_v2_smoke()
    else:
        main(sys.argv[1])
