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
import tempfile
import zlib

import independent_setup_e07 as e07

PRIMARY=("CHAT","INSTALL","MODELS","LEARN","SETTINGS")


def _receipt_sha(value: dict) -> str:
    raw=json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def nonrelease_action_observation(action: str, detail: dict) -> dict:
    """Record one verified observation without inventing a privileged PASS."""
    e07.require(action in PRIMARY[1:] and type(detail) is dict and bool(detail),
                "E07_FINAL_FUNCTION_OBSERVATION_SCHEMA_HOLD")
    return {"function_verified":"NOT_TESTED",
            "permissions_verified":"NOT_TESTED",
            "result":"HOLD",
            "receipt_sha256":_receipt_sha(detail),
            "observed_effect":detail,
            "scope":"INSTALLED_UI_OBSERVATION_NOT_FULL_FUNCTION_PASS"}


def _bounded_uia_failure(stdout: object, phase: str) -> str:
    """Only exact known UIA failure codes; no raw Windows output in receipts."""
    fallback = "E07_FINAL_UIA_" + phase + "_PROCESS_EXIT_HOLD"
    if type(stdout) is not str or not (1 <= len(stdout) <= 140):
        return fallback
    reason = stdout.strip()
    allowed = (r"E07_FINAL_UIA_" + re.escape(phase)
        + r"_(?:ORIGINAL_CONTROL_NOT_UNIQUE|PRIMARY_DOCK_NOT_UNIQUE|BUTTON_(?:CHAT|INSTALL|MODELS|LEARN|SETTINGS)_NOT_UNIQUE|"
          r"NO_ROOT|TREE_LIMIT|NO_INVOKE|RECT|MOVE|PRINT|"
          r"FX_UNIQUE|FX_INVOKE|FX_STATE|UNKNOWN_OP|VISUAL_STAGE_(?:RESIZE|DOCK|CAPTURE|RESTORE))_HOLD")
    return reason if re.fullmatch(allowed, reason) else fallback


def _run_ps(source: str, *, timeout: int=90, phase: str="UNKNOWN", env: dict|None=None) -> dict:
    e07.require(phase in (*PRIMARY, "VISUAL", "MODEL_WINDOW", "INSTALL_CONTROL", "FX", "UNKNOWN"),
                "E07_FINAL_UIA_PHASE_HOLD")
    # The real native UIA script exceeds Windows' 32767-character command-line
    # limit after UTF-16/Base64 -EncodedCommand expansion. Use one private,
    # newly-created file on the ephemeral runner instead; no extra authority.
    try:
        with tempfile.TemporaryDirectory(prefix="nox-e07-uia-",
                                         dir=os.environ["RUNNER_TEMP"]) as temp_root:
            script_path=Path(temp_root)/"independent-uia.ps1"
            # Windows PowerShell 5.1 requires the BOM for UTF-8 Cyrillic UIA.
            with script_path.open("x",encoding="utf-8-sig",newline="\n") as stream:
                stream.write(source)
            p=subprocess.run(
                ["powershell.exe","-NoProfile","-NonInteractive",
                 "-ExecutionPolicy","Bypass","-File",str(script_path)],
                capture_output=True,timeout=timeout,check=False,
                encoding="utf-8",errors="replace",env=env)
    except (OSError,subprocess.TimeoutExpired):
        raise e07.Hold("E07_FINAL_UIA_PROCESS_HOLD") from None
    # Keep bounded, non-sensitive diagnostic codes so one physical Windows
    # attempt identifies which probe phase failed. No stderr/stdout, paths,
    # window titles, user data or arbitrary PowerShell output enter receipts.
    if p.returncode != 0:
        raise e07.Hold(_bounded_uia_failure(p.stdout, phase))
    if not 0 < len(p.stdout) <= 131072:
        raise e07.Hold("E07_FINAL_UIA_"+phase+"_OUTPUT_BOUNDS_HOLD")
    try:
        result=json.loads(p.stdout.strip())
    except (ValueError,UnicodeError):
        raise e07.Hold("E07_FINAL_UIA_"+phase+"_JSON_HOLD") from None
    e07.require(type(result) is dict,"E07_FINAL_UIA_JSON_HOLD")
    return result



def dismiss_readonly_models_catalog_consent(hwnd: int) -> dict:
    """Close only a known *navigation-generated* dialog with its negative action.

    The real same-WPF UIA navigation can leave an owner consent dialog open
    for models.catalog. Its presence must never count as permission PASS or
    block the separate INSTALL/MODELS/LEARN/SETTINGS physical observations.
    Unknown/privileged dialogs remain untouched and fail closed.
    """
    e07.require(type(hwnd) is int and hwnd>0, "E07_FINAL_NAV_DIALOG_HWND_HOLD")
    ps = r'''
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[System.Text.Encoding]::UTF8
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$h=[IntPtr]__HWND__
$root=[System.Windows.Automation.AutomationElement]::FromHandle($h)
if($null -eq $root){throw 'E07_NAV_DIALOG_ORIGINAL_ROOT_HOLD'}
$pidNumber=[int]$root.Current.ProcessId
if($pidNumber -le 0){throw 'E07_NAV_DIALOG_ORIGINAL_PID_HOLD'}
$desktop=[System.Windows.Automation.AutomationElement]::RootElement
function OwnerConsent {
 $wins=$desktop.FindAll([System.Windows.Automation.TreeScope]::Children,
                         [System.Windows.Automation.Condition]::TrueCondition)
 if($wins.Count -gt 2048){throw 'E07_NAV_DIALOG_TREE_LIMIT_HOLD'}
 $found=@()
 foreach($w in $wins){
  try {
   $v=$w.Current
   if($v.ProcessId -eq $pidNumber -and
      ($v.Name+'').Trim() -ceq 'NOX HELION · Native consent' -and
      $v.ControlType -eq [System.Windows.Automation.ControlType]::Window){
     $found+=,$w
   }
  }catch{}
 }
 return $found
}
$dialogs=@(OwnerConsent)
if($dialogs.Count -gt 1){throw 'E07_NAV_DIALOG_MULTIPLE_OWNER_HOLD'}
if($dialogs.Count -eq 0){
 [pscustomobject]@{schema='NOX-E07-NAV-DIALOG-CLOSE-v1';status='ABSENT';
   ownerProcessIdMatched=$true;negativeActionInvoked=$false;
   permissionGranted=$false}|ConvertTo-Json -Compress;exit 0
}
$dialog=$dialogs[0]
$tree=$dialog.FindAll([System.Windows.Automation.TreeScope]::Descendants,
                       [System.Windows.Automation.Condition]::TrueCondition)
if($tree.Count -gt 512){throw 'E07_NAV_DIALOG_CHILDREN_LIMIT_HOLD'}
$routeCount=0
$no=@()
foreach($el in $tree){
 try {
  $v=$el.Current
  if($v.ControlType -eq [System.Windows.Automation.ControlType]::Text -and
     ($v.Name+'').Trim() -ceq 'Разрешить локальный маршрут NOX: models.catalog?'){
    $routeCount++
  }
  if($v.ControlType -eq [System.Windows.Automation.ControlType]::Button -and
     ($v.Name+'').Trim() -in @('No','Нет') -and $v.IsEnabled -and
     -not $v.IsOffscreen -and $v.BoundingRectangle.Width -ge 20){
    $no+=,$el
  }
 }catch{}
}
if($routeCount -ne 1 -or $no.Count -ne 1){
 throw 'E07_NAV_DIALOG_NOT_READONLY_CATALOG_HOLD'
}
$p=$no[0].GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
if($null -eq $p){throw 'E07_NAV_DIALOG_NEGATIVE_INVOKE_HOLD'}
$p.Invoke()
$closed=$false
for($i=0;$i -lt 20;$i++){
 Start-Sleep -Milliseconds 200
 if(@(OwnerConsent).Count -eq 0){$closed=$true;break}
}
if(-not $closed){throw 'E07_NAV_DIALOG_NEGATIVE_NOT_CLOSED_HOLD'}
[pscustomobject]@{schema='NOX-E07-NAV-DIALOG-CLOSE-v1';status='NEGATIVE_DISMISSED';
 ownerProcessIdMatched=$true;negativeActionInvoked=$true;
 permissionGranted=$false}|ConvertTo-Json -Compress
'''.replace("__HWND__",str(hwnd))
    raw=_run_ps(ps,timeout=25,phase="UNKNOWN")
    e07.require(raw.get("schema")=="NOX-E07-NAV-DIALOG-CLOSE-v1" and
                raw.get("status") in ("ABSENT","NEGATIVE_DISMISSED") and
                raw.get("ownerProcessIdMatched") is True and
                raw.get("permissionGranted") is False and
                raw.get("negativeActionInvoked") is
                    (raw.get("status")=="NEGATIVE_DISMISSED"),
                "E07_FINAL_NAV_DIALOG_NEGATIVE_RECEIPT_HOLD")
    return raw


