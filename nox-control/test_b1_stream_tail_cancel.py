"""B1 only: a cancelled SSE tail cannot leave a certifiable S03 final."""
import unittest

from test_owner_chat_stream import Chunks, StreamTests, frame


class B1TerminalCancellationTest(unittest.IsolatedAsyncioTestCase):
    def fixture(self, chunks):
        helper = StreamTests('test_bounded_sse_metadata_preserves_real_tokens_and_terminal')
        native = helper.native()
        requests, patch_client = helper.transport([chunks])
        return native, requests, patch_client

    async def test_early_close_after_finish_clears_final_without_second_post(self):
        chunks = Chunks([frame('Hola'), frame(finish='stop'), b'data: [DONE]\n\n'])
        native, requests, patch_client = self.fixture(chunks)
        payload = {'messages': [{'role': 'user', 'content': 'Hola'}]}
        with patch_client:
            response = await native['owner_completion'](
                'http://native/model', payload, 'Hola', True)
            iterator = response.body_iterator
            self.assertIn('Hola', await anext(iterator))
            terminal = await anext(iterator)
            self.assertIn('finish_reason', terminal)
            self.assertEqual(payload['_agent_final'], 'Hola')
            # Browser drops the socket between stop and [DONE].
            await iterator.aclose()
        self.assertNotIn('_agent_final', payload)
        self.assertTrue(chunks.closed)
        self.assertEqual(len(requests), 1)

    async def test_full_exhaustion_preserves_final_and_single_post(self):
        chunks = Chunks([frame('Hola'), frame(finish='stop'), b'data: [DONE]\n\n'])
        native, requests, patch_client = self.fixture(chunks)
        payload = {'messages': [{'role': 'user', 'content': 'Hola'}]}
        with patch_client:
            response = await native['owner_completion'](
                'http://native/model', payload, 'Hola', True)
            wire = ''.join([part async for part in response.body_iterator])
        self.assertIn('[DONE]', wire)
        self.assertEqual(payload['_agent_final'], 'Hola')
        self.assertTrue(chunks.closed)
        self.assertEqual(len(requests), 1)


if __name__ == '__main__':
    unittest.main()
