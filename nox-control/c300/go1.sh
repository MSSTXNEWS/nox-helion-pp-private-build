echo "K1: go1"
N=/workspace/nox; D=$N/ops/dpo
# владелец: тишина 5 минут достаточно для обучения
sed -i 's/stat -c %Y $N\/state\/orch\/OWNER_ACTIVE) )) -gt 600/stat -c %Y $N\/state\/orch\/OWNER_ACTIVE) )) -gt 300/' $D/char_cycle.sh
sed -i 's/getmtime(OWN) < 600/getmtime(OWN) < 300/' $D/build_dpo5.py
sed -i 's/OWNER_ACTIVE") > 600/OWNER_ACTIVE") > 300/' $D/dpo5_daily.py
echo "idle300: cycle=$(grep -c 'gt 300' $D/char_cycle.sh) b5=$(grep -c '< 300' $D/build_dpo5.py) daily=$(grep -c '> 300' $D/dpo5_daily.py)"
bash -n $D/char_cycle.sh && python3 -m py_compile $D/build_dpo5.py $D/dpo5_daily.py && echo syntax_ok
supervisorctl restart nox_dpo5_daily >/dev/null 2>&1
# всё включено?
for f in chat_night chat_iq chat_calc chat_verify chat_summary chat_resume chat_receipt chat_search chat_sandbox chat_consilium chat_repeat_guard chat_roles chat_think chat_pairs chat_episodes chat_passport chat_hunger sidecar voice train_window; do [ -f $N/state/$f.off ] && echo "OFF $f"; done
echo "bo2_off(slow)=$([ -f $N/state/chat_bo2.off ] && echo 1 || echo 0)"
for p in nox_sidecar nox_voice nox_music nox_inspector nox_weekly_exam nox_sensorium_ext nox_dpo5_daily; do echo -n "$p=$(supervisorctl status $p | awk '{print $2}') "; done; echo
for u in index.html chat-dc.html widgets.html memory.html writer/index.html; do echo -n "$u=$(curl -s -o /dev/null -m 6 -w %{http_code} http://127.0.0.1:18091/web/$u) "; done; echo
echo "gate=$(curl -s -o /dev/null -m 8 -w %{http_code} -u owner:$(cat $N/state/owner_gate/pass) http://127.0.0.1:18092/web/index.html) tunnel=$(pgrep -fc 'cloudflared.*20999')"
echo END
