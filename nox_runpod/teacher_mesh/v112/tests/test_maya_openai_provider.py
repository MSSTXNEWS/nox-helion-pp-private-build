import asyncio
import json
import threading
import time
import unittest

from nox_runpod.teacher_mesh.v112.maya_openai_provider import (
    MayaAdmissionHold,
    MayaV112Proxy,
    REQUIRED_ADMISSION,
    admission_ok,
    bind_existing_proxy,
)


def good_admission():
    return {
        **{name: True for name in REQUIRED_ADMISSION},
        "observed_at_unix": time.time(),
        "model_id": "DeepSeek-V4.1-Flash-1017",
        "model_sha256": "b" * 64,
        "binary_sha256": "a" * 64,
        "maya_source_commit": "c81fab6c9d63cf69b928f92460e0a662b28aa9ec",
    }


class FakeProcess:
    args = ["/opt/maya/bin/maya-ds4", "--serve", "--pack", "/models/deepseek"]

    def poll(self):
        return None


class StrataEngine:
    def __init__(self):
        self.proc = FakeProcess()
        self.stop_sent = False
        self.drain_done = False

    def generate(self, *args, **kwargs):
        yield 10
        cancel = kwargs.get("cancel") or (args[3] if len(args) > 3 else None)
        while cancel is not None and not cancel.is_set():
            time.sleep(0.005)
        self.stop_sent = True
        self.drain_done = True


class FakeService:
    model = "DeepSeek-V4.1-Flash-1017"
    template = type("Template", (), {"deepseek": True, "glm_dsa": False})()

    def __init__(self):
        self.engine = StrataEngine()
        self.prepared = None
        self.cancel = None

    def with_shared(self, request, api):
        assert api == "openai"
        return dict(request)

    def check_request(self, request):
        assert request["stream"] is True

    def _loop_guard_on(self, request):
        return True

    def prepare(self, messages, tools, kwargs, max_new, cancel=None, guard=None):
        self.prepared = (messages, tools, kwargs, max_new, guard)
        self.cancel = cancel
        return [1, 2, 3], True, max_new or 32


class FakeMayaServer:
    def __init__(self, wait_for_cancel=False):
        self.wait_for_cancel = wait_for_cancel
        self.serve_called = False
        self.ids_seen = None
        self.cancel_seen = None

    def openai_to_messages(self, request, deepseek=False, glm_dsa=False):
        assert deepseek is True
        assert glm_dsa is False
        return request["messages"], request.get("tools"), {"reasoning_effort": 50}

    def openai_chunks(self, service, request, ids, thinking, tools, max_new, cancel):
        self.ids_seen = list(ids)
        self.cancel_seen = cancel
        if self.wait_for_cancel:
            yield {"choices": [{"delta": {"role": "assistant", "content": ""}}]}
            # Stand-in for the pinned StrataEngine generate boundary: cancel
            # interrupts generation and its fixture drains the request before
            # the iterator can finish.
            for _token_id in service.engine.generate(ids, max_new, {}, cancel):
                if cancel.is_set():
                    return
            return
        yield {"choices": [{"delta": {"role": "assistant", "content": ""}}]}
        yield {"choices": [{"delta": {"content": "Hola"}}]}
        yield {"choices": [{"delta": {}, "finish_reason": "stop"}]}


