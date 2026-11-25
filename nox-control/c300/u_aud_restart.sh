echo "C300: u_aud_restart"
# Остановить зависший цикл ревизора (по просьбе координатора: pid 2389847 = qa_audit_loop.sh) и запустить чистый последовательный прогон creative, index, settings.
O=/workspace/nox/agent/out
kill 2389847 2>/dev/null
pkill -f qa_audit_loop.sh
pkill -f u_audit
pkill -f "qa_audit.py"
sleep 3
echo "left: $(pgrep -af 'qa_audit|u_audit' | wc -l)"; pgrep -af 'qa_audit|u_audit' | cut -c1-100
rm -f $O/u_qab_*
setsid nohup bash $O/u_audit5.sh >/dev/null 2>&1 < /dev/null &
sleep 4; echo "now running:"; pgrep -af 'qa_audit|u_audit' | cut -c1-110
