"""Read-only Windows foundation diagnostic; never install or attest release."""
import json,platform,sqlite3,shutil,subprocess
from pathlib import Path
from urllib.request import Request,build_opener,ProxyHandler
from importlib.metadata import version,PackageNotFoundError

def inspect(data_dir=None):
    models=[];ollama="UNAVAILABLE"
    try:
        with build_opener(ProxyHandler({})).open(Request("http://127.0.0.1:11434/api/tags"),timeout=3) as resp:
            raw=resp.read(131073)
        if len(raw)>131072:raise ValueError("OLLAMA_BODY_LIMIT")
        doc=json.loads(raw)
        if not isinstance(doc.get("models"),list):raise ValueError("MODELS_SCHEMA")
        models=sorted({m["name"] for m in doc["models"][:128] if isinstance(m,dict) and isinstance(m.get("name"),str)})
        ollama="LOCAL_MODELS_OBSERVED" if models else "LOCAL_EMPTY"
    except (OSError,ValueError,KeyError,TypeError):pass
    db="NOT_CONFIGURED";jobs=0
    if data_dir is not None:
        data=Path(data_dir);file=data/"helion.sqlite3"
        db="NOT_FOUND"
        if file.is_file():
            try:
                with sqlite3.connect(file.as_uri()+"?mode=ro",uri=True,timeout=2) as conn:
                    conn.execute("SELECT name FROM sqlite_master LIMIT 1").fetchall()
                db="READONLY_OK_NOT_WRITE_TESTED"
            except sqlite3.Error:db="READ_FAILED"
        cfg=data/"onehost-native-config.json"
        if cfg.is_file() and cfg.stat().st_size<=65536:
            try:
                x=json.loads(cfg.read_text("utf-8"))
                if x.get("version")==1 and isinstance(x.get("forge_jobs"),list):jobs=len(x["forge_jobs"])
            except (ValueError,OSError,TypeError):pass
    packages={}
    for pkg in ("torch","transformers","peft","accelerate","trl","bitsandbytes","datasets","safetensors"):
        try:packages[pkg]=version(pkg)
        except PackageNotFoundError:packages[pkg]=None
    gpu="WINDOWS_HOST_REQUIRED"
    if platform.system()=="Windows":
        gpu="NVIDIA_SMI_NOT_FOUND"
        exe=shutil.which("nvidia-smi")
        if exe:
            try:
                p=subprocess.run([exe,"--query-gpu=name,memory.total","--format=csv,noheader"],capture_output=True,text=True,timeout=8)
                gpu="HARDWARE_OBSERVED_NOT_CUDA_PROOF" if p.returncode==0 and p.stdout.strip() else "TELEMETRY_HOLD"
            except (OSError,subprocess.TimeoutExpired):gpu="TELEMETRY_HOLD"
    return {"schema":"NOX-FOUNDATION-READONLY-v1","ollama":ollama,"model_tags":models,
        "s03":db,"p04_job_count":jobs,"installed_package_versions":packages,
        "gpu":gpu,"model_sha_and_license_approved":False,"training_verified":False,
        "installed_exe_e07":False}

if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser();p.add_argument("--data-dir")
    print(json.dumps(inspect(p.parse_args().data_dir),ensure_ascii=False,indent=2))
