"""Focused source regression for the real exported chat accounting symbols."""
from __future__ import annotations
import ast
import unittest

from owner_chat_counter_lifecycle_patch import patch, digest, Hold, SYMBOL_PINS

MARK = '''def mark_chat(busy: bool, extra: dict | None = None) -> None:
    st = load_json(CHAT_STATE, {}) or {}
    now = time.time()
    if busy:
        st["inflight"] = int(st.get("inflight", 0)) + 1
        st["last_start"] = now
    else:
        st["inflight"] = max(0, int(st.get("inflight", 0)) - 1)
        st["last_end"] = now
    st["last_ts"] = now
    if extra:
        st.update(extra)
    atomic_write_json(CHAT_STATE, st)
'''

CLASS = '''class _ChatActivityStream:
    """Transfer one acquired activity count to an explicitly closable stream."""
    def __init__(self, iterator, release):
        self._iterator = iterator.__aiter__()
        self._release = release
        self._closed = False
        self._pending = None
        self._closing = None

    def __aiter__(self):
        return self

    async def __anext__(self):
        import asyncio
        if self._closed or self._closing is not None:
            raise StopAsyncIteration
        if self._pending is not None:
            raise RuntimeError('HOLD_CONCURRENT_ACTIVITY_STREAM_PULL')
        pull = asyncio.ensure_future(self._iterator.__anext__())
        self._pending = pull
        try:
            item = await pull
            if self._closing is not None:
                raise StopAsyncIteration
            return item
        except StopAsyncIteration:
            await self.aclose()
            raise
        except BaseException:
            # Preserve the original cancellation/error if cleanup also fails.
            try:
                await self.aclose()
            except BaseException:
                pass
            raise
        finally:
            if self._pending is pull:
                self._pending = None

    async def aclose(self):
        import asyncio
        if self._closed:
            return
        if self._closing is None:
            self._closing = asyncio.create_task(self._close())
        # A caller's cancellation must not cancel the only cleanup task.
        await asyncio.shield(self._closing)

    async def _close(self):
        import asyncio
        pending = self._pending
        if pending is not None:
            if not pending.done():
                pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)
        if hasattr(self._iterator, 'aclose'):
            await self._iterator.aclose()
        # Release only after the owned pull and close have finished. A failed
        # close leaves the count acquired and prohibits further reads.
        self._closed = True
        self._release()
'''


class CounterLifecycleSourceTests(unittest.TestCase):
    def test_exported_symbol_pins(self):
        self.assertEqual(digest(MARK.encode()), SYMBOL_PINS['common.py'][1])
        self.assertEqual(digest(CLASS.encode()), SYMBOL_PINS['chat_proxy.py'][1])

    def test_lock_and_release_source_rewrites(self):
        for name, original, expected in (
            ('common.py', MARK, 'LOCK_EX'),
            ('chat_proxy.py', CLASS, 'finally:'),
        ):
            before = ('# existing header\n' + original).encode()
            new = patch(name, before, digest(before), digest(original.encode()))
            self.assertNotEqual(before, new)
            ast.parse(new)
            self.assertIn(expected, new.decode())
            with self.assertRaisesRegex(Hold, 'HOLD_COUNTER_FILE_PIN'):
                patch(name, new, digest(before), digest(original.encode()))
        result = patch('chat_proxy.py', CLASS.encode(), digest(CLASS.encode()),
                       digest(CLASS.encode()))
        self.assertIn('self._release()', result.decode())

    def test_foreign_inputs_fail_closed(self):
        with self.assertRaisesRegex(Hold, 'SCOPE'):
            patch('foreign.py', b'content')
        with self.assertRaisesRegex(Hold, 'FILE_PIN'):
            patch('common.py', MARK.encode(), '0' * 64)


if __name__ == '__main__':
    unittest.main()
