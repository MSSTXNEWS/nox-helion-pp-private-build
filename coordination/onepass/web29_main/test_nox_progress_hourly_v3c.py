import importlib.util
import json
import sqlite3
import tempfile
import unittest
import asyncio
import sys
import types
from unittest.mock import patch
from datetime import datetime, timezone, timedelta
from pathlib import Path

module_path = Path(__file__).parent / 'integration/progress/nox_progress.py'
spec = importlib.util.spec_from_file_location('nox_progress', module_path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
NOW = datetime(2026,11,16,2,45,tzinfo=timezone.utc)
OWNER='owner-1'

class S03HoursTest(unittest.TestCase):
  def setUp(self):
    self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
    self.path=Path(self.tmp.name)/'s03.db'
    with sqlite3.connect(self.path) as db: db.execute('CREATE TABLE s03_items (id INTEGER PRIMARY KEY)')
    self.j=mod.ProgressJournal(self.path,lambda _owner,_event:True)
    self.j.initialize()
  def test_no_hourly_write_no_fake_closed_card(self):
    x=self.j.snapshot(OWNER,NOW,4)
    self.assertEqual(x['mode'],'native')
    self.assertEqual(x['hourly_readback'],{'expected_closed':3,'persisted_verified':0,'complete':False})
    self.assertEqual(sum(h['closed'] for h in x['hours']),0)
    self.assertEqual({h['readback_state'] for h in x['hours'] if h['end']<=mod.iso(NOW)}, {'HOLD_PERSISTED_HOUR_MISSING'})
  def test_hourly_tick_durable_digest_and_independent_db_readback(self):
    self.j.hourly_tick(OWNER,NOW,3)
    x=self.j.snapshot(OWNER,NOW,4)
    self.assertEqual(x['hourly_readback'],{'expected_closed':3,'persisted_verified':3,'complete':True})
    for h in x['hours']:
      if h['closed']:
        self.assertEqual(h['readback_state'],'S03_PERSISTED_HOUR_READBACK')
        self.assertEqual(len(h['readback_sha256']),64)
    with sqlite3.connect(self.path) as db:
      self.assertEqual(db.execute('SELECT count(*) FROM nox_evolution_hours').fetchone()[0],3)
  def test_tampered_digest_cannot_promote_hour(self):
    self.j.hourly_tick(OWNER,NOW,1)
    hour=mod.iso(mod.hour(NOW)-timedelta(hours=1))
    with sqlite3.connect(self.path) as db:
      db.execute('UPDATE nox_evolution_hours SET digest=? WHERE owner=? AND hour_utc=?',('f'*64,OWNER,hour))
    h=self.j.snapshot(OWNER,NOW,2)['hours'][1]
    self.assertFalse(h['closed']);self.assertFalse(h['readback_verified'])
    self.assertEqual(h['readback_state'],'HOLD_PERSISTED_HOUR_STALE_OR_TAMPERED')
  def test_coverage_after_finalization_prevents_stale_success(self):
    self.j.hourly_tick(OWNER,NOW,1)
    h=mod.iso(mod.hour(NOW)-timedelta(hours=1))
    self.j.mark_coverage(OWNER,'knowledge',h,collector_complete=True)
    snap=self.j.snapshot(OWNER,NOW,2)
    self.assertEqual(snap['hourly_readback']['persisted_verified'],0)
    self.assertEqual(snap['hours'][1]['readback_state'],'HOLD_PERSISTED_HOUR_STALE_OR_TAMPERED')
  def test_owner_isolation_even_with_persisted_other_owner_hours(self):
    self.j.hourly_tick(OWNER,NOW,2)
    other=self.j.snapshot('owner-2',NOW,3)
    self.assertEqual(other['hourly_readback']['persisted_verified'],0)
  def test_late_event_rebuilds_persisted_hour_with_native_proof(self):
    self.j.hourly_tick(OWNER,NOW,1)
    record={'id':'memory-1','kind':'knowledge','subject_key':'subject-1',
      'at':'2026-11-16T01:23:00Z','title':'S03 item','summary':'Persisted', 'detail':'Read back',
      'state':'verified','evidence':'native','tags':['memory'], 'sources':[],
      'proof':{'receipt_sha256':'a'*64,'records_added':2,'s03_readback_sha256':'b'*64}}
    self.j.record(OWNER,record,now=NOW)
    x=self.j.snapshot(OWNER,NOW,2)
    self.assertEqual(x['hourly_readback']['persisted_verified'],1)
    self.assertEqual(x['hours'][1]['groups']['knowledge']['value'],2)
    self.assertEqual(x['hours'][1]['groups']['knowledge']['summary'],'Знания: не менее 2 новых записей S03')
  def test_only_successful_optimizer_updates_count(self):
    proof={'receipt_sha256':'a'*64,'step_before':5,'step_after':8,
           'tensor_before':'b'*64,'tensor_after':'c'*64,'checkpoint_sha256':'d'*64}
    event={'id':'train-1','kind':'weights','subject_key':'train-1',
           'at':'2026-11-16T02:25:00Z','title':'Native training','summary':'Test',
           'detail':'Native checkpoint','state':'verified','evidence':'native',
           'tags':['optimizer'],'sources':[],'proof':proof}
    for count in (None,0,4):
      invalid={**event,'proof':{**proof,'successful_optimizer_updates':count}}
      with self.assertRaisesRegex(ValueError,'SUCCESSFUL_OPTIMIZER_UPDATES_REQUIRED'):
        self.j.record(OWNER,invalid,now=NOW)
    self.j.record(OWNER,{**event,'proof':{**proof,'successful_optimizer_updates':2,
                                        'skipped_optimizer_updates':1}},now=NOW)
    snap=self.j.snapshot(OWNER,NOW,2)
    self.assertEqual(snap['groups']['weights']['value'],2)
    self.assertEqual(snap['events'][0]['delta'],2)

  def test_stale_or_unstamped_telemetry_never_becomes_live(self):
    values={'ttft_ms':280,'gpu0_percent':45,'gpu1_percent':101}
    self.assertIsNone(self.j.snapshot(OWNER,NOW,2,telemetry=values)['metrics']['ttft_ms'])
    stale={**values,'observed_at_utc':mod.iso(NOW-timedelta(minutes=4))}
    self.assertIsNone(self.j.snapshot(OWNER,NOW,2,telemetry=stale)['metrics']['gpu0_percent'])
    future={**values,'observed_at_utc':mod.iso(NOW+timedelta(minutes=1))}
    self.assertIsNone(self.j.snapshot(OWNER,NOW,2,telemetry=future)['metrics']['ttft_ms'])
    fresh={**values,'observed_at_utc':mod.iso(NOW-timedelta(seconds=40))}
    metrics=self.j.snapshot(OWNER,NOW,2,telemetry=fresh)['metrics']
    self.assertEqual(metrics['ttft_ms'],280)
    self.assertEqual(metrics['gpu0_percent'],45)
    self.assertIsNone(metrics['gpu1_percent'])

  def test_no_implicit_owner_write_on_snapshot(self):
    self.j.snapshot(OWNER,NOW,4)
    with sqlite3.connect(self.path) as db:
      self.assertEqual(db.execute('SELECT count(*) FROM nox_evolution_hours').fetchone()[0],0)

  def _owner_route(self, auth, scope, deny):
    # Exercise the existing FastAPI mount without installing a second service
    # or requiring FastAPI on an otherwise pure SQLite CI runner.
    fake=types.ModuleType('fastapi')
    fake.Request=type('FakeRequest',(object,),{})
    responses=types.ModuleType('fastapi.responses')
    class FakeJSONResponse:
      def __init__(self,data,status_code=200,headers=None):
        self.status_code=status_code
        self.body=json.dumps(data).encode('utf-8')
    responses.JSONResponse=FakeJSONResponse
    class App:
      def __init__(self):self.routes=[]
      def add_api_route(self,path,endpoint,methods):
        self.routes.append(types.SimpleNamespace(path=path))
        self.endpoint=endpoint
    app=App()
    with patch.dict(sys.modules,{'fastapi':fake,'fastapi.responses':responses}):
      mod.register_progress(app,{'_session_ok':auth,'_unauthorized':deny,'progress_owner_scope':scope},self.j)
    return app.endpoint

  def test_async_false_owner_auth_fails_closed_before_readback(self):
    async def denied(_):return False
    async def owner(_):raise AssertionError('Owner scope must not be read after denial')
    async def deny():return types.SimpleNamespace(status_code=401)
    endpoint=self._owner_route(denied,owner,deny)
    response=asyncio.run(endpoint(types.SimpleNamespace(query_params={'hours':'2'})))
    self.assertEqual(response.status_code,401)

  def test_async_true_owner_scope_uses_existing_s03(self):
    async def allowed(_):return True
    async def owner(_):return OWNER
    endpoint=self._owner_route(allowed,owner,lambda:types.SimpleNamespace(status_code=401))
    response=asyncio.run(endpoint(types.SimpleNamespace(query_params={'hours':'2'})))
    self.assertEqual(response.status_code,200)
    self.assertEqual(json.loads(response.body)['schema'],mod.SCHEMA)
    self.assertEqual(json.loads(response.body)['hourly_readback']['persisted_verified'],0)

  def test_truthy_nonboolean_or_auth_error_is_never_permission(self):
    async def owner(_):raise AssertionError('Owner scope must not be read after denial')
    async def broken(_):raise RuntimeError('owner session unavailable')
    request=types.SimpleNamespace(query_params={'hours':'2'})
    for invalid in (lambda _:{'ok':True},lambda _:'yes',broken):
      endpoint=self._owner_route(invalid,owner,lambda:types.SimpleNamespace(status_code=401))
      self.assertEqual(asyncio.run(endpoint(request)).status_code,401)

if __name__=='__main__':unittest.main(verbosity=2)
