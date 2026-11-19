#!/usr/bin/env python3
"""Read-only JSONL delimiter diagnostic; never emits any training text."""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time

ROOT=Path('/root/nox');OUTPUT=ROOT/'lora/qlora_t866u/runs_owner_hybrid'
PREPARATION_SHA='bc4edf4bccf50c45ef84da51acb975607d0e86199e8c0301b1091121d879989a'
DATASET_BYTES=305243573
SCHEMA='NOX_TRAINING_CORPUS_DELIMITER_PROBE_V1'
SEPARATORS={'U+0085':'\u0085','U+2028':'\u2028','U+2029':'\u2029',
            'U+000B':'\x0b','U+000C':'\x0c','U+001C':'\x1c','U+001D':'\x1d','U+001E':'\x1e','U+000D':'\r'}


def fail(code):raise RuntimeError(code)
def digest(raw):return hashlib.sha256(raw).hexdigest()
def identity(info):return info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns
def plain(path):
    path=Path(path)
    if any(p.is_symlink() for p in (*path.parents,path)):fail('HOLD_CORPUS_PROBE_SYMLINK')
    return path
def read_small(path,limit=64000):
    fd=os.open(plain(path),os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as stream:
        info=os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size>limit:fail('HOLD_CORPUS_PROBE_METADATA_SCOPE')
        raw=stream.read(limit+1)
        if len(raw)!=info.st_size:fail('HOLD_CORPUS_PROBE_METADATA_RACE')
        return raw


def scan(path,expected_sha,expected_bytes,seconds=40):
    if not re.fullmatch('[a-f0-9]{64}',str(expected_sha)) or type(expected_bytes) is not int or not 1<=expected_bytes<=512*1024**2:
        fail('HOLD_CORPUS_PROBE_EXPECTED_IDENTITY')
    path=plain(path);fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    proof={'schema':SCHEMA,'state':'SCANNING','source_bytes':expected_bytes,'private_text_exported':False,
        'mutations':0,'actual_lf_records':0,'actual_lf_valid_records':0,'actual_lf_invalid_records':0,
        'legacy_splitlines_segments':0,'legacy_invalid_segments':0,'first_lf_failure':None,
        'first_legacy_failure':None,'separator_counts':{name:0 for name in SEPARATORS}}
    value=hashlib.sha256();deadline=time.monotonic()+seconds
    with os.fdopen(fd,'rb') as stream:
        before=os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size!=expected_bytes:fail('HOLD_CORPUS_PROBE_DATASET_SCOPE')
        while True:
            if time.monotonic()>deadline:fail('HOLD_CORPUS_PROBE_TIME_BOUND')
            raw=stream.readline(4*1024**2+1)
            if not raw:break
            if len(raw)>4*1024**2:fail('HOLD_CORPUS_PROBE_RECORD_BOUND')
            value.update(raw);proof['actual_lf_records']+=1
            try:
                text=raw.decode('utf8');decoded=json.loads(text)
                if not isinstance(decoded,dict) or set(decoded)!={'text'} or not isinstance(decoded['text'],str):
                    raise ValueError('schema')
                proof['actual_lf_valid_records']+=1
            except (UnicodeError,ValueError) as exc:
                proof['actual_lf_invalid_records']+=1
                if proof['first_lf_failure'] is None:
                    proof['first_lf_failure']={'record':proof['actual_lf_records'],'exception':type(exc).__name__}
                try:text=raw.decode('utf8')
                except UnicodeError:continue
            for name,separator in SEPARATORS.items():proof['separator_counts'][name]+=text.count(separator)
            for segment in text.splitlines():
                proof['legacy_splitlines_segments']+=1
                try:json.loads(segment)
                except ValueError as exc:
                    proof['legacy_invalid_segments']+=1
                    if proof['first_legacy_failure'] is None:
                        proof['first_legacy_failure']={'segment':proof['legacy_splitlines_segments'],
                            'lf_record':proof['actual_lf_records'],'exception':type(exc).__name__}
        after=os.fstat(stream.fileno());named=path.stat(follow_symlinks=False)
        if identity(before)!=identity(after) or identity(after)!=identity(named):fail('HOLD_CORPUS_PROBE_DATASET_RACE')
    if value.hexdigest()!=expected_sha:fail('HOLD_CORPUS_PROBE_DATASET_SHA')
    proof.update(state='EXACT_DATASET_DELIMITERS_VERIFIED',dataset_sha256=expected_sha,full_sha256_verified=True,
        lf_jsonl_valid=proof['actual_lf_records']>0 and proof['actual_lf_invalid_records']==0,
        legacy_splitlines_invalid=proof['legacy_invalid_segments']>0)
    return proof


def read_only_probe():
    raw=read_small(OUTPUT/'owner_preparation.json')
    if digest(raw)!=PREPARATION_SHA:fail('HOLD_CORPUS_PROBE_PREPARATION_SHA')
    preparation=json.loads(raw)
    if preparation.get('schema')!='NOX_T866U_FP32_ADAPTER_CONTINUATION_V1':fail('HOLD_CORPUS_PROBE_PREPARATION_SCHEMA')
    return scan(OUTPUT/'training_text.jsonl',preparation.get('dataset_sha256'),DATASET_BYTES)


if __name__=='__main__':
    try:
        print('NOX_MAINT_REPAIR='+json.dumps({'kind':'training_corpus_delimiter_probe','data':read_only_probe()},separators=(',',':')),flush=True)
        print('NOX_MAINT_REPAIR_COMPLETE=true',flush=True)
    except Exception as exc:
        reason=str(exc);reason=reason if re.fullmatch('HOLD_[A-Z0-9_]+',reason) else type(exc).__name__
        print('NOX_MAINT_REPAIR='+json.dumps({'kind':'training_corpus_delimiter_probe_hold','data':{'reason':reason}},separators=(',',':')),flush=True)
        raise SystemExit(2)
