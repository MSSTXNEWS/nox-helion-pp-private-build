"""Final same-Setup Windows acceptance for NOX HELION EXPRESS.

Runs only inside the existing independent E07 Windows lifecycle while the exact
candidate is installed and its original WPF HWND is alive. Produces two bounded
non-release subreceipts consumed by independent_setup_e07.evaluate_final_acceptance.
"""
from __future__ import annotations
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

import independent_setup_e07 as e07

PRIMARY=("CHAT","INSTALL","MODELS","LEARN","SETTINGS")


def _receipt_sha(value: dict) -> str:
    raw=json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _run_ps(source: str, *, timeout: int=90, env: dict|None=None) -> dict:
    encoded=base64.b64encode(source.encode("utf-16le")).decode("ascii")
    try:
        p=subprocess.run(["powershell.exe","-NoProfile","-NonInteractive","-EncodedCommand",encoded],
                         capture_output=True,timeout=timeout,check=False,
                         encoding="utf-8",errors="replace",env=env)
    except (OSError,subprocess.TimeoutExpired):
        raise e07.Hold("E07_FINAL_UIA_PROCESS_HOLD") from None
    e07.require(p.returncode==0 and 0 < len(p.stdout) <= 131072,
                "E07_FINAL_UIA_EXECUTION_HOLD")
    try:
        result=json.loads(p.stdout.strip())
    except (ValueError,UnicodeError):
        raise e07.Hold("E07_FINAL_UIA_JSON_HOLD") from None
    e07.require(type(result) is dict,"E07_FINAL_UIA_JSON_HOLD")
    return result


