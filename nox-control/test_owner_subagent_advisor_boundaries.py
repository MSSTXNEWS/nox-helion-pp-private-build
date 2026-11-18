"""Source-only advisor safety regressions; no credentials, HTTP, or native calls."""
import asyncio
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gateway = load("advisor_gateway_boundary_test", "owner_senior_gateway.py")
outbox_stub = types.ModuleType("owner_event_outbox")
with patch.dict(sys.modules, {"owner_event_outbox": outbox_stub}):
    lifecycle = load("advisor_lifecycle_binding_test", "owner_task_lifecycle.py")
mentor = load("advisor_mentor_boundary_test", "owner_dispatcher_mentor.py")


class AdvisorBoundaryTests(unittest.TestCase):
    def test_paid_gateway_public_and_transport_boundaries_make_no_requests(self):
        self.assertIs(gateway.DEFAULT_CONFIG["enabled"], False)
        self.assertIs(gateway._PAID_PROVIDER_CALLS_DISABLED, True)

        forbidden = Mock(side_effect=AssertionError("paid boundary must short-circuit"))
        with patch.object(gateway, "_credentials", forbidden), \
             patch.object(gateway, "_config", forbidden), \
             patch.object(gateway, "_request", forbidden), \
             patch.object(gateway, "_write", forbidden), \
             patch.object(gateway, "_lock", forbidden):
            self.assertEqual(gateway.consult_plan({})["state"], "DISABLED_NO_PAID_PROVIDER")
            self.assertEqual(gateway.verify_access()["state"], "DISABLED_NO_PAID_PROVIDER")
            self.assertEqual(gateway.set_credential("openai", "")["state"], "DISABLED_NO_PAID_PROVIDER")
        forbidden.assert_not_called()

        http_client = Mock(side_effect=AssertionError("HTTP client must not be constructed"))
        fake_httpx = types.SimpleNamespace(AsyncClient=http_client)
        with patch.dict(sys.modules, {"httpx": fake_httpx}):
            result = asyncio.run(gateway._request("openai", None, "diagnostic", {}))
        self.assertEqual(result["state"], "DISABLED_NO_PAID_PROVIDER")
        http_client.assert_not_called()

    def test_remote_and_hostname_advisors_hold_before_resource_or_http(self):
        admission = Mock(return_value="HOLD_ADVISOR_RESOURCE_GATE_UNBOUND")
        transport = Mock(side_effect=AssertionError("advisor HTTP must not run"))
        with patch.object(mentor, "advisor_resource_admission_hold", admission), \
             patch.object(mentor.urllib.request, "build_opener", transport):
            for endpoint in ("https://203.0.113.7:1234/chat/completions",
                             "http://localhost:1234/chat/completions"):
                with self.subTest(endpoint=endpoint):
                    with self.assertRaisesRegex(RuntimeError, "BLOCKED_SENIOR_ENDPOINT"):
                        mentor.consult({"endpoint": endpoint, "model": "local-test", "_key": None},
                                       {}, "a" * 64)
            admission.assert_not_called()
            with self.assertRaisesRegex(RuntimeError, "HOLD_ADVISOR_RESOURCE_GATE_UNBOUND"):
                mentor.consult({"endpoint": "http://127.0.0.1:1234/chat/completions",
                                "model": "local-test", "_key": None}, {}, "a" * 64)
            admission.assert_called_once_with()
            transport.assert_not_called()

    def test_lifecycle_rewrites_only_the_unique_zero_arg_bind_and_is_idempotent(self):
        pins = {
            "owner_mentor": "ed135563c70acb24ce508bbd9f0d53616b5810bd113b1818f677766f751de82a",
            "owner_event_outbox": "e15d458f9d1f03b23fcbf0267206621769ff92f2bfe00d3baf79217e2ab74a02",
            "owner_task_plans": "7eb207b361086d3c34299b44fb36d96758cf824a7bf68a05e7868408d646f773",
            "owner_senior_gateway": "40cbaec2e32e43f2aa78a1078ed296d4957c620256081695111b81136d2d3751",
        }
        source = (
            "import owner_task_lifecycle\n"
            "def run_one(): pass\n"
            "def write_status(): pass\n"
            "def owner_claim_ready(): pass\n"
            "def _nox_owner_task_admitted(): pass\n"
            "owner_task_lifecycle.bind_dispatcher()\n"
            "if __name__ == \"__main__\":\n"
            "    main()\n"
        )
        digest = lifecycle.hashlib.sha256
        source_sha = digest(source.encode()).hexdigest()
        patched = lifecycle.patch_dispatcher(source, source_sha, pins)
        self.assertEqual(patched.count("owner_task_lifecycle.bind_dispatcher("), 1)
        self.assertEqual(patched.count("# " + lifecycle.PATCH_MARKER), 1)
        self.assertIn("owner_task_lifecycle.bind_dispatcher(globals(), " + repr(pins) + ")", patched)
        self.assertEqual(lifecycle.patch_dispatcher(
            patched, digest(patched.encode()).hexdigest(), pins), patched)

        duplicate = source.replace(
            "owner_task_lifecycle.bind_dispatcher()",
            "owner_task_lifecycle.bind_dispatcher()\nowner_task_lifecycle.bind_dispatcher()")
        with self.assertRaisesRegex(RuntimeError, "HOLD_LIFECYCLE_BIND_CALL_COUNT"):
            lifecycle.patch_dispatcher(duplicate, digest(duplicate.encode()).hexdigest(), pins)


if __name__ == "__main__":
    unittest.main()
