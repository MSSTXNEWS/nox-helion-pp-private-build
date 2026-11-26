echo "C300: w_sc5"
O=/workspace/nox/agent/out
grep -E 'DONE' $O/ui_sc2.log | tail -2; ls $O/ui_sc/*_own.json 2>/dev/null | wc -l
python3 /workspace/nox/tools/uiscore/report.py 2>&1 | cut -c1-175 > $O/ui_report_now2.txt
tail -1 $O/ui_report_now2.txt
awk '{print $1,$2,$3}' $O/ui_report_now2.txt | tr '\n' ';' | cut -c1-6000
