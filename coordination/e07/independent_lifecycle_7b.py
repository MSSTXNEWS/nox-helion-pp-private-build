"""Independent physical E07 lifecycle of the exact SETTINGS candidate.

This Windows runner is NOT the installer producer or the local Qwen testing job.
Original E07 lifecycle owns install, WPF/WebView2, IPC, update, rollback and
conservative uninstall. Model streaming and full five-button function checks
must be proven separately on the SAME immutable Setup SHA before release.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import sys

from independent_setup_e07 import Hold, lifecycle, require
from probe_five_primary_action import checked_source_setup

SOURCE_SHA = "a504410cd969adfbdcda4e39fdeb9aef76e78702"
SETUP_SHA = "cd894b5a1cbd46d3106f75869733256a4adc77ea2d60d3b590bcb7353e9a7a5c"


def run_check(artifact: Path, receipt: Path) -> int:
    result = {"schema":"nox.independent.windows.lifecycle-7b.v1",
              "source_sha":SOURCE_SHA, "setup_sha256":SETUP_SHA,
              "checks":{}, "independent_lifecycle":"HOLD",
              "full_independent_e07":"HOLD", "release_accepted":False}
    try:
        require(sys.platform=="win32" and
                os.environ.get("GITHUB_ACTIONS")=="true" and
                os.environ.get("RUNNER_OS")=="Windows" and
                os.environ.get("RUNNER_ENVIRONMENT")=="github-hosted" and
                os.environ.get("GITHUB_REPOSITORY")=="MSSTXNEWS/nox-helion-pp-private-build",
                "E07_WINDOWS_INDEPENDENT_RUNNER_NOT_AUTHORIZED")
        bound=checked_source_setup(artifact, SOURCE_SHA, SETUP_SHA)
        result["checks"]["source_setup"]=bound
        # No model/UI claims copied from other binary or another Windows VM.
        lifecycle(artifact/"NOX_HELION_EXPRESS_CANDIDATE_SETUP.exe",
                  result, frozen_source=SOURCE_SHA)
        required=("install_and_manifest","installed_native_ipc","installed_gui",
                  "update","rollback","uninstall","backup_retention")
        require(all(key in result["checks"] for key in required),
                "E07_INDEPENDENT_LIFECYCLE_INCOMPLETE")
        gui=result["checks"]["installed_gui"]
        require(gui.get("gui_visible_hwnd")=="PASS" and
                gui.get("webview_navigation")=="PASS" and
                gui.get("shell_native_ipc")=="PASS",
                "E07_INDEPENDENT_WPF_GUI_OR_IPC_HOLD")
        require(all(result["checks"][name].get("status")=="PASS"
                    for name in ("install_and_manifest","update","rollback","uninstall","backup_retention")),
                "E07_INDEPENDENT_NSIS_LIFECYCLE_HOLD")
        result["independent_lifecycle"]="PASS"
        result["first_unmet_gate"]="SAME_SETUP_SHA_QWEN_STOP_HISTORY_FIVE_UIA_AND_RELEASE_RECONCILIATION"
    except (Hold, OSError, KeyError, ValueError, TimeoutError) as exc:
        result["first_unmet_gate"]=str(exc) if isinstance(exc,Hold) else (
            "E07_LIFECYCLE_"+type(exc).__name__.upper()+"_HOLD")
    except Exception as exc:
        result["first_unmet_gate"]="E07_LIFECYCLE_UNEXPECTED_"+type(exc).__name__.upper()+"_HOLD"
    receipt.parent.mkdir(parents=True,exist_ok=True)
    receipt.write_text(json.dumps(result,ensure_ascii=False,sort_keys=True,indent=2),
                       encoding="utf-8")
    print("NOX_INDEPENDENT_WINDOWS_LIFECYCLE",result["independent_lifecycle"],
          result.get("first_unmet_gate"),flush=True)
    return 0 if result["independent_lifecycle"]=="PASS" else 2


if __name__=="__main__":
    cli=argparse.ArgumentParser()
    cli.add_argument("--artifact-dir",required=True,type=Path)
    cli.add_argument("--out",required=True,type=Path)
    args=cli.parse_args()
    raise SystemExit(run_check(args.artifact_dir,args.out))
