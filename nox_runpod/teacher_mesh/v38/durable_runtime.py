"""NOX V38 durable native turn controller (source-only, requires existing OneHost).

All assistant text comes from the existing NOX model. Event persistence goes through
existing authorised S03; no new database or server. A user-visible chunk is
acknowledged only after S03 returns a verified durable receipt. Optional second
pass can correct the user-visible draft only after real verification evidence.
"""
from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from hashlib import sha256
import json
import re
import threading
import time
from typing import Any

from .synaptic_brain import SynapticBrain, Session

SEGMENTS = ('M0', 'M1', 'M2', 'M3', 'M4', 'M5', 'M6', 'M7')
SHA256 = re.compile(r'^[a-f0-9]{64}$')
SCOPE = re.compile(r'^[A-Za-z0-9._:-]{1,100}$')


def native_query_plan(prompt: str) -> dict[str, Any]:
    """All *indexed* S03 segments are eligible; never scan full history to prompt."""
    q = prompt.strip()[:8000]
    low = q.casefold()
    variants = [q]
    if any(w in low for w in ('вчера','завтра','раньше','дат','врем','прошл','сегодня','when','fecha','ayer','today')):
        variants.append('timeline chronological event history source date update correction ' + q[:240])
    if any(w in low for w in ('помни','вспомни','прошл','remember','recuerda','истори','ты кто','родил','генез')):
        variants.append('S03 M1 M3 M7 autobiography verified past conversation Genesis event ' + q[:240])
    if any(w in low for w in ('умеешь','навык','задач','трен','обуч','поглот','learn','skill','trainer')):
        variants.append('S03 M2 M4 M7 verified skill checkpoint optimizer capabilities ' + q[:240])
    if any(w in low for w in ('люблю','предпоч','интерес','личност','эмоц','чувств','persona','prefer')):
        variants.append('S03 M5 M6 preferences owner consent persona mood interaction ' + q[:240])
    return {'queries': variants[:4], 'segments': list(SEGMENTS), 'strategy':'indexed_multi_session_temporal_source_graph',
            'require_verified': True, 'include_superseded':False}


class WarmS03Cache:
    """Scope+revision-keyed ephemeral RAM cache, never canonical memory.

    Without a trustworthy native S03 revision the cache is BYPASSED, not stale.
    This is only a read-through adapter to existing S03 callbacks. Reset it on
    owner revocation, privacy settings change or after verified writes.
    """
    def __init__(self, recall: Callable[[Session,str,int],list[dict]],
                 revision: Callable[[Session],str] | None,
                 *, max_bytes:int=8*1024*1024, ttl_seconds:float=45.0):
        if not callable(recall):raise TypeError('NATIVE_S03_RECALL_REQUIRED')
        if not 4096<=max_bytes<=256*1024*1024:raise ValueError('RAM_CACHE_BUDGET')
        if not 1<=ttl_seconds<=300:raise ValueError('TTL_BOUNDS')
        self.recall=recall; self.revision=revision
        self.max_bytes=max_bytes; self.ttl=ttl_seconds
        self.entries:OrderedDict[tuple,tuple[float,int,list[dict]]]=OrderedDict()
        self.bytes=0; self.lock=threading.RLock(); self.stats={'hits':0,'misses':0,'bypasses':0}

    def invalidate(self, session:Session|None=None):
        with self.lock:
            if session is None:self.entries.clear();self.bytes=0;return
            scope=(session.tenant,session.principal,session.chat_id)
            for key in list(self.entries):
                if key[:3]==scope:
                    _,n,_=self.entries.pop(key);self.bytes-=n

    def __call__(self,session:Session,prompt:str,limit:int)->list[dict]:
        if not self.revision:
            self.stats['bypasses']+=1
            return self.recall(session,prompt,limit)
        try:
            rev=self.revision(session)
        except Exception:
            self.stats['bypasses']+=1
            return self.recall(session,prompt,limit)
        if not isinstance(rev,str) or not 1<=len(rev)<=128:
            self.stats['bypasses']+=1
            return self.recall(session,prompt,limit)
        key=(session.tenant,session.principal,session.chat_id,rev,
             sha256(prompt.encode('utf8')).hexdigest(),int(limit))
        now=time.monotonic()
        with self.lock:
            for old in list(self.entries):
                if self.entries[old][0] <= now:
                    _,n,_=self.entries.pop(old);self.bytes-=n
            found=self.entries.get(key)
            if found:
                self.entries.move_to_end(key);self.stats['hits']+=1
                return [dict(x) for x in found[2]]
        self.stats['misses']+=1
        got=self.recall(session,prompt,limit)
        if not isinstance(got,list):return got
        # Store only verified, non-superseded, exact-scope native records.
        safe=[dict(x) for x in got[:min(4*limit,80)] if isinstance(x,dict)
              and x.get('verified') is True and not x.get('superseded')
              and (x.get('tenant'),x.get('principal'),x.get('chat_id'))
                 ==(session.tenant,session.principal,session.chat_id)
              and x.get('segment') in SEGMENTS]
        try:n=len(json.dumps(safe,ensure_ascii=False).encode('utf8'))
        except (ValueError,TypeError):return got
        if n>self.max_bytes//2:return got
        with self.lock:
            # Avoid caching if revision changed while native callback was running.
            try: same=self.revision(session)==rev
            except Exception:same=False
            if same:
                old=self.entries.pop(key,None)
                if old:self.bytes-=old[1]
                self.entries[key]=(now+self.ttl,n,safe);self.bytes+=n
                while self.bytes>self.max_bytes and self.entries:
                    _,(_,removed,_)=self.entries.popitem(last=False);self.bytes-=removed
        return got


