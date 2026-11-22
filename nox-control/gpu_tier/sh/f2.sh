echo "== F2 download v5"
mkdir -p /root/nox/in_v5; cd /root/nox/in_v5
pip install -q -U gdown 2>&1 | tail -1
if ! pgrep -f "gdown --folder" >/dev/null; then nohup setsid gdown --folder 1k1JSVnIDAsHFGiTiMAUJfyZjBJS3v1Na -O /root/nox/in_v5 > /root/nox/logs/gdown_v5.log 2>&1 < /dev/null & fi
sleep 100
tail -n 5 /root/nox/logs/gdown_v5.log | cut -c1-200; find /root/nox/in_v5 -type f | head -30 | xargs -r ls -l | awk '{print $5,$9}'
