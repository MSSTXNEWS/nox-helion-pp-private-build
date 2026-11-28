echo "K1: sc2_dep"
export RUNNER_TRACKING_ID=""
N=/workspace/nox; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/${REF:-main}/nox-control/c300/bundles; ts=$(date +%s)
SC=$N/mods/nox_sidecar.py; G=$N/state/owner_gate/Caddyfile; CF=$N/ops/web_chat_auth/Caddyfile; T=$N/state/owner_gate/sidecar_token
[ "$(md5sum < $SC | cut -c1-32)" = 89c703ce874a8c333c21403c71ab7d0f ] || { echo "BASE_CHANGED abort"; echo END; exit 0; }
W=$(mktemp -d); curl -fsSL $R/enc_in/sc2.enc -o $W/e; curl -fsSL $R/enc_in/sc2.key -o $W/k
openssl pkeyutl -decrypt -inkey $N/state/keys/inbox.pem -in $W/k -out $W/kk && openssl enc -d -aes-256-cbc -pbkdf2 -in $W/e -pass file:$W/kk | tar xzf - -C $W || { echo DECRYPT_FAIL; echo END; exit 0; }
[ "$(md5sum < $W/nox_sidecar.py | cut -c1-32)" = 3e1b28302d5c8df29e056fec2fefec29 ] || { echo BAD_PAYLOAD; echo END; exit 0; }
python3 -I -m py_compile $W/nox_sidecar.py || { echo COMPILE_FAIL; echo END; exit 0; }
[ -s $T ] || (umask 077; openssl rand -hex 24 > $T); chmod 600 $T; echo "token_len=$(wc -c < $T)"
cp -a $SC $SC.bak_sc2_$ts; cp $W/nox_sidecar.py $SC; supervisorctl restart nox_sidecar >/dev/null 2>&1; sleep 3; echo "sidecar_health $(curl -s -o /dev/null -m 4 -w %{http_code} http://127.0.0.1:18798/health)"
cp -a $G $G.bak_sc2_$ts; cp -a $CF $CF.bak_sc2_$ts
python3 - $G $CF $T <<'PY'
import sys,re
g,cf,tf=sys.argv[1:4]; tok=open(tf).read().strip()
L=open(g).read().split("\n")
if not any("X-NOX-Owner-Token" in l for l in L):
    i=next((k for k,l in enumerate(L) if re.match(r"\s*reverse_proxy\b",l)),None)
    if i is None: print("gate_no_anchor")
    else:
        L.insert(i,'\trequest_header X-NOX-Owner-Token "%s"'%tok); open(g,"w").write("\n".join(L)); print("gate_header_inserted")
else: print("gate_header_present")
M=open(cf).read().split("\n"); done=0
for k,l in enumerate(M):
    if "/api/draft" in l and "/api/memory/add" in l and "/api/nox/proposals" not in l: M[k]=l.rstrip()+" /api/nox/proposals /api/nox/consent"; done=1
open(cf,"w").write("\n".join(M)); print("main_paths_added",done, "draft_lines",sum(1 for l in M if "/api/draft" in l))
PY
GP=$(pgrep -f "owner_gate/Caddyfile" | head -1); GB=$(readlink /proc/$GP/exe)
MP=$(pgrep -f "web_chat_auth/Caddyfile" | head -1); MB=$(readlink /proc/$MP/exe)
okg=no; okm=no
$GB validate --config $G --adapter caddyfile >/dev/null 2>&1 && okg=yes; $MB validate --config $CF --adapter caddyfile >/dev/null 2>&1 && okm=yes
echo "valid gate=$okg main=$okm"
restore(){ cp -a $G.bak_sc2_$ts $G; cp -a $CF.bak_sc2_$ts $CF; cp -a $SC.bak_sc2_$ts $SC; supervisorctl restart nox_sidecar >/dev/null 2>&1; }
if [ "$okg" = yes ] && [ "$okm" = yes ]; then
  SV=$(supervisorctl status 2>/dev/null | awk '{print $1}' | while read p; do supervisorctl pid $p 2>/dev/null | grep -qx "$MP" && echo $p; done | head -1)
  [ -n "$SV" ] && supervisorctl restart $SV >/dev/null 2>&1 && echo main_caddy_restarted || echo main_caddy_not_supervised
  kill $GP; sleep 1; setsid -f $GB run --config $G --adapter caddyfile >>$N/state/owner_gate/caddy.log 2>&1 </dev/null; sleep 3
else echo "invalid -> restore"; restore; echo END; exit 0; fi
P=$(cat $N/state/owner_gate/pass); TK=$(cat $T)
c(){ curl -s -o /dev/null -m 8 -w %{http_code} "$@"; }
a=$(c http://127.0.0.1:18092/web/chat-dc.html); b=$(c -u owner:$P http://127.0.0.1:18092/web/chat-dc.html)
pr=$(c -u owner:$P http://127.0.0.1:18092/api/nox/proposals); pn=$(c http://127.0.0.1:18092/api/nox/proposals); pd=$(c http://127.0.0.1:18091/api/nox/proposals); pf=$(c -H "X-NOX-Owner-Token: 0000000000000000000000000000000000000000000000000" http://127.0.0.1:18091/api/nox/proposals)
cb=$(curl -s -o /dev/null -m 8 -w %{http_code} -u owner:$P -X POST -H 'Content-Type: application/json' -d '{"kind":"hunt","id":"zz","decision":"maybe"}' http://127.0.0.1:18092/api/nox/consent)
cd2=$(curl -s -o /dev/null -m 8 -w %{http_code} -X POST -H 'Content-Type: application/json' -d '{"kind":"hunt","id":"zz","decision":"denied"}' http://127.0.0.1:18091/api/nox/consent)
echo "gate_noauth=$a gate_auth=$b proposals_gate_auth=$pr proposals_gate_noauth=$pn proposals_direct=$pd proposals_forged=$pf consent_bad_decision=$cb consent_direct=$cd2"
curl -s -u owner:$P http://127.0.0.1:18092/api/nox/proposals | python3 -c "import sys,json;d=json.load(sys.stdin);print('proposals hunt=%d forge=%d keys=%s'%(len(d['hunt']),len(d['forge']),sorted(d['hunt'][0]) if d['hunt'] else '-'))" 2>&1 | tail -1
r1=$(c "http://127.0.0.1:18091/api/convs?user=owner"); r2=$(c http://127.0.0.1:18091/api/nox/status); r3=$(c http://127.0.0.1:18091/health)
echo "sanity convs=$r1 status=$r2 health=$r3"
if [ "$a" = 401 ] && [ "$b" = 200 ] && [ "$pr" = 200 ] && [ "$pd" = 403 ] && [ "$pf" = 403 ] && [ "$cb" = 400 ] && [ "$cd2" = 403 ] && [ "$r1" = 200 ]; then echo "VERDICT GOOD"; else echo "VERDICT BAD -> restore"; restore; kill $(pgrep -f "owner_gate/Caddyfile" | head -1); sleep 1; setsid -f $GB run --config $G --adapter caddyfile >>$N/state/owner_gate/caddy.log 2>&1 </dev/null; [ -n "$SV" ] && supervisorctl restart $SV >/dev/null 2>&1; sleep 3; echo "after_restore gate_auth=$(c -u owner:$P http://127.0.0.1:18092/web/chat-dc.html)"; fi
rm -rf $W; echo END
