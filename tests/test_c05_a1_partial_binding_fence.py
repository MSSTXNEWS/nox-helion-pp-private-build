"""C05: native owner FirstBoot must not replay partially applied factory/bind."""
import unittest
from datetime import datetime, timezone
from pathlib import Path
import importlib.util

SOURCE = Path(__file__).resolve().parents[1] / 'src/nox_selfbuilder/a1_native_command.py'
spec = importlib.util.spec_from_file_location('nox_c05_exact_a1', SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
A1NativeCommand, A1NativeHold = module.A1NativeCommand, module.A1NativeHold
NOW = datetime(2026, 11, 2, tzinfo=timezone.utc)
HEAD = 'a' * 40

class Session:
    tenant = 'local'
    principal = 'native-user'
    chat_id = 'original-chat'
    def validate(self):
        pass

class Builder:
    def __init__(self, mode='ok'):
        self.mode, self.bind_calls, self.boot_calls = mode, 0, 0
    def bind_native_megapat_a(self, session, **components):
        self.bind_calls += 1
        if self.mode == 'throw_after_partial_bind':
            raise RuntimeError('partial owner bind')
        return {'state': 'INVALID_BIND_RECEIPT' if self.mode == 'bad_receipt' else
                          'PORTS_BOUND_AWAITING_NATIVE_STARTUP'}
    def native_a_boot(self, session, *, now):
        self.boot_calls += 1
        return {'schema': 'NOX-A-NATIVE-BOOT-v1', 'state': 'READY_FOR_EXISTING_IDLE_TICK'}
    def native_a_tick(self, session, *, now):
        return {'schema': 'NOX-A1-INITIATIVE-SOURCE-v1', 'state': 'SOURCE_ONLY'}

class PartialBindingFence(unittest.TestCase):
    def setup_owner(self, *, factory_fails=False, mode='ok', consent=True):
        builder = Builder(mode)
        called = []
        def components(session):
            called.append('factory')
            if factory_fails:
                raise RuntimeError('partial factory side effect')
            return {'initiative_bridge': object(), 'firstboot': object()}
        command = A1NativeCommand(builder=builder, components=components,
                 consent=lambda *args: consent, authorize=lambda *args: True,
                 stopped=lambda: False, stop_epoch=lambda: 1,
                 source_head=lambda: HEAD)
        return command, builder, called

    def boot(self, cmd):
        return cmd.invoke(Session(), {'action': 'selfbuilder.a1.boot'}, now=NOW)

    def test_partial_factory_failure_cannot_replay_side_effect(self):
        cmd, builder, called = self.setup_owner(factory_fails=True)
        with self.assertRaisesRegex(RuntimeError, 'partial factory'):
            self.boot(cmd)
        with self.assertRaisesRegex(A1NativeHold, 'ALREADY_BOUND_NO_DOUBLE_BOOT'):
            self.boot(cmd)
        self.assertEqual(called, ['factory'])
        self.assertEqual(builder.bind_calls, 0)
        self.assertEqual(cmd.invoke(Session(), {'action':'selfbuilder.a1.status'}, now=NOW)['state'], 'HOLD')

    def test_partial_native_bind_throw_cannot_repeat_binding(self):
        cmd, builder, called = self.setup_owner(mode='throw_after_partial_bind')
        with self.assertRaisesRegex(RuntimeError, 'partial owner bind'):
            self.boot(cmd)
        with self.assertRaisesRegex(A1NativeHold, 'ALREADY_BOUND_NO_DOUBLE_BOOT'):
            self.boot(cmd)
        self.assertEqual(called, ['factory'])
        self.assertEqual(builder.bind_calls, 1)
        self.assertEqual(builder.boot_calls, 0)

    def test_invalid_native_bind_receipt_never_retries(self):
        cmd, builder, called = self.setup_owner(mode='bad_receipt')
        with self.assertRaisesRegex(A1NativeHold, 'BINDING_NOT_PROVEN'):
            self.boot(cmd)
        with self.assertRaisesRegex(A1NativeHold, 'ALREADY_BOUND_NO_DOUBLE_BOOT'):
            self.boot(cmd)
        self.assertEqual(called, ['factory'])
        self.assertEqual(builder.bind_calls, 1)

    def test_consent_denied_before_factory_does_not_bind(self):
        cmd, builder, called = self.setup_owner(consent=False)
        with self.assertRaisesRegex(A1NativeHold, 'WPF_CONSENT_REQUIRED'):
            self.boot(cmd)
        self.assertEqual(called, [])
        self.assertEqual(builder.bind_calls, 0)

    def test_successful_boot_still_reports_only_source_state(self):
        cmd, builder, called = self.setup_owner()
        receipt = self.boot(cmd)
        self.assertEqual(receipt['state'], 'READY_FOR_EXISTING_IDLE_TICK')
        self.assertIs(receipt['installed_windows_e07'], False)
        self.assertEqual(cmd.invoke(Session(), {'action':'selfbuilder.a1.status'}, now=NOW)['state'],
                         'ACTIVE_NATIVE_BOOT_RECEIPT')
        self.assertEqual(called, ['factory'])
        self.assertEqual(builder.bind_calls, 1)

if __name__ == '__main__':
    unittest.main()
