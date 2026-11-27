echo "K1: v1_02s"
export RUNNER_TRACKING_ID=""
N=/workspace/nox
for p in 3494338 3471009 202580; do echo "pp $p: $(ps -o etimes=,args= -p $p | cut -c1-200)"; done
grep -rIl "qa_audit" $N --include=*.sh --include=*.py --include=*.cron --include=*.service 2>/dev/null | grep -v "/venv" | head
grep -l qa_audit /etc/cron.d/* /var/spool/cron/crontabs/* /etc/crontab 2>/dev/null
crontab -l 2>/dev/null | grep -n qa_audit | cut -c1-160
ls -la $N/qa_audit.py
echo "--- cmd files"
A=$N/agent/autotrain; cat $A/mode; ls -la $A/donor_*.cmd* | cut -c1-120
tr '\n' ' ' < $A/donor_$(cat $A/mode).cmd | cut -c1-700; echo
echo END
