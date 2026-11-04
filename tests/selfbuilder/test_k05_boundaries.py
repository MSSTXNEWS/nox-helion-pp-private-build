import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from nox_selfbuilder.builder import SelfBuilder, SelfBuilderHold
from nox_selfbuilder.complete_builder import CompleteBuilder
from nox_selfbuilder.evolution import EvolutionWorker
from nox_selfbuilder.release_governor import inspect_release_task
from test_evolution_worker import Host, job

HEAD = 'a' * 40
EVIDENCE = [{'source_id':'source-owner', 'text':'An approved additive extension.', 'verified':True}]
PY = {'module_path':'extensions/taskqueue/action.py','code':'def action():\n    return 1\n',
      'tests':'def test_action():\n    assert action() == 1\n',
      'rationale':'A small additive source candidate for owner review.', 'sources':['source-owner']}
MULTI = {'files':[{'path':'extensions/taskqueue/action.py','content':PY['code']}],
         'source_ids':['source-owner'],'rationale':PY['rationale']}

class Boundaries(unittest.TestCase):
    def test_revoke_after_generation_no_staged_source(self):
        allowed = [True]
        def generate(*_):
            allowed[0] = False
            return json.dumps(PY)
        b = SelfBuilder(recall=lambda *_:EVIDENCE, generate=generate,
                        native_authorize=lambda *_:allowed[0])
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaisesRegex(SelfBuilderHold,'REVOKED_BEFORE_PERSIST'):
                b.propose(session='native',task='Add an approved extension module',source_head=HEAD,workspace=root)
            self.assertEqual(list(Path(root).iterdir()),[])

    def test_source_head_changes_during_generation_no_staged_source(self):
        current = [HEAD]
        def generate(*_):
            current[0] = 'b' * 40
            return json.dumps(MULTI)
        b = CompleteBuilder(recall=lambda *_:EVIDENCE,generate=generate,
             native_authorize=lambda *_:True,source_admission=lambda h:h==current[0])
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaisesRegex(SelfBuilderHold,'HEAD_DRIFT_BEFORE_PERSIST'):
                b.propose(session='native',task='Add an approved extension module',source_head=HEAD,workspace=root)
            self.assertEqual(list(Path(root).iterdir()),[])

    def test_candidate_has_reviewable_diff_and_hash(self):
        b = SelfBuilder(recall=lambda *_:EVIDENCE,generate=lambda *_:json.dumps(PY),native_authorize=lambda *_:True)
        with tempfile.TemporaryDirectory() as root:
            r=b.propose(session='native',task='Add an approved extension module',source_head=HEAD,workspace=root)
            patch=(Path(root)/r['run_id']/'candidate.patch').read_bytes()
            self.assertEqual(hashlib.sha256(patch).hexdigest(),r['patch_sha256'])
            self.assertIn(b'+++ b/extensions/taskqueue/action.py',patch)
            self.assertFalse(r['integrated'])
            self.assertFalse((Path(root)/PY['module_path']).exists())

    def test_foreign_ticket_is_rejected_before_generation(self):
        class WrongTicket(Host):
            def release_ticket(self,task):
                ticket=super().release_ticket(task);ticket['task_id']='OTHER-TASK';return ticket
        with tempfile.TemporaryDirectory() as root:
            host=WrongTicket([job()]);r=EvolutionWorker(host,workspace=root).tick()
            self.assertEqual(r.status,'HOLD')
            self.assertIn('TICKET_TASK_MISMATCH',r.receipt['reason'])
            self.assertEqual(host.call_count,0)

    def test_textual_permission_is_not_proof(self):
        t={'task_id':'TASK-1','owner_id':'1','head':HEAD,'existing_code_checked':'yes',
           'critical_sources_complete':True,'overlapping_owner_paths':False,
           'required_scope_fixed':True,'code_preimage_sha':'ABSENT'}
        self.assertEqual(inspect_release_task(t,current_head=HEAD).status,'HOLD')
