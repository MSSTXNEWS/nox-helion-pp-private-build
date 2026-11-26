echo "C300: ch_chk6"
N=/workspace/nox/state; tail -c 1500 $N/ch_audit1.log; echo; ls -l $N/ch_audit1.log | cut -c20-80; pgrep -af "qa_audit" | cut -c1-110 | head -6
python3 -I -c "
import json;d=json.load(open('/workspace/nox/web/site/qa/audit.json'))['chat'];print(d.get('ts'));[print('-',f['item'][:80],'|',str(f['detail'])[:160]) for f in d.get('fails',[])]" 2>&1 | head -12
tail -3 $N/ch_q10b.out | cut -c1-200
