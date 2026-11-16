"""Exact static transition and rollback tests; no native actions."""
import base64
from contextlib import redirect_stdout
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

HERE=Path(__file__).parent
def load(name):
    spec=importlib.util.spec_from_file_location(name,HERE/(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
entry=load('owner_chat_reports_state_entry');deploy_primitives=load('owner_download_status_entry')


class ReportsInstall(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        root=Path(self.temp.name);site=root/'site';site.mkdir();state=root/'state';state.mkdir();(state/'media').mkdir()
        self.deploy=types.SimpleNamespace(ROOT=root,SITE=site,STATE=state,plain=deploy_primitives.plain,
            read=deploy_primitives.read,lock=deploy_primitives.lock,model_identity=lambda _:{'pid':7,'starttime':8},
            proxy_identity=lambda _:{'pid':9,'starttime':10},stopped_by_owner=lambda:False)
        self.evidence=types.SimpleNamespace(training_observation=lambda _:{'state':'RUNNING','control_action_performed':False})
        self.helper=types.SimpleNamespace(atomic=self.atomic);self.old=b'old reviewed js';self.new=b'new reviewed js'
        self.path=site/'owner-chat-ui.js';self.atomic(self.path,self.old)
        patches=[patch.object(entry,'OLD_JS',entry.digest(self.old)),patch.object(entry,'NEW_JS',entry.digest(self.new)),
            patch.object(entry,'BUNDLE',{'owner_chat_composer_entry.py':base64.b64encode((HERE/'owner_chat_composer_entry.py').read_bytes()).decode(),
                'owner-chat-ui.js':base64.b64encode(self.new).decode()})]
        for item in patches:item.start();self.addCleanup(item.stop)
        self.core=entry.primitives()
        prior={'schema':'NOX_OWNER_CHAT_COMPOSER_DEPLOY_V1','request':entry.PREVIOUS_REQUEST,
            'source_sha':entry.PREVIOUS_SOURCE,'state':'BOUNDED_REPORTS_SOURCE_AND_HTTP_VERIFIED_BROWSER_PENDING',
            'installed_js_sha256':entry.OLD_JS,'preservation_verified':True,'rollback':False}
        self.atomic(state/('owner_chat_composer_'+entry.PREVIOUS_REQUEST+'.json'),json.dumps(prior).encode())
    def atomic(self,path,raw):path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw);path.chmod(0o600)
    def run_entry(self,probe):
        with patch.dict(os.environ,{'NOX_OWNER_REQUEST_ID':'123','NOX_OWNER_SOURCE_SHA':'a'*40}), \
             patch.object(entry,'primitives',return_value=self.core), \
             patch.object(self.core,'dependencies',return_value=(self.deploy,self.evidence,self.helper)), \
             patch.object(self.core,'guards',return_value={'trainer.py':'b'*64}), \
             patch.object(self.core,'live_probe',side_effect=probe),redirect_stdout(io.StringIO()):
            code=entry.main()
        return code,json.loads((self.deploy.STATE/'owner_chat_reports_state_123.json').read_text())
    def test_static_delivery_never_restarts_or_claims_browser_acceptance(self):
        code,record=self.run_entry(lambda *_:{'owner_script_http':200})
        self.assertEqual(code,0);self.assertEqual(self.path.read_bytes(),self.new)
        for key in ('proxy_restarted','model_restarted','training_control_performed','actual_browser_acceptance'):
            self.assertFalse(record[key])
    def test_delivery_failure_restores_only_owned_postimage(self):
        def failed(*_):raise RuntimeError('HOLD_HTTP_TEST')
        code,record=self.run_entry(failed)
        self.assertEqual(code,2);self.assertTrue(record['rollback_verified']);self.assertEqual(self.path.read_bytes(),self.old)
    def test_foreign_change_is_not_overwritten(self):
        def changed(*_):self.atomic(self.path,b'foreign');raise RuntimeError('HOLD_HTTP_TEST')
        code,record=self.run_entry(changed)
        self.assertEqual(code,2);self.assertFalse(record['rollback_verified']);self.assertEqual(self.path.read_bytes(),b'foreign')
    def test_pinned_frozen_primitives_remain_exact(self):
        self.assertEqual(hashlib.sha256((HERE/'owner_chat_composer_entry.py').read_bytes()).hexdigest(),entry.COMPOSER_SHA)


if __name__=='__main__':unittest.main()
