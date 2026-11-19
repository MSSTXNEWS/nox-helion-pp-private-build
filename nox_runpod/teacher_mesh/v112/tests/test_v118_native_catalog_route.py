"""V118: actual staged V29 owner catalog navigation; zero changes to frozen source."""
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from nox_runpod.teacher_mesh.v112 import native_v29_full_bridge as bridge

ORIGINAL = b"const path=page=>native?'/nox/'+page:(files[page]||page)+'.html';"


class FrozenCatalogOverlayTests(unittest.TestCase):
    def test_exact_sha_and_rewrite_in_staged_mount_only(self):
        data = b"/* source */\n" + ORIGINAL + b"\n"
        sha = hashlib.sha256(data).hexdigest()
        new = bridge._catalog_owner_overlay(data, expected_sha=sha)
        self.assertEqual(data, b"/* source */\n"+ORIGINAL+b"\n")
        self.assertIn(b"location.pathname.startsWith('/nox-web-v29/')", new)
        self.assertIn(b"'/nox-web-v29/'+(files[page]||page)+'.html'", new)
        self.assertIn(b"native?'/nox/'+page", new)
        self.assertNotEqual(new, data)

    def test_drift_hold_does_not_silently_serve_wrong_source(self):
        sha = hashlib.sha256(ORIGINAL).hexdigest()
        with self.assertRaisesRegex(ValueError, "HOLD_FROZEN_V29_CATALOG_SHA"):
            bridge._catalog_owner_overlay(ORIGINAL + b" changed", expected_sha=sha)
        with self.assertRaisesRegex(ValueError, "HOLD_CATALOG_LINK_SOURCE_DRIFT"):
            bridge._catalog_owner_overlay(b"// other code", expected_sha=hashlib.sha256(b"// other code").hexdigest())

    def test_authenticated_mount_uses_overlay_and_keeps_disk_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            web = Path(folder)
            data = b"/* fixture */\n" + ORIGINAL + b"\n"
            target = web / 'nox-function-catalog.js'
            target.write_bytes(data)
            (web / 'chat.html').write_text('<html><head></head><body>NOX</body></html>')
            app = FastAPI()
            app.mount('/nox-web-v29', bridge._OwnerStatic(
                directory=web,
                auth=lambda req: req.cookies.get('nox_owner') == 'yes',
                unauthorized=lambda: JSONResponse({'error':'AUTH'},status_code=401)))
            native = bridge._catalog_owner_overlay
            with patch.object(bridge, '_catalog_owner_overlay',
                              side_effect=lambda raw: native(raw, expected_sha=hashlib.sha256(data).hexdigest())):
                with TestClient(app) as client:
                    denied=client.get('/nox-web-v29/nox-function-catalog.js')
                    self.assertEqual(denied.status_code, 401)
                    good=client.get('/nox-web-v29/nox-function-catalog.js',cookies={'nox_owner':'yes'})
                    self.assertEqual(good.status_code, 200)
                    self.assertIn('application/javascript',good.headers['content-type'])
                    self.assertEqual(good.headers['cache-control'],'no-store')
                    self.assertIn("'/nox-web-v29/'",good.text)
                    html=client.get('/nox-web-v29/chat.html',cookies={'nox_owner':'yes'})
                    self.assertEqual(html.status_code,200)
            self.assertEqual(target.read_bytes(),data)


if __name__=='__main__':
    unittest.main()
