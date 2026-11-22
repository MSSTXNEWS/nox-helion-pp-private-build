import asyncio,json,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(sys.argv[1]).resolve()))
from brain800.bridge import handle
from brain800 import life

async def main(state):
    scope='test-workshop'
    counter=0
    async def say(message):
        nonlocal counter
        counter+=1
        v=await handle(message,scope,'u'+str(counter),state)
        assert v and v['ok'],v
        try:return json.loads(v['text'])
        except json.JSONDecodeError:return v['text']
    await say('Открой мастерскую навыков')
    final=None
    for k in (1,2):
        a={'scene':{'pause':[{'id':'a','start':0,'end':100*k}]},'ids':['a'],'ms':30}
        mid=await say('/brain studio.pause.shift '+json.dumps(a))
        out=await say('/brain studio.pause.duration '+json.dumps({'scene':mid}))
        assert out['occupied_ms']==100*k
        final=await say('Это помогло')
        assert final['growth']['status']==('candidate' if k==1 else 'active'),final
    catalog=await say('/brain skills')
    assert catalog
    rule=final['growth']['rule']
    a={'scene':{'pause':[{'id':'c','start':24,'end':374}]},'ids':['c'],'ms':145}
    out=await say('/brain apply '+json.dumps({'name':rule,'a':a,'b':{}}))
    assert out=={'occupied_ms':350,'span_ms':350},out
    await say('/brain event {"kind":"prediction","subject":"voice.timing","value":0.9}')
    await say('/brain event {"kind":"outcome","subject":"voice.timing","value":0.1}')
    details=await say('/brain self')
    assert details['predictions_corrected']>=1,details
    suggestions=await say('/brain подбери посчитай частоту слов')
    assert len(suggestions)==5,suggestions
    print(json.dumps({'learned':rule,'samples':2,'new_example':out,'corrected_predictions':details['predictions_corrected'],'policy':life.policy(state,scope),'suggestions':len(suggestions)},ensure_ascii=False))
with tempfile.TemporaryDirectory() as d:asyncio.run(main(d))
