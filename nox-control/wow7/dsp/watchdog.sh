#!/usr/bin/env bash
# DSP watchdog: лёгкий независимый сторож (bash+python3 -I), не зависит от кода диспетчера. Запуск: cron каждую минуту (--once),
# либо --loop (если cron в контейнере нет), либо --boot (из /root/onstart.sh: пауза 20 с, затем once).
# Делает: (1) пишет свой heartbeat (его проверяет диспетчер и перезапускает сторожа); (2) если heartbeat диспетчера протух - запускает его;
# (3) откат релиза: pending из updates.json просрочен или диспетчер не стартует 3 раза за 10 мин -> current -> previous;
# (4) если и откат не помог - разовый fallback c122/boot_s1.sh (старый идемпотентный подъём чата). STOP: диспетчер жив, fallback не запускается.
# Env: DSP_HOME (/root/nox) DSP_RUN_CMD DSP_STALE_S (90) DSP_STOP_FILES (/run/nox/STOP:$H/STOP) DSP_FALLBACK (boot_s1.sh) DSP_LOOP_S (60)
set -u
H="${DSP_HOME:-/root/nox}"; I="$H/dsp"; R="$H/run"; L="$H/logs"
STALE="${DSP_STALE_S:-90}"; LOOP_S="${DSP_LOOP_S:-60}"; DRY=0; MODE=once
for a in "$@"; do case "$a" in --once) MODE=once;; --loop) MODE=loop;; --boot) MODE=boot;; --dry-run) DRY=1;; *) echo "неизвестный флаг $a" >&2; exit 2;; esac; done
RUN_CMD="${DSP_RUN_CMD:-python3 $I/current/nox_dispatcher.py run}"
FALLBACK="${DSP_FALLBACK:-$H/repo/nox-control/c122/boot_s1.sh}"
STOPS="${DSP_STOP_FILES:-/run/nox/STOP:$H/STOP}"
mkdir -p "$R" "$L" 2>/dev/null
log() { echo "[$(date '+%F %T')] wd: $*" >> "$L/dsp_watchdog.log"; [ "$DRY" = 1 ] && echo "wd: $*"; }
py() { python3 -I -c "$@"; }
stop_active() { local f; IFS=: read -ra A <<< "$STOPS"; for f in "${A[@]}"; do [ -e "$f" ] && return 0; done; return 1; }

hb_age() {  # возраст heartbeat диспетчера в секундах, 999999 если нет/мёртв
  py 'import json,os,sys,time
try:
    h=json.load(open(sys.argv[1])); pid=int(h.get("pid",0))
    os.kill(pid,0) if pid else (_ for _ in ()).throw(OSError())
    print(int(time.time()-float(h["ts"])))
except Exception:
    print(999999)' "$R/dsp_dispatcher.hb"
}

rollback() {  # rollback <причина>: current -> previous, версия в bad, pending сброшен
  local why="$1"
  [ -L "$I/previous" ] || { log "откат невозможен: нет previous ($why)"; return 1; }
  [ "$DRY" = 1 ] && { log "dry-run: откат ($why)"; return 0; }
  py 'import json,os,sys,time
inst,why=sys.argv[1],sys.argv[2]
cur=os.path.basename(os.readlink(inst+"/current")) if os.path.islink(inst+"/current") else None
prev=os.path.basename(os.readlink(inst+"/previous"))
tmp=inst+"/current.wd.new"
if os.path.lexists(tmp): os.remove(tmp)
os.symlink("releases/"+prev,tmp); os.replace(tmp,inst+"/current")
p=inst+"/updates.json"
try: st=json.load(open(p))
except Exception: st={"bad":[],"history":[],"pending":None}
if cur and cur not in st.setdefault("bad",[]): st["bad"].append(cur)
st["pending"]=None
st.setdefault("history",[]).append({"ts":time.time(),"version":cur,"ok":False,"why":"watchdog: "+why,"back_to":prev})
json.dump(st,open(p+".tmp","w"),ensure_ascii=False); os.replace(p+".tmp",p)' "$I" "$why" && { log "ОТКАТ релиза: $why"; return 0; }
  return 1
}

pending_expired() {  # 0 если есть pending с истёкшим deadline
  [ -f "$I/updates.json" ] && py 'import json,sys,time
st=json.load(open(sys.argv[1])); p=st.get("pending")
sys.exit(0 if p and time.time()>float(p.get("deadline",0)) else 1)' "$I/updates.json" 2>/dev/null
}

start_dispatcher() {
  local starts_f="$R/dsp_wd_starts" now; now=$(date +%s)
  touch "$starts_f"
  awk -v n="$now" 'n-$1<600' "$starts_f" > "$starts_f.t" 2>/dev/null; mv "$starts_f.t" "$starts_f"
  local cnt; cnt=$(wc -l < "$starts_f")
  if [ "$cnt" -ge 3 ]; then
    log "диспетчер не стартует ($cnt запусков за 10 мин)"
    : > "$starts_f"
    if ! rollback "диспетчер не стартовал 3 раза за 10 мин"; then
      if ! stop_active && [ -f "$FALLBACK" ]; then log "fallback: $FALLBACK"; [ "$DRY" = 1 ] || { nohup setsid bash "$FALLBACK" >> "$L/boot.log" 2>&1 < /dev/null & }; fi
    fi
  fi
  echo "$now" >> "$starts_f"
  log "запуск диспетчера: $RUN_CMD"
  [ "$DRY" = 1 ] || { nohup setsid $RUN_CMD >> "$L/dsp_dispatcher.out" 2>&1 < /dev/null & }
}

once() {
  exec 8>"$R/dsp_watchdog.lock"
  command -v flock >/dev/null && { flock -n 8 || exit 0; }
  [ "$DRY" = 1 ] || py 'import json,os,sys,time
p=sys.argv[1]; json.dump({"ts":time.time(),"pid":os.getppid()},open(p+".tmp","w")); os.replace(p+".tmp",p)' "$R/dsp_watchdog.hb"
  if pending_expired; then rollback "обновление не подтверждено до deadline" && age=999999; fi
  age=$(hb_age)
  if [ "$age" -gt "$STALE" ]; then
    log "heartbeat диспетчера: ${age} с (порог $STALE)"
    start_dispatcher
  fi
}

case "$MODE" in
  once) once;;
  boot) sleep "${DSP_BOOT_SLEEP:-20}"; once;;
  loop) pgrep -f "watchdog.sh --loop" | grep -qv "^$$\$" && [ "${DSP_LOOP_FORCE:-0}" != 1 ] && { echo "loop уже запущен"; exit 0; }
        while true; do once; sleep "$LOOP_S"; done;;
esac
