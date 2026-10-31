"""NOX OIE V4 future module CLI: read-only research by explicit opt-in, local UI."""
import argparse, json, sys
from pathlib import Path
from collections import Counter
from .gates import validate,evidence_ready,can_enter_pilot,score_exploratory_only,audit
from .discovery import propose,load_seeds
from .journal import append,verify as verify_journal
from .workflow import plan_transition
ROOT=Path(__file__).resolve().parents[1]

def _print(obj):print(json.dumps(obj,ensure_ascii=False,indent=2,sort_keys=True))
def main(argv=None):
    parser=argparse.ArgumentParser(prog='nox-opportunity',description='OFFLINE framework: idea hypotheses only; no market/clinical/agent execution')
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('list').add_argument('--stream',default='ALL')
    sub.add_parser('verify');sub.add_parser('report');sub.add_parser('templates')
    det=sub.add_parser('show');det.add_argument('id')
    check=sub.add_parser('audit');check.add_argument('id')
    plan=sub.add_parser('plan');plan.add_argument('id');plan.add_argument('target')
    ideate=sub.add_parser('discover');ideate.add_argument('--count',type=int,default=3);ideate.add_argument('--theme',default='');ideate.add_argument('--seed',type=int,default=0);ideate.add_argument('--record',action='store_true');ideate.add_argument('--db',default=str(ROOT/'state'/'oie.db'))
    journal=sub.add_parser('journal-verify');journal.add_argument('--db',default=str(ROOT/'state'/'oie.db'))
    mission=sub.add_parser('mission');mission.add_argument('--theme',default='');mission.add_argument('--count',type=int,default=3)
    mission.add_argument('--seed',type=int,default=0);mission.add_argument('--provider',choices=['offline','ollama'],default='offline')
    mission.add_argument('--model',default='');mission.add_argument('--research',choices=['none','crossref','openalex'],default='none')
    mission.add_argument('--network',action='store_true',help='opt in to read-only public research provider request')
    mission.add_argument('--output',default=None);mission.add_argument('--journal',default=None)
    mb=sub.add_parser('megablock1');mb.add_argument('--count',type=int,default=3);mb.add_argument('--seed',type=int,default=0);mb.add_argument('--theme',default='');mb.add_argument('--output',default=None)
    mbverify=sub.add_parser('megablock1-verify');mbverify.add_argument('file')
    ui=sub.add_parser('studio');ui.add_argument('--port',type=int,default=8765)
    review=sub.add_parser('research-packet');review.add_argument('file',help='JSON public source notes, NOT verified evidence')
    adapter=sub.add_parser('bridge');adapter.add_argument('--input',required=True,help='JSON job contract file on disk; no network or external effects')
    a=parser.parse_args(argv)
    data=json.loads((ROOT/'catalog'/'ideas_60.json').read_text(encoding='utf-8'))
    if a.command=='research-packet':
        from .evidence import load_research_packet
        try:_print(load_research_packet(a.file));return 0
        except (ValueError,KeyError,TypeError,json.JSONDecodeError) as exc:
            print('RESEARCH_PACKET_ERROR:'+type(exc).__name__,file=sys.stderr);return 2
    if a.command=='megablock1':
        from .megablock1 import run_megablock1
        from .pipeline import save_json_atomic
        try:
            payload=run_megablock1(data,count=a.count,seed=a.seed,theme=a.theme)
            if a.output:payload['file_receipt']=save_json_atomic(a.output,payload)
            _print(payload);return 0
        except (ValueError,FileExistsError) as exc:
            print('MEGABLOCK1_ERROR:'+str(exc),file=sys.stderr);return 2
    if a.command=='megablock1-verify':
        from .megablock1 import verify_megablock1
        try:
            file=Path(a.file)
            if not file.is_file() or file.stat().st_size>500000:raise ValueError('FILE_SIZE')
            payload=json.loads(file.read_text(encoding='utf-8'))
            result=verify_megablock1(payload,catalog=data);_print(result)
            return 0 if result['valid'] else 3
        except (OSError,ValueError,TypeError) as exc:
            print('RECEIPT_READ_ERROR:'+type(exc).__name__,file=sys.stderr);return 2
    if a.command=='studio':
        from .studio import serve
        serve(port=a.port);return 0
    if a.command=='bridge':
        from .integration import run_job
        path=Path(a.input)
        if not path.is_file() or path.stat().st_size>10000:print('INVALID_JOB_FILE',file=sys.stderr);return 2
        response=run_job(json.loads(path.read_text('utf-8')))
        _print(response)
        return 0 if response['ok'] else 2
    if a.command=='mission':
        from .pipeline import run_mission,save_json_atomic
        try:
            response=run_mission(data,count=a.count,seed=a.seed,theme=a.theme,provider=a.provider,
                                 research=a.research,network=a.network,model=a.model,journal=a.journal)
            if a.output:response['file_receipt']=save_json_atomic(a.output,response)
            _print(response)
            return 0
        except (ValueError,FileExistsError) as exc:
            print('MISSION_ERROR:'+str(exc),file=sys.stderr);return 2
        except Exception as exc:
            from .llm import LocalModelError
            if isinstance(exc,LocalModelError):
                print('LOCAL_MODEL_ERROR:'+str(exc),file=sys.stderr);return 3
            raise
    if a.command=='list':
        for x in data:
            if a.stream=='ALL' or x['stream']==a.stream:print(f"{x['id']} | {x['name']} | {x['stream']} | {x['status']}")
        return 0
    if a.command in ('show','audit','plan'):
        item=next((x for x in data if x['id']==a.id),None)
        if item is None:print('UNKNOWN_ID',file=sys.stderr);return 2
        if a.command=='show':_print({'idea':item,'audit':audit(item)})
        elif a.command=='plan':_print(plan_transition(item,a.target))
        else:_print(audit(item))
        return 0
    if a.command=='templates':
        for p in sorted((ROOT/'templates').glob('*')):
            if p.is_file():print(p.name)
        return 0
    if a.command=='verify':
        problems=[];seen=set()
        for x in data:
            if x.get('id') in seen:problems.append('DUPLICATE:'+str(x.get('id')))
            seen.add(x.get('id'))
            problems.extend(f"{x.get('id')}:{e}" for e in validate(x))
        for x in load_seeds():
            if not x.get('pairing_options'): problems.append('SEED_WITHOUT_PAIRING:'+str(x.get('key')))
        _print({'ideas':len(data),'unique':len(seen),'problem_seeds':len(load_seeds()),'validation_errors':problems,
                'all_unverified':all(x.get('status')=='IDEA_UNVERIFIED' for x in data),'pilot_grants':sum(not can_enter_pilot(x) for x in data)})
        return 2 if problems else 0
    if a.command=='report':
        _print({'schema':'NOX_OIE_V4_SOURCE_ONLY','idea_count':len(data), 'streams':dict(Counter(x['stream'] for x in data)),
                'status':dict(Counter(x['status'] for x in data)), 'problem_seeds':len(load_seeds()),
                'authenticated_owner_grants':0,'independently_verified_market_cases':0,
                'approved_external_pilots':0,'commercial_revenue_verified':0,
                'scientific_novelty_verified':0,'product_release_accepted':False,'windows_r1_touched':False})
        return 0
    if a.command=='discover':
        try:
            result=propose(data,limit=a.count,theme=a.theme,seed=a.seed)
            if a.record:
                result['journal_receipts']=[append(a.db,'CANDIDATE_DRAFTED',{'candidate_id':c['candidate_id'],'name':c['name'],'status':'IDEA_UNVERIFIED'}) for c in result['candidates']]
            _print(result);return 0
        except ValueError as e:print(str(e),file=sys.stderr);return 2
    if a.command=='journal-verify':
        result=verify_journal(a.db);_print(result);return 0 if result['valid'] else 3
    return 2
if __name__=='__main__':sys.exit(main())
