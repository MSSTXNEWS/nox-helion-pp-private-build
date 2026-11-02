#!/usr/bin/env python3
"""NOX: checked offline monolith. Does not install or run anything."""
import argparse,base64,hashlib,json,subprocess,zipfile,io
from pathlib import Path
D02={"home.png":("382c1069afcaaaed11c319796f2c553d2bd977d7e46c68ecd7d55af26e132a4a",3707870),"menu.png":("4c73d137e6d25f496abb006dbb8af08b1fe272d2f935c5006f0f42b6fd9992b9",2304970),"core01.png":("343e5c73539358fe2c086706b4155cc0f9cd9702fcd40a98b4aab130585bec97",2285847),"menu_sections.png":("7d181604f913cf9956c173c14da3dc7fd0238c389322896588cec4407b4024a4",2662583)}
ART={"13089912982":("9eceadef3e3593794546fbaec744bc1183dc909c2828e2ce3608b0967b450262",239029177),"13091816182":("98ebe63f1ce5ce97f6eb47aa869e8f868488273845574cad67151f2dbe7e2f11",145062596),"13091551815":("243724730a8d756709377d54bf106307e54e6455b8bcc25c3d14c88b093da32a",212131337),"13092140486":("3a039cd99295aab2fb38c38e2258379678d3d623d226402e8497ce7f5720135f",1313),"13091167316":("b43c11b0c491f092ace92a293a7cef471576fba7e1812af7fbabd8829692bcb8",678),"13091032633":("7d73b9f9d442f28f2f23f8471ecf3e2f88bc475793d803ba2feb0f12144ce30f",402653360),"13090299607":("ada1537cd9f579ae698b970d9f47a78a210d0bbe4287981e6eadf279e0943fae",402653360),"13090519359":("aa9de4dc0e71f6e030c2ce545ad8b8b026234b0a51a400174ea20c3750f1c5a8",402653360),"13091207322":("d03365202e681f9f9dadf2dd04e07a4f7d1833348b6bb5d5492aed9835f4c4cb",402653360),"13091730341":("b2be016857e1ae740600c4064468e1b6a4940798c562edc468fd18dfd522f75e",65653880)}
def sha_file(p):
 h=hashlib.sha256()
 with p.open("rb") as f:
  for part in iter(lambda:f.read(4*1024*1024),b""):h.update(part)
 return h.hexdigest()
def shards(folder,name):
 p=sorted(folder.glob(name+".b64.part*"))
 if not p:raise RuntimeError("MISSING_ASSET_PARTS "+name)
 return base64.b64decode("".join(x.read_text("ascii") for x in p),validate=True)
def main():
 p=argparse.ArgumentParser();p.add_argument("--downloads",required=True);p.add_argument("--output",required=True);args=p.parse_args()
 src=Path.cwd();dl=Path(args.downloads);out=Path(args.output);data={};checked={}
 for name,(digest,size) in D02.items():
  raw=shards(src/"BOOST_CACHE/d02_chunks",name)
  if len(raw)!=size or hashlib.sha256(raw).hexdigest()!=digest:raise RuntimeError("D02_SHA_HOLD "+name)
  data[name]=raw;checked[name]={"sha256":digest,"bytes":size}
 r9=shards(src/"BOOST_CACHE/r9_chunks","NOX_APP_R9.zip")
 if len(r9)!=10777015:raise RuntimeError("R9_SIZE_HOLD")
 with zipfile.ZipFile(io.BytesIO(r9)) as z:
  if z.testzip():raise RuntimeError("R9_BAD_ZIP")
 data["NOX_APP_R9.zip"]=r9;checked["NOX_APP_R9.zip"]={"sha256":hashlib.sha256(r9).hexdigest(),"bytes":len(r9)}
 for id,(digest,size) in ART.items():
  f=dl/(id+".zip")
  if not f.is_file() or f.stat().st_size!=size or sha_file(f)!=digest:raise RuntimeError("ARTIFACT_PIN_HOLD "+id)
  with zipfile.ZipFile(f) as z:
   if z.testzip():raise RuntimeError("ARTIFACT_CRC_HOLD "+id)
  checked["artifact_"+id]={"sha256":digest,"bytes":size}
 names=subprocess.check_output(["git","ls-files","-z"]).decode().split("\0")
 exclude=(".ttf",".otf",".woff",".woff2",".eot")
 out.parent.mkdir(parents=True,exist_ok=True)
 with zipfile.ZipFile(out,"w",compression=zipfile.ZIP_STORED,allowZip64=True) as z:
  count=0
  for name in names:
   if not name or name.startswith(("BOOST_CACHE/d02_chunks/","BOOST_CACHE/r9_chunks/")) or name.lower().endswith(exclude):continue
   f=src/name
   if f.is_file() and not f.is_symlink():z.write(f,"SOURCES/"+name);count+=1
  for name,raw in data.items():z.writestr("APPROVED_D02/"+name,raw)
  for id in ART:z.write(dl/(id+".zip"),"GITHUB_CACHED_BINARIES/"+id+".zip")
  manifest={"schema":"NOX-MEGA-BOOST-MONOLITH-V1","base_pr162_sha":"ed4fbb76a04f3998d9dfe891e42a9a53caa6be3c","source_files":count,"verified_components":checked,"status":"SOURCE_AND_DEPS_CACHE_ONLY","installed_e07":False,"onehost_replaced":False}
  z.writestr("MANIFEST.json",json.dumps(manifest,indent=2,ensure_ascii=False))
 with zipfile.ZipFile(out) as z:
  bad=z.testzip()
  if bad:raise RuntimeError("FINAL_ZIP_CRC_HOLD "+bad)
 out.with_suffix(".sha256").write_text(sha_file(out)+"  "+out.name+"\n")
 print("MONOLITH_PASS",out.stat().st_size,"source_files",count,"sha256",sha_file(out),flush=True)
if __name__=="__main__":main()
