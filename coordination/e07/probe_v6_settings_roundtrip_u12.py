"""Physical original V6 WPF SETTINGS -> BACK interaction, never E07 approval.

Tests an actual second UIA InvokePattern action in the same installed WPF
HWND after clicking SETTINGS, not a heading-only navigation receipt. Does not
activate privileged actions, alter settings, replace backend or bypass consent.
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
import probe_full_d02_722399_u13 as frozen

SCHEMA = "NOX-V6-U12-SETTINGS-BACK-UIA-v1"


def classify(witness: object) -> dict:
    """Only observed state transitions and TWO physical invokes can pass."""
    e07.require(type(witness) is dict and set(witness) == {
        "schema", "initialSettingsHeading", "settingsInvoke", "settingsHeadingAfter",
        "backControlVisibleAfterSettings", "backInvoke", "settingsHeadingAfterBack",
        "fivePrimaryVisibleAfterBack", "sameOriginalHwndAlive"},
        "U12_SETTINGS_RECEIPT_SCHEMA_HOLD")
    e07.require(witness["schema"] == SCHEMA and
                all(type(v) is bool for k, v in witness.items() if k != "schema") and
                witness["initialSettingsHeading"] is False and
                witness["settingsInvoke"] is True and
                witness["settingsHeadingAfter"] is True and
                witness["backControlVisibleAfterSettings"] is True and
                witness["backInvoke"] is True and
                witness["settingsHeadingAfterBack"] is False and
                witness["fivePrimaryVisibleAfterBack"] is True and
                witness["sameOriginalHwndAlive"] is True,
                "U12_SETTINGS_BACK_PHYSICAL_TRANSITION_HOLD")
    return {"status": "PASS", "scope": "SETTINGS_PANEL_BACK_INVOKE_ONLY",
            "uia_invocations": 2, "full_settings_function_verified": False,
            "independent_e07_10_10": "HOLD", "release_accepted": False}


def invoke_settings_back(hwnd: int) -> dict:
    e07.require(sys.platform == "win32" and type(hwnd) is int and hwnd > 0,
                "U12_SETTINGS_REAL_WPF_HWND_REQUIRED")
    ps = r'''
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[System.Text.Encoding]::UTF8
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$h=[IntPtr]__HWND__
function Root {
  $r=[System.Windows.Automation.AutomationElement]::FromHandle($h)
  if($null -eq $r){throw 'U12_LOST_ORIGINAL_HWND'}
  return $r
}
function Tree($r) {
  $a=$r.FindAll([System.Windows.Automation.TreeScope]::Descendants,[System.Windows.Automation.Condition]::TrueCondition)
  if($a.Count -gt 2048){throw 'U12_UIA_TREE_UNBOUNDED'}
  return $a
}
function Visible($v) {
  $b=$v.BoundingRectangle
  return (-not $v.IsOffscreen -and $v.IsEnabled -and $b.Width -ge 20 -and $b.Height -ge 12)
}
function Heading {
  $a=Tree (Root)
  for($i=0;$i -lt $a.Count;$i++){
    try {
      $v=$a.Item($i).Current
      if($v.ControlType -eq [System.Windows.Automation.ControlType]::Text -and
         ($v.Name+'').Trim() -ceq 'СИСТЕМА' -and (Visible $v)){return $true}
    }catch{}
  }
  return $false
}
function OneButton([string]$name) {
  $a=Tree (Root)
  $found=[System.Collections.Generic.List[System.Windows.Automation.AutomationElement]]::new()
  for($i=0;$i -lt $a.Count;$i++){
    try {
      $el=$a.Item($i);$v=$el.Current
      $label=($v.Name+'').Trim().TrimStart([char[]]@([char]0x2726,[char]0x2605,[char]0x2022,[char]0x20)).Trim()
      if($v.ControlType -eq [System.Windows.Automation.ControlType]::Button -and
         $label -ceq $name -and (Visible $v)){$found.Add($el)}
    }catch{}
  }
  if($found.Count -ne 1){throw 'U12_EXPECTED_EXACTLY_ONE_ORIGINAL_BUTTON'}
  return $found.Item(0)
}
function MainVisible {
  foreach($name in @('CHAT','INSTALL','MODELS','LEARN','SETTINGS')){
    try {$null=OneButton $name}catch{return $false}
  }
  return $true
}
$before=Heading
if($before){throw 'U12_SETTINGS_ALREADY_VISIBLE_NO_TRANSITION'}
$s=OneButton 'SETTINGS'
$p=$s.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
if($null -eq $p){throw 'U12_SETTINGS_NO_INVOKE'}
$p.Invoke()
$entered=$false
for($i=0;$i -lt 40;$i++){
  Start-Sleep -Milliseconds 200
  if(Heading){$entered=$true;break}
}
if(-not $entered){throw 'U12_SETTINGS_SCREEN_NOT_VISIBLE'}
$back=OneButton '← НАЗАД В МЕНЮ'
$q=$back.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
if($null -eq $q){throw 'U12_BACK_NO_INVOKE'}
$q.Invoke()
$left=$false
for($i=0;$i -lt 40;$i++){
  Start-Sleep -Milliseconds 200
  if(-not (Heading)){$left=$true;break}
}
if(-not $left){throw 'U12_BACK_STILL_SETTINGS'}
$main=MainVisible
[pscustomobject]@{schema='NOX-V6-U12-SETTINGS-BACK-UIA-v1';
 initialSettingsHeading=$before;settingsInvoke=$true;settingsHeadingAfter=$entered;
 backControlVisibleAfterSettings=$true;backInvoke=$true;
 settingsHeadingAfterBack=(-not $left);fivePrimaryVisibleAfterBack=$main;
 sameOriginalHwndAlive=($null -ne [System.Windows.Automation.AutomationElement]::FromHandle($h))} | ConvertTo-Json -Compress
'''.replace("__HWND__", str(hwnd))
    encoded = base64.b64encode(ps.encode("utf-16le")).decode("ascii")
    try:
        p = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive",
                            "-EncodedCommand", encoded], capture_output=True,
                           timeout=80, check=False, encoding="utf-8", errors="replace")
    except (OSError, subprocess.TimeoutExpired):
        raise e07.Hold("U12_SETTINGS_UIA_PROCESS_HOLD") from None
    e07.require(p.returncode == 0 and 1 <= len(p.stdout) <= 2048,
                "U12_SETTINGS_UIA_INVOCATION_OR_TIMEOUT_HOLD")
    try:
        raw = json.loads(p.stdout.strip())
    except (UnicodeError, ValueError):
        raise e07.Hold("U12_SETTINGS_UIA_JSON_HOLD") from None
    return classify(raw)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--artifact-dir", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()
    receipt = {"schema": SCHEMA, "source_sha": frozen.SOURCE,
               "setup_sha256": frozen.SETUP_SHA, "build_id": frozen.BUILDID,
               "settings_roundtrip": "HOLD", "independent_e07_10_10": "HOLD",
               "release_accepted": False, "first_failure": "NOT_RUN"}
    try:
        e07.require(sys.platform == "win32" and os.getenv("GITHUB_ACTIONS") == "true" and
                    os.getenv("RUNNER_OS") == "Windows" and
                    os.getenv("RUNNER_ENVIRONMENT") == "github-hosted" and
                    os.getenv("GITHUB_REPOSITORY") == "MSSTXNEWS/nox-helion-pp-private-build",
                    "U12_UNTRUSTED_WINDOWS_RUNNER_HOLD")
        setup = frozen.candidate(args.artifact_dir)
        local = Path(os.environ["LOCALAPPDATA"])
        install = local / "Programs" / "NOX HELION"
        e07.verify_fresh_install_targets(local, install,
                                         Path(str(install) + ".__p01_stage"),
                                         Path(str(install) + ".__p01_previous"),
                                         Path(str(install) + ".__p01_rollback_saved"))
        e07.require(e07.run([str(setup), "/S"], limit=300) == 0,
                    "U12_EXACT_FROZEN_SETUP_NSIS_INSTALL_HOLD")
        _, owned = e07.manifest_owner(install)
        e07.require(len(owned) == 1004, "U12_INSTALLED_OWNED_FILES_HOLD")
        original = e07.observe_original_primary_buttons
        observed: list[dict] = []
        def observer(hwnd: int) -> dict:
            found = original(hwnd)
            e07.require(found.get("status") == "PASS", "U12_ORIGINAL_FIVE_BUTTONS_HOLD")
            observed.append(invoke_settings_back(hwnd))
            return found
        e07.observe_original_primary_buttons = observer
        gui = e07.gui_hwnd(install / "NOX.P01.Shell.exe", local)
        e07.require(len(observed) == 1 and
                    all(gui.get(k) == "PASS" for k in
                        ("gui_visible_hwnd", "webview_navigation", "shell_native_ipc")),
                    "U12_REAL_GUI_WEBVIEW2_IPC_HOLD")
        receipt.update({"settings_roundtrip": "PASS", "scope": observed[0]["scope"],
                        "uia_invocations": observed[0]["uia_invocations"],
                        "full_settings_function_verified": False,
                        "first_failure": None})
    except (e07.Hold, OSError, KeyError, TimeoutError, ValueError) as exc:
        receipt["first_failure"] = (str(exc) if isinstance(exc, e07.Hold)
                                    else "U12_" + type(exc).__name__.upper() + "_HOLD")[:150]
    except Exception as exc:
        receipt["first_failure"] = "U12_UNEXPECTED_" + type(exc).__name__.upper() + "_HOLD"
    finally:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(receipt, sort_keys=True, indent=2), encoding="utf-8")
        print("U12_REAL_ORIGINAL_SETTINGS_BACK", receipt["settings_roundtrip"],
              receipt["first_failure"], "E07_HOLD", flush=True)
    return 0 if receipt["settings_roundtrip"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
