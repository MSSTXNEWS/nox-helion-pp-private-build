"""Read-only physical D02 screenshot on a SHA-pinned installed original WPF HWND.

Never claims final visual approval or E07 release. Reuses the existing strict
independent GUI/UIA witness and SourceLock; no second host/GUI/backend.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys

import independent_setup_e07 as e07
import probe_full_d02_722399_u13 as frozen

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def checked_png(path: Path) -> dict:
    """Reject stale, tiny/blank or malformed captures; do NOT call it visual PASS."""
    e07.require(e07.clean_file(path) and 30_000 <= path.stat().st_size <= 16_000_000,
                "V6_VISUAL_CAPTURE_EMPTY_OR_UNTRUSTED_HOLD")
    with path.open("rb") as f:
        prefix = f.read(24)
    e07.require(len(prefix) == 24 and prefix[:8] == PNG_SIGNATURE and
                prefix[12:16] == b"IHDR", "V6_VISUAL_CAPTURE_NOT_PNG_HOLD")
    w, h = struct.unpack(">II", prefix[16:24])
    e07.require(640 <= w <= 7680 and 480 <= h <= 4320,
                "V6_VISUAL_CAPTURE_DIMENSIONS_HOLD")
    return {"sha256": e07.sha256(path), "bytes": path.stat().st_size,
            "width": w, "height": h, "physical_capture": "PASS",
            "independent_visual_review": "NOT_RUN", "reduced_motion": "NOT_TESTED"}


def capture_window(hwnd: int, png: Path) -> dict:
    """Capture precisely the currently focused original WPF HWND, not a mock HTML."""
    e07.require(sys.platform == "win32" and type(hwnd) is int and hwnd > 0,
                "V6_VISUAL_ORIGINAL_WINDOWS_HWND_REQUIRED")
    ps = r'''
$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Drawing
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class NoxVisualWin32 {
 [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left,Top,Right,Bottom; }
 [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
 [DllImport("user32.dll")] public static extern bool ShowWindowAsync(IntPtr h,int c);
 [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
 [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
}
'@
$h=[IntPtr]__HWND__
$null=[NoxVisualWin32]::ShowWindowAsync($h,9)
$null=[NoxVisualWin32]::SetForegroundWindow($h)
Start-Sleep -Milliseconds 700
if([NoxVisualWin32]::GetForegroundWindow() -ne $h){throw 'V6_VISUAL_FOREGROUND_HWND_HOLD'}
$r=New-Object NoxVisualWin32+RECT
if(-not [NoxVisualWin32]::GetWindowRect($h,[ref]$r)){throw 'V6_VISUAL_RECT_HOLD'}
$w=$r.Right-$r.Left;$hgt=$r.Bottom-$r.Top
if($w -lt 640 -or $hgt -lt 480 -or $w -gt 7680 -or $hgt -gt 4320){throw 'V6_VISUAL_BOUNDS_HOLD'}
$bmp=New-Object System.Drawing.Bitmap($w,$hgt)
try {
 $g=[System.Drawing.Graphics]::FromImage($bmp)
 try { $g.CopyFromScreen($r.Left,$r.Top,0,0,$bmp.Size,[System.Drawing.CopyPixelOperation]::SourceCopy) }
 finally { $g.Dispose() }
 $bmp.Save($env:NOX_V6_VISUAL_OUTPUT,[System.Drawing.Imaging.ImageFormat]::Png)
} finally { $bmp.Dispose() }
Write-Host 'V6_ORIGINAL_WPF_SAME_HWND_CAPTURED_NO_VISUAL_PASS'
'''.replace("__HWND__", str(hwnd))
    encoded = base64.b64encode(ps.encode("utf-16le")).decode("ascii")
    env = dict(os.environ)
    env["NOX_V6_VISUAL_OUTPUT"] = str(png)
    try:
        result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive",
                                 "-EncodedCommand", encoded], env=env,
                                capture_output=True, timeout=25, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise e07.Hold("V6_VISUAL_GDI_EXECUTION_HOLD") from None
    e07.require(result.returncode == 0,
                "V6_VISUAL_GDI_OR_FOREGROUND_HOLD")
    return checked_png(png)



def evaluate_fx_cycle(data: object) -> dict:
    """Only genuine three sequential InvokePattern transitions count as FX evidence."""
    e07.require(type(data) is dict and set(data) ==
                {"initial", "observed", "invocations"} and
                data["initial"] == "FX BALANCED" and
                type(data["invocations"]) is int and data["invocations"] == 3 and
                type(data["observed"]) is list and
                data["observed"] == ["FX MAX", "FX ECO", "FX BALANCED"],
                "V6_FX_PHYSICAL_TRANSITION_HOLD")
    return {"fx_control": "PASS", "actual_invoke_transitions": 3,
            "states": ["BALANCED", "MAX", "ECO", "BALANCED"],
            "reduced_motion": "NOT_TESTED", "independent_visual_review": "NOT_RUN"}


def probe_fx_cycle(hwnd: int) -> dict:
    """Exercise existing original WPF/WebView2 FX button, restore BALANCED."""
    e07.require(sys.platform == "win32" and type(hwnd) is int and hwnd > 0,
                "V6_FX_ORIGINAL_WINDOWS_HWND_REQUIRED")
    script = r'''
$ErrorActionPreference='Stop'
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$root=[System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]__HWND__)
if ($null -eq $root) { throw 'V6_FX_ORIGINAL_HWND_NOT_FOUND' }
$filter=[System.Windows.Automation.PropertyCondition]::new(
 [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
 [System.Windows.Automation.ControlType]::Button)
function Get-OriginalFxButton {
 $controls=$root.FindAll([System.Windows.Automation.TreeScope]::Descendants,$filter)
 $foundControls=New-Object System.Collections.ArrayList
 foreach($c in $controls) {
  if (($c.Current.Name+'') -cmatch '^FX (BALANCED|MAX|ECO)$') {
   [void]$foundControls.Add($c)
  }
 }
 if ($foundControls.Count -ne 1) { throw 'V6_FX_UNIQUE_REAL_BUTTON_HOLD' }
 return $foundControls[0]
}
$initial=(Get-OriginalFxButton).Current.Name+''
if ($initial -cne 'FX BALANCED') { throw 'V6_FX_INITIAL_BALANCED_HOLD' }
$observed=New-Object System.Collections.ArrayList
$prior=$initial
foreach($expected in @('FX MAX','FX ECO','FX BALANCED')) {
 $button=Get-OriginalFxButton
 if (($button.Current.Name+'') -cne $prior) { throw 'V6_FX_STALE_UIA_STATE_HOLD' }
 $pattern=$button.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
 if ($null -eq $pattern) { throw 'V6_FX_NO_NATIVE_INVOKEPATTERN_HOLD' }
 $pattern.Invoke()
 Start-Sleep -Milliseconds 300
 $actual=(Get-OriginalFxButton).Current.Name+''
 if ($actual -cne $expected) { throw 'V6_FX_NO_REAL_TRANSITION_HOLD' }
 [void]$observed.Add($actual)
 $prior=$actual
}
[pscustomobject]@{initial=$initial;observed=@($observed.ToArray());invocations=3} |
 ConvertTo-Json -Compress -Depth 3
'''.replace("__HWND__", str(hwnd))
    encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    try:
        run = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive",
                              "-EncodedCommand", encoded],
                             capture_output=True, timeout=32, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise e07.Hold("V6_FX_UIA_PROCESS_HOLD") from None
    e07.require(run.returncode == 0 and 1 <= len(run.stdout) <= 2048,
                "V6_FX_UIA_INVOKE_OR_TRANSITION_HOLD")
    try:
        return evaluate_fx_cycle(json.loads(run.stdout.decode("utf-8-sig")))
    except (UnicodeError, ValueError, json.JSONDecodeError):
        raise e07.Hold("V6_FX_UIA_RECEIPT_HOLD") from None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--png", type=Path, required=True)
    args = parser.parse_args()
    receipt = {"schema": "NOX-E07-V6-PHYSICAL-VISUAL-WITNESS-v1",
               "source_sha": frozen.SOURCE, "setup_sha256": frozen.SETUP_SHA,
               "build_id": frozen.BUILDID, "release_accepted": False,
               "visual_e07": "HOLD", "independent_e07_10_10": "HOLD",
               "error": "NOT_RUN"}
    try:
        e07.require(sys.platform == "win32" and os.getenv("GITHUB_ACTIONS") == "true" and
                    os.getenv("RUNNER_OS") == "Windows" and
                    os.getenv("RUNNER_ENVIRONMENT") == "github-hosted" and
                    os.getenv("GITHUB_REPOSITORY") == "MSSTXNEWS/nox-helion-pp-private-build",
                    "V6_VISUAL_UNAUTHORIZED_HOST_HOLD")
        temp = Path(os.environ["RUNNER_TEMP"]).absolute()
        e07.require(args.png.absolute().parent == temp and
                    args.png.name == "nox-v6-physical-d02.png" and
                    not args.png.exists() and not args.png.is_symlink() and
                    e07.clean_dir(temp), "V6_VISUAL_PNG_PATH_HOLD")
        setup = frozen.candidate(args.artifact_dir)
        local = Path(os.environ["LOCALAPPDATA"])
        install = local / "Programs" / "NOX HELION"
        e07.verify_fresh_install_targets(
            local, install, Path(str(install) + ".__p01_stage"),
            Path(str(install) + ".__p01_previous"),
            Path(str(install) + ".__p01_rollback_saved"))
        e07.require(e07.run([str(setup), "/S"], limit=300) == 0,
                    "V6_VISUAL_SAME_SETUP_INSTALL_HOLD")
        _, owned = e07.manifest_owner(install)
        e07.require(len(owned) == 1004, "V6_VISUAL_INSTALLED_MANIFEST_HOLD")
        original_observer = e07.observe_original_primary_buttons
        captures: list[dict] = []
        fx_checks: list[dict] = []
        def observer(hwnd: int) -> dict:
            # Native reviewed WPF HWND, fresh NAV+IPC and 8 seconds of stability
            # are already required by gui_hwnd before it invokes this observer.
            captures.append(capture_window(hwnd, args.png))
            fx_checks.append(probe_fx_cycle(hwnd))
            return original_observer(hwnd)
        e07.observe_original_primary_buttons = observer
        gui = e07.gui_hwnd(install / "NOX.P01.Shell.exe", local, safe_nav=False)
        e07.require(len(captures) == 1 and len(fx_checks) == 1 and
                    fx_checks[0].get("fx_control") == "PASS" and
                    gui.get("gui_visible_hwnd") == "PASS" and
                    gui.get("webview_navigation") == "PASS" and
                    gui.get("shell_native_ipc") == "PASS" and
                    gui.get("five_primary_buttons", {}).get("status") == "PASS",
                    "V6_VISUAL_GUI_OR_CAPTURE_HOLD")
        receipt.update({"physical_capture": captures[0], "physical_fx_cycle": fx_checks[0],
                        "installed_owned_sha256_verified": 1004,
                        "wpf_gui_ipc": "PASS", "error": None})
    except (e07.Hold, OSError, ValueError, KeyError,
            subprocess.TimeoutExpired) as exc:
        receipt["error"] = (str(exc) if isinstance(exc, e07.Hold)
                            else "V6_VISUAL_" + type(exc).__name__.upper() + "_HOLD")[:150]
    except Exception as exc:
        receipt["error"] = "V6_VISUAL_UNEXPECTED_" + type(exc).__name__.upper() + "_HOLD"
    finally:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(receipt, sort_keys=True, indent=2), encoding="utf-8")
        print("V6_INDEPENDENT_PHYSICAL_VISUAL", receipt["error"], "RELEASE_HOLD", flush=True)
    # Successful photographic acquisition is NOT the independent visual review.
    return 0 if receipt["error"] is None else 1

if __name__ == "__main__":
    raise SystemExit(main())
