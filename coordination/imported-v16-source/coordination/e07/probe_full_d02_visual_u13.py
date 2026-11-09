"""Capture a real installed FULL D02 WPF window on independent Windows.
Screenshot existence is only evidence; visual approval and E07 remain HOLD.
"""
from __future__ import annotations
import argparse,base64,hashlib,json,os,subprocess,sys,time
from pathlib import Path
from probe_full_d02_722399_u13 import candidate,SOURCE,SETUP_SHA,BUILDID
import independent_setup_e07 as e07

PS= r"""
$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Drawing
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class Capture {
 [StructLayout(LayoutKind.Sequential)]public struct Rect{public int Left,Top,Right,Bottom;}
 [DllImport("user32.dll")]public static extern bool GetWindowRect(IntPtr h,out Rect r);
 [DllImport("user32.dll")]public static extern bool PrintWindow(IntPtr h,IntPtr dc,uint flags);
}
'@
$rect=New-Object Capture+Rect
$handle=[IntPtr]__HWND__
if(-not [Capture]::GetWindowRect($handle,[ref]$rect)){throw 'NO_WINDOW_RECT'}
$w=$rect.Right-$rect.Left;$h=$rect.Bottom-$rect.Top
if($w -lt 500 -or $h -lt 300 -or $w -gt 8192 -or $h -gt 8192){throw 'BOUNDS_HOLD'}
$b=New-Object System.Drawing.Bitmap($w,$h)
$g=[System.Drawing.Graphics]::FromImage($b)
$dc=$g.GetHdc()
try{$ok=[Capture]::PrintWindow($handle,$dc,2)}
finally{$g.ReleaseHdc($dc);$g.Dispose()}
if(-not $ok){$b.Dispose();throw 'PRINTWINDOW_HOLD'}
$b.Save('__DEST__',[System.Drawing.Imaging.ImageFormat]::Png)
$unique=New-Object 'System.Collections.Generic.HashSet[string]'
for($y=0;$y -lt $h;$y+=[Math]::Max(10,[int]($h/25))){
 for($x=0;$x -lt $w;$x+=[Math]::Max(10,[int]($w/25))){
  $c=$b.GetPixel($x,$y)
  [void]$unique.Add("$($c.R):$($c.G):$($c.B)")
 }
}
$b.Dispose()
[pscustomobject]@{width=$w;height=$h;colors=$unique.Count;captured=$true}|ConvertTo-Json -Compress
"""
def main():
 p=argparse.ArgumentParser()
 p.add_argument("--artifact-dir",type=Path,required=True)
 p.add_argument("--out-dir",type=Path,required=True)
 a=p.parse_args()
 a.out_dir.mkdir(parents=True,exist_ok=True)
 receipt={"schema":"NOX-INSTALLED-FULL-D02-VISUAL-V1","source_sha":SOURCE,
          "setup_sha256":SETUP_SHA,"build_id":BUILDID,
          "physical_capture":"HOLD","visual_e07":"HOLD","release_accepted":False}
 shell=None
 try:
  e07.require(sys.platform=="win32" and os.environ.get("GITHUB_ACTIONS")=="true"
    and os.environ.get("RUNNER_OS")=="Windows"
    and os.environ.get("RUNNER_ENVIRONMENT")=="github-hosted"
    and os.environ.get("GITHUB_REPOSITORY")=="MSSTXNEWS/nox-helion-pp-private-build",
    "VISUAL_WINDOWS_HOST_HOLD")
  setup=candidate(a.artifact_dir)
  with setup.open("rb") as f:
   e07.require(hashlib.file_digest(f,"sha256").hexdigest()==SETUP_SHA,"VISUAL_SETUP_SHA_HOLD")
  install=subprocess.run([str(setup),"/S"],capture_output=True,timeout=180,check=False)
  e07.require(install.returncode==0,"VISUAL_INSTALL_HOLD")
  local=Path(os.environ["LOCALAPPDATA"])
  root=local/"Programs"/"NOX HELION"
  _,owned=e07.manifest_owner(root)
  e07.require(len(owned)==1004,"VISUAL_1004_MANIFEST_HOLD")
  exe=root/"NOX.P01.Shell.exe"
  e07.require(exe in owned and e07.clean_file(exe),"VISUAL_SHELL_NOT_VERIFIED")
  log=local/"NOX_HELION"/"P01"/"logs"/"shell.log"
  start=log.stat().st_size if e07.clean_file(log) else 0
  shell=subprocess.Popen([str(exe)],cwd=str(exe.parent),
        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  seen=None;stable=None;deadline=time.monotonic()+80
  while time.monotonic()<deadline and shell.poll() is None:
   if e07.clean_file(log):
    with log.open("rb") as f:
     f.seek(start);data=f.read(65536).decode("utf-8",errors="replace")
    flags=e07.wpf_marker_flags(data)
    e07.require(not flags.get("NAV_FAIL") and not flags.get("INIT_ERROR"),"VISUAL_NAV_FATAL")
    if flags.get("NAV_OK") and flags.get("P02_ORIGINAL_NATIVE_PIPE_HANDSHAKE_OK"):
     hwnd=e07.original_wpf_hwnd(shell.pid)
     if hwnd is not None:
      if seen!=hwnd:seen=hwnd;stable=time.monotonic()
      if time.monotonic()-stable>=5:break
   time.sleep(.3)
  e07.require(seen is not None and stable is not None and
        time.monotonic()-stable>=5 and shell.poll() is None,"VISUAL_STABLE_HWND_HOLD")
  png=a.out_dir/"D02_REAL_INSTALLED_WINDOW.png"
  ps=PS.replace("__HWND__",str(seen)).replace("__DEST__",str(png).replace("'","''"))
  cmd=base64.b64encode(ps.encode("utf-16le")).decode("ascii")
  run=subprocess.run(["powershell.exe","-NoProfile","-NonInteractive","-EncodedCommand",cmd],
       capture_output=True,text=True,timeout=50,encoding="utf-8",errors="replace")
  e07.require(run.returncode==0 and 0<len(run.stdout)<4096,"VISUAL_CAPTURE_PROCESS_HOLD")
  image=json.loads(run.stdout.strip())
  e07.require(image.get("captured") is True and type(image.get("colors")) is int
      and image["colors"]>=12 and png.is_file()
      and 5000<png.stat().st_size<40_000_000,"VISUAL_EMPTY_SCREEN_HOLD")
  with png.open("rb") as f:sha=hashlib.file_digest(f,"sha256").hexdigest()
  receipt.update({"physical_capture":"PASS","screenshot_sha256":sha,
       "screen_dimensions":[image["width"],image["height"]],
       "sampled_unique_colors":image["colors"],
       "first_unmet_gate":"INDEPENDENT_VISUAL_REVIEW_AND_FINAL_E07"})
 except Exception as err:
  receipt["first_unmet_gate"]=str(err)[:140] if isinstance(err,e07.Hold) else (
      "VISUAL_"+type(err).__name__.upper()+"_HOLD")
 finally:
  if shell is not None and shell.poll() is None:
   shell.terminate()
   try:shell.wait(timeout=7)
   except subprocess.TimeoutExpired:shell.kill();shell.wait(timeout=5)
  (a.out_dir/"VISUAL_RECEIPT.json").write_text(json.dumps(receipt,indent=2),encoding="utf-8")
  print("NOX_REAL_D02_VISUAL",receipt["physical_capture"],receipt.get("first_unmet_gate"),flush=True)
 return 0 if receipt["physical_capture"]=="PASS" else 2
if __name__=="__main__":raise SystemExit(main())
