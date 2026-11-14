"""R08 WPF source diagnostic: E02 stage-only compatibility patches, all originals preserved.

Applied AFTER existing E06 compiler repairs; stage source is pinned by Git SHA,
original R08 ZIP byte manifest and E06 original/repair receipts. Nothing here
changes GitHub owner files, product source, historical archives, or user data.
"""
from __future__ import annotations
import difflib
import hashlib
import json
from pathlib import Path

STAGE = Path("work/e06/staged").resolve()
ROOT = STAGE / "R11"
LEGACY = STAGE / "legacy-compiler-repair-receipts.json"
RUN = "NOX-V16-E02-R08-DIAGNOSTIC-COMPAT-20261028"

def sha(b: bytes) -> str: return hashlib.sha256(b).hexdigest()

def edit(rel: str, replacements: list[tuple[str, str]], known_sha: str | None, receipts: list):
    file = ROOT / rel
    if not file.is_file() or file.is_symlink() or not file.resolve().is_relative_to(ROOT):
        raise SystemExit("UNSAFE_DIAGNOSTIC_FILE:" + rel)
    before = file.read_bytes()
    if known_sha is not None and sha(before) != known_sha:
        raise SystemExit("DIAGNOSTIC_UNEXPECTED_SOURCE:" + rel + ":" + sha(before))
    source = before.decode("utf-8")
    after = source
    for old, new in replacements:
        if after.count(old) != 1:
            raise SystemExit("TOKEN_DRIFT:" + rel + ":" + old[:50])
        after = after.replace(old, new, 1)
    if after == source: raise SystemExit("DIAGNOSTIC_NO_OP:" + rel)
    new = after.encode("utf-8")
    backup = STAGE / "e02-original-owners" / rel
    backup.parent.mkdir(parents=True, exist_ok=True)
    backup.write_bytes(before)
    file.write_bytes(new)
    if file.read_bytes() != new or backup.read_bytes() != before:
        raise SystemExit("DIAGNOSTIC_BYTE_READBACK_FAILED:" + rel)
    diff = "".join(difflib.unified_diff(source.splitlines(True), after.splitlines(True),fromfile=rel+":pre",tofile=rel+":ci-only"))
    receipts.append({"path": "R11/"+rel, "pre_sha256":sha(before), "post_sha256":sha(new),
                     "patch_sha256":sha(diff.encode()), "run_id":RUN,
                     "scope":"DIAGNOSTIC_BUILD_ONLY", "original_retained":True,
                     "owner_acceptance":"HOLD"})

def main():
    if not LEGACY.is_file(): raise SystemExit("E06_BASELINE_REPAIR_RECEIPT_MISSING")
    previous = json.loads(LEGACY.read_text("utf-8"))
    verified = {x["path"].removeprefix("R11/"):x["postimage_sha256"] for x in previous["files"]}
    # All script-edited paths must match E06 byte receipts; every other source
    # was already checked against the R08 manifest during stage extraction.
    receipts=[]
    edit("Packages/P03/worker-window/ModelDownloaderWindow.xaml.cs", [
      ("_queueStore.Items.CollectionChanged += _queueItemsChanged;",
       "((System.Collections.Specialized.INotifyCollectionChanged)_queueStore.Items).CollectionChanged += _queueItemsChanged;"),
      ("_queueStore.Items.CollectionChanged -= _queueItemsChanged;",
       "((System.Collections.Specialized.INotifyCollectionChanged)_queueStore.Items).CollectionChanged -= _queueItemsChanged;"),
      ("var hasCompleted = item.HasBytesCompletedMeasurement;",
       "var hasCompleted = item.BytesCompleted > 0; // diagnostic fallback: never assert unknown progress"),
      ("var hasTotal = item.HasBytesTotalMeasurement;",
       "var hasTotal = item.BytesTotal > 0; // diagnostic fallback: zero is not measured"),
      ("var percent = bytesTotal is > 0 && bytesCompleted is not null",
       "double? percent = bytesTotal is > 0 && bytesCompleted is not null"),
    ],verified.get("Packages/P03/worker-window/ModelDownloaderWindow.xaml.cs"),receipts)
    edit("Packages/P03/worker-queue/ModelDownloadQueueStore.cs", [
      ("new List<PersistedItem>(records.Count)","new List<PersistedQueueItem>(records.Count)"),
    ], verified.get("Packages/P03/worker-queue/ModelDownloadQueueStore.cs"),receipts)
    edit("Contracts/EventV3Bridge.cs", [
      ("var completed = total.HasValue && sourceEvent.BytesCompleted is >= 0",
       "long? completed = total.HasValue && sourceEvent.BytesCompleted is >= 0"),
    ],verified.get("Contracts/EventV3Bridge.cs"),receipts)
    # Default implicit using set in this older project lacks System.IO.
    # Add one new stage-only C# global import, instead of changing 10+ owner files.
    imports = ROOT / "GlobalUsings.E02Diagnostic.cs"
    if imports.exists():raise SystemExit("DIAGNOSTIC_IMPORT_ALREADY_EXISTS")
    imports.write_bytes(b"global using System.IO;\n")
    receipts.append({"path":"R11/GlobalUsings.E02Diagnostic.cs","pre_sha256":None,
       "post_sha256":sha(imports.read_bytes()),"source_origin":"ADDED_STAGE_ONLY",
       "run_id":RUN,"owner_acceptance":"HOLD"})
    payload={"run_id":RUN,"schema":"NOX_E02_R08_DIAGNOSTIC_STAGE_ONLY_V1",
             "no_product_owner_source_changed":True,"release_accepted":False,
             "entries":receipts}
    target=STAGE/"E02-compiler-compat-receipt.json"
    target.write_text(json.dumps(payload,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print("E02_R08_DIAGNOSTIC_REPAIRS",len(receipts),"ALL_BACKUPS_PRESERVED")

if __name__ == "__main__":main()
