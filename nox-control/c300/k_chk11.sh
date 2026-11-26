echo "C300: k_chk11"
uptime; free -g | head -2; df -h /workspace | tail -1
for u in /web/chat-dc.html /web/index.html /api/nox/status; do curl -s -m 20 -o /dev/null -w "18091$u %{http_code} %{time_total}s\n" http://127.0.0.1:18091$u; done
curl -s -m 20 -o /dev/null -w "8091 chat-dc %{http_code} %{time_total}s\n" http://127.0.0.1:8091/web/chat-dc.html
curl -s -m 10 http://127.0.0.1:8104/health; echo
ps -eo pid,etimes,pcpu,rss,args --sort=-pcpu | head -12 | cut -c1-150
ps -eo pid,etimes,args | grep -E "[r]v_audit|[r]v_chat|[c]hain5|[q]uant4|[t]eacher_dump" | cut -c1-150
ls /workspace/nox/STOP 2>/dev/null && echo STOP_SET
tail -5 /workspace/nox/ops/dpo/run5.log 2>/dev/null | cut -c1-160
