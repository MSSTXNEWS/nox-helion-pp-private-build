"""One source-only gate for megablock 8–14; no fake E07."""
# The original assertions must never vanish when PYTHONOPTIMIZE/-O is set.
if not __debug__:
 raise RuntimeError("MEGA814_OPTIMIZED_ASSERTIONS_HOLD")
import ast,json,hashlib
from pathlib import Path
from stage_original_r11 import verified_png
ROOT=Path(__file__).resolve().parents[2]/"coordination/mega814"
def check():
 d=json.loads((ROOT/"manifest.json").read_text("utf-8"))
 # Canonical MENU10: actual owner Drive bytes, not a proxy/reference image.
 menu=ROOT/d["asset"]["menu10OwnerOriginal"]["file"]
 assert d["asset"]["menu10SHA256"]=="1cdc1d9d6f17033bf4a1c6a8ec1b8f5816ab35ddd5ed6d682eb8a190e1943dca", "MENU10_CANONICAL_MANIFEST_HOLD"
 assert verified_png(menu,d["asset"]["menu10SHA256"],2955611), "MENU10_CANONICAL_SHA_HOLD"
 assert d["asset"]["menu10OwnerOriginal"]["driveFileId"]=="1B8rPaZ7dBvn_s8dh-UTUFSj9zLlfrYnk"
 routes=[x for lane in d["legacyRouteGroups"].values() for x in lane]
 assert len(routes)==len(set(routes))==54

 # Prove both distinct identities, and verify ORIGINAL pixel bytes rather
 # than overriding the approved MENU10 digest in a manifest.
 ref=ROOT/"reference/NOX_HELION_MENU_LAVA_WORLD_CURRENT_20261022.png"
 assert verified_png(ref,"ff9e65eda7bc9675ab92c74b5bb0e29acda66e1daa59a08aa781af968a62fdb0",2799300),"RAW_DRIVE_REFERENCE_SHA"
 assert d["asset"]["menuReferenceSHA256"]=="ff9e65eda7bc9675ab92c74b5bb0e29acda66e1daa59a08aa781af968a62fdb0"
 assert d["asset"]["menu10SHA256"]=="1cdc1d9d6f17033bf4a1c6a8ec1b8f5816ab35ddd5ed6d682eb8a190e1943dca"
 assert d["asset"]["menu10SHA256"]!=d["asset"]["menuReferenceSHA256"]
 assert d["asset"]["menuReference"]["status"]=="REFERENCE_ONLY_NOT_CANONICAL_MENU10"
 assert len(d["worlds"])==10 and len(d["workViews"])==8
 assert len(d["coreIds"])==8 and len(d["personas"])==5
 assert len(d["criteria"]["motion"])==len(d["criteria"]["realism"])==len(d["criteria"]["ui"])==10
 assert d["personas"][3]["status"]=="IDENTITY_CONFLICT_HOLD"
 assets=ROOT/"approved_persona"
 for person in d["personas"]:
  if person["id"]=="EV":continue
  f=assets/person["file"]
  assert verified_png(f,person["sha256"]),person["id"]
 assert not (assets/d["personas"][3]["file"]).exists(), "EV_MUST_NOT_BE_BUNDLED"

 assert all(0<=w["legacyIndex"]<8 and set(w["routes"])<=set(routes) for w in d["worlds"])
 ast.parse((ROOT/"stage_original_r11.py").read_text("utf-8"))
 assert "b57d58bb001c9826feb3bf7ff19510d047c7ec2926ee8b703538dfca886a960b" in (ROOT/"stage_original_r11.py").read_text("utf-8")
 js=(ROOT/"mega814.mjs").read_text("utf-8")
 catalog=json.loads((ROOT/"menu-v2-193.json").read_text("utf-8"))
 assert hashlib.sha256((ROOT/"menu-v2-193.json").read_bytes()).hexdigest()=="0e300d0675930c5f5b83a03fc768868e89fd5f5545fd3ba5009493680c0d743b", "MENU_V2_APPROVED_CATALOG_SHA_HOLD"
 assert hashlib.sha256((ROOT/"menu-v2-adapter.mjs").read_bytes()).hexdigest()=="cee7e06fb60406c5f4e37cc84b974f36de147696011607578fc6808fe6af2e05", "MENU_V2_APPROVED_ADAPTER_SHA_HOLD"
 assert catalog["schema"]=="NOX-MENU-V2-193-EXACT-OWNER-SPEC-V1"
 assert len(catalog["worlds"])==10 and sum(len(w["items"]) for w in catalog["worlds"])==193
 assert len({i["id"] for w in catalog["worlds"] for i in w["items"]})==193
 assert {w["id"] for w in catalog["worlds"]}=={w["id"] for w in d["worlds"]}
 assert all(i["handler_status"]!="E07_ACCEPTED" for w in catalog["worlds"] for i in w["items"])
 assert "HOLD" in js and "projectSpaceView" in js
 assert (ROOT/"owner-dispatch.mjs").is_file() and (ROOT/"owner-e05.mjs").is_file()
 assert "NAMES=(\"mega814.mjs\",\"mega814.css\",\"manifest.json\",\"menu-v2-193.json\",\"menu-v2-adapter.mjs\",\"owner-dispatch.mjs\",\"owner-e05.mjs\",\"native-readonly.mjs\")" in (ROOT/"stage_original_r11.py").read_text("utf-8")

 assert (ROOT/"native-readonly.mjs").is_file()
 native=(ROOT/"native-readonly.mjs").read_text("utf-8")
 assert "chat.model" in native and "p02.native" in native and "p02NativeResult" in native
 assert "getRandomValues" in native and "NATIVE_TIMEOUT_HOLD" in native
 assert "e07Accepted:false" in native and "chat.stop" in native
 assert "createE05ReadOnlyStore" in js and "window.chrome?.webview" in js
 assert 'host.postMessage({action:"refreshTelemetry"})' in js
 assert 'host.postMessage({action:"readMainSnapshot"})' in js
 assert "typeof gpu.temperature" in js and "typeof gpu.utilization" in js
 assert "E07" in js and "nativeReady" in js

 assert "const port=null,dispatcher=null" not in js
 assert "SOURCE_COMPILE_PASS_NOT_E07" not in js

 print("MEGA814_SOURCE_GATE_PASS WORLD10 WORK8 PERSONA5 ROUTE54 CRITERIA30 INDEX_SOURCE_LOCK")
if __name__=="__main__":check()
