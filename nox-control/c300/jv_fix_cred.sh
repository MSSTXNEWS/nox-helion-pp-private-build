echo "K1: jv_fix_cred"
S=/workspace/nox/web/site; T=/workspace/nox/state/web_bak_cred_$(date +%s); mkdir -p $T
F='/*nox-credfix*/(function(){if(window.__noxCred)return;window.__noxCred=1;var f=window.fetch;window.fetch=function(u,o){try{if(typeof u==="string"&&u.charAt(0)==="/"&&u.charAt(1)!=="/")u=location.origin+u;}catch(e){}return f.call(this,u,o)};})();'
for f in nox-jarvis.js nox-jarvis-layer.js nox-dc.js; do [ -f $S/$f ] || continue; cp -a $S/$f $T/; grep -q nox-credfix $S/$f || { printf '%s\n' "$F" | cat - $S/$f > /tmp/cf && cat /tmp/cf > $S/$f; }; echo "$f $(grep -c nox-credfix $S/$f)"; done
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles; cb=$(date +%s)
bash <(curl -fsSL "$R/th_graphite/webroot_sync.sh?cb=$cb") | tail -1
sed -i 's/nox-jarvis.js"/nox-jarvis.js?v=cf1"/' $S/chat-dc.html; grep -o 'nox-jarvis.js[^"]*' $S/chat-dc.html | head -1
echo "chat-dc $(curl -s -o /dev/null -w %{http_code} http://127.0.0.1:18091/web/chat-dc.html)"
