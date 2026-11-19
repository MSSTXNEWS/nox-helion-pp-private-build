"""Owner-scoped evolution journal inside EXISTING S03. No daemon/new DB/GPU work.

Register in the existing OneHost; call record() from independently verified
native callbacks and hourly_tick() from the existing dispatcher. Browser GETs
never authorize operations or start learning. Unknown coverage is never zero.
"""
from __future__ import annotations
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from pathlib import Path
from collections.abc import Callable, Mapping
import hashlib, json, math, re, sqlite3

SCHEMA = 'NOX_EVOLUTION_V1'
KINDS = ('self_improvement','knowledge','weights')
LABELS = {'self_improvement':'Самоулучшение','knowledge':'Знания','weights':'Веса'}
STATES = {'verified','active','blocked','failed','source','unknown'}
ID = re.compile(r'^[A-Za-z0-9._:-]{1,160}$')
SHA = re.compile(r'^[0-9a-f]{64}$')
DDL = '''
CREATE TABLE IF NOT EXISTS nox_evolution_events (
 owner TEXT NOT NULL, event_id TEXT NOT NULL, kind TEXT NOT NULL,
 subject_key TEXT NOT NULL, at_utc TEXT NOT NULL, payload TEXT NOT NULL, digest TEXT NOT NULL,
 PRIMARY KEY(owner,event_id), UNIQUE(owner,kind,subject_key));
CREATE INDEX IF NOT EXISTS nox_evolution_time ON nox_evolution_events(owner,at_utc);
CREATE TABLE IF NOT EXISTS nox_evolution_coverage (
 owner TEXT NOT NULL, hour_utc TEXT NOT NULL, kind TEXT NOT NULL,
 PRIMARY KEY(owner,hour_utc,kind));
CREATE TABLE IF NOT EXISTS nox_evolution_hours (
 owner TEXT NOT NULL, hour_utc TEXT NOT NULL, payload TEXT NOT NULL, digest TEXT NOT NULL,
 PRIMARY KEY(owner,hour_utc));
'''

def stamp(value):
    if not isinstance(value,str) or len(value)>40: raise ValueError('INVALID_TIMESTAMP')
    d=datetime.fromisoformat(value.replace('Z','+00:00'))
    if d.tzinfo is None: raise ValueError('TIMEZONE_REQUIRED')
    return d.astimezone(timezone.utc)

