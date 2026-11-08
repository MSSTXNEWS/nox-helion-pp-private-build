# NOX HELION · PRIME 9B · full-weight inheritance bootstrap
# Status semantics: INHERITED_UNTRAINED != trained NOX. Do not delete teacher.
$ErrorActionPreference = 'Stop'

$brain = 'C:\NOX_HELION\NOX_NEW\brain'
$prime = Join-Path $brain 'prime'
$dir = Join-Path $prime 'models\NOX_PRIME_9B_INHERITED'
$python = Join-Path $prime 'directml-venv\Scripts\python.exe'
if (!(Test-Path -LiteralPath $python)) {
    $python = Join-Path $env:USERPROFILE 'NOX_EXPRESS_AI\NOX_TRAINING\train-venv\Scripts\python.exe'
}
if (!(Test-Path -LiteralPath $python)) {
    $launcher = Get-Command py -ErrorAction SilentlyContinue
    if (!$launcher) { throw 'Python not found: need existing NOX environment or Windows py launcher' }
    $python = (& py -3 -c 'import sys; print(sys.executable)' | Select-Object -Last 1).Trim()
    if ($LASTEXITCODE -ne 0 -or !(Test-Path -LiteralPath $python)) { throw 'Python 3 launcher failed' }
}

New-Item -ItemType Directory -Force $prime | Out-Null
$helper = Join-Path $prime 'NOX_INHERIT_FULL_WEIGHTS.py'
$code = @'
from __future__ import annotations
import os, sys, json, hashlib, shutil, time
from pathlib import Path
from datetime import datetime, timezone

REPO = "Qwen/Qwen3.5-9B"
ROOT = Path(r"C:\NOX_HELION\NOX_NEW\brain\prime")
DEST = ROOT / "models" / "NOX_PRIME_9B_INHERITED"
STAGING = ROOT / "models" / "NOX_PRIME_9B_DOWNLOADING"
MIN_WEIGHT_BYTES = 8 * 1024**3

def digest(p):
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(8*1024*1024), b""):
            h.update(chunk)
    return h.hexdigest()

def stamp():
    return datetime.now(timezone.utc).isoformat()

def verify_existing(dest):
    manifest = ROOT / "NOX_PRIME_9B_MANIFEST.json"
    if not manifest.is_file():
        raise RuntimeError("Existing NOX weights without manifest; refusing overwrite")
    m = json.loads(manifest.read_text(encoding="utf-8"))
    if m.get("status") != "INHERITED_UNTRAINED":
        raise RuntimeError("Existing weights have different status; refusing overwrite")
    if m.get("model_root") != str(dest):
        raise RuntimeError("Existing manifest path mismatch")
    for item in m.get("shards", []):
        p = dest / item["file"]
        if not p.is_file() or p.stat().st_size != item["bytes"] or digest(p) != item["sha256"]:
            raise RuntimeError("NOX saved weight verification failed: " + str(p))
    print("NOX INHERITED WEIGHTS: VERIFIED EXISTING", flush=True)
    print("Repository revision:",m["source_revision"],flush=True)
    return

