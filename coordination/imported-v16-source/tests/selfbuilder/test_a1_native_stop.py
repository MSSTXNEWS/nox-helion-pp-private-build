"""Focused regression for the exact current GitHub worm_autopilot.py with injected
existing OneHost APIs. No network, second worker, permissions or files modified.
"""
import importlib.util
import sys
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
PKG='nox_a1_stop_isolated_fixture'
# Private test-only package: never overwrite production nox_selfbuilder sys.modules.
for name in (PKG,PKG+'.growth_sandbox',PKG+'.worms'):
    if name not in sys.modules:
        m=types.ModuleType(name)
        if name==PKG:m.__path__=[]
        sys.modules[name]=m

class WormHold(RuntimeError):pass
class WormSwarm:
    def __init__(self):self.enabled=False;self.ticks=0;self.toggle_calls=0
    def set_enabled(self, session, enabled):
        self.toggle_calls+=1;self.enabled=enabled;return self.status()
    def tick(self, session, now, max_tasks):
        self.ticks+=1;return self.status()
    def status(self):return {'enabled':self.enabled,'ticks':self.ticks}

def daily_initiatives(now, source_head):return {'planned_tasks':240,'source_head':source_head}

sys.modules[PKG+'.worms'].WormHold=WormHold
sys.modules[PKG+'.worms'].WormSwarm=WormSwarm
sys.modules[PKG+'.growth_sandbox'].daily_initiatives=daily_initiatives
spec=importlib.util.spec_from_file_location(PKG+'.worm_autopilot',ROOT/'src/nox_selfbuilder/worm_autopilot.py')
mod=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=mod;spec.loader.exec_module(mod)
NOW=datetime(2026,11,1,18,0,tzinfo=timezone.utc)

class NativeStopTests(unittest.TestCase):
    def setUp(self):
        self.swarm=WormSwarm();self.saved=[];self.native=False
        self.policy={'schema':'NOX-NATIVE-WORMS-POLICY-v1',
         'signed_by_native_owner':True,'allow_autonomous_public_research':True,
         'approved_source_head':'a'*40,'expires_at_utc':(NOW+timedelta(days=1)).isoformat()}
        self.engine=mod.WormAutopilot(native_signed_policy=lambda session:self.policy,
         source_head=lambda:'a'*40,swarm=self.swarm,native_stop=lambda:self.native,
         s03_append_readback=lambda session,agenda:self.saved.append(agenda) or True)
    def test_native_false_allows_one_boot_and_one_existing_tick(self):
        self.assertEqual(self.engine.boot('owner',now=NOW)['state'],'RESEARCH_READY_FOR_EXISTING_IDLE_TICK')
        self.assertEqual(len(self.saved),1)
        self.engine.tick('owner',now=NOW)
        self.assertEqual(self.swarm.ticks,1)
    def test_native_true_blocks_no_write_no_fetch(self):
        self.native=True
        self.assertEqual(self.engine.boot('owner',now=NOW)['state'],'STOPPED_BEFORE_BOOT')
        self.assertFalse(self.saved);self.assertEqual(self.swarm.toggle_calls,0)
    def test_none_or_truthy_string_never_grants_consent(self):
        for bad in (None,0,1,'False','true',[],{}):
            with self.subTest(bad=bad):
                self.native=bad
                self.assertEqual(self.engine.boot('owner',now=NOW)['state'],'NATIVE_STOP_UNAVAILABLE')
                self.assertFalse(self.saved);self.assertFalse(self.swarm.enabled)
    def test_native_stop_callback_error_fails_closed(self):
        self.engine._stop=lambda:(_ for _ in ()).throw(ConnectionError('owner lost'))
        self.assertEqual(self.engine.boot('owner',now=NOW)['state'],'NATIVE_STOP_UNAVAILABLE')
        self.assertEqual(self.swarm.toggle_calls,0)
    def test_stop_during_s03_readback_never_enables(self):
        def persist(session,agenda):
            self.saved.append(agenda);self.native=True;return True
        self.engine._persist=persist
        self.assertEqual(self.engine.boot('owner',now=NOW)['state'],'STOPPED_BEFORE_BOOT')
        self.assertFalse(self.swarm.enabled);self.assertEqual(self.swarm.toggle_calls,0)
    def test_stop_during_policy_read_for_tick_blocks_network(self):
        self.engine.boot('owner',now=NOW)
        def policy(session):
            self.native=True
            return self.policy
        self.engine._policy=policy
        self.assertEqual(self.engine.tick('owner',now=NOW)['reason'],'STOP_OR_SCOPE_HOLD')
        self.assertEqual(self.swarm.ticks,0)
    def test_native_stop_bridge_lost_after_boot_blocks_tick(self):
        self.engine.boot('owner',now=NOW)
        self.engine._stop=lambda:None
        self.assertEqual(self.engine.tick('owner',now=NOW)['reason'],'NATIVE_STOP_UNAVAILABLE')
        self.assertEqual(self.swarm.ticks,0)
    def test_reject_naive_tick_clock_without_crash(self):
        self.engine.boot('owner',now=NOW)
        self.assertEqual(self.engine.tick('owner',now=NOW.replace(tzinfo=None))['reason'],'UTC_NOW_REQUIRED')
        self.assertEqual(self.swarm.ticks,0)
    def test_scope_cannot_reuse_other_tenant_boot(self):
        self.engine.boot('owner',now=NOW)
        self.assertEqual(self.engine.tick('other',now=NOW)['reason'],'STOP_OR_SCOPE_HOLD')
        self.assertEqual(self.swarm.ticks,0)
if __name__=='__main__':unittest.main()
