import unittest
from training.chat_activity_lease import ChatActivityLease

class ChatStreamLeaseRegression(unittest.TestCase):
    def test_no_proxy_heartbeat_means_training_hold(self):
        lease=ChatActivityLease(clock=lambda: 100.0)
        self.assertIsNone(lease.snapshot())
        self.assertTrue(lease.should_pause_background())

    def test_response_header_does_not_end_stream(self):
        now=[100.0]
        lease=ChatActivityLease(grace_seconds=45,clock=lambda:now[0])
        self.assertTrue(lease.begin("nox.request-001"))
        now[0]=125.0  # StreamingResponse returned, SSE still open
        self.assertTrue(lease.should_pause_background())
        self.assertEqual(lease.snapshot().active_streams,1)
        lease.heartbeat("nox.request-001")
        now[0]=180.0
        self.assertTrue(lease.should_pause_background())
        self.assertTrue(lease.end("nox.request-001"))
        self.assertTrue(lease.should_pause_background())
        now[0]=226.0
        self.assertFalse(lease.should_pause_background())

    def test_multiple_streams_require_all_to_complete(self):
        lease=ChatActivityLease(clock=lambda:10.0)
        lease.begin("nox.request-001")
        lease.begin("nox.request-002")
        lease.end("nox.request-001")
        self.assertTrue(lease.should_pause_background())
        self.assertEqual(lease.snapshot().active_streams,1)

    def test_duplicate_begin_is_idempotent(self):
        lease=ChatActivityLease(clock=lambda:10.0)
        self.assertTrue(lease.begin("nox.request-001"))
        self.assertFalse(lease.begin("nox.request-001"))
        self.assertEqual(lease.snapshot().active_streams,1)
        self.assertTrue(lease.end("nox.request-001"))
        self.assertFalse(lease.end("nox.request-001"))

    def test_missing_terminal_does_not_release_gpu(self):
        now=[10.0]
        lease=ChatActivityLease(clock=lambda:now[0])
        lease.begin("nox.request-001")
        now[0]=1_000_000
        self.assertTrue(lease.should_pause_background())

    def test_invalid_request_id_rejected(self):
        lease=ChatActivityLease(clock=lambda:10.0)
        with self.assertRaises(ValueError):
            lease.begin("x")
        with self.assertRaises(ValueError):
            lease.heartbeat("nox.request-absent")
