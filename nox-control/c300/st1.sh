echo "K1: st1"; N=/workspace/nox
echo "OFF:"; ls $N/state/*.off 2>/dev/null | xargs -n1 basename | sed 's/\.off$//' | tr '\n' ' '; echo
echo "SUP:"; supervisorctl status 2>/dev/null | awk '{print $1"="$2}' | tr '\n' ' '; echo
echo "accepted=$(ls $N/agent/autotrain/accepted* 2>/dev/null | wc -l) cand=$(ls -d $N/agent/autotrain/cand* 2>/dev/null | wc -l)"
echo "birth_done=$([ -e $N/state/birth_done ] && echo 1 || echo 0) passport=$([ -s $N/state/passport_self.json ] && echo 1 || echo 0)"
for m in inspector sensorium conscience hunger_goals birth_ritual weekly_exam passport_self; do echo "$m mod=$([ -e $N/mods/$m.py ] && echo 1 || echo 0)"; done
grep -c . $N/state/p3/gate_log.jsonl 2>/dev/null | sed 's/^/gate_log=/'
echo END
