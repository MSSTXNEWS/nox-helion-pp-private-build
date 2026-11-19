#!/usr/bin/env python3
"""NOX V30: recover TWO oversized official registry distributions.

NPM promptfoo and PyPI pydantic-ai. Original full Git repositories are not
claimed, and packages are not executed/installed. Verify official metadata
registry SHA512 or SHA256, ZIP/TAR structure and provide complete provenance.
"""
from __future__ import annotations
import urllib.request, urllib.parse, hashlib, base64, json, pathlib, tarfile, zipfile, datetime, shutil
ROOT=pathlib.Path("NOX_V30_OFFICIAL_REGISTRY_DISTRIBUTIONS")
ROOT.mkdir(parents=True,exist_ok=True)
MAX_BYTES=95_000_000
records=[]

def request(url):
    return urllib.request.Request(url,headers={"User-Agent":"NOX-v30-verified-public-package-mirror/2026-11-13","Accept":"application/json"})

def get_json(url):
    with urllib.request.urlopen(request(url),timeout=65) as r:return json.load(r)

def save(name,dist_url):
    dest=ROOT/name
    partial=ROOT/(name+".partial")
    n=0;h=hashlib.sha256();h512=hashlib.sha512()
    try:
        with urllib.request.urlopen(urllib.request.Request(dist_url,headers={
            "User-Agent":"NOX-v30-source-only-download/1.0"}),timeout=180) as r,partial.open("wb") as f:
            while True:
                b=r.read(1024*1024)
                if not b:break
                n+=len(b)
                if n>MAX_BYTES:raise ValueError("OFFICIAL_PACKAGE_OVER_95MB")
                f.write(b);h.update(b);h512.update(b)
        if n<1000:raise ValueError("TOO_SMALL")
        if not tarfile.is_tarfile(partial) and not zipfile.is_zipfile(partial):
            raise ValueError("NOT_ARCHIVE")
        if zipfile.is_zipfile(partial):
            with zipfile.ZipFile(partial) as z:
                if z.testzip():raise ValueError("ZIP_CRC_FAIL")
        else:
            with tarfile.open(partial,"r:*") as tar:
                members=tar.getmembers()
                if not members:raise ValueError("TAR_EMPTY")
                if any(pathlib.PurePosixPath(m.name).is_absolute() or ".." in pathlib.PurePosixPath(m.name).parts for m in members):
                    raise ValueError("TAR_UNSAFE_PATHS")
        partial.replace(dest)
        return {"name":name,"bytes":n,"sha256":h.hexdigest(),"sha512_base64":base64.b64encode(h512.digest()).decode()}
    finally:partial.unlink(missing_ok=True)

def npm():
    pkg="promptfoo"
    meta=get_json("https://registry.npmjs.org/"+pkg+"/latest")
    dist=meta["dist"]
    revision=meta["version"]
    name="promptfoo_npm_"+revision+".tgz"
    x=save(name,dist["tarball"])
    integrity=dist.get("integrity","")
    if not integrity.startswith("sha512-") or x["sha512_base64"]!=integrity.split("-",1)[1]:
        (ROOT/name).unlink(missing_ok=True)
        raise ValueError("NPM_SHA512_DIGEST_MISMATCH")
    records.append({"project":"promptfoo/promptfoo","kind":"OFFICIAL_NPM_DISTRIBUTION_NOT_FULL_GIT_TREE",
      "package":"promptfoo","version":revision,"artifact":name,"registry":"npm",
      "source_url":"https://registry.npmjs.org/"+pkg,"registry_integrity":integrity,
      "status":"DOWNLOADED_REGISTRY_INTEGRITY_VERIFIED","size_bytes":x["bytes"],"sha256":x["sha256"],
      "license_review_required":True,"installed":False,"executed":False})

def pypi():
    pkg="pydantic-ai"
    meta=get_json("https://pypi.org/pypi/"+pkg+"/json")
    options=[p for p in meta["urls"] if p["packagetype"]=="sdist" and not p.get("yanked")]
    if not options:raise RuntimeError("PYPI_SDIST_UNAVAILABLE")
    dist=options[0]
    name="pydantic-ai_PyPI_"+dist["filename"]
    x=save(name,dist["url"])
    if x["sha256"]!=dist["digests"]["sha256"]:
        (ROOT/name).unlink(missing_ok=True)
        raise ValueError("PYPI_SHA256_DIGEST_MISMATCH")
    records.append({"project":"pydantic/pydantic-ai","kind":"OFFICIAL_PYPI_SDIST_NOT_FULL_GIT_TREE",
      "package":pkg,"version":meta["info"]["version"],"artifact":name,"registry":"PyPI",
      "source_url":"https://pypi.org/project/"+pkg,"registry_sha256":dist["digests"]["sha256"],
      "status":"DOWNLOADED_REGISTRY_INTEGRITY_VERIFIED","size_bytes":x["bytes"],"sha256":x["sha256"],
      "license_review_required":True,"installed":False,"executed":False})
err=[]
for key,fn in (("promptfoo",npm),("pydantic-ai",pypi)):
    try:fn()
    except Exception as e:err.append({"package":key,"error":str(e)})
report={"schema":"nox-v30-oversized-source-registry-recovery-v1","date_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "sources":records,"holds":err,"downloaded":len(records),"requested":2,
        "source_only":True,"production_modified":False,"models_trained":False,
        "contains_full_git_repositories":False}
(ROOT/"RESULT.json").write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf8")
(ROOT/"SHA256SUMS.txt").write_text("".join(x["sha256"]+"  "+x["artifact"]+"\n" for x in records),encoding="utf8")
print(json.dumps(report,ensure_ascii=False),flush=True)
if err:raise SystemExit(2)
