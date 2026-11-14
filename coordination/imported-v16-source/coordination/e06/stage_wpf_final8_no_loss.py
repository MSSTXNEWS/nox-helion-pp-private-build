"""R51 reusable E06 native C# compiler compatibility; disposable R11 only.
Restores typed events and ModelCenter queue integration, no code deletion.
Does not modify immutable source donor, D02 assets, consent, or original media.
"""
import hashlib
import re
import sys
from pathlib import Path

FILES = (
 "Contracts/EventV3Bridge.cs",
 "Packages/P03/worker-window/ModelDownloaderWindow.xaml.cs",
 "Packages/P03/worker-queue/ModelDownloadQueueStore.cs",
)
REPLACEMENTS = {
 "_queueStore.Items.CollectionChanged += _queueItemsChanged;":
 "((System.Collections.Specialized.INotifyCollectionChanged)_queueStore.Items).CollectionChanged += _queueItemsChanged;",
 "_queueStore.Items.CollectionChanged -= _queueItemsChanged;":
 "((System.Collections.Specialized.INotifyCollectionChanged)_queueStore.Items).CollectionChanged -= _queueItemsChanged;",
 "var hasCompleted = item.HasBytesCompletedMeasurement;":
 "var hasCompleted = item.BytesCompleted > 0;",
 "var hasTotal = item.HasBytesTotalMeasurement;":
 "var hasTotal = item.BytesTotal > 0;",
 "var percent = bytesTotal is > 0 && bytesCompleted is not null":
 "double? percent = bytesTotal is > 0 && bytesCompleted is not null",
}
def run(root:Path)->None:
 root=root.resolve(strict=True)
 raw={}
 sources={}
 for relative in FILES:
  file=root.joinpath(*relative.split("/"))
  if not file.is_file() or file.is_symlink():
   raise RuntimeError("E06_R51_ORIGINAL_OWNER_FILE_HOLD:"+relative)
  data=file.read_bytes()
  value=data.decode("utf-8-sig")
  raw[relative]=(file,data,data.startswith(b"\xef\xbb\xbf"),"\r\n" in value)
  sources[relative]=value.replace("\r\n","\n")
 event,win,queue=FILES
 rows=sources[event].splitlines(keepends=True)
 if len(rows)<=88:raise RuntimeError("E06_R51_EVENT_SOURCE_TOO_SHORT")
 source="".join(rows)
 position=sum(len(row) for row in rows[:87])+min(24,len(rows[87])-1)
 left=max(source.rfind(";",0,position),
          source.rfind("{",0,position),
          source.rfind("}",0,position))+1
 right=source.find(";",position)
 if right<=position:raise RuntimeError("E06_R51_EVENT_STATEMENT_BOUNDARY_HOLD")
 clause=source[left:right]
 arms=list(re.finditer(r"(?:\?|:)\s*(null)\b",clause))
 if len(arms)!=1 or "?" not in clause or ":" not in clause:
  raise RuntimeError("E06_R51_EVENT_TYPED_NULL_AMBIGUITY")
 offset=left+arms[0].start(1)
 patched={event:source[:offset]+"(long?)null"+source[offset+4:]}
 view=sources[win]
 for old,new in REPLACEMENTS.items():
  if view.count(old)!=1:raise RuntimeError("E06_R51_MODEL_CENTER_OWNER_ANCHOR_HOLD:"+old)
  view=view.replace(old,new,1)
 patched[win]=view
 original=sources[queue]
 if "PersistedQueueItem" not in original:
  raise RuntimeError("E06_R51_QUEUE_MODEL_TYPE_MISSING")
 converted,count=re.subn(r"\bPersistedItem\b","PersistedQueueItem",original)
 if not 0<count<8:raise RuntimeError("E06_R51_QUEUE_TYPE_AMBIGUITY")
 patched[queue]=converted
 prepared=[]
 for rel in FILES:
  file,data,bom,crlf=raw[rel]
  body=patched[rel].replace("\n","\r\n") if crlf else patched[rel]
  out=(b"\xef\xbb\xbf" if bom else b"")+body.encode("utf-8")
  if out==data:raise RuntimeError("E06_R51_EXPECTED_OWNER_CHANGE_MISSING:"+rel)
  prepared.append((file,out))
 # Preflight all original sources BEFORE any staged-source mutation.
 global_uses=root/"Integration/NOX.BuildGlobalUsings.cs"
 if global_uses.exists() or global_uses.is_symlink():
  raise RuntimeError("E06_R51_GLOBAL_USINGS_COLLISION")
 global_uses.parent.mkdir(parents=True,exist_ok=True)
 for file,out in prepared:
  file.write_bytes(out)
  if file.read_bytes()!=out:raise RuntimeError("E06_R51_SOURCE_READBACK_HOLD")
 global_uses.write_text(
    "global using System.IO;\n"
    "global using System.Net.Http;\n"
    "global using System.Net.Http.Headers;\n"
    "global using System.Threading;\n"
    "global using System.Threading.Tasks;\n",encoding="utf-8")
 print("E06_R51_NATIVE_WPF_OWNER_COMPAT_STAGED",len(prepared),
       "ORIGINAL_ARCHIVES_AND_PERSONA_MEDIA_UNCHANGED",flush=True)

if __name__=="__main__":
 if len(sys.argv)!=2:raise SystemExit("Usage: stage_wpf_final8_no_loss.py R11")
 run(Path(sys.argv[1]))
