echo "C300: ch_chk7"
N=/workspace/nox/state; cat $N/ch_golden3.out | cut -c1-230; cat $N/ch_verified.json | cut -c1-300; echo
tail -c 500 $N/ch_audit1.log; pgrep -af "qa_audit" | cut -c1-100 | head -5
python3 -I -c "
import json;d=json.load(open('/workspace/nox/web/site/qa/audit.json'))['chat'];print(d.get('ts'));[print('-',f['item'][:80],'|',str(f['detail'])[:160]) for f in d.get('fails',[])]" 2>&1 | head -8
