"""Read-only future NOX host adapter, versioned and independent of current Windows R1.
This function cannot grant runtime permission, deploy, schedule, or spend funds.
"""
from __future__ import annotations
import json
from pathlib import Path
from .pipeline import run_mission
from .gates import audit
ROOT=Path(__file__).resolve().parents[1]
ACTIONS={'idea.list','idea.inspect','idea.propose','mission.run','megablock1.preview','capabilities'}

def run_job(request):
    if not isinstance(request,dict) or request.get('contract')!='nox.oie.job.v1':
        return {'ok':False,'error':'CONTRACT_UNSUPPORTED'}
    action=request.get('action')
    if action not in ACTIONS:return {'ok':False,'error':'ACTION_DENIED'}
    data=json.loads((ROOT/'catalog'/'ideas_60.json').read_text('utf-8'))
    try:
        if action=='capabilities':
            body={'version':5,'mode':'READ_ONLY','network_enabled':False,
                 'external_actions':False,'installed_in_r1':False,'businesses_launched':0,
                 'supported_actions':sorted(ACTIONS)}
        elif action=='idea.list':body={'count':len(data),'ideas':[{'id':x['id'],'name':x['name'],'status':x['status']} for x in data]}
        elif action=='idea.inspect':
            idea=next((x for x in data if x['id']==request.get('idea_id')),None)
            if idea is None:return {'ok':False,'error':'IDEA_NOT_FOUND'}
            body={'idea':idea,'audit':audit(idea)}
        else:
            # Host has NOT granted network from this interface; future connector has its own policy.
            inp=request.get('parameters',{})
            if not isinstance(inp,dict):return {'ok':False,'error':'INVALID_PARAMETERS'}
            if len(str(inp.get('theme','')))>240:return {'ok':False,'error':'THEME_TOO_LONG'}
            try:count=int(inp.get('count',3))
            except (ValueError,TypeError):return {'ok':False,'error':'INVALID_COUNT'}
            if not 1<=count<=12:return {'ok':False,'error':'INVALID_COUNT'}
            try:seed=int(inp.get('seed',0))
            except (ValueError,TypeError):return {'ok':False,'error':'INVALID_SEED'}
            if action=='megablock1.preview':
                from .megablock1 import run_megablock1
                body=run_megablock1(data,count=count,seed=seed,theme=str(inp.get('theme','')))
            else:
                body=run_mission(data,count=count,seed=seed,theme=str(inp.get('theme','')),
                                 research='none',network=False,provider='offline')
        return {'ok':True,'contract':'nox.oie.result.v1','result':body}
    except (ValueError,TypeError,KeyError) as exc:
        return {'ok':False,'error':type(exc).__name__}
