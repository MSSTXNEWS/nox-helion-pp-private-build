"""NOX V135: source-verified teacher distillation corpus for ONE existing student.

Accept only licensed, nonprivate, independently checked local teacher evidence.
Do NOT invent teacher answers, call paid APIs, train weights, or export private rows.
Source groups (not only prompts) are train/holdout disjoint. Emits original V47
format + SHA manifest, never contaminates owner S03 or public GitHub.
"""
from __future__ import annotations
from collections import Counter
import hashlib,json,os,re
from pathlib import Path
from typing import Mapping

ALLOWED_LICENSES=frozenset({'owner-authored','cc0-1.0','apache-2.0','mit','cc-by-4.0',
                          'bsd-3-clause','public-domain','internal-owner-templates'})
TEACHER_ROLES=frozenset({'qwen-language','deepseek-reasoning','coder','owner-verified-knowledge'})
REQUIRE_FIELDS=frozenset({'prompt','completion','teacher_role','teacher_model_sha256',
   'source_group','source_uri','source_license','rights_verified','privacy_approved',
   'independent_validation_passed','source_content_sha256'})
_SHA=re.compile(r'^[0-9a-f]{64}$')
SENSITIVE=re.compile(r'(?i)(?:[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}|\b(?:passport|diagnosis|expediente|medical|patient|address|password|secret|api.?key|private.?key|bank|police.report)\b|\b(?:паспорт|диагноз|медицин|банк|парол|врач|полици|адрес|персонал)\w*|\b\+?[0-9][\d\s().\-]{9,}\b)')
GROUP_MIN=3
MAX_BYTES=120_000_000
MAX_RECORDS=100_000
MAX_PROMPT=5000
MAX_COMPLETION=9000

def _digest(content:str|bytes)->str:
    if isinstance(content,str):content=content.encode('utf8')
    return hashlib.sha256(content).hexdigest()

def _file_sha(path:Path)->str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for p in iter(lambda:f.read(1024*1024),b''):h.update(p)
    return h.hexdigest()

def _text_key(value:str)->str:
    return ' '.join(value.strip().casefold().split())

def check_row(row:Mapping)->dict:
    if not isinstance(row,dict) or not REQUIRE_FIELDS.issubset(row):
        raise ValueError('HOLD_TEACHER_PROVENANCE_SCHEMA')
    if len(row)>30:raise ValueError('HOLD_TEACHER_ROW_EXTENSIONS')
    prompt=row['prompt'];answer=row['completion'];origin=row['source_uri']
    group=row['source_group'];teacher=row['teacher_role']
    if not (isinstance(prompt,str) and isinstance(answer,str) and
            isinstance(origin,str) and isinstance(group,str) and
            isinstance(teacher,str)):
        raise ValueError('HOLD_TEACHER_TYPES')
    prompt=prompt.strip();answer=answer.strip()
    if not 8<=len(prompt)<=MAX_PROMPT or not 2<=len(answer)<=MAX_COMPLETION:
        raise ValueError('HOLD_TEACHER_TEXT_BOUNDS')
    if len(prompt.encode('utf8'))+len(answer.encode('utf8'))>30000:
        raise ValueError('HOLD_TEACHER_BYTE_BOUNDS')
    if SENSITIVE.search(prompt) or SENSITIVE.search(answer):
        raise ValueError('HOLD_TEACHER_PRIVATE_DATA')
    if not 10<=len(origin)<=300 or not 8<=len(group)<=150:
        raise ValueError('HOLD_TEACHER_SOURCE_GROUP')
    if SENSITIVE.search(origin) or SENSITIVE.search(group):
        raise ValueError('HOLD_TEACHER_PRIVATE_SOURCE')
    if teacher not in TEACHER_ROLES:
        raise ValueError('HOLD_TEACHER_UNKNOWN_ROLE')
    if not isinstance(row['source_license'],str) or row['source_license'].lower() not in ALLOWED_LICENSES:
        raise ValueError('HOLD_TEACHER_LICENSE')
    if any(row.get(k) is not True for k in
           ('rights_verified','privacy_approved','independent_validation_passed')):
        raise ValueError('HOLD_TEACHER_UNVERIFIED_ANSWER_OR_PERMISSION')
    if row.get('private_owner_s03_row') is True or row.get('origin_personal_document') is True:
        raise ValueError('HOLD_TEACHER_ORIGIN_OWNER_RECORD')
    if row.get('training_allowed') is not True:
        raise ValueError('HOLD_TEACHER_TRAINING_CONSENT')
    if not _SHA.fullmatch(str(row['teacher_model_sha256'])):
        raise ValueError('HOLD_TEACHER_MODEL_SHA')
    actual=_digest(prompt+'\n'+answer)
    if actual!=row['source_content_sha256']:
        raise ValueError('HOLD_TEACHER_PAIR_SHA')
    return {
      'prompt':prompt,'completion':answer,'source_uri':origin,
      'teacher_role':teacher,'teacher_model_sha256':row['teacher_model_sha256'],
      'source_group':group,'rights_verified':True,'privacy_approved':True,
      'rights_basis':row['source_license'].lower(),
      'validation_passed':True,'source_content_sha256':actual,
      'external_publication_allowed':False
    }

