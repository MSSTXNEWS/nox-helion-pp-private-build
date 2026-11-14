"""NOX R11 block1 — split already downloaded signed Ollama artifact; no execution."""
import hashlib,json,os
from pathlib import Path
root=Path(os.environ["RUNNER_TEMP"])
source=root/"nox-r11-ollama-existing"/"OllamaSetup-v0.40.13-x64.exe"
out=root/"nox-r11-ollama-parts";out.mkdir(parents=True,exist_ok=True)
expected_size=1676266440
expected_sha="9e3c76e54e7184c68e88a2378b909bf59bbe454f83c076cb4f4a717e946ae719"
chunk_size=384*1024*1024
if not source.is_file() or source.is_symlink():raise SystemExit("EXISTING_OLLAMA_BINARY_NOT_FOUND")
whole=hashlib.sha256();total=0;parts=[]
with source.open("rb") as inp:
 for index in range(1,6):
  p=out/f"OllamaSetup-v0.40.13-x64.part{index:02d}"
  count=0;digest=hashlib.sha256()
  with p.open("xb") as f:
   while count<chunk_size:
    buf=inp.read(min(8*1024*1024,chunk_size-count))
    if not buf:break
    f.write(buf);whole.update(buf);digest.update(buf)
    count+=len(buf);total+=len(buf)
  if count==0:p.unlink();break
  parts.append({"name":p.name,"position":index,"bytes":count,"sha256":digest.hexdigest()})
  print("CHUNK",index,count,digest.hexdigest(),flush=True)
 if inp.read(1):raise SystemExit("MORE_THAN_FIVE_CHUNKS")
if total!=expected_size or whole.hexdigest()!=expected_sha or len(parts)!=5:
 raise SystemExit("ORIGINAL_OLLAMA_SHA_REASSEMBLY_HOLD")
manifest={"schema":"NOX-R11-BLOCK1-OLLAMA-CHUNKS-v1","source_run":41324910974,"sha256":expected_sha,"bytes":expected_size,"phase":"DOWNLOAD_TRANSFER_ONLY","installed":False,"merged":False,"parts":parts}
(out/"CHUNKS_MANIFEST.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf8")
print("TRANSFER_COMPLETE",total,whole.hexdigest(),flush=True)
