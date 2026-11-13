#!/usr/bin/env python3
"""Download actual missing NOX catalog items. No install, training or production writes."""
import os, sys, json, hashlib, shutil, tarfile, zipfile, urllib.request, urllib.parse, pathlib, time, traceback, datetime
ROOT=pathlib.Path("out")
ROOT.mkdir(exist_ok=True)
TARGETS={
  "70":{"id":70,"kind":"github","name":"Hindsight","repo":"vectorize-io/hindsight"},
  "74":{"id":74,"kind":"github","name":"Generative Agents","repo":"joonspk-research/generative_agents"},
  "32":{"id":32,"kind":"hf","name":"Qwen3 Embedding 0.6B","repo":"Qwen/Qwen3-Embedding-0.6B"},
  "33":{"id":33,"kind":"hf","name":"Qwen3 Reranker 0.6B","repo":"Qwen/Qwen3-Reranker-0.6B"},
  "77":{"id":77,"kind":"hf","name":"ruBERT CEDR Emotion","repo":"cointegrated/rubert-tiny2-cedr-emotion-detection"},
  "78":{"id":78,"kind":"hf","name":"MarIA Emotion ES","repo":"UMUTeam/MarIA-emotion-es"},
  "6":{"id":6,"kind":"service","name":"OpenRouter Free","url":"https://openrouter.ai/collections/free-models"}
}
def hexsha(p):
    h=hashlib.sha256()
    with open(p,"rb") as f:
        for chunk in iter(lambda:f.read(4*1024*1024),b""):h.update(chunk)
    return h.hexdigest()
def request(url,token=False):
    h={"User-Agent":"NOX-Catalog-Verified-Source-Acquisition/1.0","Accept":"application/vnd.github+json"}
    if token and os.getenv("GH_TOKEN"):h["Authorization"]="Bearer "+os.environ["GH_TOKEN"]
    return urllib.request.Request(url,headers=h)
def json_url(url,token=False):
    with urllib.request.urlopen(request(url,token),timeout=45) as r:return json.load(r)
def streaming_download(url,path,limit=2_000_000_000):
    tmp=path.with_name(path.name+".partial")
    count=0
    try:
        with urllib.request.urlopen(request(url),timeout=240) as r,open(tmp,"wb") as out:
            while True:
                block=r.read(4*1024*1024)
                if not block:break
                count+=len(block)
                if count>limit:raise RuntimeError("Exceeded 2GB source archive safety bound")
                out.write(block)
        if count<128:raise RuntimeError("Upstream content too small")
        os.replace(tmp,path)
        return count
    finally:tmp.unlink(missing_ok=True)
def github_snapshot(config,report):
    owner,repo=config["repo"].split("/")
    meta=json_url("https://api.github.com/repos/"+owner+"/"+repo,token=True)
    branch=meta["default_branch"]
    commit=json_url("https://api.github.com/repos/"+owner+"/"+repo+"/commits/"+urllib.parse.quote(branch,safe=""),token=True)["sha"]
    report.update({"revision":commit,"branch":branch,"source":"https://github.com/"+config["repo"]})
    url="https://codeload.github.com/"+config["repo"]+"/zip/"+commit
    output=ROOT/("source_"+str(config["id"])+".zip")
    streaming_download(url,output)
    if not zipfile.is_zipfile(output):raise RuntimeError("Downloaded repo not valid ZIP")
    with zipfile.ZipFile(output) as z:
        if not z.namelist():raise RuntimeError("Empty archive")
        bad=z.testzip()
        if bad:raise RuntimeError("ZIP CRC failure: "+bad)
        report["archive_members"]=len(z.namelist())
    report["files"]=[{"file":output.name,"bytes":output.stat().st_size,"sha256":hexsha(output)}]
    report["status"]="DOWNLOADED_VERIFIED"
