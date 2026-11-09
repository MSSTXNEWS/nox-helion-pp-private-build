"""Focused real A1NativeCommand regression: late ACL revoke cannot pass as native success.

Use the actual old/new immutable A1 module via NOX_A1_NATIVE_SOURCE path. No WPF,
model, DB, network or synthetic permissions in production are created.
"""
from datetime import datetime, timezone
from pathlib import Path
import importlib.util
import os
import unittest


def load_native():
    path = Path(os.environ.get('NOX_A1_NATIVE_SOURCE',
                               'src/nox_selfbuilder/a1_native_command.py')).resolve(strict=True)
    spec = importlib.util.spec_from_file_location('i1_real_a1_native_command', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class NativeSession:
    tenant = 'local'
    principal = 'owner'
    chat_id = 'a1-same-owner'
    def validate(self):
        return None


class OriginalBuilderStub:
    def __init__(self, state):
        self.state = state
        self.binds = self.boots = self.ticks = 0

    def bind_native_megapat_a(self, session, *, initiative_bridge, firstboot):
        self.binds += 1
        if self.state['mode'] == 'head_during_bind':
            self.state['head'] = 'b' * 40
        return {'state': 'PORTS_BOUND_AWAITING_NATIVE_STARTUP'}

    def native_a_boot(self, session, *, now):
        self.boots += 1
        if self.state['mode'] == 'revoke_during_boot':
            self.state['allowed'] = False
        return {'schema': 'NOX-A-NATIVE-BOOT-v1',
                'state': 'READY_FOR_EXISTING_IDLE_TICK'}

    def native_a_tick(self, session, *, now):
        self.ticks += 1
        if self.state['mode'] == 'revoke_during_tick':
            self.state['allowed'] = False
        return {'schema': 'NOX-A1-INITIATIVE-SOURCE-v1',
                'state': 'CANDIDATES_FOR_OWNER_REVIEW'}


class A1NativeAclRevocationRegression(unittest.TestCase):
    def setUp(self):
        self.mod = load_native()
        self.state = dict(allowed=True, stopped=False, epoch=0,
                          head='a' * 40, mode='ok')
        self.builder = OriginalBuilderStub(self.state)
        self.session = NativeSession()
        self.now = datetime(2026, 11, 2, tzinfo=timezone.utc)
        def components(session):
            if self.state['mode'] == 'revoke_during_components':
                self.state['allowed'] = False
            return {'initiative_bridge': object(), 'firstboot': object()}
        def authorize(session, action):
            if self.state['mode'] == 'status_authorize_port_error':
                raise RuntimeError('native ACL port temporarily unavailable')
            return self.state['allowed'] is True
        self.cmd = self.mod.A1NativeCommand(
            builder=self.builder, components=components,
            consent=lambda s,a: self.state['allowed'] is True,
            authorize=authorize,
            stopped=lambda: self.state['stopped'],
            stop_epoch=lambda: self.state['epoch'],
            source_head=lambda: self.state['head'])

    def act(self, command):
        return self.cmd.invoke(self.session, {'action':'selfbuilder.a1.'+command}, now=self.now)

    def test_acl_revoked_during_factory_denies_native_bind(self):
        self.state['mode'] = 'revoke_during_components'
        with self.assertRaises(self.mod.A1NativeHold):
            self.act('boot')
        self.assertEqual(self.builder.binds, 0)
        self.assertEqual(self.builder.boots, 0)

    def test_source_changed_during_bind_denies_native_boot(self):
        self.state['mode'] = 'head_during_bind'
        with self.assertRaises(self.mod.A1NativeHold):
            self.act('boot')
        self.assertEqual(self.builder.boots, 0)

    def test_acl_revoked_during_native_boot_denies_ack(self):
        self.state['mode'] = 'revoke_during_boot'
        with self.assertRaises(self.mod.A1NativeHold):
            self.act('boot')
        self.assertIsNone(self.cmd._boot_receipt)

    def test_acl_revoked_during_native_tick_denies_ack(self):
        self.act('boot')
        self.state['mode'] = 'revoke_during_tick'
        with self.assertRaises(self.mod.A1NativeHold):
            self.act('tick')
        self.assertIsNone(self.cmd._last_tick)

    def test_acl_revoked_after_boot_must_not_report_active(self):
        self.act('boot')
        self.state['allowed'] = False
        view = self.act('status')
        self.assertEqual(view['state'], 'HOLD')
        self.assertIs(view['native_bound'], False)
        self.assertEqual(view['boot_state'], 'NOT_VERIFIED')

    def test_status_fails_closed_but_remains_readable_on_acl_callback_error(self):
        self.act('boot')
        self.state['mode'] = 'status_authorize_port_error'
        status = self.act('status')
        self.assertEqual(status['state'], 'HOLD')
        self.assertIs(status['native_bound'], False)

    def test_valid_original_boot_tick_status_still_work(self):
        b = self.act('boot')
        self.assertEqual(b['state'], 'READY_FOR_EXISTING_IDLE_TICK')
        self.assertIs(b['installed_windows_e07'], False)
        t = self.act('tick')
        self.assertEqual(t['schema'], 'NOX-A1-INITIATIVE-SOURCE-v1')
        self.assertIs(t['installed_windows_e07'], False)
        s = self.act('status')
        self.assertEqual(s['state'], 'ACTIVE_NATIVE_BOOT_RECEIPT')
        self.assertIs(s['native_bound'], True)
        self.assertEqual((self.builder.binds,self.builder.boots,self.builder.ticks),(1,1,1))


if __name__ == '__main__':
    unittest.main()
