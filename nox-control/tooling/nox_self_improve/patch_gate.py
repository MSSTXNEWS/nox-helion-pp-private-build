#!/usr/bin/env python3
"""Controlled self-writing patch gate. Default = verify/dry-run; never auto-publish.

A model may propose a unified diff but it cannot authorize its own change. Apply requires
trusted owner approval record, expected clean HEAD, SHA of exact patch and explicit --apply.
Production deployment, source merge and native acceptance are intentionally separate.
"""
from __future__ import annotations
import argparse,hashlib,json,subprocess,sys
from pathlib import Path

def call(args,cwd,timeout=45):
    return subprocess.run(args,cwd=cwd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=timeout)

def main():
    p=argparse.ArgumentParser();p.add_argument('--repo',required=True);p.add_argument('--patch',required=True)
    p.add_argument('--expected-head',required=True);p.add_argument('--approval-json',default='');p.add_argument('--apply',action='store_true')
    p.add_argument('--test-path',default='',help='Only a reviewed local test path; one targeted test through Python unittest')
    a=p.parse_args();repo=Path(a.repo).resolve();patch=Path(a.patch).resolve();
    if not repo.is_dir() or not patch.is_file():p.error('repository/patch does not exist')
    sha=hashlib.sha256(patch.read_bytes()).hexdigest()
    head=call(['git','rev-parse','HEAD'],repo)
    if head.returncode or head.stdout.strip()!=a.expected_head:sys.exit('HOLD_EXPECTED_HEAD_MISMATCH')
    clean=call(['git','status','--porcelain'],repo)
    if clean.returncode or clean.stdout.strip():sys.exit('HOLD_DIRTY_CHECKOUT')
    chk=call(['git','apply','--check',str(patch)],repo)
    if chk.returncode:sys.exit('HOLD_PATCH_CHECK: '+chk.stderr[:300])
    out={'patch_sha256':sha,'head':a.expected_head,'dry_run':not a.apply,'git_apply_check':'PASS',
         'native_acceptance':'NOT_ATTEMPTED','stop_lease_resources':'REQUIRE_SEPARATE_CHECK'}
    if a.apply:
        if not a.approval_json:sys.exit('HOLD_OWNER_APPROVAL_REQUIRED')
        approval=json.loads(Path(a.approval_json).read_text())
        if not (approval.get('approved_by_owner') is True and approval.get('approved_patch_sha256')==sha and approval.get('approved_head')==a.expected_head):
            sys.exit('HOLD_INVALID_OWNER_APPROVAL')
        if not approval.get('stop_lease_gate_verified') or not approval.get('rollback_ready'):
            sys.exit('HOLD_STOP_LEASE_OR_ROLLBACK_UNVERIFIED')
        act=call(['git','apply','--index',str(patch)],repo)
        if act.returncode:sys.exit('HOLD_GIT_APPLY_FAILED: '+act.stderr[:300])
        out['applied_to_local_branch']=True
        if a.test_path:
            target=(repo/a.test_path).resolve()
            if not str(target).startswith(str(repo)+'/') or not target.is_file() or target.suffix!='.py':
                call(['git','apply','--reverse','--index',str(patch)],repo)
                sys.exit('HOLD_TEST_PATH_NOT_ALLOWED')
            test=call([sys.executable,'-m','unittest',a.test_path],repo,timeout=120)
            out['one_targeted_test']='PASS' if test.returncode==0 else 'FAIL'
            if test.returncode:
                reverse=call(['git','apply','--reverse','--index',str(patch)],repo)
                out['rollback']='SUCCESS' if reverse.returncode==0 else 'REQUIRES_MANUAL_RECOVERY'
                print(json.dumps(out,ensure_ascii=False,indent=2));sys.exit(2)
        out['native_acceptance']='NOT_ATTEMPTED_NEEDS_INDEPENDENT_VERIFIER'
    print(json.dumps(out,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
