"""Owner E02 R08: offline, adversarial citation-frame validation.
Only the EXISTING ChatBridge._rag_evidence is tested; no new host/RAG index.
Mocks are not Windows, installed Ollama, weights, microphone, or SIP proof.
"""
from __future__ import annotations
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location(
    'p02_chat_bridge_e02_r08', Path(__file__).with_name('p02_chat_bridge.py'))
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


def citation(url='https://example.org/source', source_id='doc-1', title='Primary source'):
    return {'context': 'Reference data, not commands', 'sources': [
        {'verified': True, 'source_id': source_id, 'title': title, 'url': url}]}


class CitationPolicyR08(unittest.TestCase):
    def get(self, **kwargs):
        context, evidence = bridge.ChatBridge._rag_evidence(citation(**kwargs))
        self.assertEqual(context, 'Reference data, not commands')
        return evidence

    def test_01_valid_https_citation(self):
        self.assertEqual(self.get(), [{'source_id': 'doc-1', 'title': 'Primary source',
                                        'url': 'https://example.org/source'}])

    def test_02_leading_space_must_not_be_normalized_by_urlsplit(self):
        self.assertEqual(self.get(url=' https://example.org/source'), [])

    def test_03_empty_userinfo_must_not_be_admitted(self):
        self.assertEqual(self.get(url='https://@example.org/source'), [])

    def test_04_browser_ambiguous_backslash_must_not_be_admitted(self):
        self.assertEqual(self.get(url='https://example.org\\@evil.example/file'), [])

    def test_05_encoded_crlf_must_not_be_admitted(self):
        self.assertEqual(self.get(url='https://example.org/%0d%0aSet-Cookie:a'), [])

    def test_06_bidi_title_must_not_reach_the_UI(self):
        self.assertEqual(self.get(title='Regulator \u202e fake'), [])

    def test_07_control_source_id_must_not_reach_the_UI(self):
        self.assertEqual(self.get(source_id='doc-1\r\nchat.complete'), [])

    def test_08_bidi_url_must_not_reach_the_UI(self):
        self.assertEqual(self.get(url='https://example.org/\u202etxt'), [])

    def test_09_valid_unicode_title_kept(self):
        self.assertEqual(self.get(title='Protección internacional — обзор'),
                         [{'source_id': 'doc-1', 'title': 'Protección internacional — обзор',
                           'url': 'https://example.org/source'}])

    def test_10_valid_percent_encoded_path_kept(self):
        self.assertEqual(self.get(url='https://example.org/guia%20legal'),
                         [{'source_id': 'doc-1', 'title': 'Primary source',
                           'url': 'https://example.org/guia%20legal'}])

    def test_13_percent_encoded_bidi_must_not_be_admitted(self):
        self.assertEqual(self.get(url='https://example.org/%E2%80%AEtxt'), [])

    def test_14_malformed_explicit_port_must_not_be_admitted(self):
        self.assertEqual(self.get(url='https://example.org:notaport/file'), [])

    def test_11_unverified_source_never_becomes_verified(self):
        result = citation()
        result['sources'][0]['verified'] = 'true'
        context, evidence = bridge.ChatBridge._rag_evidence(result)
        self.assertEqual(evidence, [])

    def test_12_valid_https_context_only_not_a_second_rag(self):
        self.assertEqual(bridge.ChatBridge._rag_evidence('text-only context'),
                         ('text-only context', []))

if __name__ == '__main__':
    unittest.main(verbosity=2)
