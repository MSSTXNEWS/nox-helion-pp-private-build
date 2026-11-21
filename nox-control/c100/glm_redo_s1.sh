#!/bin/bash
# 2A03 source-only: resume only missing/bad shards. No broad pkill and no
# publication or success receipt until all 11 exact HF LFS hashes match.
set -euo pipefail
umask 077
mkdir -p /root/nox/logs
exec 9>/root/nox/logs/redo.launch.lock
flock -n 9 || { echo HOLD_REDO_LAUNCHER_BUSY; exit 75; }
if pgrep -f '^python3 /root/nox/redo_worker.py$' >/dev/null; then
    echo HOLD_REDO_WORKER_ACTIVE
    exit 75
fi
cat > /root/nox/redo_worker.py <<'W'
import fcntl, hashlib, json, os, re, subprocess, sys, urllib.request
from concurrent.futures import ThreadPoolExecutor

API = "https://huggingface.co/api/models/unsloth/GLM-5.3-GGUF/tree/main/UD-Q4_K_XL"
BASE = "https://huggingface.co/unsloth/GLM-5.3-GGUF/resolve/main/UD-Q4_K_XL/"
ROOT = "/root/nox/glm53"
RUN_ID = os.environ.get("NOX_GGUF_RUN_ID", "")
if re.fullmatch(r"[0-9]{8}T[0-9]{6}Z-[0-9]+", RUN_ID) is None:
    print("HOLD_GGUF_RUN_ID", flush=True)
    sys.exit(2)
PATTERN = re.compile(r"^GLM-5\.3-UD-Q4_K_XL-(\d{5})-of-00011\.gguf$")
os.makedirs("/root/nox/logs", exist_ok=True)
lock = open("/root/nox/logs/redo.worker.lock", "a")
try:
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
    print("HOLD_REDO_WORKER_ACTIVE", flush=True)
    sys.exit(75)

