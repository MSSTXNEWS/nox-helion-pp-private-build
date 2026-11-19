"""Source-only tests for dynamic NOX proxy inspection."""
from __future__ import annotations

import json
import re
import unittest

from nox_runpod.teacher_mesh.v76 import proxy_source_inspect_v2 as probe


def analyzer():
    namespace = {}
    exec(compile(probe.ANALYZER, "<proxy-source-analyzer>", "exec"), namespace)
    return namespace["analyze_source"]


class ProxySourceInspectTests(unittest.TestCase):
    def test_reports_context_functions_routes_and_constant_slice_bounds_only(self):
        raw = b'''
API_KEY = "DO_NOT_PRINT_THIS_SECRET"
def _trim_ctx(messages):
    return messages[-16:]
def _build_messages(body):
    prompt = body["prompt"][:8000]
    dialog_id = body.get("dialog_id")
    messages = body.get("messages", [])
    history = body.get("history", [])
    message = body.get("message")
    prior = load_dialog_history(dialog_id)
    return prompt
def prepare_payload(messages):
    return messages
@app.post("/api/nox/chat")
def route(body):
    return prepare_payload(_trim_ctx(_build_messages(body)))
'''
        report = analyzer()(raw)
        self.assertEqual(report["source_bytes"], len(raw))
        self.assertEqual(report["functions"]["_trim_ctx"][0]["constant_slice_bounds"][0]["lower"], -16)
        self.assertEqual(report["functions"]["_build_messages"][0]["constant_slice_bounds"][0]["upper"], 8000)
        self.assertEqual(report["functions"]["prepare_payload"][0]["line"], 13)
        self.assertTrue(report["callsites"]["prepare_payload"])
        self.assertEqual(report["chat_routes"][0]["method"], "POST")
        self.assertEqual(report["chat_routes"][0]["path"], "/api/nox/chat")
        self.assertIn("prepare_payload", report["chat_routes"][0]["context_calls"])
        self.assertEqual(
            report["chat_routes"][0]["body_key_reads"],
            [],
        )
        context = report["functions"]["_build_messages"][0]
        self.assertEqual(
            context["body_key_reads"],
            ["dialog_id", "history", "message", "messages", "prompt"],
        )
        self.assertTrue(context["hydration_call_presence"]["history"])
        self.assertTrue(context["hydration_call_presence"]["dialog"])
        self.assertTrue(context["hydration_call_presence"]["storage"])
        self.assertTrue(report["chat_routes"][0]["hydration_call_presence"]["s03"] == [])
        encoded = json.dumps(report, ensure_ascii=False)
        self.assertNotIn("DO_NOT_PRINT_THIS_SECRET", encoded)
        self.assertIn("AST-only", report["analysis_note"])

    def test_reports_stream_route_and_s03_call_presence_without_values(self):
        raw = b'''\ndef _build_messages(payload):\n    dialog_id = payload.get("dialog_id")\n    return load_s03_history(dialog_id)\n@app.post("/api/nox/chat/stream")\nasync def route(request):\n    body = await request.json()\n    return _build_messages(body)\n'''
        report = analyzer()(raw)
        route = report["chat_routes"][0]
        self.assertEqual(route["path"], "/api/nox/chat/stream")
        self.assertEqual(route["body_key_reads"], [])
        context = report["functions"]["_build_messages"][0]
        self.assertEqual(context["body_key_reads"], ["dialog_id"])
        self.assertTrue(context["hydration_call_presence"]["s03"])
        self.assertTrue(context["hydration_call_presence"]["history"])
        encoded = json.dumps(report)
        self.assertNotIn("load_s03_history", encoded)
        self.assertNotIn("dialog_id)", encoded)

    def test_route_binding_contract_reports_static_calls_but_unknown_runtime_identity(self):
        raw = b'''
API_KEY = "DO_NOT_PRINT_BINDING_SECRET"
@app.post("/api/nox/chat")
async def chat_route(request):
    return model_bridge.stream(load_model(request))
'''
        report = analyzer()(raw)
        route = report["chat_routes"][0]
        self.assertEqual(route["handler"], "chat_route")
        self.assertEqual(
            route["direct_call_symbols"],
            ["load_model", "model_bridge.stream"],
        )
        bindings = route["serving_bindings"]
        self.assertEqual(bindings["evidence_scope"], "PROXY_SOURCE_AST_ONLY")
        self.assertEqual(bindings["bridge_identity"], "UNKNOWN")
        self.assertEqual(bindings["model_identity"], "UNKNOWN")
        self.assertEqual(
            bindings["callbacks"],
            {f"C{i:02d}": "UNKNOWN" for i in range(1, 9)},
        )
        encoded = json.dumps(report, ensure_ascii=False)
        self.assertNotIn("DO_NOT_PRINT_BINDING_SECRET", encoded)
        self.assertIn("UNKNOWN", report["analysis_note"])

    def test_route_direct_call_metadata_is_bounded(self):
        calls = "\\n".join(f"    f{i}()" for i in range(40))
        raw = (
            '@app.post("/api/nox/chat")\\ndef chat_route():\\n'
            + calls
            + "\\n    return None\\n"
        ).encode()
        route = analyzer()(raw)["chat_routes"][0]
        self.assertEqual(len(route["direct_call_symbols"]), 32)
        self.assertEqual(route["direct_call_symbols"], sorted(route["direct_call_symbols"]))

    def test_missing_context_functions_are_explicitly_reported(self):
        report = analyzer()(b"def health():\n    return True\n")
        self.assertEqual(report["functions"]["_trim_ctx"], [])
        self.assertEqual(report["functions"]["_build_messages"], [])
        self.assertEqual(report["functions"]["prepare_payload"], [])
        self.assertEqual(report["chat_routes"], [])

    def test_rejects_oversized_source(self):
        with self.assertRaisesRegex(ValueError, "HOLD_PROXY_SOURCE_SIZE"):
            analyzer()(b"x" * (probe.MAX_SOURCE_BYTES + 1))

    def test_rejects_invalid_source_without_echoing_contents(self):
        with self.assertRaisesRegex(ValueError, "HOLD_PROXY_SOURCE_PARSE"):
            analyzer()(b'password = "sensitive"\ndef broken(:\n')

    def test_remote_python_payload_compiles_without_host_execution(self):
        remote_python = probe.REMOTE.split("python3 - <<'PYREMOTE'\n", 1)[1].split("\nPYREMOTE", 1)[0]
        compile(remote_python, "<remote-proxy-inspector>", "exec")
        self.assertIn("st_size=0", remote_python)
        self.assertIn("start_ticks", remote_python)

    def test_remote_probe_payload_has_a_stable_exact_sha256_pin(self):
        digest = probe.probe_source_hash()
        self.assertRegex(digest, re.compile(r"^[0-9a-f]{64}$"))
        self.assertEqual(digest, probe.probe_source_hash())
        self.assertIn("NATIVE_PROXY_NOT_RESTARTED=true", probe.REMOTE)
        self.assertIn("NATIVE_PROXY_SOURCE_META=", probe.REMOTE)


if __name__ == "__main__":
    unittest.main()

