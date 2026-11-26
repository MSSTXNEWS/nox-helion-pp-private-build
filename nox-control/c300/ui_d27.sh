echo "C300: ui_d27"
F=/workspace/nox/agent/done_27.sh; ls -la --time-style=full-iso $F; grep -n "web/site\|webroot\|pkg/\|cp \|rsync\|nox-theme\|graphite" $F | head -40; wc -l $F
echo == who calls it; grep -rl "done_27" /workspace/nox/agent/*.sh /workspace/nox/*.sh 2>/dev/null | head; crontab -l 2>/dev/null | grep -i "done_27\|webroot" ; ps aux | grep -c "done_27"
echo == lh count; ls /workspace/nox/agent/out/ui_sc | grep -c lh; tail -3 /workspace/nox/agent/out/ui_sc.log | cut -c1-200
