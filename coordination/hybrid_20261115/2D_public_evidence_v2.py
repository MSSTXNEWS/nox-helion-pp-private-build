"""NOX AUTO 2D: fail-closed check of public HF metadata pins, not native evidence.

Only source metadata is validated here. Never import/execute remote model or code files.
"""
import json
import re
import sys
from pathlib import Path

REPO_REV = re.compile(r"[0-9a-f]{40}\Z")
SHA = re.compile(r"[0-9a-f]{64}\Z")
SAFEPATH = re.compile(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*\Z")


def check(cond, msg):
    if not cond:
        raise ValueError("HOLD_" + msg)


def pin(r, size_limit=1_000_000_000):
    check(isinstance(r, dict), "FILE_SCHEMA")
    name, size, digest = r.get("path"), r.get("size_bytes"), r.get("sha256")
    check(isinstance(name,str) and SAFEPATH.fullmatch(name) and not any(p.startswith('.') for p in name.split('/')), "UNSAFE_PATH")
    check(type(size) is int and 0 < size < size_limit, "EXACT_FILE_SIZE")
    check(isinstance(digest,str) and SHA.fullmatch(digest), "MISSING_FILE_SHA")


def repo(row, required_license=None):
    check(isinstance(row,dict) and bool(row.get('repo_id')), "REPO_ID")
    check(isinstance(row.get('revision'), str) and REPO_REV.fullmatch(row['revision']), "MUTABLE_REVISION")
    check(isinstance(row.get('source'),str) and ('/'+row['revision']) in row['source'], "MUTABLE_SOURCE_LINK")
    if required_license is not None:
        check(row.get('license_card') == required_license, "LICENSE_PROVENANCE")


def validate(data):
    check(isinstance(data,dict) and data.get('schema')=='NOX_AUTO_2D_IMMUTABLE_PUBLIC_EVIDENCE_V2', "SCHEMA")
    check(data.get('instructions_version')=='0.0.6', "GUIDE_VERSION")
    check(data.get('evidence_scope')=='OFFICIAL_HF_METADATA_AND_LFS_POINTERS_ONLY', "PROVENANCE")
    check(data.get('active_nox_hf_base_verified') is False and data.get('active_nox_hf_base_revision') is None, "UNVERIFIED_BASE")
    check(data.get('owner_native_write_lease_verified') is False and data.get('independent_s03_optimizer_restore_verified') is False, "UNVERIFIED_OWNER_ADMISSION")
    for key in ('authorized_native_downloads_this_run','native_optimizer_steps_this_run','native_merges_this_run','native_files_deleted_this_run','native_freed_bytes_this_run'):
        check(type(data.get(key)) is int and data[key] == 0, "FALSE_NATIVE_CLAIM")
    adapters = data.get('adapters_research_only')
    check(isinstance(adapters,list) and len(adapters)==2, "ADAPTER_COUNT")
    expected={
      'rk500/Born-9B-Qwen3.5-9B-Preview': ('f9eff01a754f2ce1274d1edfbe861cba608165b6',116426136,'4f55e1cd99ba9c1fc92aea69aa412b8e794b56198060398140b6c6dde59f9542', 'apache-2.0'),
      '6cf/qwen35-9b-deepseek-v4-pro-agent-lora': ('494fa3e1bc0c7c0e0441cb51ef498af1f69bd5da',129020368,'9b40db78e4cfcc9c2125c4c9c13b66980011fc9d95a7807d3140e62c143a2c1c', None)
    }
    seen=set()
    for a in adapters:
        repo(a)
        x=expected.get(a['repo_id'])
        check(x is not None and a['repo_id'] not in seen, "ADAPTER_ID")
        seen.add(a['repo_id'])
        check(a['revision']==x[0] and a.get('license_card')==x[3], "ADAPTER_REV_LICENSE")
        check(a.get('declared_base')=='Qwen/Qwen3.5-9B' and a.get('base_revision_in_adapter_config') is None, "BASE_LINEAGE_NOT_PINNED")
        check(a.get('adapter_type')=='LORA' and a.get('rank')==32 and a.get('lora_alpha')==64, "LORA_CONFIG")
        targets=a.get('target_modules')
        check(isinstance(targets,list) and len(set(targets))==len(targets) and all(isinstance(t,str) and t for t in targets), "LORA_TARGETS")
        check(a.get('metadata_only') is True and a.get('merge_approved') is False, "MERGE_FORBIDDEN")
        w=a.get('weights');pin(w)
        check(w['path']=='adapter_model.safetensors' and w['size_bytes']==x[1] and w['sha256']==x[2], "ADAPTER_WEIGHT_POINTER")
    check(adapters[1].get('unsafe_metadata_filename')=='training_args.bin', "PICKLE_FILE_NOT_QUARANTINED")
    code=data.get('code_benchmark_research_only');repo(code,'cc-by-4.0')
    check(code['repo_id']=='google-research-datasets/mbpp' and code['revision']=='4bb6404fdc6cacfda99d4ac4205087b89d32030c', "MBPP_SOURCE")
    check(code.get('training_authorized') is False and code.get('locale')=='en' and 'sandbox' in code.get('split_policy',''), "BENCHMARK_CONTAMINATION")
    files=code.get('files'); check(isinstance(files,list) and len(files)==3, "MBPP_FILE_COUNT")
    expect={'train':(87223,'09d125ca31edacb7800be8c67c45abff618faf0214ff551291817d06bdb914ae'),
           'validation':(25144,'3f0ec060987432d99fe8fb409d31e6c67445b208a01741c5583517c80a10fe80'),
           'test':(115824,'566fd53060ffba5766dace1d1e2f4c38906781526de222b0dfbdbc325b696c77')}
    splits=set()
    for f in files:
        pin(f)
        split=f.get('split');check(split in expect and split not in splits, "MBPP_DUP_SPLIT")
        splits.add(split)
        check(f['path']==f'full/{split}-00000-of-00001.parquet' and (f['size_bytes'],f['sha256'])==expect[split], "MBPP_PIN_MISMATCH")
    check(splits==set(expect), "MBPP_SPLIT_MISSING")
    reasoning=data.get('reasoning_dataset_research_only');repo(reasoning,'cc-by-4.0')
    check(reasoning['repo_id']=='nvidia/OpenCodeReasoning' and reasoning['revision']=='20a1ca19c0d050fe9057fc08339d6b370ec1c67a', "REASONING_SOURCE")
    check(reasoning.get('training_authorized') is False and reasoning.get('quality_privacy_license_review_required') is True, "REASONING_REVIEW")
    pin(reasoning.get('file'))
    f=reasoning['file']
    check((f['path'], f['size_bytes'], f['sha256'])==('split_0/train-00000-of-00030.parquet',242388599,'e4f4ee6da02d2b590e4746056e23c3ebabba638f1033a7263530a399938513f2'), "REASONING_SHARD_POINTER")
    check(data.get('existing_multilingual_emotion_pins')=='coordination/hybrid_20261115/2D_pins.json', "EXISTING_PINS_LINK")
    return {'status':'SOURCE_METADATA_VALIDATED_NOT_DOWNLOADED','adapters':len(adapters),'code_files':len(files),'reasoning_shards':1,'new_metadata_bytes':sum(x['weights']['size_bytes'] for x in adapters)+sum(f['size_bytes'] for f in files)+reasoning['file']['size_bytes'],'native_downloads':0,'native_merges':0}


def main():
    path=Path(__file__).with_name('2D_public_evidence_v2.json')
    try:
        print(json.dumps(validate(json.loads(path.read_text(encoding='utf-8'))),sort_keys=True))
        return 0
    except (ValueError,OSError,TypeError) as exc:
        print(str(exc),file=sys.stderr);return 1

if __name__=='__main__':raise SystemExit(main())
