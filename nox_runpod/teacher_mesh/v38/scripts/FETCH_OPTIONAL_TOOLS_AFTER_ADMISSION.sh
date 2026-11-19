#!/usr/bin/env bash
set -euo pipefail
# Download into a side-cache only after owner approval, no installation.
if [ "${NOX_ALLOW_OPTIONAL_DOWNLOAD:-NO}" != YES ]; then
 echo 'HOLD_OWNER_APPROVAL: export NOX_ALLOW_OPTIONAL_DOWNLOAD=YES' >&2;exit 5
fi
free_bytes=$(df -PB1 /workspace 2>/dev/null | awk 'NR==2{print $4}')
if [ -z "$free_bytes" ] || [ "$free_bytes" -lt 20000000000 ]; then
 echo 'HOLD_DISK_LT_20GB: no new downloads on near-full NOX disk' >&2;exit 6
fi
if ! command -v python3 >/dev/null || ! python3 -m pip --version >/dev/null; then
 echo 'HOLD_PYTHON_PIP_UNAVAILABLE' >&2;exit 7
fi
base=/workspace/nox_v38_optional_wheels
mkdir -p "$base"
# Source URLs are the regular configured index; no execution or installation.
python3 -m pip download --no-deps --dest "$base" 'psutil>=5.9,<9' 'prometheus_client>=0.20,<1' 'watchdog>=4,<7'
find "$base" -maxdepth 1 -type f -printf '%f %s bytes\n'
echo 'DOWNLOADED_TO_ISOLATED_CACHE_ONLY - NOT_INSTALLED'
