"""B1 source-only guard: aggregate chat deadline cannot certify an unfinished turn."""
import asyncio
import json
import unittest
from unittest.mock import patch

import owner_chat_stream as stream
from test_owner_chat_stream import Chunks, StreamTests, frame


class B1TurnDeadlineTest(unittest.IsolatedAsyncioTestCase):
    def fixture(self):
        # The model emits a partial token, then can remain silent indefinitely.
        gate = asyncio.Event()
        chunks = Chunks([frame('partial'), frame(finish='stop'),
                         b'data: [DONE]\n\n'], gate=gate)
        helper = StreamTests('test_bounded_sse_metadata_preserves_real_tokens_and_terminal')
        native = helper.native()
        requests, patch_client = helper.transport([chunks])
        return chunks, native, requests, patch_client

    async def test_sse_timeout_after_partial_never_sets_s03_final_or_reposts(self):
        chunks, native, requests, patch_client = self.fixture()
        payload = {'messages': [{'role': 'user', 'content': 'slow reply'}]}
        with patch_client, patch.object(stream, 'OWNER_TURN_DEADLINE_SECONDS', 0.035):
            response = await native['owner_completion'](
                'http://native/model', payload, 'slow reply', True)
            wire = ''.join([part async for part in response.body_iterator])
        self.assertIn('partial', wire)
        self.assertIn('HOLD_OWNER_TURN_TIMEOUT', wire)
        self.assertNotIn('[DONE]', wire)
        self.assertNotIn('_agent_final', payload)
        self.assertEqual(len(requests), 1)
        self.assertTrue(chunks.closed)

    async def test_nonstream_timeout_has_502_without_final_or_repost(self):
        chunks, native, requests, patch_client = self.fixture()
        payload = {'messages': [{'role': 'user', 'content': 'slow reply'}]}
        with patch_client, patch.object(stream, 'OWNER_TURN_DEADLINE_SECONDS', 0.035):
            response = await native['owner_completion'](
                'http://native/model', payload, 'slow reply', False)
        self.assertEqual(response.status_code, 502)
        self.assertEqual(json.loads(response.body)['error']['code'],
                         'HOLD_OWNER_TURN_TIMEOUT')
        self.assertNotIn('_agent_final', payload)
        self.assertEqual(len(requests), 1)
        self.assertTrue(chunks.closed)


if __name__ == '__main__':
    unittest.main()
