"""A binding contracts for original OneHost: never claim Windows E07."""
import unittest
from unittest.mock import Mock
from datetime import datetime, timezone
from src.nox_selfbuilder.onehost_builder import OneHostSelfBuilder
from src.nox_selfbuilder.a1_initiative_bridge import A1InitiativeBridge
from src.nox_selfbuilder.firstboot_coordinator import FirstBootCoordinator

NOW = datetime(2026, 11, 2, tzinfo=timezone.utc)

class Session:
    allowed={'chat.commands'}
    def validate(self): return None

class NativeMegapatABinding(unittest.TestCase):
    def setUp(self):
        self.stop = False
        self.epoch = 10
        self.session = Session()
        self.host = OneHostSelfBuilder(
            queue=Mock(), coder=lambda *_: None, memory_scope=lambda *_: {},
            authorize=lambda s,a,d: a == 'evolution.autonomy.read',
            stop_requested=lambda: self.stop,stop_epoch=lambda: self.epoch)
        self.initiative = Mock(spec=A1InitiativeBridge)
        self.initiative.boot.return_value={'state':'READY_FOR_EXISTING_IDLE_TICK'}
        self.initiative.tick.return_value={'state':'SOURCE_CYCLE_COMPLETED_NOT_INSTALLED'}
        self.firstboot = Mock(spec=FirstBootCoordinator)
        self.firstboot.run.return_value={'status':'ALREADY_PRESENT'}

    def bind(self):
        return self.host.bind_native_megapat_a(
            self.session,initiative_bridge=self.initiative,firstboot=self.firstboot)

    def test_binding_is_owner_callback_only(self):
        self.assertEqual(self.bind()['state'],'PORTS_BOUND_AWAITING_NATIVE_STARTUP')
        with self.assertRaises(PermissionError): self.bind()
        self.assertFalse(self.host.native_a_boot(self.session,now=NOW)['e07'])
        self.assertEqual(self.host.native_a_tick(self.session,now=NOW)['state'],
                         'SOURCE_CYCLE_COMPLETED_NOT_INSTALLED')
        self.firstboot.run.assert_called_once_with(self.session,now=NOW)
        self.initiative.tick.assert_called_once_with(self.session,now=NOW)

    def test_no_unbound_boot_or_idle_tick(self):
        with self.assertRaises(PermissionError):
            self.host.native_a_tick(self.session,now=NOW)
        self.firstboot.run.assert_not_called()

    def test_epoch_revoke_blocks_all_native_callbacks(self):
        self.bind()
        self.epoch += 1
        with self.assertRaises(PermissionError):
            self.host.native_a_boot(self.session,now=NOW)
        self.firstboot.run.assert_not_called()

    def test_null_stop_is_fail_closed(self):
        self.stop = None
        with self.assertRaises(PermissionError): self.bind()

    def test_scope_cannot_be_reused_for_other_session(self):
        self.bind()
        with self.assertRaises(PermissionError):
            self.host.native_a_tick(Session(),now=NOW)

    def test_firstboot_hold_does_not_boot_worms(self):
        self.bind()
        self.firstboot.run.return_value={'status':'HOLD'}
        self.assertEqual(self.host.native_a_boot(self.session,now=NOW)['state'],'HOLD')
        self.initiative.boot.assert_not_called()

    def test_native_owner_revoked_after_firstboot_does_not_start_worms(self):
        self.bind()
        def revoke(*_a,**_k):
            self.stop=True
            return {'status':'ALREADY_PRESENT'}
        self.firstboot.run.side_effect=revoke
        with self.assertRaises(PermissionError):
            self.host.native_a_boot(self.session,now=NOW)
        self.initiative.boot.assert_not_called()

if __name__ == '__main__':unittest.main()
