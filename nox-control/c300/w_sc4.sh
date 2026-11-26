echo "C300: w_sc4"
O=/workspace/nox/agent/out
grep -E '^(chat |studio|qa |voice|ops |operators|evolution|assistant|resonance|messenger)' $O/ui_report_now.txt | cut -c1-175
