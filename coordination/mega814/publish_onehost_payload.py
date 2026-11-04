"""Copy the pre-verified owner MENU10 payload into the existing OneHost.

Call ONLY from owner #1: after WPF publish/visual copy, before NSIS manifest.
No alternate EXE, backend, image or release assertion.
"""
from __future__ import annotations
import argparse, hashlib, json, shutil, tempfile
from pathlib import Path
MENU_SHA="1cdc1d9d6f17033bf4a1c6a8ec1b8f5816ab35ddd5ed6d682eb8a190e1943dca"
EXPECTED=frozenset(("mega814.mjs","mega814.css","manifest.json","menu-v2-193.json","menu-v2-adapter.mjs",
 "owner-dispatch.mjs","owner-e05.mjs","native-readonly.mjs",
 "menu10.png","menu-reference.png","persona-KV.png","persona-AM.png",
 "persona-LA.png","persona-KW.png"))
def digest(path):
 h=hashlib.sha256()
 with path.open("rb") as f:
  while block:=f.read(1024*1024):h.update(block)
 return h.hexdigest()
def under_plain(root,path):
 root=root.resolve(strict=True)
 path=path.absolute()
 if not path.is_relative_to(root):raise RuntimeError("MEGAB_OUTSIDE_APPROVED_ROOT")
 p=path
 while p!=root:
  if p.is_symlink():raise RuntimeError("MEGAB_REPARSE_HOLD")
  p=p.parent
 return path
