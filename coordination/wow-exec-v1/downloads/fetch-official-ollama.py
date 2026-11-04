"""NOX R11 - Official Ollama source only, no install, no merge."""
import datetime,hashlib,json,os,pathlib,subprocess,urllib.request,urllib.parse
ROOT=pathlib.Path(os.environ.get("NOX_OLLAMA_BLOCK1_OUT","ollama-block1")).resolve()
ROOT.mkdir(parents=True,exist_ok=True)
URL="https://github.com/ollama/ollama/releases/download/v0.40.13/OllamaSetup.exe"
EXPECTED_BYTES=1676266440
EXPECTED_SHA="9e3c76e54e7184c68e88a2378b909bf59bbe454f83c076cb4f4a717e946ae719"
TARGET=ROOT/"OllamaSetup-v0.40.13-x64.exe"
PART=ROOT/"OllamaSetup.part"
def authorized(u):
 p=urllib.parse.urlsplit(u)
 return p.scheme=="https" and p.hostname in ("github.com","release-assets.githubusercontent.com","objects.githubusercontent.com")
def main():
 rec={"schema":"NOX-R11-BLOCK1-OLLAMA-v1","phase":"DOWNLOAD_ONLY","release":"v0.40.13","url":URL,"expected_bytes":EXPECTED_BYTES,"expected_sha256":EXPECTED_SHA,"status":"DOWNLOAD_HOLD","installed":False,"merged":False,"created_utc":datetime.datetime.now(datetime.timezone.utc).isoformat()}
 try:
  if TARGET.exists():raise ValueError("NO_OVERWRITE")
  if PART.exists():PART.unlink()
  if not authorized(URL):raise ValueError("UNTRUSTED_SOURCE")
  with urllib.request.urlopen(urllib.request.Request(URL,headers={"User-Agent":"NOX-EXPRESS-R11-BLOCK1"}),timeout=150) as response:
   final=response.geturl()
   if not authorized(final):raise ValueError("UNTRUSTED_REDIRECT")
   digest=hashlib.sha256();size=0
   with PART.open("xb") as writer:
    while True:
     chunk=response.read(1024*1024)
     if not chunk:break
     size+=len(chunk)
     if size>EXPECTED_BYTES:raise ValueError("OVERSIZE")
     digest.update(chunk);writer.write(chunk)
    writer.flush();os.fsync(writer.fileno())
  rec.update(actual_bytes=size,actual_sha256=digest.hexdigest(),redirect_host=urllib.parse.urlsplit(final).hostname)
  if size!=EXPECTED_BYTES or digest.hexdigest()!=EXPECTED_SHA:raise ValueError("OFFICIAL_SHA_OR_LENGTH_MISMATCH")
  with PART.open("rb") as reader:
   if reader.read(2)!=b"MZ":raise ValueError("NOT_PE")
  PART.replace(TARGET)
  rec["status"]="DOWNLOADED_SHA256_VERIFIED"
  ps="""$ErrorActionPreference='Stop'
$manifest=Join-Path $PSHOME 'Modules\\Microsoft.PowerShell.Security\\Microsoft.PowerShell.Security.psd1'
Import-Module -Name $manifest -ErrorAction Stop
$s=Get-AuthenticodeSignature -LiteralPath $env:NOX_VERIFY_FILE -ErrorAction Stop
$subject=if($s.SignerCertificate){[string]$s.SignerCertificate.Subject}else{''}
@{status=[string]$s.Status;subject=$subject}|ConvertTo-Json -Compress
"""
  try:
   proc=subprocess.run(["powershell.exe","-NoProfile","-NonInteractive","-Command",ps],env={**os.environ,"NOX_VERIFY_FILE":str(TARGET)},capture_output=True,text=True,timeout=90)
   rec["authenticode"]=json.loads(proc.stdout.strip().splitlines()[-1])
   if rec["authenticode"]["status"]=="Valid":rec["status"]="DOWNLOADED_SHA256_AUTHENTICODE_VALID"
  except Exception as ex:rec["signature_warning"]=str(ex)[:300]
 except Exception as ex:
  rec["error"]=str(ex)[:700]
  if PART.exists():PART.unlink()
 finally:
  (ROOT/"ollama-receipt.json").write_text(json.dumps(rec,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
  print("OLLAMA_BLOCK1",json.dumps(rec,ensure_ascii=False),flush=True)
if __name__=="__main__":main()
