echo "C300: w_sc3"
O=/workspace/nox/agent/out
python3 /workspace/nox/tools/uiscore/report.py 2>&1 | cut -c1-175 > $O/ui_report_now.txt
awk '{print $1,$2,$3}' $O/ui_report_now.txt | tr '\n' ';' | cut -c1-6000
echo; tail -1 $O/ui_report_now.txt
ls $O/ui_sc/*_lh.json 2>/dev/null | wc -l