def qa_approve_readonly_catalog_consent(hwnd: int) -> dict:
    """Test-only owner consent for exactly models.catalog on ephemeral GitHub Windows.

    This is NOT approval for downloading models, installation or training.
    The real WPF Yes action is accepted only for one exact same-PID dialog and
    route. User-owned Windows machines can never call this QA helper.
    """
    e07.require(type(hwnd) is int and hwnd>0 and sys.platform=="win32" and
                os.environ.get("GITHUB_ACTIONS")=="true" and
                os.environ.get("RUNNER_OS")=="Windows" and
                os.environ.get("RUNNER_ENVIRONMENT")=="github-hosted" and
                os.environ.get("GITHUB_REPOSITORY")=="MSSTXNEWS/nox-helion-pp-private-build",
                "E07_CATALOG_QA_HOST_NOT_AUTHORIZED_HOLD")
    ps = r'''
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[System.Text.Encoding]::UTF8
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$h=[IntPtr]__HWND__
$root=[System.Windows.Automation.AutomationElement]::FromHandle($h)
if($null -eq $root){throw 'E07_CATALOG_QA_ORIGINAL_HWND_HOLD'}
$pidNumber=[int]$root.Current.ProcessId
if($pidNumber -le 0){throw 'E07_CATALOG_QA_ORIGINAL_PID_HOLD'}
$desktop=[System.Windows.Automation.AutomationElement]::RootElement
function MatchCatalogDialog {
 $wins=$desktop.FindAll([System.Windows.Automation.TreeScope]::Children,
                         [System.Windows.Automation.Condition]::TrueCondition)
 if($wins.Count -gt 2048){throw 'E07_CATALOG_QA_TREE_LIMIT_HOLD'}
 $found=@()
 foreach($w in $wins){
  try{
   $v=$w.Current
   if($v.ProcessId -eq $pidNumber -and
      ($v.Name+'').Trim() -ceq 'NOX HELION · Native consent' -and
      $v.ControlType -eq [System.Windows.Automation.ControlType]::Window){
    $found+=,$w
   }
  }catch{}
 }
 return $found
}
$dialogs=@(MatchCatalogDialog)
if($dialogs.Count -gt 1){throw 'E07_CATALOG_QA_MULTIPLE_OWNER_DIALOGS_HOLD'}
if($dialogs.Count -eq 0){
 [pscustomobject]@{schema='NOX-E07-QA-CATALOG-CONSENT-v1';status='ABSENT';
  sameOwnerProcess=$true;readOnlyCatalogConsentGranted=$false;
  fullModelPermissionsVerified=$false}|ConvertTo-Json -Compress;exit 0
}
$tree=$dialogs[0].FindAll([System.Windows.Automation.TreeScope]::Descendants,
                          [System.Windows.Automation.Condition]::TrueCondition)
if($tree.Count -gt 512){throw 'E07_CATALOG_QA_CHILDREN_LIMIT_HOLD'}
$routeCount=0;$yes=@()
foreach($element in $tree){
 try{
  $v=$element.Current
  if($v.ControlType -eq [System.Windows.Automation.ControlType]::Text -and
     ($v.Name+'').Trim() -ceq 'Разрешить локальный маршрут NOX: models.catalog?'){$routeCount++}
  if($v.ControlType -eq [System.Windows.Automation.ControlType]::Button -and
     ($v.Name+'').Trim() -in @('Yes','Да') -and $v.IsEnabled -and
     -not $v.IsOffscreen -and $v.BoundingRectangle.Width -ge 20){$yes+=,$element}
 }catch{}
}
if($routeCount -ne 1 -or $yes.Count -ne 1){throw 'E07_CATALOG_QA_UNEXPECTED_CONSENT_HOLD'}
$pattern=$yes[0].GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
if($null -eq $pattern){throw 'E07_CATALOG_QA_YES_INVOKE_HOLD'}
$pattern.Invoke()
$closed=$false
for($i=0;$i -lt 20;$i++){
 Start-Sleep -Milliseconds 200
 if(@(MatchCatalogDialog).Count -eq 0){$closed=$true;break}
}
if(-not $closed){throw 'E07_CATALOG_QA_YES_STILL_VISIBLE_HOLD'}
[pscustomobject]@{schema='NOX-E07-QA-CATALOG-CONSENT-v1';status='QA_READONLY_CATALOG_APPROVED';
 sameOwnerProcess=$true;readOnlyCatalogConsentGranted=$true;
 fullModelPermissionsVerified=$false}|ConvertTo-Json -Compress
'''.replace("__HWND__",str(hwnd))
    value=_run_ps(ps,timeout=25,phase="UNKNOWN")
    e07.require(value.get("schema")=="NOX-E07-QA-CATALOG-CONSENT-v1" and
                value.get("status") in ("ABSENT","QA_READONLY_CATALOG_APPROVED") and
                value.get("sameOwnerProcess") is True and
                value.get("fullModelPermissionsVerified") is False and
                value.get("readOnlyCatalogConsentGranted") is
                    (value.get("status")=="QA_READONLY_CATALOG_APPROVED"),
                "E07_CATALOG_QA_CONSENT_RECEIPT_HOLD")
    return value

def classify_fresh_original_install_log(data: bytes) -> dict:
    """Classify only bounded, newly appended REAL owner log rows.

    Never infer success from a pre-existing server.py, arbitrary stdout or a
    synthetic UI click. Expose no user paths, script output or stderr to E07.
    """
    e07.require(type(data) is bytes and len(data)<=200000,
                "E07_FINAL_INSTALL_LOG_BOUNDS_HOLD")
    # WPF shell.log has a space-separated timestamp; approved ISO rows also occur.
    # Do not treat an arbitrary line containing a successful-looking word as proof.
    stamp=rb"\[\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:\.\d{1,7})?(?:Z|[+-]\d{2}:\d{2})?\] "
    starts=list(re.finditer(rb"(?m)^"+stamp+rb"ACTION_START install\r?$",data))
    failures=list(re.finditer(rb"(?m)^"+stamp+rb"ACTION_FAIL install(?:[ \t][^\r\n]*)?\r?$",data))
    completed=list(re.finditer(rb"(?m)^"+stamp+rb"ACTION_END install exit=([0-9]{1,3})(?:[ \t][^\r\n]*)?\r?$",data))
    e07.require(len(starts)<=1 and len(completed)<=1 and len(failures)<=1,
                "E07_FINAL_INSTALL_DUPLICATE_OWNER_LOG_HOLD")
    # A log END/FAIL preceding this invocation's START cannot prove its result.
    # A standalone real ACTION_FAIL is a denial, never a success: preserve it
    # even if the native owner could not emit START before its exception.
    # Only successful-looking END must be strictly paired after this START.
    e07.require(not completed or (starts and starts[0].start()<completed[0].start()),
                "E07_FINAL_INSTALL_EVENT_ORDER_HOLD")
    return {"started":bool(starts),
            "owner_exit_code":int(completed[0].group(1)) if completed else None,
            "owner_exception":bool(failures)}

