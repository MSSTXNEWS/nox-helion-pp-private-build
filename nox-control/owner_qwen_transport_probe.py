#!/usr/bin/env python3
"""Finite public transport diagnostics in an owned child; no trainer mutation.

Small metadata may be fully hashed. Shard prefixes/ranges never prove a full
download. Default proxy/TLS and the pinned loader redirect policy are retained.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import time
import types

INSTALLER = Path('/root/nox/scripts/owner_qwen_revision_install.py')
INSTALLER_SHA = '2dd28da0d4e90614dbc168e0d921022c2b95061d08e21b2f76394f2f6280c468'
SHARED_SHA = '0dbb06d3384b3436165056ccf4e35bff937fda4f85d96ab2a97ab16a6619998e'
MEMFD_SHA = '938335009efe691a9cef7b41daa7c55f3c8d3d8618a10a5eb5db125fd45afa82'
MANIFEST_SHA = '2275fc88370ca8ba409a791819e13c8ab7d4e38cce4576a13170b05bcb8b839b'
REFERENCE = {'request': '6912442714', 'source_sha': '7e27ab2ce0673205701727f4d3ef3f4a59b3d096',
             'receipt_sha256': 'c7304317a76fe08869eec9b6127ffd51107d69698e8b0ea678ae7c0f8d1e2858'}
MIB = 1024 ** 2

CHILD = r'''
import ast, concurrent.futures, fcntl, hashlib, json, os, re, sys, threading, time
import urllib.error, urllib.request
MIB = 1024 ** 2
LOCK = threading.RLock()
RESERVED = RETURNED = 0
ERROR_TYPES = {'HTTPError','URLError','TimeoutError','OSError','SSLError','SSLCertVerificationError',
 'ConnectionResetError','ConnectionAbortedError','ConnectionRefusedError','gaierror',
 'RemoteDisconnected','IncompleteRead','BadStatusLine','Hold'}
class Hold(RuntimeError): pass
def need(ok, code):
 if not ok: raise Hold(code)
def emit(value):
 with LOCK: print('NOX_TRANSPORT='+json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False),flush=True)
def error(exc):
 value=getattr(exc,'errno',None)
 if type(value) is not int: value=getattr(getattr(exc,'reason',None),'errno',None)
 return {'exception_type':type(exc).__name__ if type(exc).__name__ in ERROR_TYPES else 'OTHER_EXCEPTION',
         'errno':value if type(value) is int and -65535<=value<=65535 else None,
         'validation_code':str(exc) if isinstance(exc,Hold) and re.fullmatch('[A-Z_]{1,60}',str(exc)) else None}
def limited_read(response, count):
 global RESERVED,RETURNED
 with LOCK:
  need(0<count<=MIB and RESERVED+count<=12*MIB,'BODY_BUDGET'); RESERVED+=count
 raw=response.read(count)
 need(isinstance(raw,bytes) and len(raw)<=count,'BODY_READ_TYPE')
 with LOCK: RETURNED+=len(raw)
 return raw
def tiny_memfd(policy):
 fd=None; stage='CREATE'; result={'event':'memfd','ok':False,'synthetic':True,'bytes':MIB,'pages_retained':False}
 try:
  fd=os.memfd_create('nox-public-transport-probe',os.MFD_CLOEXEC|os.MFD_ALLOW_SEALING)
  raw=b'\0'*MIB; view=memoryview(raw); stage='WRITE'
  while view:
   count=os.write(fd,view); need(count>0,'MEMFD_WRITE'); view=view[count:]
  stage='READBACK'; os.lseek(fd,0,os.SEEK_SET); parts=[]; left=MIB
  while left:
   part=os.read(fd,left); need(bool(part),'MEMFD_READBACK'); parts.append(part); left-=len(part)
  need(hashlib.sha256(b''.join(parts)).digest()==hashlib.sha256(raw).digest() and not os.read(fd,1),'MEMFD_HASH')
  stage='SEAL'; policy['seal'](fd); need(os.fstat(fd).st_size==MIB,'MEMFD_SIZE')
  result.update(ok=True,write_readback_and_seal_verified=True)
 except Exception as exc: result.update(error(exc),stage=stage)
 finally:
  if fd is not None: os.close(fd)
 emit(result); return result
def request(policy,row,label,phase,offset=0,full=False):
 started=time.monotonic(); stage='OPEN'; response=None
 result={'event':'result','label':label,'phase':phase,'method':'GET','offset':offset,'ok':False,
  'http_status':None,'exception_type':None,'errno':None,'bytes_returned':0,
  'public_host_allowed':None,'full_file_sha_verified':False,'intentional_prefix_close':not full}
 def mark(value):
  nonlocal stage
  stage=value; emit({'event':'stage','label':label,'phase':phase,'stage':stage,'offset':offset})
 try:
  headers={'Accept-Encoding':'identity','User-Agent':'NOX-owner-pinned-student/1'}
  if offset: headers['Range']='bytes='+str(offset)+'-'
  opener=urllib.request.build_opener(policy['PublicHFRedirect']())
  mark('OPEN'); response=opener.open(urllib.request.Request(row['immutable_url'],headers=headers),timeout=15)
  mark('HEADERS'); result['http_status']=int(response.code)
  policy['allowed_public_url'](response.geturl()); result['public_host_allowed']=True
  if offset:
   match=re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)',response.headers.get('Content-Range',''))
   need(response.code==206 and match and tuple(map(int,match.groups()))==(offset,row['bytes']-1,row['bytes']),'RANGE_RESPONSE')
   result.update(range_start=offset,range_end=row['bytes']-1,range_total=row['bytes'])
  else: need(response.code==200,'HTTP_STATUS')
  length=response.headers.get('Content-Length')
  need(length is None or re.fullmatch('[0-9]{1,12}',length) and int(length)==row['bytes']-offset,'CONTENT_LENGTH')
  result['content_length']=int(length) if length is not None else None
  count=row['bytes'] if full else min(MIB,row['bytes']-offset)
  mark('READ'); raw=limited_read(response,count); result['bytes_returned']=len(raw)
  need(len(raw)==count,'SHORT_BODY')
  if full:
   need(not limited_read(response,1),'EXTRA_BODY')
   need(hashlib.sha256(raw).hexdigest()==row['sha256'],'METADATA_SHA')
   result['full_file_sha_verified']=True
  mark('CLOSE'); response.close(); response=None; result['ok']=True
 except Exception as exc:
  if isinstance(exc,urllib.error.HTTPError): response=exc; result['http_status']=int(exc.code)
  result.update(error(exc),failure_stage=stage)
 finally:
  if response is not None:
   try: response.close()
   except Exception as exc: result.update(error(exc),failure_stage='CLOSE',ok=False)
 result['elapsed_seconds']=round(time.monotonic()-started,3); emit(result); return result
def main():
 raw=sys.stdin.buffer.read(131073); need(len(raw)<=131072,'INPUT_BOUND'); packet=json.loads(raw)
 source=packet['memfd_source'].encode(); manifest_raw=packet['manifest_raw'].encode()
 need(hashlib.sha256(source).hexdigest()=='938335009efe691a9cef7b41daa7c55f3c8d3d8618a10a5eb5db125fd45afa82','SOURCE_PIN')
 need(hashlib.sha256(manifest_raw).hexdigest()=='2275fc88370ca8ba409a791819e13c8ab7d4e38cce4576a13170b05bcb8b839b','MANIFEST_PIN')
 nodes=[n for n in ast.parse(source).body if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name in ('seal','allowed_public_url','PublicHFRedirect')]
 need([n.name for n in nodes]==['seal','allowed_public_url','PublicHFRedirect'],'POLICY_DEFINITIONS')
 policy={'urllib':urllib,'fcntl':fcntl,'Hold':Hold,'F_ADD_SEALS':getattr(fcntl,'F_ADD_SEALS',1033),
         'F_GET_SEALS':getattr(fcntl,'F_GET_SEALS',1034),'SEALS':15}
 exec(compile(ast.Module(body=nodes,type_ignores=[]),'<pinned-public-transport-policy>','exec'),policy)
 files=json.loads(manifest_raw)['files']; need(isinstance(files,list) and len(files)==16,'FILE_SET')
 small=[r for r in files if not r['path'].endswith('.safetensors') and r['bytes']<=128*1024]
 shards=sorted((r for r in files if r['path'].endswith('.safetensors')),key=lambda r:r['path'])
 selected=[r for r in shards if r['bytes']==5368717440]
 need(len(shards)==4 and len(selected)==1 and len(small)<=12,'CASE_SET')
 smoke=tiny_memfd(policy); rows=[]; parallel=False
 if smoke['ok']:
  for i,row in enumerate(small): rows.append(request(policy,row,'metadata_'+str(i),'metadata_full',full=True))
  for i,row in enumerate(shards): rows.append(request(policy,row,'sequential_'+str(i),'sequential_prefix'))
  rows.append(request(policy,selected[0],'resume_3gib','resume_prefix',offset=3*1024**3))
  if all(r['ok'] for r in rows):
   parallel=True
   with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
    futures=[pool.submit(request,policy,row,'parallel_'+str(i),'parallel_prefix') for i,row in enumerate(shards)]
    rows.extend(f.result() for f in futures)
 emit({'event':'complete','metadata_selected':len(small),'metadata_not_full_tested':12-len(small),
       'parallel_executed':parallel,'all_checked_requests_passed':bool(rows) and all(r['ok'] for r in rows) and smoke['ok'],
       'request_count':len(rows),'reserved_body_bytes':RESERVED,'returned_body_bytes':RETURNED,
       'full_shard_download_verified':False,'large_memfd_write_verified':False})
 return 0
if __name__=='__main__':
 try: raise SystemExit(main())
 except Exception as exc: emit({'event':'child_failure',**error(exc)}); raise SystemExit(2)
'''


class ProbeDeadline(BaseException):
    pass


def require(ok, code):
    if not ok:
        raise RuntimeError('HOLD_QWEN_TRANSPORT_PROBE_' + code)


def core_module():
    require(not any(p.is_symlink() for p in (INSTALLER, *INSTALLER.parents)), 'INSTALLER_PATH')
    with os.fdopen(os.open(INSTALLER, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC), 'rb') as stream:
        first = os.fstat(stream.fileno())
        require(stat.S_ISREG(first.st_mode) and first.st_uid == os.geteuid()
                and not first.st_mode & 0o022 and 0 < first.st_size <= 131072, 'INSTALLER_FILE')
        raw = stream.read(131073)
        identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        require(len(raw) == first.st_size and identity(first) == identity(os.fstat(stream.fileno()))
                == identity(INSTALLER.stat(follow_symlinks=False))
                and hashlib.sha256(raw).hexdigest() == INSTALLER_SHA, 'INSTALLER_PIN')
    value = types.ModuleType('_nox_transport_readonly'); value.__file__ = str(INSTALLER)
    exec(compile(raw, str(INSTALLER), 'exec'), value.__dict__)
    return value


def current_proof(core, shared):
    ctx = shared.current_context(REFERENCE); core.protected(); core.global_stop()
    trainer = core.trainer(ctx)
    require(trainer == {'service': {'state': 'FATAL', 'pid': None}, 'process_identity': None}, 'TRAINER_NOT_STOPPED')
    require(shared.activation_status(ctx)['active'] is False, 'ACTIVATION_PRESENT')
    pointer, raw = core.document(ctx['output'] / 'latest_checkpoint.json', 16384)
    require(core.digest(raw) == core.ANCHOR['pointer_sha256'] and pointer['directory'] == core.ANCHOR['directory'], 'ANCHOR_POINTER')
    folder = ctx['output'] / core.ANCHOR['directory']
    manifest, mraw = core.document(folder / 'checkpoint_manifest.json', 65536)
    state, sraw = core.document(folder / 'student_state.json')
    require(core.digest(mraw) == core.ANCHOR['manifest_sha256'] and core.digest(sraw) == core.ANCHOR['student_state_sha256'], 'ANCHOR_METADATA')
    require(shared.checkpoint_binding(ctx, manifest, state, allow_initial_anchor=True)['legacy_anchor'] is True, 'LEGACY_ANCHOR')
    chat = ctx['helper'].model_identity()
    require(chat == {'pid': 7637, 'start_ticks': '149189867'}, 'CHAT_IDENTITY')
    return ctx, {'execution_revision': ctx['context'], 'admission_sha256': core.digest(ctx['raw']),
                 'wrapper_sha256': core.digest(ctx['wrapper']), 'checkpoint_manifest_sha256': core.digest(mraw),
                 'metadata_only': True, 'checkpoint_payload_bytes_read': 0, 'trainer': trainer, 'chat': chat}


def memory(obs):
    result = {}
    for name in ('memory.current', 'memory.max', 'memory.events'):
        try:
            raw = obs.proc_bytes(Path('/sys/fs/cgroup') / name, 4096).decode('ascii').strip()
            if name == 'memory.events':
                result['events'] = {k: int(v) for line in raw.splitlines() for k, v in [line.split()]
                                    if k in ('oom', 'oom_kill', 'high', 'max') and v.isdecimal()}
            else:
                result[name.replace('.', '_') + '_bytes'] = int(raw) if raw.isdecimal() else None
        except Exception:
            result['events' if name == 'memory.events' else name.replace('.', '_') + '_bytes'] = None
    a, b = result.get('memory_current_bytes'), result.get('memory_max_bytes')
    result['headroom_bytes'] = b - a if type(a) is int and type(b) is int and b >= a else None
    return result


def run_child(packet, timeout, python=None):
    payload = json.dumps(packet, separators=(',', ':')).encode(); require(len(payload) <= 131072, 'INPUT_BOUND')
    child = subprocess.Popen([python or sys.executable, '-I', '-S', '-B', '-c', CHILD], stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, start_new_session=True)
    expired = False
    try:
        try:
            output, _ = child.communicate(payload, timeout=timeout)
        except subprocess.TimeoutExpired:
            expired = True; child.kill(); output, _ = child.communicate(timeout=2)
        require(len(output) <= 131072, 'OUTPUT_BOUND')
        return output, child.returncode, expired
    finally:
        if child.poll() is None:
            child.kill(); child.wait(timeout=2)  # Only this owned Python child, including its threads.


def child_projection(raw):
    result = {'rows': [], 'incomplete_requests': {}, 'memfd': None, 'complete': None}
    lines = raw.splitlines(); require(len(lines) <= 256, 'EVENT_BOUND')
    for line in lines:
        require(len(line) <= 4096 and line.startswith(b'NOX_TRANSPORT='), 'CHILD_PROTOCOL')
        row = json.loads(line[len(b'NOX_TRANSPORT='):]); event = row.get('event')
        require(event in ('stage', 'result', 'memfd', 'complete', 'child_failure'), 'CHILD_EVENT')
        if event == 'stage':
            result['incomplete_requests'][row['label']] = row
        elif event == 'result':
            result['rows'].append(row); result['incomplete_requests'].pop(row['label'], None)
        else:
            result[event] = row
    return result


def main():
    started = time.monotonic(); timer = signal.getitimer(signal.ITIMER_REAL)
    previous = {sig: signal.getsignal(sig) for sig in (signal.SIGALRM, signal.SIGTERM)}
    def expired(_signal, _frame):
        raise ProbeDeadline('HOLD_QWEN_TRANSPORT_PROBE_DEADLINE')
    for sig in previous:
        signal.signal(sig, expired)
    signal.setitimer(signal.ITIMER_REAL, min(60, timer[0]) if timer[0] else 60)
    result = {'schema': 'NOX_QWEN_TRANSPORT_PROBE_V1', 'state': 'PREFLIGHT', 'managed_files_written': 0,
              'service_actions': 0, 'checkpoint_payload_bytes_read': 0, 'full_shard_download_verified': False,
              'default_proxy_policy_preserved': True, 'public_manifest_sha256': MANIFEST_SHA,
              'transport_source_sha256': MEMFD_SHA, 'response_body_budget_bytes': 12 * MIB}
    try:
        core = core_module(); raw = core.read(core.SCRIPTS / core.SHARED)
        require(core.digest(raw) == SHARED_SHA == core.PINS[core.SHARED], 'SHARED_PIN')
        shared = core.module(core.SHARED, raw); ctx, before = current_proof(core, shared)
        result.update(before=before, memory_before=memory(ctx['observer']))
        source = core.read(core.SCRIPTS / 'owner_qwen_memfd.py', 131072)
        manifest, mraw = core.document(core.SCRIPTS / 'qwen35_9b_manifest.json', 131072)
        require(core.digest(source) == MEMFD_SHA and core.digest(mraw) == MANIFEST_SHA, 'TRANSPORT_SOURCE_PINS')
        ctx['contract'].validate_manifest(manifest)
        packet = {'memfd_source': source.decode(), 'manifest_raw': mraw.decode()}
        remaining = 55 - (time.monotonic() - started); require(remaining > 0, 'PREPARATION_DEADLINE')
        require(ctx['argv'][0] == '/root/venv_volta/bin/python', 'ADMITTED_PYTHON')
        output, code, timed_out = run_child(packet, min(50, remaining), python=ctx['argv'][0])
        result.update(child_projection(output), child_exit_code=code, child_deadline_reached=timed_out,
                      owned_child_exited=True, memory_after=memory(ctx['observer']))
        _, after = current_proof(core, shared); require(before == after, 'CURRENT_CONTEXT_CHANGED')
        result['after'] = after
        complete = code == 0 and not timed_out and result['complete'] is not None and not result['incomplete_requests']
        result.update(state='TRANSPORT_OBSERVATION_COMPLETE' if complete else 'TRANSPORT_OBSERVATION_PARTIAL',
                      observation_complete=complete, trainer_failure_cause_established=False)
        rc = 0 if complete else 2
    except (Exception, ProbeDeadline) as exc:
        reason = str(exc)
        result.update(state='HOLD', reason=reason if re.fullmatch('(HOLD|WAIT)_[A-Z0-9_]{1,150}', reason)
                      else 'HOLD_QWEN_TRANSPORT_PROBE_' + type(exc).__name__.upper(), observation_complete=False)
        rc = 2
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        for sig, handler in previous.items():
            signal.signal(sig, handler)
        signal.setitimer(signal.ITIMER_REAL, max(.001, timer[0] - (time.monotonic() - started)) if timer[0] else 0, timer[1])
    result['elapsed_seconds'] = round(time.monotonic() - started, 3)
    print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'qwen_transport_probe', 'data': result},
          sort_keys=True, separators=(',', ':'), allow_nan=False), flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=' + str(rc == 0).lower(), flush=True)
    return rc


if __name__ == '__main__':
    raise SystemExit(main())
