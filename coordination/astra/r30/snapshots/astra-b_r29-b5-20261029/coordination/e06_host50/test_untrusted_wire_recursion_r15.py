"""E06 R15: offline-only regression for deeply nested untrusted frames."""
import tempfile
import unittest
from pathlib import Path
from admission import Denied, Hold, NativeFileSelection, run_read_only_audit
import test_native_callback_failclosed_r14 as fixture


def deep():
    item = {}
    for _ in range(20000):
        item = {'child': item}
    return item


class MalformedWire(unittest.TestCase):
    def setUp(self):
        fixture.NativeCallbackErrors.setUp(self)

    def request(self, route):
        return fixture.NativeCallbackErrors.request(self, route)

    def test_page_frame_depth_denied(self):
        req = self.request('chat.attach')
        req['settings'] = deep()
        with self.assertRaisesRegex(Denied, 'INVALID_JSON'):
            self.host.admit(session=self.session, actual_origin=self.session.origin,
                            request=req, native_file_picker=lambda *_: None)
        self.assertFalse(self.host.pending)

    def test_mutation_during_native_picker_denied(self):
        req = self.request('chat.attach')
        def picker(*_):
            req['settings'] = deep()
            return NativeFileSelection('native-opaque-ticket-r15', 'f'*64, 12, 't', 'p', 'c')
        with self.assertRaisesRegex(Denied, 'REQUEST_MUTATED_DURING_NATIVE_CHECKS'):
            self.host.admit(session=self.session, actual_origin=self.session.origin,
                            request=req, native_file_picker=picker)
        self.assertFalse(self.host.pending)

    def test_deep_signed_ack_denied_without_consumption(self):
        ticket = self.host.admit(session=self.session, actual_origin=self.session.origin,
            request=self.request('chat.attach'), native_file_picker=lambda *_:
            NativeFileSelection('native-opaque-ticket-r15', 'f'*64, 12, 't', 'p', 'c'))
        fields = ('runId','taskId','routeId','owner','ownerReceiptSha256',
            'payloadSha256','sourceLockTree','sessionScopeSha256',
            'targetRunId','fileSha256','fileTicketSha256')
        ack = {key: ticket[key] for key in fields}
        ack.update(event='DONE', proofSha256=deep(), seal='0'*64)
        with self.assertRaisesRegex(Denied, 'NATIVE_ACK_INVALID'):
            self.host.finish(ticket['runId'], ack)
        self.assertIn(ticket['runId'], self.host.pending)

    def test_source_catalog_depth_hold(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp)/'catalog.json', Path(tmp)/'binding.json'
            a.write_text('{"nested":'*18000+'null'+'}'*18000, encoding='utf-8')
            b.write_text('{}', encoding='utf-8')
            with self.assertRaisesRegex(Hold, 'AUDIT_INVALID_UTF8_JSON'):
                run_read_only_audit(str(a), str(b))

if __name__ == '__main__':
    unittest.main()
