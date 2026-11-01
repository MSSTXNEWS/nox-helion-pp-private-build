import unittest
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from nox_selfbuilder.a1_native_command import A1NativeCommand, A1NativeHold
NOW=datetime(2026,11,2,12,tzinfo=timezone.utc)
HEAD='a'*40

@dataclass
class Session:
    tenant:str='local'
    principal:str='original'
    chat_id:str='default'
    def validate(self):
        if self.tenant!='local': raise PermissionError('native scope')

class Builder:
    def __init__(self): self.calls=[];self.ready=True
    def bind_native_megapat_a(self,session,*,initiative_bridge,firstboot):
        self.calls.append('bind');return {'state':'PORTS_BOUND_AWAITING_NATIVE_STARTUP'}
    def native_a_boot(self,session,*,now):
        self.calls.append('boot');return {'schema':'NOX-A-NATIVE-BOOT-v1','state':('READY_FOR_EXISTING_IDLE_TICK' if self.ready else 'HOLD')}
    def native_a_tick(self,session,*,now):
        self.calls.append('tick');return {'schema':'NOX-A1-INITIATIVE-SOURCE-v1','state':'SOURCE_CYCLE_COMPLETED_NOT_INSTALLED'}

class Tests(unittest.TestCase):
    def setUp(self):
        self.b=Builder();self.stopped=False;self.epoch=1;self.head=HEAD;self.grant=True;self.consent=True;self.created=0
        def components(_):
            self.created+=1
            return {'initiative_bridge':object(),'firstboot':object()}
        self.x=A1NativeCommand(builder=self.b,components=components,
                 consent=lambda *a:self.consent,authorize=lambda *a:self.grant,
                 stopped=lambda:self.stopped,stop_epoch=lambda:self.epoch,
                 source_head=lambda:self.head)
        self.s=Session()
    def go(self,action,session=None):return self.x.invoke(session or self.s,{'action':action},now=NOW)
    def boot(self):return self.go('selfbuilder.a1.boot')
    def test_status_before_boot_is_hold_no_side_effects(self):
        a=self.go('selfbuilder.a1.status');self.assertEqual(a['state'],'HOLD');self.assertEqual(self.b.calls,[])
    def test_native_boot_and_tick(self):
        self.assertEqual(self.boot()['state'],'READY_FOR_EXISTING_IDLE_TICK')
        self.assertEqual(self.go('selfbuilder.a1.tick')['state'],'SOURCE_CYCLE_COMPLETED_NOT_INSTALLED')
        self.assertEqual(self.b.calls,['bind','boot','tick'])
        self.assertEqual(self.go('selfbuilder.a1.status')['last_tick_state'],'SOURCE_CYCLE_COMPLETED_NOT_INSTALLED')
    def test_no_consent_no_factory(self):
        self.consent=False
        with self.assertRaisesRegex(A1NativeHold,'CONSENT'):self.boot()
        self.assertEqual(self.created,0)
    def test_no_acl_no_factory(self):
        self.grant=False
        with self.assertRaisesRegex(A1NativeHold,'ACL'):self.boot()
        self.assertEqual(self.created,0)
    def test_native_stop_before_bind(self):
        self.stopped=True
        with self.assertRaisesRegex(A1NativeHold,'STOP'):self.boot()
        self.assertEqual(self.b.calls,[])
    def test_bad_head_holds(self):
        self.head='bad'
        with self.assertRaisesRegex(A1NativeHold,'SOURCE'):self.boot()
    def test_status_stop_never_active(self):
        self.boot();self.stopped=True
        self.assertEqual(self.go('selfbuilder.a1.status')['state'],'HOLD')
        with self.assertRaisesRegex(A1NativeHold,'STOP'):self.go('selfbuilder.a1.tick')
    def test_epoch_change_denies_tick(self):
        self.boot();self.epoch+=1
        with self.assertRaisesRegex(A1NativeHold,'REBOOT'):self.go('selfbuilder.a1.tick')
    def test_head_change_denies_tick(self):
        self.boot();self.head='b'*40
        with self.assertRaisesRegex(A1NativeHold,'REBOOT'):self.go('selfbuilder.a1.tick')
    def test_one_boot_only(self):
        self.boot()
        with self.assertRaisesRegex(A1NativeHold,'ALREADY_BOUND'):self.boot()
        self.assertEqual(self.created,1)
    def test_cross_principal_never_reuse(self):
        self.boot()
        with self.assertRaisesRegex(A1NativeHold,'CROSS_OWNER'):
            self.go('selfbuilder.a1.tick',Session(principal='different'))
    def test_unapproved_action_denied(self):
        with self.assertRaisesRegex(A1NativeHold,'NOT_APPROVED'):self.go('training.start')
    def test_untrusted_arguments_denied(self):
        with self.assertRaisesRegex(A1NativeHold,'EXACT_COMMAND'):
            self.x.invoke(self.s,{'action':'selfbuilder.a1.boot','signed_by_native_owner':True},now=NOW)
    def test_tick_before_boot_holds(self):
        with self.assertRaisesRegex(A1NativeHold,'BOOT_NOT_READY'):self.go('selfbuilder.a1.tick')
    def test_boot_hold_not_active(self):
        self.b.ready=False;self.boot()
        self.assertEqual(self.go('selfbuilder.a1.status')['state'],'HOLD')
        with self.assertRaisesRegex(A1NativeHold,'BOOT_NOT_READY'):self.go('selfbuilder.a1.tick')
    def test_source_receipts_not_windows_acceptance(self):
        self.boot();self.assertFalse(self.go('selfbuilder.a1.status')['installed_windows_e07'])

if __name__=='__main__':unittest.main()
