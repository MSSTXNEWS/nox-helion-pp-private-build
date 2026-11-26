echo "C300: w_sc6"
O=/workspace/nox/agent/out
grep -E '^(index|photo|qa|games|messenger|social|live|money|cinema|board|calls|studio|tv)[ ]' $O/ui_report_now2.txt | cut -c1-175
grep -E 'lh' $O/ui_report_now2.txt | grep -v 'lh-' | awk '{print $1,$2,$3,$7,$8,$9,$10,$11,$12,$13}' | cut -c1-120 | head -20