def hf_snapshot(config,report):
    from huggingface_hub import HfApi,snapshot_download
    api=HfApi()
    repo=config["repo"]
    info=api.model_info(repo,files_metadata=True)
    revision=info.sha
    report.update({"revision":revision,"source":"https://huggingface.co/"+repo})
    dst=ROOT/"model"
    os.environ["HF_HUB_DISABLE_TELEMETRY"]="1"
    snapshot_download(repo_id=repo,revision=revision,local_dir=str(dst),max_workers=6)
    weights=list(dst.rglob("*.safetensors"))+list(dst.rglob("*.bin"))
    if not any(x.stat().st_size>10_000_000 for x in weights):
        raise RuntimeError("NO FULL WEIGHTS: downloaded snapshot missing nontrivial model weight file")
    files=[]; sibling_by_name={s.rfilename:s for s in info.siblings or []}
    for p in sorted(dst.rglob("*")):
        if not p.is_file() or ".cache" in p.relative_to(dst).parts:continue
        rel=p.relative_to(dst).as_posix()
        sha=hexsha(p)
        sib=sibling_by_name.get(rel)
        lfs=getattr(sib,"lfs",None)
        expected=lfs.get("sha256") if isinstance(lfs,dict) else (getattr(lfs,"sha256",None) if lfs else None)
        if expected and sha!=expected:raise RuntimeError("LFS SHA mismatch: "+rel)
        files.append({"file":rel,"bytes":p.stat().st_size,"sha256":sha, "matches_upstream_sha256":bool(expected)})
    report["files"]=files
    report["total_file_bytes"]=sum(x["bytes"] for x in files)
    if not files:raise RuntimeError("Model snapshot empty")
    bundle=ROOT/("model_"+str(config["id"])+".tar")
    with tarfile.open(bundle,"w") as tar:
        for p in sorted(dst.rglob("*")):
            if p.is_file() and ".cache" not in p.relative_to(dst).parts:
                tar.add(p,arcname="model/"+p.relative_to(dst).as_posix(),recursive=False)
    shutil.rmtree(dst)
    report["bundle"]={"file":bundle.name,"bytes":bundle.stat().st_size,"sha256":hexsha(bundle)}
    report["status"]="DOWNLOADED_VERIFIED"
    report["usage"]="weights downloaded; NOX integration, GPU fit and unsafe PyTorch pickle formats NOT validated"
def openrouter_service(config,report):
    models=json_url("https://openrouter.ai/api/v1/models")
    (ROOT/"openrouter_models_public.json").write_text(json.dumps(models,ensure_ascii=False,indent=2)+"\n")
    def zero(x):
        try:return float(x.get("pricing",{}).get("prompt","1"))==0 and float(x.get("pricing",{}).get("completion","1"))==0
        except:return False
    free=[m for m in models.get("data",[]) if zero(m)]
    (ROOT/"openrouter_free_models.json").write_text(json.dumps(free,ensure_ascii=False,indent=2)+"\n")
    desc=("OpenRouter Free is a hosted API SERVICE, not downloadable code/weights. "
          "These are real, date-specific public API model listings; offline operation requires different local weights. "
          "NOX credentials are not stored. No API calls to paid models.\n")
    (ROOT/"SERVICE_README.txt").write_text(desc)
    report["files"]=[{"file":str(p.relative_to(ROOT)),"bytes":p.stat().st_size,"sha256":hexsha(p)} for p in sorted(ROOT.glob("*")) if p.is_file()]
    report["free_model_count"]=len(free)
    report["status"]="SERVICE_REFERENCE_VERIFIED_NOT_INSTALLABLE"
def main():
    target=os.getenv("TARGET","").strip()
    if target not in TARGETS:raise SystemExit("Invalid target "+target)
    config=TARGETS[target]
    report={"catalog_number":config["id"],"name":config["name"],"target":target,"kind":config["kind"],
            "policy":"NONDESTRUCTIVE; no installation, production/NOX weights/S03/training untouched",
            "created_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),"status":"FAILED"}
    try:
        if config["kind"]=="github":github_snapshot(config,report)
        elif config["kind"]=="hf":hf_snapshot(config,report)
        else:openrouter_service(config,report)
    except Exception as ex:
        report["error"]=type(ex).__name__+": "+str(ex)
        print(traceback.format_exc(),file=sys.stderr)
    finally:
        (ROOT/"RESULTS.json").write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n")
        print("NOX_CATALOG_FINAL_RESULT",json.dumps({k:report.get(k) for k in ("catalog_number","name","status","error","revision","total_file_bytes")},ensure_ascii=False),flush=True)
    if report["status"]=="FAILED":return 1
    return 0
if __name__=="__main__":sys.exit(main())