class MayaV112ProviderTests(unittest.TestCase):
    def run_async(self, coro):
        return asyncio.run(coro)

    def make_provider(self, *, gate=None, enabled=True, server=None, counter=None):
        service = FakeService()
        factory_calls = counter if counter is not None else []

        def factory():
            factory_calls.append("create")
            return service

        provider = MayaV112Proxy(
            maya_server=server or FakeMayaServer(),
            service_factory=factory,
            admission=gate or good_admission,
            enabled=enabled,
        )
        return provider, service, factory_calls

    async def body_bytes(self, response):
        chunks = []
        async for item in response.body_iterator:
            chunks.append(item)
        return b"".join(chunks)

    def test_every_gate_is_explicit_and_true(self):
        self.assertTrue(admission_ok(good_admission(), True))
        self.assertFalse(admission_ok(good_admission(), False))
        for key in REQUIRED_ADMISSION:
            gate = good_admission()
            gate[key] = False
            self.assertFalse(admission_ok(gate, True), key)
            gate[key] = 1
            self.assertFalse(admission_ok(gate, True), key + " must be bool True")

    def test_admission_timestamp_must_be_fresh_and_present(self):
        gate = good_admission()
        self.assertFalse(admission_ok(gate, True, now=gate["observed_at_unix"] + 10.01))
        self.assertFalse(admission_ok(gate, True, now=gate["observed_at_unix"] - 1.01))
        gate["model_sha256"] = "not-a-sha"
        self.assertFalse(admission_ok(gate, True))
        gate["model_sha256"] = "b" * 64
        gate["maya_source_commit"] = "unPinned"
        self.assertFalse(admission_ok(gate, True))
        gate["maya_source_commit"] = "c81fab6c9d63cf69b928f92460e0a662b28aa9ec"
        del gate["observed_at_unix"]
        self.assertFalse(admission_ok(gate, True))

    def test_default_hold_does_not_construct_or_spawn_engine(self):
        provider, _service, calls = self.make_provider(enabled=False)
        response = self.run_async(provider({"messages": [{"role": "user", "content": "hi"}]}))
        body = self.run_async(self.body_bytes(response))
        self.assertEqual(calls, [])
        self.assertIn(b"HOLD_MAYA_ADMISSION", body)
        self.assertNotIn(b"[DONE]", body.split(b"HOLD_MAYA_ADMISSION")[0])

    def test_v112_proxy_streams_official_openai_chunks_without_listener(self):
        server = FakeMayaServer()
        provider, service, calls = self.make_provider(server=server)
        response = self.run_async(provider({
            "messages": [{"role": "user", "content": "Hola"}],
            "stream": True,
            "_owner": True,
        }))
        body = self.run_async(self.body_bytes(response))
        self.assertEqual(calls, ["create"])
        self.assertEqual(response.media_type, "text/event-stream")
        self.assertIn(b'"content": "Hola"', body)
        self.assertTrue(body.endswith(b"data: [DONE]\n\n"))
        self.assertEqual(service.prepared[0][0]["content"], "Hola")
        self.assertEqual(service.prepared[3], 0)
        self.assertEqual(server.ids_seen, [1, 2, 3])
        self.assertIs(server.cancel_seen, service.cancel)
        self.assertFalse(server.serve_called)

    def test_v112_body_iterator_close_sets_engine_cancel(self):
        server = FakeMayaServer(wait_for_cancel=True)
        provider, service, calls = self.make_provider(server=server)
        response = self.run_async(provider({
            "messages": [{"role": "user", "content": "stop me"}],
        }))

        async def cancel_stream():
            iterator = response.body_iterator.__aiter__()
            first = await anext(iterator)
            self.assertIn(b"data:", first)
            await iterator.aclose()

        self.run_async(cancel_stream())
        self.assertTrue(service.cancel.is_set())
        self.assertIs(server.cancel_seen, service.cancel)
        self.assertTrue(service.engine.stop_sent)
        self.assertTrue(service.engine.drain_done)
        self.assertEqual(calls, ["create"])

    def test_wrong_model_contract_holds_before_streaming_chunks(self):
        server = FakeMayaServer()
        provider, service, calls = self.make_provider(server=server)
        service.model = "wrong-model"
        response = self.run_async(provider({"messages": [{"role": "user", "content": "hi"}]}))
        body = self.run_async(self.body_bytes(response))
        self.assertIn(b"HOLD_MAYA_ENGINE_UNAVAILABLE", body)
        self.assertIsNone(server.ids_seen)
        self.assertEqual(calls, ["create"])

    def test_binding_replaces_only_existing_provider_slot_without_fallback(self):
        provider, _service, _calls = self.make_provider(enabled=False)
        fallback_calls = []
        trusted = {"_proxy_completion": lambda payload: fallback_calls.append(payload)}
        bind_existing_proxy(trusted, provider)
        self.assertIs(trusted["_proxy_completion"], provider)
        self.assertTrue(trusted["_maya_v112_provider_bound"])
        with self.assertRaises(MayaAdmissionHold):
            bind_existing_proxy(trusted, provider)
        self.assertEqual(fallback_calls, [])


if __name__ == "__main__":
    unittest.main()
