#!/usr/bin/env python3
"""NOX final source acquisition: official SDKs for hosted OpenRouter and Rive JS runtimes.
Never installs or executes upstream files, never accesses production or checkpoints.
"""
import base64, datetime, hashlib, json, os, pathlib, tarfile, time, urllib.parse, urllib.request, zipfile
ROOT=pathlib.Path("NOX_MASTER_CATALOG_FINAL_REGISTRY_DISTRIBUTIONS")
FILES=ROOT/"sources"
FILES.mkdir(parents=True,exist_ok=True)
records=[]
def req(url, accept=None):
    headers={"User-Agent":"NOX-CATALOG-REAL-UPSTREAM/2026-11-12"}
    if accept:headers["Accept"]=accept
    return urllib.request.Request(url,headers=headers)
def fetch_json(url):
    with urllib.request.urlopen(req(url,"application/json"),timeout=40) as r:
        return json.load(r)
def download(url,target,limit=95_000_000):
    p=target.with_name(target.name+".partial")
    h=hashlib.sha256();h512=hashlib.sha512();n=0
    try:
        with urllib.request.urlopen(req(url),timeout=150) as res, p.open("wb") as f:
            while True:
                block=res.read(1024*1024)
                if not block:break
                n+=len(block)
                if n>limit:raise ValueError("Download above 95MB limit")
                h.update(block);h512.update(block);f.write(block)
        if n<100:raise ValueError("Truncated package")
        if tarfile.is_tarfile(p):
            with tarfile.open(p,"r:*") as tar:
                if not tar.getmembers():raise ValueError("Empty tar archive")
        elif zipfile.is_zipfile(p):
            with zipfile.ZipFile(p) as z:
                if z.testzip():raise ValueError("Broken ZIP file")
        else:raise ValueError("Not an archive")
        p.replace(target)
        return {"bytes":n,"sha256":h.hexdigest(),"sha512_base64":base64.b64encode(h512.digest()).decode()}
    finally:p.unlink(missing_ok=True)
def npm(package, prefix, catalog_number):
    encoded=urllib.parse.quote(package,safe="@")
    meta=fetch_json("https://registry.npmjs.org/"+encoded+"/latest")
    ver=meta["version"];dist=meta["dist"]
    suffix=prefix+"_"+ver.replace("/","_")+".tgz"
    result={"catalog_number":catalog_number,"package":package,"registry":"npm",
            "version":ver,"url":dist["tarball"],"artifact":f"sources/{suffix}","status":"FAILED"}
    try:
        dl=download(dist["tarball"],FILES/suffix)
        integrity=dist.get("integrity")
        if not integrity or not integrity.startswith("sha512-"):
            raise ValueError("NPM registry SHA512 integrity missing")
        if dl["sha512_base64"]!=integrity.split("-",1)[1]:
            (FILES/suffix).unlink(missing_ok=True)
            raise ValueError("NPM SHA512 mismatch")
        result.update(bytes=dl["bytes"],sha256=dl["sha256"],registry_integrity=integrity,status="DOWNLOADED_VERIFIED")
    except Exception as e:
        result["error"]=str(e)
    records.append(result)
def pypi(package,prefix,catalog_number):
    meta=fetch_json("https://pypi.org/pypi/"+urllib.parse.quote(package)+"/json")
    choices=[p for p in meta["urls"] if p["packagetype"]=="sdist" and not p.get("yanked")]
    if not choices:choices=[p for p in meta["urls"] if p["packagetype"]=="bdist_wheel" and not p.get("yanked")]
    if not choices:raise RuntimeError("No PyPI distribution for "+package)
    pkg=choices[0];url=pkg["url"]
    name=prefix+"_"+pkg["filename"]
    result={"catalog_number":catalog_number,"package":package,"registry":"PyPI",
            "version":meta["info"]["version"],"url":url,"artifact":f"sources/{name}","status":"FAILED"}
    try:
        dl=download(url,FILES/name)
        expected=pkg["digests"]["sha256"]
        if dl["sha256"]!=expected:
            (FILES/name).unlink(missing_ok=True)
            raise ValueError("PyPI SHA256 mismatch")
        result.update(bytes=dl["bytes"],sha256=dl["sha256"],registry_sha256=expected,status="DOWNLOADED_VERIFIED")
    except Exception as e:result["error"]=str(e)
    records.append(result)
pypi("openrouter","006_python_openrouter",6)
npm("@openrouter/sdk","006_typescript_openrouter_sdk",6)
npm("@rive-app/canvas","115_rive_canvas",115)
npm("@rive-app/react-canvas","115_rive_react_canvas",115)
report={"schema":"nox-real-source-completion-registry-v1",
        "purpose":"Official distributed SDKs. OpenRouter is a hosted service, not downloadable weights or server",
        "source_repo":"MSSTXNEWS/nox-helion-pp-private-build",
        "produced_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "status":"PASS" if all(r["status"]=="DOWNLOADED_VERIFIED" for r in records) else "FAIL",
        "packages":records,
        "policy":"INTEGRATION_CANDIDATE_NOT_INSTALLED; no NOX production, GPU training, S03 or checkpoints altered"}
(ROOT/"AUDIT.json").write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
(ROOT/"SHA256SUMS.txt").write_text("".join(f'{r["sha256"]}  {r["artifact"]}\n' for r in records if r["status"]=="DOWNLOADED_VERIFIED"),encoding="utf-8")
(ROOT/"README_RU.txt").write_text(
    "NOX MASTER CATALOG: реальные официальные дистрибутивы OpenRouter Python/TypeScript SDK и Rive JS Canvas/React Canvas.\n"
    "OpenRouter — облачный сервис; на компьютер скачиваются SDK, но не сам сервис или его модели.\n"
    "Rive — JS runtime packages из npm. До интеграции проверить лицензии и совместимость.\n"
    "Статус: СКАЧАНО, но НЕ УСТАНОВЛЕНО. Отчёт AUDIT.json, SHA256SUMS.txt.\n",encoding="utf-8")
for r in records:print("REGISTRY",r["catalog_number"],r["package"],r["status"],r.get("bytes",0),r.get("error",""),flush=True)
if report["status"]!="PASS":raise SystemExit(1)
