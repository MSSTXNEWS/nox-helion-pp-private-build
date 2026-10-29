"""Real unchanged original E11+PACK01 component fixture; no PC execution.

NOX_ORIGINAL_ZIP points to the verified immutable archive. NOX_PACK01_PATH
points to an exact owner checkout. Missing input is a failure, never a skip.
"""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

archive = Path(os.environ['NOX_ORIGINAL_ZIP']).resolve()
assert hashlib.sha256(archive.read_bytes()).hexdigest() == 'ff8e2848c7c7ab776b90cbd8ac28e41e3815e96373c3c5f635d7587284629e9a'
sys.path.insert(0, str(archive))
pack = Path(os.environ['NOX_PACK01_PATH']).resolve()
sys.path.insert(0, str(pack))
from native_bridge import HostDenied, HostHold, NativeSession, NoxPackHost
from helion.e11.service import E11Service
from pc_control_owner_port import ExistingPcControlPort, NativePcBinding, ROUTE


class PcPortTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.service = E11Service(Path(self.tmp.name))
        self.session = NativeSession('tenant', 'owner', 'chat', frozenset({ROUTE}), frozenset({ROUTE}))
        self.approvals = []
        def approve(session, route, payload):
            self.approvals.append((session, route, payload))
            return True
        self.host = NoxPackHost(json.loads((pack/'catalog.json').read_text()), native_approve=approve)
        self.binding = lambda session: NativePcBinding(self.session, self.service, 'project_one')
        self.port = ExistingPcControlPort(native_binding_from_session=lambda s:self.binding(s), owner_ready=lambda:True)
        self.port.register(self.host, receipt='R29-A06-PC-ORIGINAL-SOURCE-FIXTURE')

    def call(self, payload, session=None):
        return self.host.execute(ROUTE, payload, session or self.session)

    def test_real_preview_uses_native_project_and_does_not_execute(self):
        result = self.call({'op':'preview','action':'read-system-summary'})
        self.assertEqual(result['project_id'], 'project_one')
        self.assertEqual(result['execution'], 'NOT_AUTHORIZED')
        self.assertFalse(result['mutations_allowed'])
        self.assertIn(result['preview_id'], self.service._pc_preview)
        self.assertEqual(len(self.approvals), 1)
        self.assertEqual(list(Path(self.tmp.name).iterdir()), [])

    def test_actual_stop_revokes_original_preview_tickets(self):
        self.call({'op':'preview','action':'read-system-summary'})
        self.assertTrue(self.service._pc_preview)
        result = self.call({'op':'stop'})
        self.assertEqual(result['status'], 'STOPPED')
        self.assertFalse(self.service._pc_preview)
        self.assertFalse(self.service._pc_enabled)

    def test_page_cannot_enable_execute_or_override_native_identity(self):
        for payload in ({'op':'enable'}, {'op':'execute','preview_id':'a'*32},
                {'op':'preview','action':'read-system-summary','project_id':'other'},
                {'op':'stop','owner_confirmed':True},
                {'op':'preview','action':'run-command'},
                {'op':'preview','action':[]}):
            with self.subTest(payload=payload), self.assertRaises(HostDenied):
                self.call(payload)
        self.assertFalse(self.service._pc_preview)

    def test_native_approval_denial_never_reaches_original(self):
        self.host.native_approve = lambda *args: False
        with self.assertRaises(HostDenied):
            self.call({'op':'preview','action':'read-system-summary'})
        self.assertFalse(self.service._pc_preview)

    def test_copied_or_other_session_cannot_borrow_binding(self):
        copied = NativeSession('tenant','owner','chat',frozenset({ROUTE}),frozenset({ROUTE}))
        with self.assertRaises(HostHold):
            self.call({'op':'preview','action':'read-system-summary'}, copied)
        self.binding = lambda s: None
        with self.assertRaises(HostHold):
            self.call({'op':'stop'})

    def test_callback_scope_mutation_denied_and_no_competing_handler(self):
        def mutate(session):
            object.__setattr__(session, 'principal', 'different')
            return NativePcBinding(session,self.service,'project_one')
        self.binding = mutate
        with self.assertRaises(HostDenied):
            self.call({'op':'preview','action':'read-system-summary'})
        self.assertFalse(self.service._pc_preview)
        with self.assertRaises(HostDenied):
            self.port.register(self.host, receipt='duplicate')

    def test_missing_owner_probe_holds_original_unchanged(self):
        host = NoxPackHost(json.loads((pack/'catalog.json').read_text()), native_approve=lambda *a:True)
        port = ExistingPcControlPort(native_binding_from_session=self.binding, owner_ready=lambda:False)
        port.register(host, receipt='unavailable')
        with self.assertRaises(HostHold):
            host.execute(ROUTE, {'op':'stop'}, self.session)
        self.assertEqual(self.service._pc_epoch,0)

if __name__ == '__main__': unittest.main()
