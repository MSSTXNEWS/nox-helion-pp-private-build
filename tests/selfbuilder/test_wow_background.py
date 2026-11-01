import unittest
from datetime import datetime, timedelta, timezone
from nox_selfbuilder.wow_background import BackgroundWowController, SCHEMA, BackgroundHold

H='a'*40
class Session:
    def validate(self):pass
class BackTests(unittest.TestCase):
    def setUp(self):
        self.session=Session();self.saved=None;self.events=[];self.clock=datetime(2026,11,1,tzinfo=timezone.utc)
        self.consent=True;self.idle=True;self.global_stop=False;self.source=H;self.cancel_calls=0
        self.on_generate=None;self.on_cas=None;self.on_persist=None
        self.proposal={'schema':'NOX-WOW-DESIGN-REVIEW-v1','state':'OWNER_REVIEW_REQUIRED','source_head':H,'proposal_sha256':'e'*64}
        def cas(s,expected,new):
            if self.on_cas:self.on_cas(s,expected,new)
            if (self.saved or {}).get('revision',0)!=expected:return False
            self.saved=dict(new);return True
        def persist(s,p,rev,head):
            if self.on_persist:return self.on_persist(s,p,rev,head)
            # Simulate transactional S03 actor rechecking enabled/revision.
            if not self.saved['enabled'] or self.saved['revision']!=rev or head!=self.source:return False
            self.events.append(('WOW_DESIGN_CANDIDATE',p['proposal_sha256']));return True
        def generate(s,task,permitted):
            if self.on_generate:self.on_generate(permitted)
            if not permitted():raise BackgroundHold('BACKGROUND_STOPPED')
            self.events.append(('P02_GENERATED',task));return dict(self.proposal)
        self.worker=BackgroundWowController(s03_read=lambda s:self.saved,
           s03_compare_and_swap=cas,native_authorize=lambda s,a,v:self.consent,
           native_stop=lambda s:self.global_stop,native_idle=lambda s:self.idle,
           current_head=lambda s:self.source,generate_proposal=generate,
           conditional_s03_proposal=persist,cancel_background=lambda s:self._cancel(),
           now_utc=lambda:self.clock)
    def _cancel(self):self.cancel_calls+=1
    def enable(self):return self.worker.set_enabled(self.session,True)
    def disable(self):return self.worker.set_enabled(self.session,False)
    def test_default_off_no_generation(self):
        self.assertEqual(self.worker.status(self.session)['status'],'OFF')
        self.assertEqual(self.worker.tick(self.session)['status'],'OFF');self.assertEqual(self.events,[])
    def test_toggle_s03_readback(self):
        on=self.enable();self.assertEqual(on['status'],'ON');self.assertEqual(on['source'],'ORIGINAL_S03')
        self.assertFalse(on['auto_install']);self.assertTrue(self.saved['enabled'])
        self.assertEqual(self.disable()['status'],'OFF');self.assertFalse(self.saved['enabled'])
    def test_no_consent_no_toggle(self):
        self.consent=False
        with self.assertRaises(PermissionError):self.enable()
        self.assertIsNone(self.saved)
    def test_idle_only(self):
        self.enable();self.idle=False
        self.assertEqual(self.worker.tick(self.session)['status'],'WAITING_FOR_IDLE')
        self.assertEqual(self.events,[])
    def test_once_per_24_hours(self):
        self.enable();a=self.worker.tick(self.session)
        self.assertEqual(a['status'],'OWNER_REVIEW_REQUIRED');self.assertTrue(a['proposal_saved'])
        self.assertEqual(self.worker.tick(self.session)['status'],'NOT_DUE')
        self.clock+=timedelta(hours=24)
        self.assertTrue(self.worker.tick(self.session)['proposal_saved'])
        self.assertEqual(len([a for a in self.events if a[0]=='P02_GENERATED']),2)
    def test_disable_while_p02_busy_refuses_commit(self):
        self.enable();self.on_generate=lambda check:self.disable()
        result=self.worker.tick(self.session)
        self.assertFalse(result['proposal_saved']);self.assertEqual(self.cancel_calls,1)
        self.assertEqual(self.worker.status(self.session)['status'],'OFF')
        self.assertEqual([a for a in self.events if a[0]=='WOW_DESIGN_CANDIDATE'],[])
    def test_head_drift_suppresses_commit(self):
        self.enable();self.on_generate=lambda check:setattr(self,'source','f'*40)
        result=self.worker.tick(self.session)
        self.assertFalse(result['proposal_saved']);self.assertEqual(self.events,[])
    def test_atomic_s03_revocation_wins(self):
        self.enable()
        self.on_persist=lambda s,p,rev,h:(self.disable(),False)[1]
        self.assertEqual(self.worker.tick(self.session)['status'],'S03_ATOMIC_CONSENT_REVOKED')
    def test_stopped_before_start(self):
        self.enable();self.global_stop=True
        self.assertEqual(self.worker.tick(self.session)['status'],'WAITING_FOR_IDLE')
    def test_failure_retry_thirty_minutes(self):
        self.enable()
        self.proposal['proposal_sha256']='bad'
        self.assertEqual(self.worker.tick(self.session)['status'],'HOLD')
        self.assertEqual(self.worker.tick(self.session)['status'],'NOT_DUE')
        self.clock+=timedelta(minutes=30);self.proposal['proposal_sha256']='e'*64
        self.assertTrue(self.worker.tick(self.session)['proposal_saved'])
    def test_must_not_start_separate_scheduler(self):
        self.enable()
        # Enabling never calls generation or creates a worker thread.
        self.assertEqual(self.events,[])
    def test_disable_doesnt_stop_manual_chat(self):
        self.enable();self.disable();self.assertEqual(self.cancel_calls,0)
    def test_persisted_session_restore_on_new_service(self):
        self.enable();raw=dict(self.saved)
        self.assertTrue(raw['enabled']);self.assertEqual(raw['schema'],SCHEMA)
        self.assertTrue(self.worker.status(self.session)['enabled'])
    def test_no_code_is_automatically_merged(self):
        self.enable();x=self.worker.tick(self.session)
        self.assertFalse(x['code_generated']);self.assertFalse(x['code_installed'])
    def test_fast_disable_reenable_never_persists_stale_proposal(self):
        self.enable()
        self.on_generate=lambda check:(self.disable(),self.enable())
        old=self.worker.tick(self.session)
        self.assertFalse(old['proposal_saved'])
        self.assertEqual([x for x in self.events if x[0]=='WOW_DESIGN_CANDIDATE'],[])
        self.on_generate=None
        self.assertTrue(self.worker.tick(self.session)['proposal_saved'])
    def test_bad_persist_rejects_dropped_atomic_write(self):
        self.enable();self.on_persist=lambda s,p,rev,h:False
        self.assertEqual(self.worker.tick(self.session)['status'],'S03_ATOMIC_CONSENT_REVOKED')
    def test_source_validation_hold(self):
        self.enable();self.source='INVALID'
        self.assertEqual(self.worker.tick(self.session)['reason'],'MANAGED_SOURCE_HEAD_REQUIRED')
if __name__=='__main__':unittest.main()