@dataclass(frozen=True)
class DurablePorts:
    """Host callbacks are authenticated and must run S03 transactions durably.

    `s03_append` must return {verified: true, event_id: nonempty, durable: true}.
    The callback, not this module, must set SQLite WAL + synchronous FULL,
    perform idempotency on (turn_id,seq), and commit a native transaction.
    """
    s03_append:Callable[[Session,dict],Mapping[str,Any]]
    s03_backup:Callable[[Session],Mapping[str,Any]]|None=None
    s03_backup_verify:Callable[[Session,Mapping[str,Any]],bool]|None=None
    native_revision:Callable[[Session],str]|None=None


@dataclass(frozen=True)
class TurnPolicy:
    chunk_chars:int=130
    flush_ms:int=250
    max_turn_chars:int=40000
    max_verification_chars:int=5000
    first_chunk_chars:int=36
    first_flush_ms:int=90
    def validate(self):
        if not 16<=self.chunk_chars<=2048 or not 25<=self.flush_ms<=1500:
            raise ValueError('BAD_STREAM_BATCHING')
        if not 2000<=self.max_turn_chars<=100000 or not 300<=self.max_verification_chars<=16000:
            raise ValueError('BAD_TURN_LIMITS')
        if not 10<=self.first_chunk_chars<=self.chunk_chars or not 25<=self.first_flush_ms<=self.flush_ms:
            raise ValueError('BAD_FIRST_CHUNK_POLICY')


