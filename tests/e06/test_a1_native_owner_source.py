"""A.1 owner activation must use ORIGINAL WPF/pipe, signed owner callbacks, STOP and archive data SHA."""
import hashlib
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
def blob(path):
    b = path.read_bytes()
    return hashlib.sha1(b"blob " + str(len(b)).encode() + b"\0" + b).hexdigest()

class A1NativeSource(unittest.TestCase):
    def test_owner_gates_and_archive(self):
        owner = (ROOT / "coordination/e06/e06_native_stdio_owner.py").read_text("utf-8")
        stage = (ROOT / "coordination/e06/stage_native_stdio.py").read_text("utf-8")
        wpf = (ROOT / "coordination/e06/MainWindow.NativeP02.cs").read_text("utf-8")
        builder = (ROOT / "private_build.ps1").read_text("utf-8")
        self.assertIn("A1_NATIVE_SIGNED_COMPONENTS_FACTORY_HOLD", owner)
        self.assertIn('a1_command.invoke(session, {"action": action}, now=datetime.now(timezone.utc))', owner)
        self.assertIn("grant(session, \"evolution.autonomy.read\", {})", owner)
        # The private WPF HMAC ticket is verified and consumed inside the
        # original native ingress; it must not reach the selfbuilder command.
        self.assertIn('a1_wpf_proof.verify(ticket, action) is not True', owner)
        self.assertIn('if set(args) != {"action", "a1_wpf_ticket"}:', owner)
        self.assertIn('CreateA1PrivateConsentReceipt(a1Name)', wpf)
        self.assertIn('_a1OwnerApprovedAction=null; // WPF approval is consumed once.', wpf)
        self.assertIn('NOX_A1_WPF_OWNER_KEY', wpf)
        self.assertIn('NOX_A1_WPF_OWNER_KEY', owner)
        self.assertIn('A1_WPF_OWNER_NONCE_REPLAY', (ROOT / "src/nox_selfbuilder/a1_wpf_owner_proof.py").read_text("utf-8"))
        self.assertIn('a1_wpf_owner_proof.py', stage)
        self.assertIn("source_head=builder.source.head", owner)
        self.assertIn("stop_epoch=lambda: adapter._stop_epoch", owner)
        self.assertIn("native_a_owner_components=None", owner)
        self.assertIn("A1_OWNER_NATIVE_COMMAND_SOURCE_SHA_REQUIRED", builder)
        self.assertIn("'--hidden-import','nox_selfbuilder.a1_native_command'", builder)
        for action in ("selfbuilder.a1.status", "selfbuilder.a1.boot", "selfbuilder.a1.tick"):
            self.assertIn(action, owner)
            self.assertIn(action, wpf)
        self.assertIn("payload.EnumerateObject().Count() != 1", wpf)
        self.assertIn("or dest == \"nox_selfbuilder/a1_native_command.py\"", stage)
        self.assertIn("or dest == \"nox_selfbuilder/a1_existing_components.py\"", stage)
        self.assertIn("build_existing_a1_command(builder, owner_ports)", owner)
        self.assertIn("A1_NATIVE_SIGNED_OWNER_PORTS_HOLD", owner)
        self.assertIn("native_a_owner_components=native_a_owner_components", owner)
        self.assertIn("A1_R2_NATIVE_COMPONENTS_SOURCE_SHA_REQUIRED", builder)
        self.assertIn("'--hidden-import','nox_selfbuilder.a1_existing_components'", builder)
        owner_pin = re.findall(r"\('coordination/e06/e06_native_stdio_owner.py', 'helion/e06_native_stdio_owner.py', '([0-9a-f]{40})'\)", stage)
        donor_pin = re.findall(r"\('src/nox_selfbuilder/a1_native_command.py', 'nox_selfbuilder/a1_native_command.py', '([0-9a-f]{40})'\)", stage)
        self.assertEqual(owner_pin, [blob(ROOT / "coordination/e06/e06_native_stdio_owner.py")])
        self.assertEqual(donor_pin, [blob(ROOT / "src/nox_selfbuilder/a1_native_command.py")])
        factory_pin = re.findall(r"\('src/nox_selfbuilder/a1_existing_components.py', 'nox_selfbuilder/a1_existing_components.py', '([0-9a-f]{40})'\)", stage)
        self.assertEqual(factory_pin, [blob(ROOT / "src/nox_selfbuilder/a1_existing_components.py")])


