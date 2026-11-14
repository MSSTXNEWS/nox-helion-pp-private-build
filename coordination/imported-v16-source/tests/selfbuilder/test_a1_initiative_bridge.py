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

class A1CompletionRegressionTests(Fixture):
    def test_stop_epoch_changed_between_idle_ticks_requires_new_boot(self):
        self.engine.boot('tenant', now=NOW)
        self.epoch += 1
        self.assertEqual(self.engine.tick('tenant', now=NOW)['state'], 'HOLD')
        self.worm.tick.assert_not_called()
        self.assertEqual(self.engine.boot('tenant', now=NOW)['state'], 'READY_FOR_EXISTING_IDLE_TICK')
        self.assertEqual(self.engine.tick('tenant', now=NOW)['state'], 'SOURCE_CYCLE_COMPLETED_NOT_INSTALLED')

    def test_catalog_approved_query_cannot_exceed_daily_cap(self):
        self.grants.add('worm.official_catalog.read')
        count = iter(range(100))
        names = []
        def query(session, head):
            name = f'pkg{next(count)}'
            names.append(name)
            return [('pypi', name)]
        def fetch(url, *, host):
            return {'info': {'name': names[-1], 'version': '1.0'}, 'urls': []}
        self.engine._catalog_queries = query
        self.engine._catalog_fetch = fetch
        self.engine.boot('tenant', now=NOW)
        for _ in range(30):
            self.assertEqual(self.engine.tick('tenant', now=NOW)['state'], 'SOURCE_CYCLE_COMPLETED_NOT_INSTALLED')
        self.assertEqual(self.engine.tick('tenant', now=NOW)['reason'], 'A1_CATALOG_DAILY_NETWORK_LIMIT')
        self.assertEqual(self.engine._catalog_requests, 30)
        self.assertEqual(self.engine._catalog_saved, 30)
        self.assertEqual(len(self.saved), 30)

    def test_catalog_stop_epoch_revoked_mid_network_never_persists(self):
        self.grants.add('worm.official_catalog.read')
        self.engine._catalog_queries=lambda s,h:[('pypi','ruff')]
        def fetch(url, *, host):
            self.epoch += 1
            return {'info': {'name': 'ruff', 'version': '1.0'}, 'urls': []}
        self.engine._catalog_fetch = fetch
        self.engine.boot('tenant', now=NOW)
        result=self.engine.tick('tenant', now=NOW)
        self.assertEqual(result['state'], 'HOLD')
        self.assertEqual(self.saved, [])

    def test_catalog_failed_request_charges_attempt_budget(self):
        self.grants.add('worm.official_catalog.read')
        self.engine._catalog_queries=lambda s,h:[('pypi','ruff')]
        self.engine._catalog_fetch=lambda u,*,host: (_ for _ in ()).throw(OSError('provider down'))
        self.engine.boot('tenant', now=NOW)
        self.assertEqual(self.engine.tick('tenant', now=NOW)['state'], 'HOLD')
        self.assertEqual(self.engine._catalog_requests, 1)
        self.assertEqual(self.engine._catalog_saved, 0)

    def test_catalog_unbounded_query_denied_before_io(self):
        self.grants.add('worm.official_catalog.read')
        sent=[]
        self.engine._catalog_queries=lambda s,h:[('pypi',str(x)) for x in range(5)]
        self.engine._catalog_fetch=lambda u,*,host:sent.append(u)
        self.engine.boot('tenant', now=NOW)
        self.assertEqual(self.engine.tick('tenant', now=NOW)['state'], 'HOLD')
        self.assertEqual(sent, [])


