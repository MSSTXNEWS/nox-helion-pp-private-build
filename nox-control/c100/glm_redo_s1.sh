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

def one(name):
    size, oid = meta[name]
    directory = place(name)
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, name)
    part = path + ".verified-download.part"
    if os.path.islink(path) or os.path.islink(part):
        print(name, "HOLD_SYMLINK", flush=True)
        return False
    if verified(path, size, oid):
        print(name, "SHA_OK_EXISTING", flush=True)
        return True
    if os.path.isfile(part) and os.path.getsize(part) >= size:
        # A same-size but wrong-hash partial cannot be resumed. Never touch
        # the live shard; only discard our own unverified temporary download.
        if not verified(part, size, oid):
            os.remove(part)
    for attempt in range(3):
        if verified(part, size, oid):
            os.replace(part, path)
            print(name, "SHA_OK_REPLACED", flush=True)
            return True
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
        os.replace(part, path)
        print(name, "SHA_OK_REPLACED", flush=True)
        return True
    print(name, "HOLD_SHA_OR_DOWNLOAD", flush=True)
    return False

with ThreadPoolExecutor(max_workers=2) as executor:
    results = list(executor.map(one, names))
if not all(results):
    print("HOLD_GGUF_NOT_ALL_VERIFIED", sum(results), "of", len(names), flush=True)
    sys.exit(3)

# Publication is deferred until all 11 exact-size+SHA checks have succeeded.
# The existing live shard targets are never modified on a failed generation.
os.makedirs(ROOT, exist_ok=True)
for name in names:
    link = os.path.join(ROOT, name)
    temp = link + ".verified-link.tmp"
    if os.path.lexists(temp):
        os.remove(temp)
    os.symlink(os.path.join(place(name), name), temp)
    os.replace(temp, link)
receipt = {
    "state": "ALL_11_SHARDS_SHA_VERIFIED",
    "manifest_sha256": hashlib.sha256(
        json.dumps(meta, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest(),
    "shard_count": 11,
    "verified": {name: meta[name][1] for name in names},
    "native_relay35_acceptance": False
}
temp_receipt = "/root/nox/logs/redo_sha_receipt.json.tmp"
with open(temp_receipt, "w") as output:
    json.dump(receipt, output, sort_keys=True)
    output.flush()
    os.fsync(output.fileno())
os.replace(temp_receipt, "/root/nox/logs/redo_sha_receipt.json")
print("ALL_11_SHA_VERIFIED_SOURCE_WORKER", receipt["manifest_sha256"], flush=True)
W
# This only submits a background transfer. A terminal result requires an
# independent read of redo_sha_receipt.json, not this launcher exit code.
nohup setsid bash -c 'exec 9>&-; python3 /root/nox/redo_worker.py' > /root/nox/logs/redo.log 2>&1 < /dev/null &
worker_pid=$!
echo "PENDING_GGUF_SHA worker_pid=$worker_pid; terminal receipt NOT YET VERIFIED"
