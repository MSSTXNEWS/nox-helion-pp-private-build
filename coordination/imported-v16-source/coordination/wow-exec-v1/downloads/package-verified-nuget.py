import hashlib,json,os,pathlib,shutil
base=pathlib.Path(os.environ["RUNNER_TEMP"])
root=base/"nox-nuget-original"
out=base/"nox-nuget-transfer"
out.mkdir(exist_ok=True)
r=json.loads((root/"BLOCK1_NUGET_CLOSURE_RECEIPT.json").read_text("utf-8-sig"))
assert r["status"]=="PASS" and len(r["packages"])==16
group,used,limit=1,0,250*1024*1024
entries=[]
for p in r["packages"]:
 assert p["verification"]=="SIGNED_NUGET_PASS"
 file=root.joinpath(*p["relative_path"].split("/"))
 assert file.is_file() and not file.is_symlink()
 size=file.stat().st_size
 assert size==p["bytes"] and size<=limit
 h=hashlib.file_digest(file.open("rb"),"sha256").hexdigest()
 assert h==p["sha256"]
 if used+size>limit:group+=1;used=0
 assert group<=8
 dest=out/f"group{group:02d}"
 dest.mkdir(exist_ok=True)
 target=dest/file.name
 assert not target.exists()
 shutil.copyfile(file,target)
 assert hashlib.file_digest(target.open("rb"),"sha256").hexdigest()==h
 used+=size
 entries.append(dict(group=group,name=file.name,sha256=h,bytes=size))
manifest={"schema":"NOX-R11-NUGET-TRANSFER-V1","source_run":41326720252,"installed":False,"merged":False,"package_count":len(entries),"entries":entries}
(out/"PACKAGES_MANIFEST.json").write_text(json.dumps(manifest,indent=2))
print("NUGET_PARTS_VERIFIED",len(entries),"GROUPS",group,flush=True)
