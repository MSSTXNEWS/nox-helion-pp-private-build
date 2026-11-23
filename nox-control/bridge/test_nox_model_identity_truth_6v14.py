#!/usr/bin/env python3
"""6V14-01: health checks must not fabricate a model-weight identity."""
import asyncio
import sys
import unittest
from pathlib import Path
from unittest import mock

from fastapi import FastAPI

sys.path.insert(0, str(Path(__file__).resolve().parent))
import nox_webapi as W


class Bridge:
    MODEL = "http://127.0.0.1:8098/v1/chat/completions"
    SOUL = None


class ModelIdentityTruthTest(unittest.TestCase):
    def test_health_is_not_a_weight_identity_attestation(self):
        for reachable in (True, False):
            with self.subTest(reachable=reachable):
                with (mock.patch.object(W.threading.Thread, "start"),
                      mock.patch.object(W.os.path, "isdir", return_value=False),
                      mock.patch.object(W, "_model_ok", return_value=reachable)):
                    app = FastAPI()
                    W.install(app, Bridge())
                    endpoint = next(route.endpoint for route in app.routes
                                    if route.path == "/api/nox/status")
                    result = asyncio.run(endpoint())
                self.assertEqual(result["status"], "READY" if reachable else "HOLD")
                self.assertIsNone(result["primary_model"])
                self.assertIs(result["model_identity_verified"], False)
                self.assertEqual(result["model_identity_hold"],
                                 "OWNER_MODEL_ID_NOT_ATTESTED")
                self.assertIs(result["digest_is_weight_sha"], False)
                self.assertTrue(result["digest"].startswith("sha256:"))


if __name__ == "__main__":
    unittest.main()
