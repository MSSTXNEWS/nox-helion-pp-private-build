"""Fast physical D02 evidence on the exact frozen f842 Setup, NOT a release.

Uses the original Windows WPF HWND and the existing E07 install/update/
rollback/uninstall implementation. Does not download Ollama, models, start a
new host, or turn a screenshot into a fabricated visual-design PASS.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

import independent_setup_e07 as e07
from probe_final_same_setup import _uia_script, _run_ps, _physical_adaptive_sized
from probe_v6_visual_physical_u01 import capture_window
from probe_91a6_real_visual_u17 import probe_d02_quality_modes

SCHEMA = "NOX-E07-F842-FAST-PHYSICAL-D02-WITNESS-v1"


def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--artifact-dir",required=True,type=Path)
    parser.add_argument("--out",required=True,type=Path)
    args=parser.parse_args()
    result={"schema":SCHEMA,"source_sha":e07.F842_D02_SOURCE_SHA,
            "setup_sha256":e07.F842_D02_SETUP_SHA,"release_accepted":False,
            "design_review":"NOT_TESTED","reduced_motion":"NOT_TESTED",
            "full_functional_acceptance":"NOT_TESTED",
            "visual_probe":"HOLD","error":"NOT_RUN","checks":{}}
    try:
        e07.require(sys.platform=="win32" and
                    os.getenv("GITHUB_ACTIONS")=="true" and
                    os.getenv("RUNNER_OS")=="Windows" and
                    os.getenv("RUNNER_ENVIRONMENT")=="github-hosted" and
                    os.getenv("GITHUB_REPOSITORY")=="MSSTXNEWS/nox-helion-pp-private-build",
                    "F842_VISUAL_UNAUTHORIZED_WINDOWS_HOST_HOLD")
        folder=args.artifact_dir/"e06"/"onehost-wow-diagnostic"
        setup=folder/"NOX-HELION-V16-DIAGNOSTIC-SETUP.exe"
        identity=e07.setup_lock(setup,folder/"E07_BUILT_HANDOFF.json",
                                candidate="d02-f842")
        e07.require(identity["setup_sha256"]==e07.F842_D02_SETUP_SHA,
                    "F842_VISUAL_SETUP_IDENTITY_HOLD")
        temp=Path(os.environ["RUNNER_TEMP"]).absolute()
        e07.require(e07.clean_dir(temp),"F842_VISUAL_TRUSTED_TEMP_HOLD")
        gdi=temp/"nox-f842-window-gdi.png"
        printed=temp/"nox-f842-window-print.png"
        for dest in (gdi,printed):
            e07.require(not dest.exists() and not dest.is_symlink() and
                        not getattr(dest,"is_junction",lambda:False)(),
                        "F842_VISUAL_CAPTURE_COLLISION_HOLD")
        physical={}
        original=e07.observe_original_primary_buttons

        def observe(hwnd: int) -> dict:
            physical["same_original_hwnd"]=hwnd>0
            try:
                physical["foreground_capture"]=capture_window(hwnd,gdi)
            except (e07.Hold,OSError,subprocess.TimeoutExpired) as exc:
                physical["foreground_error"]=(str(exc) if isinstance(exc,e07.Hold)
                                              else "F842_GDI_"+type(exc).__name__.upper()+"_HOLD")
            try:
                value=_run_ps(_uia_script(hwnd,"VISUAL",png=printed),
                              phase="VISUAL",timeout=60)
                physical["resize_witness"]=value
                physical["adaptive_layout"]=("PASS" if
                    _physical_adaptive_sized(value.get("sizes")) else "HOLD")
                physical["print_capture_sha256"]=(e07.sha256(printed)
                    if e07.clean_file(printed) else None)
            except (e07.Hold,OSError,subprocess.TimeoutExpired) as exc:
                physical["resize_error"]=(str(exc) if isinstance(exc,e07.Hold)
                                          else "F842_RESIZE_"+type(exc).__name__.upper()+"_HOLD")
            try:
                physical["five_quality_modes"]=probe_d02_quality_modes(hwnd)
            except (e07.Hold,OSError,subprocess.TimeoutExpired) as exc:
                physical["quality_error"]=(str(exc) if isinstance(exc,e07.Hold)
                                           else "F842_QUALITY_"+type(exc).__name__.upper()+"_HOLD")
            return original(hwnd)

        e07.observe_original_primary_buttons=observe
        checks={}
        try:
            e07.lifecycle(setup,{"checks":checks},
                          frozen_source=e07.F842_D02_SOURCE_SHA,
                          physical_nav=True)
        finally:
            e07.observe_original_primary_buttons=original
        result["checks"]={
            "gui":checks.get("installed_gui",{}).get("gui_visible_hwnd"),
            "native_ipc":checks.get("installed_gui",{}).get("shell_native_ipc"),
            "update":checks.get("update",{}).get("status"),
            "rollback":checks.get("rollback",{}).get("status"),
            "uninstall":checks.get("uninstall",{}).get("status"),
        }
        # Captures and transitions are diagnostic evidence; NOT visual design
        # approval, OS reduced-motion verification, or privileged-function PASS.
        physical.pop("same_original_hwnd",None)
        result["physical"]=physical
        e07.require(result["checks"]=={
            "gui":"PASS","native_ipc":"PASS","update":"PASS",
            "rollback":"PASS","uninstall":"PASS"},
            "F842_VISUAL_INSTALLED_LIFECYCLE_HOLD")
        e07.require("foreground_capture" in physical,
                    physical.get("foreground_error","F842_VISUAL_GDI_MISSING_HOLD"))
        e07.require(physical.get("adaptive_layout")=="PASS",
                    physical.get("resize_error","F842_VISUAL_RESIZE_NOT_ACCEPTED_HOLD"))
        fx=physical.get("five_quality_modes",{})
        e07.require(fx.get("fx_control")=="PASS" and
                    fx.get("actual_invocations")==5,
                    physical.get("quality_error","F842_QUALITY_MODES_HOLD"))
        result["visual_probe"]="PHYSICAL_LAYOUT_AND_MODES_OBSERVED_NOT_DESIGN_APPROVAL"
        result["error"]=None
    except (e07.Hold,FileNotFoundError,ValueError,OSError,
            subprocess.TimeoutExpired) as exc:
        result["error"]=(str(exc) if isinstance(exc,e07.Hold)
                         else "F842_VISUAL_"+type(exc).__name__.upper()+"_HOLD")[:140]
    except Exception as exc:
        result["error"]="F842_VISUAL_UNEXPECTED_"+type(exc).__name__.upper()+"_HOLD"
    finally:
        args.out.parent.mkdir(parents=True,exist_ok=True)
        args.out.write_text(json.dumps(result,sort_keys=True,indent=2),encoding="utf-8")
        print("F842_FAST_VISUAL_WITNESS",result["error"],"NOT_RELEASE",flush=True)
    return 0 if result["error"] is None else 1


if __name__=="__main__":
    raise SystemExit(main())
