"""Physical FULL D02 91a6 original-WPF screenshot and FX-cycle witness.

E07 visual design, Reduced Motion and all functionality remain HOLD until
independently tested on the SAME immutable Setup SHA. Never fake PASS.
"""
from __future__ import annotations
import argparse
import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import independent_setup_e07 as e07
from probe_v6_visual_physical_u01 import capture_window

SCHEMA = "NOX-91A6-INSTALLED-PHYSICAL-VISUAL-WITNESS-v1"

QUALITY_NAMES = (
    "MAX WOW — ПОЛНЫЙ",
    "ECO — ЭКОНОМ",
    "MINI START — МИНИ",
    "AUTO — АДАПТИВНО",
    "CINEMA — КИНО",
)


def validate_quality_witness(payload: object) -> dict:
    """A genuine UIA-Invoke+Toggle/Selection cycle, NOT reduced-motion review."""
    e07.require(type(payload) is dict and
                payload.get("schema") == "NOX-D02-QUALITY-UIA-v1" and
                type(payload.get("actions")) is list and
                len(payload["actions"]) == len(QUALITY_NAMES),
                "U17_D02_QUALITY_SCHEMA_HOLD")
    for expected, item in zip(QUALITY_NAMES, payload["actions"]):
        e07.require(type(item) is dict and
                    item.get("name") == expected and
                    item.get("invoked") is True and
                    item.get("pressed") is True and
                    item.get("same_hwnd") is True,
                    "U17_D02_QUALITY_REAL_TRANSITION_HOLD")
    return {"fx_control": "PASS", "actual_invocations": len(QUALITY_NAMES),
            "observed_modes": list(QUALITY_NAMES),
            "reduced_motion": "NOT_TESTED",
            "independent_visual_review": "NOT_RUN"}


