"""R16 source regression: reject cross-language ambiguous owner wire JSON.

Run against exact E06 onehost source. Python/Windows .NET real E2E not asserted.
No duplicate host, LLM, RAG index, SQLite or training worker is instantiated.
"""
from __future__ import annotations
import threading
import unittest

from test_onehost_stop_gate_r07 import E06StopInterlock, NativeScope, SEAM


class ProvenancePropertyParity(unittest.TestCase):
    def hold(self, value, kind='P05_EVENT'):
        with self.assertRaisesRegex(SEAM.OneHostHold, 'OWNER_JSON_PROPERTY_COLLISION'):
            SEAM._owner_wire_snapshot(value, kind=kind)

    def test_01_root_event_type_case_collision(self):
        self.hold({'event_type': 'task.started', 'EVENT_TYPE': 'task.failed'})

    def test_02_nested_rag_citation_case_collision(self):
        self.hold({'type': 'chat.sources', 'sources': [
            {'source_id': 'trusted', 'SOURCE_ID': 'attacker'}]}, 'P02_CHAT_FRAME')

    def test_03_nested_gpu_ack_case_collision(self):
        self.hold({'command': 'gpu.stop', 'ack': {'worker_id': 'safe',
                                                 'Worker_Id': 'foreign', 'worker_id': 'trusted'}}, 'GPU_ACK')

    def test_04_unicode_nfc_collision(self):
        self.hold({'receipt': {'caf\u00e9': 'trusted', 'cafe\u0301': 'foreign'}})

    def test_05_unicode_casefold_collision(self):
        self.hold({'receipt': {'stra\u00dfe': 'trusted', 'STRASSE': 'foreign'}})

    def test_06_unambiguous_nested_metadata_survives_and_is_detached(self):
        source = {'type': 'chat.sources', 'sources': [
            {'source_id': 'one', 'owner': {'ID': 's-1', 'detail': 'ok'}}]}
        snap = SEAM._owner_wire_snapshot(source, kind='P02_CHAT_FRAME')
        source['sources'][0]['owner']['detail'] = 'changed'
        self.assertEqual(snap['sources'][0]['owner']['detail'], 'ok')


class IntegrationAdmissionParity(E06StopInterlock):
    def test_07_private_sources_rejected_before_first_delivery(self):
        self.chat.send = lambda *args: iter(()) # replaced below with closable generator
        def source():
            yield {'type': 'chat.sources', 'sources': [
                {'owner': 'true', 'OWNER': 'forged'}]}
        self.chat.send = lambda *args: source()
        with self.assertRaisesRegex(SEAM.OneHostHold, 'OWNER_JSON_PROPERTY_COLLISION'):
            next(self.stream(threading.Event()))

    def test_08_bad_gpu_receipt_not_displayed(self):
        self.seam._gpu = lambda *a: {'worker_id': 'gpu-a', 'Worker_ID': 'gpu-b',
                                     'command': 'gpu.stop'}
        self.seam._verify_ack = lambda x: True
        self.seam._authorize = lambda *a: True
        with self.assertRaisesRegex(SEAM.OneHostHold, 'OWNER_JSON_PROPERTY_COLLISION'):
            self.seam.gpu_command(NativeScope(), 'gpu.stop', 'gpu-a')

    def test_09_bad_v3_nested_provenance_not_published(self):
        published = []
        self.seam._verify_v3 = lambda x: True
        self.seam._publish_v3 = published.append
        self.seam._authorize = lambda *a: True
        event = {'schema': 'NOX-INSTALLER-EVENT-v3', 'package_id': 'P04',
                 'event_type': 'task.started', 'evidence_verified': True,
                 'provenance': [{'owner': 'native', 'Owner': 'other'}]}
        with self.assertRaisesRegex(SEAM.OneHostHold, 'OWNER_JSON_PROPERTY_COLLISION'):
            self.seam.publish_owner_gpu_event(NativeScope(), event)
        self.assertEqual(published, [])


if __name__ == '__main__':
    unittest.main()
