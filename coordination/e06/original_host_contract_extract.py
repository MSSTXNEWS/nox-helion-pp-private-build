"""Read-only original NOX Python host contract recovery from three frozen parts."""
from pathlib import Path
import hashlib,zipfile,io,json
root=Path(".")
expected="ff8e2848c7c7ab776b90cbd8ac28e41e3815e96373c3c5f635d7587284629e9a"
h=hashlib.sha256()
parts=("source_00.part","source_01.part","source_02.part")
buf=io.BytesIO()
for part in parts:
    with (root/part).open("rb") as f:
        while block:=f.read(1024*1024):
            h.update(block);buf.write(block)
if h.hexdigest()!=expected:raise SystemExit("SOURCELOCK_ARCHIVE_HOLD")
targets=("run_helion.py","helion/app.py","helion/desktop_routes.py",
         "helion/e06_route_adapter.py","helion/ai_core_runtime.py",
         "helion/core_chat_bridge.py","helion_voice/service.py",
         "helion_voice/integration.py","helion/security.py",
         "helion/ai_weights/weights/MODEL_FEATURE_CONTRACT.json",
         "build_windows.ps1","C_RELEASE_SPRINT_BUILD.ps1",
         "helion_scoped_capabilities.py")
out=Path("e06-original-host-source");out.mkdir(exist_ok=True)
ledger={}
with zipfile.ZipFile(buf) as archive:
    for name in targets:
        try: item=archive.getinfo(name)
        except KeyError: ledger[name]={"state":"MISSING"};continue
        if item.file_size>1200000:ledger[name]={"state":"OVERSIZED"};continue
        raw=archive.read(item)
        target=out/name
        target.parent.mkdir(exist_ok=True,parents=True)
        target.write_bytes(raw)
        ledger[name]={"state":"RECOVERED","bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest()}
(out/"ORIGINAL_HOST_PINS.json").write_text(json.dumps({"schema":"NOX-E06-ORIGINAL-HOST-PINS-v1","archive_sha256":expected,"files":ledger,"merged":False,"release":False},indent=2))
print("E06_ORIGINAL_READ_ONLY_SOURCE_PINS",len(ledger),sum(x["state"]=="RECOVERED" for x in ledger.values()))
