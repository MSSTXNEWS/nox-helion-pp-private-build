"""Stage NOX MEGA 8–14 into SHA-pinned original R11, NEVER original ZIP."""
from pathlib import Path
import argparse,hashlib,json,base64,binascii
ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/"coordination/mega814"
INDEX_SHA="b57d58bb001c9826feb3bf7ff19510d047c7ec2926ee8b703538dfca886a960b"
CSS='<link rel="stylesheet" href="mega814/mega814.css" data-nox814="approved-owner">'
JS='<script type="module" src="mega814/mega814.mjs" data-nox814="approved-owner"></script>'
NAMES=("mega814.mjs","mega814.css","manifest.json","menu-v2-193.json","menu-v2-adapter.mjs","owner-dispatch.mjs","owner-e05.mjs","native-readonly.mjs")
PNG_SIGNATURE=bytes.fromhex("89504e470d0a1a0a")
def sha(raw):return hashlib.sha256(raw).hexdigest()
# Exact Git blob preimages of the eight original GitLab R75 donor sources.
# A self-generated staging SHA256 receipt is NOT independent provenance.
OWNER_BLOB_PINS={
 "mega814.mjs": "56c5ca52982bc39aae595597e7d0f9e5e3506f44",
 "mega814.css": "3d7ca3028b8ec84189bb3bdec9edb2f7614d0d8e",
 "manifest.json": "2b98f4c4182750eedcec879f5e2e696167aaf4e9",
 "menu-v2-193.json": "a57ced96e6edb5d77d99a83f945c47dbe97bbaf8",
 "menu-v2-adapter.mjs": "859dbabdd1915979cac79f8e7478326d63e44a59",
 "owner-dispatch.mjs": "f4eb000843bc78af116e4015ed06528b032ee991",
 "owner-e05.mjs": "1dcf0df656cdce6f4231f5f411db9150d0768ead",
 "native-readonly.mjs": "e698d3605646df0e2d39c7f2943c55d2364778c0"
}
def git_blob_sha(raw):
 return hashlib.sha1(b"blob "+str(len(raw)).encode("ascii")+b"\x00"+raw).hexdigest()
def approved_source(path,name):
 if name not in OWNER_BLOB_PINS or not path.is_file() or path.is_symlink():
  raise RuntimeError("MEGA814_APPROVED_SOURCE_PATH_HOLD:"+name)
 raw=path.read_bytes()
 if len(raw)>1048576 or git_blob_sha(raw)!=OWNER_BLOB_PINS[name]:
  raise RuntimeError("MEGA814_APPROVED_SOURCE_BLOB_HOLD:"+name)
 return raw
# Compatible with either original R11 or the exact verified Creative + WOW200
# additive tags; reconstruct the SAME immutable original HTML before admission.
D02_TAGS = (
 '<script src="creative/entry.js"></script>',
 '<link rel="stylesheet" href="creative/wow200/proposals/NOX-CINEMA-FX/nox-cinema.css">',
 '<link rel="stylesheet" href="creative/wow200/runtime/home-guard.css">',
 '<script type="module" src="creative/wow200/runtime/home-scene.mjs"></script>',
)
def verified_index_mode(raw:bytes,original_sha=INDEX_SHA):
 if sha(raw)==original_sha:return "ORIGINAL_R11"
 try: text=raw.decode("utf-8")
 except UnicodeDecodeError as exc:raise RuntimeError("MEGAB_INDEX_UTF8_HOLD") from exc
 if any(text.count(marker)!=1 for marker in D02_TAGS):
  raise RuntimeError("MEGAB_D02_MARKERS_MISSING_DUPLICATED_HOLD")
 clean=text
 for marker in D02_TAGS:clean=clean.replace(marker,"",1)
 if sha(clean.encode("utf-8"))!=original_sha:
  raise RuntimeError("MEGAB_ORIGINAL_INDEX_PREIMAGE_SHA_HOLD")
 return "D02_CREATIVE_WOW200_VERIFIED"

def verified_png(path, expected_sha, expected_bytes=None):
 # GitLab stores previously imported donor PNGs as strict base64 text blobs.
 # Decode to ORIGINAL image pixels only at disposable staging; raw PNG also
 # supported for local Drive mounts. Never skip the full approved SHA check.
 if not path.is_file() or path.is_symlink():raise RuntimeError("MEGA814_PNG_SOURCE_MISSING:"+path.name)
 raw=path.read_bytes()
 if len(raw)>16000000:raise RuntimeError("MEGA814_PNG_SOURCE_OVERSIZE:"+path.name)
 if raw.startswith(PNG_SIGNATURE):
  original=raw
 else:
  try:original=base64.b64decode(raw,validate=True)
  except (ValueError,binascii.Error) as error:
   raise RuntimeError("MEGA814_PNG_TRANSPORT_ENCODING_HOLD:"+path.name) from error
 if not original.startswith(PNG_SIGNATURE) or not (100<len(original)<=12000000) or (expected_bytes is not None and len(original)!=expected_bytes) or sha(original)!=expected_sha:
  raise RuntimeError("MEGA814_PNG_ORIGINAL_SHA_HOLD:"+path.name)
 return original