def sha(path):
    digest = hashlib.sha256()
    with open(path, "rb") as fp:
        for chunk in iter(lambda: fp.read(8 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()

def place(name):
    index = int(PATTERN.fullmatch(name).group(1))
    return "/dev/shm/nox_glm" if index <= 9 else "/root/nox/glm53_disk"

def verified(path, size, oid):
    return (os.path.isfile(path) and not os.path.islink(path)
            and os.path.getsize(path) == size and sha(path) == oid)

try:
    with urllib.request.urlopen(API, timeout=25) as response:
        rows = json.load(response)
    if not isinstance(rows, list):
        raise ValueError("metadata_shape")
    meta = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = os.path.basename(str(row.get("path", "")))
        match = PATTERN.fullmatch(name)
        if not match:
            continue
        index = int(match.group(1))
        size = row.get("size")
        oid = str((row.get("lfs") or {}).get("oid", "")).removeprefix("sha256:")
        if (name in meta or index < 1 or index > 11
                or type(size) is not int or size <= 0
                or re.fullmatch(r"[0-9a-f]{64}", oid) is None):
            raise ValueError("metadata_invalid")
        meta[name] = (size, oid)
    names = sorted(meta)
    if len(names) != 11 or [int(PATTERN.fullmatch(n).group(1)) for n in names] != list(range(1, 12)):
        raise ValueError("metadata_not_exact_11")
except Exception as exc:
    print("HOLD_GGUF_METADATA_" + type(exc).__name__, flush=True)
    sys.exit(2)

def cgroup_admitted():
    try:
        with open("/sys/fs/cgroup/memory.max") as fp:
            upper = fp.read().strip()
        with open("/sys/fs/cgroup/memory.current") as fp:
            current = int(fp.read().strip())
        return upper != "max" and int(upper) - current >= (2 << 30)
    except (OSError, ValueError):
        return False

def one(name):
    size, oid = meta[name]
    directory = place(name)
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, name)
    stage_dir = os.path.join(directory, ".nox_verified", RUN_ID)
    os.makedirs(stage_dir, exist_ok=True)
    staged = os.path.join(stage_dir, name)
    part = staged + ".part"
    if any(os.path.islink(p) for p in (path, staged, part)):
        print(name, "HOLD_SYMLINK", flush=True)
        return False
    if verified(path, size, oid):
        print(name, "SHA_OK_EXISTING", flush=True)
        return path
    if verified(staged, size, oid):
        print(name, "SHA_OK_STAGED", flush=True)
        return staged
    if os.path.isfile(part) and os.path.getsize(part) >= size:
        # A same-size but wrong-hash partial cannot be resumed. Never touch
        # the live shard; only discard our own unverified temporary download.
        if not verified(part, size, oid):
            os.remove(part)
    for attempt in range(3):
        if not cgroup_admitted():
            print(name, "HOLD_CGROUP_RESERVE", flush=True)
            return False
        if verified(part, size, oid):
            os.replace(part, staged)
            print(name, "SHA_OK_REPLACED", flush=True)
            return staged
        prior = os.path.getsize(part) if os.path.isfile(part) else 0
        reserve = os.statvfs(directory)
        free = reserve.f_bavail * reserve.f_frsize
        if free < max(0, size - prior) + (2 << 30):
            print(name, "HOLD_DISK_RESERVE", flush=True)
            return False
        try:
            result = subprocess.run(
                ["curl", "-fsSL", "-C", "-", "--retry", "3", "--retry-all-errors",
                 "--connect-timeout", "30", "-o", part, BASE + name],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=3600, check=False)
        except subprocess.TimeoutExpired:
            print(name, "HOLD_DOWNLOAD_TIMEOUT", flush=True)
            return False
        if result.returncode != 0:
            print(name, "RETRY_DOWNLOAD", attempt + 1, flush=True)
        if os.path.isfile(part) and os.path.getsize(part) == size and not verified(part, size, oid):
            os.remove(part)
    if verified(part, size, oid):
        os.replace(part, staged)
        print(name, "SHA_OK_REPLACED", flush=True)
        return staged
    print(name, "HOLD_SHA_OR_DOWNLOAD", flush=True)
    return False

with ThreadPoolExecutor(max_workers=2) as executor:
    results = list(executor.map(one, names))
if not all(results):
    print("HOLD_GGUF_NOT_ALL_VERIFIED", sum(results), "of", len(names), flush=True)
    sys.exit(3)

# The complete verified generation is staged, but the live S1 directory
# and files are untouched. Owner-pinned lease/CAS and active-reader checks
# must authorize a later one-pointer atomic publish. Do not claim completion.
versions = "/root/nox/glm53_verified_sets"
os.makedirs(versions, exist_ok=True)
generation = os.path.join(versions, RUN_ID)
os.mkdir(generation)
for name, target in zip(names, results):
    os.symlink(target, os.path.join(generation, name))
receipt = {
    "state": "ALL_11_SHA_VERIFIED_STAGED_HOLD_OWNER_CAS",
    "manifest_sha256": hashlib.sha256(
        json.dumps(meta, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest(),
    "shard_count": 11,
    "verified": {name: meta[name][1] for name in names},
    "generation_path": generation,
    "live_root_untouched": ROOT,
    "native_relay35_acceptance": False,
    "run_id": RUN_ID
}
target_receipt = "/root/nox/logs/redo_sha_receipt-" + RUN_ID + ".json"
temp_receipt = target_receipt + ".tmp"
with open(temp_receipt, "w") as output:
    json.dump(receipt, output, sort_keys=True)
    output.flush()
    os.fsync(output.fileno())
os.replace(temp_receipt, target_receipt)
print("HOLD_GGUF_OWNER_CAS_PUBLICATION", receipt["manifest_sha256"], flush=True)
sys.exit(75)
W
# This only submits a background transfer. A terminal result requires an
# independent read of the unique run-scoped receipt, not this launcher exit.
run_id="$(date -u '+%Y%m%dT%H%M%SZ')-$$"
NOX_GGUF_RUN_ID="$run_id" nohup setsid bash -c 'exec 9>&-; python3 /root/nox/redo_worker.py' > /root/nox/logs/redo.log 2>&1 < /dev/null &
worker_pid=$!
echo "PENDING_GGUF_SHA worker_pid=$worker_pid expected_receipt=/root/nox/logs/redo_sha_receipt-$run_id.json"
