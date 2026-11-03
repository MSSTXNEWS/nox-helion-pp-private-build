"""M2.3 isolation and STOP. Includes the old shared-list failure mode."""
from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path

from helion.m23_persona_stop import TurnGate, legacy_shared_transcript
from helion.personas import PERSONAS


class PersonaIsolationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'buckets.sqlite3'
        self.p1 = PERSONAS[0].persona_id
        self.p2 = PERSONAS[1].persona_id
        self.gate = TurnGate(self.path)

    def test_old_shared_list_leaks_other_persona(self):
        shared = []
        shared.append({'persona_id': self.p1, 'body': 'ALPHA_SECRET'})
        shared.append({'persona_id': self.p2, 'body': 'BETA_SECRET'})
        viewed = legacy_shared_transcript(shared, self.p1)
        self.assertTrue(any(row['body'] == 'BETA_SECRET' for row in viewed))
        self.assertEqual(len(viewed), 2)

    def test_buckets_do_not_repeat_the_shared_list_leak(self):
        self.gate.switch_persona(self.p1)
        self.gate.record_user(self.p1, 'ALPHA_SECRET')
        self.gate.remember(self.p1, 'MEMORY_ALPHA')
        self.gate.switch_persona(self.p2)
        self.gate.record_user(self.p2, 'BETA_SECRET')
        visible = self.gate.buckets.history(self.p1)
        bodies = [row['body'] for row in visible]
        self.assertEqual([row['persona_id'] for row in visible], [self.p1, self.p1])
        self.assertIn('ALPHA_SECRET', bodies)
        self.assertIn('MEMORY_ALPHA', bodies)
        self.assertNotIn('BETA_SECRET', bodies)
        shown = [row['body'] for row in self.gate.switch_persona(self.p2)]
        self.assertEqual(shown, ['BETA_SECRET'])
        self.assertNotIn('ALPHA_SECRET', shown)

    def test_switch_does_not_write_into_the_other_persona(self):
        self.gate.switch_persona(self.p1)
        with self.assertRaises(PermissionError):
            self.gate.record_user(self.p2, 'CROSS_WRITE')
        with self.assertRaises(PermissionError):
            self.gate.remember(self.p2, 'CROSS_MEMORY')
        self.assertEqual(self.gate.buckets.history(self.p2), [])
        self.assertEqual(self.gate.buckets.history(self.p1), [])

    def test_persistence_survives_restart_per_persona(self):
        self.gate.switch_persona(self.p1)
        self.gate.record_user(self.p1, 'KEEP_A')
        self.gate.switch_persona(self.p2)
        self.gate.remember(self.p2, 'KEEP_B')
        reopened = TurnGate(self.path)
        reopened.switch_persona(self.p1)
        self.assertEqual([row['body'] for row in reopened.buckets.history(self.p1)], ['KEEP_A'])
        self.assertEqual([row['body'] for row in reopened.buckets.history(self.p2)], ['KEEP_B'])
        self.assertEqual(reopened.chips()['persona_id'], self.p1)
        self.assertNotIn('KEEP_B', [row['body'] for row in reopened.buckets.history(self.p1)])


class StopGuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.p1 = PERSONAS[0].persona_id
        self.p2 = PERSONAS[1].persona_id
        self.gate = TurnGate(Path(self.tmp.name) / 'stop.sqlite3')
        self.gate.switch_persona(self.p1)

    def test_stop_blocks_send(self):
        self.gate.halt()
        with self.assertRaises(PermissionError) as raised:
            self.gate.record_user(self.p1, 'NOPE')
        self.assertEqual(str(raised.exception), 'stop_blocks_send')
        with self.assertRaises(PermissionError):
            self.gate.begin_turn(self.p1, 'NOPE')
        self.assertEqual(self.gate.buckets.history(self.p1), [])
        self.assertEqual(self.gate.chips()['state'], 'HALTED')
        self.assertFalse(self.gate.chips()['live_ai'])
        self.assertEqual(self.gate.chips()['ai'], 'NOT_LIVE')

    def test_inflight_cancel(self):
        generation = self.gate.begin_turn(self.p1, 'QUESTION')
        self.assertTrue(self.gate.chips()['inflight'])
        self.assertEqual(self.gate.chips()['state'], 'IN_FLIGHT')
        receipt = self.gate.halt()
        self.assertEqual(receipt['cancelled_generation'], generation)
        self.assertIsNone(self.gate.inflight)
        self.assertTrue(self.gate.halted)
        self.assertFalse(self.gate.input_enabled)

    def test_late_write_forbidden(self):
        generation = self.gate.begin_turn(self.p1, 'QUESTION')
        box = {}
        started = threading.Event()
        release = threading.Event()

        def late():
            started.set()
            self.assertTrue(release.wait(2))
            box['ok'] = self.gate.try_commit_assistant(
                self.p1, 'LATE_SECRET', generation,
                source='stub_callback_not_live_ai')

        worker = threading.Thread(target=late)
        worker.start()
        self.assertTrue(started.wait(2))
        self.gate.halt()
        release.set()
        worker.join(timeout=2)
        self.assertFalse(box['ok'])
        bodies = [row['body'] for row in self.gate.buckets.history(self.p1)]
        self.assertIn('QUESTION', bodies)
        self.assertNotIn('LATE_SECRET', bodies)
        self.assertGreaterEqual(self.gate.late_rejects, 1)
        self.assertFalse(self.gate.try_commit_assistant(
            self.p1, 'LIVE_FAKE', generation, source='live_ai'))
        self.assertNotIn('LIVE_FAKE', [row['body'] for row in self.gate.buckets.history(self.p1)])

    def test_resume_reenables_input(self):
        generation = self.gate.begin_turn(self.p1, 'QUESTION')
        self.gate.halt()
        self.assertFalse(self.gate.try_commit_assistant(
            self.p1, 'LATE_SECRET', generation, source='stub_callback_not_live_ai'))
        resumed = self.gate.resume()
        self.assertEqual(resumed['state'], 'READY')
        self.assertTrue(self.gate.input_enabled)
        self.assertFalse(self.gate.halted)
        follow = self.gate.begin_turn(self.p1, 'AFTER_RESUME')
        self.assertGreater(follow, 0)
        self.assertTrue(self.gate.try_commit_assistant(
            self.p1, 'STUB_REPLY', follow, source='stub_callback_not_live_ai'))
        bodies = [row['body'] for row in self.gate.buckets.history(self.p1)]
        self.assertIn('AFTER_RESUME', bodies)
        self.assertIn('STUB_REPLY', bodies)
        self.assertNotIn('LATE_SECRET', bodies)
        self.assertEqual(self.gate.chips()['ai'], 'NOT_LIVE')
        self.assertEqual(self.gate.chips()['state'], 'READY')

    def test_switch_during_inflight_drops_late_reply(self):
        generation = self.gate.begin_turn(self.p1, 'QUESTION')
        self.gate.switch_persona(self.p2)
        accepted = self.gate.try_commit_assistant(
            self.p1, 'LATE_TO_OLD', generation, source='stub_callback_not_live_ai')
        self.assertFalse(accepted)
        self.assertNotIn('LATE_TO_OLD', [row['body'] for row in self.gate.buckets.history(self.p1)])
        self.assertNotIn('LATE_TO_OLD', [row['body'] for row in self.gate.buckets.history(self.p2)])


