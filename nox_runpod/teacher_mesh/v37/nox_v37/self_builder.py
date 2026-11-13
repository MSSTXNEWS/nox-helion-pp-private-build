"""NOX self-development change-review gate: propose, verify source and tests, never merge own PR."""
from __future__ import annotations
import hashlib,re
from pathlib import PurePosixPath

ALLOWED_PREFIX=('nox_runpod/teacher_mesh/','ui/','web/','tests/')
BLOCKED_PREFIX=('.github/workflows/','.git/','secrets/','credentials/','production/')

def review(candidate, *, current_head, independent_test_receipt=None):
    reasons=[]
    if not isinstance(candidate,dict):return {'state':'HOLD','reasons':['MALFORMED_CANDIDATE']}
    if not re.fullmatch(r'[0-9a-f]{40}',current_head):reasons.append('LIVE_GIT_HEAD_REQUIRED')
    if candidate.get('expected_head')!=current_head:reasons.append('BASE_SHA_DRIFT')
    paths=candidate.get('changed_paths') or []
    if not isinstance(paths,list) or not paths or len(paths)>40:reasons.append('INVALID_PATCH_SCOPE')
    else:
        for path in paths:
            if not isinstance(path,str) or path.startswith('/') or '\\' in path or '..' in PurePosixPath(path).parts:
                reasons.append('UNSAFE_PATH');break
            if not path.startswith(ALLOWED_PREFIX) or path.startswith(BLOCKED_PREFIX):
                reasons.append('OUT_OF_SCOPE_CHANGE');break
    if not re.fullmatch(r'[0-9a-f]{64}',str(candidate.get('diff_sha256',''))):reasons.append('PATCH_SHA_REQUIRED')
    if not candidate.get('owner_review_required'):reasons.append('NO_OWNER_REVIEW_GATE')
    if independent_test_receipt is None or independent_test_receipt.get('source_head')!=current_head:
        reasons.append('INDEPENDENT_TEST_NOT_CONFIRMED')
    elif independent_test_receipt.get('all_pass') is not True:reasons.append('TEST_FAILURE')
    return {'state':'REVIEWABLE_PR_CANDIDATE_NOT_MERGED' if not reasons else 'HOLD',
            'reasons':reasons,'auto_merged':False,'weights_changed':False}
