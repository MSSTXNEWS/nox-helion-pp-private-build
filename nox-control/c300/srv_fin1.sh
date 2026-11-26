P=/workspace/nox/state/p3
for f in persona_gen persona_gen2 persona_gen3; do echo "$f: $(cat $P/$f.json | head -c 160)"; done
cat /workspace/nox/distill_v2/raw_skill_p3_persona_*.jsonl 2>/dev/null | wc -l
python3 -c "
import json,glob,collections
C=collections.Counter()
for f in glob.glob('/workspace/nox/distill_v2/raw_skill*p3_persona*.jsonl')+glob.glob('/workspace/nox/distill_v2/raw_skill*p3_antisyc_ru*.jsonl')+glob.glob('/workspace/nox/distill_v2/raw_skill.ingested.*p3_persona*'):
    for l in open(f): C[json.loads(l).get('cat')]+=1
print(C)"
echo load $(cat /proc/loadavg); tail -2 $P/repin.log