class HudTests(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        try:
            self.root = tk.Tk()
        except tk.TclError:
            self.skipTest('DISPLAY_UNAVAILABLE')
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(self.root.destroy)
        self.p1 = PERSONAS[0].persona_id
        self.p2 = PERSONAS[1].persona_id
        self.gate = TurnGate(Path(self.tmp.name) / 'hud.sqlite3')
        from helion.m23_hud import PersonaStopHud

        def physical():
            self.gate.halt()
            self.hud.show_halted()

        def resume():
            self.gate.resume()
            self.hud.show_ready()

        self.hud = PersonaStopHud(self.root, self.gate, physical_stop=physical,
                                  resume=resume, reduced_motion=True)
        self.root.bind_all('<Alt-s>', lambda _event: physical() or 'break')
        self.root.bind_all('<Alt-S>', lambda _event: physical() or 'break')
        self.root.update()

    def test_panel_isolates_persona_history(self):
        self.gate.switch_persona(self.p1)
        self.hud.entry.insert(0, 'ALPHA_SECRET')
        self.hud._record()
        self.gate.switch_persona(self.p2)
        self.hud.animate_to(self.p2)
        self.root.update()
        shown = list(self.hud.history.get(0, 'end'))
        self.assertTrue(all('ALPHA_SECRET' not in line for line in shown))
        self.assertEqual(self.hud.chips['state'].cget('text'), self.gate.chips()['state'])
        self.assertEqual(self.hud.chips['ai'].cget('text'), 'NOT_LIVE')

    def test_stop_button_alt_s_and_resume(self):
        self.gate.switch_persona(self.p1)
        generation = self.gate.begin_turn(self.p1, 'QUESTION')
        self.hud.refresh()
        self.assertEqual(self.hud.chips['state'].cget('text'), 'IN_FLIGHT')
        self.hud.stop_button.invoke()
        self.root.update()
        self.assertTrue(self.gate.halted)
        self.assertEqual(self.hud.chips['state'].cget('text'), 'HALTED')
        self.assertEqual(self.hud.entry.cget('state'), 'disabled')
        self.assertFalse(self.gate.try_commit_assistant(
            self.p1, 'LATE_SECRET', generation, source='stub_callback_not_live_ai'))
        self.hud.resume_button.invoke()
        self.root.update()
        self.assertFalse(self.gate.halted)
        self.assertEqual(self.hud.entry.cget('state'), 'normal')
        self.assertEqual(self.hud.chips['ai'].cget('text'), 'NOT_LIVE')
        self.gate.begin_turn(self.p1, 'SECOND')
        self.root.focus_force()
        self.root.update()
        self.root.event_generate('<Alt-s>')
        self.root.update()
        self.assertTrue(self.gate.halted)
        self.assertIsNone(self.gate.inflight)


class ShellBindingTests(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        try:
            self.root = tk.Tk()
        except tk.TclError:
            self.skipTest('DISPLAY_UNAVAILABLE')
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        def _destroy_root():
            try:
                if self.root.winfo_exists():
                    self.root.destroy()
            except Exception:
                return
        self.addCleanup(_destroy_root)

    def test_desktop_alt_s_and_stop_block_late_session_write(self):
        from helion.app import build_routes
        from helion.e08_desktop_ui import E08Desktop
        from helion.storage import Store
        data = Path(self.tmp.name)
        store = Store(data / 'helion.sqlite3')
        self.addCleanup(store.close)
        ui = E08Desktop(self.root, store, build_routes(store), data_dir=data)
        self.addCleanup(lambda: ui.close() if not ui._closed else None)
        self.root.update()
        persona = ui.persona.get()
        ui.m23_gate.switch_persona(persona)
        generation = ui._poll_generation + 1
        ui.m23_gate.arm_inflight(persona, generation)
        ui.m23_physical_stop()
        self.root.update()
        self.assertTrue(ui.m23_gate.halted)
        self.assertFalse(ui.m23_gate.allow_assistant_write(persona, generation))
        self.assertEqual(ui.m23_hud.chips['state'].cget('text'), 'HALTED')
        self.assertEqual(ui.m23_hud.chips['ai'].cget('text'), 'NOT_LIVE')
        before = len(ui.m23_gate.buckets.history(persona))
        self.assertFalse(ui.m23_gate.try_commit_assistant(
            persona, 'LATE_SHELL', generation, source='stub_callback_not_live_ai'))
        self.assertEqual(len(ui.m23_gate.buckets.history(persona)), before)
        ui.m23_resume()
        self.root.update()
        self.assertFalse(ui.m23_gate.halted)
        self.assertEqual(ui.m23_hud.entry.cget('state'), 'normal')
        other = next(p.persona_id for p in PERSONAS if p.persona_id != persona)
        ui.m23_gate.record_user(persona, 'SHELL_ALPHA')
        ui.persona.set(other)
        self.root.update()
        shown = list(ui.m23_hud.history.get(0, 'end'))
        self.assertTrue(all('SHELL_ALPHA' not in line for line in shown))
        self.assertIn('SHELL_ALPHA', [row['body'] for row in ui.m23_gate.buckets.history(persona)])


if __name__ == '__main__':
    unittest.main()
