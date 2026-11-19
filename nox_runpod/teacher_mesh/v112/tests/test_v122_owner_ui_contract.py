"""V122: exact WEB V29.3 owner telemetry overlay, isolated source regression.

No user password, live SSH, S03 database, checkpoint, API or GPU touched.
The full source SHA is checked separately against original Drive ZIP.
"""
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from nox_runpod.teacher_mesh.v112 import native_v29_full_bridge as module


class OwnerUiV122Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture=('(()=>{\n'+'\n'.join(old for old,_ in module._V122_OWNER_UI_PATCHES)+'\n})();\n').encode()
        cls.sha=hashlib.sha256(cls.fixture).hexdigest()

    def test_real_contract_paths_use_truthful_s03_and_model_checks(self):
        text=module._overlay_v122_owner_ui(self.fixture,expected_sha=self.sha).decode()
        for old,new in module._V122_OWNER_UI_PATCHES:
            self.assertNotIn(old,text)
            self.assertIn(new,text)
        for needed in ("health.chat_http===200","health.model_http===200",
                       "core.native_s03_recall_bound===true",
                       "core.native_dialogs_ready===true",
                       "observedActivity?.source==='ACTUAL_NOX_MODEL_SLOTS'",
                       "age>=-5&&age<=30"):
            self.assertIn(needed,text)
        self.assertNotIn('Math.random',text)
        self.assertNotIn('ready=true',text)

    def test_fails_closed_on_sha_drift(self):
        with self.assertRaisesRegex(ValueError,'SHA'):
            module._overlay_v122_owner_ui(self.fixture+b' ',expected_sha=self.sha)

    def test_fails_closed_on_missing_and_duplicate_anchors(self):
        text=self.fixture.decode()
        for changed in (text.replace(module._V122_OWNER_UI_PATCHES[0][0],''),
                        text+module._V122_OWNER_UI_PATCHES[0][0]):
            raw=changed.encode()
            with self.assertRaisesRegex(ValueError,'ANCHOR'):
                module._overlay_v122_owner_ui(raw,expected_sha=hashlib.sha256(raw).hexdigest())

    def test_reapplication_rejected(self):
        patched=module._overlay_v122_owner_ui(self.fixture,expected_sha=self.sha)
        with self.assertRaisesRegex(ValueError,'ANCHOR'):
            module._overlay_v122_owner_ui(patched,expected_sha=hashlib.sha256(patched).hexdigest())

    def test_genuine_native_contract_fields_are_supported_by_existing_sources(self):
        read=Path('nox_runpod/teacher_mesh/v118/real_read_surfaces.py').read_text(encoding='utf8')
        bridge=Path('nox_runpod/teacher_mesh/v112/native_v29_full_bridge.py').read_text(encoding='utf8')
        for field in ("'source':'ACTUAL_NOX_MODEL_SLOTS'","'timestamp':time.time()",
                      "'chat_http':200","'model_http':200"):
            self.assertIn(field,read)
        for field in ("'backend':'EXISTING_NATIVE_ONEHOST'",
                      "'native_s03_store_present':s03_store_present",
                      "'native_s03_recall_bound':False",
                      "'native_cognitive_memory_bound':False",
                      "'v38_integration_state':'UNBOUND'",
                      "'v38_missing_required_host_bindings':list(v38_required)",
                      "'native_dialogs_ready':_schema_ready()"):
            self.assertIn(field,bridge)

    def test_protected_static_mount_overlays_only_authenticated_v29(self):
        with tempfile.TemporaryDirectory() as folder:
            site=Path(folder)
            (site/'nox-ui.js').write_bytes(self.fixture)
            (site/'index.html').write_text('<html><head></head><body>NOX</body></html>',encoding='utf8')
            app=FastAPI()
            app.mount('/nox-web-v29',module._OwnerStatic(
                site,lambda request:request.cookies.get('owner')=='yes',
                lambda:JSONResponse({'error':'AUTH'},status_code=401)))
            real=module._overlay_v122_owner_ui
            with patch.object(module,'_overlay_v122_owner_ui',
                              side_effect=lambda raw:real(raw,expected_sha=self.sha)):
                with TestClient(app) as client:
                    self.assertEqual(client.get('/nox-web-v29/nox-ui.js').status_code,401)
                    response=client.get('/nox-web-v29/nox-ui.js',cookies={'owner':'yes'})
                    self.assertEqual(response.status_code,200,response.text)
                    self.assertEqual(response.headers.get('cache-control'),'no-store')
                    self.assertIn('javascript',response.headers['content-type'])
                    self.assertEqual(response.headers.get('x-content-type-options'),'nosniff')
                    self.assertIn('ACTUAL_NOX_MODEL_SLOTS',response.text)
                    self.assertEqual((site/'nox-ui.js').read_bytes(),self.fixture)

    def test_unexpected_static_file_returns_409_not_fake_success(self):
        with tempfile.TemporaryDirectory() as folder:
            site=Path(folder)
            (site/'nox-ui.js').write_bytes(self.fixture)
            app=FastAPI()
            app.mount('/nox-web-v29',module._OwnerStatic(
                site,lambda request:request.cookies.get('owner')=='yes',
                lambda:JSONResponse({'error':'AUTH'},status_code=401)))
            with TestClient(app) as client:
                response=client.get('/nox-web-v29/nox-ui.js',cookies={'owner':'yes'})
                self.assertEqual(response.status_code,409)
                self.assertIn('HOLD_V122',response.text)
                self.assertEqual(client.get('/nox-web-v29/nox-ui.js').status_code,401)


if __name__=='__main__':
    unittest.main()