def probe_d02_quality_modes(hwnd: int) -> dict:
    """Invoke five source-approved graphical mode planets on original WPF HWND.

    The legacy three-state FX BALANCED/MAX/ECO test is NOT this D02 interface.
    Source: integrations/wow200/runtime/home-scene.mjs, exact aria-labels.
    """
    e07.require(sys.platform == "win32" and type(hwnd) is int and hwnd > 0,
                "U17_D02_ORIGINAL_WPF_HWND_REQUIRED")
    ps = r'''
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[System.Text.Encoding]::UTF8
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
try {
 $h=[IntPtr]__HWND__
 $root=[System.Windows.Automation.AutomationElement]::FromHandle($h)
 if($null -eq $root){throw 'U17_D02_UIA_HWND_LOST_HOLD'}
 $expected=@('MAX WOW — ПОЛНЫЙ','ECO — ЭКОНОМ',
             'MINI START — МИНИ','AUTO — АДАПТИВНО','CINEMA — КИНО')
 function ExactRealButton([string]$label) {
   $root=[System.Windows.Automation.AutomationElement]::FromHandle($h)
   if($null -eq $root){throw 'U17_D02_UIA_HWND_LOST_HOLD'}
   $filter=[System.Windows.Automation.PropertyCondition]::new(
     [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
     [System.Windows.Automation.ControlType]::Button)
   $nodes=$root.FindAll([System.Windows.Automation.TreeScope]::Descendants,$filter)
   if($nodes.Count -gt 4096){throw 'U17_D02_UIA_TREE_LIMIT_HOLD'}
   $matches=@()
   foreach($item in $nodes){
     if(($item.Current.Name+'') -ceq $label){$matches+=,$item}
   }
   if($matches.Count -ne 1){throw 'U17_D02_QUALITY_UNIQUE_BUTTON_HOLD'}
   $btn=$matches[0]
   $r=$btn.Current.BoundingRectangle
   if(-not $btn.Current.IsEnabled -or $btn.Current.IsOffscreen -or
      $r.Width -lt 15 -or $r.Height -lt 12){
     throw 'U17_D02_QUALITY_NOT_VISIBLE_HOLD'
   }
   return $btn
 }
 $results=@()
 foreach($label in $expected){
   $btn=ExactRealButton $label
   try {$invoke=$btn.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)}
   catch {throw 'U17_D02_QUALITY_INVOKEPATTERN_HOLD'}
   if($null -eq $invoke){throw 'U17_D02_QUALITY_INVOKEPATTERN_HOLD'}
   $invoke.Invoke()
   Start-Sleep -Milliseconds 500
   $current=ExactRealButton $label
   $pressed=$false
   try {
     $toggle=$current.GetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern)
     $pressed=$toggle.Current.ToggleState -eq [System.Windows.Automation.ToggleState]::On
   } catch {
     try {
       $selected=$current.GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern)
       $pressed=$selected.Current.IsSelected
     } catch {throw 'U17_D02_QUALITY_PRESSED_UIA_NOT_EXPOSED_HOLD'}
   }
   if(-not $pressed){throw 'U17_D02_QUALITY_PRESSED_STATE_HOLD'}
   $alive=$null -ne [System.Windows.Automation.AutomationElement]::FromHandle($h)
   if(-not $alive){throw 'U17_D02_UIA_HWND_LOST_HOLD'}
   $results+=([pscustomobject]@{name=$label;invoked=$true;pressed=$true;same_hwnd=$true})
 }
 [pscustomobject]@{schema='NOX-D02-QUALITY-UIA-v1';actions=@($results)} |
   ConvertTo-Json -Compress -Depth 5
} catch {
 $msg=$_.Exception.Message
 if($msg -cmatch '^U17_[A-Z0-9_]+_HOLD$'){Write-Output $msg}
 else {Write-Output 'U17_D02_UIA_UNEXPECTED_HOLD'}
 exit 2
}
'''.replace("__HWND__", str(hwnd))
    encoded=base64.b64encode(ps.encode("utf-16le")).decode("ascii")
    try:
        run=subprocess.run(
            ["powershell.exe","-NoProfile","-NonInteractive","-EncodedCommand",encoded],
            capture_output=True,timeout=60,check=False)
    except (OSError,subprocess.TimeoutExpired):
        raise e07.Hold("U17_D02_QUALITY_PROCESS_HOLD") from None
    e07.require(0 < len(run.stdout) <= 8192,
                "U17_D02_QUALITY_NO_UIA_OUTPUT_HOLD")
    if run.returncode != 0:
        try:
            code=run.stdout.decode("utf-8-sig").strip()
        except UnicodeError:
            code=""
        import re
        if re.fullmatch(r"U17_[A-Z0-9_]+_HOLD",code):
            raise e07.Hold(code)
        raise e07.Hold("U17_D02_QUALITY_UIA_PROCESS_HOLD")
    try:
        data=json.loads(run.stdout.decode("utf-8-sig"))
    except (ValueError,UnicodeError):
        raise e07.Hold("U17_D02_QUALITY_UIA_JSON_HOLD") from None
    return validate_quality_witness(data)