def publish(staged,payload):
 staged=staged.resolve(strict=True); payload=payload.resolve(strict=True)
 source=under_plain(staged,staged/"Assets/mega814")
 assets=under_plain(payload,payload/"Assets")
 dest=under_plain(payload,assets/"mega814")
 if not source.is_dir() or not assets.is_dir():
  raise RuntimeError("MEGAB_STAGE_OR_PAYLOAD_COLLISION")
 source_index=under_plain(staged,staged/"Assets/index.html")
 published_index=under_plain(payload,assets/"index.html")
 if not source_index.is_file() or not published_index.is_file() or digest(source_index)!=digest(published_index):
  raise RuntimeError("MEGAB_PUBLISHED_INDEX_SHA_DIFFERS")
 html=source_index.read_text("utf-8")
 if (html.count('data-nox814="approved-owner"')!=2 or
     html.count('src="mega814/mega814.mjs"')!=1 or
     html.count('href="mega814/mega814.css"')!=1 or
     html.count('creative/wow200/runtime/home-scene.mjs')!=1):
  raise RuntimeError("MEGAB_NATIVE_D02_MENU10_ENTRY_NOT_PRESENT")
 receipt_path=under_plain(staged,source/"MEGA814_RECEIPT.json")
 if not receipt_path.is_file():raise RuntimeError("MEGAB_SOURCE_RECEIPT_MISSING")
 receipt=json.loads(receipt_path.read_text("utf-8"))
 if (receipt.get("status")!="SOURCE_MOUNTED_NOT_E07" or
     receipt.get("index_preimage_mode")!="D02_CREATIVE_WOW200_VERIFIED" or
     receipt.get("release_accepted") is not False or
     receipt.get("windows_gui_qa")!="NOT_RUN" or
     receipt.get("menu10_asset_verified") is not True or
     [receipt.get(x) for x in ("worlds","work_views","legacy_routes","visual_criteria")]!=[10,8,54,30]):
  raise RuntimeError("MEGAB_OWNER_RECEIPT_HOLD")
 rows=receipt.get("files")
 if not isinstance(rows,list) or len(rows)!=len(EXPECTED) or any(not isinstance(r,dict) for r in rows):
  raise RuntimeError("MEGAB_ASSET_RECEIPT_COUNT_HOLD")
 names=[x.get("name") for x in rows]
 if set(names)!=EXPECTED or len(set(names))!=len(rows):
  raise RuntimeError("MEGAB_ASSET_SET_HOLD")
 if {p.name for p in source.iterdir()}!=EXPECTED|{"MEGA814_RECEIPT.json"}:
  raise RuntimeError("MEGAB_UNLISTED_SOURCE_HOLD")
 seen=0
 for row in rows:
  file=under_plain(staged,source/row["name"])
  if not file.is_file() or file.stat().st_size!=row.get("bytes") or digest(file)!=row.get("sha256"):
   raise RuntimeError("MEGAB_SOURCE_ASSET_MISMATCH:"+row["name"])
  seen+=file.stat().st_size
  if seen>50000000:raise RuntimeError("MEGAB_SOURCE_SIZE_CAP")
 if next(r["sha256"] for r in rows if r["name"]=="menu10.png")!=MENU_SHA:
  raise RuntimeError("MEGAB_MENU10_CANONICAL_SHA_HOLD")
 # The installed WebView2 root is Assets/. Resolve native imports only
 # against the original approved WOW200 module tree, not a phantom /ui/ root.
 menu_js=(source/"mega814.mjs").read_text("utf-8")
 if 'from "../creative/wow200/ui/onehost-menu-bindings.mjs"' not in menu_js:
  raise RuntimeError("MEGAB_NATIVE_CLIENT_RELATIVE_IMPORT_HOLD")
 native_src=under_plain(staged,staged/"Assets/creative/wow200/ui/onehost-menu-bindings.mjs")
 native_dest=under_plain(payload,payload/"Assets/creative/wow200/ui/onehost-menu-bindings.mjs")
 if not native_src.is_file() or not native_dest.is_file() or digest(native_src)!=digest(native_dest):
  raise RuntimeError("MEGAB_NATIVE_CLIENT_PUBLISHED_SHA_HOLD")
 if dest.exists() or dest.is_symlink():
  # dotnet publish may already copy Content Assets/**. In that case verify
  # it in place, never overwrite an untrusted published output.
  if not dest.is_dir() or dest.is_symlink() or (
      {x.name for x in dest.iterdir()}!=EXPECTED|{"MEGA814_RECEIPT.json"}):
   raise RuntimeError("MEGAB_PUBLISHED_ASSET_SET_HOLD")
  for row in rows:
   existing=under_plain(payload,dest/row["name"])
   if (not existing.is_file() or existing.stat().st_size!=row["bytes"]
       or digest(existing)!=row["sha256"]):
    raise RuntimeError("MEGAB_PUBLISHED_ASSET_SHA_HOLD:"+row["name"])
  saved=under_plain(payload,dest/"MEGA814_RECEIPT.json")
  if not saved.is_file() or digest(saved)!=digest(receipt_path):
   raise RuntimeError("MEGAB_PUBLISHED_RECEIPT_SHA_HOLD")
  return dict(status="SOURCE_PUBLISHED_VERIFIED_NOT_E07",files=len(rows),
              menu10_sha256=MENU_SHA,release_accepted=False)
 temp=Path(tempfile.mkdtemp(prefix=".nox-megab-",dir=str(assets)))
 try:
  for row in rows:
   target=temp/row["name"]
   shutil.copyfile(source/row["name"],target)
   if digest(target)!=row["sha256"]:raise RuntimeError("MEGAB_COPY_SHA_HOLD:"+row["name"])
  shutil.copyfile(receipt_path,temp/"MEGA814_RECEIPT.json")
  if digest(temp/"MEGA814_RECEIPT.json")!=digest(receipt_path):
   raise RuntimeError("MEGAB_COPY_RECEIPT_SHA_HOLD")
  temp.rename(dest)
 except BaseException:
  if temp.exists():shutil.rmtree(temp)
  raise
 return dict(status="SOURCE_PAYLOAD_NOT_E07",files=len(rows),
             menu10_sha256=MENU_SHA,release_accepted=False)
if __name__=="__main__":
 p=argparse.ArgumentParser()
 p.add_argument("--r11",required=True);p.add_argument("--payload",required=True)
 a=p.parse_args()
 print(json.dumps(publish(Path(a.r11),Path(a.payload)),sort_keys=True))
