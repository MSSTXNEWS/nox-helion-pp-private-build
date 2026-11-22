"""Source-only regression for active owner WEB archive assets (TaskID 5V14-01).

Do not import the FastAPI runtime, access the owner host or alter production files.
"""
import ast
import json
import os
import tempfile
import time
from unittest.mock import patch
from html.parser import HTMLParser
from pathlib import Path
import re
import unittest


def load_decorator():
    source=Path(__file__).with_name('owner_chat_ui.py').read_text(encoding='utf-8')
    tree=ast.parse(source, filename='owner_chat_ui.py')
    parts=[node for node in tree.body if
           isinstance(node, ast.ClassDef) and node.name=='_LiveOwnerAssetScanner'
           or isinstance(node, ast.FunctionDef) and node.name=='decorate_html']
    if len(parts)!=2:
        raise AssertionError('HOLD_WEB_OWNER_SOURCE_ANCHOR')
    namespace={'HTMLParser':HTMLParser, 're':re, 'PAGES':{
        'pc/resonance.html', 'pc/v22/resonance.template.html'
    }, 'BUILD':'NOX_OWNER_LIVE_RESONANCE_20261116'}
    exec(compile(ast.Module(body=parts, type_ignores=[]), 'owner_chat_ui.py','exec'),namespace)
    return namespace['decorate_html']


class OwnerLiveAssetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.decorate=staticmethod(load_decorator())

    def rendered(self,head=''):
        return self.decorate('<html><head>'+head+'</head><body></body></html>',
                             'pc/resonance.html')

    def test_inert_template_does_not_hide_live_bridge(self):
        content='<template><script src="/nox-web-v29/owner-chat-ui.js"></script></template>'
        result=self.rendered(content)
        self.assertEqual(result.count('src="/nox-web-v29/owner-chat-ui.js"'),2)
        self.assertEqual(result.count('data-nox-live-owner="1"'),4)

    def test_nested_inert_elements_never_suppress_real_bridge(self):
        # The inner close does NOT make the outer template executable.
        for inert in ('template', 'noscript'):
            with self.subTest(inert=inert):
                content=('<template><'+inert+'>nested</'+inert+'>'
                         '<script src="/nox-web-v29/owner-chat-ui.js"></script>'
                         '<meta name="nox-live-build" content="fake"></template>')
                result=self.rendered(content)
                self.assertEqual(result.count('src="/nox-web-v29/owner-chat-ui.js"'),2)
                self.assertEqual(result.count('data-nox-live-owner="1"'),4)
                self.assertIn('content="NOX_OWNER_LIVE_RESONANCE_20261116"',result)

    def test_stray_inert_closer_never_exposes_fake_owner_assets(self):
        # HTMLParser emits unmatched closing tags that the browser ignores.
        # A depth counter would expose assets still inside the outer inert tag.
        for outer, stray in (('template', 'noscript'), ('noscript', 'template')):
            with self.subTest(outer=outer, stray=stray):
                content=(f'<{outer}></{stray}>'
                         '<script src="/nox-web-v29/owner-chat-ui.js"></script>'
                         '<meta name="nox-live-build" content="inert-fake">'
                         f'</{outer}>')
                result=self.rendered(content)
                self.assertEqual(result.count('src="/nox-web-v29/owner-chat-ui.js"'),2)
                self.assertEqual(result.count('data-nox-live-owner="1"'),4)
                self.assertIn('content="NOX_OWNER_LIVE_RESONANCE_20261116"',result)
                self.assertEqual(self.decorate(result,'pc/resonance.html'),result)

    def test_noscript_and_nonexecuting_script_cannot_satisfy_live_asset(self):
        content=('<noscript><script src="/nox-web-v29/owner-presence.js"></script></noscript>'
                 '<script type="application/json" src="/nox-web-v29/owner-chat-ui.js"></script>')
        result=self.rendered(content)
        self.assertEqual(result.count('src="/nox-web-v29/owner-presence.js"'),2)
        self.assertEqual(result.count('src="/nox-web-v29/owner-chat-ui.js"'),2)

    def test_raw_text_elements_do_not_fake_executable_owner_scripts(self):
        # HTMLParser reports a script tag inside textarea/title/iframe, while
        # the actual HTML browser treats each nested tag as inert text.
        raw=('<html><head><title><script src="/nox-web-v29/owner-chat-ui.js"></script></title>'
             '</head><body><textarea><script src="/nox-web-v29/owner-presence.js"></script>'
             '<meta name="nox-live-build"></textarea>'
             '<iframe><script src="/nox-web-v29/nox-v137-owner-self-status.js"></script>'
             '</iframe></body></html>')
        result=self.decorate(raw,'pc/resonance.html')
        for asset in ('owner-chat-ui.js','owner-presence.js',
                      'nox-v137-owner-self-status.js'):
            self.assertEqual(result.count('src="/nox-web-v29/'+asset+'"'),2)
        self.assertEqual(result.count('data-nox-live-owner="1"'),4)
        self.assertIn('<meta name="nox-live-build" content="',result)

    def test_comments_do_not_count_and_content_is_preserved(self):
        content='<!--<meta name="nox-live-build"><script src="/nox-web-v29/owner-presence.js"></script>-->'
        result=self.rendered(content)
        self.assertIn(content,result)
        self.assertIn('<meta name="nox-live-build" content="',result)
        self.assertEqual(result.count('src="/nox-web-v29/owner-presence.js"'),2)

    def test_existing_executable_and_query_assets_not_duplicated(self):
        content=('<meta name="nox-live-build" content="v1">'
                 '<script type="module" src="/nox-web-v29/owner-chat-ui.js?v=2"></script>'
                 '<script src="/nox-web-v29/owner-presence.js"></script>')
        result=self.rendered(content)
        self.assertEqual(result.count('nox-live-build'),1)
        self.assertNotIn('src="/nox-web-v29/owner-chat-ui.js" data-nox-live-owner=',result)
        self.assertEqual(result.count('src="/nox-web-v29/owner-presence.js"'),1)

    def test_decorator_is_idempotent_and_preserves_unrelated_page(self):
        start='<html><head></head><body></body></html>'
        first=self.decorate(start,'pc/resonance.html')
        self.assertEqual(self.decorate(first,'pc/resonance.html'),first)
        self.assertEqual(self.decorate(start,'pc/unrelated.html'),start)

    def test_mixed_case_head_end_tag_preserved_and_idempotent(self):
        # HTML5 closing tags are case-insensitive. Archived WEB skins may use
        # uppercase or whitespace while remaining valid in a browser.
        for closing in ('</HEAD>', '</HeAd >', '</head >'):
            with self.subTest(closing=closing):
                raw='<html><HEAD><title>NOX</title>'+closing+'<body></body></html>'
                result=self.decorate(raw,'pc/resonance.html')
                self.assertIn('<meta name="nox-live-build" content="',result)
                self.assertIn('data-nox-live-owner="1"',result)
                self.assertIn(closing,result)
                self.assertIn('data-nox-live-owner="1"></script>\n'+closing,result)
                self.assertEqual(self.decorate(result,'pc/resonance.html'),result)

    def test_legacy_pc_assets_remain_nested_mount(self):
        result=self.rendered('<link rel="stylesheet" href="/pc/v25/nox-shell-v25.css">')
        self.assertIn('href="/nox-web-v29/pc/v25/nox-shell-v25.css"',result)
        self.assertIn('data-n25-css="1"',result)


def load_worker_reader():
    source=Path(__file__).with_name('owner_chat_ui.py').read_text(encoding='utf-8')
    tree=ast.parse(source, filename='owner_chat_ui.py')
    names={'_owner_status_pairs_unique','_owner_status_no_nonfinite','workers'}
    parts=[node for node in tree.body if isinstance(node,ast.FunctionDef)
           and node.name in names]
    if {node.name for node in parts} != names:
        raise AssertionError('HOLD_OWNER_WORKER_SOURCE_ANCHOR')
    import stat
    namespace={'os':os,'stat':stat,'json':json,'time':time,'re':re,
               'Path':Path}
    exec(compile(ast.Module(body=parts,type_ignores=[]),
                 'owner_chat_ui.py','exec'),namespace)
    return namespace['workers']


class OwnerWorkerSnapshotTrustTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reader=staticmethod(load_worker_reader())

    def read_snapshot(self,raw,mode=0o600):
        with tempfile.TemporaryDirectory() as base:
            root=Path(base)
            (root/'status').mkdir()
            status=root/'status'/'agents_t856u.json'
            status.write_bytes(raw.encode('utf-8'))
            status.chmod(mode)
            with patch.dict(self.reader.__globals__,
                            {'ROOT':root,'owner_maintenance_gate':lambda:'ABSENT'}):
                return self.reader()

    def test_valid_owner_readonly_snapshot_is_observed(self):
        raw='{"n":1,"workers":[{"id":"nox-agent-01","status":"idle","current_task":null}]}'
        snap=self.read_snapshot(raw)
        self.assertEqual(snap['state'],'OBSERVED')
        self.assertEqual(snap['configured'],1)

    def test_group_or_world_writable_status_never_certifies_work(self):
        raw='{"n":1,"workers":[{"id":"nox-agent-01","status":"idle","current_task":null}]}'
        self.assertEqual(self.read_snapshot(raw,0o666)['state'],'UNAVAILABLE')

    def test_duplicate_json_keys_cannot_override_status(self):
        raw='{"n":1,"workers":[{"id":"nox-agent-01","status":"idle","current_task":null}],"n":1}'
        self.assertEqual(self.read_snapshot(raw)['state'],'UNAVAILABLE')

    def test_nonfinite_json_cannot_be_certified(self):
        raw='{"n":1,"workers":[{"id":"nox-agent-01","status":"idle","current_task":null}],"extra":NaN}'
        self.assertEqual(self.read_snapshot(raw)['state'],'UNAVAILABLE')

    def test_status_path_swap_during_read_never_certifies_stale_worker(self):
        # The file descriptor stays readable after os.replace(); validating
        # just before/after fstat would incorrectly advertise its old content.
        with tempfile.TemporaryDirectory() as base:
            root=Path(base)
            (root/'status').mkdir()
            status=root/'status'/'agents_t856u.json'
            original={'n':1,'workers':[{'id':'nox-agent-01',
                        'status':'idle','current_task':None}]}
            status.write_text(json.dumps(original),encoding='utf-8')
            status.chmod(0o600)
            real_read=os.read
            reads=[]
            def replace_after_read(fd, limit):
                data=real_read(fd,limit)
                reads.append(True)
                replacement=status.with_suffix('.replacement')
                replacement.write_bytes(data)
                replacement.chmod(0o600)
                os.replace(replacement,status)
                return data
            with patch.object(os,'read',side_effect=replace_after_read):
                with patch.dict(self.reader.__globals__,
                                {'ROOT':root,'owner_maintenance_gate':lambda:'ABSENT'}):
                    observed=self.reader()
            self.assertEqual(reads,[True])
            self.assertEqual(observed['state'],'UNAVAILABLE')

    def test_busy_claim_id_must_be_printable_canonical_text(self):
        def snapshot(claim):
            return json.dumps({'n':1,'workers':[{'id':'nox-agent-01',
                'status':'busy','current_task':{'id':claim}}]})
        self.assertEqual(self.read_snapshot(snapshot('6V14-04'))['state'],'OBSERVED')
        for invalid in (' 6V14-04','6V14-04 ','bad\nid','', 'x'*101):
            with self.subTest(invalid=repr(invalid)):
                self.assertEqual(self.read_snapshot(snapshot(invalid))['state'],
                                 'UNAVAILABLE')


if __name__ == '__main__':
    unittest.main()