def iso(d): return d.astimezone(timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z')
def hour(d): return d.replace(minute=0,second=0,microsecond=0)
def encode(o): return json.dumps(o,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
def digest(o): return hashlib.sha256(encode(o).encode()).hexdigest()
def integer(n): return type(n) is int and 0<=n<=10**12

def successful_weight_updates(proof):
    """Only independently verified successful optimizer updates count, not global_step."""
    if not isinstance(proof,Mapping):return None
    a,b=proof.get('step_before'),proof.get('step_after')
    n=proof.get('successful_optimizer_updates')
    skipped=proof.get('skipped_optimizer_updates')
    if not (integer(a) and integer(b) and b>a and integer(n) and 0<n<=b-a):return None
    # A reported skipped step cannot also be a successful optimizer update.
    # Reject contradictions rather than inflating the weights progress card.
    if skipped is not None and (not integer(skipped) or n+skipped>b-a):return None
    return n

def clean_event(raw:Mapping, *, now:datetime):
    if not isinstance(raw,Mapping): raise ValueError('INVALID_EVENT')
    e={k:raw.get(k) for k in ('id','kind','subject_key','at','title','summary','detail','state','evidence','tags','sources','proof')}
    if not all(isinstance(e[k],str) and ID.fullmatch(e[k]) for k in ('id','subject_key')): raise ValueError('INVALID_ID')
    if e['kind'] not in KINDS or e['state'] not in STATES or e['evidence'] not in ('native','source','unknown'): raise ValueError('INVALID_STATE')
    dt=stamp(e['at'])
    if dt>now+timedelta(seconds=30): raise ValueError('FUTURE_EVENT')
    e['at']=iso(dt)
    for k,limit in (('title',120),('summary',500),('detail',6000)):
        if not isinstance(e[k],str) or len(e[k])>limit: raise ValueError('INVALID_TEXT')
    if not isinstance(e['tags'],list) or len(e['tags'])>12 or any(not isinstance(t,str) or not 1<=len(t)<=40 for t in e['tags']): raise ValueError('INVALID_TAGS')
    e['tags']=list(dict.fromkeys(e['tags']))
    if not isinstance(e['sources'],list) or len(e['sources'])>8: raise ValueError('INVALID_SOURCES')
    for s in e['sources']:
        if not isinstance(s,dict) or set(s)!={'label','url'} or not isinstance(s['label'],str) or len(s['label'])>100 or not isinstance(s['url'],str) or len(s['url'])>700: raise ValueError('INVALID_SOURCE')
        # Only HTTPS or a same-app absolute path; no javascript/data/protocol-relative links.
        from urllib.parse import urlsplit
        u=urlsplit(s['url'])
        if not ((u.scheme=='https' and u.netloc and not u.username and not u.password) or (not u.scheme and not u.netloc and s['url'].startswith('/') and not s['url'].startswith('//'))): raise ValueError('UNSAFE_SOURCE')
    p=e['proof']
    if not isinstance(p,dict) or len(encode(p))>8000: raise ValueError('INVALID_PROOF')
    e['delta']=None
    if e['evidence']=='source' and e['state']=='verified': e['state']='source'
    if e['state']=='verified':
        if e['evidence']!='native': raise ValueError('VERIFIED_NEEDS_NATIVE')
        if not isinstance(p.get('receipt_sha256'),str) or not SHA.fullmatch(p['receipt_sha256']): raise ValueError('RECEIPT_REQUIRED')
        if e['kind']=='weights':
            a,b=p.get('step_before'),p.get('step_after');x,y=p.get('tensor_before'),p.get('tensor_after')
            if not(integer(a) and integer(b) and b>a): raise ValueError('REAL_STEPS_REQUIRED')
            if not(all(isinstance(v,str) and SHA.fullmatch(v) for v in (x,y,p.get('checkpoint_sha256'))) and x!=y): raise ValueError('TENSOR_CHANGE_REQUIRED')
            successful=successful_weight_updates(p)
            if successful is None: raise ValueError('SUCCESSFUL_OPTIMIZER_UPDATES_REQUIRED')
            e['delta']=successful
        elif e['kind']=='knowledge':
            if not integer(p.get('records_added')) or not isinstance(p.get('s03_readback_sha256'),str) or not SHA.fullmatch(p['s03_readback_sha256']): raise ValueError('S03_READBACK_REQUIRED')
            e['delta']=p['records_added']
        else:
            if p.get('independent_test_passed') is not True or not isinstance(p.get('deployed_sha'),str) or not re.fullmatch(r'[0-9a-f]{40,64}',p['deployed_sha']): raise ValueError('DEPLOYED_TEST_REQUIRED')
            e['delta']=1
    return e

def summarize(events, coverage, start, end):
    groups={}
    for kind in KINDS:
        rows=[e for e in events if e['kind']==kind and start<=stamp(e['at'])<end]
        verified=[e for e in rows if e['evidence']=='native' and e['state']=='verified'
                  and (kind!='weights' or successful_weight_updates(e.get('proof')) is not None)]
        covered=kind in coverage
        # Partial positive evidence is a lower bound, not a complete count.
        value=sum((successful_weight_updates(e['proof']) if kind=='weights' else (e.get('delta') or 0))
                  for e in verified) if (verified or covered) else None
        failed=sum(e['state']=='failed' for e in rows)
        state='failed' if failed else ('blocked' if any(e['state']=='blocked' for e in rows) else ('active' if any(e['state']=='active' for e in rows) else ('verified' if verified else ('source' if rows else 'unknown'))))
        count_text='нет подтверждённых данных' if value is None else (str(value) if covered else 'не менее '+str(value))
        unit={'self_improvement':'внедрений','knowledge':'новых записей S03','weights':'шагов оптимизатора'}[kind]
        groups[kind]={'state':state,'value':value,'complete':covered,'source_events':sum(e['evidence']=='source' for e in rows),'events':len(rows),'failed':failed,'ids':[e['id'] for e in rows], 'summary':f"{LABELS[kind]}: {count_text}"+(f' {unit}' if value is not None else '')}
    return groups

class ProgressJournal:
    def __init__(self, existing_s03:Path, verifier:Callable):
        self.path=Path(existing_s03);self.verifier=verifier
        if not callable(verifier): raise ValueError('TRUSTED_VERIFIER_REQUIRED')
    @contextmanager
    def db(self,write=False):
        if not self.path.is_file() or self.path.is_symlink():raise ValueError('EXISTING_S03_REQUIRED')
        db=sqlite3.connect(self.path.resolve().as_uri()+('?mode=rw' if write else '?mode=ro'),uri=True,timeout=3)
        try:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='s03_items'").fetchone():raise ValueError('ORIGINAL_S03_REQUIRED')
            if not write:db.execute('PRAGMA query_only=ON')
            with db:yield db
        finally:db.close()
    def initialize(self):
        """Call once under an existing authenticated owner maintenance lease."""
        with self.db(True) as db:db.executescript(DDL)
    @staticmethod
    def owner(owner):
        if not isinstance(owner,str) or not ID.fullmatch(owner):raise ValueError('OWNER_SCOPE_REQUIRED')
        return owner
    def record(self,owner,raw,now=None):
        self.owner(owner); now=now or datetime.now(timezone.utc)
        e=clean_event(raw,now=now)
        # A JSON true/verified flag is never a signature or an owner permission.
        if self.verifier(owner,e) is not True:raise ValueError('INDEPENDENT_EVENT_VERIFICATION_FAILED')
        payload=encode(e);sha=digest(e)
        with self.db(True) as db:
            prior=db.execute('SELECT event_id,digest FROM nox_evolution_events WHERE owner=? AND (event_id=? OR (kind=? AND subject_key=?))',(owner,e['id'],e['kind'],e['subject_key'])).fetchone()
            if prior:
                if prior[0]==e['id'] and prior[1]==sha:return {'state':'ALREADY_RECORDED','id':e['id']}
                raise ValueError('EVENT_ID_OR_SUBJECT_CONFLICT')
            db.execute('INSERT INTO nox_evolution_events VALUES(?,?,?,?,?,?,?)',(owner,e['id'],e['kind'],e['subject_key'],e['at'],payload,sha))
        # Rebuild a past-hour card on a late receipt. No event is overwritten.
        if hour(stamp(e['at']))<hour(now):self.finalize_hour(owner,hour(stamp(e['at'])),now=now)
        return {'state':'RECORDED','id':e['id'],'sha256':sha}
    def mark_coverage(self,owner,kind,hour_utc,*,collector_complete):
        self.owner(owner)
        if collector_complete is not True or kind not in KINDS:raise ValueError('COMPLETE_NATIVE_COLLECTOR_REQUIRED')
        h=iso(hour(stamp(hour_utc)))
        with self.db(True) as db:db.execute('INSERT OR IGNORE INTO nox_evolution_coverage VALUES(?,?,?)',(owner,h,kind))
    def _events(self,owner,start,end,limit=5001,*,allow_sentinel=False):
        with self.db() as db:
            rows=db.execute('SELECT payload,digest FROM nox_evolution_events WHERE owner=? AND at_utc>=? AND at_utc<? ORDER BY at_utc DESC,event_id DESC LIMIT ?',(owner,iso(start),iso(end),limit)).fetchall()
        if len(rows)>=limit and not allow_sentinel:raise ValueError('WINDOW_TOO_DENSE_REDUCE_RANGE')
        # The snapshot requests one overflow sentinel; finalization must
        # still reject a dense hour instead of publishing an incomplete card.
        events=[]
        for payload,recorded_sha in rows:
            try: event=json.loads(payload)
            except (TypeError,ValueError) as exc: raise ValueError('EVENT_DIGEST_MISMATCH') from exc
            if not (isinstance(event,dict) and isinstance(recorded_sha,str) and
                    SHA.fullmatch(recorded_sha) and digest(event)==recorded_sha):
                raise ValueError('EVENT_DIGEST_MISMATCH')
            events.append(event)
        return events
    def _coverage(self,owner,h):
        with self.db() as db:return {x[0] for x in db.execute('SELECT kind FROM nox_evolution_coverage WHERE owner=? AND hour_utc=?',(owner,iso(h)))}
    def finalize_hour(self,owner,h,*,now=None):
        self.owner(owner);now=now or datetime.now(timezone.utc);h=hour(h)
        if h+timedelta(hours=1)>now:raise ValueError('HOUR_NOT_CLOSED')
        rows=self._events(owner,h,h+timedelta(hours=1));groups=summarize(rows,self._coverage(owner,h),h,h+timedelta(hours=1))
        card={'id':'hour-'+h.strftime('%Y%m%dT%H'),'start':iso(h),'end':iso(h+timedelta(hours=1)),'closed':True,'groups':groups}
        payload=encode(card)
        with self.db(True) as db:db.execute('INSERT INTO nox_evolution_hours VALUES(?,?,?,?) ON CONFLICT(owner,hour_utc) DO UPDATE SET payload=excluded.payload,digest=excluded.digest',(owner,iso(h),payload,digest(card)))
        return card
    def hourly_tick(self,owner,now=None,catchup_hours=24):
        """Invoke from existing dispatcher, not from a new timer/daemon."""
        self.owner(owner);now=now or datetime.now(timezone.utc)
        if type(catchup_hours) is not int or not 1<=catchup_hours<=168:raise ValueError('INVALID_HOURS')
        end=hour(now)
        return [self.finalize_hour(owner,end-timedelta(hours=i),now=now) for i in range(1,catchup_hours+1)]
    def persisted_hour(self, owner, h, expected_groups):
        """Independent S03 readback; an in-memory aggregation is NOT a saved hour.

        A missing, tampered or stale row is a HOLD. It never becomes a completed
        hourly card simply because the wall clock crossed the hour boundary.
        """
        key=iso(h)
        expected={'id':'hour-'+h.strftime('%Y%m%dT%H'),'start':key,
                  'end':iso(h+timedelta(hours=1)),'closed':True,
                  'groups':expected_groups}
        with self.db() as db:
            found=db.execute('SELECT payload,digest FROM nox_evolution_hours WHERE owner=? AND hour_utc=?',
                             (owner,key)).fetchone()
        if found is None:
            return {**expected,'closed':False,'readback_verified':False,
                    'readback_state':'HOLD_PERSISTED_HOUR_MISSING'}
        try:
            payload=json.loads(found[0])
            if not (isinstance(payload,dict) and isinstance(found[1],str) and
                    SHA.fullmatch(found[1]) and digest(payload)==found[1] and payload==expected):
                raise ValueError('HOLD_PERSISTED_HOUR_STALE_OR_TAMPERED')
        except (ValueError,TypeError,KeyError):
            return {**expected,'closed':False,'readback_verified':False,
                    'readback_state':'HOLD_PERSISTED_HOUR_STALE_OR_TAMPERED'}
        return {**payload,'readback_verified':True,'readback_state':'S03_PERSISTED_HOUR_READBACK',
                'readback_sha256':found[1]}

    def snapshot(self,owner,now=None,hours=24,telemetry=None):
        self.owner(owner);now=now or datetime.now(timezone.utc)
        if type(hours) is not int or not 1<=hours<=168:raise ValueError('INVALID_HOURS')
        start=hour(now)-timedelta(hours=hours-1);end=hour(now)+timedelta(hours=1)
        # Query one extra row to detect overflow, but never ship >5000 records
        # to the existing browser contract (which rejects an oversized response).
        fetched=self._events(owner,start,min(end,now+timedelta(seconds=1)),limit=5001,allow_sentinel=True)
        truncated=len(fetched)>5000
        events=fetched[:5000]
        cards=[];all_coverage=set(KINDS);expected_closed=0;verified_closed=0
        for i in range(hours):
            h=start+timedelta(hours=i);covered=self._coverage(owner,h);all_coverage &= covered
            groups=summarize(events,covered,h,h+timedelta(hours=1))
            if h+timedelta(hours=1)<=now:
                expected_closed+=1
                card=self.persisted_hour(owner,h,groups)
                verified_closed+=int(card['readback_verified'])
            else:
                card={'id':'hour-'+h.strftime('%Y%m%dT%H'),'start':iso(h),
                      'end':iso(h+timedelta(hours=1)),'closed':False,'groups':groups,
                      'readback_verified':False,'readback_state':'HOUR_NOT_CLOSED'}
            cards.append(card)
        # Fresh API snapshot time cannot relabel old GPU samples as live.
        sample=telemetry if isinstance(telemetry,Mapping) else {}
        try:
            observed=stamp(sample.get('observed_at_utc'))
            sample_fresh=0 <= (now-observed).total_seconds() <= 120
        except (ValueError,TypeError,OverflowError,AttributeError):
            sample_fresh=False
        metrics={}
        for k in ('ttft_ms','tokens_per_second','gpu0_percent','gpu1_percent','ram_percent'):
            v=sample.get(k)
            metrics[k]=v if sample_fresh and type(v) in (float,int) and math.isfinite(v) and v>=0 and ('percent' not in k or v<=100) else None
        groups=summarize(events,all_coverage,start,end)
        if truncated:
            # A clipped list cannot prove complete learning or a true zero.
            # Keep source events visible, but never publish a partial sum as
            # verified optimizer updates / knowledge / deploys.
            groups={kind:{**group,'value':None,'complete':False,
                          'state':'blocked',
                          'summary':f"{LABELS[kind]}: HOLD · окно превышает 5000 событий; подтверждённый итог неизвестен"}
                    for kind,group in groups.items()}
        return {'schema':SCHEMA,'mode':'native','generated_at':iso(now),'window_start':iso(start),'timezone':'Europe/Moscow','groups':groups,'metrics':metrics,'hours':list(reversed(cards)),'events':events,'truncated':truncated,
                'hourly_readback':{'expected_closed':expected_closed,'persisted_verified':verified_closed,
                                   'complete':not truncated and expected_closed==verified_closed}}

def register_progress(app, trusted, journal):
    """Mount read-only owner-auth route inside the existing FastAPI app."""
    import asyncio, inspect
    from fastapi import Request
    from fastapi.responses import JSONResponse
    auth=trusted.get('_session_ok');deny=trusted.get('_unauthorized');owner=trusted.get('progress_owner_scope')
    if not all(callable(x) for x in (auth,deny,owner)):raise ValueError('EXISTING_OWNER_AUTH_REQUIRED')
    if any(getattr(r,'path',None)=='/api/nox/evolution' for r in app.routes):raise ValueError('DUPLICATE_ROUTE')
    async def resolved(callback,*args):
        # Async owner callbacks must be AWAITED; a coroutine is truthy even
        # when the real permission result is False. Never grant on truthiness.
        result=callback(*args)
        return await asyncio.wait_for(result,timeout=2) if inspect.isawaitable(result) else result
    async def endpoint(request):
        try:
            allowed=await resolved(auth,request)
        except Exception:
            allowed=False
        if allowed is not True:
            # Preserve the original owner's denial response where available.
            try:
                denial=await resolved(deny)
                if denial is not None:return denial
            except Exception:
                pass
            return JSONResponse({'schema':SCHEMA,'mode':'unavailable','state':'HOLD','reason':'OWNER_SESSION_REQUIRED'},status_code=401,headers={'Cache-Control':'no-store'})
        try:
            count=int(request.query_params.get('hours','24'))
            if not 1<=count<=168:raise ValueError('INVALID_HOURS')
            who=journal.owner(await resolved(owner,request))
            value=await asyncio.wait_for(asyncio.to_thread(journal.snapshot,who,hours=count),timeout=8)
            return JSONResponse(value,headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})
        except Exception:
            return JSONResponse({'schema':SCHEMA,'mode':'unavailable','state':'HOLD','reason':'NATIVE_PROGRESS_NOT_VERIFIED'},status_code=503,headers={'Cache-Control':'no-store'})
    endpoint.__annotations__['request']=Request
    app.add_api_route('/api/nox/evolution',endpoint,methods=['GET'])
