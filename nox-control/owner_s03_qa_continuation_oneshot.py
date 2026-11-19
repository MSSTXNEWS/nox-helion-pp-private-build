#!/usr/bin/env python3
"""Run one exact owner QA continuation with the existing serving venv."""
import ast
import os
import subprocess

SOURCE = r'''#!/usr/bin/env python3
"""Continue the one existing, independently verified NOX QA dialog.

Only the same-dialog exchange is written through the native serving route. No raw
model/user content, credentials, cookies or chat excerpts leave the host.
"""
from __future__ import annotations

from datetime import datetime
from hashlib import sha256
import hashlib
import http.cookiejar
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import subprocess
import sys
import time
import urllib.request
import urllib.error

sys.dont_write_bytecode = True

ROOT = Path("/root/nox")
STOP_FILES = (
    ROOT / "STOP", ROOT / "STOP.flag", ROOT / "stop.flag", ROOT / ".stop",
    ROOT / "program/STOP", ROOT / "state/STOP", ROOT / "state/STOP.flag",
    Path("/workspace/NOX_STOP"), ROOT / "state/OWNER_MAINTENANCE.flag",
)
def output(data):
    print("NOX_MAINT_REPAIR=" + json.dumps({"kind":"chat_s03_same_dialog",
          "data":data},sort_keys=True,separators=(",",":"),ensure_ascii=False,
          allow_nan=False),flush=True)

def source_status():
    # Exact source observed on the owner host; no untrusted script injection.
    path=ROOT/"scripts"/"chat_proxy.py"
    pin="9fedaefbe39f4cac8a47d77bb0dada2ccf09c43ec38a5624869d3a00c0fbe5a3"
    if path.is_symlink() or not path.is_file() or path.stat().st_size>150000:
        raise RuntimeError("HOLD_LIVE_SMOKE_SOURCE_SCOPE")
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    if digest!=pin:
        raise RuntimeError("HOLD_LIVE_SMOKE_SOURCE_PIN")
    for name, expected in {"nox_v38_native_context.py":"32fa7c3729bbb7a4ab3e43183f10fec70e4c9254d0f9c2f9458db68c1c4a6deb","nox_v38_s03_native.py":"c1c4d77d86e833c69b5af8cee82bbd83211ca0184f4a63f66dc067eb0b50ebc3","nox_s03_scoped_pair.py":"d347ff7247e2f883b955094ca4e98205346ddb6e39b0fa52e13c360a8144c57f","nox_v38_self_model.py":"b15bf20557601028ecc4e6163d1d6add682616d466fa9fb78b3640411f7c1ada"}.items():
        item=ROOT/"scripts"/name
        if item.is_symlink() or not item.is_file() or item.stat().st_size>150000:
            raise RuntimeError("HOLD_LIVE_SMOKE_RELEASE_SCOPE")
        if hashlib.sha256(item.read_bytes()).hexdigest()!=expected:
            raise RuntimeError("HOLD_LIVE_SMOKE_RELEASE_PIN")
    return digest

def process_identity(pid):
    try:
        raw=(Path('/proc')/str(pid)/'stat').read_bytes()
        values=raw.rsplit(b') ',1)[1].split()
        if len(raw)>8192 or values[0] in (b'Z',b'X'):
            return None
        return {'pid':pid,'start_ticks':int(values[19])}
    except (OSError,ValueError,IndexError):
        return None

def guards():
    if any(os.path.lexists(p) for p in STOP_FILES):
        raise RuntimeError("HOLD_LIVE_SMOKE_STOP")
    source_status()
    # No second model or browser is launched. Keep a real 512 MiB raw buffer,
    # and require zero PSI/OOM plus a conservative unused file-cache floor.
    cg=Path('/sys/fs/cgroup')
    try:
        maximum=(cg/'memory.max').read_text().strip()
        current=(cg/'memory.current').read_text().strip()
        stats=dict((line.split()[0],int(line.split()[1]))
                   for line in (cg/'memory.stat').read_text().splitlines())
        events=dict((line.split()[0],int(line.split()[1]))
                    for line in (cg/'memory.events').read_text().splitlines())
        pressure=(cg/'memory.pressure').read_text().splitlines()
    except (OSError,IndexError,ValueError):
        raise RuntimeError("HOLD_LIVE_SMOKE_CGROUP_UNKNOWN") from None
    if not maximum.isdigit() or not current.isdigit():
        raise RuntimeError("HOLD_LIVE_SMOKE_CGROUP_UNBOUNDED")
    free=int(maximum)-int(current)
    cold=max(0,min(stats.get('inactive_file',0),
              max(0,stats.get('file',0)-stats.get('shmem',0)))-stats.get('shmem',0))
    # Reclaimable cold page-cache can safely satisfy a single EXISTING model
    # POST with no new model/browser/weights. The low-raw profile needs a larger
    # cold-cache reserve; PSI/OOM and current service/model-slot checks remain.
    normal = free>=512*1024**2 and cold>=4*1024**3
    cold_cache_profile = free>=256*1024**2 and cold>=12*1024**3
    if not (normal or cold_cache_profile):
        raise RuntimeError("HOLD_LIVE_SMOKE_MEMORY")
    if events.get('oom',1)!=0 or events.get('oom_kill',1)!=0:
        raise RuntimeError("HOLD_LIVE_SMOKE_OOM")
    if len(pressure)!=2 or any(
            re.search(r'avg10=0\.00(?:\s|$)',row) is None for row in pressure):
        raise RuntimeError("HOLD_LIVE_SMOKE_PRESSURE")
    names=('nox-proxy','nox-ds41-8098','nox-dispatcher-t855u')
    identities={}
    for name in names:
        p=subprocess.run(['supervisorctl','status',name],text=True,capture_output=True,timeout=7)
        match=re.match(r'^'+re.escape(name)+r'\s+RUNNING\s+pid\s+([0-9]+),',p.stdout.strip())
        if p.returncode!=0 or not match:
            raise RuntimeError("HOLD_LIVE_SMOKE_SERVICES")
        identity=process_identity(int(match.group(1)))
        if identity is None:
            raise RuntimeError("HOLD_LIVE_SMOKE_PID")
        identities[name]=identity
    conn=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with conn.open("http://127.0.0.1:8080/health",timeout=5) as response:
            if response.status!=200:raise RuntimeError("HOLD_LIVE_SMOKE_HEALTH")
            response.read(4097)
    except urllib.error.URLError:
        raise RuntimeError("HOLD_LIVE_SMOKE_PROXY_UNREACHABLE") from None
    if identities!={name:process_identity(row['pid']) for name,row in identities.items()}:
        raise RuntimeError("HOLD_LIVE_SMOKE_PROCESS_CHANGED")
    slots, slot_port = None, None
    for port in (8081,8098):
        try:
            with conn.open("http://127.0.0.1:%d/slots" % port,timeout=5) as response:
                if response.status!=200:continue
                raw=response.read(15001)
            if len(raw)>15000:continue
            candidate=json.loads(raw)
            if not isinstance(candidate,list) or len(candidate)>10 or any(
                    not isinstance(row,dict) for row in candidate):continue
            slots,slot_port=candidate,port
            break
        except (urllib.error.URLError,ValueError):
            continue
    if slots is None:
        raise RuntimeError("HOLD_LIVE_SMOKE_NO_LOCAL_MODEL_SLOTS")
    if any(bool(row.get("is_processing",row.get("processing",False))) for row in slots):
        raise RuntimeError("HOLD_LIVE_SMOKE_MODEL_BUSY")
    return {"stable_services":len(identities),"slots":len(slots),
            "slot_port":slot_port,"source_pin":True,
            "admission_profile":"COLD_CACHE_256M_12G" if not normal else "RAW_512M_4G",
            "raw_headroom_bytes":free,"cold_lower_bound_bytes":cold}

def parse_frame_line(raw):
    """Accept the existing NOX browser SSE data frames or legacy NDJSON."""
    if not isinstance(raw,bytes) or len(raw)>100000:
        raise RuntimeError("HOLD_LIVE_SMOKE_FRAME_LENGTH")
    line=raw.strip()
    if not line or line.startswith((b":",b"event:",b"id:",b"retry:")):
        return None
    if line.startswith(b"data:"):
        line=line[5:].strip()
    if line==b"[DONE]":
        return {"type":"sentinel"}
    try:
        result=json.loads(line)
    except (ValueError,UnicodeError):
        raise RuntimeError("HOLD_LIVE_SMOKE_SSE_JSON") from None
    if not isinstance(result,dict):
        raise RuntimeError("HOLD_LIVE_SMOKE_FRAME")
    return result


DB = Path('/root/nox/kb/knowledge.sqlite')
WRITER = Path('/root/nox/scripts/nox_s03_scoped_pair.py')
WRITER_SHA = 'd347ff7247e2f883b955094ca4e98205346ddb6e39b0fa52e13c360a8144c57f'
QUESTION = 'Кто ты? Ты голоден? Что сейчас делаешь?'
ANSWER_SHA = '13d4daf0713273858d46332185eb4fea6fefac44ea3884e4bf2aa2a99a5e9318'
TITLES = tuple(f'NOX QA nox_policy_qa_{second}' for second in range(1795113247, 1795113266))
OWNER = 'nox-single-owner'
QUERY = """
SELECT d.dialog_id,g.request_id,g.received_at,g.s03_record_id,g.s03_sha256,
       s.segment,s.provenance,s.text,s.meta,s.sha256,u.content,a.content
  FROM nox_v29_dialogs d
  JOIN nox_chat_received_goals g ON g.dialog_id=d.dialog_id AND g.owner=d.owner
  JOIN s03_items s ON s.id=g.s03_record_id AND s.sha256=g.s03_sha256
  JOIN nox_v29_dialog_messages u ON u.dialog_id=d.dialog_id AND u.exchange_id=s.id AND u.role='user'
  JOIN nox_v29_dialog_messages a ON a.dialog_id=d.dialog_id AND a.exchange_id=s.id AND a.role='assistant'
 WHERE d.owner=? AND d.archived=0 AND d.title IN ({titles})
   AND g.request_id=g.resolved_by_request_id AND g.state='RESPONSE_COMMITTED'
   AND g.question_sha256=? AND CAST(g.question AS BLOB)=CAST(? AS BLOB)
 LIMIT 33
"""


def require(ok, code):
    if not ok:
        raise RuntimeError('HOLD_S03_QA_' + code)


def digest(value):
    return sha256(value).hexdigest()


def anchored_regular(path):
    for parent in path.parents:
        row = parent.lstat()
        require(stat.S_ISDIR(row.st_mode) and row.st_uid == 0 and not row.st_mode & 0o002, 'PATH_SCOPE')
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o002,
            'FILE_SCOPE')
    return info.st_dev, info.st_ino


def load_manifest_builder():
    before = anchored_regular(WRITER)
    fd = os.open(WRITER, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    with os.fdopen(fd, 'rb') as handle:
        row = os.fstat(handle.fileno())
        raw = handle.read(65537)
        require((row.st_dev, row.st_ino) == before == anchored_regular(WRITER)
                and len(raw) <= 65536 and digest(raw) == WRITER_SHA, 'WRITER_PIN')
    namespace = {}
    exec(compile(raw, str(WRITER), 'exec'), namespace)
    return namespace['_pair_manifest']



NEXT = 'Повтори дословно последнее законченное предложение из своего предыдущего ответа. Напиши только это предложение.'
M1_SHA = '29ae0cef920db4c84d1a3c575e544ea1a9d12e8f34a252a36b34096b8cd0de77'

def pairs(db, build, question, answer_hash, expected_dialog=None):
    rows=db.execute(QUERY.format(titles=','.join('?' for _ in TITLES)),
                    (OWNER,*TITLES,digest(question.encode()),question)).fetchall()
    require(len(rows) <= 32, 'MATCH_BOUND')
    matches=[]
    for dialog,request,received,record,goal_sha,segment,provenance,text,meta,stored_sha,user,assistant in rows:
        if user!=question or not isinstance(assistant,str) or digest(assistant.encode())!=answer_hash:
            continue
        if expected_dialog is not None and dialog!=expected_dialog:
            continue
        require(all(isinstance(v,str) and re.fullmatch(r'[a-f0-9]{32}',v)
                    for v in (dialog,request)), 'BINDING')
        event=datetime.fromisoformat(received.replace('Z','+00:00'))
        require(event.tzinfo is not None, 'TIMEZONE')
        require((record,text,stored_sha,meta)==build(dialog,request,question,assistant,event)
                and goal_sha==stored_sha and segment=='M1' and provenance=='chat_turn_scoped_v3', 'MANIFEST')
        matches.append((dialog,record,stored_sha,assistant))
    require(len(matches)==1,'OWNER_PAIR_UNPROVEN')
    return matches[0]

def snapshot(build, answer=None, expected_prior=None):
    identity=anchored_regular(DB)
    wal,shm=(Path(str(DB)+suffix) for suffix in ('-wal','-shm'))
    if os.path.lexists(wal) or os.path.lexists(shm):
        anchored_regular(wal)
        anchored_regular(shm)
    with sqlite3.connect(DB.as_uri()+'?mode=ro',uri=True,timeout=0.5) as db:
        deadline=time.monotonic()+2
        db.set_progress_handler(lambda: int(time.monotonic()>deadline),1000)
        db.execute('PRAGMA query_only=ON')
        db.execute('BEGIN')
        first=pairs(db,build,QUESTION,ANSWER_SHA)
        require(first[2]==M1_SHA,'PRIOR_M1')
        require(expected_prior is None or first==expected_prior,'PRIOR_CHANGED')
        rows=db.execute('SELECT exchange_id,role,content FROM nox_v29_dialog_messages WHERE dialog_id=? LIMIT 5',
                        (first[0],)).fetchall()
        expected=[(first[1],'user',QUESTION),(first[1],'assistant',first[3])]
        second=None
        if answer is not None:
            second=pairs(db,build,NEXT,digest(answer.encode()),first[0])
            require(first[1]!=second[1],'EXCHANGE_REUSED')
            expected.extend([(second[1],'user',NEXT),(second[1],'assistant',answer)])
        require(len(rows)==len(expected) and set(rows)==set(expected),'EXACT_OWNER_ROWS')
        require(anchored_regular(DB)==identity,'DB_CHANGED')
    return first,second

def prior_sentence(answer):
    parts=re.split(r'(?<=[.!?])\s+',answer.strip())
    complete=[part.strip() for part in parts if re.fullmatch(r'[^.!?\n]{18,400}[.!?]',part.strip())]
    require(bool(complete),'PRIOR_SENTENCE')
    return complete[-1]

def main():
    record={'schema':'NOX_S03_SAME_DIALOG_V1','model_requests':0,'canonical_pairs':0,
            'raw_content_exported':False,'status':'HOLD_S03_QA'}
    client=None
    try:
        require(re.fullmatch(r'[1-9][0-9]{0,23}',os.environ.get('NOX_OWNER_REQUEST_ID','')) and
                re.fullmatch(r'[0-9a-f]{40}',os.environ.get('NOX_OWNER_SOURCE_SHA','')),'OWNER_CONTEXT')
        record['precheck']=guards()
        build=load_manifest_builder()
        first,_=snapshot(build)
        target=prior_sentence(first[3])
        record['prior_answer_sha256']=ANSWER_SHA
        sys.path.insert(0,str(ROOT/'scripts'))
        import chat_proxy
        password=chat_proxy._read_chat_password()
        require(isinstance(password,str) and len(password)>=6,'OWNER_PASSWORD')
        jar=http.cookiejar.CookieJar()
        client=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPCookieProcessor(jar))
        def call(path,method='GET',value=None,timeout=12):
            raw=None if value is None else json.dumps(value,ensure_ascii=False).encode()
            req=urllib.request.Request('http://127.0.0.1:8080'+path,data=raw,method=method,
                                       headers={'Content-Type':'application/json'})
            return client.open(req,timeout=timeout)
        with call('/chat/login','POST',{'password':password}) as response:
            require(response.status==200,'OWNER_LOGIN')
        password=None
        require(any(True for _ in jar),'SESSION_COOKIE')
        with call('/chat/session') as response:
            require(json.loads(response.read(8192)).get('ok') is True,'OWNER_SESSION')
        guards()
        snapshot(build,expected_prior=first)
        started=time.monotonic()
        record['model_requests']=1
        with call('/api/nox/chat/stream','POST',{'message':NEXT,'dialog_id':first[0]},timeout=100) as response:
            require(response.status==200,'HTTP')
            tokens=[]
            size=0
            done=None
            for count,line in enumerate(response):
                require(count<500 and len(line)<=100000 and time.monotonic()-started<=105,'STREAM_BOUND')
                frame=parse_frame_line(line)
                if frame is None:
                    continue
                kind=frame.get('type')
                if kind=='delta':
                    token=frame.get('text')
                    require(isinstance(token,str),'DELTA')
                    size+=len(token)
                    require(size<=12000,'OUTPUT_BOUND')
                    tokens.append(token)
                elif kind=='done':
                    done=frame
                    break
                elif kind in ('error','sentinel'):
                    require(False,'STREAM_TERMINAL')
        answer=''.join(tokens)
        require(done is not None and answer.strip() and done.get('dialog_id')==first[0],'STREAM_DONE')
        _,second=snapshot(build,answer,first)
        require(done.get('exchange_id')==second[1],'TERMINAL_BINDING')
        record.update(canonical_pairs=2,owner_message_rows=4,second_answer_sha256=digest(answer.encode()),
                      second_s03_sha256=second[2],recall_exact=answer.strip().strip('«»"')==target,
                      native_delta_count=len(tokens))
        require(record['recall_exact'],'RECALL_CONTENT')
        record['status']='SAME_DIALOG_RECALL_AND_CANONICAL_S03_VERIFIED'
    except Exception as error:
        reason=str(error)
        record['reason']=reason if re.fullmatch(r'HOLD_[A-Z0-9_]{1,100}',reason) else type(error).__name__
    finally:
        if client is not None:
            try:
                request=urllib.request.Request('http://127.0.0.1:8080/chat/logout',data=b'{}',method='POST')
                with client.open(request,timeout=5) as response:
                    response.read(4097)
            except Exception:
                pass
    output(record)
    okay=record['status']=='SAME_DIALOG_RECALL_AND_CANONICAL_S03_VERIFIED'
    print('NOX_MAINT_REPAIR_COMPLETE='+str(okay).lower(),flush=True)
    return 0 if okay else 2

if __name__=='__main__':
    raise SystemExit(main())
'''
if not SOURCE.startswith("#!/usr/bin/env python3\n"):
    # Source is embedded as an owner-pinned literal, not fetched at runtime.
    raise SystemExit("HOLD_SMOKE_ENTRY_SOURCE")
ast.parse(SOURCE)
env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", CUDA_VISIBLE_DEVICES="")
process = subprocess.run(["/root/nox/venv/bin/python", "-"], input=SOURCE.encode("utf-8"),
                         capture_output=True, timeout=160, env=env)
for line in process.stdout.decode("utf-8", "replace").splitlines():
    if line.startswith("NOX_MAINT_") and len(line) <= 12000:
        print(line, flush=True)
if process.returncode:
    print("NOX_MAINT_CONTINUATION_CHILD_EXIT=" + str(process.returncode), flush=True)
raise SystemExit(0 if process.returncode == 0 else 2)
