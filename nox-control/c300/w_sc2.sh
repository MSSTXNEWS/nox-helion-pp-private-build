echo "C300: w_sc2"
O=/workspace/nox/agent/out
grep -c . $O/ui_sc.log; grep -E 'DONE|done' $O/ui_sc.log | tail -3
ls $O/ui_sc/*_own.json 2>/dev/null | wc -l; ls $O/ui_sc/*_lh.json 2>/dev/null | wc -l
python3 /workspace/nox/tools/uiscore/report.py 2>&1 | cut -c1-170 > $O/ui_report_now.txt; tail -1 $O/ui_report_now.txt
grep '<8' $O/ui_report_now.txt | cut -c1-120 | head -60