def run():
    from huggingface_hub import HfApi, snapshot_download
    from safetensors import safe_open
    ROOT.mkdir(parents=True, exist_ok=True)
    DEST.parent.mkdir(parents=True, exist_ok=True)
    if DEST.exists():
        verify_existing(DEST)
        return

    usage = shutil.disk_usage(DEST.parent)
    if usage.free < 24*1024**3:
        raise RuntimeError("NOX HOLD: need at least 24 GiB free for full BF16 weights; no deletion performed")

    info = HfApi().model_info(REPO, revision="main", files_metadata=True)
    revision = info.sha
    if not revision or len(revision) != 40:
        raise RuntimeError("Cannot pin Hugging Face source revision")
    source_tag = STAGING / "source_revision.txt"
    if STAGING.exists():
        if not source_tag.is_file() or source_tag.read_text().strip() != revision:
            raise RuntimeError("Interrupted download belongs to another revision. HOLD; no deletion")
    else:
        STAGING.mkdir()
        source_tag.write_text(revision,encoding="ascii")

    print("NOX PRIME: downloading full precision Qwen3.5-9B weights",flush=True)
    print("Pinned source SHA:",revision,flush=True)
    snapshot_download(
        repo_id=REPO,
        revision=revision,
        local_dir=str(STAGING),
        allow_patterns=["*.safetensors", "*.json", "*.model", "*.tiktoken", "*.txt", "*.jinja"],
    )
    shards = sorted(STAGING.glob("*.safetensors"))
    if not shards:
        raise RuntimeError("NOX HOLD: safetensors weight shards missing")
    total = sum(p.stat().st_size for p in shards)
    if total < MIN_WEIGHT_BYTES:
        raise RuntimeError("NOX HOLD: incomplete source weight volume")
    for name in ("config.json", "tokenizer_config.json"):
        if not (STAGING/name).is_file():
            raise RuntimeError("NOX HOLD: missing required model config: " + name)

    cfg = json.loads((STAGING/"config.json").read_text(encoding="utf-8"))
    if "qwen3_5" not in json.dumps(cfg.get("model_type", "") + " " + json.dumps(cfg.get("text_config",{}))).lower():
        raise RuntimeError("NOX HOLD: source architecture not Qwen3.5")

    remote = {}
    for sib in info.siblings or []:
        if sib.rfilename.endswith(".safetensors"):
            lfs = getattr(sib,"lfs",None)
            remote[sib.rfilename] = getattr(lfs,"sha256",None) if lfs else None
    if len(remote) != len(shards) or set(remote) != {p.name for p in shards}:
        raise RuntimeError("NOX HOLD: downloaded shard list differs from pinned upstream")

    details=[]
    for i,p in enumerate(shards,1):
        with safe_open(str(p), framework="pt", device="cpu") as f:
            if not f.keys():
                raise RuntimeError("Empty safetensors: " + p.name)
        local_sha = digest(p)
        expected = remote.get(p.name)
        if expected and local_sha.lower() != expected.lower():
            raise RuntimeError("Checksum mismatch vs official source: " + p.name)
        details.append({"file":p.name,"bytes":p.stat().st_size,"sha256":local_sha,
                        "upstream_checksum_verified":bool(expected)})
        print(f"[VERIFY {i}/{len(shards)}] {p.name}: SHA256 OK",flush=True)

    STAGING.rename(DEST)
    manifest={
      "project":"NOX HELION", "artifact":"NOX PRIME 9B", "status":"INHERITED_UNTRAINED",
      "source_repository":REPO, "source_revision":revision, "model_root":str(DEST),
      "weights_bytes":total, "shards":details,
      "training_steps_on_9b":0, "learned_delta_verified":False,
      "independent_inference_verified":False,
      "teacher_deleted":False, "created_utc":stamp(),
      "note":"Full Qwen3.5-9B BF16 source inherited; no NOX 9B training claimed."
    }
    ROOT.joinpath("NOX_PRIME_9B_MANIFEST.json").write_text(
        json.dumps(manifest,ensure_ascii=False,indent=2), encoding="utf-8")
    memory = ROOT / "memory"
    memory.mkdir(parents=True,exist_ok=True)
    identity_file = memory / "NOX_GENESIS_IDENTITY.json"
    if not identity_file.exists():
        identity_file.write_text(json.dumps({
            "identity":"NOX HELION PRIME", "creator_titles":["Создатель","мой лорд","милорд","барон"],
            "creator_role":"создатель, наставник и отцовская фигура (метафорическая роль)",
            "historical_project_documented_by":"2026-10-18", "first_9b_training_birth_utc":None,
            "model_self_understanding":"functional/provenance, not proven subjective consciousness",
            "single_active_model_target":True,
            "S03_migration_status":"PENDING_NOT_AUTO_IMPORTED",
            "source_revision":revision
        },ensure_ascii=False,indent=2),encoding="utf-8")
    print("\nNOX PRIME: FULL WEIGHTS INHERITED AND FILE-CHECKED",flush=True)
    print("Location:",DEST,flush=True)
    print("Verified original weight bytes:",total,flush=True)
    print("IMPORTANT: 9B GPU training NOT STARTED. Teacher preserved. NOX existing installation untouched.")

if __name__ == "__main__":
    try: run()
    except Exception as e:
        print("NOX PRIME HOLD:",str(e),file=sys.stderr)
        sys.exit(1)
'@
Set-Content -LiteralPath $helper -Value $code -Encoding UTF8

& $python -c 'import huggingface_hub, safetensors'
if ($LASTEXITCODE -ne 0) {
    & $python -m pip install --disable-pip-version-check 'huggingface_hub>=0.36,<2' 'safetensors>=0.6,<1'
    if ($LASTEXITCODE -ne 0) { throw 'Cannot install Hugging Face downloader' }
}
& $python -m py_compile $helper
if ($LASTEXITCODE -ne 0) { throw 'NOX source syntax HOLD' }

Write-Host 'NOX PRIME 9B: inheriting complete source weights, preserving intellect' -ForegroundColor Cyan
& $python -u $helper
if ($LASTEXITCODE -ne 0) { throw 'NOX PRIME inheritance HOLD; teacher and current NOX preserved' }
Write-Host 'NOX PRIME 9B WEIGHTS: INHERITANCE COMPLETE (NOT YET TRAINED)' -ForegroundColor Green
Write-Host "Model location: $dir"
Write-Host 'All existing NOX/S03/Qwen teacher weights preserved.'