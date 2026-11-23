#!/usr/bin/env python3
"""Select high-value candidate without admitting it. Uses existing dispatch cap and gates."""
import argparse,json
from pathlib import Path

def suggest(catalog,accepted,blocked):
    allcards=catalog['cards'];ranked=[c for c in allcards if c.get('origin')=='ORIGINAL_295' and c['id'] not in accepted]
    ranked.sort(key=lambda c:(-c['priority_score_heuristic'],c['id']))
    for c in ranked:
        dep=c.get('dependencies','')
        if c['id'] in blocked:continue
        if dep and any(x in dep for x in blocked):continue
        return {'recommendation':c['id'],'name':c['title'],'candidate_path':c['candidate_target'],
                'eligibility':'NEEDS_OWNER_LEASE_STOP_RESOURCE_AND_SOURCE_VERIFICATION','spec_sha256':c['source_sha256']}
    return {'recommendation':None,'reason':'No source-only candidate; contact owner for actual eligibility'}

def main():
    p=argparse.ArgumentParser();p.add_argument('--catalog',required=True);p.add_argument('--accepted',default='[]');p.add_argument('--blocked',default='[]')
    a=p.parse_args();cat=json.loads(Path(a.catalog).read_text());print(json.dumps(suggest(cat,set(json.loads(a.accepted)),set(json.loads(a.blocked))),ensure_ascii=False,indent=2))
if __name__=='__main__':main()