class DurableTurn:
    """Journal-before-display progressive NOX messages, with optional verified revision.

    `model_stream`: existing NOX inference callback yielding text deltas.
    `postcheck`: optional **real** source/tool verifier returning trusted host-owned
    {verified: true, evidence: ...}, not a language-model claim of correctness.
    `revise_stream`: optional existing NOX model callback to synthesize a final
    revision from verified evidence. UI needs `replace_revision` support to
    visually replace draft; else display a separate correction and preserve log.
    No hidden model chain-of-thought is exposed or persisted by this module.
    """
    def __init__(self, brain:SynapticBrain, storage:DurablePorts,
                 policy:TurnPolicy=TurnPolicy()):
        policy.validate();self.brain=brain;self.storage=storage;self.policy=policy
        if not callable(storage.s03_append):raise TypeError('NATIVE_S03_PERSIST_REQUIRED')

    def _append(self,session:Session,turn_id:str,seq:int,kind:str,body:Mapping[str,Any])->dict:
        if not SCOPE.fullmatch(turn_id):raise ValueError('TURN_ID_REQUIRED')
        if not self.brain._gate(session):raise RuntimeError('STOP_OR_SCOPE_REVOKED')
        payload={'turn_id':turn_id,'seq':seq,'kind':kind,'schema':'NOX_V38_S03_JOURNAL',
                 'body':dict(body)}
        try:receipt=self.storage.s03_append(session,payload)
        except Exception:raise RuntimeError('HOLD_S03_WRITE_FAILED') from None
        if (not isinstance(receipt,Mapping) or receipt.get('verified') is not True
            or receipt.get('durable') is not True or not isinstance(receipt.get('event_id'),str)
            or not receipt['event_id']):
            raise RuntimeError('HOLD_NO_DURABLE_RECEIPT')
        return {'event_id':receipt['event_id'][:128], 'seq':seq}

    def run(self,session:Session,prompt:str,turn_id:str,
            model_stream:Callable[[str,dict],Iterator[str]], *,
            deep:bool=False,postcheck:Callable[[str,dict],Mapping[str,Any]]|None=None,
            revise_stream:Callable[[str,dict],Iterator[str]]|None=None,
            ui_replace_supported:bool=False)->Iterator[dict]:
        try:
            session.validate()
            self._append(session,turn_id,0,'user_message',{'text':prompt[:8000]})
        except Exception as e:
            yield {'type':'hold','state':str(e) if isinstance(e,RuntimeError) else 'HOLD_INPUT'};return
        seq=1;answer='';pending='';last_flush=time.monotonic()
        # Existing brain.stream invokes exactly ONE NOX model, returns real deltas.
        for event in self.brain.stream(session,prompt,model_stream,deep=deep):
            kind=event.get('type')
            if kind=='hold':
                yield event;return
            if kind in ('cortex_ready','phase'):
                yield event;continue
            if kind!='delta':continue
            delta=event.get('text','')
            if len(answer)+len(pending)+len(delta)>self.policy.max_turn_chars:
                yield {'type':'hold','state':'HOLD_TURN_TOO_LONG'};return
            pending+=delta
            required_chars = self.policy.first_chunk_chars if seq == 1 else self.policy.chunk_chars
            max_delay_ms = self.policy.first_flush_ms if seq == 1 else self.policy.flush_ms
            if len(pending)>=required_chars or (time.monotonic()-last_flush)*1000>=max_delay_ms:
                try:receipt=self._append(session,turn_id,seq,'assistant_draft_chunk',{'text':pending})
                except RuntimeError as e:
                    yield {'type':'hold','state':str(e)};return
                answer+=pending
                yield {'type':'delta','text':pending,'seq':seq,'evidence_receipt':receipt['event_id'],
                       'visibility':'provisional'}
                pending='';seq+=1;last_flush=time.monotonic()
        if pending:
            try:receipt=self._append(session,turn_id,seq,'assistant_draft_chunk',{'text':pending})
            except RuntimeError as e:
                yield {'type':'hold','state':str(e)};return
            answer+=pending
            yield {'type':'delta','text':pending,'seq':seq,'evidence_receipt':receipt['event_id'],
                   'visibility':'provisional'}
            seq+=1
        if not answer.strip():
            yield {'type':'hold','state':'HOLD_EMPTY_NOX_ANSWER'};return
        verified=None
        if postcheck is not None and revise_stream is not None:
            try:
                source=postcheck(prompt,{'draft':answer[:self.policy.max_turn_chars],
                                        'turn_id':turn_id,'session_scope':session.chat_id})
                if not isinstance(source,Mapping) or source.get('verified') is not True:
                    source=None
            except Exception:source=None
            if source is not None:
                evidence=source.get('evidence')
                # The host verifier must return structured source ids, NOT raw arbitrary instructions.
                if (isinstance(evidence,list) and len(evidence)<=16 and all(
                    isinstance(x,Mapping) and isinstance(x.get('source_uri'),str)
                    and x['source_uri'].startswith(('s03://','https://','nox-checkpoint://'))
                    and x.get('verified') is True for x in evidence)):
                    verified=[{'source_uri':x['source_uri'][:300],
                               'fact':str(x.get('fact',''))[:360]} for x in evidence]
            if verified is not None and self.brain._gate(session):
                yield {'type':'verification','state':'REAL_SOURCE_CHECK_COMPLETED',
                       'sources':len(verified)}
                try:
                    revision=''.join(revise_stream(prompt,{'draft':answer,'verified_evidence':verified,
                        'revision_instruction':'Use only the installed NOX model. Produce final answer; no fabricated sources or consciousness claims.'}))
                except Exception:revision=''
                if 0<len(revision)<=self.policy.max_turn_chars and revision.strip():
                    try:receipt=self._append(session,turn_id,seq,'assistant_verified_revision',{
                        'text':revision,'sources':verified})
                    except RuntimeError as e:
                        yield {'type':'hold','state':str(e)};return
                    yield {'type':'revision','text':revision,'seq':seq,
                           'presentation':'replace_provisional' if ui_replace_supported else 'append_correction',
                           'receipt':receipt['event_id']}
                    answer=revision;seq+=1
        try:receipt=self._append(session,turn_id,seq,'assistant_final',{'sha256':sha256(answer.encode('utf8')).hexdigest(),
                                                                      'chars':len(answer)})
        except RuntimeError as e:
            yield {'type':'hold','state':str(e)};return
        yield {'type':'done','state':'S03_DURABLE_TURN','receipt':receipt['event_id'],
               'output_chars':len(answer),'full_memory_scan':False,
               'verified_training_steps':'NOT_CHECKED'}

    def request_backup(self,session:Session)->dict:
        """NOX OneHost performs ONLINE native S03 backup and offsite verify.

        Backups must capture a consistent native SQLite snapshot and associated
        WAL, metadata/Genesis ledger, encrypted when required. Never delete source.
        """
        if not self.brain._gate(session):return {'state':'HOLD_SCOPE_OR_STOP'}
        if not (callable(self.storage.s03_backup) and callable(self.storage.s03_backup_verify)):
            return {'state':'HOLD_NO_EXTERNAL_BACKUP_CONNECTOR'}
        try:
            receipt=self.storage.s03_backup(session)
            if not isinstance(receipt,Mapping) or receipt.get('external') is not True:
                return {'state':'HOLD_NOT_OFFSITE'}
            if self.storage.s03_backup_verify(session,receipt) is not True:
                return {'state':'HOLD_BACKUP_NOT_VERIFIED'}
        except Exception:return {'state':'HOLD_BACKUP_FAILURE'}
        return {'state':'OFFSITE_BACKUP_READBACK_VERIFIED','receipt_id':str(receipt.get('id',''))[:100]}
