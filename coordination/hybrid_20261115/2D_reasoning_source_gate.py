"""NOX 2D: offline, source-only licence and holdout review of already extracted reasoning rows.
Not a native training admission; never downloads, executes code, modifies S03 or models.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import unicodedata

REV = '20a1ca19c0d050fe9057fc08339d6b370ec1c67a'
SHARD = 'split_0/train-00000-of-00030.parquet'
SHA = 'e4f4ee6da02d2b590e4746056e23c3ebabba638f1033a7263530a399938513f2'
SIZE = 242388599
REPO = 'nvidia/OpenCodeReasoning'
ALLOWED_LICENSE_LABELS = {'cc-by-4.0','apache-2.0','mit'}
HEX = re.compile('[0-9a-f]{64}\\Z')

class Hold(ValueError): pass

def need(ok, reason):
    if not ok: raise Hold('HOLD_'+reason)

def atom(x):
    need(type(x) is str and 0 < len(x.strip()) <= 256 and not any(ord(c) < 32 for c in x),'MISSING_OR_UNSAFE_FIELD')
    return x.strip()

def group_hash(row):
    # Dataset and source-platform identifiers are case-insensitive; original
    # question ID is case-sensitive. This is not semantic cross-dataset dedup.
    fields=(atom(row['dataset']).casefold(),atom(row['source']).casefold(),atom(row['id']))
    return hashlib.sha256(json.dumps(fields,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()

def question_sha256(value):
    """Canonical exact-prompt fingerprint (not a semantic equivalence proof)."""
    need(type(value) is str and 0 < len(value) < 2_000_000,'INVALID_QUESTION_TEXT')
    # Reject Unicode format controls (Cf) before hashing: zero-width joiners,
    # soft hyphen and bidi overrides can make visually identical questions hash
    # differently, defeating an exact-text sealed holdout. Never log raw text.
    need(not any(unicodedata.category(ch) == 'Cf' for ch in value),
         'UNSAFE_QUESTION_FORMAT_CONTROL')
    canonical=' '.join(unicodedata.normalize('NFKC',value).casefold().split())
    need(bool(canonical) and canonical!='-','UNRESOLVED_QUESTION')
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()

def validate(rows, catalogue, policy, sealed_holdout, sealed_holdout_questions):
    """Review metadata ONLY; owner-authentic licence review and Parquet SHA are external."""
    need(type(catalogue) is dict and catalogue.get('schema')=='NOX_AUTO_2D_IMMUTABLE_PUBLIC_EVIDENCE_V2','CATALOGUE')
    src=catalogue.get('reasoning_dataset_research_only')
    need(type(src) is dict and src.get('repo_id')==REPO and src.get('revision')==REV,'REVISION')
    need(src.get('training_authorized') is False and src.get('quality_privacy_license_review_required') is True,'NO_AUTOMATIC_TRAIN_APPROVAL')
    shard=src.get('file')
    need(type(shard) is dict and (shard.get('path'),shard.get('size_bytes'),shard.get('sha256'))==(SHARD,SIZE,SHA),'SHARD_POINTER')
    need(type(policy) is dict and policy.get('schema')=='NOX_OWNER_REVIEWED_SOURCE_LICENSES_V1','REVIEW_POLICY')
    need(policy.get('repository')==REPO and policy.get('revision')==REV,'POLICY_REVISION')
    grants=policy.get('approved_triplets')
    need(type(grants) is list and bool(grants),'EMPTY_LICENSE_REVIEW')
    allowed=set()
    for item in grants:
        need(type(item) is dict and item.get('source_license_reviewed') is True and item.get('attribution_reviewed') is True,'NO_SOURCE_RIGHTS_REVIEW')
        triple=tuple(atom(item.get(k)).casefold() for k in ('dataset','platform','license'))
        need(triple[2] in ALLOWED_LICENSE_LABELS and triple not in allowed,'INVALID_REVIEW_ENTRY')
        allowed.add(triple)
    need(type(sealed_holdout) is set and bool(sealed_holdout) and all(type(x) is str and HEX.fullmatch(x) for x in sealed_holdout),'NO_SEALED_HOLDOUT_GROUPS')
    need(type(sealed_holdout_questions) is set and bool(sealed_holdout_questions)
         and all(type(x) is str and HEX.fullmatch(x) for x in sealed_holdout_questions),
         'NO_SEALED_HOLDOUT_QUESTION_SHA256')
    answer_pairs=set();families=set();count=0
    question_by_family={}
    family_by_question={}
    for row in rows:
        need(type(row) is dict,'ROW_SCHEMA')
        triple=tuple(atom(row.get(k)).casefold() for k in ('dataset','source','license'))
        need(triple[2] in ALLOWED_LICENSE_LABELS and triple in allowed,'UNREVIEWED_ROW_LICENSE_OR_SOURCE')
        # 'split' in this dataset is the original question collection split,
        # not the OpenCodeReasoning HF split_0 folder.
        need(atom(row.get('split')).casefold()=='train','ORIGINAL_TEST_OR_VALIDATION_LEAK')
        question,answer=row.get('input'),row.get('output')
        need(type(question) is str and type(answer) is str and question.strip() not in ('','-') and answer.strip() not in ('','-'),'UNRESOLVED_QUESTION_OR_ANSWER')
        need(len(question)<2_000_000 and len(answer)<2_000_000,'OVERSIZE_TEXT')
        g=group_hash(row)
        need(g not in sealed_holdout,'HOLDOUT_FAMILY_OVERLAP')
        question_digest=question_sha256(question)
        need(question_digest not in sealed_holdout_questions,'HOLDOUT_QUESTION_CONTENT_OVERLAP')
        # Same dataset/source/id may have multiple independent completions, but
        # must never silently designate two different questions as one problem.
        # Exact same questions with different IDs are likewise not independent.
        existing=question_by_family.setdefault(g,question_digest)
        need(existing==question_digest,'SOURCE_ID_REUSED_FOR_DIFFERENT_QUESTION')
        old_family=family_by_question.setdefault(question_digest,g)
        need(old_family==g,'DUPLICATE_QUESTION_ACROSS_SOURCE_IDS')
        # Multiple answers per problem are valid; same answer on same problem
        # is a duplicate, however. Never log text or inferred personal data.
        pair=g+':'+hashlib.sha256(answer.encode()).hexdigest()
        need(pair not in answer_pairs,'DUPLICATE_COMPLETION')
        answer_pairs.add(pair);families.add(g);count+=1
    need(count>0,'EMPTY_ROWS')
    return {'state':'SOURCE_METADATA_REVIEW_ONLY','reviewed_rows':count,'distinct_question_families':len(families),
            'exact_question_fingerprints':len(family_by_question),
            'semantic_cross_language_disjointness_independently_verified':False,
            'parquet_payload_sha_verified':False,'original_source_rights_independently_verified':False,
            'native_downloaded':False,'native_training_verified':False,'merge_approved':False}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for flag in ('catalogue','rows-jsonl','reviewed-policy','sealed-holdout-groups','sealed-holdout-question-sha256'):
        p.add_argument('--'+flag,required=True,type=Path)
    a=p.parse_args()
    try:
        cat=json.loads(a.catalogue.read_text());pol=json.loads(a.reviewed_policy.read_text())
        holdout=set(json.loads(a.sealed_holdout_groups.read_text()))
        holdout_questions=set(json.loads(a.sealed_holdout_question_sha256.read_text()))
        def stream():
            with a.rows_jsonl.open(encoding='utf-8') as f:
                for line in f:
                    if line.strip(): yield json.loads(line)
        print(json.dumps(validate(stream(),cat,pol,holdout,holdout_questions),sort_keys=True));return 0
    except (OSError,ValueError,TypeError,KeyError) as e:
        print(json.dumps({'state':'HOLD','reason':str(e) if isinstance(e,Hold) else type(e).__name__}));return 2
if __name__=='__main__':raise SystemExit(main())
