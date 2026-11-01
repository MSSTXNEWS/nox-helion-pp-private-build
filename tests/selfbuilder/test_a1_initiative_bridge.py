"""A.1 source tests. All callbacks simulate existing ports; never claim real E07."""
import unittest
from datetime import datetime, timezone
from unittest.mock import Mock
from nox_selfbuilder.a1_initiative_bridge import A1InitiativeBridge

NOW = datetime(2026, 11, 1, 19, 30, tzinfo=timezone.utc)
HEAD = 'a' * 40
SHA = 'b' * 64

class Fixture(unittest.TestCase):
    def setUp(self):
        self.stop_state = False
        self.epoch = 7
        self.head = HEAD
        self.grants = {'evolution.autonomy.read', 'evolution.competency.propose'}
        self.worm = Mock()
        self.worm.boot.return_value = {'state':'RESEARCH_READY_FOR_EXISTING_IDLE_TICK'}
        self.worm.tick.return_value = {'status':'READY_FOR_NATIVE_APPROVED_TICK'}
        self.idea = Mock()
        self.idea.tick.return_value = {'schema':'NOX-GROWTH-AUTONOMOUS-IDEAS-v1'}
        self.saved = []
        self.lessons = []
        self.verify = lambda _s, _p: True
        self.engine = A1InitiativeBridge(
            worm_autopilot=self.worm, idea_loop=self.idea,
            native_authorize=lambda _s,a: a in self.grants,
            native_stop=lambda:self.stop_state,
            native_stop_epoch=lambda:self.epoch,
            current_source_head=lambda:self.head,
            native_s03_recent_lessons=lambda _s,_h:self.lessons,
            native_verify_lesson=lambda s,p:self.verify(s,p),
            native_s03_append_readback=lambda s,c:self.saved.append(c) or True)

    def lesson(self):
        return {'schema':'NOX-S03-NATIVE-ERROR-LESSON-v1',
                'error_id':'EV-NATIVE-001','source_head':HEAD,
                'cause':'native callback exception', 'fix':'fail closed on unknown stop status',
                'regression_sha256':SHA,'source_sha256':SHA,
                'state':'NATIVE_REGRESSION_VERIFIED'}

    def test_existing_owner_boot_and_tick_calls_each_existing_module(self):
        self.assertEqual(self.engine.boot('tenant',now=NOW)['state'], 'READY_FOR_EXISTING_IDLE_TICK')
        self.assertEqual(self.engine.tick('tenant',now=NOW)['state'],'SOURCE_CYCLE_COMPLETED_NOT_INSTALLED')
        self.worm.tick.assert_called_once()
        self.idea.tick.assert_called_once()
        self.assertEqual(len(self.saved),0)

    def test_unset_stop_callback_fails_closed_before_boot(self):
        self.stop_state = None
        self.assertEqual(self.engine.boot('tenant',now=NOW)['state'], 'HOLD')
        self.worm.boot.assert_not_called()

    def test_revocation_after_worm_tick_blocks_p02(self):
        self.engine.boot('tenant',now=NOW)
        self.worm.tick.side_effect = lambda *_args, **_kw: (
            setattr(self,'stop_state',True) or {'status':'READY_FOR_NATIVE_APPROVED_TICK'})
        self.assertEqual(self.engine.tick('tenant',now=NOW)['state'], 'HOLD')
        self.idea.tick.assert_not_called()

    def test_source_head_change_blocks_after_worm(self):
        self.engine.boot('tenant',now=NOW)
        self.head = 'c' * 40
        self.assertEqual(self.engine.tick('tenant',now=NOW)['state'], 'HOLD')
        self.worm.tick.assert_not_called()

    def test_valid_proof_only_creates_owner_review_candidate(self):
        self.engine.boot('tenant',now=NOW)
        self.lessons = [self.lesson()]
        res=self.engine.tick('tenant',now=NOW)
        self.assertEqual(res['verified_lesson_proposals_saved_today'],1)
        self.assertEqual(self.saved[0]['state'],'OWNER_REVIEW_REQUIRED')
        self.assertFalse(self.saved[0]['code_merged'])
        self.assertFalse(res['weights_updated'])
        self.engine.tick('tenant',now=NOW)
        self.assertEqual(len(self.saved),1)

    def test_bad_native_proof_never_writes(self):
        self.engine.boot('tenant',now=NOW)
        self.lessons=[self.lesson()]
        self.verify=lambda *_:False
        self.assertEqual(self.engine.tick('tenant',now=NOW)['state'],'HOLD')
        self.assertEqual(self.saved,[])

    def test_native_acl_revoke_prevents_lesson_write(self):
        self.engine.boot('tenant',now=NOW)
        self.lessons=[self.lesson()]
        self.grants.remove('evolution.competency.propose')
        self.assertEqual(self.engine.tick('tenant',now=NOW)['state'],'HOLD')
        self.assertEqual(self.saved,[])

    def test_s03_failure_not_counted_as_success(self):
        self.engine.boot('tenant',now=NOW)
        self.lessons=[self.lesson()]
        self.engine._save=lambda s,c:False
        self.assertEqual(self.engine.tick('tenant',now=NOW)['state'],'HOLD')
        self.assertEqual(self.engine.tick('tenant',now=NOW)['verified_lesson_proposals_saved_today'],0)

    def test_wrong_tenant_does_not_reuse_boot(self):
        self.engine.boot('tenant',now=NOW)
        self.assertEqual(self.engine.tick('tenant2',now=NOW)['state'],'HOLD')
        self.worm.tick.assert_not_called()

    def test_stop_epoch_change_before_p02_holds(self):
        self.engine.boot('tenant',now=NOW)
        def revoked(*_a,**_kw):
            self.epoch+=1
            return {'status':'READY_FOR_NATIVE_APPROVED_TICK'}
        self.worm.tick.side_effect=revoked
        self.assertEqual(self.engine.tick('tenant',now=NOW)['state'],'HOLD')
        self.idea.tick.assert_not_called()

    def test_untrusted_lesson_schema_does_not_train(self):
        self.engine.boot('tenant',now=NOW)
        self.lessons=[{**self.lesson(),'state':'NATIVE_REGRESSION_UNVERIFIED'}]
        r=self.engine.tick('tenant',now=NOW)
        self.assertEqual(r['state'],'HOLD')
        self.assertFalse(r['models_installed'])

