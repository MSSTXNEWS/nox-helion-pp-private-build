echo "C300: ch_chk3"
N=/workspace/nox/state; echo "== crit"; cat $N/ch_crit.out | cut -c1-1900; echo "== audit"; tail -c 2500 $N/ch_audit1.log; pgrep -af "qa_audit|crit_ch" | cut -c1-120 | head -4