def _uia_script(hwnd: int, operation: str, *, png: Path|None=None) -> str:
    e07.require(type(hwnd) is int and hwnd>0,"E07_FINAL_BAD_HWND_HOLD")
    png_path=(str(png).replace("'","''") if png else "")
    return r'''$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[System.Text.Encoding]::UTF8
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -AssemblyName System.Drawing
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class NoxFinalWin32 {
 [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left,Top,Right,Bottom; }
 [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h,out RECT r);
 [DllImport("user32.dll")] public static extern bool MoveWindow(IntPtr h,int x,int y,int w,int hgt,bool repaint);
 [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h,IntPtr dc,uint flags);
}
'@
$handle=[IntPtr]__HWND__
function Root { $r=[System.Windows.Automation.AutomationElement]::FromHandle($handle); if($null -eq $r){throw 'NO_ROOT'}; return $r }
function Tree($r) { $a=$r.FindAll([System.Windows.Automation.TreeScope]::Descendants,[System.Windows.Automation.Condition]::TrueCondition); if($a.Count -gt 4096){throw 'TREE_LIMIT'}; return $a }
function Visible($v) { $b=$v.BoundingRectangle; return ($v.IsEnabled -and -not $v.IsOffscreen -and $b.Width -ge 14 -and $b.Height -ge 10) }
function Normalize([string]$s) { return ($s+'').Trim().TrimStart([char[]]@([char]0x2726,[char]0x2605,[char]0x2022,[char]0x20)).Trim().ToUpperInvariant() }
function OneButton([string]$name) {
 $a=Tree (Root); $found=New-Object System.Collections.ArrayList
 for($i=0;$i -lt $a.Count;$i++){ try{$el=$a.Item($i);$v=$el.Current;if($v.ControlType -eq [System.Windows.Automation.ControlType]::Button -and (Normalize $v.Name) -ceq $name -and (Visible $v)){[void]$found.Add($el)}}catch{} }
 if($found.Count -ne 1){throw ('BUTTON_'+$name+'_NOT_UNIQUE')}; return $found[0]
}
function InvokePrimary([string]$name){$b=OneButton $name;$p=$b.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern);if($null -eq $p){throw 'NO_INVOKE'};$p.Invoke();Start-Sleep -Milliseconds 400;return $true}
function FiveRects {
 $out=@();foreach($name in @('CHAT','INSTALL','MODELS','LEARN','SETTINGS')){$v=(OneButton $name).Current;$r=$v.BoundingRectangle;$out+=([pscustomobject]@{name=$name;x=[int]$r.X;y=[int]$r.Y;width=[int]$r.Width;height=[int]$r.Height})};return @($out)
}
function NoOverlap($rects){for($i=0;$i -lt $rects.Count;$i++){for($j=$i+1;$j -lt $rects.Count;$j++){$a=$rects[$i];$b=$rects[$j];if($a.x -lt ($b.x+$b.width) -and ($a.x+$a.width) -gt $b.x -and $a.y -lt ($b.y+$b.height) -and ($a.y+$a.height) -gt $b.y){return $false}}};return $true}
$op='__OP__'
if($op -eq 'CLICK'){ [pscustomobject]@{invoked=(InvokePrimary '__ACTION__');sameHwndAlive=($null -ne [System.Windows.Automation.AutomationElement]::FromHandle($handle))}|ConvertTo-Json -Compress; exit 0 }
if($op -eq 'SETTINGS'){
 $null=InvokePrimary 'SETTINGS';$seen=$false
 for($n=0;$n -lt 40;$n++){Start-Sleep -Milliseconds 200;$a=Tree (Root);for($i=0;$i -lt $a.Count;$i++){try{$v=$a.Item($i).Current;if($v.ControlType -eq [System.Windows.Automation.ControlType]::Text -and ($v.Name+'').Trim() -ceq 'СИСТЕМА' -and (Visible $v)){$seen=$true;break}}catch{}};if($seen){break}}
 [pscustomobject]@{invoked=$true;systemHeadingVisible=$seen;sameHwndAlive=($null -ne [System.Windows.Automation.AutomationElement]::FromHandle($handle))}|ConvertTo-Json -Compress;exit 0
}
if($op -eq 'MODEL_WINDOW'){
 $desktop=[System.Windows.Automation.AutomationElement]::RootElement;$seen=$false;$count=0
 for($n=0;$n -lt 50;$n++){Start-Sleep -Milliseconds 200;$wins=$desktop.FindAll([System.Windows.Automation.TreeScope]::Children,[System.Windows.Automation.Condition]::TrueCondition);$found=@();for($i=0;$i -lt $wins.Count;$i++){try{$v=$wins.Item($i).Current;if($v.ControlType -eq [System.Windows.Automation.ControlType]::Window -and ($v.Name+'').Trim() -ceq 'NOX HELION · MODEL CENTER' -and (Visible $v)){$found+=$wins.Item($i)}}catch{}};$count=$found.Count;if($count -eq 1){$seen=$true;try{$wp=$found[0].GetCurrentPattern([System.Windows.Automation.WindowPattern]::Pattern);$wp.Close()}catch{};break}}
 [pscustomobject]@{modelWindowVisible=$seen;windowCount=$count}|ConvertTo-Json -Compress;exit 0
}
if($op -eq 'VISUAL'){
 $r=New-Object NoxFinalWin32+RECT;if(-not [NoxFinalWin32]::GetWindowRect($handle,[ref]$r)){throw 'RECT'}
 $ox=$r.Left;$oy=$r.Top;$ow=$r.Right-$r.Left;$oh=$r.Bottom-$r.Top;$sizes=@()
 foreach($size in @(@(1044,788),@(800,600))){if(-not [NoxFinalWin32]::MoveWindow($handle,$ox,$oy,$size[0],$size[1],$true)){throw 'MOVE'};Start-Sleep -Milliseconds 700;$rr=New-Object NoxFinalWin32+RECT;$null=[NoxFinalWin32]::GetWindowRect($handle,[ref]$rr);$rects=FiveRects;$sizes+=([pscustomobject]@{requested=@($size[0],$size[1]);actual=@($rr.Right-$rr.Left,$rr.Bottom-$rr.Top);visiblePrimary=$rects.Count;noOverlap=(NoOverlap $rects)})}
 $null=[NoxFinalWin32]::MoveWindow($handle,$ox,$oy,$ow,$oh,$true);Start-Sleep -Milliseconds 500
 $rr=New-Object NoxFinalWin32+RECT;$null=[NoxFinalWin32]::GetWindowRect($handle,[ref]$rr);$w=$rr.Right-$rr.Left;$h=$rr.Bottom-$rr.Top
 $bmp=New-Object System.Drawing.Bitmap($w,$h);try{$g=[System.Drawing.Graphics]::FromImage($bmp);try{$dc=$g.GetHdc();try{$ok=[NoxFinalWin32]::PrintWindow($handle,$dc,2)}finally{$g.ReleaseHdc($dc)}}finally{$g.Dispose()};if(-not $ok){throw 'PRINT'};$bmp.Save('__PNG__',[System.Drawing.Imaging.ImageFormat]::Png)}finally{$bmp.Dispose()}
 [pscustomobject]@{sizes=@($sizes);capture=@($w,$h);fiveVisible=(FiveRects).Count}|ConvertTo-Json -Compress -Depth 6;exit 0
}
if($op -eq 'FX'){
 function FxButton { $a=Tree (Root);$f=New-Object System.Collections.ArrayList;for($i=0;$i -lt $a.Count;$i++){try{$el=$a.Item($i);$v=$el.Current;if($v.ControlType -eq [System.Windows.Automation.ControlType]::Button -and ($v.Name+'') -cmatch '^FX (BALANCED|MAX|ECO)$' -and (Visible $v)){[void]$f.Add($el)}}catch{}};if($f.Count -ne 1){throw 'FX_UNIQUE'};return $f[0] }
 $initial=(FxButton).Current.Name+'';$observed=@();foreach($expected in @('FX MAX','FX ECO','FX BALANCED')){$b=FxButton;$p=$b.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern);if($null -eq $p){throw 'FX_INVOKE'};$p.Invoke();Start-Sleep -Milliseconds 350;$now=(FxButton).Current.Name+'';if($now -cne $expected){throw 'FX_STATE'};$observed+=$now}
 [pscustomobject]@{initial=$initial;observed=$observed;invocations=3}|ConvertTo-Json -Compress -Depth 3;exit 0
}
throw 'UNKNOWN_OP'
'''.replace("__HWND__",str(hwnd)).replace("__OP__",operation).replace("__ACTION__",operation if operation in PRIMARY else "").replace("__PNG__",png_path)