def split_group(group:str)->str:
    """A source group stays entirely within train or holdout, preventing leakage."""
    v=int.from_bytes(hashlib.sha256(group.encode('utf8')).digest()[:8],'big')
    return 'holdout' if v%5==0 else 'train'

def build(source:Path,outdir:Path,*,minimum_train:int=300,minimum_holdout:int=30)->dict:
    source,outdir=Path(source),Path(outdir)
    if not source.is_file() or source.is_symlink() or source.stat().st_size>MAX_BYTES:
        raise ValueError('HOLD_TEACHER_SOURCE_FILE')
    if outdir.exists() or not outdir.parent.is_dir() or outdir.parent.is_symlink():
        raise ValueError('HOLD_OUTPUT_DESTINATION_CONFLICT')
    if type(minimum_train) is not int or type(minimum_holdout) is not int or minimum_train<4 or minimum_holdout<4:
        raise ValueError('HOLD_MINIMUM_SCHEMA')
    # No outputs are created until full validation and all split constraints pass.
    seen_prompt=set();seen_exact=set();rows={'train':[],'holdout':[]};groups={'train':set(),'holdout':set()}
    roles=Counter();all_groups=Counter();accepted=0
    with source.open('rt',encoding='utf8') as f:
        for line in f:
            if not line.strip():continue
            if len(line)>50000:raise ValueError('HOLD_LONG_TEACHER_LINE')
            try:obj=json.loads(line)
            except ValueError as ex:raise ValueError('HOLD_INVALID_TEACHER_JSON') from ex
            row=check_row(obj)
            prompt_key=_digest(_text_key(row['prompt']))
            if prompt_key in seen_prompt:
                raise ValueError('HOLD_DUPLICATE_TRAIN_OR_HOLDOUT_PROMPT')
            seen_prompt.add(prompt_key)
            lesson_key=_digest(row['prompt']+'\n'+row['completion'])
            if lesson_key in seen_exact:raise ValueError('HOLD_DUPLICATE_LESSON')
            seen_exact.add(lesson_key)
            lane=split_group(row['source_group'])
            groups[lane].add(row['source_group'])
            all_groups[row['source_group']]+=1
            roles[row['teacher_role']]+=1
            rows[lane].append(row);accepted+=1
            if accepted>MAX_RECORDS:raise ValueError('HOLD_TEACHER_CORPUS_TOO_LARGE')
    if (len(rows['train'])<minimum_train or len(rows['holdout'])<minimum_holdout
        or groups['train'] & groups['holdout']):
        raise ValueError('HOLD_SOURCE_DISJOINT_TRAIN_HOLDOUT_COUNTS')
    if len(set(roles))<2 or len(all_groups)<GROUP_MIN:
        raise ValueError('HOLD_INSUFFICIENT_INDEPENDENT_TEACHERS_OR_SOURCES')
    source_sha=_file_sha(source)
    outdir.mkdir(mode=0o700)
    try:
        hashes={}
        for split in ('train','holdout'):
            target=outdir/(split+'.jsonl')
            with target.open('x',encoding='utf8') as f:
                os.chmod(target,0o600)
                for row in sorted(rows[split],key=lambda r:(_digest(r['prompt']),r['source_group'])):
                    f.write(json.dumps(row,sort_keys=True,ensure_ascii=False,separators=(',',':'))+'\n')
                f.flush();os.fsync(f.fileno())
            hashes[split]=_file_sha(target)
        report={'schema':'NOX_V135_VERIFIED_TEACHER_DISTILL_CORPUS_V1',
                'source_sha256':source_sha,
                'train_sha256':hashes['train'],
                'holdout_sha256':hashes['holdout'],
                'train_rows':len(rows['train']),
                'holdout_rows':len(rows['holdout']),
                'source_groups_disjoint':True,
                'teacher_roles':dict(sorted(roles.items())),
                'teacher_lanes_verified':len(roles),
                'private_examples_exported':False,
                'original_owner_s03_modified':False,
                'teacher_models_downloaded':False,'student_weights_changed':False,
                'optimizer_steps_verified':0,'training_started':False,
                'release_status':'TRAINSET_READY_NOT_MODEL_TRAINED'}
        target=outdir/'manifest.json'
        with target.open('x',encoding='utf8') as f:
            os.chmod(target,0o600)
            json.dump(report,f,indent=2,sort_keys=True);f.write('\n')
            f.flush();os.fsync(f.fileno())
        if any(_file_sha(outdir/(part+'.jsonl'))!=hashes[part] for part in hashes):
            raise RuntimeError('HOLD_DATASET_AFTER_WRITE_SHA')
        return report
    except Exception:
        # Preserve any partially written files for audit; no deletion of user work.
        raise