def run(source,menu=None,personas=None):
 source=Path(source).resolve(strict=True)
 idx=source/"Assets/index.html"
 if not idx.is_file() or idx.is_symlink():
  raise RuntimeError("MEGAB_INDEX_MISSING_HOLD")
 index_mode=verified_index_mode(idx.read_bytes())
 raw=idx.read_bytes();text=raw.decode("utf-8")
 if text.count("</head>")!=1 or text.count("</body>")!=1 or text.count('<section id="menu"')!=1 or text.count('<section id="control"')!=1 or 'nox-mega814-menu' in text:
  raise RuntimeError("MEGA814_ORIGINAL_SCREEN_ANCHOR_HOLD")
 spec=json.loads(approved_source(SOURCE/"manifest.json","manifest.json").decode("utf-8"))
 if spec["schema"]!="NOX-MEGA814-V16-OWNER-SOURCE-v1" or spec["sourceLock"]["originalIndexSHA256"]!=INDEX_SHA:
  raise RuntimeError("MEGA814_MANIFEST_SOURCELOCK_HOLD")
 target=source/"Assets/mega814"
 if target.exists() or target.is_symlink():raise RuntimeError("MEGA814_COLLISION_HOLD")
 files=[]
 for name in NAMES:
  p=SOURCE/name
  if not p.is_file() or p.is_symlink():raise RuntimeError("MEGA814_SOURCE_MISSING")
  asset_raw=approved_source(p,name)
  source_pins={"menu-v2-193.json":"0e300d0675930c5f5b83a03fc768868e89fd5f5545fd3ba5009493680c0d743b",
               "menu-v2-adapter.mjs":"cee7e06fb60406c5f4e37cc84b974f36de147696011607578fc6808fe6af2e05"}
  if name in source_pins and sha(asset_raw)!=source_pins[name]:
   raise RuntimeError("MEGA814_MENU_V2_SOURCE_SHA_HOLD:"+name)
  files.append((name,asset_raw))

 # Keep actual current Drive PNG byte-identical as reference, never
 # impersonate the later owner-design MENU10 SHA. The separate canonical
 # --menu10 path below remains a strict hard gate on its original digest.
 reference=SOURCE/"reference/NOX_HELION_MENU_LAVA_WORLD_CURRENT_20261022.png"
 if not reference.is_file() or reference.is_symlink():
  raise RuntimeError("MEGA814_CURRENT_REFERENCE_MISSING")
 reference_bytes=verified_png(reference,"ff9e65eda7bc9675ab92c74b5bb0e29acda66e1daa59a08aa781af968a62fdb0",2799300)
 if spec["asset"]["menuReferenceSHA256"]!="ff9e65eda7bc9675ab92c74b5bb0e29acda66e1daa59a08aa781af968a62fdb0":
  raise RuntimeError("MEGA814_CURRENT_REFERENCE_MANIFEST_SHA_HOLD")
 if spec["asset"]["menu10SHA256"]=="ff9e65eda7bc9675ab92c74b5bb0e29acda66e1daa59a08aa781af968a62fdb0":
  raise RuntimeError("MEGA814_CANONICAL_AND_REFERENCE_COLLISION_HOLD")
 files.append(("menu-reference.png",reference_bytes))
 # Reuse the byte-identical, owner-approved Drive MENU10 carried by this
 # source branch. An explicit CI path is permitted only with the same SHA.
 if not menu:
  menu=SOURCE/spec["asset"]["menu10OwnerOriginal"]["file"]
 p=Path(menu).resolve(strict=True)
 menu_bytes=verified_png(p,spec["asset"]["menu10SHA256"],2955611)
 files.append(("menu10.png",menu_bytes))
 # Preserve the four actual owner-approved PNG files, unmodified.
 # EV is withheld by the owner's IDENTITY_CONFLICT_HOLD.
 folder=Path(personas).resolve(strict=True) if personas else SOURCE/"approved_persona"
 if not folder.is_dir() or folder.is_symlink():raise RuntimeError("MEGA814_PERSONA_FOLDER_HOLD")
 for person in spec["personas"]:
  if person["status"]=="IDENTITY_CONFLICT_HOLD":continue
  pic=folder/person["file"]
  pic_bytes=verified_png(pic,person["sha256"])
  files.append(("persona-"+person["id"]+".png",pic_bytes))
 patched=text.replace("</head>",CSS+"</head>",1).replace("</body>",JS+"</body>",1).encode("utf-8")
 if patched.replace(CSS.encode(),b"").replace(JS.encode(),b"")!=raw:
  raise RuntimeError("MEGA814_ORIGINAL_BODY_NOLOSS_HOLD")
 target.mkdir()
 receipts=[]
 for name,data in files:
  p=target/name
  with p.open("xb") as out:out.write(data)
  if p.read_bytes()!=data:raise RuntimeError("MEGA814_STAGE_READBACK_HOLD")
  receipts.append({"name":name,"sha256":sha(data),"bytes":len(data)})
 idx.write_bytes(patched)
 if idx.read_bytes()!=patched:raise RuntimeError("MEGA814_INDEX_READBACK_HOLD")
 (target/"MEGA814_RECEIPT.json").write_text(json.dumps({
  "source_index_sha256":INDEX_SHA,"staged_sha256":sha(patched),
  "status":"SOURCE_MOUNTED_NOT_E07",
  "index_preimage_mode":index_mode,
  "menu10_asset_verified":True,"menu_reference_sha256":"ff9e65eda7bc9675ab92c74b5bb0e29acda66e1daa59a08aa781af968a62fdb0","menu_reference_status":"REFERENCE_ONLY_NOT_CANONICAL_MENU10","personas_asset_verified":sum(x["name"].startswith("persona-") for x in receipts),
  "worlds":10,"work_views":8,"legacy_routes":54,"visual_criteria":30,
  "windows_gui_qa":"NOT_RUN","release_accepted":False,"files":receipts
 },indent=2),"utf-8")
 print("NOX_MEGA814_ORIGINAL_WPF_SOURCE_MOUNTED_NOLOSS",len(files))
if __name__=="__main__":
 p=argparse.ArgumentParser();p.add_argument("--r11",required=True)
 p.add_argument("--menu10");p.add_argument("--personas");args=p.parse_args()
 run(args.r11,args.menu10,args.personas)