class A1StopRevokesNativeTicket(unittest.TestCase):
    """Execute the exact original nested STOP method without another host."""

    def _actual_stop(self, *, failed=False):
        source = (ROOT / "coordination/e06/e06_native_stdio_owner.py").read_text("utf-8")
        start = source.index("    def stop(session, args):\n")
        end = source.index("    for route, method in ((", start)
        original = source[start:end]
        program = ("def outer(adapter, stop_hooks, a1_wpf_proof):\n" +
                   original +
                   "    def peek():\n        return a1_wpf_proof\n" +
                   "    return stop, peek\n")
        namespace = {}
        exec(compile(program, "<original-nested-STOP>", "exec"), namespace)
        class Adapter:
            epoch = 0
            def stop(self, session, args):
                self.epoch += 1
                if failed:
                    raise RuntimeError("injected STOP error")
                return {"status": "STOPPED"}
        adapter = Adapter()
        hooks = []
        stop, peek = namespace["outer"](adapter, [lambda: hooks.append("called")], object())
        return stop, peek, adapter, hooks

    def test_stop_then_reset_never_reuses_old_wpf_ticket(self):
        stop, peek, adapter, hooks = self._actual_stop()
        self.assertIsNotNone(peek())
        self.assertEqual(stop(None, {}), {"status": "STOPPED"})
        self.assertIsNone(peek())
        self.assertEqual(adapter.epoch, 1)
        self.assertEqual(hooks, ["called"])
        self.assertIsNone(peek())  # Later STOP reset cannot restore ticket.

    def test_stop_failure_still_revokes_owner_proof(self):
        stop, peek, adapter, hooks = self._actual_stop(failed=True)
        with self.assertRaisesRegex(RuntimeError, "injected STOP error"):
            stop(None, {})
        self.assertIsNone(peek())
        self.assertEqual(adapter.epoch, 1)
        self.assertEqual(hooks, ["called"])


class A1FirstBootSharedStopClock(unittest.TestCase):
    """Exercise original A1 assembly: either native STOP witness denies FirstBoot."""

    def test_firstboot_never_ignores_owner_stop_or_epoch_divergence(self):
        import ast
        from dataclasses import dataclass, replace
        from types import SimpleNamespace
        source = (ROOT / "src/nox_selfbuilder/a1_existing_components.py").read_text("utf-8")
        function = next(x for x in ast.parse(source).body
                        if isinstance(x, ast.FunctionDef) and x.name == "build_existing_a1_command")

        @dataclass(frozen=True)
        class FirstBootPorts:
            stopped: object
            stop_epoch: object

        class OwnerPorts:
            def __init__(self):
                self.halted = False
                self.epoch = 0
                self.firstboot_halted = False
                self.firstboot_epoch = 0
                self.stopped = lambda: self.halted
                self.stop_epoch = lambda: self.epoch
                self.native_firstboot = FirstBootPorts(
                    lambda: self.firstboot_halted, lambda: self.firstboot_epoch)
                self.approved_providers = lambda session: ({}, {})
                self.authorize = lambda session, action: True

            def verify(self):
                return True

            def __getattr__(self, key):
                return lambda *args, **kwargs: None

        namespace = {
            "ExistingA1OwnerPorts": OwnerPorts, "A1OwnerPortsHold": PermissionError,
            "replace": replace,
            "WormSwarm": lambda **kwargs: object(),
            "WormAutopilot": lambda **kwargs: object(),
            "NativeIdeaLoop": lambda **kwargs: object(),
            "A1InitiativeBridge": lambda **kwargs: object(),
            "FirstBootCoordinator": lambda callbacks: SimpleNamespace(callbacks=callbacks),
            "A1NativeCommand": lambda **kwargs: SimpleNamespace(_components=kwargs["components"]),
        }
        exec(compile(ast.Module(body=[function], type_ignores=[]),
                     "<original-A1-owner-assembly>", "exec"), namespace)
        owner = OwnerPorts()
        command = namespace["build_existing_a1_command"](object(), owner)
        callbacks = command._components("test-session")["firstboot"].callbacks
        self.assertIs(callbacks.stopped(), False)
        self.assertEqual(callbacks.stop_epoch(), 0)
        owner.halted = True
        self.assertIs(callbacks.stopped(), True)
        owner.halted = False
        owner.firstboot_halted = True
        self.assertIs(callbacks.stopped(), True)
        owner.firstboot_halted = False
        owner.epoch = 1
        with self.assertRaisesRegex(PermissionError, "A1_NATIVE_FIRSTBOOT_STOP_EPOCH_MISMATCH"):
            callbacks.stop_epoch()
        owner.firstboot_epoch = 1
        self.assertEqual(callbacks.stop_epoch(), 1)