if __name__=='__main__':unittest.main()

class OfficialIntegrationTests(unittest.TestCase):
    def setUp(self):
        Fixture.setUp(self)
        self.grants.add('worm.official_catalog.read')
        self.fetches=[]
        def fetch(url,*,host):
            self.fetches.append((url,host))
            return {'info':{'name':'ruff','version':'1.0.0'},'urls':[]}
        self.engine=A1InitiativeBridge(
            worm_autopilot=self.worm, idea_loop=self.idea,
            native_authorize=lambda _s,a: a in self.grants,
            native_stop=lambda:self.stop_state,
            native_stop_epoch=lambda:self.epoch,
            current_source_head=lambda:self.head,
            native_s03_recent_lessons=lambda _s,_h:self.lessons,
            native_verify_lesson=lambda s,p:self.verify(s,p),
            native_s03_append_readback=lambda s,c:self.saved.append(c) or True,
            native_catalog_queries=lambda s,h:[('pypi','ruff')],
            catalog_fetch_json=fetch)
    def test_official_source_flows_to_existing_s03_data_only(self):
        self.engine.boot('tenant',now=NOW)
        out=self.engine.tick('tenant',now=NOW)
        self.assertEqual(out['reviewed_catalog_candidates_saved_today'],1)
        self.assertEqual(len(self.fetches),1)
        self.assertEqual(self.saved[0]['status'],'SOURCE_OBSERVED_REVIEW_REQUIRED')
        self.assertFalse(self.saved[0]['installed'])
        self.engine.tick('tenant',now=NOW)
        self.assertEqual(len(self.saved),1)
    def test_official_source_s03_fail_is_hold(self):
        self.engine.boot('tenant',now=NOW)
        self.engine._save=lambda *_:False
        self.assertEqual(self.engine.tick('tenant',now=NOW)['state'],'HOLD')
        self.assertEqual(self.engine.tick('tenant',now=NOW)['reviewed_catalog_candidates_saved_today'],0)
    def test_official_source_native_revoke_prevents_network(self):
        self.engine.boot('tenant',now=NOW)
        self.grants.remove('worm.official_catalog.read')
        self.assertEqual(self.engine.tick('tenant',now=NOW)['state'],'HOLD')
        self.assertEqual(self.fetches,[])
