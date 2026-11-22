#!/usr/bin/env bash
set -euo pipefail

mkdir -p /root/nox/logs
task=/tmp/nox_load_v6_20261122.sh
log=/root/nox/logs/load_v6_20261122.log

cat > "$task" <<'TASK'
#!/usr/bin/env bash
set -euo pipefail
mkdir -p /root/nox/in_v6
cd /root/nox/in_v6
pip install -q -U gdown
gdown 1zl20T5qy9A7tIU2GKTV1kIsCA1ahR2aj -O NOX_V7_BRAIN_v6.zip.part00.bin
gdown 1gYucZQr4VizHgxcmVuey7JflgK8Drpxr -O NOX_V7_BRAIN_v6.zip.part01.bin
cat NOX_V7_BRAIN_v6.zip.part00.bin NOX_V7_BRAIN_v6.zip.part01.bin > NOX_V7_BRAIN_v6_20261122.zip
echo "95b9effdf88d04b1d517aeaf3adca21860eceb29270eb68ebadeb4b995750a4a  NOX_V7_BRAIN_v6_20261122.zip" | sha256sum -c -
unzip -q -o NOX_V7_BRAIN_v6_20261122.zip -d /root/nox/v7_src_v6
ls /root/nox/v7_src_v6/nox_wow | head -50
df -h /root /dev/shm
free -g
TASK

chmod 700 "$task"
if pgrep -af '[n]ox_load_v6_20261122.sh' >/dev/null; then
  echo "load already running"
  pgrep -af '[n]ox_load_v6_20261122.sh' | tail -5
  exit 0
fi
nohup bash "$task" > "$log" 2>&1 < /dev/null &
echo "started pid=$! log=$log"
