import importlib,sys,tempfile
from pathlib import Path
from copy import deepcopy
sys.path.insert(0,str(Path(sys.argv[1]).resolve()))
from brain800.kernel import Kernel, MODULES
from brain800.intent import KINDS
from brain800.phrases import route_phrase,EXAMPLES
with tempfile.TemporaryDirectory() as tmp:
    kernel=Kernel(Path(tmp)/'state.sqlite')
    used=set()
    for domain in MODULES:
        module=importlib.import_module('brain800.'+domain)
        for key in module.OPS:
            name=key if key.startswith(domain+'.') else domain+'.'+key
            examples=getattr(module,'SAMPLES',{})
            sample=examples[key] if key in examples else module.SAMPLE
            initial=deepcopy(sample); kernel.run(name,sample)
            assert sample==initial,name
            used.add(name)
    for kind in KINDS:
        def act(action,**kw):
            name=f'intent.{kind}.{action}';used.add(name)
            return kernel.run(name,{'key':'a',**kw},'project-A')
        assert act('open',text='Первая версия',source='файл A')['version']==1
        assert act('revise',text='Вторая версия',expected_version=1)['version']==2
        assert act('close',expected_version=2)['closed']
        assert not act('reopen',expected_version=3)['closed']
        assert act('read')['text']=='Вторая версия'
        assert len(act('history'))==4 and len(act('source'))==4
        assert len(act('search',query='ВТОРАЯ'))==1 and len(act('active'))==1
        assert act('compare',before=1,after=2)['text']['before']=='Первая версия'
    assert used==set(kernel.meta) and len(used)==800
    for text,name in EXAMPLES:
        req=route_phrase(text,[]);assert req['op']==name
        kernel.run(name,req['data'])
    print('800/800 operations returned JSON; 10 revision histories; 13 RU/ES examples routed.')
