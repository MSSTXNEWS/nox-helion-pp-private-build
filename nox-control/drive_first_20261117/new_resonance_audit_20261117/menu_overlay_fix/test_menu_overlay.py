"""Offline regression for the existing pinned serving overlay; no native import."""
import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess
import unittest

HERE = Path(__file__).resolve().parent
REFRESH = HERE.parents[1]
BASE = Path(os.environ.get('NOX_MENU_BASE_SOURCE',
            str(REFRESH / 'history_contract_reuse/candidates/native_v29_bridge_432b6195.py')))
RAW_JS = Path(os.environ.get('NOX_MENU_RAW_UI',
              str(REFRESH / 'web29_original_chat_audit_20261117/source_v13/site/nox-ui.js')))
CANDIDATE = Path(os.environ.get('NOX_MENU_CANDIDATE_SOURCE',
                 str(HERE / 'historical_native_v29_bridge.candidate.py')))
RECIPE = json.loads((HERE / 'PATCH_RECIPE.json').read_text())


def overlay_from_source(path, expected_sha):
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha:
        raise ValueError('HOLD_MENU_SOURCE_SHA')
    nodes = []
    for node in ast.parse(raw).body:
        if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id in
                {'_V122_FROZEN_NOX_UI_SHA', '_V122_OWNER_UI_PATCHES'}
                for target in node.targets):
            nodes.append(node)
        if isinstance(node, ast.FunctionDef) and node.name == '_overlay_v122_owner_ui':
            nodes.append(node)
    namespace = {'hashlib': hashlib}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), '<pure pinned overlay>', 'exec'), namespace)
    return namespace['_overlay_v122_owner_ui']


def route_function(raw):
    source = raw.decode()
    start = source.index('  function routeLinks(root){')
    end = source.index('\n  if(nativeOwner){', start)
    return source[start:end]


class MenuOverlayRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = RAW_JS.read_bytes()
        if hashlib.sha256(cls.raw).hexdigest() != RECIPE['frozen_js_input_sha256']:
            raise ValueError('HOLD_MENU_FROZEN_UI_SHA')
        cls.before = overlay_from_source(BASE, RECIPE['historical_context_sha256'])(cls.raw)
        cls.after = overlay_from_source(CANDIDATE, RECIPE['candidate_sha256'])(cls.raw)

    def test_exact_served_baseline_and_one_added_rewrite(self):
        self.assertEqual(hashlib.sha256(self.raw).hexdigest(), RECIPE['frozen_js_input_sha256'])
        self.assertEqual(hashlib.sha256(self.before).hexdigest(),
                         '18d8c8d6009323188b9f903920308b3b871a6123f7b425a77184a6b2c147640e')
        old, new = (RECIPE[key].encode() for key in ('old_js_anchor', 'new_js_anchor'))
        self.assertEqual(self.before.count(old), 1)
        self.assertEqual(self.after.count(new), 1)
        self.assertEqual(self.after.replace(new, old, 1), self.before)
        self.assertEqual(RAW_JS.read_bytes(), self.raw)

    def test_only_staged_native_chat_links_change(self):
        cases = [
            {'owner': True, 'path': '/nox-web-v29/chat.html', 'href': 'chat.html',
             'before': '/nox/chat', 'after': '/nox-web-v29/chat.html'},
            {'owner': True, 'path': '/nox-web-v29/home.html', 'href': './chat.html?view=full#messages',
             'before': '/nox/chat?view=full#messages', 'after': '/nox-web-v29/chat.html?view=full#messages'},
            {'owner': True, 'path': '/nox-web-v29/chat.html', 'href': 'memory.html#latest',
             'before': '/nox/memory#latest', 'after': '/nox/memory#latest'},
            {'owner': True, 'path': '/nox/home', 'href': 'chat.html',
             'before': '/nox/chat', 'after': '/nox/chat'},
            {'owner': True, 'path': '/nox-web-v290/chat.html', 'href': 'chat.html',
             'before': '/nox/chat', 'after': '/nox/chat'},
            {'owner': False, 'path': '/nox-web-v29/chat.html', 'href': './chat.html#messages',
             'before': './chat.html#messages', 'after': './chat.html#messages'},
            {'owner': True, 'path': '/nox-web-v29/chat.html', 'href': 'https://example.invalid/chat.html',
             'before': 'https://example.invalid/chat.html', 'after': 'https://example.invalid/chat.html'},
            {'owner': True, 'path': '/nox-web-v29/chat.html', 'href': '/nox-web-v29/chat.html#messages',
             'before': '/nox-web-v29/chat.html#messages', 'after': '/nox-web-v29/chat.html#messages'},
            {'owner': True, 'path': '/nox-web-v29/chat.html', 'href': '#messages',
             'before': '/nox-web-v29/chat.html#messages', 'after': '/nox-web-v29/chat.html#messages'},
        ]
        program = r"""
const fs=require('fs'),vm=require('vm');
const input=JSON.parse(fs.readFileSync(0,'utf8'));
const result=[];
for(const row of input.cases){
  const values={};
  for(const key of ['before','after']){
    let href=row.href;
    const link={getAttribute:()=>href,setAttribute:(_,value)=>{href=value;}};
    const context={nativeOwner:row.owner,location:{pathname:row.path},
      nativePages:new Set(['home','chat','training','models','memory','system','dashboard','projects','install','cinema','settings']),
      root:{matches:()=>false,querySelectorAll:()=>[link]}};
    vm.runInNewContext(input[key]+';routeLinks(root);',context,{timeout:100});
    values[key]=href;
  }
  result.push(values);
}
process.stdout.write(JSON.stringify(result));
"""
        result = subprocess.run(['node', '-e', program], input=json.dumps({
            'before': route_function(self.before), 'after': route_function(self.after),
            'cases': cases}), text=True, capture_output=True, check=True, timeout=10)
        observed = json.loads(result.stdout)
        self.assertEqual(len(observed), len(cases))
        for case, actual in zip(cases, observed):
            with self.subTest(case=case):
                self.assertEqual(actual, {key: case[key] for key in ('before', 'after')})


if __name__ == '__main__':
    unittest.main()
