"""Deterministic native request admission after a lost/corrupted reply stream."""
import io
import threading
import unittest
from p02_native_ingress import NativeIngress, ProtocolHold
from p02_framed_worker import serve_native_frames
from test_p02_framed_worker import Dispatch, R, request, frames

class FaultWriter(io.BytesIO):
    def __init__(self, mode):
        super().__init__(); self.mode=mode
        self.failed=threading.Event(); self.worker=None
        self.write_calls=0; self.calls_at_failure=None
    def fail(self):
        self.worker=threading.current_thread()
        self.calls_at_failure=self.write_calls
        self.failed.set()
    def write(self, data):
        self.write_calls+=1
        if self.mode in ('zero','write_error') and self.write_calls==1:
            return super().write(data[:1])
        if self.mode in ('zero','write_error') and self.write_calls==2:
            self.fail()
            if self.mode=='write_error':raise BrokenPipeError('transport closed')
            return 0
        return super().write(data)
    def flush(self):
        if self.mode=='flush_error' and not self.failed.is_set():
            self.fail();raise OSError('flush failed')
        return super().flush()

class FailureAdmissionTests(unittest.TestCase):
    def test_reply_failure_prevents_later_native_request_and_more_frame_writes(self):
        for mode in ('zero','write_error','flush_error'):
            with self.subTest(failure=mode):
                writer=FaultWriter(mode)
                first=frames(request(301)); second=frames(request(302))
                class GatedReader(io.BytesIO):
                    def read(self, n=-1):
                        if self.tell()==len(first):
                            if not writer.failed.wait(1):raise AssertionError('failure never reached')
                            writer.worker.join(1)
                            if writer.worker.is_alive():raise AssertionError('first dispatch did not exit')
                        return super().read(n)
                dispatcher=Dispatch()
                ingress=NativeIngress(dispatcher,lambda:'native-only',expected_run_id=R)
                with self.assertRaisesRegex(ProtocolHold,'NATIVE_OUTPUT_TRANSPORT_FAILED'):
                    serve_native_frames(ingress,GatedReader(first+second),writer)
                self.assertEqual(dispatcher.seen,['chat.model'])
                self.assertEqual(writer.write_calls,writer.calls_at_failure)

if __name__=='__main__':unittest.main()