def _uia_script(hwnd: int, operation: str, *, png: Path|None=None) -> str:
    e07.require(type(hwnd) is int and hwnd>0,"E07_FINAL_BAD_HWND_HOLD")
    png_path=(str(png).replace("'","''") if png else "")
    return r'''$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[System.Text.Encoding]::UTF8
$__e07Operation='__OP__'
$__e07Stage='INIT'
# Deliberately allowlist physical UIA exceptions: no user paths, stderr,
# arbitrary titles, model data or tokens may enter the independent receipt.
trap {
 $why=$_.Exception.Message+''
 $reason='E07_FINAL_UIA_'+$__e07Operation+'_PROCESS_EXIT_HOLD'
 $stage=if($null -ne $__e07FailureStage){$__e07FailureStage}else{$__e07Stage}
 if($__e07Operation -eq 'VISUAL' -and $stage -in @('RESIZE','DOCK','CAPTURE','RESTORE')) {
   $reason='E07_FINAL_UIA_VISUAL_VISUAL_STAGE_'+$stage+'_HOLD'
 }
 if($why -eq 'ORIGINAL_CONTROL_NOT_UNIQUE'){
   $reason='E07_FINAL_UIA_'+$__e07Operation+'_ORIGINAL_CONTROL_NOT_UNIQUE_HOLD'
 } elseif($why -eq 'PRIMARY_DOCK_NOT_UNIQUE'){
   $reason='E07_FINAL_UIA_'+$__e07Operation+'_PRIMARY_DOCK_NOT_UNIQUE_HOLD'
 } elseif(($why -cmatch '^BUTTON_(CHAT|INSTALL|MODELS|LEARN|SETTINGS)_NOT_UNIQUE$') -or (@('NO_ROOT','TREE_LIMIT','NO_INVOKE','RECT','MOVE','PRINT','FX_UNIQUE','FX_INVOKE','FX_STATE','UNKNOWN_OP') -ccontains $why)) {
   $reason='E07_FINAL_UIA_'+$__e07Operation+'_'+$why+'_HOLD'
 }
 Write-Output $reason
 exit 2
}
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
if($__e07Operation -eq 'VISUAL'){
 Add-Type -AssemblyName System.Drawing
 Add-Type -AssemblyName WindowsBase
 Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class NoxFinalWin32 {
 [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left,Top,Right,Bottom; }
 [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h,out RECT r);
 [DllImport("user32.dll")] public static extern bool MoveWindow(IntPtr h,int x,int y,int w,int hgt,bool repaint);
 // Resize requests must not synchronously wait for a busy WebView2/WPF UI thread.
 // SWP_ASYNCWINDOWPOS | SWP_NOZORDER | SWP_NOACTIVATE; GetWindowRect below
 // still measures the ACTUAL physical window and fails on clamped geometry.
 [DllImport("user32.dll", SetLastError=true)] public static extern bool SetWindowPos(IntPtr h,IntPtr after,int x,int y,int w,int hgt,uint flags);
 [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h,IntPtr dc,uint flags);
 [DllImport("user32.dll")] public static extern bool ShowWindowAsync(IntPtr h,int c);
 [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
 [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
}
'@
}
$handle=[IntPtr]__HWND__
function Root { $r=[System.Windows.Automation.AutomationElement]::FromHandle($handle); if($null -eq $r){throw 'NO_ROOT'}; return $r }
# UIA FindAll yields AutomationElementCollection (IEnumerable). Unary comma prevents
# PowerShell function-output enumeration into Object[], preserving .Item(index).
function Tree($r) { $a=$r.FindAll([System.Windows.Automation.TreeScope]::Descendants,[System.Windows.Automation.Condition]::TrueCondition); if($a.Count -gt 4096){throw 'TREE_LIMIT'}; return ,$a }
# Same admission as the independent five-button source proof: small or
# clipped controls must never create a second real actionable button.
function Visible($v) { $b=$v.BoundingRectangle; return ($v.IsEnabled -and -not $v.IsOffscreen -and $b.Width -ge 20 -and $b.Height -ge 12) }
function Normalize([string]$s) { return ($s+'').Trim().TrimStart([char[]]@([char]0x2726,[char]0x2605,[char]0x2022,[char]0x20)).Trim().ToUpperInvariant() }
# The original WPF window may expose another CHAT outside EXPRESS.
# Admit exactly one geometric five-action dock on this SAME HWND. Original
# responsive CSS uses five columns on wide clients, three at <=800px and
# two at <=520px: a forced horizontal-row test misclassifies real 800px UI.
# Never infer success from just button names or a synthetic resize.
# UIA may expose multiple wrappers of the same original native element.
# Collapse ONLY Compare-identical controls; distinct original buttons stay
# separate and still fail strict unique-five-dock admission.
function SameElementSeen($items,$candidate) {
 foreach($prior in $items) {
  try { if([System.Windows.Automation.Automation]::Compare($prior.element,$candidate)) { return $true } }
  catch { } # Failure to compare never implies identical elements.
 }
 return $false
}
# Purely geometric admission over ACTUAL enabled/visible UIA element rectangles.
# Row-major original order and bounded gaps distinguish the true HOME dock
# from duplicate route buttons elsewhere in the WPF/WebView2 UIA tree.
function GridMatches($row,[int]$columns) {
 $names=@('CHAT','INSTALL','MODELS','LEARN','SETTINGS')
 $rects=@();foreach($name in $names){$rects+=,($row[$name].rect)}
 $base=$rects[0]
 for($i=0;$i -lt 5;$i++){
  $r=$rects[$i];$col=$i%$columns
  $rowStart=[int]([math]::Floor($i/$columns)*$columns)
  if($r.Width -lt 20 -or $r.Height -lt 12 -or
     [math]::Abs($r.Width-$base.Width) -gt [math]::Max(36,$base.Width*.25) -or
     [math]::Abs($r.Height-$base.Height) -gt [math]::Max(20,$base.Height*.25)){return $false}
  if($col -eq 0){
   if($rowStart -gt 0){
    $above=$rects[$rowStart-$columns]
    $gap=$r.Top-$above.Bottom
    if($gap -lt -1 -or $gap -gt 55 -or
       [math]::Abs($r.Left-$base.Left) -gt 24){return $false}
   }
  } else {
   $prev=$rects[$i-1]
   $gap=$r.Left-$prev.Right
   if($gap -lt -1 -or $gap -gt 45 -or
      [math]::Abs(($r.Top+$r.Height/2)-($prev.Top+$prev.Height/2)) -gt 16){return $false}
  }
  if($rowStart -gt 0 -and
     [math]::Abs($r.Left-$rects[$col].Left) -gt 24){return $false}
  for($j=0;$j -lt $i;$j++){
   $p=$rects[$j]
   if($r.Left -lt $p.Right -and $r.Right -gt $p.Left -and
      $r.Top -lt $p.Bottom -and $r.Bottom -gt $p.Top){return $false}
  }
 }
 return $true
}
# IsOffscreen=False can still mean a partially clipped UIA button.
# Every accepted dock element must stay inside the original installed WPF HWND.
# This is visual admission only, never a privileged action or release PASS.
function WithinOriginalHwnd($rect,$frame) {
 if($frame.IsEmpty -or $frame.Width -lt 320 -or $frame.Height -lt 200){return $false}
 $pad=2
 return ($rect.Left -ge ($frame.Left - $pad) -and
         $rect.Top -ge ($frame.Top - $pad) -and
         $rect.Right -le ($frame.Right + $pad) -and
         $rect.Bottom -le ($frame.Bottom + $pad))
}
# IsOffscreen=False and an inside-HWND rectangle cannot rule out occlusion.
# Observe the actual UIA point on the physical Windows desktop. Unrelated
# dialogs, sidebar overlays, or absent automation ancestry must HOLD.
function HitTestOriginalPrimary($button,$bounds) {
 try {
  if($null -eq $button -or $bounds.IsEmpty -or
     $bounds.Width -lt 20 -or $bounds.Height -lt 12){return $false}
  $cx=[double]($bounds.Left+$bounds.Width/2)
  $cy=[double]($bounds.Top+$bounds.Height/2)
  if([double]::IsNaN($cx) -or [double]::IsInfinity($cx) -or
     [double]::IsNaN($cy) -or [double]::IsInfinity($cy)){return $false}
  $hit=[System.Windows.Automation.AutomationElement]::FromPoint(
   [System.Windows.Point]::new($cx,$cy))
  if($null -eq $hit){return $false}
  $walker=[System.Windows.Automation.TreeWalker]::RawViewWalker
  for($depth=0;$depth -lt 32 -and $null -ne $hit;$depth++){
   if([System.Windows.Automation.Automation]::Compare($hit,$button)){return $true}
   $hit=$walker.GetParent($hit)
  }
 } catch { return $false }
 return $false
}
function PrimaryDock {
 $names=@('CHAT','INSTALL','MODELS','LEARN','SETTINGS')
 $seen=@{};foreach($n in $names){$seen[$n]=New-Object System.Collections.ArrayList}
 $originalRoot=Root
 $frame=$originalRoot.Current.BoundingRectangle
 if($frame.IsEmpty -or $frame.Width -lt 320 -or $frame.Height -lt 200){throw 'RECT'}
 $a=Tree $originalRoot
 for($i=0;$i -lt $a.Count;$i++){
  try{
   $el=$a.Item($i);$v=$el.Current
   if($v.ControlType -ne [System.Windows.Automation.ControlType]::Button){continue}
   $name=Normalize $v.Name
   if($name -notin $names -or -not (Visible $v)){continue}
   $rect=$v.BoundingRectangle
   if($rect.Width -lt 20 -or $rect.Height -lt 12){continue}
   if(-not (WithinOriginalHwnd $rect $frame)){continue}
   if($__e07Operation -eq 'VISUAL' -and -not (HitTestOriginalPrimary $el $rect)){continue}
   if(-not (SameElementSeen -items ($seen[$name]) -candidate $el)) {
    [void]$seen[$name].Add([pscustomobject]@{element=$el;rect=$rect})
   }
  }catch{}
 }
 $clusters=New-Object System.Collections.ArrayList
 foreach($n in @('CHAT','INSTALL','MODELS','LEARN','SETTINGS')){
  # Bound combinations: fail closed on anomalous or duplicated UIA trees.
  if($seen[$n].Count -lt 1 -or $seen[$n].Count -gt 6){throw 'PRIMARY_DOCK_NOT_UNIQUE'}
 }
 foreach($chat in @($seen['CHAT'].ToArray())){
 foreach($install in @($seen['INSTALL'].ToArray())){
 foreach($models in @($seen['MODELS'].ToArray())){
 foreach($learn in @($seen['LEARN'].ToArray())){
 foreach($settings in @($seen['SETTINGS'].ToArray())){
  $row=@{CHAT=$chat;INSTALL=$install;MODELS=$models;LEARN=$learn;SETTINGS=$settings}
  foreach($columns in @(5,3,2)){
   if(GridMatches $row $columns){[void]$clusters.Add($row);break}
  }
 }}}}}
 if($clusters.Count -ne 1){throw 'PRIMARY_DOCK_NOT_UNIQUE'}
 return $clusters[0]
}
function OneButton([string]$name) {
 $dock=PrimaryDock
 if($null -eq $dock[$name]){throw ('BUTTON_'+$name+'_NOT_UNIQUE')}
 return $dock[$name].element
}
function OriginalPcInstall {
 # Trigger the ORIGINAL R11 WebView2 install control, not the EXPRESS
 # five-button dock (INSTALL only navigates to CONTROL).
 # A missing/ambiguous UIA AutomationId must HOLD; never click by position.
 $a=Tree (Root)
 $matches=New-Object System.Collections.ArrayList
 for($i=0;$i -lt $a.Count;$i++){
  try{
   $el=$a.Item($i);$v=$el.Current
   if($v.ControlType -ne [System.Windows.Automation.ControlType]::Button){continue}
   if(($v.AutomationId+'').Trim() -cne 'pc-install' -or -not (Visible $v)){continue}
   if(-not (SameElementSeen -items $matches -candidate $el)){[void]$matches.Add([pscustomobject]@{element=$el})}
  }catch{}
 }
 if($matches.Count -ne 1){throw 'ORIGINAL_CONTROL_NOT_UNIQUE'}
 return $matches[0].element
}
function InvokePrimary([string]$name){$b=OneButton $name;$p=$b.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern);if($null -eq $p){throw 'NO_INVOKE'};$p.Invoke();Start-Sleep -Milliseconds 400;return $true}
function FiveRects {
 $dock=PrimaryDock
 $out=@();foreach($name in @('CHAT','INSTALL','MODELS','LEARN','SETTINGS')){$r=$dock[$name].rect;$out+=([pscustomobject]@{name=$name;x=[int]$r.X;y=[int]$r.Y;width=[int]$r.Width;height=[int]$r.Height})};return @($out)
}
function NoOverlap($rects){for($i=0;$i -lt $rects.Count;$i++){for($j=$i+1;$j -lt $rects.Count;$j++){$a=$rects[$i];$b=$rects[$j];if($a.x -lt ($b.x+$b.width) -and ($a.x+$a.width) -gt $b.x -and $a.y -lt ($b.y+$b.height) -and ($a.y+$a.height) -gt $b.y){return $false}}};return $true}
function SaveAdaptiveHold([int]$requestedWidth) {
 # Diagnostic ONLY after UIA failed; never supplies a layout PASS.
 if($requestedWidth -notin @(800,1044)){return}
 $bounds=[NoxFinalWin32+RECT]::new()
 if(-not [NoxFinalWin32]::GetWindowRect($handle,[ref]$bounds)){return}
 $bw=[int]($bounds.Right-$bounds.Left);$bh=[int]($bounds.Bottom-$bounds.Top)
 if($bw -lt 320 -or $bw -gt 2200 -or $bh -lt 320 -or $bh -gt 1600){return}
 $photo=[System.Drawing.Bitmap]::new($bw,$bh)
 try {
  $graphics=[System.Drawing.Graphics]::FromImage($photo)
  try {
   $null=[NoxFinalWin32]::ShowWindowAsync($handle,9)
   $null=[NoxFinalWin32]::SetForegroundWindow($handle)
   Start-Sleep -Milliseconds 200
   if([NoxFinalWin32]::GetForegroundWindow() -ne $handle){return}
   $graphics.CopyFromScreen($bounds.Left,$bounds.Top,0,0,$photo.Size,
     [System.Drawing.CopyPixelOperation]::SourceCopy)
  } finally {$graphics.Dispose()}
  $base=[System.IO.Path]::GetDirectoryName('__PNG__')
  $target=[System.IO.Path]::Combine($base,'D02_ADAPTIVE_'+$requestedWidth+'.png')
  $photo.Save($target,[System.Drawing.Imaging.ImageFormat]::Png)
 } finally {$photo.Dispose()}
}
$op='__OP__'
if($op -eq 'INSTALL_CONTROL'){
 # Source-locked EXPRESS primary already delegates its one trusted user click
 # to original #pc-install. Inspect existing owner control: NEVER Invoke twice.
 $b=OriginalPcInstall
 $p=$b.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
 if($null -eq $p){throw 'NO_INVOKE'}
 [pscustomobject]@{originalControlPresent=$true;invokePatternAvailable=$true;sameHwndAlive=($null -ne [System.Windows.Automation.AutomationElement]::FromHandle($handle))}|ConvertTo-Json -Compress;exit 0
}
if($op -in @('CHAT','INSTALL','MODELS','LEARN')){ [pscustomobject]@{invoked=(InvokePrimary '__ACTION__');sameHwndAlive=($null -ne [System.Windows.Automation.AutomationElement]::FromHandle($handle))}|ConvertTo-Json -Compress; exit 0 }
if($op -eq 'SETTINGS'){
 $null=InvokePrimary 'SETTINGS';$seen=$false
 for($n=0;$n -lt 40;$n++){Start-Sleep -Milliseconds 200;$a=Tree (Root);for($i=0;$i -lt $a.Count;$i++){try{$v=$a.Item($i).Current;if($v.ControlType -eq [System.Windows.Automation.ControlType]::Text -and ($v.Name+'').Trim() -ceq 'СИСТЕМА' -and (Visible $v)){$seen=$true;break}}catch{}};if($seen){break}}
 [pscustomobject]@{invoked=$true;systemHeadingVisible=$seen;sameHwndAlive=($null -ne [System.Windows.Automation.AutomationElement]::FromHandle($handle))}|ConvertTo-Json -Compress;exit 0
}
if($op -eq 'MODEL_WINDOW'){
 # The original approved C# OneHost does NOT spawn a second WPF Model Center:
 # MainWindow.NativeP02.cs navigates its existing trusted WebView2 to
 # https://nox.local/creative/modelcenter/index.html after native owner ACL
 # and explicit catalog consent. Probe the same ORIGINAL installed HWND.
 $root=Root;$ownerProcessId=[int]$root.Current.ProcessId
 if($ownerProcessId -le 0){throw 'NO_ROOT'}
 $seen=$false;$count=0;$heading=$false
 for($n=0;$n -lt 50;$n++){
  Start-Sleep -Milliseconds 200
  $a=Tree (Root);$count=0;$heading=$false
  for($i=0;$i -lt $a.Count;$i++){
   try{
    $v=$a.Item($i).Current;$name=($v.Name+'').Trim()
    if($v.ControlType -eq [System.Windows.Automation.ControlType]::Document -and
       $name -ceq 'NOX · MODEL CORE' -and (Visible $v)){$count++}
    if($v.ControlType -eq [System.Windows.Automation.ControlType]::Text -and
       $name -ceq 'Модели' -and (Visible $v)){$heading=$true}
   }catch{}
  }
  if($count -eq 1 -and $heading){$seen=$true;break}
 }
 [pscustomobject]@{
  modelPageVisible=$seen;modelDocumentCount=$count;modelHeadingVisible=$heading;
  sameOriginalHwndAlive=($null -ne [System.Windows.Automation.AutomationElement]::FromHandle($handle));
  originalOwnerProcessIdPositive=($ownerProcessId -gt 0)
 }|ConvertTo-Json -Compress;exit 0
}
if($op -eq 'VISUAL'){
 $r=[NoxFinalWin32+RECT]::new();if(-not [NoxFinalWin32]::GetWindowRect($handle,[ref]$r)){throw 'RECT'}
 $ox=$r.Left;$oy=$r.Top;$ow=$r.Right-$r.Left;$oh=$r.Bottom-$r.Top;$sizes=@()
 $__e07FailureStage=$null
 try {
 $__e07Stage='RESIZE'
 # Actual HWND must be foreground for physical UIA point admission.
 $null=[NoxFinalWin32]::ShowWindowAsync($handle,9)
 $null=[NoxFinalWin32]::SetForegroundWindow($handle)
 Start-Sleep -Milliseconds 200
 if([NoxFinalWin32]::GetForegroundWindow() -ne $handle){throw 'PRINT'}
 foreach($size in @([pscustomobject]@{width=1044;height=788},[pscustomobject]@{width=800;height=600})){$__e07Stage='RESIZE';$width=[int]$size.width;$height=[int]$size.height;if(-not [NoxFinalWin32]::SetWindowPos($handle,[IntPtr]::Zero,0,0,$width,$height,[uint32]0x4014)){throw 'MOVE'};Start-Sleep -Milliseconds 700;$rr=[NoxFinalWin32+RECT]::new();$null=[NoxFinalWin32]::GetWindowRect($handle,[ref]$rr);$__e07Stage='DOCK';$rects=$null
 for($tryDock=0;$tryDock -lt 30;$tryDock++){
  try{$rects=FiveRects;break}
  catch{
   if(($_.Exception.Message+'') -ne 'PRIMARY_DOCK_NOT_UNIQUE'){throw}
   Start-Sleep -Milliseconds 300
  }
 }
 if($null -eq $rects){try{SaveAdaptiveHold $width}catch{}}
 if($null -eq $rects){throw 'PRIMARY_DOCK_NOT_UNIQUE'}
 $sizes+=([pscustomobject]@{requested=@($width,$height);actual=@($rr.Right-$rr.Left,$rr.Bottom-$rr.Top);visiblePrimary=$rects.Count;noOverlap=(NoOverlap $rects)})}
 } catch {
  # Preserve the original failure stage even though finally always restores
  # the original size. Previously every DOCK failure was reported as RESTORE.
  $__e07FailureStage=$__e07Stage
  throw
 } finally {
  # Restore original WPF HWND even when a UIA resize or button lookup fails.
  $__e07Stage='RESTORE';$null=[NoxFinalWin32]::SetWindowPos($handle,[IntPtr]::Zero,$ox,$oy,$ow,$oh,[uint32]0x4014)
  Start-Sleep -Milliseconds 500
 }
 $__e07Stage='CAPTURE'
 $rr=[NoxFinalWin32+RECT]::new();if(-not [NoxFinalWin32]::GetWindowRect($handle,[ref]$rr)){throw 'RECT'};$w=$rr.Right-$rr.Left;$h=$rr.Bottom-$rr.Top
 $__e07Stage='CAPTURE'
 $null=[NoxFinalWin32]::ShowWindowAsync($handle,9)
 $null=[NoxFinalWin32]::SetForegroundWindow($handle)
 Start-Sleep -Milliseconds 200
 if([NoxFinalWin32]::GetForegroundWindow() -ne $handle){throw 'PRINT'}
 $bmp=[System.Drawing.Bitmap]::new([int]$w,[int]$h)
 try{
  $g=[System.Drawing.Graphics]::FromImage($bmp)
  try{$g.CopyFromScreen($rr.Left,$rr.Top,0,0,$bmp.Size,
    [System.Drawing.CopyPixelOperation]::SourceCopy)}
  finally{$g.Dispose()}
  $bmp.Save('__PNG__',[System.Drawing.Imaging.ImageFormat]::Png)
 }finally{$bmp.Dispose()}
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
    # Substitute the allowlisted action directly into the encoded UIA script.
    # The old CLICK placeholder produced InvokePrimary '' and could never invoke
    # the original installed control, even when that control was working.
    script=_uia_script(hwnd,action)
    result=_run_ps(script,timeout=35,phase=action)
    e07.require(result.get("invoked") is True and result.get("sameHwndAlive") is True,
                "E07_FINAL_"+action+"_UIA_HOLD")
    return result


def _physical_adaptive_sized(sizes: object) -> bool:
    """Fail closed when Windows clamps a requested D02 resize.

    Five non-overlapping UIA buttons alone cannot certify the 800x600 layout
    if WPF min-size constraints kept the HWND at a larger physical size.
    Actual dimensions come from GetWindowRect after MoveWindow on that HWND.
    """
    expected = ((1044, 788), (800, 600))
    return type(sizes) is list and len(sizes) == len(expected) and all(
        type(item) is dict
        and item.get("requested") == list(target)
        and item.get("actual") == list(target)
        and type(item.get("visiblePrimary")) is int
        and item["visiblePrimary"] == 5
        and item.get("noOverlap") is True
        for item, target in zip(sizes, expected)
    )


def _physical_webview2_motion_verified(observation: object) -> bool:
    """Require the installed WebView2 CDP's reduced-media/CSS/WAAPI evidence.

    WinRT AnimationsEnabled is an independent diagnostic and may differ from
    this specific WebView2 profile. Never infer a physical PASS from OS state.
    """
    return (type(observation) is dict and
            observation.get("status") == "PASS" and
            observation.get("scope") == "INSTALLED_WEBVIEW2_MEDIA_CSS_WAAPI_NOT_OS_SETTING_ALONE" and
            observation.get("media_reduced") is True and
            type(observation.get("visible_nodes")) is int and
            5 <= observation["visible_nodes"] <= 4096 and
            type(observation.get("d02_visible_nodes")) is int and
            5 <= observation["d02_visible_nodes"] <= 4096 and
            type(observation.get("d02_scope_count")) is int and
            observation["d02_scope_count"] == 1 and
            all(type(observation.get(k)) is int and observation[k] == 0
                for k in ("css_animated", "css_transitions", "waapi_running")))


def probe_windows_animation_setting() -> dict:
    """Collect OS animation preference; it is not proof that WebView2 obeys it.

    Read-only physical signal on the same hosted Windows VM. Never change a
    user's accessibility setting and never promote this signal to visual PASS.
    """
    script = r"""
$ErrorActionPreference='Stop'
try {
  $ui=[Windows.UI.ViewManagement.UISettings,Windows.UI.ViewManagement,ContentType=WindowsRuntime]::new()
  $enabled=[bool]$ui.AnimationsEnabled
  [pscustomobject]@{os_ui_animations_enabled=$enabled;source='WinRT.UISettings.AnimationsEnabled';webview2_media_query='NOT_TESTED'} | ConvertTo-Json -Compress
} catch {
  [pscustomobject]@{os_ui_animations_enabled=$null;source='WinRT.UISettings.UNAVAILABLE';webview2_media_query='NOT_TESTED'} | ConvertTo-Json -Compress
}
"""
    try:
        result = _run_ps(script, timeout=15, phase="VISUAL")
    except e07.Hold as exc:
        return {"os_ui_animations_enabled":None,
                "source":"WINRT_QUERY_HOLD",
                "webview2_media_query":"NOT_TESTED",
                "diagnostic_hold":str(exc)}
    if type(result.get("os_ui_animations_enabled")) not in (bool,type(None)):
        return {"os_ui_animations_enabled":None,
                "source":"WINRT_INVALID_VALUE",
                "webview2_media_query":"NOT_TESTED"}
    return result


def _newest(paths: set[Path], folder: Path, pattern: str) -> Path|None:
    now=set(folder.glob(pattern)) if folder.is_dir() else set()
    fresh=[p for p in now-paths if e07.clean_file(p)]
    return max(fresh,key=lambda p:p.stat().st_mtime_ns) if fresh else None




def prepare_final_visual_directory(out_dir: Path, *, new_observation: bool) -> None:
    """Create evidence once for fresh WPF HOME; reuse only on same-run continuation.

    Never follow a preexisting file, junction, symlink or prior run's directory
    when writing screenshots. The pre-navigation/function pass shares exactly
    one admitted root, with the PNG digest checked separately.
    """
    e07.require(isinstance(out_dir, Path) and e07.clean_dir(out_dir.parent),
                "E07_FINAL_EVIDENCE_PARENT_HOLD")
    if new_observation:
        e07.require(not os.path.lexists(out_dir),
                    "E07_FINAL_EVIDENCE_COLLISION_HOLD")
        try:
            out_dir.mkdir()
        except OSError:
            raise e07.Hold("E07_FINAL_EVIDENCE_CREATE_HOLD") from None
    e07.require(e07.clean_dir(out_dir) and
                out_dir.resolve().parent == out_dir.parent.resolve(),
                "E07_FINAL_EVIDENCE_DIR_REPARSE_HOLD")


def _capture_png_dimensions(path: Path) -> list[int] | None:
    """Bind the original HWND PNG to COMPLETE, bounded real PNG pixel bytes.

    PNG CRC/IHDR/IEND alone cannot prove that its IDAT is a valid compressed
    image: a CRC-correct attacker-chosen stream used to pass the source probe.
    Decode only bounded incremental DEFLATE, verify exact expected scanline
    byte count including Adam7, and refuse trailing/reordered IDAT data.
    This remains a screenshot-identity check, NEVER independent visual PASS.
    """
    if not e07.clean_file(path):
        return None
    try:
        size=path.stat().st_size
        if not 57<=size<=40_000_000:
            return None
        with path.open("rb") as source:
            if source.read(8)!=b"\x89PNG\r\n\x1a\n":
                return None
            dimensions=None
            inflater=zlib.decompressobj()
            inflated=0
            expected=None
            seen_idat=False
            ended_idat=False
            for index in range(4096):
                header=source.read(8)
                if len(header)!=8:
                    return None
                length=int.from_bytes(header[:4],"big")
                kind=header[4:]
                if not all(65<=value<=90 or 97<=value<=122 for value in kind):
                    return None
                if length>size-source.tell()-4:
                    return None
                crc=zlib.crc32(kind)
                if index==0:
                    if kind!=b"IHDR" or length!=13:
                        return None
                    ihdr=source.read(13)
                    crc=zlib.crc32(ihdr,crc)
                    width=int.from_bytes(ihdr[:4],"big")
                    height=int.from_bytes(ihdr[4:8],"big")
                    depth, color, compression, filtering, interlace=ihdr[8:]
                    depths={0:(1,2,4,8,16),2:(8,16),3:(1,2,4,8),
                            4:(8,16),6:(8,16)}
                    channels={0:1,2:3,3:1,4:2,6:4}
                    if not (320<=width<=8192 and 200<=height<=8192 and
                            depth in depths.get(color,()) and
                            compression==0 and filtering==0 and
                            interlace in (0,1)):
                        return None
                    dimensions=[width,height]
                    passes=((0,0,1,1),) if interlace==0 else (
                        (0,0,8,8),(4,0,8,8),(0,4,4,8),(2,0,4,4),
                        (0,2,2,4),(1,0,2,2),(0,1,1,2))
                    expected=0
                    for x,y,dx,dy in passes:
                        if x>=width or y>=height:
                            continue
                        cols=(width-x+dx-1)//dx
                        rows=(height-y+dy-1)//dy
                        expected+=rows*(1+(cols*channels[color]*depth+7)//8)
                else:
                    if kind==b"IHDR":
                        return None
                    if kind==b"IDAT":
                        if ended_idat:
                            return None
                        if length:
                            seen_idat=True
                    elif seen_idat:
                        ended_idat=True
                    if kind==b"IEND" and (length!=0 or not seen_idat):
                        return None
                    remaining=length
                    while remaining:
                        block=source.read(min(65536,remaining))
                        if not block:
                            return None
                        crc=zlib.crc32(block,crc)
                        remaining-=len(block)
                        if kind==b"IDAT":
                            pending=block
                            while pending:
                                decoded=inflater.decompress(pending,65536)
                                inflated+=len(decoded)
                                if inflated>expected or inflater.unused_data:
                                    return None
                                pending=inflater.unconsumed_tail
                    if kind==b"IEND" and not (
                        inflater.eof and not inflater.unused_data and
                        inflated==expected):
                        return None
                checksum=source.read(4)
                if len(checksum)!=4 or (crc&0xffffffff)!=int.from_bytes(checksum,"big"):
                    return None
                if kind==b"IEND":
                    return dimensions if source.read(1)==b"" else None
        return None
    except (OSError,ValueError,OverflowError,zlib.error):
        return None


def _capture_matches_png(path: Path, expected: object) -> bool:
    return (type(expected) is list and len(expected)==2
            and all(type(dim) is int for dim in expected)
            and _capture_png_dimensions(path)==expected)


def verify_pre_nav_visual_capture(out_dir: Path, observation: dict) -> None:
    """Bind a pre-navigation physical PASS to its actual same-run WPF PNG.

    A HOLD observation remains diagnostic and must not suppress subsequent
    real function probes. Never promote a missing/replaced image to PASS.
    """
    if observation.get("physical_capture") != "PASS":
        return
    expected = observation.get("screenshot_sha256")
    image = out_dir / "D02_FINAL_SAME_SETUP.png"
    e07.require(type(expected) is str and re.fullmatch(r"[0-9a-f]{64}", expected)
                and e07.clean_dir(out_dir) and e07.clean_file(image)
                and _capture_matches_png(image, observation.get("capture_dimensions")),
                "E07_PRENAV_VISUAL_CAPTURE_IDENTITY_HOLD")
    try:
        size = image.stat().st_size
        actual = e07.sha256(image) if 20_000 <= size <= 40_000_000 else None
    except OSError:
        raise e07.Hold("E07_PRENAV_VISUAL_CAPTURE_IDENTITY_HOLD") from None
    e07.require(actual == expected, "E07_PRENAV_VISUAL_CAPTURE_IDENTITY_HOLD")


def run(hwnd: int, install: Path, local: Path, *, source_sha: str, setup_sha: str,
        out_dir: Path, visual_only: bool=False,
        precomputed_visual: dict|None=None) -> tuple[dict,dict]:
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
    prepare_final_visual_directory(out_dir, new_observation=precomputed_visual is None)

    if precomputed_visual is None:
        png=out_dir/"D02_FINAL_SAME_SETUP.png"
        # Visual WPF UIA may fail independently of the real function handlers.
        # Record that physical HOLD and still collect same-Setup native actions.
        visual_raw={}
        visual_first_hold=None
        try:
            visual_raw=_run_ps(_uia_script(hwnd,"VISUAL",png=png),
                               timeout=60,phase="VISUAL")
        except e07.Hold as exc:
            visual_first_hold=str(exc)
        # A failing UIA probe may still leave a real photo unavailable. Obtain a
        # strictly diagnostic screenshot from the SAME original WPF HWND, while
        # keeping visual_first_hold and every release gate unchanged.
        diagnostic_photo={"scope":"NOT_RUN_ORIGINALLY"}
        if visual_first_hold is not None and not e07.clean_file(png):
            try:
                from probe_v6_visual_physical_u01 import capture_window
                photo=capture_window(hwnd,png)
                diagnostic_photo={
                    "scope":"SAME_WPF_PHYSICAL_CAPTURE_NOT_VISUAL_ACCEPTANCE",
                    "sha256":photo["sha256"],
                    "width":photo["width"],"height":photo["height"]}
            except (e07.Hold,OSError,ValueError,KeyError):
                diagnostic_photo={"scope":"SAME_WPF_PHYSICAL_CAPTURE_HOLD"}
        actual_png=(e07.clean_file(png) and
                    20_000<=png.stat().st_size<=40_000_000 and
                    _capture_matches_png(png, visual_raw.get("capture")))
        resize_diagnostics={}
        for target_width in (800,1044):
            diagnostic_path=out_dir / f"D02_ADAPTIVE_{target_width}.png"
            if (e07.clean_file(diagnostic_path) and
                    20_000 <= diagnostic_path.stat().st_size <= 40_000_000):
                resize_diagnostics[str(target_width)]=e07.sha256(diagnostic_path)
        sizes=visual_raw.get("sizes")
        actual_layout=_physical_adaptive_sized(sizes)
        screenshot_sha=e07.sha256(png) if actual_png else None
        if visual_first_hold is None and not actual_png:
            visual_first_hold="E07_FINAL_VISUAL_PNG_HOLD"
        if visual_first_hold is None and not actual_layout:
            visual_first_hold="E07_FINAL_ADAPTIVE_LAYOUT_HOLD"
        # The original installed D02 has five graphical quality planets, not
        # the obsolete three-state FX BALANCED/MAX/ECO button. Reuse the existing
        # physical original-HWND UIA probe (Invoke + actual pressed state).
        from probe_91a6_real_visual_u17 import probe_d02_quality_modes
        # A failing graphical-mode UIA probe MUST NOT prevent collection of the
        # other real function witnesses on this one physical installed HWND.
        # Keep exact failure evidence; never promote a missing FX response.
        try:
            fx=probe_d02_quality_modes(hwnd)
            e07.require(fx.get("fx_control")=="PASS" and
                        fx.get("actual_invocations")==5 and
                        fx.get("reduced_motion")=="NOT_TESTED" and
                        fx.get("independent_visual_review")=="NOT_RUN",
                        "E07_FINAL_D02_FIVE_GRAPHICS_MODE_HOLD")
        except e07.Hold as exc:
            fx={"fx_control":"HOLD","first_unmet_gate":str(exc)}
        os_animation=probe_windows_animation_setting()
        # Physical OS animation setting alone is NOT WebView2 media evidence.
        # Read the actual installed page's matchMedia / computed CSS / WAAPI
        # via read-only loopback CDP on ephemeral GitHub Windows only.
        webview_motion={"status":"HOLD","reason":"E07_WEBVIEW2_MEDIA_NOT_TESTED_HOLD"}
        # OS animation preference is recorded, not used as a CDP permission or
        # release gate. Read the installed WebView2's own reduced-media state
        # on the same GitHub-hosted Windows runner, even if OS animations are on.
        # A media/CSS/WAAPI mismatch continues to fail closed.
        try:
            from probe_webview_motion import probe as probe_webview_motion
            webview_motion=probe_webview_motion()
        except e07.Hold as exc:
            webview_motion={"status":"HOLD","reason":str(exc)}
        motion_verified=_physical_webview2_motion_verified(webview_motion)
        visual={"schema":e07.FINAL_VISUAL_SCHEMA,"source_sha":source_sha,
                "setup_sha256":setup_sha,"release_accepted":False,
                "physical_capture":"PASS" if actual_png and visual_first_hold is None else "HOLD",
                "d02_visual":"PASS" if actual_png and actual_layout and
                             visual_first_hold is None and fx["fx_control"]=="PASS" else "HOLD",
                "adaptive_layout":"PASS" if actual_layout else "HOLD",
                # Physical D02 graphics are not OS Reduced Motion or design review.
                "reduced_motion":"HOLD","screenshot_sha256":screenshot_sha,
                "capture_dimensions":visual_raw.get("capture") if actual_png else None,
                "physical_sizes":sizes or [],"fx_cycle":fx,
                "diagnostic_photo":diagnostic_photo,
                "adaptive_failure_diagnostics":resize_diagnostics,
                "visual_first_unmet_gate":visual_first_hold or
                     (fx.get("first_unmet_gate") if fx["fx_control"]!="PASS"
                      else "E07_INDEPENDENT_VISUAL_REVIEW_NOT_RUN"),
                "reduced_motion_evidence":(
                    "INSTALLED_WEBVIEW2_MEDIA_CSS_WAAPI_PHYSICAL"
                    if motion_verified else
                    "OS_SETTING_OBSERVED_WEBVIEW2_MEDIA_QUERY_NOT_PHYSICALLY_VERIFIED"),
                "os_animation_observation":os_animation,
                "webview2_motion_evidence":webview_motion}
        if motion_verified:
            visual["reduced_motion"]="PASS"

    else:
        # This receipt was obtained on the original WPF HOME before any
        # CHAT/SETTINGS navigation or native consent dialog altered the screen.
        # Identity and non-release state are mandatory; never invent PASS.
        e07.require(type(precomputed_visual) is dict and
                    precomputed_visual.get("schema")==e07.FINAL_VISUAL_SCHEMA and
                    precomputed_visual.get("source_sha")==source_sha and
                    precomputed_visual.get("setup_sha256")==setup_sha and
                    precomputed_visual.get("release_accepted") is False,
                    "E07_PRENAV_VISUAL_IDENTITY_HOLD")
        # The earlier SAME-HWND physical UIA observation is not independently
        # admissible after navigation if its frozen screenshot is gone or changed.
        # A genuine visual HOLD still allows collecting other real actions.
        verify_pre_nav_visual_capture(out_dir, precomputed_visual)
        visual=precomputed_visual
    if visual_only:
        e07.require(precomputed_visual is None,"E07_PRENAV_VISUAL_MODE_HOLD")
        return visual, {}

    # Navigation to the original Model Center may display a real WPF
    # models.catalog consent dialog. Close only that exact OWNER dialog with
    # its NEGATIVE button before independent function attempts. This does
    # not authorize any privileged operation or modify native ACL.
    try:
        navigation_consent = dismiss_readonly_models_catalog_consent(hwnd)
    except (e07.Hold, OSError, ValueError, subprocess.TimeoutExpired) as exc:
        navigation_consent = {"status":"HOLD",
                              "error":str(exc) if isinstance(exc,e07.Hold)
                              else "E07_NAV_DIALOG_"+type(exc).__name__.upper()+"_HOLD",
                              "permissionGranted":False}

    actions={}
    def observed(action: str, detail: dict) -> None:
        # An installed command, ModelCenter window, GPU preflight or settings
        # heading is not proof of a downloaded model, completed training,
        # authorized owner operation or persisted configuration change.
        actions[action]=nonrelease_action_observation(action,detail)

    def attempt(action: str, callback) -> None:
        # Collect every safe physical original-owner observation from the SAME
        # installed WPF. A failure must not manufacture PASS or hide evidence
        # for other actions; all privileged permission checks remain outside
        # this diagnostic wrapper and remain NOT_TESTED until truly verified.
        try:
            callback()
        except (e07.Hold, OSError, ValueError, subprocess.TimeoutExpired) as exc:
            reason=(str(exc) if isinstance(exc,e07.Hold)
                    else "E07_FINAL_"+action+"_"+type(exc).__name__.upper()+"_HOLD")
            actions[action]={"function_verified":"NOT_TESTED",
                             "permissions_verified":"NOT_TESTED",
                             "result":"HOLD","error_code":reason[:140],
                             "scope":"SAME_SETUP_PHYSICAL_ACTION_FAILED"}
        except Exception as exc:
            actions[action]={"function_verified":"NOT_TESTED",
                             "permissions_verified":"NOT_TESTED",
                             "result":"HOLD",
                             "error_code":"E07_FINAL_"+action+"_UNEXPECTED_"+
                                          type(exc).__name__.upper()+"_HOLD",
                             "scope":"SAME_SETUP_PHYSICAL_ACTION_FAILED"}

    def install_check():
        app=local/"NOX_HELION_Integrator"/"app"
        server=app/"server.py"
        # The approved original NoxActions.ps1: -Action install emits a real
        # ACTION_START / ACTION_END exit=N sequence in the owner WPF shell.log.
        # A stale file or untrusted stdout must never satisfy a new operation.
        before_server_sha=e07.sha256(server) if e07.clean_file(server) else None
        log=local/"NOX_HELION"/"P01"/"logs"/"shell.log"
        before_info=log.stat() if e07.clean_file(log) else None
        before_log_size=before_info.st_size if before_info else 0
        invoke_primary(hwnd,"INSTALL")
        # Current original EXPRESS source delegates its one trusted INSTALL
        # user event to R11 #pc-install. Verify unique same-HWND UIA control
        # read-only, not a second native installation. Only fresh real WPF
        # ACTION_START/END plus original installed result can prove success.
        # Never approve WPF privileged consent on behalf of a user.
        original_control=None
        for _ in range(20):
            try:
                original_control=_run_ps(_uia_script(hwnd,"INSTALL_CONTROL"),
                                         timeout=15,phase="INSTALL_CONTROL")
                break
            except e07.Hold as exc:
                if str(exc)!="E07_FINAL_UIA_INSTALL_CONTROL_ORIGINAL_CONTROL_NOT_UNIQUE_HOLD":
                    raise
                time.sleep(.3)
        e07.require(type(original_control) is dict and
                    original_control.get("originalControlPresent") is True and
                    original_control.get("invokePatternAvailable") is True and
                    original_control.get("sameHwndAlive") is True,
                    "E07_FINAL_INSTALL_REAL_CONTROL_NOT_FOUND_HOLD")
        started_at=time.monotonic()
        deadline=started_at+120
        owner={"started":False,"owner_exit_code":None,"owner_exception":False}
        while time.monotonic()<deadline:
            if e07.clean_file(log):
                now=log.stat()
                if before_info is not None:
                    e07.require((now.st_dev,now.st_ino)==(before_info.st_dev,before_info.st_ino),
                                "E07_FINAL_INSTALL_LOG_REPLACED_HOLD")
                e07.require(before_log_size<=now.st_size<=before_log_size+200000,
                            "E07_FINAL_INSTALL_LOG_REWOUND_OR_GROWN_HOLD")
                with log.open("rb") as handle:
                    handle.seek(before_log_size)
                    owner=classify_fresh_original_install_log(handle.read(200000))
            if owner["owner_exception"]:
                raise e07.Hold("E07_FINAL_INSTALL_OWNER_EXCEPTION_HOLD")
            if owner["owner_exit_code"] is not None:
                if owner["owner_exit_code"]!=0:
                    raise e07.Hold("E07_FINAL_INSTALL_OWNER_NONZERO_EXIT_HOLD")
                break
            if not owner["started"] and time.monotonic()-started_at>=12:
                raise e07.Hold("E07_FINAL_INSTALL_OWNER_ACTION_NOT_STARTED_HOLD")
            time.sleep(.4)
        e07.require(owner["started"] and owner["owner_exit_code"]==0,
                    "E07_FINAL_INSTALL_OWNER_TIMEOUT_HOLD")
        e07.require(e07.clean_file(server),"E07_FINAL_INSTALL_RESULT_HOLD")
        observed("INSTALL",{"server_sha256":e07.sha256(server),
                            "preexisting_server_sha256":before_server_sha,
                            "fresh_original_owner_action":True,
                            "action_exit":0,
                            "scope":"ORIGINAL_PC_INSTALL_UI_TO_NOX_ACTIONS"})

    def models_check():
        invoke_primary(hwnd,"MODELS")
        # Only the exact read-only models.catalog WPF consent can be approved
        # by this ephemeral CI test owner, never model pull/training permissions.
        catalog_consent=qa_approve_readonly_catalog_consent(hwnd)
        model=_run_ps(_uia_script(hwnd,"MODEL_WINDOW"),
                      timeout=35,phase="MODEL_WINDOW")
        e07.require(model.get("modelPageVisible") is True and
                    model.get("modelDocumentCount")==1 and
                    model.get("modelHeadingVisible") is True and
                    model.get("sameOriginalHwndAlive") is True and
                    model.get("originalOwnerProcessIdPositive") is True,
                    "E07_FINAL_MODELS_ORIGINAL_WEBVIEW_PAGE_HOLD")
        observed("MODELS",{"model_center_same_webview_page":"PASS",
                           "document_title":"NOX · MODEL CORE",
                           "catalog_qa_consent":catalog_consent,
                           "model_pull":"NOT_TESTED",
                           "model_download_queue":"NOT_TESTED"})

    def learn_check():
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
                    type(data.get("windows")) is str and
                    type(data.get("dotnet")) is str and
                    type(data.get("webview2")) is str and
                    data.get("releaseGate")=="BLOCKED",
                    "E07_FINAL_LEARN_DIAGNOSTIC_SCHEMA_HOLD")
        observed("LEARN",{"diagnostics_sha256":e07.sha256(diag),
                          "cpu":data["cpu"],
                          "scope":"ORIGINAL_TRAINING_ENVIRONMENT_PREFLIGHT"})

    def settings_check():
        settings=_run_ps(_uia_script(hwnd,"SETTINGS"),
                         timeout=35,phase="SETTINGS")
        e07.require(settings.get("invoked") is True and
                    settings.get("systemHeadingVisible") is True and
                    settings.get("sameHwndAlive") is True,
                    "E07_FINAL_SETTINGS_ROUTE_HOLD")
        observed("SETTINGS",{"system_screen":"PASS","same_original_hwnd":True,
                             "scope":"ORIGINAL_SYSTEM_SETTINGS_SCREEN"})

    for name,callback in (
        ("INSTALL",install_check),("MODELS",models_check),
        ("LEARN",learn_check),("SETTINGS",settings_check)):
        attempt(name,callback)

    functions={"schema":e07.FINAL_FUNCTION_SCHEMA,"source_sha":source_sha,
               "setup_sha256":setup_sha,"release_accepted":False,"actions":actions,
               "navigation_consent_cleanup":navigation_consent}
    return visual,functions
