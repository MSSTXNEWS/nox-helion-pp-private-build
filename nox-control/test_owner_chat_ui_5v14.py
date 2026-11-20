"""Source-only regression for active owner WEB archive assets (TaskID 5V14-01).

Do not import the FastAPI runtime, access the owner host or alter production files.
"""
import ast
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

    def test_noscript_and_nonexecuting_script_cannot_satisfy_live_asset(self):
        content=('<noscript><script src="/nox-web-v29/owner-presence.js"></script></noscript>'
                 '<script type="application/json" src="/nox-web-v29/owner-chat-ui.js"></script>')
        result=self.rendered(content)
        self.assertEqual(result.count('src="/nox-web-v29/owner-presence.js"'),2)
        self.assertEqual(result.count('src="/nox-web-v29/owner-chat-ui.js"'),2)

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

    def test_legacy_pc_assets_remain_nested_mount(self):
        result=self.rendered('<link rel="stylesheet" href="/pc/v25/nox-shell-v25.css">')
        self.assertIn('href="/nox-web-v29/pc/v25/nox-shell-v25.css"',result)
        self.assertIn('data-n25-css="1"',result)


if __name__ == '__main__':
    unittest.main()
