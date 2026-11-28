echo "K1: mv1"
# Владелец 28.11 «Мои решения все далее»: музыка вкл, чистка кэша установщика, видео, ночная консолидация.
export RUNNER_TRACKING_ID=""
N=/workspace/nox; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/${REF:-main}/nox-control/c300/bundles; ts=$(date +%s)
CD=$(grep -lr "program:nox_sidecar" /etc/supervisor /etc/supervisord* $N/ops 2>/dev/null | head -1 | xargs -r dirname)
[ -n "$CD" ] || { echo NO_CONF_DIR; exit 0; }
# 1) ночная консолидация
rm -f $N/state/chat_night.off; echo "night_on=$([ -f $N/state/chat_night.off ] && echo 0 || echo 1)"
# 2) чистка кэшей установщика (восстановимы)
echo "disk_before=$(df -BG /workspace | awk 'NR==2{print $4}')"
for d in /root/.cache/uv /root/.cache/pip /root/.cache/huggingface/xet; do [ -d $d ] && { s=$(du -sh $d 2>/dev/null | cut -f1); rm -rf $d; echo "cleaned $(basename $d) $s"; }; done
echo "disk_after_clean=$(df -BG /workspace | awk 'NR==2{print $4}')"
# 3) музыка: автозапуск + маршрут
sed 's/^autostart=false/autostart=true/' $N/mods/sup_pending/nox_music.conf > $CD/nox_music.conf
supervisorctl reread >/dev/null 2>&1; supervisorctl update >/dev/null 2>&1; sleep 5; echo "sv nox_music $(supervisorctl status nox_music | awk '{print $2}')"
CF=$N/ops/web_chat_auth/Caddyfile; cp -a $CF $CF.bak_mv1_$ts
curl -fsSL "$R/caddy_mv.snippet" -o /tmp/mv.snip
if ! grep -q "NOX_MUSICVIDEO" $CF; then python3 - $CF /tmp/mv.snip <<'PY'
import sys
cf,sn=sys.argv[1],sys.argv[2]; L=open(cf).read().split("\n")
i=next((k for k,l in enumerate(L) if "NOX_SIDECAR" in l),None)
if i is None: print("NO_MARKER"); sys.exit(0)
S=["\t# NOX_MUSICVIDEO"]+open(sn).read().rstrip("\n").split("\n")
open(cf,"w").write("\n".join(L[:i+1]+S+L[i+1:])); print("inserted")
PY
fi
PID=$(pgrep -f "caddy.*web_chat_auth/Caddyfile" | head -1); BIN=$(readlink /proc/$PID/exe)
if $BIN validate --config $CF --adapter caddyfile >/dev/null 2>&1; then echo valid=yes
  SV=$(supervisorctl status 2>/dev/null | awk '{print $1}' | while read p; do supervisorctl pid $p 2>/dev/null | grep -qx "$PID" && echo $p; done | head -1)
  [ -n "$SV" ] && supervisorctl restart $SV >/dev/null 2>&1 && echo caddy_restarted
else echo "valid=no -> restore"; cp -a $CF.bak_mv1_$ts $CF; fi
sleep 3
echo "music_options $(curl -s -o /dev/null -m 10 -X OPTIONS -w %{http_code} http://127.0.0.1:18091/music/gen)"
echo "music_gen $(curl -s -m 300 -o /tmp/m.mp3 -w '%{http_code} %{size_download} %{time_total}' -X POST -H 'Content-Type: application/json' -d '{"prompt":"спокойный эмбиент, синтезатор","seconds":10,"loop":false}' http://127.0.0.1:18091/music/gen)"
echo "chat $(curl -s -o /dev/null -m 8 -w %{http_code} http://127.0.0.1:18091/web/chat-dc.html) gate $(curl -s -o /dev/null -m 8 -w %{http_code} -u owner:$(cat $N/state/owner_gate/pass) http://127.0.0.1:18092/web/music.html)"
# 4) видео — только если хватает диска (18 ГБ модели + 15 запас)
free_g=$(df -BG /workspace | awk 'NR==2{gsub("G","",$4);print $4}')
if [ "$free_g" -ge 34 ]; then
  cd $N/mods && (nice -n 19 timeout 2400 bash install_video.sh > $N/logs/install_video.log 2>&1; echo "rc=$?" >> $N/logs/install_video.log)
  grep -iE '"ok"|vram|sec|rc=|error|fail' $N/logs/install_video.log | sed -E 's/[0-9a-f]{40,64}/<sha>/g' | cut -c1-200 | tail -8
  sed 's/^autostart=false/autostart=true/' $N/mods/sup_pending/nox_video.conf > $CD/nox_video.conf; supervisorctl reread >/dev/null; supervisorctl update >/dev/null; sleep 4
  echo "sv nox_video $(supervisorctl status nox_video | awk '{print $2}') video_route $(curl -s -o /dev/null -m 8 -w %{http_code} http://127.0.0.1:18091/video/job/x)"
else echo "SKIP_VIDEO disk_free=${free_g}G need>=34"; fi
echo "disk_final=$(df -BG /workspace | awk 'NR==2{print $4}')"
echo END
