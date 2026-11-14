"""Physical frozen full-D02 91a6 WPF pixels; never an independent E07 PASS.

Reuse the original, reviewed Windows/GDI capture and immutable producer gates.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import independent_setup_e07 as e07
from probe_full_d02_visual_u13 import PS

SOURCE=e07.NEW_D02_SOURCE_SHA
SETUP_SHA=e07.NEW_D02_SETUP_SHA
BUILD_ID=e07.NEW_D02_BUILD_ID
COUNT=e07.NEW_D02_OWNED_COUNT

def checked_candidate(folder: Path) -> Path:
    root=folder/"e06"/"onehost-wow-diagnostic"
    setup=root/"NOX-HELION-V16-DIAGNOSTIC-SETUP.exe"
    e07.require(e07.clean_dir(folder) and e07.clean_dir(root),
                "D02_91A6_VISUAL_ARTIFACT_DIR_HOLD")
    claim=e07.setup_lock(setup,root/"E07_BUILT_HANDOFF.json",
                         candidate="d02-91a6")
    e07.require(claim.get("source_sha")==SOURCE
                and claim.get("setup_sha256")==SETUP_SHA
                and claim.get("build_id")==BUILD_ID
                and claim.get("setup_bytes")==e07.NEW_D02_SETUP_SIZE,
                "D02_91A6_VISUAL_SOURCE_SETUP_ID_HOLD")
    return setup

def observe(folder:Path,output:Path)->dict:
    e07.require(sys.platform=="win32" and os.environ.get("GITHUB_ACTIONS")=="true"
                and os.environ.get("RUNNER_OS")=="Windows"
                and os.environ.get("RUNNER_ENVIRONMENT")=="github-hosted"
                and os.environ.get("GITHUB_REPOSITORY")==
                    "MSSTXNEWS/nox-helion-pp-private-build",
                "D02_91A6_VISUAL_TRUSTED_RUNNER_HOLD")
    setup=checked_candidate(folder)
    install=subprocess.run([str(setup),"/S"],capture_output=True,timeout=180,
                           check=False)
    e07.require(install.returncode==0,"D02_91A6_VISUAL_INSTALL_HOLD")
    local=Path(os.environ["LOCALAPPDATA"])
    root=local/"Programs"/"NOX HELION"
    _,owned=e07.manifest_owner(root)
    e07.require(len(owned)==COUNT,"D02_91A6_VISUAL_MANIFEST_1011_HOLD")
    exe=root/"NOX.P01.Shell.exe"
    e07.require(exe in owned and e07.clean_file(exe),
                "D02_91A6_VISUAL_OWNED_EXE_HOLD")
    log=local/"NOX_HELION"/"P01"/"logs"/"shell.log"
    start=log.stat().st_size if e07.clean_file(log) else 0
    process=None
    try:
        process=subprocess.Popen([str(exe)],cwd=str(exe.parent),
                                 stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
        hwnd=None;stable=None;deadline=time.monotonic()+80
        while time.monotonic()<deadline and process.poll() is None:
            if e07.clean_file(log):
                with log.open("rb") as stream:
                    size=stream.seek(0,2)
                    e07.require(size>=start,
                                "D02_91A6_VISUAL_SHELL_LOG_ROTATED_HOLD")
                    stream.seek(start)
                    data=stream.read(65536).decode("utf-8",errors="replace")
                flags=e07.wpf_marker_flags(data)
                e07.require(not any(flags.get(k) for k in
                            ("NAV_FAIL","INIT_ERROR","BLOCK_NAV",
                             "WEBVIEW_PROCESS_FAILED")),
                            "D02_91A6_VISUAL_NAV_FATAL_HOLD")
                if flags.get("NAV_OK") and flags.get("P02_ORIGINAL_NATIVE_PIPE_HANDSHAKE_OK"):
                    current=e07.original_wpf_hwnd(process.pid)
                    if current is not None:
                        if hwnd!=current:hwnd=current;stable=time.monotonic()
                        if time.monotonic()-stable>=5:break
            time.sleep(0.3)
        e07.require(hwnd is not None and stable is not None
                    and time.monotonic()-stable>=5 and process.poll() is None,
                    "D02_91A6_VISUAL_STABLE_HWND_HOLD")
        output.mkdir(parents=True,exist_ok=True)
        png=output/"D02_91A6_ORIGINAL_WPF.png"
        ps=PS.replace("__HWND__",str(hwnd)).replace(
            "__DEST__",str(png).replace("'","''"))
        cmd=base64.b64encode(ps.encode("utf-16le")).decode("ascii")
        capture=subprocess.run(["powershell.exe","-NoProfile","-NonInteractive",
            "-EncodedCommand",cmd],capture_output=True,text=True,timeout=50,
            encoding="utf-8",errors="replace",check=False)
        e07.require(capture.returncode==0 and 0<len(capture.stdout)<4096,
                    "D02_91A6_VISUAL_GDI_PROCESS_HOLD")
        pixels=json.loads(capture.stdout.strip())
        e07.require(pixels.get("captured") is True
                    and type(pixels.get("colors")) is int
                    and pixels["colors"]>=12
                    and type(pixels.get("width")) is int
                    and type(pixels.get("height")) is int
                    and 500<=pixels["width"]<=8192
                    and 300<=pixels["height"]<=8192
                    and e07.clean_file(png)
                    and 5000<png.stat().st_size<40000000,
                    "D02_91A6_VISUAL_BLANK_OR_INVALID_HOLD")
        with png.open("rb") as stream:
            digest=hashlib.file_digest(stream,"sha256").hexdigest()
        return {"physical_capture":"PASS","screenshot_sha256":digest,
                "screenshot_name":png.name,
                "screen_dimensions":[pixels["width"],pixels["height"]],
                "sampled_unique_colors":pixels["colors"],
                "first_unmet_gate":"D02_VISUAL_REVIEW_REDUCED_MOTION_AND_FINAL_E07_NOT_RUN"}
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:process.wait(timeout=7)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--artifact-dir",required=True,type=Path)
    ap.add_argument("--out-dir",required=True,type=Path)
    args=ap.parse_args()
    out={"schema":"NOX-D02-91A6-PHYSICAL-VISUAL-v1",
         "source_sha":SOURCE,"setup_sha256":SETUP_SHA,
         "build_id":BUILD_ID,"source_lock_count":729,"manifest_count":COUNT,
         "physical_capture":"HOLD","visual_e07":"HOLD",
         "reduced_motion":"NOT_TESTED","functional_e07":"NOT_RUN",
         "independent_e07":"HOLD","release_accepted":False}
    try:out.update(observe(args.artifact_dir,args.out_dir))
    except Exception as exc:
        out["first_unmet_gate"]=(str(exc)[:120] if isinstance(exc,e07.Hold)
                                else "D02_91A6_VISUAL_"+type(exc).__name__.upper()+"_HOLD")
    finally:
        args.out_dir.mkdir(parents=True,exist_ok=True)
        (args.out_dir/"VISUAL_91A6_RECEIPT.json").write_text(
            json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
        print("D02_91A6_REAL_PIXELS",out["physical_capture"],
              out["first_unmet_gate"],"RELEASE_HOLD",flush=True)
    return 0 if out["physical_capture"]=="PASS" else 2

if __name__=="__main__":raise SystemExit(main())