class A1WowV3DedupAndForgeTests(Fixture):
    def test_same_catalog_query_only_fetched_once_per_utc_day(self):
        self.grants.add('worm.official_catalog.read')
        calls=[]
        self.engine._catalog_queries=lambda s,h:[('pypi','ruff')]
        def fetch(u,*,host):
            calls.append(u)
            return {'info': {'name':'ruff', 'version':'1.2'},'urls':[]}
        self.engine._catalog_fetch=fetch
        self.engine.boot('tenant',now=NOW)
        self.engine.tick('tenant',now=NOW)
        self.engine.tick('tenant',now=NOW)
        self.assertEqual(len(calls),1)
        self.assertEqual(self.engine._catalog_requests,1)
        self.assertEqual(self.engine._catalog_saved,1)

    def test_new_query_still_probes_when_old_is_deduped(self):
        self.grants.add('worm.official_catalog.read')
        names=[['ruff'],['ruff','pytest']]
        self.engine._catalog_queries=lambda s,h:[('pypi',x) for x in names.pop(0)]
        calls=[]
        def fetch(u,*,host):
            name=u.split('/')[-2];calls.append(name)
            return {'info': {'name':name,'version':'1.0'},'urls':[]}
        self.engine._catalog_fetch=fetch
        self.engine.boot('tenant',now=NOW)
        self.engine.tick('tenant',now=NOW)
        self.engine.tick('tenant',now=NOW)
        self.assertEqual(calls,['ruff','pytest'])
        self.assertEqual(self.engine._catalog_saved,2)

    def test_catalog_s03_failure_does_not_cache_unconfirmed_query(self):
        self.grants.add('worm.official_catalog.read')
        self.engine._catalog_queries=lambda s,h:[('pypi','ruff')]
        self.engine._catalog_fetch=lambda u,*,host:{'info':{'name':'ruff','version':'1'},'urls':[]}
        self.engine._save=lambda s,c:False
        self.engine.boot('tenant',now=NOW)
        self.assertEqual(self.engine.tick('tenant',now=NOW)['state'],'HOLD')
        self.assertEqual(len(self.engine._catalog_seen_queries),0)
        self.assertEqual(self.engine._catalog_requests,1)

    def _saved_competency(self):
        self.engine.boot('tenant',now=NOW)
        self.lessons=[self.lesson()]
        self.assertEqual(self.engine.tick('tenant',now=NOW)['state'],'SOURCE_CYCLE_COMPLETED_NOT_INSTALLED')
        self.grants.add('forge.candidate.review')
        return self.saved[0]

    def test_native_forge_review_exact_ack_and_s03_readback(self):
        c=self._saved_competency()
        seen=[]
        def request(s,t):
            seen.append(t)
            return {'schema':'NOX-FORGE-NATIVE-REVIEW-ACK-v1',
                    'state':'ACK_QUEUED_FOR_OWNER_REVIEW',
                    'candidate_sha256':t['candidate_sha256'],'receipt_sha256':'c'*64}
        r=self.engine.stage_competency_for_forge('tenant',c,native_forge_review=request)
        self.assertEqual(r['state'],'QUEUED_FOR_OWNER_REVIEW')
        self.assertFalse(r['production_merged'])
        self.assertFalse(seen[0]['installation_authorized'])
        self.assertEqual(len(self.saved),2)
        again=self.engine.stage_competency_for_forge('tenant',c,native_forge_review=request)
        self.assertEqual(again['state'],'ALREADY_QUEUED_FOR_OWNER_REVIEW')
        self.assertEqual(len(seen),1)

    def test_forge_rejects_fake_unsaved_competency(self):
        c=self._saved_competency()
        c={**c,'candidate_sha256':'f'*64}
        with self.assertRaisesRegex(Exception,'NATIVE_S03_RECEIPT_REQUIRED'):
            self.engine.stage_competency_for_forge('tenant',c,
                native_forge_review=lambda s,t:self.fail('no forge call'))

    def test_forge_invalid_ack_never_advances(self):
        c=self._saved_competency()
        with self.assertRaisesRegex(Exception,'REVIEW_ACK_REQUIRED'):
            self.engine.stage_competency_for_forge('tenant',c,
                native_forge_review=lambda s,t:{'state':'ACK_QUEUED_FOR_OWNER_REVIEW'})
        self.assertEqual(len(self.saved),1)

    def test_forge_stop_or_revoked_acl_never_calls_native(self):
        c=self._saved_competency()
        self.stop_state=True
        with self.assertRaisesRegex(Exception,'STOP_OR_POLICY'):
            self.engine.stage_competency_for_forge('tenant',c,
                native_forge_review=lambda s,t:self.fail('no forge call'))
        self.stop_state=False
        self.grants.remove('forge.candidate.review')
        with self.assertRaisesRegex(Exception,'STOP_OR_POLICY'):
            self.engine.stage_competency_for_forge('tenant',c,
                native_forge_review=lambda s,t:self.fail('no forge call'))

    def test_forge_s03_failure_does_not_mark_review_queued(self):
        c=self._saved_competency()
        self.engine._save=lambda s,c:False
        with self.assertRaisesRegex(Exception,'S03_READBACK_REQUIRED'):
            self.engine.stage_competency_for_forge('tenant',c,
                native_forge_review=lambda s,t:{'schema':'NOX-FORGE-NATIVE-REVIEW-ACK-v1',
                  'state':'ACK_QUEUED_FOR_OWNER_REVIEW', 'candidate_sha256':t['candidate_sha256'],
                  'receipt_sha256':'c'*64})
        self.assertEqual(len(self.engine._forge_review_seen),0)
