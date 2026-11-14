"""NOX R11/MENU10 block 1 ONLY: download, verify, receipt. NEVER INSTALL."""
import datetime,hashlib,json,os,pathlib,subprocess,urllib.request,urllib.parse
ROOT=pathlib.Path(os.environ.get("NOX_BLOCK1_OUT","block1-out"));ROOT.mkdir(parents=True,exist_ok=True)
ITEMS=[
("webview2_x64","https://go.microsoft.com/fwlink/?linkid=2124701","MicrosoftEdgeWebView2RuntimeInstallerX64.exe","exe","microsoft",350000000),
("windowsappsdk","https://api.nuget.org/v3-flatcontainer/microsoft.windowsappsdk/1.8.260921001/microsoft.windowsappsdk.1.8.260921001.nupkg","microsoft.windowsappsdk.1.8.260921001.nupkg","zip","nuget",150000000),
("hardwaremon","https://api.nuget.org/v3-flatcontainer/librehardwaremonitorlib/0.9.6/librehardwaremonitorlib.0.9.6.nupkg","librehardwaremonitorlib.0.9.6.nupkg","zip","nuget",40000000),
("ollama_win","https://ollama.com/download/OllamaSetup.exe","OllamaSetup.exe","exe","ollama",900000000),
("nsis","https://sourceforge.net/projects/nsis/files/NSIS%203/3.13/nsis-3.13-setup.exe/download","nsis-3.13-setup.exe","exe","sourceforge",45000000),
("dotnet_install","https://dot.net/v1/dotnet-install.ps1","dotnet-install.ps1","text","dotnet",500000),
]
SVG={"back":"Arrow%20Left/SVG/ic_fluent_arrow_left_24_regular.svg","search":"Search/SVG/ic_fluent_search_24_regular.svg","settings":"Settings/SVG/ic_fluent_settings_24_regular.svg","close":"Dismiss/SVG/ic_fluent_dismiss_24_regular.svg","notifications":"Alert/SVG/ic_fluent_alert_24_regular.svg","success":"Checkmark%20Circle/SVG/ic_fluent_checkmark_circle_24_regular.svg"}
def allowed(u,kind):
 host=(urllib.parse.urlsplit(u).hostname or "").lower()
 if kind=="microsoft":return host=="microsoft.com" or host.endswith(".microsoft.com")
 if kind=="nuget":return host=="nuget.org" or host.endswith(".nuget.org")
 if kind=="ollama":return host in ("ollama.com","github.com","release-assets.githubusercontent.com","objects.githubusercontent.com")
 if kind=="sourceforge":return host.endswith(".sourceforge.net") or host=="sourceforge.net"
 if kind=="dotnet":return host in ("dot.net","aka.ms","raw.githubusercontent.com") or host.endswith(".microsoft.com")
 return host=="raw.githubusercontent.com"
def pull(item):
 name,url,filename,kind,origin,limit=item
 folder=ROOT/("fluent" if origin=="githubraw" else "official");folder.mkdir(exist_ok=True)
 dest=folder/filename;temp=dest.with_name(dest.name+".part")
 r={"name":name,"url":url,"file":str(dest.relative_to(ROOT)).replace("\\","/"),"status":"DOWNLOAD_HOLD","installed":False}
 try:
  if temp.exists():temp.unlink()
  if not allowed(url,origin):raise ValueError("INVALID_SOURCE")
  req=urllib.request.Request(url,headers={"User-Agent":"NOX-EXPRESS-R11-BLOCK1/1"})
  with urllib.request.urlopen(req,timeout=180) as response:
   redirect=response.geturl()
   if urllib.parse.urlsplit(redirect).scheme!="https" or not allowed(redirect,origin):raise ValueError("INVALID_REDIRECT:"+redirect)
   size=0
   with temp.open("xb") as w:
    while True:
     data=response.read(131072)
     if not data:break
     size+=len(data)
     if size>limit:raise ValueError("OVERSIZE")
     w.write(data)
   if size<100:raise ValueError("TOO_SMALL")
  with temp.open("rb") as f:magic=f.read(4)
  if kind=="exe" and not magic.startswith(b"MZ"):raise ValueError("INVALID_PE")
  if kind=="zip" and not magic.startswith(b"PK"):raise ValueError("INVALID_NUGET")
  if kind=="svg" and not temp.read_text("utf-8").strip().startswith("<svg"):raise ValueError("INVALID_SVG")
  if kind=="text" and b"<html" in temp.read_bytes()[:200].lower():raise ValueError("INVALID_SCRIPT")
  temp.replace(dest)
  h=hashlib.sha256()
  with dest.open("rb") as f:
   for chunk in iter(lambda:f.read(1024*1024),b""):h.update(chunk)
  r.update(status="DOWNLOADED",sha256=h.hexdigest(),bytes=size,redirect=redirect)
  if kind=="exe":
   ps="$s=Get-AuthenticodeSignature -LiteralPath $env:NOX_BLOCK1_SIGNED_FILE; $subject=$(if($s.SignerCertificate){$s.SignerCertificate.Subject}else{''}); @{status=[string]$s.Status;subject=[string]$subject}|ConvertTo-Json -Compress"
   result=subprocess.run(["powershell.exe","-NoProfile","-NonInteractive","-Command",ps],env={**os.environ,"NOX_BLOCK1_SIGNED_FILE":str(dest)},capture_output=True,text=True,timeout=65)
   try:r["signature"]=json.loads(result.stdout.strip().splitlines()[-1])
   except:r["signature"]={"status":"UNKNOWN","diagnostic":result.stderr[-300:]}
   if origin=="microsoft" and not (r["signature"].get("status")=="Valid" and "Microsoft" in r["signature"].get("subject","")):r["status"]="SIGNATURE_HOLD"
 except Exception as e:
  r["error"]=str(e)[:600]
  if temp.exists():temp.unlink()
 print(name,r["status"],flush=True)
 return r
records=[pull(i) for i in ITEMS]
for name,path in SVG.items():
 records.append(pull(("fluent-"+name,"https://raw.githubusercontent.com/microsoft/fluentui-system-icons/main/assets/"+path,name+".svg","svg","githubraw",50000)))
records.append(pull(("fluent-license","https://raw.githubusercontent.com/microsoft/fluentui-system-icons/main/LICENSE","LICENSE.microsoft-fluentui.txt","text","githubraw",100000)))
manifest={"schema":"NOX-WOW-R11-BLOCK1","stage":"DOWNLOAD_ONLY","installation":"NOT_EXECUTED","merge":"NOT_EXECUTED","timestamp_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),"entries":records}
(ROOT/"download-receipt.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
