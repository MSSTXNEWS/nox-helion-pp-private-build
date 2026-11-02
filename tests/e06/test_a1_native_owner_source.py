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

if __name__ == "__main__":
    unittest.main()
