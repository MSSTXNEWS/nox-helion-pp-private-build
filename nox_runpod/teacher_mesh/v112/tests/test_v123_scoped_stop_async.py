"""V123: prompt-independent owner STOP with blocked upstream, pure source regression."""
import asyncio
import inspect
import unittest

from nox_runpod.teacher_mesh.v112.native_v29_full_bridge import (
    _next_native_chunk_or_stop, register_native_v29_chat,
)


class RealStreamCancellation(unittest.IsolatedAsyncioTestCase):
    async def test_cancel_without_waiting_for_next_upstream_token(self):
        closed=asyncio.Event()
        waiting=asyncio.Event()
        async def blocked_source():
            try:
                waiting.set()
                await asyncio.Event().wait()  # no next chunk ever arrives
                yield 'unreachable'
            finally:
                closed.set()
        iterator=blocked_source()
        cancel=asyncio.Event()
        task=asyncio.create_task(_next_native_chunk_or_stop(iterator,cancel))
        await asyncio.wait_for(waiting.wait(),1)
        cancel.set()
        self.assertEqual(
            await asyncio.wait_for(task,timeout=2),
            ('stop',None))
        self.assertTrue(closed.is_set())

    async def test_disconnected_caller_closes_pending_upstream(self):
        waiting=asyncio.Event()
        closed=asyncio.Event()
        async def blocked_source():
            try:
                waiting.set()
                await asyncio.Event().wait()
                yield 'unreachable'
            finally:
                # Cleanup may itself await HTTP-client resource release.
                await asyncio.sleep(0)
                closed.set()
        iterator=blocked_source()
        cancel=asyncio.Event()
        task=asyncio.create_task(_next_native_chunk_or_stop(iterator,cancel))
        await asyncio.wait_for(waiting.wait(),1)
        task.cancel()  # HTTP client disconnected; no explicit STOP request.
        with self.assertRaises(asyncio.CancelledError):
            await asyncio.wait_for(task,timeout=2)
        self.assertFalse(cancel.is_set())
        self.assertTrue(closed.is_set())
        # An orphaned anext() used to make this raise "already running".
        await iterator.aclose()

    async def test_existing_unstopped_stream_and_eof_still_work(self):
        async def native_source():
            yield b'data: {"choices":[]}\n\n'
            yield b'data: [DONE]\n\n'
        iterator=native_source()
        cancel=asyncio.Event()
        first=await _next_native_chunk_or_stop(iterator,cancel)
        second=await _next_native_chunk_or_stop(iterator,cancel)
        last=await _next_native_chunk_or_stop(iterator,cancel)
        self.assertEqual(first[0],'chunk')
        self.assertEqual(second[0],'chunk')
        self.assertEqual(last,('eof',None))
        self.assertFalse(cancel.is_set())

    async def test_cancel_before_start_never_pulls_from_upstream(self):
        called=False
        async def native_source():
            nonlocal called
            called=True
            yield 'bad'
        iterator=native_source()
        cancel=asyncio.Event()
        cancel.set()
        self.assertEqual(
            await _next_native_chunk_or_stop(iterator,cancel),
            ('stop',None))
        self.assertFalse(called)
        await iterator.aclose()

    async def test_source_does_not_claim_native_gpu_stop(self):
        source=inspect.getsource(register_native_v29_chat)
        self.assertIn("'gpu_stop_verified':False",source)
        self.assertIn("event,chunk=await _next_native_chunk_or_stop(",source)
        self.assertIn("'STREAM_STOP_REQUESTED'",source)
        self.assertIn("await wire.body_iterator.aclose()",source)


if __name__=="__main__":
    unittest.main()
