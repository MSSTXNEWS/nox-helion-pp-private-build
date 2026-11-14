"""E06 source-only native picker boundary: no Windows picker or file I/O executed."""
from dataclasses import replace
import unittest
from admission import Denied, NativeFileSelection
import test_admission

class NativePickerWireTests(unittest.TestCase):
    def setUp(self):
        # Reuse the exact 50-action, real admission fixture; no parallel host.
        test_admission.HostScopeAndReceiptTests.setUp(self)
        self.request = self.req('chat.attach', 'NIP01-06')
        self.good = NativeFileSelection(
            ticket='opaque-native-ticket-777', sha256='c' * 64,
            size_bytes=42, tenant='tenant', principal='person', chat='chat1')

    req = test_admission.HostScopeAndReceiptTests.req

    def admit_picker(self, item):
        return self.host.admit(session=self.s, actual_origin=self.s.origin,
                               request=self.request, native_file_picker=lambda *_: item)

    def test_native_picker_malformed_sha_types_fail_closed(self):
        for payload in ([1, 2], {'hash':'c'*64}, 1, True, None, b'c'*64):
            with self.subTest(kind=type(payload).__name__), self.assertRaises(Denied):
                self.admit_picker(replace(self.good, sha256=payload))
        self.assertEqual(self.host.pending, {})

    def test_native_picker_unicode_surrogate_ticket_fail_closed(self):
        with self.assertRaises(Denied):
            self.admit_picker(replace(self.good, ticket='native-ticket-verified-\ud800'))
        self.assertEqual(self.host.pending, {})

    def test_native_picker_bad_size_type_fail_closed(self):
        for size in (True, '42', 0, -2, 20_000_000_001):
            with self.subTest(size=repr(size)), self.assertRaises(Denied):
                self.admit_picker(replace(self.good, size_bytes=size))
        self.assertEqual(self.host.pending, {})

    def test_valid_native_ticket_keeps_sha_proof_but_hides_ticket(self):
        admitted = self.admit_picker(self.good)
        self.assertEqual(admitted['fileSha256'], 'c'*64)
        self.assertEqual(len(admitted['fileTicketSha256']), 64)
        self.assertNotIn(self.good.ticket, str(admitted))
        self.assertEqual(admitted['state'], 'ADMITTED_NOT_EXECUTED')
        self.assertEqual(admitted['nativeAck'], 'PENDING')

if __name__ == '__main__':
    unittest.main()