def is_real_visual_witness(obj):
    if type(obj) is not dict:
        return False
    pic, fx = obj.get("photo"), obj.get("fx")
    return (obj.get("schema") == SCHEMA and
        obj.get("source_sha") == e07.NEW_D02_SOURCE_SHA and
        obj.get("setup_sha256") == e07.NEW_D02_SETUP_SHA and
        obj.get("release_accepted") is False and
        obj.get("visual_e07") == "HOLD" and
        obj.get("adaptive_layout") == "NOT_TESTED" and
        obj.get("reduced_motion") == "NOT_TESTED" and
        type(pic) is dict and pic.get("physical_capture") == "PASS" and
        type(pic.get("sha256")) is str and len(pic["sha256"]) == 64 and
        type(fx) is dict and fx.get("fx_control") == "PASS" and
        obj.get("original_wpf_ipc") == "PASS" and
        all(obj.get(k) == "PASS" for k in ("update", "rollback", "uninstall")))

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--artifact-dir", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--png", type=Path, required=True)
    a = p.parse_args()
    result = {
        "schema": SCHEMA, "source_sha": e07.NEW_D02_SOURCE_SHA,
        "setup_sha256": e07.NEW_D02_SETUP_SHA,
        "build_id": e07.NEW_D02_BUILD_ID,
        "release_accepted": False, "visual_e07": "HOLD",
        "adaptive_layout": "NOT_TESTED", "reduced_motion": "NOT_TESTED",
        "physical_capture": "HOLD", "witness_status": "HOLD",
        "first_unmet_gate": "NOT_RUN"}
    try:
        e07.require(sys.platform == "win32" and
            os.getenv("GITHUB_ACTIONS") == "true" and
            os.getenv("RUNNER_OS") == "Windows" and
            os.getenv("RUNNER_ENVIRONMENT") == "github-hosted" and
            os.getenv("GITHUB_REPOSITORY") == "MSSTXNEWS/nox-helion-pp-private-build",
            "U17_WINDOWS_NOT_AUTHORIZED")
        tmp = Path(os.environ["RUNNER_TEMP"]).absolute()
        e07.require(e07.clean_dir(tmp) and
            a.png.absolute() == tmp / "nox-91a6-real-wpf.png" and
            not a.png.exists() and not a.png.is_symlink(),
            "U17_PHOTO_UNOWNED_PATH_HOLD")
        root = a.artifact_dir / "e06" / "onehost-wow-diagnostic"
        setup = root / "NOX-HELION-V16-DIAGNOSTIC-SETUP.exe"
        identity = e07.setup_lock(setup, root / "E07_BUILT_HANDOFF.json",
                                  candidate="d02-91a6")
        e07.require(identity["setup_sha256"] == e07.NEW_D02_SETUP_SHA,
                    "U17_SETUP_SHA_HOLD")
        screenshots = []
        fx_states = []
        photo_errors = []
        fx_errors = []
        previous = e07.observe_original_primary_buttons
        def probe(hwnd):
            try:
                screenshots.append(capture_window(hwnd, a.png))
            except e07.Hold as error:
                photo_errors.append(str(error))
            try:
                fx_states.append(probe_d02_quality_modes(hwnd))
            except e07.Hold as error:
                fx_errors.append(str(error))
            # Even when the optional photo or FX test fails, the original GUI
            # observer still runs and the E07 lifecycle gets to uninstall.
            return previous(hwnd)
        checks = {}
        e07.observe_original_primary_buttons = probe
        try:
            e07.lifecycle(setup, {"checks": checks},
                          frozen_source=e07.NEW_D02_SOURCE_SHA, physical_nav=True)
        finally:
            e07.observe_original_primary_buttons = previous
        e07.require(len(screenshots) == 1,
                    photo_errors[0] if photo_errors else
                    "U17_PHYSICAL_SCREENSHOT_NOT_OBSERVED_HOLD")
        e07.require(e07.clean_file(a.png),
                    "U17_PHYSICAL_SCREENSHOT_MISSING_OR_REPARSE_HOLD")
        e07.require(e07.sha256(a.png) == screenshots[0].get("sha256"),
                    "U17_PHYSICAL_SCREENSHOT_SHA_HOLD")
        result["photo"] = screenshots[0]
        result["physical_capture"] = "PASS"
        result["fx"] = fx_states[0] if len(fx_states) == 1 else {
            "fx_control": "HOLD",
            "reason": fx_errors[0] if fx_errors else "U17_FX_NOT_OBSERVED_HOLD"}
        result.update(
            original_wpf_ipc=checks.get("installed_gui", {}).get("shell_native_ipc"),
            update=checks.get("update", {}).get("status"),
            rollback=checks.get("rollback", {}).get("status"),
            uninstall=checks.get("uninstall", {}).get("status"))
        e07.require(len(fx_states) == 1,
                    fx_errors[0] if fx_errors else "U17_FX_NOT_OBSERVED_HOLD")
        e07.require(is_real_visual_witness(result), "U17_PHYSICAL_UIA_OR_NSIS_HOLD")
        result["witness_status"] = "PASS"
        result["first_unmet_gate"] = "ADAPTIVE_REDUCED_MOTION_AND_INDEPENDENT_VISUAL_REVIEW"
    except (e07.Hold, OSError, ValueError, KeyError, TimeoutError) as exc:
        result["first_unmet_gate"] = (
            str(exc) if isinstance(exc, e07.Hold) else
            "U17_" + type(exc).__name__.upper() + "_HOLD")[:140]
    except Exception as exc:
        result["first_unmet_gate"] = "U17_UNEXPECTED_" + type(exc).__name__.upper() + "_HOLD"
    finally:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
        print("U17_PHYSICAL_WPF_VISUAL", result["physical_capture"],
              result["first_unmet_gate"], flush=True)
    return 0 if result["witness_status"] == "PASS" else 2

if __name__ == "__main__":
    raise SystemExit(main())
