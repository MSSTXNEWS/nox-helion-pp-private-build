#!/usr/bin/env python3
"""Read-only cgroup and process mapped-RAM census for a single owner request.

Never call a mutable kernel API, delete files, stop services or read argv/env/secrets.
Only fixed /proc and /sys/fs/cgroup counters, and exact protected Supervisor PIDs.
"""
from __future__ import annotations
import json,os,re,stat,subprocess,time
from pathlib import Path

SERVICES=('nox-ds41-8098','nox-proxy','nox-web29-18775','nox-dispatcher-t855u')
ROOT=Path('/proc')
CG=Path('/sys/fs/cgroup')
STAGE='INIT'

class Hold(RuntimeError):pass
def need(ok,code):
    if not ok:raise Hold('HOLD_NOX_MEMORY_CENSUS_'+code)
def ascii_read(path,limit=8192):
    fd=os.open(path,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as f:
        before=os.fstat(f.fileno())
        need(stat.S_ISREG(before.st_mode),'FILE_TYPE')
        raw=f.read(limit+1)
    need(len(raw)<=limit,'FILE_BOUND')
    return raw.decode('ascii','strict')
def fields(raw):
    out={}
    for line in raw.splitlines():
        if ':' in line:
            key,rest=line.split(':',1)
            m=re.fullmatch(r'\s*([0-9]+)\s*kB\s*',rest)
            if m:out[key]=int(m[1])
    return out
def processes():
    result={}
    for name in SERVICES:
        p=subprocess.run(['supervisorctl','status',name],capture_output=True,text=True,timeout=8)
        m=re.match('^'+re.escape(name)+r'\s+RUNNING\s+pid\s+([1-9][0-9]*),',p.stdout.strip())
        need(p.returncode==0 and m is not None,'PROTECTED_NOT_RUNNING')
        pid=int(m[1])
        statline=ascii_read(ROOT/str(pid)/'stat',4096)
        tail=statline.rsplit(') ',1)
        need(len(tail)==2 and len(tail[1].split())>19,'PROTECTED_PROC_STAT')
        tick=int(tail[1].split()[19])
        result[name]={'pid':pid,'start_ticks':tick}
    return result
def cgroup():
    current=int(ascii_read(CG/'memory.current',40))
    maximum=int(ascii_read(CG/'memory.max',40))
    need(0<current<maximum,'CGROUP_MEMORY_LIMIT')
    statmap={}
    for line in ascii_read(CG/'memory.stat',16000).splitlines():
        p=line.split()
        need(len(p)==2 and p[1].isdecimal(),'CGROUP_STATS')
        statmap[p[0]]=int(p[1])
    return {'current':current,'max':maximum,'free':maximum-current,
            'file_bytes':statmap.get('file'),'file_mapped_bytes':statmap.get('file_mapped'),
            'shmem_bytes':statmap.get('shmem'),'anon_bytes':statmap.get('anon'),
            'inactive_file_bytes':statmap.get('inactive_file')}
def census():
    global STAGE
    STAGE='OWNER_ID'
    need(re.fullmatch(r'[0-9]{1,24}',os.getenv('NOX_OWNER_REQUEST_ID','')) is not None,'OWNER_ID')
    need(re.fullmatch(r'[a-f0-9]{40}',os.getenv('NOX_OWNER_SOURCE_SHA','')) is not None,'OWNER_SHA')
    STAGE='PROTECTED'
    pins=processes()
    STAGE='MEMORY'
    before=cgroup()
    STAGE='PROC_SCAN'
    found=[];count=0;skip=0
    for e in ROOT.iterdir():
        if not e.name.isdecimal():continue
        count+=1
        need(count<=10000,'PROC_BOUND')
        pid=int(e.name)
        try:
            status=ascii_read(e/'status',16384)
            lines=status.splitlines()
            name=next((l[5:].strip() for l in lines if l.startswith('Name:')),None)
            if not name or not re.fullmatch(r'[A-Za-z0-9_.:/+-]{1,64}',name):name='UNKNOWN'
            v=fields(status)
            rss=v.get('VmRSS',0)
            if rss<256*1024:continue
            statline=ascii_read(e/'stat',4096)
            tail=statline.rsplit(') ',1)
            if len(tail)!=2 or len(tail[1].split())<=19:continue
            tick=int(tail[1].split()[19])
            protected=next((label for label,x in pins.items() if x['pid']==pid and x['start_ticks']==tick),None)
            found.append({'pid':pid,'start_ticks':tick,'comm':name,'rss_kib':rss,
                          'rss_file_kib':v.get('RssFile'),'rss_shmem_kib':v.get('RssShmem'),
                          'rss_anon_kib':v.get('RssAnon'),'vm_swap_kib':v.get('VmSwap'),
                          'protected_service':protected})
        except (OSError,ValueError,UnicodeDecodeError,Hold):
            skip+=1
    found.sort(key=lambda x:-x['rss_kib'])
    selected=found[:24]
    STAGE='PSS_SCAN'
    for p in selected[:12]:
        try:
            rollup=ascii_read(ROOT/str(p['pid'])/'smaps_rollup',65536)
            v=fields(rollup)
            p['pss_kib']=v.get('Pss')
            p['pss_file_kib']=v.get('Pss_File')
            p['pss_shmem_kib']=v.get('Pss_Shmem')
            p['private_clean_kib']=v.get('Private_Clean')
            p['private_dirty_kib']=v.get('Private_Dirty')
        except (OSError,ValueError,UnicodeDecodeError,Hold):
            p['pss_state']='NOT_AVAILABLE'
    STAGE='POST'
    after=cgroup()
    need(processes()==pins and after['max']==before['max'],'PROTECTED_CHANGED')
    return {'schema':'NOX_OWNER_MAPPED_RAM_CENSUS_V1','read_only':True,'raw_free_before':before['free'],
        'raw_free_after':after['free'],'memory':after,'count_proc_scanned':count,
        'count_skipped':skip,'large_process_count':len(found),'top_processes':selected,
        'services_unchanged':True,'no_process_stopped':True,'no_file_deleted':True,
        'no_s03_weights_or_queue_write':True}
if __name__=='__main__':
    try:
        payload=census()
        print('NOX_MAINT_MAPPED_CENSUS='+json.dumps(payload,sort_keys=True,separators=(',',':')),flush=True)
        print('NOX_MAINT_REPAIR_COMPLETE=true',flush=True)
    except Exception as err:
        code=str(err)
        if not re.fullmatch(r'HOLD_NOX_MEMORY_CENSUS_[A-Z0-9_]{1,100}',code):
            code='HOLD_NOX_MEMORY_CENSUS_INTERNAL_'+STAGE+'_'+type(err).__name__.upper()
        print('NOX_MAINT_MAPPED_CENSUS='+json.dumps({'status':'HOLD','reason':code},sort_keys=True),flush=True)
        raise SystemExit(2)
