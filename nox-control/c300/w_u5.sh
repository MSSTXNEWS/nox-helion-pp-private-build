echo "C300: w_u5"
for u in vendor/deep-chat/deep-chat.iife.js nox-u-pad.js nox-dc-live.js nox-dc.js; do for h in 18091 8091; do echo -n "$h $u: "; curl -s -o /dev/null -m25 -w '%{http_code} %{size_download}B ttfb=%{time_starttransfer}s total=%{time_total}s\n' -H 'Accept-Encoding: gzip' http://127.0.0.1:$h/web/$u; done; done
ls -l /workspace/nox/web/site/vendor/deep-chat/deep-chat.iife.js | awk '{print $5}'
echo -n "8091 parallel x6: "; for i in 1 2 3 4 5 6; do (curl -s -o /dev/null -m25 -w '%{time_total} ' http://127.0.0.1:8091/web/vendor/deep-chat/deep-chat.iife.js) & done; wait; echo
uptime; ps -eo pid,pcpu,etime,cmd --sort=-pcpu | head -6 | cut -c1-110