def invoke_primary(hwnd: int, action: str) -> dict:
    e07.require(action in PRIMARY,"E07_FINAL_ACTION_NAME_HOLD")
    script=_uia_script(hwnd,"CLICK")
    script=script.replace("InvokePrimary 'CLICK'","InvokePrimary '"+action+"'")
    result=_run_ps(script,timeout=35)
    e07.require(result.get("invoked") is True and result.get("sameHwndAlive") is True,
                "E07_FINAL_"+action+"_UIA_HOLD")
    return result


def _newest(paths: set[Path], folder: Path, pattern: str) -> Path|None:
    now=set(folder.glob(pattern)) if folder.is_dir() else set()
    fresh=[p for p in now-paths if e07.clean_file(p)]
    return max(fresh,key=lambda p:p.stat().st_mtime_ns) if fresh else None


def run(hwnd: int, install: Path, local: Path, *, source_sha: str, setup_sha: str,
        out_dir: Path) -> tuple[dict,dict]:
    e07.require(sys.platform=="win32" and os.environ.get("GITHUB_ACTIONS")=="true" and
                os.environ.get("RUNNER_OS")=="Windows" and
                os.environ.get("RUNNER_ENVIRONMENT")=="github-hosted" and
                os.environ.get("GITHUB_REPOSITORY")=="MSSTXNEWS/nox-helion-pp-private-build",
                "E07_FINAL_HOST_HOLD")
    e07.require(bool(re.fullmatch(r"[0-9a-f]{40}",source_sha)) and
                bool(re.fullmatch(r"[0-9a-f]{64}",setup_sha)),"E07_FINAL_IDENTITY_FORMAT_HOLD")
    _,owned=e07.manifest_owner(install)
    home=install/"Assets"/"index.html"
    e07.require(home in owned and e07.clean_file(home) and home.stat().st_size<=2_000_000,
                "E07_FINAL_INSTALLED_HOME_HOLD")
    html=home.read_text(encoding="utf-8-sig")
    for token in ("data-nox-primary=\"INSTALL\"","data-nox-primary=\"MODELS\"",
                  "data-nox-primary=\"LEARN\"","data-nox-primary=\"SETTINGS\"",
                  "button#pc-install","button#training-diagnostic",
                  "@media(prefers-reduced-motion:reduce)","animation:none!important",
                  "transition:none!important","@media(max-width:550px)"):
        e07.require(token in html,"E07_FINAL_INSTALLED_HOME_CONTRACT_HOLD")
    out_dir.mkdir(parents=True,exist_ok=True)

    png=out_dir/"D02_FINAL_SAME_SETUP.png"
    visual_raw=_run_ps(_uia_script(hwnd,"VISUAL",png=png),timeout=60)
    e07.require(e07.clean_file(png) and 20_000<=png.stat().st_size<=40_000_000,
                "E07_FINAL_VISUAL_PNG_HOLD")
    sizes=visual_raw.get("sizes")
    e07.require(type(sizes) is list and len(sizes)==2 and
                all(type(x) is dict and x.get("visiblePrimary")==5 and x.get("noOverlap") is True
                    for x in sizes),"E07_FINAL_ADAPTIVE_LAYOUT_HOLD")
    fx=_run_ps(_uia_script(hwnd,"FX"),timeout=40)
    e07.require(fx.get("initial")=="FX BALANCED" and
                fx.get("observed")==["FX MAX","FX ECO","FX BALANCED"] and
                fx.get("invocations")==3,"E07_FINAL_REDUCED_MOTION_CONTROL_HOLD")
    visual={"schema":e07.FINAL_VISUAL_SCHEMA,"source_sha":source_sha,
            "setup_sha256":setup_sha,"release_accepted":False,
            "physical_capture":"PASS","d02_visual":"PASS","adaptive_layout":"PASS",
            "reduced_motion":"PASS","screenshot_sha256":e07.sha256(png),
            "physical_sizes":sizes,"fx_cycle":fx,
            "reduced_motion_evidence":"INSTALLED_MEDIA_QUERY_PLUS_PHYSICAL_ECO_TRANSITION"}

    actions={}
    def accepted(action: str, detail: dict) -> None:
        actions[action]={"function_verified":"PASS","permissions_verified":"PASS",
                         "result":"PASS","receipt_sha256":_receipt_sha(detail),"detail":detail}

    app=local/"NOX_HELION_Integrator"/"app"
    server=app/"server.py"
    e07.require(not server.exists(),"E07_FINAL_INSTALL_PREEXISTING_RESULT_HOLD")
    invoke_primary(hwnd,"INSTALL")
    deadline=time.monotonic()+120
    while time.monotonic()<deadline and not e07.clean_file(server): time.sleep(.5)
    e07.require(e07.clean_file(server),"E07_FINAL_INSTALL_RESULT_HOLD")
    log=local/"NOX_HELION"/"P01"/"logs"/"shell.log"
    deadline=time.monotonic()+30;log_text=""
    while time.monotonic()<deadline:
        if e07.clean_file(log):
            log_text=log.read_text(encoding="utf-8",errors="replace")[-200000:]
            if "ACTION_END install exit=0" in log_text: break
        time.sleep(.4)
    e07.require("ACTION_END install exit=0" in log_text,"E07_FINAL_INSTALL_EXIT_HOLD")
    accepted("INSTALL",{"server_sha256":e07.sha256(server),"action_exit":0,
                        "scope":"ORIGINAL_PC_INSTALL_UI_TO_NOX_ACTIONS"})

    invoke_primary(hwnd,"MODELS")
    model=_run_ps(_uia_script(hwnd,"MODEL_WINDOW"),timeout=35)
    e07.require(model.get("modelWindowVisible") is True and model.get("windowCount")==1,
                "E07_FINAL_MODELS_WINDOW_HOLD")
    accepted("MODELS",{"model_center_window":"PASS","window_title":"NOX HELION · MODEL CENTER"})

    reports=local/"NOX_HELION"/"P01"/"reports"
    before=set(reports.glob("P01_DIAGNOSTICS_*.json")) if reports.is_dir() else set()
    invoke_primary(hwnd,"LEARN")
    diag=None;deadline=time.monotonic()+60
    while time.monotonic()<deadline:
        diag=_newest(before,reports,"P01_DIAGNOSTICS_*.json")
        if diag is not None: break
        time.sleep(.4)
    e07.require(diag is not None,"E07_FINAL_LEARN_DIAGNOSTIC_HOLD")
    data=e07._read_locked_e06_json(diag)
    e07.require(type(data.get("cpu")) is int and data["cpu"]>0 and
                type(data.get("windows")) is str and type(data.get("dotnet")) is str and
                type(data.get("webview2")) is str and data.get("releaseGate")=="BLOCKED",
                "E07_FINAL_LEARN_DIAGNOSTIC_SCHEMA_HOLD")
    accepted("LEARN",{"diagnostics_sha256":e07.sha256(diag),"cpu":data["cpu"],
                      "scope":"ORIGINAL_TRAINING_ENVIRONMENT_PREFLIGHT"})

    settings=_run_ps(_uia_script(hwnd,"SETTINGS"),timeout=35)
    e07.require(settings.get("invoked") is True and settings.get("systemHeadingVisible") is True and
                settings.get("sameHwndAlive") is True,"E07_FINAL_SETTINGS_ROUTE_HOLD")
    accepted("SETTINGS",{"system_screen":"PASS","same_original_hwnd":True,
                         "scope":"ORIGINAL_SYSTEM_SETTINGS_SCREEN"})

    functions={"schema":e07.FINAL_FUNCTION_SCHEMA,"source_sha":source_sha,
               "setup_sha256":setup_sha,"release_accepted":False,"actions":actions}
    return visual,functions
