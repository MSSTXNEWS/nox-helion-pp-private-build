echo "K1: l1_rc3"
W=/workspace/nox/web/pkg/server
sed -n 160,265p $W/chat_core.py | cut -c1-220
echo ====; sed -n 326,341p $W/chat_core.py | cut -c1-300; sed -n 411,430p $W/chat_core.py | cut -c1-300
echo ==== core; sed -n 694,747p $W/chat_core.py | cut -c1-220
echo == 8105; ps aux | grep llama-server | grep -v grep | sed -E 's/--(api-key|key)[ =][^ ]+/--key X/g' | cut -c1-330
curl -s -m 3 http://127.0.0.1:8105/health; echo; curl -s -m 3 http://127.0.0.1:8104/slots | head -c 900
echo; echo == df; df -h /workspace /; du -sh /workspace/* 2>/dev/null | sort -h | tail -8
ls /workspace/nox/state | grep -E "disk_low|flag"; cat /workspace/nox/state/disk_low.flag 2>/dev/null
echo == restic; ls /workspace/nox/backup* 2>/dev/null | head; grep -rl restic /workspace/nox/ops 2>/dev/null | head -5
echo == crontab count; crontab -l 2>/dev/null | grep -v '^#' | grep -v '^$' | wc -l
echo == gwj; ls /workspace/nox/state | grep -i gw_journal; tail -5 /workspace/nox/state/gw_journal* 2>/dev/null | cut -c1-300