class A1BootFailedLeaseRollback(unittest.TestCase):
    """Runs the ORIGINAL nested Python command with isolated denial callbacks.

    Synthetic callbacks here test rejection only. They do not attest Windows
    SID, WPF private pipe, native policy, or a working production FirstBoot.
    """
    def _command(self, failed):
        import ast
        import threading
        from datetime import datetime, timezone
        source = (ROOT / "coordination/e06/e06_native_stdio_owner.py").read_text("utf-8")
        fn = next(n for n in ast.walk(ast.parse(source))
                  if isinstance(n, ast.FunctionDef) and n.name == "command")
        leases = {}
        class Session:
            chat_id = "isolated-original-chat"
        class WpfProof:
            def verify(self, ticket, action):
                return ticket == "test-only-ticket" and action == "selfbuilder.a1.boot"
        class NativeCommand:
            def invoke(self, session, args, *, now):
                if failed:
                    raise PermissionError("A1_NATIVE_SIGNED_COMPONENTS_FACTORY_HOLD")
                return {"schema": "NOX-A-NATIVE-BOOT-v1",
                        "state": "READY_FOR_EXISTING_IDLE_TICK"}
        def owner_grant(session, action, args):
            leases[(session.chat_id, action)] = 7
        namespace = {
            "select_scope": lambda s, a: (s, a),
            "a1_wpf_proof": WpfProof(),
            "grant": owner_grant,
            "a1_command": NativeCommand(),
            "lease_lock": threading.Lock(),
            "leases": leases,
            "A1NativeHold": PermissionError,
            "datetime": datetime,
            "timezone": timezone,
        }
        exec(compile(ast.Module(body=[fn], type_ignores=[]),
                     "<original-A1-native-command>", "exec"), namespace)
        return namespace["command"], Session(), leases

    def test_missing_factory_revokes_research_lease(self):
        command, session, leases = self._command(failed=True)
        with self.assertRaisesRegex(PermissionError, "A1_NATIVE_SIGNED_COMPONENTS_FACTORY_HOLD"):
            command(session, {"action": "selfbuilder.a1.boot",
                              "a1_wpf_ticket": "test-only-ticket"})
        self.assertNotIn((session.chat_id, "evolution.autonomy.read"), leases)

    def test_successful_one_shot_retains_original_lease(self):
        command, session, leases = self._command(failed=False)
        response = command(session, {"action": "selfbuilder.a1.boot",
                                     "a1_wpf_ticket": "test-only-ticket"})
        self.assertEqual(response["state"], "READY_FOR_EXISTING_IDLE_TICK")
        self.assertEqual(leases[(session.chat_id, "evolution.autonomy.read")], 7)



class A1NativeConsentEpochRace(unittest.TestCase):
    """Exercise the actual nested original native lease grant, not a mock host."""

    def _grant(self, *, interrupted=False, principal="owner", valid=True):
        import ast
        import threading
        from types import SimpleNamespace
        src = (ROOT / "coordination/e06/e06_native_stdio_owner.py").read_text("utf-8")
        methods = [n for n in ast.walk(ast.parse(src))
                   if isinstance(n, ast.FunctionDef) and n.name == "grant"]
        self.assertEqual(len(methods), 1)
        adapter = SimpleNamespace(_stop_epoch=7, stop_event=threading.Event())
        adapter.stop_event.set()
        leases, prompts = {}, []

        class Session:
            tenant = "local"
            chat_id = "real-private-frame"
            def __init__(self):
                self.principal = principal
            def validate(self):
                if not valid:
                    raise PermissionError("NATIVE_SESSION_INVALID")

        def native_approve(session, action, args):
            prompts.append(action)
            if interrupted:
                adapter._stop_epoch += 1  # STOP during the real consent callback.
            return True

        scope = {"native_approve": native_approve, "adapter": adapter,
                 "queue": SimpleNamespace(is_busy=lambda: False),
                 "principal": "owner", "lease_lock": threading.Lock(),
                 "leases": leases}
        exec(compile(ast.Module(body=methods, type_ignores=[]),
                     "<original-native-grant>", "exec"), scope)
        return scope["grant"], Session(), leases, prompts, adapter

    def test_stop_during_consent_cannot_grant_post_stop_lease(self):
        grant, session, leases, prompts, adapter = self._grant(interrupted=True)
        with self.assertRaisesRegex(PermissionError, "E06_NATIVE_CONSENT_STOP_RACE_HOLD"):
            grant(session, "selfbuilder.worker.start", {})
        self.assertEqual(leases, {})
        self.assertTrue(adapter.stop_event.is_set())
        self.assertEqual(prompts, ["selfbuilder.worker.start"])

    def test_foreign_principal_never_reaches_native_approve(self):
        grant, session, leases, prompts, adapter = self._grant(principal="foreign")
        with self.assertRaisesRegex(PermissionError, "E06_NATIVE_OWNER_SCOPE_REQUIRED"):
            grant(session, "selfbuilder.worker.start", {})
        self.assertEqual(leases, {})
        self.assertEqual(prompts, [])

    def test_invalid_native_session_never_reaches_native_approve(self):
        grant, session, leases, prompts, adapter = self._grant(valid=False)
        with self.assertRaisesRegex(PermissionError, "NATIVE_SESSION_INVALID"):
            grant(session, "selfbuilder.worker.start", {})
        self.assertEqual(leases, {})
        self.assertEqual(prompts, [])

    def test_same_epoch_fresh_consent_keeps_original_worker_actions(self):
        grant, session, leases, prompts, adapter = self._grant()
        grant(session, "selfbuilder.worker.start", {})
        for action in ("selfbuilder.propose", "selfbuilder.worker.start",
                       "selfbuilder.coding.generate", "selfbuilder.reflect",
                       "selfbuilder.proposal.persist"):
            self.assertEqual(leases[(session.chat_id, action)], 7)
        self.assertFalse(adapter.stop_event.is_set())
        self.assertEqual(prompts, ["selfbuilder.worker.start"])


if __name__ == "__main__":
    unittest.main()
