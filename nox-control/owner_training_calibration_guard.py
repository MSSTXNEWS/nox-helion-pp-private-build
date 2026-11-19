"""Apply the reviewed disk-pause algorithm to a generic positive calibration.

The original disk guard remains byte-identical. Only its admission and budget
callbacks are replaced inside this explicitly pinned wrapper module.
"""
import hashlib
import os
from pathlib import Path
import re
import stat
import sys
import types

ROOT=Path('/root/nox');SCRIPTS=ROOT/'scripts';STATE=ROOT/'state'
BASE_SHA='9fab629c442e572f89dac9f078e43d505c7d93c9feb94ebc34182c56ca5b94e8'
PROOF_SHA='e8a804a0e9450f4c69aa04c6b8d3daa7feecfa75b934343d13459b3ade30a63d'
SCHEMA='NOX_OWNER_CALIBRATED_TRAINING_DISK_GUARD_V1'
MARKER='NOX_OWNER_CALIBRATED_DISK_GUARD_BIND_V1'
STATUS=STATE/'owner_training_calibration_disk_guard.json'
_LOADED=[]


def fail(code):raise RuntimeError(code)
def source(name,pin):
    path=SCRIPTS/(name+'.py')
    if any(p.is_symlink() for p in (*path.parents,path)):fail('HOLD_CALIBRATED_GUARD_SOURCE_PATH')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as stream:
        info=os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or not 0<info.st_size<=262144:fail('HOLD_CALIBRATED_GUARD_SOURCE_SIZE')
        raw=stream.read(262145)
    if hashlib.sha256(raw).hexdigest()!=pin:fail('HOLD_CALIBRATED_GUARD_SOURCE_PIN')
    return raw,path
def runtime():
    rows=[('owner_training_disk_guard',BASE_SHA),('owner_training_calibration_proof',PROOF_SHA)]
    checked=[(name,*source(name,pin)) for name,pin in rows]
    if not _LOADED:
        modules=[]
        for name,raw,path in checked:
            alias='_nox_calibrated_guard_'+name;module=types.ModuleType(alias);module.__file__=str(path)
            sys.modules[alias]=module;exec(compile(raw,str(path),'exec'),module.__dict__);modules.append(module)
        base,proof=modules;base.SCHEMA=SCHEMA;base.STATUS=STATUS
        base.admission=admission;base.checkpoint_budget=checkpoint_budget
        _LOADED.extend((base,proof))
    return tuple(_LOADED)


def admission(context):
    _,proof=runtime();return proof.continuation_context(context)
def checkpoint_budget(lineage,first):
    base,proof=runtime();return budget_for(lineage,first,base,proof)
def budget_for(lineage,first,base,proof):
    """The operator can preflight the same budget before installing modules."""
    metadata=proof.checkpoint(first,rehash=False)
    targets=lineage.get('targets') or {};parameters=targets.get('trainable_parameters')
    if type(parameters) is not int or not 1<=parameters<=2_000_000_000 or targets.get('trainable_dtype')!='float32':
        fail('HOLD_CALIBRATED_GUARD_PARAMETER_COUNT')
    path=proof.OUTPUT/('checkpoint-'+str(metadata['global_step']));observed=0
    for name in base.NAMES:
        file=base.plain(path/name);fd=os.open(file,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        try:
            info=os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or not 0<info.st_size<=8*1024**3:
                fail('HOLD_CALIBRATED_GUARD_CHECKPOINT_SIZE')
            observed+=info.st_size
        finally:os.close(fd)
    upper=max(parameters*16+128*1024**2,(observed*3+1)//2)
    return {'trainable_parameters':parameters,'observed_checkpoint_bytes':observed,
        'checkpoint_global_step':metadata['global_step'],'checkpoint_budget_bytes':upper,
        'disk_reserve_bytes':base.RESERVE_BYTES,'required_free_bytes':base.RESERVE_BYTES+2*upper+256*1024**2}
def trainer_process():return runtime()[0].trainer_process()
def latch_pause(context,budget,process):return runtime()[0].latch_pause(context,budget,process)
def tick(context):return runtime()[0].tick(context)
def plain(path):return runtime()[0].plain(path)
def read(path,limit=262144):return runtime()[0].read(path,limit)
def document(path,limit=262144):return runtime()[0].document(path,limit)


def binding_text(context):
    if (not isinstance(context,dict) or set(context)!={'request','source_sha','receipt_sha256'}
            or not re.fullmatch('[0-9]{1,24}',str(context.get('request','')))
            or not re.fullmatch('[a-f0-9]{40}',str(context.get('source_sha','')))
            or not re.fullmatch('[a-f0-9]{64}',str(context.get('receipt_sha256','')))):
        fail('HOLD_CALIBRATED_GUARD_CONTEXT')
    return ('# '+MARKER+'\nimport owner_training_calibration_guard\n'
            'owner_training_calibration_guard.bind_scheduler(globals(), '+repr(dict(sorted(context.items())))+')\n\n')
def patch_scheduler(source_text,expected_sha,context):
    if hashlib.sha256(source_text.encode()).hexdigest()!=expected_sha:fail('HOLD_CALIBRATED_GUARD_SCHEDULER_PREIMAGE')
    if MARKER in source_text or 'NOX_OWNER_TRAINING_DISK_GUARD_BIND_V1' in source_text:
        fail('HOLD_CALIBRATED_GUARD_ALREADY_BOUND')
    anchor='if __name__ == "__main__":\n    main()\n'
    if source_text.count(anchor)!=1:fail('HOLD_CALIBRATED_GUARD_SCHEDULER_ANCHOR')
    updated=source_text.replace(anchor,binding_text(context)+anchor,1)
    compile(updated,'nox_priority_scheduler.py','exec');return updated
def bind_scheduler(namespace,context):
    binding_text(context)
    if namespace.get('_owner_training_calibration_guard_bound'):return
    runtime()[0].bind_scheduler(namespace,context)
    namespace['_owner_training_calibration_guard_bound']=True
