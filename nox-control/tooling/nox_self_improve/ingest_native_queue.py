#!/usr/bin/env python3
"""Offline reconciler for actual native queue snapshot; does not invent or publish TaskIDs."""
import argparse,json,hashlib,collections
from pathlib import Path

def reconcile(snapshot,catalog):
    records=snapshot.get('items',snapshot.get('tasks',snapshot.get('jobs')))
    if not isinstance(records,list):raise ValueError('Expected actual native records array items/tasks/jobs; aggregate counts alone cannot become task cards')
    known={x['id']:x for x in catalog['cards']}
    rows=[];seen=set()
    for x in records:
        if not isinstance(x,dict):continue
        native_id=x.get('task_id') or x.get('TaskID') or x.get('id')
        if not native_id:continue # do not synthesize
        native_id=str(native_id)
        if native_id in seen:continue
        seen.add(native_id)
        original=x.get('original_task_id') or native_id
        match=known.get(str(original))
        status=x.get('status','UNVERIFIED')
        rows.append({'native_id':native_id,'original_task_id':original,
                     'canonical_match':match['id'] if match else None,
                     'category':match['category'] if match else 'UNMAPPED_NATIVE_QUEUE',
                     'source_status':status,
                     'accepted': bool(status=='ACCEPTED' and x.get('terminal_receipt') and x.get('verifier_receipt') and x.get('source_sha')),
                     'terminal_receipt':x.get('terminal_receipt'),
                     'verifier_receipt':x.get('verifier_receipt'),
                     'source_sha':x.get('source_sha'),
                     'requires_review':not bool(match)})
    return {'actual_unique_native_ids_in_snapshot':len(rows),'matched_to_original295':sum(bool(x['canonical_match']) for x in rows),
            'not_automatically_published':True,'records':rows}

def main():
    p=argparse.ArgumentParser();p.add_argument('native_snapshot');p.add_argument('--catalog',required=True);p.add_argument('--out',required=True)
    a=p.parse_args();snap=json.loads(Path(a.native_snapshot).read_text());cat=json.loads(Path(a.catalog).read_text())
    out=reconcile(snap,cat);Path(a.out).write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8');print('reconciled',out['actual_unique_native_ids_in_snapshot'])
if __name__=='__main__':main()
