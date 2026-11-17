import argparse
from dataclasses import asdict
import json
from pathlib import Path
from . import Controller, CommandHooks, load_manifest, read_snapshot, Hold, Paused


def main():
    p=argparse.ArgumentParser(description='NOX existing-host cache/mode controller. Default is dry-run.')
    p.add_argument('--manifest',required=True);p.add_argument('--cache-root',required=True)
    p.add_argument('--journal',required=True);p.add_argument('--cgroup',default='/sys/fs/cgroup')
    p.add_argument('--meminfo',default='/proc/meminfo');p.add_argument('--hooks')
    p.add_argument('--apply',action='store_true')
    sub=p.add_subparsers(dest='command',required=True)
    sub.add_parser('status');sub.add_parser('startup');sub.add_parser('rollback-plan')
    q=sub.add_parser('transition');q.add_argument('target',choices=['WORK','TRAIN','PAUSED_TRAIN']);q.add_argument('transition_id')
    q=sub.add_parser('cache-local');q.add_argument('group');q.add_argument('source')
    q=sub.add_parser('adopt-host-state');q.add_argument('receipt')
    args=p.parse_args();hooks=CommandHooks(json.loads(Path(args.hooks).read_text())) if args.hooks else None
    snapshot=lambda:read_snapshot(args.cgroup,args.meminfo)
    def owner_pause():
        result=hooks('owner_activity',{})
        return result.get('owner_active') is not False or result.get('stop_requested') is not False
    c=Controller(load_manifest(args.manifest),args.cache_root,args.journal,snapshot=snapshot,hooks=hooks,
                 host_resource_admission=(lambda x:hooks('resource_admission',x)) if hooks else None,
                 host_release_resource=(lambda x:hooks('resource_release',x)) if hooks else None,
                 owner_should_pause=owner_pause if hooks else None)
    try:
        if args.command=='status':out={'memory':asdict(snapshot()),'journal':c.data,'native_ready':False,'live_host_probe_performed':False}
        elif args.command=='startup':out=c.startup(apply=args.apply)
        elif args.command=='rollback-plan':out=c.rollback_plan()
        elif args.command=='transition':out=c.transition(args.target,args.transition_id,apply=args.apply)
        elif args.command=='cache-local':
            out=c.cache_local(args.group,args.source,apply=args.apply)
        elif args.command=='adopt-host-state':
            r=json.loads(Path(args.receipt).read_text())
            if args.apply:c.adopt_verified_state(r['mode'],r['loaded'],r)
            out={'status':'STATE_ADOPTED' if args.apply else 'DRY_RUN','verified_by_caller_not_a_probe':True}
    except (Hold,Paused,ValueError,OSError) as e:out={'status':'HOLD','reason':str(e),'native_ready':False}
    print(json.dumps(out,ensure_ascii=False,indent=2))
    return 2 if out.get('status')=='HOLD' else 0

if __name__=='__main__':raise SystemExit(main())
