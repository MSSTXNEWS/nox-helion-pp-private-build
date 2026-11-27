echo "K1: ln_p1"
export RUNNER_TRACKING_ID=""
N=/workspace/nox; R=$N/web/pkg/webroot
c(){ curl -s -m ${3:-8} -o /dev/null -w "$1 %{http_code} %{time_total}s\n" "127.0.0.1:$2$1"; }
echo "== pages"; bad=0; tot=0
for f in $(cd $R; ls *.html); do o=$(curl -s -m 8 -o /dev/null -w "%{http_code}" 127.0.0.1:8091/web/$f); tot=$((tot+1)); [ "$o" = 200 ] || { echo "web/$f $o"; bad=$((bad+1)); }; done; echo "pages total=$tot bad=$bad"
echo "== mini-chat on pages"; n=0; m=0; for f in $(cd $R; ls *.html); do n=$((n+1)); grep -qiE "mini-?chat|nox-mini|noxMini" $R/$f && m=$((m+1)); done; echo "with minichat $m of $n"
echo "== caddy api paths"
for p in $(grep -oE "handle(_path)? /[A-Za-z0-9_/.*-]+" $N/ops/web_chat_auth/Caddyfile | awk '{print $2}' | sed 's#/\*$##' | sort -u); do c $p 8091 6; done
echo "== matrix"
for p in /api/nox/agenda /api/nox/outbox /api/nox/briefs /api/nox/self_now /api/nox/memory/health /api/nox/status /api/chat/health /svc/_status /svc/nox-living/health /svc/nox-living/ /health; do c $p 8091 8; done
for u in 18220/health 8093/health 8094/health 8810/health 8810/tasks 8810/board 18218/health 8400/health 8200/running 8793/health 9100/health 8120/health; do c /${u#*/} ${u%%/*} 6 | sed "s#^#:${u%%/*} #"; done
