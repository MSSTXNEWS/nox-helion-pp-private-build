"""COMPONENT TEST ONLY: original P02 NativeIngress and FramedWorker over real OS pipes.
Never deployed, serves no network socket, holds no user data, and uses no models.
"""
import sys
import threading
from p02_native_ingress import NativeIngress
from p02_framed_worker import serve_native_frames

ready = threading.Event()
class ExistingFakeOwner:
    def execute(self, route, payload, session):
        assert session == 'trusted-windows-native-test-only'
        if route == 'helion.chat':
            if not ready.wait(timeout=5): raise RuntimeError('STOP was not delivered')
        if route == 'chat.stop': ready.set()
        return {'route': route, 'acceptedBy': 'existing-owner-fixture'}

run_id = sys.argv[1]
ingress = NativeIngress(ExistingFakeOwner(), lambda: 'trusted-windows-native-test-only', expected_run_id=run_id)
serve_native_frames(ingress, sys.stdin.buffer, sys.stdout.buffer)
